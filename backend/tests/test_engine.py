"""AI 引擎骨架测试（3.1）：模型三级解析、标题总结、agent 构建。"""

import pytest
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.db.models import Project, Setting
from app.engine.agent import build_agent
from app.engine.models import ModelConfigError, _resolve, resolve_chat_model, resolve_tool_chat_model
from app.engine.title import fallback_title, summarize_title

LLM_CFG = {
    "providers": [
        {
            "id": "p1",
            "name": "厂商A",
            "base_url": "https://api.a.example/v1",
            "api_key": "key-a",
            "models": [{"display": "快版", "request": "a-fast"}, {"display": "强版", "request": "a-strong"}],
        },
        {
            "id": "p2",
            "name": "厂商B",
            "base_url": "",
            "api_key": "key-b",
            "models": [{"display": "默认", "request": "b-1"}],
        },
    ],
    "default": {"provider_id": "p1", "model": "a-fast"},
}


async def _seed_global(session):
    session.add(Setting(scope="global", project_id=None, key="llm", value=LLM_CFG))
    await session.commit()


async def _seed_project_model(session, project_id, value):
    session.add(Setting(scope="project", project_id=project_id, key="model", value=value))
    await session.commit()


# ---------- 模型三级解析 ----------


def test_resolve_global_default():
    m = _resolve(LLM_CFG)
    assert isinstance(m, ChatOpenAI)
    assert m.model_name == "a-fast"
    assert m.openai_api_key.get_secret_value() == "key-a"
    assert m.openai_api_base.endswith("/v1")


def test_resolve_project_override():
    m = _resolve(LLM_CFG, project_model={"provider_id": "p2", "model": "b-1"})
    assert m.model_name == "b-1"
    assert m.openai_api_key.get_secret_value() == "key-b"
    # base_url 为空 → 不强制补协议，走 OpenAI 默认端点
    assert m.openai_api_base is None or m.openai_api_base == "https://api.openai.com/v1"


def test_resolve_session_override():
    m = _resolve(LLM_CFG, project_model={"provider_id": "p2", "model": "b-1"}, session_ref="p1::a-strong")
    assert m.model_name == "a-strong"
    assert m.openai_api_key.get_secret_value() == "key-a"


def test_resolve_session_empty_falls_through():
    m = _resolve(LLM_CFG, session_ref="")
    assert m.model_name == "a-fast"


def test_resolve_no_config_raises():
    with pytest.raises(ModelConfigError):
        _resolve({"providers": [], "default": None})


def test_resolve_unknown_provider_raises():
    with pytest.raises(ModelConfigError):
        _resolve(LLM_CFG, session_ref="nope::x")


async def test_resolve_chat_model_with_db(session):
    """DB 路径：无配置 → 报错；有全局默认 → 命中。"""
    with pytest.raises(ModelConfigError):
        await resolve_chat_model(session)
    await _seed_global(session)
    m = await resolve_chat_model(session)
    assert m.model_name == "a-fast"


async def test_resolve_chat_model_project_level(session):
    await _seed_global(session)
    project = Project(name="P", directory="/tmp/x")
    session.add(project)
    await session.flush()
    await _seed_project_model(session, project.id, {"provider_id": "p2", "model": "b-1"})
    m = await resolve_chat_model(session, project_id=project.id)
    assert m.model_name == "b-1"


# ---------- 标题总结 ----------


def test_fallback_title_empty():
    assert fallback_title("") == "未命名卡片"
    assert fallback_title("   ") == "未命名卡片"


def test_fallback_title_truncates():
    t = fallback_title("这是一个非常长的卡片内容，" * 10)
    assert len(t) <= 21 and t.endswith("…")


class _FakeModel:
    def __init__(self, content="修复登录页按钮错位"):
        self._c = content

    async def ainvoke(self, messages):
        return type("R", (), {"content": self._c})()


async def test_summarize_title_ok():
    m = _FakeModel()
    title = await summarize_title("登录页按钮错位，需要修复对齐", m)
    assert title == "修复登录页按钮错位"


async def test_summarize_title_failure_falls_back():
    class _Bad:
        async def ainvoke(self, messages):
            raise RuntimeError("boom")

    title = await summarize_title("", _Bad())
    assert title == "未命名卡片"


# ---------- agent 构建 ----------


def test_build_agent_returns_graph():
    model = ChatOpenAI(model="a-fast", api_key="k", base_url="https://x/v1")
    agent = build_agent(model, checkpointer=InMemorySaver())
    assert hasattr(agent, "ainvoke") and hasattr(agent, "astream_events")


def test_build_agent_without_checkpointer():
    """不传 checkpointer 时自动创建（仅验证类型，不实际连接）。"""
    model = ChatOpenAI(model="a-fast", api_key="k", base_url="https://x/v1")
    agent = build_agent(model)
    assert hasattr(agent, "ainvoke")


# ---------- 工具模型（3.1c：标题提炼等轻任务专用） ----------


async def test_resolve_tool_model_uses_tool_config(session):
    """配置了工具模型（独立配置）→ 用它，含 enable_thinking extra_body。"""
    await _seed_global(session)
    session.add(Setting(scope="global", project_id=None, key="tool_llm",
                        value={"name": "工具", "base_url": "https://api.tool.example/v1",
                               "api_key": "key-tool", "model": "tool-fast", "enable_thinking": False}))
    await session.commit()
    m = await resolve_tool_chat_model(session)
    assert m.model_name == "tool-fast"
    assert m.openai_api_key.get_secret_value() == "key-tool"
    assert m.openai_api_base.endswith("/v1")
    assert m.extra_body == {"enable_thinking": False}


async def test_resolve_tool_model_falls_back_to_global(session):
    """未配置工具模型 → 回落全局默认。"""
    await _seed_global(session)
    m = await resolve_tool_chat_model(session)
    assert m.model_name == "a-fast"
