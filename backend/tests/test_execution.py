"""3.3 执行模型测试：触发、执行链路、AI 回帖（A1/C1 mock 策略）。"""

import asyncio

from langchain_core.messages import AIMessage

from app.db.enums import CommentAuthor, ExecutionStatus
from app.db.models import Card, Comment, Execution, Project
from app.engine.runner import _card_task_instruction, thread_id_for


class StubAgent:
    """假 agent：直接返回固定回复，不调任何模型/工具。"""

    async def ainvoke(self, messages, config=None):
        return {"messages": [AIMessage(content="已完成任务，测试通过")]}


# ---------- 上下文组装 ----------


async def test_card_task_instruction_includes_body_and_comments(session):
    project = Project(name="P", description="D", agent_md=None)
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="任务", content="实现登录",
        card_type="requirement", priority="medium", status="in_progress",
        acceptance_criteria="可登录", remark="注意安全",
    )
    session.add(card)
    await session.commit()
    comments = [
        Comment(card_id=card.id, author=CommentAuthor.USER.value, content="用户问题"),
        Comment(card_id=card.id, author=CommentAuthor.AI.value, thread_id="t1", content="AI 回复"),
    ]
    ins = _card_task_instruction(card, comments)
    assert "实现登录" in ins
    assert "验收标准：可登录" in ins
    assert "备注：注意安全" in ins
    assert "[用户] 用户问题" in ins
    assert "[AI(t1)] AI 回复" in ins


def test_extract_final_prefers_subagent_content():
    """主 agent 一句话总结时，回退取 task 子代理的完整内容。"""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.engine.runner import _extract_final

    result = {
        "messages": [
            HumanMessage(content="介绍下 react"),
            AIMessage(content="", tool_calls=[{"name": "task", "args": {}, "id": "t1", "type": "tool_call"}]),
            ToolMessage(name="task", tool_call_id="t1", content="React 是 ... 完整内容" * 10),
            AIMessage(content="一句话总结：已介绍 React。"),
        ]
    }
    out = _extract_final(result)
    assert "完整内容" in out
    assert out.startswith("React 是")


def test_extract_final_keeps_normal_ai_reply():
    """无 task 子代理时，仍取最后一条 AI 回复。"""
    from langchain_core.messages import AIMessage

    from app.engine.runner import _extract_final

    result = {"messages": [AIMessage(content="已完成任务")]}
    assert _extract_final(result) == "已完成任务"


# ---------- 执行链路（stub agent） ----------


async def test_execute_card_flow(session, monkeypatch):
    """执行成功：execution completed + AI 评论回帖 + thread_id 正确。"""
    from langchain_openai import ChatOpenAI

    from app.engine import runner

    async def _stub_model(*a, **k):
        return ChatOpenAI(model="a-fast", api_key="k", base_url="https://x/v1")

    monkeypatch.setattr(runner, "resolve_chat_model", _stub_model)
    async def _no_checkpoint():
        return None

    monkeypatch.setattr(runner, "build_agent", lambda *a, **k: StubAgent())
    monkeypatch.setattr(runner, "create_checkpointer", _no_checkpoint)

    project = Project(name="P", description="D", agent_md="规范")
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="任务", content="实现登录",
        card_type="requirement", priority="medium", status="in_progress",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    await runner._execute_in_session(card.id, session)

    # execution 记录
    exec_rows = (await session.execute(
        __import__("sqlalchemy").select(Execution).where(Execution.card_id == card.id)
    )).scalars().all()
    assert len(exec_rows) == 1
    assert exec_rows[0].status == ExecutionStatus.COMPLETED.value
    assert exec_rows[0].thread_id == thread_id_for(card.id)

    # AI 评论
    comments = list(
        (await session.execute(
            __import__("sqlalchemy").select(Comment).where(Comment.card_id == card.id)
        )).scalars().all()
    )
    assert len(comments) == 1
    assert comments[0].author == CommentAuthor.AI.value
    assert comments[0].thread_id == thread_id_for(card.id)
    assert "已完成任务" in comments[0].content


async def test_execute_card_requires_model(session, monkeypatch):
    """未配置模型 → execution failed + AI 评论说明（不崩）。"""
    from app.engine import runner
    from app.engine.models import ModelConfigError

    async def _no_model(session_, project_id=None, session_ref=None):
        raise ModelConfigError("未配置默认模型")

    monkeypatch.setattr(runner, "resolve_chat_model", _no_model)
    async def _no_checkpoint():
        return None

    monkeypatch.setattr(runner, "build_agent", lambda *a, **k: StubAgent())
    monkeypatch.setattr(runner, "create_checkpointer", _no_checkpoint)

    project = Project(name="P", description=None, agent_md=None)
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="任务", content="x",
        card_type="task", priority="low", status="in_progress",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    await runner._execute_in_session(card.id, session)

    exec_rows = (await session.execute(
        __import__("sqlalchemy").select(Execution).where(Execution.card_id == card.id)
    )).scalars().all()
    assert exec_rows[0].status == ExecutionStatus.FAILED.value
    comments = list(
        (await session.execute(
            __import__("sqlalchemy").select(Comment).where(Comment.card_id == card.id)
        )).scalars().all()
    )
    assert "执行失败" in comments[0].content


