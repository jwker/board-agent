"""审批 API（3.4）：沙箱命令挂起后的批准/拒绝/编辑恢复。"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.enums import ExecutionStatus
from app.db.models import Execution
from app.engine.runner import resume_execution
from app.schemas.approval import ApprovalRequest, ApprovalResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["approvals"])


def _build_decisions(actions: list[dict], body: ApprovalRequest) -> list[dict]:
    """按审批请求构造 HITL decisions（数量与挂起动作一致）。

    - approve：全部放行
    - reject：全部拒绝（原因随 ToolMessage 返回模型）
    - edit：替换第一个 execute 命令，其余放行
    """
    decisions: list[dict] = []
    for i, action in enumerate(actions):
        if body.decision == "approve":
            decisions.append({"type": "approve"})
        elif body.decision == "reject":
            decisions.append({"type": "reject", "message": body.message or "用户拒绝了该操作"})
        else:  # edit：仅替换第一个 execute 命令，其余放行
            if i == 0 and body.command and body.command.strip():
                decisions.append(
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": action.get("name", "execute"),
                            "args": {**action.get("args", {}), "command": body.command.strip()},
                        },
                    }
                )
            else:
                decisions.append({"type": "approve"})
    return decisions


@router.post("/cards/{card_id}/approval", response_model=ApprovalResponse)
async def approve_card_action(
    card_id: int,
    body: ApprovalRequest,
    session: AsyncSession = Depends(get_session),
) -> ApprovalResponse:
    """对等待审批的执行提交决策；AI 恢复执行（可能再次挂起审批）。

    - approve：放行原命令
    - reject：拒绝（原因随 ToolMessage 返回模型，AI 换方案继续）
    - edit：用替代命令执行
    """
    execution = (
        await session.execute(
            select(Execution).where(Execution.card_id == card_id)
        )
    ).scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=404, detail="该卡片没有执行记录")
    if execution.status != ExecutionStatus.WAITING_APPROVAL.value:
        raise HTTPException(status_code=409, detail="该卡片当前没有等待审批的执行")

    payload = execution.interrupt_payload or {}
    actions = payload.get("actions", [])
    if not actions:
        raise HTTPException(status_code=409, detail="审批载荷为空，无法恢复")

    decisions = _build_decisions(actions, body)

    logger.info(
        "card %s approval decision=%s actions=%d",
        card_id, body.decision, len(actions),
    )
    asyncio.create_task(resume_execution(execution.id, decisions))
    return ApprovalResponse()
