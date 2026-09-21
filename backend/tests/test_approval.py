"""3.4 审批生命周期测试：载荷结构化、决策构造、审批 API 前置校验。"""

import pytest

from app.api.approvals import _build_decisions
from app.db.enums import ExecutionStatus
from app.db.models import Card, Execution, Project
from app.engine.runner import _build_sandbox, _hitl_to_payload

# ---------- 载荷结构化 ----------


def test_hitl_to_payload_struct():
    hitl = {
        "action_requests": [
            {
                "name": "execute",
                "args": {"command": "python deploy.py", "timeout": None},
                "description": "运行部署脚本",
            }
        ],
        "review_configs": [{"action_name": "execute", "allowed_decisions": ["approve", "reject", "edit"]}],
    }
    payload = _hitl_to_payload(hitl)
    assert payload["actions"][0]["name"] == "execute"
    assert payload["actions"][0]["args"]["command"] == "python deploy.py"
    assert payload["configs"][0]["action_name"] == "execute"
    assert "saved_at" in payload


# ---------- 决策构造 ----------


def _actions():
    return [{"name": "execute", "args": {"command": "python deploy.py", "timeout": None}}]


def test_decisions_approve():
    body = type("B", (), {"decision": "approve", "message": None, "command": None})()
    d = _build_decisions(_actions(), body)
    assert d == [{"type": "approve"}]


def test_decisions_reject_with_message():
    body = type("B", (), {"decision": "reject", "message": "不要跑部署", "command": None})()
    d = _build_decisions(_actions(), body)
    assert d == [{"type": "reject", "message": "不要跑部署"}]


def test_decisions_edit_command():
    body = type("B", (), {"decision": "edit", "message": None, "command": "pytest"})()
    d = _build_decisions(_actions(), body)
    assert d[0]["type"] == "edit"
    assert d[0]["edited_action"]["name"] == "execute"
    assert d[0]["edited_action"]["args"]["command"] == "pytest"
    # 原参数保留（timeout 等）
    assert "timeout" in d[0]["edited_action"]["args"]


def test_decisions_edit_multiple_actions_others_approved():
    actions = [
        {"name": "execute", "args": {"command": "python a.py"}},
        {"name": "execute", "args": {"command": "python b.py"}},
    ]
    body = type("B", (), {"decision": "edit", "message": None, "command": "pytest"})()
    d = _build_decisions(actions, body)
    assert d[0]["type"] == "edit"
    assert d[1] == {"type": "approve"}


# ---------- 沙箱构建 ----------


async def test_build_sandbox_none_without_directory(session):
    project = Project(name="P", directory=None)
    assert _build_sandbox(project) is None


async def test_build_sandbox_uses_project_dir(session, tmp_path):
    project = Project(name="P", directory=str(tmp_path))
    sandbox = _build_sandbox(project)
    assert sandbox is not None
    assert str(sandbox.cwd) == str(tmp_path)


async def test_build_sandbox_none_for_missing_dir(session, tmp_path):
    project = Project(name="P", directory=str(tmp_path / "nope"))
    assert _build_sandbox(project) is None


# ---------- 审批 API 前置校验 ----------


async def test_approval_requires_waiting_execution(session):
    """无待审批执行 → 409。"""
    from fastapi import HTTPException

    from app.api.approvals import approve_card_action

    project = Project(name="P")
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="t", content="c",
        card_type="requirement", priority="medium", status="in_progress",
    )
    session.add(card)
    await session.commit()
    execution = Execution(card_id=card.id, thread_id="card-1", status=ExecutionStatus.RUNNING.value)
    session.add(execution)
    await session.commit()

    body = type("B", (), {"decision": "approve", "message": None, "command": None})()
    with pytest.raises(HTTPException) as ei:
        await approve_card_action(card.id, body, session)
    assert ei.value.status_code == 409


async def test_approval_no_execution_404(session):
    from fastapi import HTTPException

    from app.api.approvals import approve_card_action

    body = type("B", (), {"decision": "approve", "message": None, "command": None})()
    with pytest.raises(HTTPException) as ei:
        await approve_card_action(99999, body, session)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_park_for_approval_notifies(session, monkeypatch):
    """3.6+：审批挂起 → approval_waiting 站内通知。"""
    from app.engine.runner import _park_for_approval
    from app.services import notice_service

    calls: list[tuple] = []

    async def _fake_notify(session, *, category, content, project_id=None, card_id=None, force=False):
        calls.append((category, content, project_id, card_id))
        return None

    monkeypatch.setattr(notice_service, "notify", _fake_notify)

    project = Project(name="P", description="D", agent_md="规范")
    session.add(project)
    await session.commit()
    card = Card(
        project_id=project.id, title="审批挂起", content="跑命令",
        card_type="requirement", priority="medium", status="in_progress",
        custom_tags=[],
    )
    session.add(card)
    await session.commit()
    execution = Execution(
        card_id=card.id, thread_id="card-1", status=ExecutionStatus.RUNNING.value
    )
    session.add(execution)
    await session.commit()

    hitl = {
        "action_requests": [
            {
                "action": {"name": "execute", "args": {"command": "ls -la", "timeout": 5}},
                "description": "list files",
                "id": "req-1",
            }
        ],
        "review_configs": [{"action_ids": ["req-1"], "decision_mode": "require_approval"}],
    }
    await _park_for_approval(session, execution, hitl, card)

    assert calls, "审批挂起应发通知"
    category, content, pid, cid = calls[-1]
    assert category == "approval_waiting"
    assert pid == project.id
    assert cid == card.id
    assert "审批挂起" in content
