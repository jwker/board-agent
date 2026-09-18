"""项目与项目级配置。"""

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.enums import ProjectStatus


class Project(Base, TimestampMixin):
    """项目。"""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)  # 项目介绍（简报静态部分，系统内）
    directory: Mapped[str | None] = mapped_column(Text)  # 授权目录（AI 工作边界）
    directory_status: Mapped[str | None] = mapped_column(default=None)  # existing / empty
    agent_md: Mapped[str | None] = mapped_column(Text)  # 项目规范（创建时写入 <目录>/AGENT.md）
    status: Mapped[str] = mapped_column(default=ProjectStatus.ACTIVE.value, nullable=False)

    cards = relationship(
        "Card", back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class Setting(Base, TimestampMixin):
    """键值配置：全局（scope=global）/ 项目级（scope=project + project_id）。"""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("scope", "project_id", "key", name="uq_settings_key"),)

    scope: Mapped[str] = mapped_column(nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    key: Mapped[str] = mapped_column(nullable=False)
    value: Mapped[dict] = mapped_column(nullable=False)  # JSONB
