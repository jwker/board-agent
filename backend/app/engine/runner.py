"""3.3 执行模型（简单版）：进行中触发 → 后台执行 → AI 评论回帖。

上下文组装（TECH-DESIGN §3 不变式）：
① L1 简报（build_system_prompt：项目介绍 + 卡片索引 + AGENT.md）
② 当前卡片主体（标题/内容/验收标准/备注）
③ 近期评论流（最近 N 条正序，简单版不全量）

并发：3.3 简单版直接 asyncio 后台任务；信号量/队列在阶段 4 细化。
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.event_bus import Event, EventType, bus
from app.db.enums import CommentAuthor, ExecutionStatus
from app.db.models import Card, Comment, Execution, Project
from app.engine.agent import build_agent, create_checkpointer
from app.engine.models import ModelConfigError, resolve_chat_model
from app.engine.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# AI 评论内容上限（防止超长回复撑爆评论）
AI_COMMENT_MAX = 4000


def thread_id_for(card_id: int) -> str:
    """一卡一线程（checkpoint 会话标识）。"""
    return f"card-{card_id}"


def _card_task_instruction(card: Card, new_comments: list[Comment]) -> str:
    """组装当前卡片任务指令：卡片主体（每次带，保证最新）+ 增量评论流。

    new_comments 是"上次执行之后新增的评论"（增量），避免历史评论随每次
    执行重复叠加进上下文（重复内容会让 token 线性膨胀、稀释注意力）。
    """
    parts = [
        f"本次任务卡片 #{card.id}：{card.title}",
        f"内容：{card.content}",
    ]
    if card.acceptance_criteria:
        parts.append(f"验收标准：{card.acceptance_criteria}")
    if card.remark:
        parts.append(f"备注：{card.remark}")
    if new_comments:
        parts.append("新评论流（上次执行后新增，按时间顺序）：")
        for c in new_comments:
            who = "用户" if c.author == CommentAuthor.USER.value else f"AI({c.thread_id or '?'})"
            parts.append(f"- [{who}] {c.content}")
    return "\n".join(parts)


def _extract_final(result: dict) -> str:
    """从 agent invoke 结果提取最终 AI 回复。

    主 agent 调用 task 子代理后，最终 ai 消息常只是"一句话总结"，
    而子代理的详细回答在 name=task 的 tool 消息里。此时若子代理内容
    比主 agent 总结更长，优先返回子代理完整内容（问答场景需要全文）。
    """
    try:
        msgs = result.get("messages", [])
        last_ai = None
        for m in reversed(msgs):
            if getattr(m, "type", None) == "ai" and str(getattr(m, "content", "") or "").strip():
                last_ai = str(m.content).strip()
                break
        # task 子代理的详细结果（如有且更完整，覆盖一句话总结）
        for m in reversed(msgs):
            if getattr(m, "type", None) == "tool" and getattr(m, "name", None) == "task":
                tool_content = str(getattr(m, "content", "") or "").strip()
                if tool_content and (last_ai is None or len(tool_content) > len(last_ai or "")):
                    return tool_content
                break
        if last_ai:
            return last_ai
    except Exception:
        logger.debug("extract final message failed: %s", exc_info=True)
    return "（执行完成，无输出）"


async def _post_ai_comment(
    session: AsyncSession, card_id: int, thread_id: str, content: str
) -> None:
    """AI 结果以评论回帖（author=ai，thread_id 标识会话）。"""
    comment = Comment(
        card_id=card_id,
        author=CommentAuthor.AI.value,
        thread_id=thread_id,
        content=content[:AI_COMMENT_MAX],
    )
    session.add(comment)
    await session.commit()
    await bus.publish(
        Event(EventType.COMMENT_CREATED, {"card_id": card_id, "comment_id": comment.id})
    )


async def _publish_execution_status(card_id: int, status: str) -> None:
    await bus.publish(
        Event(EventType.CARD_UPDATED, {"card_id": card_id, "execution_status": status})
    )


async def execute_card(card_id: int) -> None:
    """后台执行入口：加载 → 组装 → 构建 agent → invoke → AI 回帖。全程兜底不抛出。"""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await _execute_in_session(card_id, session)
    except Exception:
        logger.exception("execute_card %s fatal", card_id)
    finally:
        await engine.dispose()


async def _execute_in_session(card_id: int, session: AsyncSession) -> None:
    card = await session.get(Card, card_id)
    if card is None:
        return
    project = (
        await session.execute(
            select(Project).options(selectinload(Project.cards)).where(Project.id == card.project_id)
        )
    ).scalar_one_or_none()
    if project is None:
        return
    comments = list(
        (
            await session.execute(
                select(Comment).where(Comment.card_id == card_id).order_by(Comment.id.asc())
            )
        ).scalars().all()
    )

    # 一卡一线程：建/复用 execution
    execution = (
        await session.execute(select(Execution).where(Execution.card_id == card_id))
    ).scalar_one_or_none()
    if execution is None:
        execution = Execution(
            card_id=card_id,
            thread_id=thread_id_for(card_id),
            status=ExecutionStatus.RUNNING.value,
        )
        session.add(execution)
    else:
        execution.status = ExecutionStatus.RUNNING.value
        execution.interrupt_payload = None
        execution.current_step = None
    await session.commit()
    await _publish_execution_status(card_id, ExecutionStatus.RUNNING.value)

    # 上下文组装：L1 简报 + 当前卡任务指令（卡片主体 + 增量评论流）
    system_prompt = build_system_prompt(project, list(project.cards))
    new_comments = [c for c in comments if c.id > (execution.last_comment_id or 0)]
    instruction = _card_task_instruction(card, new_comments)
    # 游标立即推进（无论本次成败）：历史评论已留在 checkpoint，不重复注入
    if comments:
        execution.last_comment_id = comments[-1].id

    try:
        model = await resolve_chat_model(session, project_id=project.id)
    except ModelConfigError as e:
        execution.status = ExecutionStatus.FAILED.value
        await session.commit()
        await _post_ai_comment(session, card_id, thread_id_for(card_id), f"执行失败：未配置可用模型（{e}）")
        await _publish_execution_status(card_id, ExecutionStatus.FAILED.value)
        return

    try:
        agent = build_agent(model, checkpointer=await create_checkpointer(), system_prompt=system_prompt)
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": instruction}]},
            config={"configurable": {"thread_id": thread_id_for(card_id)}},
        )
    except Exception as e:  # noqa: BLE001 - 模型/引擎异常统一落为 failed，避免卡 running
        reason = f"{type(e).__name__}: {str(e)[:300]}"
        logger.error("card %s execution failed: %s", card_id, reason)
        execution.status = ExecutionStatus.FAILED.value
        await session.commit()
        await _post_ai_comment(session, card_id, thread_id_for(card_id), f"执行失败：{reason}")
        await _publish_execution_status(card_id, ExecutionStatus.FAILED.value)
        return
    final = _extract_final(result)

    execution.status = ExecutionStatus.COMPLETED.value
    await session.commit()
    await _post_ai_comment(session, card_id, thread_id_for(card_id), final)
    await _publish_execution_status(card_id, ExecutionStatus.COMPLETED.value)
    logger.info("card %s executed ok, reply=%d chars", card_id, len(final))


def trigger_execution(card_id: int) -> None:
    """异步触发执行（不等待；由 API 层调用）。"""
    asyncio.create_task(execute_card(card_id))
