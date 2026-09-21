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

    async def astream(self, input, config=None, stream_mode=None):
        # 模拟流式：单次 values 输出完整状态（走真实 _stream_agent 路径）
        yield "values", {"messages": [AIMessage(content="已完成任务，测试通过")]}


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

        async def astream(self, input, config=None, stream_mode=None):
            if False:  # 保持 async generator 形态
                yield None
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


async def test_execute_card_completed_notifies(session, monkeypatch):
    """3.6：执行完成 → 生成 completed 站内通知（category + 卡片关联）。"""
    from langchain_openai import ChatOpenAI

    from app.engine import runner
    from app.services import notice_service

    calls: list[tuple] = []

    async def _stub_model(*a, **k):
        return ChatOpenAI(model="a-fast", api_key="k", base_url="https://x/v1")

    async def _no_checkpoint():
        return None

    async def _fake_notify(session, *, category, content, project_id=None, card_id=None, force=False):
        calls.append((category, content, project_id, card_id))
        return None

    monkeypatch.setattr(runner, "resolve_chat_model", _stub_model)
    monkeypatch.setattr(runner, "build_agent", lambda *a, **k: StubAgent())
    monkeypatch.setattr(runner, "create_checkpointer", _no_checkpoint)
    monkeypatch.setattr(notice_service, "notify", _fake_notify)

    project = Project(name="P", description="D", agent_md="规范")
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="通知任务", content="实现登录",
        card_type="requirement", priority="medium", status="in_progress",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    await runner._execute_in_session(card.id, session)

    assert calls, "应调用通知服务"
    category, content, pid, cid = calls[-1]
    assert category == "completed"
    assert pid == project.id
    assert cid == card.id
    assert "通知任务" in content


async def test_execute_card_failed_notifies(session, monkeypatch):
    """3.6：执行失败 → 生成 failed 站内通知。"""
    from langchain_openai import ChatOpenAI

    from app.engine import runner
    from app.services import notice_service

    calls: list[tuple] = []

    async def _stub_model(*a, **k):
        return ChatOpenAI(model="a-fast", api_key="k", base_url="https://x/v1")

    async def _no_checkpoint():
        return None

    async def _fake_notify(session, *, category, content, project_id=None, card_id=None, force=False):
        calls.append((category, content, project_id, card_id))
        return None

    monkeypatch.setattr(runner, "resolve_chat_model", _stub_model)
    monkeypatch.setattr(runner, "build_agent", lambda *a, **k: BoomAgent())
    monkeypatch.setattr(runner, "create_checkpointer", _no_checkpoint)
    monkeypatch.setattr(notice_service, "notify", _fake_notify)

    project = Project(name="P", description="D", agent_md="规范")
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="失败卡", content="会失败",
        card_type="requirement", priority="medium", status="in_progress",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()

    await runner._execute_in_session(card.id, session)

    assert calls, "应调用通知服务"
    assert calls[-1][0] == "failed"
    assert calls[-1][3] == card.id


# ---------- 流式输出 ----------


async def test_stream_agent_pushes_delta_and_collects_state():
    """_stream_agent：model 节点文本块经 CARD_STREAM 推送；values 收集最终状态与中断。"""
    from langchain_core.messages import AIMessageChunk
    from app.core.event_bus import EventType

    class FakeStreamAgent:
        async def astream(self, input, config=None, stream_mode=None):
            # messages：两个 model 节点文本块
            yield "messages", (AIMessageChunk(content="你好"), {"langgraph_node": "model"})
            yield "messages", (AIMessageChunk(content="世界"), {"langgraph_node": "model"})
            # 非 model 节点文本块：不推送
            yield "messages", (AIMessageChunk(content="子代理输出"), {"langgraph_node": "agent"})
            # values：最终状态
            yield "values", {"messages": [AIMessage(content="你好世界")]}

    deltas: list[str] = []
    received = []

    def on_stream(event):
        deltas.append(event.payload["delta"])

    from app.engine import runner
    unsub = runner.bus.subscribe(EventType.CARD_STREAM, on_stream)
    try:
        final_state, hitl = await runner._stream_agent(
            FakeStreamAgent(), {"messages": []}, {"configurable": {"thread_id": "t"}}, card_id=99
        )
    finally:
        unsub()

    assert deltas == ["你好", "世界"], deltas
    assert hitl is None
    assert runner._stream_buffers.pop(99, "") == "你好世界"


