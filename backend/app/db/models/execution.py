"""执行会话：一卡一线程，checkpoint 与审批状态。"""

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Execution(Base, TimestampMixin):
    """执行记录（引擎侧）：驱动 agent 生命周期。"""

    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("card_id", name="uq_execution_card"),)

    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(
        nullable=False, index=True
    )  # Deep Agents checkpoint 线程
    status: Mapped[str] = mapped_column(nullable=False, index=True)  # ExecutionStatus
    current_step: Mapped[str | None] = mapped_column(Text)  # "步骤 x/y"
    interrupt_payload: Mapped[dict | None] = mapped_column(JSONB)  # 审批挂起载荷

    card = relationship("Card", lazy="selectin")
