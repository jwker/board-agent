"""卡片 API：看板卡片 CRUD（仅用户建卡；状态迁移矩阵在 2.3 收紧）。"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.event_bus import Event, EventType, bus
from app.db.deps import get_session
from app.db.enums import CardStatus, CardType, Priority
from app.db.models import Card, Project
from app.engine.models import ModelConfigError, resolve_tool_chat_model
from app.engine.title import fallback_title, summarize_title
from app.schemas.card import CardCreate, CardOut, CardUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["cards"])


def _validate_enum(value: str, enum_cls: type, field: str) -> None:
    if value not in {e.value for e in enum_cls}:
        raise HTTPException(status_code=422, detail=f"非法{field}: {value}")


@router.get("/projects/{project_id}/cards", response_model=list[CardOut])
async def list_cards(project_id: int, session: AsyncSession = Depends(get_session)) -> list[CardOut]:
    """项目内全部卡片（前端按状态分组；含归档）。附带 comment_count。"""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    stmt = select(Card).where(Card.project_id == project_id).order_by(Card.id.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/projects/{project_id}/cards", response_model=CardOut, status_code=201)
async def create_card(
    project_id: int,
    body: CardCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> Card:
    """新建卡片（内容必填；标题可选，留空先用兜底、后台 AI 异步精修标题）。

    异步设计：建卡立即返回（不阻塞在 LLM 上）；后台总结完成后更新标题并
    通过 WS 推送 card.updated，前端实时刷新。总结失败保留兜底标题。
    """
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    _validate_enum(body.card_type, CardType, "类型")
    _validate_enum(body.priority, Priority, "优先级")
    _validate_enum(body.status, CardStatus, "状态")

    title = body.title.strip() or fallback_title(body.content)
    card = Card(
        project_id=project_id,
        title=title,
        content=body.content,
        card_type=body.card_type,
        custom_tags=body.custom_tags or [],
        priority=body.priority,
        status=body.status,
        acceptance_criteria=body.acceptance_criteria,
        due_date=body.due_date,
        remark=body.remark,
        read_only=body.read_only or False,
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    if not body.title.strip():
        # 标题留空：后台 AI 精修（独立会话，不占用请求会话）
        background_tasks.add_task(refine_title_async, card.id, body.content)
    logger.info("card created: %s (project=%s, status=%s)", card.title, project_id, card.status)
    return card


async def refine_title_async(card_id: int, content: str) -> None:
    """后台任务：全局默认模型轻量总结标题 → 更新卡片 → WS 推送。全程兜底，失败静默。

    用任务级独立引擎（NullPool）而非共享池：后台任务可能运行在任意事件循环，
    共享池连接跨 loop 复用会抛错，独立引擎+即用即关最稳。
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await _refine_title_in_session(card_id, content, session)
    finally:
        await engine.dispose()


async def _refine_title_in_session(card_id: int, content: str, session: AsyncSession) -> None:
    """实际精修逻辑（在调用方提供的会话内执行）。"""
    try:
        card = await session.get(Card, card_id)
        if card is None or card.title != fallback_title(content):
            # 卡片已删或标题已非兜底（用户已改名）→ 不覆盖
            return
        model = await resolve_tool_chat_model(session)  # 工具模型：标题提炼走专用轻模型
        logger.info("card %s title refine using model: %s", card.id, getattr(model, "model_name", "?"))
        title = await summarize_title(content, model)
        if not title or title == card.title:
            return
        card.title = title
        await session.commit()
        await bus.publish(Event(EventType.CARD_UPDATED, {"card_id": card.id, "title": card.title}))
        logger.info("card %s title refined: %s", card.id, card.title)
    except ModelConfigError:
        logger.info("card %s title refine skipped: 未配置默认模型", card_id)
    except Exception as e:  # noqa: BLE001 - 后台任务绝不抛出
        logger.warning("card %s title refine failed: %s", card_id, e)

@router.get("/cards/{card_id}", response_model=CardOut)
async def get_card(card_id: int, session: AsyncSession = Depends(get_session)) -> Card:
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return card


@router.patch("/cards/{card_id}", response_model=CardOut)
async def update_card(
    card_id: int,
    body: CardUpdate,
    session: AsyncSession = Depends(get_session),
) -> Card:
    """更新卡片字段（含状态）。状态迁移矩阵（2.3）：
    - 四态（积压/待办/进行中/已完成）之间自由迁移，确认语义在前端
    - 归档是终态：不通过 PATCH 进入/离开，必须走 archive / restore 专用接口
    """
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")

    updates = body.model_dump(exclude_unset=True)
    if "card_type" in updates:
        _validate_enum(updates["card_type"], CardType, "类型")
    if "priority" in updates:
        _validate_enum(updates["priority"], Priority, "优先级")
    if "status" in updates:
        _validate_enum(updates["status"], CardStatus, "状态")
        if card.status == CardStatus.ARCHIVED.value:
            raise HTTPException(status_code=409, detail="已归档卡片需先恢复，才能修改状态")
        if updates["status"] == CardStatus.ARCHIVED.value:
            raise HTTPException(status_code=409, detail="归档请使用归档接口（POST /cards/{id}/archive）")

    for field, value in updates.items():
        setattr(card, field, value)
    await session.commit()
    await session.refresh(card)
    return card


@router.post("/cards/{card_id}/archive", response_model=CardOut)
async def archive_card(card_id: int, session: AsyncSession = Depends(get_session)) -> Card:
    """归档卡片（用户主动触发，终态；进行中卡片不允许归档）。"""
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if card.status == CardStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="卡片已归档")
    if card.status == CardStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=409, detail="进行中的卡片不能归档，请先移出进行中")
    card.archived_from = card.status
    card.status = CardStatus.ARCHIVED.value
    await session.commit()
    await session.refresh(card)
    logger.info("card archived: %s", card_id)
    return card


@router.post("/cards/{card_id}/restore", response_model=CardOut)
async def restore_card(card_id: int, session: AsyncSession = Depends(get_session)) -> Card:
    """恢复归档卡片（回到归档前状态，缺省回积压）。"""
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    if card.status != CardStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="卡片未归档")
    card.status = card.archived_from or CardStatus.BACKLOG.value
    card.archived_from = None
    await session.commit()
    await session.refresh(card)
    logger.info("card restored: %s -> %s", card_id, card.status)
    return card
