"""项目相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    directory: str | None = None  # 授权目录（AI 工作边界）
    directory_status: str | None = None  # existing / empty
    agent_md: str | None = None  # 项目规范（写入 <目录>/AGENT.md）


class ProjectUpdate(BaseModel):
    """归档/恢复。"""

    status: str  # ProjectStatus: active / archived


class ProjectStats(BaseModel):
    """首页卡片统计。"""

    total: int = 0
    in_progress: int = 0
    done: int = 0


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    directory: str | None
    directory_status: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectListItem(ProjectOut):
    """列表项：在基础字段上附加卡片统计。"""

    stats: ProjectStats = ProjectStats()
