"""Deep Agents 引擎骨架：构建 agent、checkpointer 接入（TECH-DESIGN §1/§3）。

- create_deep_agent 返回 LangGraph 编译图，天然支持 .ainvoke / .astream_events
- checkpointer 用 AsyncPostgresSaver（PG 持久化，按 thread_id 区分卡片会话）
- 同一编译图 + 不同 thread_id 即可并发处理多卡片
"""

import asyncio
import logging
from typing import Any

from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# 卡片任务基础系统提示：只干活、按卡片要求执行，结果以评论形式输出
# 暂不注入角色定位与行为规则：卡片主体/评论流已在任务指令中，
# 去掉"任务执行者"定位避免模型自行推断"拒绝无关提问"。
# 安全规则（破坏性动作审批等）将在阶段 4 工具/沙箱层设计，此处不前置。
BASE_SYSTEM_PROMPT = ""

_checkpointer: AsyncPostgresSaver | None = None
# from_conn_string 返回 async 上下文管理器：必须保持引用，否则被 GC 后
# 会异步执行 finally 关闭连接，导致 agent 恢复 checkpoint 时 connection closed
_checkpointer_cm: Any | None = None
# 单例创建锁：多卡片同时首次触发执行时，多个 setup() 并发执行
# CREATE INDEX CONCURRENTLY 会互相等锁挂死（langgraph MIGRATIONS 含 CONCURRENTLY）
_checkpointer_lock: asyncio.Lock | None = None


def _get_checkpointer_lock() -> asyncio.Lock:
    global _checkpointer_lock
    if _checkpointer_lock is None:
        _checkpointer_lock = asyncio.Lock()
    return _checkpointer_lock


def _pg_dsn() -> str:
    """AsyncPostgresSaver 用 psycopg 协议，需去掉 asyncpg 方言。"""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def create_checkpointer() -> AsyncPostgresSaver:
    """创建并初始化 PG checkpointer（进程内单例，首次调用建表）。

    并发安全两层：
    1. 进程内 asyncio.Lock：多卡片后台任务同时首次触发，仅一个执行 setup()
    2. PG advisory lock：跨进程互斥。langgraph setup() 会执行
       CREATE INDEX CONCURRENTLY，多进程并发时互相等锁挂死
       （uvicorn --reload 重启时旧连接残留即触发过）。
    """
    global _checkpointer
    if _checkpointer is None:
        async with _get_checkpointer_lock():
            if _checkpointer is None:
                global _checkpointer_cm
                # 跨进程互斥：session 级 advisory lock，须同一连接解锁
                lock_engine = create_async_engine(settings.database_url, poolclass=NullPool)
                async with lock_engine.connect() as lock_conn:
                    await lock_conn.execute(text("SELECT pg_advisory_lock(793106601)"))
                    # 立即结束事务：CREATE INDEX CONCURRENTLY 会等所有其他事务结束，
                    # 若此处空闲事务不提交，会把同进程的 setup() 自己等死
                    await lock_conn.commit()
                    try:
                        _checkpointer_cm = AsyncPostgresSaver.from_conn_string(_pg_dsn())
                        _checkpointer = await _checkpointer_cm.__aenter__()
                        await _checkpointer.setup()  # 自动创建 checkpoints / checkpoint_writes 等表
                        logger.info("checkpointer ready (db=%s)", settings.database_url.split("@")[-1])
                    finally:
                        await lock_conn.execute(text("SELECT pg_advisory_unlock(793106601)"))
                        await lock_conn.commit()
                await lock_engine.dispose()
    return _checkpointer


def build_agent(
    model: BaseChatModel,
    checkpointer: Any | None = None,
    tools: list | None = None,
    system_prompt: str = BASE_SYSTEM_PROMPT,
) -> Any:
    """构建单个 Deep Agent 编译图。

    - model: 解析后的 chat model 实例（三级配置见 engine/models.py）
    - checkpointer: BaseCheckpointSaver 实例（默认走 create_checkpointer，调用方需先 await）
    - tools: 阶段 3.3+ 注入卡片工具（读卡/回帖/沙箱等），当前为空
    - 返回 CompiledStateGraph；调用 .ainvoke({messages: [...]}, config={"configurable": {"thread_id": ...}})
    """
    logger.info("building deep agent (model=%s, tools=%d)", getattr(model, "model_name", model), len(tools or []))
    return create_deep_agent(
        model=model,
        tools=tools or [],
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )
