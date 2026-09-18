"""通知 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str  # NoticeCategory
    content: str
    project_id: int | None
    card_id: int | None
    read: bool
    created_at: datetime


class NoticeIdsIn(BaseModel):
    ids: list[int]


class NoticeCountOut(BaseModel):
    count: int
