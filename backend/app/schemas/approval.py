"""审批请求 Pydantic 模型（3.4 沙箱命令审批）。"""

from typing import Literal

from pydantic import BaseModel, Field


class ApprovalRequest(BaseModel):
    """审批决策：批准 / 拒绝（附原因）/ 编辑命令后批准。"""

    decision: Literal["approve", "reject", "edit"]
    message: str | None = Field(default=None, max_length=500)  # reject 时的原因
    command: str | None = Field(default=None, max_length=2000)  # edit 时的替代命令


class ApprovalResponse(BaseModel):
    ok: bool = True
    status: str = "running"
    message: str = "已提交审批决策，AI 继续执行"
