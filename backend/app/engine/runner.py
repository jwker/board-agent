"""3.3/3.4 执行模型：进行中触发 → 后台执行 → AI 评论回帖；沙箱命令审批挂起/恢复。

上下文组装（TECH-DESIGN §3 不变式）：
① L1 简报（build_system_prompt：项目介绍 + 卡片索引 + AGENT.md）
② 当前卡片主体（标题/内容/验收标准/备注）
③ 近期评论流（最近 N 条正序，增量游标 last_comment_id）

并发：3.3 简单版直接 asyncio 后台任务；信号量/队列在阶段 4 细化。

3.4 审批生命周期（TECH-DESIGN §3）：
- agent.ainvoke 遇到 execute 工具触发 HumanInTheLoopMiddleware 的 interrupt
  → 抛出 GraphInterrupt → 持久化 interrupt_payload、execution 置 waiting_approval
- 审批 API 批准/拒绝/编辑后 → resume_execution 用 Command(resume=...) 恢复同一线程
- 拒绝：模型收到 reject ToolMessage，自行换方案继续（可能再次挂起审批）
"""

import asyncio
import logging
from datetime import UTC, datetime

from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.event_bus import Event, EventType, bus
from app.db.enums import CommentAuthor, ExecutionStatus
from app.db.models import Card, Comment, Execution, Project
from app.engine.agent import build_agent, create_checkpointer
from app.engine.backends import CommandSandboxBackend, build_execute_interrupt_config
from app.engine.models import ModelConfigError, resolve_chat_model
from app.engine.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# AI 评论内容上限（防止超长回复撑爆评论）
AI_COMMENT_MAX = 4000


def thread_id_for(card_id: int) -> str:
    """一卡一线程（checkpoint 会话标识）。"""
    return f"card-{card_id}"


def _build_sandbox(project: Project) -> CommandSandboxBackend | None:
    """按项目授权目录构建命令沙箱；目录缺失/未配置时返回 None（仅对话）。"""
    if not project.directory:
        return None
    target = str(project.directory).strip()
    if not target:
        return None
    from pathlib import Path

    d = Path(target).expanduser()
    if not d.is_dir():
        logger.warning("授权目录不存在，跳过沙箱接入: %s", target)
        return None
    return CommandSandboxBackend(root_dir=str(d))


def _interrupt_from_result(result: dict) -> dict | None:
    """langgraph 1.x ainvoke 遇到 interrupt 不抛异常，而是把中断放在结果 __interrupt__ 键。

    __interrupt__ 元素形如 Interrupt(value={action_requests, review_configs}, id=...)；
    value 即 HITLRequest dict。返回 value 或 None。
    """
    intr = result.get("__interrupt__")
    if not intr:
        return None
    first = intr[0] if isinstance(intr, list) else intr
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else None


def _hitl_to_payload(hitl_request: dict) -> dict:
    """HITLRequest（interrupt 载荷）→ 可持久化 JSONB 结构。"""
    actions = []
    for req in hitl_request.get("action_requests", []):
        actions.append(
            {
                "name": req.get("name", ""),
                "args": req.get("args", {}),
                "description": req.get("description", ""),
            }
        )
    return {
        "actions": actions,
        "configs": hitl_request.get("review_configs", []),
        "saved_at": datetime.now(UTC).isoformat(),
    }


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def _park_for_approval(
    session: AsyncSession,
    execution: Execution,
    hitl_request: dict,
) -> None:
    """挂起等待审批：持久化载荷、状态置 waiting_approval、WS 推送。"""
    execution.status = ExecutionStatus.WAITING_APPROVAL.value
    execution.interrupt_payload = _hitl_to_payload(hitl_request)
    await session.commit()
    await _publish_execution_status(execution.card_id, ExecutionStatus.WAITING_APPROVAL.value)
    actions = execution.interrupt_payload.get("actions", [])
    cmds = [a["args"].get("command", "") for a in actions if a.get("name") == "execute"]
    logger.info(
        "card %s waiting approval: %d action(s), commands=%s",
        execution.card_id,
        len(actions),
        cmds,
    )


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


