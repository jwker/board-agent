"""Deep Agents 引擎骨架：构建 agent、checkpointer 接入（TECH-DESIGN §1/§3）。

- create_deep_agent 返回 LangGraph 编译图，天然支持 .ainvoke / .astream_events
- checkpointer 用 AsyncPostgresSaver（PG 持久化，按 thread_id 区分卡片会话）
- 同一编译图 + 不同 thread_id 即可并发处理多卡片
"""

import logging
from typing import Any

from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings

logger = logging.getLogger(__name__)

# 卡片任务基础系统提示：只干活、按卡片要求执行，结果以评论形式输出
BASE_SYSTEM_PROMPT = """你是看板 Agent 中的任务执行者。你的工作对象是一张卡片上的任务。

规则：
1. 先理解卡片主题与内容，明确目标、验收标准和约束。
2. 需要动手的编程任务：在项目授权目录内完成实现，遵循项目现有结构与代码风格。
3. 破坏性动作（运行命令、写项目外文件等）不得擅自执行，先询问用户。
4. 完成后用一句话总结做了什么、结果如何、遗留什么；不要长篇大论。
5. 遇到不确定或需求冲突时，向用户提问澄清，不要臆测。"""

_checkpointer: AsyncPostgresSaver | None = None


def _pg_dsn() -> str:
    """AsyncPostgresSaver 用 psycopg 协议，需去掉 asyncpg 方言。"""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def create_checkpointer() -> AsyncPostgresSaver:
    """创建并初始化 PG checkpointer（进程内单例，首次调用建表）。"""
    global _checkpointer
    if _checkpointer is None:
        cm = AsyncPostgresSaver.from_conn_string(_pg_dsn())
        saver = await cm.__aenter__()
        await saver.setup()  # 自动创建 checkpoints / checkpoint_writes 等表
        _checkpointer = saver
        logger.info("checkpointer ready (db=%s)", settings.database_url.split("@")[-1])
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
