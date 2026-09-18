"""产物：系统产物目录 + PG 元数据。"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Artifact(Base):
    """产物元数据（文件存 ~/.board-agent/artifacts/<项目>/<卡片>/）。"""

    __tablename__ = "artifacts"

    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(nullable=False)
    file_type: Mapped[str] = mapped_column(nullable=False)  # ArtifactType
    size: Mapped[int] = mapped_column(default=0, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)  # 相对产物根目录的路径