async def execute_card(card_id: int, session_ref: str | None = None) -> None:
    """后台执行入口：加载 → 组装 → 构建 agent → invoke → AI 回帖。全程兜底不抛出。

    session_ref: 卡片详情页临时切换的会话模型（"provider_id::model"）；None 用项目/全局默认。
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await _execute_in_session(card_id, session, session_ref)
    except asyncio.CancelledError:
        # 用户停止：取消信号向上传播，状态由 stop_execution → _mark_stopped 落库
        raise
    except Exception:
        logger.exception("execute_card %s fatal", card_id)
    finally:
        await engine.dispose()
        _running_tasks.pop(card_id, None)


async def _execute_in_session(card_id: int, session: AsyncSession, session_ref: str | None = None) -> None:
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
            model_ref=session_ref,
        )
        session.add(execution)
    else:
        execution.status = ExecutionStatus.RUNNING.value
        execution.interrupt_payload = None
        execution.current_step = None
        execution.model_ref = session_ref
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
        model = await resolve_chat_model(session, project_id=project.id, session_ref=execution.model_ref or session_ref)
        # 关键：立即结束配置读取事务。否则 build_agent → checkpointer.setup()
        # 的 CREATE INDEX CONCURRENTLY 会等待本事务结束而自锁（并发时互相等死）
        await session.commit()
    except ModelConfigError as e:
        execution.status = ExecutionStatus.FAILED.value
        await session.commit()
        await _post_ai_comment(session, card_id, thread_id_for(card_id), f"执行失败：未配置可用模型（{e}）")
        await _publish_execution_status(card_id, ExecutionStatus.FAILED.value)
        return

    try:
        sandbox = _build_sandbox(project)
        interrupt_on = {"execute": build_execute_interrupt_config()} if sandbox else None
        agent = build_agent(
            model,
            checkpointer=await create_checkpointer(),
            system_prompt=system_prompt,
            backend=sandbox,
            interrupt_on=interrupt_on,
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": instruction}]},
            config=_thread_config(thread_id_for(card_id)),
        )
        hitl = _interrupt_from_result(result)
        if hitl:
            # 命令审批挂起：保存载荷后返回，等待审批 API 恢复
            await _park_for_approval(session, execution, hitl)
            return
    except GraphInterrupt as e:
        # 兼容老版本 langgraph：异常形式的审批挂起
        await _park_for_approval(session, execution, e.value)
        return
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
    execution.interrupt_payload = None
    await session.commit()
    await _post_ai_comment(session, card_id, thread_id_for(card_id), final)
    await _publish_execution_status(card_id, ExecutionStatus.COMPLETED.value)
    logger.info("card %s executed ok, reply=%d chars", card_id, len(final))


async def resume_execution(execution_id: int, decisions: list[dict]) -> None:
    """审批后恢复同一 checkpoint 线程继续执行（Command(resume=...)）。

    - decisions: HITL 决策列表（approve / reject(message) / edit(edited_action)）
    - 再次挂起审批则继续等待；完成则回帖；异常落 failed。
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            execution = await session.get(Execution, execution_id)
            if execution is None:
                logger.warning("resume execution %s: 执行记录不存在", execution_id)
                return
            card = await session.get(Card, execution.card_id)
            if card is None:
                return
            project = (
                await session.execute(
                    select(Project).options(selectinload(Project.cards)).where(Project.id == card.project_id)
                )
            ).scalar_one_or_none()
            if project is None:
                return
            execution.status = ExecutionStatus.RUNNING.value
            await session.commit()
            await _publish_execution_status(card.id, ExecutionStatus.RUNNING.value)

            try:
                model = await resolve_chat_model(session, project_id=project.id, session_ref=execution.model_ref)
                # 关键：立即结束配置读取事务，避免 checkpointer.setup() 的
                # CREATE INDEX CONCURRENTLY 等待本事务造成自锁/互锁
                await session.commit()
            except ModelConfigError as e:
                execution.status = ExecutionStatus.FAILED.value
                await session.commit()
                await _post_ai_comment(session, card.id, execution.thread_id, f"执行失败：未配置可用模型（{e}）")
                await _publish_execution_status(card.id, ExecutionStatus.FAILED.value)
                return

            try:
                sandbox = _build_sandbox(project)
                interrupt_on = {"execute": build_execute_interrupt_config()} if sandbox else None
                agent = build_agent(
                    model,
                    checkpointer=await create_checkpointer(),
                    system_prompt=build_system_prompt(project, list(project.cards or [])),
                    backend=sandbox,
                    interrupt_on=interrupt_on,
                )
                result = await agent.ainvoke(
                    Command(resume={"decisions": decisions}),
                    config=_thread_config(execution.thread_id),
                )
                hitl = _interrupt_from_result(result)
                if hitl:
                    await _park_for_approval(session, execution, hitl)
                    return
            except GraphInterrupt as e:
                await _park_for_approval(session, execution, e.value)
                return
            except Exception as e:  # noqa: BLE001
                reason = f"{type(e).__name__}: {str(e)[:300]}"
                logger.error("card %s resume failed: %s", card.id, reason)
                execution.status = ExecutionStatus.FAILED.value
                await session.commit()
                await _post_ai_comment(session, card.id, execution.thread_id, f"执行失败：{reason}")
                await _publish_execution_status(card.id, ExecutionStatus.FAILED.value)
                return

            final = _extract_final(result)
            execution.status = ExecutionStatus.COMPLETED.value
            execution.interrupt_payload = None
            await session.commit()
            await _post_ai_comment(session, card.id, execution.thread_id, final)
            await _publish_execution_status(card.id, ExecutionStatus.COMPLETED.value)
            logger.info("card %s resumed ok, reply=%d chars", card.id, len(final))
    except Exception:
        logger.exception("resume_execution %s fatal", execution_id)
    finally:
        await engine.dispose()


