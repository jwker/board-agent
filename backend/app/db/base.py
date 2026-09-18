"""SQLAlchemy 声明式基类。"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """全模型基类：统一主键与时间戳。"""

    # Mapped[dict] / Mapped[list] 注解映射到 PG JSONB
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy 声明式基类标准配置
        dict: JSONB,
        list: JSONB,
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin:
    """带 updated_at 的混入。"""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
