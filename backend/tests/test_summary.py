"""3.5 收尾总结器测试：仅总结不执行 + 组装 + 降级。"""

import pytest

from app.engine.summary import (
    COMPLETION_PROMPT,
    build_comments_text,
    summarize_completion,
)


class _FakeCard:
    title = "测试卡片"
    content = "实现登录功能"


class _FakeComment:
    def __init__(self, author: str, content: str):
        self.author = author
        self.content = content


class _FakeResp:
    def __init__(self, content: str = "", reasoning: str = ""):
        self.content = content
        self.reasoning_content = reasoning


class _FakeModel:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def ainvoke(self, messages):
        if self._exc is not None:
            raise self._exc
        return self._resp


def test_prompt_forbids_execution():
    """收尾提示词必须包含"仅总结不执行"约束（3.5 核心：防止 AI 自行开工）。"""
    assert "不要执行任何任务" in COMPLETION_PROMPT
    assert "不要调用任何工具" in COMPLETION_PROMPT
    assert "已完成" in COMPLETION_PROMPT


def test_build_comments_text():
    comments = [
        _FakeComment("user", "第一步"),
        _FakeComment("ai", "完成了"),
        _FakeComment("user", "第二步"),
    ]
    text = build_comments_text(comments)
    assert "[用户] 第一步" in text
    assert "[AI] 完成了" in text
    assert text.index("[用户] 第二步") > text.index("[AI] 完成了")


def test_build_comments_text_empty():
    assert build_comments_text([]) == "（无）"


@pytest.mark.asyncio
async def test_summarize_completion_ok():
    model = _FakeModel(_FakeResp("已完成登录功能，测试通过，无遗留问题。"))
    result = await summarize_completion(_FakeCard(), [_FakeComment("user", "做")], model)
    assert result == "已完成登录功能，测试通过，无遗留问题。"


@pytest.mark.asyncio
async def test_summarize_completion_truncates():
    model = _FakeModel(_FakeResp("长" * 500))
    result = await summarize_completion(_FakeCard(), [], model)
    assert len(result) <= 300


@pytest.mark.asyncio
async def test_summarize_completion_reasoning_fallback():
    """推理模型 content 为空时退回 reasoning_content。"""
    model = _FakeModel(_FakeResp("", reasoning="思考过程\n总结：登录完成"))
    result = await summarize_completion(_FakeCard(), [], model)
    assert "登录完成" in result


@pytest.mark.asyncio
async def test_summarize_completion_failure_returns_empty():
    """调用失败返回空串，调用方放弃回帖（不影响状态迁移）。"""
    model = _FakeModel(exc=TimeoutError("boom"))
    assert await summarize_completion(_FakeCard(), [], model) == ""


@pytest.mark.asyncio
async def test_complete_card_summary_posts_and_notifies(session, monkeypatch):
    """3.5+：收尾总结回帖完成后 → completed 站内通知。"""
    from sqlalchemy import select

    from app.db.models import Card, Comment, Project
    from app.engine import runner
    from app.services import notice_service

    calls: list[tuple] = []

    async def _fake_summarize(card, comments, model):
        return "已完成，无遗留。"

    async def _fake_comment(session, card_id, thread_id, content):
        pass

    async def _fake_notify(session, *, category, content, project_id=None, card_id=None, force=False):
        calls.append((category, content, project_id, card_id))
        return None

    async def _stub_model(*a, **k):
        return _FakeModel(_FakeResp("ok"))

    monkeypatch.setattr(runner, "resolve_chat_model", _stub_model)
    monkeypatch.setattr(runner, "summarize_completion", _fake_summarize)
    monkeypatch.setattr(runner, "_post_ai_comment", _fake_comment)
    monkeypatch.setattr(notice_service, "notify", _fake_notify)

    project = Project(name="P", description="D", agent_md="规范")
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="收尾通知", content="做点什么",
        card_type="requirement", priority="medium", status="done",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    await runner.complete_card_summary(card.id)

    assert calls, "收尾总结完成应发通知"
    category, content, pid, cid = calls[-1]
    assert category == "completed"
    assert pid == project.id
    assert cid == card.id
    assert "收尾通知" in content