# 执行任务登记：card_id -> asyncio.Task，供"停止"取消
_running_tasks: dict[int, asyncio.Task] = {}


def trigger_execution(card_id: int, session_ref: str | None = None) -> None:
    """异步触发执行（不等待；由 API 层调用）。登记任务以便停止。"""
    task = asyncio.create_task(execute_card(card_id, session_ref))
    _running_tasks[card_id] = task
    task.add_done_callback(lambda _t: _running_tasks.pop(card_id, None))


async def stop_execution(card_id: int) -> bool:
    """取消正在运行的执行任务（AI 处理中可停止）。

    返回是否有任务被取消；状态落 cancelled 由调用方（API）执行 _mark_stopped。
    """
    task = _running_tasks.get(card_id)
    if task is None or task.done():
        return False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 - 取消后任务可能带出异常，忽略
        logger.debug("stop_execution %s: task exited with error", card_id)
    return True


async def _mark_stopped(card_id: int, reason: str) -> None:
    """停止后落状态：仅当执行仍处于可取消状态（running/queued）时置 cancelled。"""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            execution = (
                await session.execute(select(Execution).where(Execution.card_id == card_id))
            ).scalar_one_or_none()
            if execution is None or execution.status not in (
                ExecutionStatus.RUNNING.value,
                ExecutionStatus.QUEUED.value,
            ):
                return
            execution.status = ExecutionStatus.CANCELLED.value
            execution.interrupt_payload = None
            await session.commit()
            await _post_ai_comment(session, card_id, execution.thread_id, reason)
            await _publish_execution_status(card_id, ExecutionStatus.CANCELLED.value)
            logger.info("card %s execution stopped (cancelled)", card_id)
    finally:
        await engine.dispose()
