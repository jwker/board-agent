"""模型三级解析：全局默认 → 项目默认 → 会话切换（TECH-DESIGN §3）。

配置来源（settings API 存储，Setting 表 JSONB）：
- 全局：key=llm → {providers: [{id, name, base_url, api_key, models: [{display, request}]}], default: {provider_id, model}}
- 项目：key=model（scope=project）→ {provider_id, model}
- 会话：前端传 "provider_id::model_request" 字符串，查全局 providers
"""

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting

logger = logging.getLogger(__name__)


class ModelConfigError(RuntimeError):
    """模型配置缺失或不可用。"""


async def _get_global_llm(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Setting).where(Setting.scope == "global", Setting.key == "llm")
    )
    row = result.scalar_one_or_none()
    return (row.value if row else {}) or {"providers": [], "default": None}


async def _get_tool_llm(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Setting).where(Setting.scope == "global", Setting.key == "tool_llm")
    )
    row = result.scalar_one_or_none()
    return (row.value if row else {}) or {}


async def _get_project_model(session: AsyncSession, project_id: int) -> dict | None:
    result = await session.execute(
        select(Setting).where(
            Setting.scope == "project", Setting.project_id == project_id, Setting.key == "model"
        )
    )
    row = result.scalar_one_or_none()
    if row is None or not row.value:
        return None
    return row.value


def _find_provider(llm: dict, provider_id: str) -> dict:
    for p in llm.get("providers", []):
        if p.get("id") == provider_id:
            return p
    raise ModelConfigError(f"未找到模型厂商 {provider_id}，请先在全局设置中配置")


def build_chat_model(provider: dict, model_request: str, enable_thinking: bool | None = None) -> BaseChatModel:
    """按 OpenAI 兼容协议构造模型实例（支持 DeepSeek 等任意兼容厂商）。

    enable_thinking: 非空时以 extra_body 传平台特有参数（如硅基流动）；不支持的平台会忽略。
    """
    api_key = provider.get("api_key") or "sk-not-set"
    base_url = (provider.get("base_url") or "").strip() or None
    if base_url is not None and not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    kwargs: dict = {}
    if enable_thinking is not None:
        kwargs["extra_body"] = {"enable_thinking": enable_thinking}
    return ChatOpenAI(
        model=model_request,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=120,
        max_retries=1,
        **kwargs,
    )


def _resolve(
    llm: dict, project_model: dict | None = None, session_ref: str | None = None
) -> BaseChatModel:
    """三级解析核心（无 DB 依赖，便于测试）。

    session_ref 格式："{provider_id}::{model_request}"；为空串视为未指定。
    """
    if session_ref and session_ref.strip():
        provider_id, _, model_request = session_ref.strip().partition("::")
        if provider_id and model_request:
            return build_chat_model(_find_provider(llm, provider_id), model_request)

    if project_model and project_model.get("provider_id") and project_model.get("model"):
        provider = _find_provider(llm, project_model["provider_id"])
        return build_chat_model(provider, project_model["model"])

    default = llm.get("default")
    if default and default.get("provider_id") and default.get("model"):
        provider = _find_provider(llm, default["provider_id"])
        return build_chat_model(provider, default["model"])

    raise ModelConfigError("未配置默认模型，请先在全局设置 → 大模型中配置")


async def resolve_chat_model(
    session: AsyncSession, project_id: int | None = None, session_ref: str | None = None
) -> BaseChatModel:
    """对外入口：读配置后按 会话 → 项目 → 全局 顺序解析。"""
    llm = await _get_global_llm(session)
    project_model = None
    if project_id is not None:
        project_model = await _get_project_model(session, project_id)
    return _resolve(llm, project_model, session_ref)


async def resolve_tool_chat_model(session: AsyncSession) -> BaseChatModel:
    """工具模型（标题提炼等轻任务专用）：配置齐全（base_url/api_key/model）用它，否则回落全局默认。"""
    tool = await _get_tool_llm(session)
    if tool.get("base_url") and tool.get("model"):
        provider = {"base_url": tool.get("base_url", ""), "api_key": tool.get("api_key", "")}
        return build_chat_model(provider, tool["model"], tool.get("enable_thinking"))
    return await resolve_chat_model(session)
