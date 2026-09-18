"""通知中心。"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notice(Base):
    """站内通知（五类；审批 30 分钟提醒强制不受勾选控制）。"""

    __tablename__ = "notices"

    category: Mapped[str] = mapped_column(nullable=False, index=True)  # NoticeCategory
    content: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id"), nullable=True)
    read: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
