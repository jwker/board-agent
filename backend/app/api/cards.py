"""卡片 API：看板卡片 CRUD（仅用户建卡；状态迁移矩阵在 2.3 收紧）。"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.enums import CardStatus, CardType, Priority
from app.db.models import Card, Project
from app.schemas.card import CardCreate, CardOut, CardUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["cards"])


def _validate_enum(value: str, enum_cls: type, field: str) -> None:
    if value not in {e.value for e in enum_cls}:
        raise HTTPException(status_code=422, detail=f"非法{field}: {value}")


@router.get("/projects/{project_id}/cards", response_model=list[CardOut])
async def list_cards(project_id: int, session: AsyncSession = Depends(get_session)) -> list[Card]:
    """项目内全部卡片（前端按状态分组；含归档）。"""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    stmt = select(Card).where(Card.project_id == project_id).order_by(Card.id.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/projects/{project_id}/cards", response_model=CardOut, status_code=201)
async def create_card(
    project_id: int,
    body: CardCreate,
    session: AsyncSession = Depends(get_session),
) -> Card:
    """新建卡片（内容必填；标题可选，留空由 AI 自动总结，阶段 3 接入）。"""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    _validate_enum(body.card_type, CardType, "类型")
    _validate_enum(body.priority, Priority, "优先级")
    _validate_enum(body.status, CardStatus, "状态")

    card = Card(
        project_id=project_id,
        title=body.title.strip(),
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
    logger.info("card created: %s (project=%s, status=%s)", card.title, project_id, card.status)
    return card


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
    """更新卡片字段（含状态；只更新传入字段）。"""
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

    for field, value in updates.items():
        setattr(card, field, value)
    await session.commit()
    await session.refresh(card)
    return card
