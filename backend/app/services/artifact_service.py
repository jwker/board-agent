"""产物服务：磁盘存储（~/.board-agent/artifacts）+ PG 元数据。

目录结构：<artifacts_root>/<project_id>/<card_id>/<filename>
安全：所有文件路径经 resolve + is_relative_to 校验，禁止越出产物根目录。
"""

import logging
import mimetypes
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.enums import ArtifactType
from app.db.models import Artifact

logger = logging.getLogger(__name__)

# 扩展名 → 产物类型（未知归 other）
_EXT_TO_TYPE = {
    ".pdf": ArtifactType.PDF.value,
    ".png": ArtifactType.IMAGE.value,
    ".jpg": ArtifactType.IMAGE.value,
    ".jpeg": ArtifactType.IMAGE.value,
    ".gif": ArtifactType.IMAGE.value,
    ".webp": ArtifactType.IMAGE.value,
    ".svg": ArtifactType.IMAGE.value,
    ".py": ArtifactType.CODE.value,
    ".js": ArtifactType.CODE.value,
    ".ts": ArtifactType.CODE.value,
    ".tsx": ArtifactType.CODE.value,
    ".vue": ArtifactType.CODE.value,
    ".go": ArtifactType.CODE.value,
    ".java": ArtifactType.CODE.value,
    ".rs": ArtifactType.CODE.value,
    ".c": ArtifactType.CODE.value,
    ".cpp": ArtifactType.CODE.value,
    ".sh": ArtifactType.CODE.value,
    ".sql": ArtifactType.CODE.value,
    ".json": ArtifactType.CODE.value,
    ".html": ArtifactType.HTML.value,
    ".htm": ArtifactType.HTML.value,
}

# 可直接内联预览的类型；其余一律附件下载
_PREVIEWABLE = {ArtifactType.PDF.value, ArtifactType.IMAGE.value, ArtifactType.HTML.value}


def infer_type(filename: str) -> str:
    return _EXT_TO_TYPE.get(Path(filename).suffix.lower(), ArtifactType.OTHER.value)


def is_previewable(file_type: str) -> bool:
    return file_type in _PREVIEWABLE


def artifact_root() -> Path:
    return Path(settings.artifacts_root).expanduser()


def _resolve_safe(project_id: int, card_id: int, filename: str) -> Path:
    """按 项目/卡片/文件名 拼绝对路径，并校验未越出产物根目录。"""
    root = artifact_root().resolve()
    target = (root / str(project_id) / str(card_id) / filename).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"非法产物路径: {filename}")
    return target


async def store(
    session: AsyncSession,
    *,
    project_id: int,
    card_id: int,
    filename: str,
    data: bytes,
) -> Artifact:
    """写入文件并登记元数据。filename 仅允许文件名（不含路径分隔符）。"""
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise ValueError(f"非法文件名: {filename}")
    target = _resolve_safe(project_id, card_id, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    logger.info("artifact stored: %s (%d bytes)", target, len(data))

    artifact = Artifact(
        card_id=card_id,
        project_id=project_id,
        filename=filename,
        file_type=infer_type(filename),
        size=len(data),
        path=f"{project_id}/{card_id}/{filename}",
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    return artifact


async def list_by_card(session: AsyncSession, card_id: int) -> list[Artifact]:
    result = await session.execute(
        select(Artifact).where(Artifact.card_id == card_id).order_by(Artifact.id)
    )
    return list(result.scalars().all())


def resolve_artifact_path(artifact: Artifact) -> Path:
    """由元数据解析磁盘绝对路径（读时二次校验，防元数据被篡改）。"""
    parts = artifact.path.split("/")
    if len(parts) != 3:
        raise ValueError(f"产物路径格式异常: {artifact.path}")
    project_id, card_id, filename = parts
    return _resolve_safe(int(project_id), int(card_id), filename)


def content_type_for(filename: str, file_type: str | None = None) -> str:
    """按扩展名给 MIME；代码/未知类型给纯文本，便于浏览器内联。"""
    if file_type == ArtifactType.CODE.value:
        return "text/plain; charset=utf-8"
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"
