"""评论 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    author: str  # CommentAuthor: user / ai
    thread_id: str | None  # AI 评论关联的执行会话
    content: str
    created_at: datetime