async def test_stream_agent_captures_interrupt():
    """values 流的 __interrupt__（tuple 形态）能被 _stream_agent 捕获。"""
    from langchain_core.messages import AIMessageChunk

    class FakeInterruptAgent:
        async def astream(self, input, config=None, stream_mode=None):
            yield "messages", (AIMessageChunk(content="我先执行"), {"langgraph_node": "model"})
            yield "values", {"__interrupt__": ({"action_requests": [{"name": "execute"}]},)}

    from app.engine import runner
    final_state, hitl = await runner._stream_agent(
        FakeInterruptAgent(), {"messages": []}, {"configurable": {"thread_id": "t"}}, card_id=None
    )
    assert hitl is not None
    assert hitl["action_requests"][0]["name"] == "execute"


# ---------- 工具调用步骤解析 ----------


async def test_ingest_step_chunk_tool_call_and_result():
    """工具调用增量拼参 → calling 步骤；结果返回 → done + 摘要截断。"""
    from langchain_core.messages import AIMessageChunk, ToolMessageChunk
    from app.engine import runner

    # 增量：name 完整、args 分两段拼 JSON
    c1 = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {"name": "ls", "args": '{"path": ', "id": "call_1", "index": 0}
        ],
    )
    evs = runner._ingest_step_chunk(1, c1, {})
    assert evs == [], "参数未拼完不产出步骤"

    c2 = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "", "args": '"/"}', "id": "call_1", "index": 0}],
    )
    evs = runner._ingest_step_chunk(1, c2, {})
    assert len(evs) == 1
    step = evs[0][1]
    assert step["name"] == "ls"
    assert step["args"] == {"path": "/"}
    assert step["status"] == "calling"

    # 结果返回（超长截断）
    long_result = "x" * 600
    tm = ToolMessageChunk(content=long_result, tool_call_id="call_1", name="ls")
    evs = runner._ingest_step_chunk(1, tm, {})
    assert len(evs) == 1
    step = evs[0][1]
    assert step["status"] == "done"
    assert step["result"].endswith("…")
    assert len(step["result"]) == runner.STEP_RESULT_SUMMARY_MAX + 1
    assert len(step["result_full"]) == len(long_result)

    # 落库结构：steps_buffer 完整
    steps = runner._steps_buffer_pop(1)
    assert len(steps) == 1
    assert steps[0]["name"] == "ls"
    assert steps[0]["status"] == "done"


async def test_stream_agent_publishes_step_events():
    """_stream_agent 将工具调用/结果经 CARD_STEP 事件发布。"""
    from langchain_core.messages import AIMessageChunk, ToolMessageChunk
    from app.core.event_bus import EventType
    from app.engine import runner

    class FakeStepAgent:
        async def astream(self, input, config=None, stream_mode=None):
            yield "messages", (AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "ls", "args": '{"path": "/"}', "id": "c2", "index": 0}],
            ), {"langgraph_node": "model"})
            yield "messages", (ToolMessageChunk(content='["AGENT.md"]', tool_call_id="c2", name="ls"), {"langgraph_node": "tool"})
            yield "messages", (AIMessageChunk(content="目录只有 AGENT.md"), {"langgraph_node": "model"})
            yield "values", {"messages": [AIMessageChunk(content="目录只有 AGENT.md")]}

    published = []

    def on_step(event):
        published.append(event.payload["step"])

    unsub = runner.bus.subscribe(EventType.CARD_STEP, on_step)
    try:
        await runner._stream_agent(
            FakeStepAgent(), {"messages": []}, {"configurable": {"thread_id": "t"}}, card_id=7
        )
    finally:
        unsub()

    assert len(published) == 2, published
    assert published[0]["name"] == "ls" and published[0]["status"] == "calling"
    assert published[1]["status"] == "done"
    assert published[1]["result"] == '["AGENT.md"]'
    steps = runner._steps_buffer_pop(7)
    assert len(steps) == 1
    assert steps[0]["name"] == "ls"
    assert steps[0]["status"] == "done"
