"""评论 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    model_ref: str | None = None  # 会话模型引用 "provider_id::model"（详情页临时切换，仅本次触发生效）


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    author: str  # CommentAuthor: user / ai
    thread_id: str | None  # AI 评论关联的执行会话
    content: str
    steps: list | None  # 工具调用步骤（仅 AI 评论）：[{name, args, result, result_full, status}]
    created_at: datetime