# ---------- API 触发（A1） ----------


async def test_patch_to_in_progress_triggers_execution(client, session, monkeypatch):
    """积压/待办 → 进行中：触发执行。"""
    from app.api import cards as cards_api

    project = Project(name="P", description=None, agent_md=None)
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="任务", content="x",
        card_type="task", priority="low", status="backlog",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    called: list[int] = []
    monkeypatch.setattr(cards_api, "trigger_execution", lambda cid: called.append(cid))

    resp = await client.patch(f"/api/cards/{card.id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert called == [card.id]


async def test_reopen_does_not_trigger(client, session, monkeypatch):
    """已完成 → 进行中（重开）：不触发执行。"""
    from app.api import cards as cards_api

    project = Project(name="P", description=None, agent_md=None)
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="任务", content="x",
        card_type="task", priority="low", status="done",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    called: list[int] = []
    monkeypatch.setattr(cards_api, "trigger_execution", lambda cid: called.append(cid))

    resp = await client.patch(f"/api/cards/{card.id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert called == []


async def test_comment_in_progress_triggers(client, session, monkeypatch):
    """进行中卡片评论 → 触发执行；非进行中不触发。"""
    from app.api import comments as comments_api

    project = Project(name="P", description=None, agent_md=None)
    session.add(project)
    await session.commit()
    running = Card(project_id=project.id, title="A", content="x",
                   card_type="task", priority="low", status="in_progress", custom_tags=[])
    todo = Card(project_id=project.id, title="B", content="y",
                card_type="task", priority="low", status="todo", custom_tags=[])
    session.add_all([running, todo])
    await session.commit()

    called: list[int] = []
    monkeypatch.setattr(comments_api, "trigger_execution", lambda cid, session_ref=None: called.append(cid))

    r1 = await client.post(f"/api/cards/{running.id}/comments", json={"content": "补充要求"})
    assert r1.status_code == 201
    r2 = await client.post(f"/api/cards/{todo.id}/comments", json={"content": "待办评论"})
    assert r2.status_code == 201
    assert called == [running.id]


async def test_execute_endpoint_only_in_progress(client, session, monkeypatch):
    """手动执行端点：仅进行中卡片允许。"""
    from app.api import cards as cards_api

    project = Project(name="P", description=None, agent_md=None)
    session.add(project)
    await session.commit()
    todo = Card(project_id=project.id, title="B", content="y",
                card_type="task", priority="low", status="todo", custom_tags=[])
    session.add(todo)
    await session.commit()

    called: list[int] = []
    monkeypatch.setattr(cards_api, "trigger_execution", lambda cid: called.append(cid))

    resp = await client.post(f"/api/cards/{todo.id}/execute")
    assert resp.status_code == 409
    assert called == []


async def test_create_checkpointer_concurrent_safe():
    """并发首次创建只执行一次 setup，全部复用同一实例（防 CREATE INDEX CONCURRENTLY 互锁挂死）。"""
    from app.engine import agent as agent_mod

    agent_mod._checkpointer = None  # 清空单例模拟首次创建
    try:
        cps = await asyncio.gather(*(agent_mod.create_checkpointer() for _ in range(4)))
        assert all(c is cps[0] for c in cps), "并发创建返回了不同实例"
    finally:
        agent_mod._checkpointer = None
        agent_mod._checkpointer_cm = None


async def test_execute_card_model_error_marks_failed(session, monkeypatch):
    """模型调用失败（如不支持 function call）→ execution failed + AI 评论说明，不卡 running。"""
    from langchain_openai import ChatOpenAI

    from app.engine import runner

    async def _stub_model(*a, **k):
        return ChatOpenAI(model="a", api_key="k", base_url="https://x/v1")

    class BoomAgent:
        async def ainvoke(self, messages, config=None):
            raise RuntimeError("Function call is not supported for this model")

    async def _no_checkpoint():
        return None

    monkeypatch.setattr(runner, "resolve_chat_model", _stub_model)
    monkeypatch.setattr(runner, "build_agent", lambda *a, **k: BoomAgent())
    monkeypatch.setattr(runner, "create_checkpointer", _no_checkpoint)

    project = Project(name="P", description=None, agent_md=None)
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="任务", content="x",
        card_type="task", priority="low", status="in_progress", custom_tags=[],
    )
    session.add(card)
    await session.commit()

    await runner._execute_in_session(card.id, session)

    exec_rows = (await session.execute(
        __import__("sqlalchemy").select(Execution).where(Execution.card_id == card.id)
    )).scalars().all()
    assert exec_rows[0].status == ExecutionStatus.FAILED.value
    comments = list(
        (await session.execute(
            __import__("sqlalchemy").select(Comment).where(Comment.card_id == card.id)
        )).scalars().all()
    )
    assert "执行失败" in comments[0].content
    assert "Function call is not supported" in comments[0].content
