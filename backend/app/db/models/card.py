"""卡片与评论。"""

from datetime import date

from sqlalchemy import Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Card(Base, TimestampMixin):
    """看板卡片（主贴 + 评论流）。"""

    __tablename__ = "cards"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 主贴内容
    card_type: Mapped[str] = mapped_column(nullable=False)  # CardType
    custom_tags: Mapped[list | None] = mapped_column(JSONB)  # 自定义标签
    priority: Mapped[str] = mapped_column(nullable=False)  # Priority
    status: Mapped[str] = mapped_column(nullable=False, index=True)  # CardStatus
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)  # 验收标准
    due_date: Mapped[date | None] = mapped_column(Date)  # 截止日期
    remark: Mapped[str | None] = mapped_column(Text)  # 备注
    read_only: Mapped[bool] = mapped_column(default=False, nullable=False)  # 只读开关

    project = relationship("Project", back_populates="cards", lazy="selectin")
    comments = relationship(
        "Comment", back_populates="card", cascade="all, delete-orphan", lazy="selectin"
    )


class Comment(Base, TimestampMixin):
    """评论（Issue 回帖流；AI 评论以 thread_id 短标识为作者名）。"""

    __tablename__ = "comments"

    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False, index=True)
    author: Mapped[str] = mapped_column(nullable=False)  # CommentAuthor
    thread_id: Mapped[str | None] = mapped_column(nullable=True)  # AI 评论关联的执行会话
    content: Mapped[str] = mapped_column(Text, nullable=False)

    card = relationship("Card", back_populates="comments", lazy="selectin")
