"""通知中心 API：列表 / 未读数 / 标记已读（通知生成走 services.notice_service）。"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.models import Notice
from app.schemas.notice import NoticeCountOut, NoticeIdsIn, NoticeOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notices"])


@router.get("/notices", response_model=list[NoticeOut])
async def list_notices(
    limit: int = 50,
    unread_only: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[Notice]:
    """通知列表（时间倒序；可选仅未读）。"""
    stmt = select(Notice).order_by(Notice.id.desc()).limit(min(limit, 100))
    if unread_only:
        stmt = stmt.where(Notice.read.is_(False))
    return list((await session.execute(stmt)).scalars().all())


@router.get("/notices/unread-count", response_model=NoticeCountOut)
async def unread_count(session: AsyncSession = Depends(get_session)) -> NoticeCountOut:
    n = await session.scalar(select(func.count()).select_from(Notice).where(Notice.read.is_(False)))
    return NoticeCountOut(count=n or 0)


@router.post("/notices/read", response_model=NoticeCountOut)
async def mark_read(body: NoticeIdsIn, session: AsyncSession = Depends(get_session)) -> NoticeCountOut:
    if not body.ids:
        return NoticeCountOut(count=0)
    result = await session.execute(
        Notice.__table__.update().where(Notice.id.in_(body.ids)).values(read=True)
    )
    await session.commit()
    return NoticeCountOut(count=result.rowcount or 0)


@router.post("/notices/read-all", response_model=NoticeCountOut)
async def mark_all_read(session: AsyncSession = Depends(get_session)) -> NoticeCountOut:
    result = await session.execute(
        Notice.__table__.update().where(Notice.read.is_(False)).values(read=True)
    )
    await session.commit()
    return NoticeCountOut(count=result.rowcount or 0)
