"""卡片 Pydantic 模型。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CardCreate(BaseModel):
    title: str = Field(default="", max_length=200)  # 可选：留空由 AI 自动总结（阶段 3）
    content: str = Field(min_length=1, max_length=10000)  # 必填
    card_type: str = "task"  # CardType
    custom_tags: list[str] = []
    priority: str = "medium"  # Priority
    status: str = "backlog"  # 入列位置（CardStatus 四态之一）
    acceptance_criteria: str | None = None
    due_date: date | None = None
    remark: str | None = None
    read_only: bool = False


class CardUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)  # 允许空串（无标题卡片）
    content: str | None = None
    card_type: str | None = None
    custom_tags: list[str] | None = None
    priority: str | None = None
    status: str | None = None
    acceptance_criteria: str | None = None
    due_date: date | None = None
    remark: str | None = None
    read_only: bool | None = None


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    content: str
    card_type: str
    custom_tags: list[str]
    priority: str
    status: str
    acceptance_criteria: str | None
    due_date: date | None
    remark: str | None
    read_only: bool
    archived_from: str | None
    comment_count: int = 0  # 评论数（列表查询时填充；单卡详情不展示）
    created_at: datetime
    updated_at: datetime
