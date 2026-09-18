"""产物 API：上传 / 列表 / 预览下载。"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.models import Artifact
from app.services import artifact_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.post("")
async def upload_artifact(
    card_id: int = Form(...),
    project_id: int = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """上传产物：落盘 + 登记元数据。"""
    try:
        data = await file.read()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail="读取上传文件失败") from exc

    try:
        artifact = await artifact_service.store(
            session,
            project_id=project_id,
            card_id=card_id,
            filename=file.filename or "unnamed",
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": artifact.id, "filename": artifact.filename, "size": artifact.size}


@router.get("")
async def list_artifacts(
    card_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """某卡片的产物列表。"""
    artifacts = await artifact_service.list_by_card(session, card_id)
    return [
        {
            "id": a.id,
            "filename": a.filename,
            "file_type": a.file_type,
            "size": a.size,
            "previewable": artifact_service.is_previewable(a.file_type),
        }
        for a in artifacts
    ]


@router.get("/{artifact_id}/file")
async def get_artifact_file(
    artifact_id: int,
    inline: int = 0,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """产物文件：inline=1 内联预览（pdf/图片/html），默认附件下载。"""
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="产物不存在")
    try:
        path = artifact_service.resolve_artifact_path(artifact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="产物文件缺失")

    media_type = artifact_service.content_type_for(artifact.filename, artifact.file_type)
    disposition = (
        "inline"
        if inline == 1 and artifact_service.is_previewable(artifact.file_type)
        else "attachment"
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=artifact.filename,
        content_disposition_type=disposition,
    )
