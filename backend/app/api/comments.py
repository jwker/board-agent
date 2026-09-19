"""评论 API：卡片讨论流基础读写（AI 触发语义在 2.4 接入）。"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.enums import CardStatus, CommentAuthor
from app.db.models import Card, Comment
from app.engine.runner import trigger_execution
from app.schemas.comment import CommentCreate, CommentOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["comments"])


@router.get("/cards/{card_id}/comments", response_model=list[CommentOut])
async def list_comments(card_id: int, session: AsyncSession = Depends(get_session)) -> list[Comment]:
    """卡片评论列表（按时间正序：Issue 回帖流）。"""
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    stmt = select(Comment).where(Comment.card_id == card_id).order_by(Comment.id.asc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("/cards/{card_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    card_id: int,
    body: CommentCreate,
    session: AsyncSession = Depends(get_session),
) -> Comment:
    """新增评论（阶段 2.2：仅用户评论记录；AI 触发与 AI 评论在 2.4 接入）。"""
    card = await session.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="卡片不存在")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="评论内容不能为空")

    comment = Comment(card_id=card_id, author=CommentAuthor.USER.value, content=content)
    session.add(comment)
    await session.commit()
    await session.refresh(comment)

    # 3.3 评论触发：进行中的卡片，用户评论 → 触发 AI 执行（AI 评论不经过此接口，不会循环）
    if card.status == CardStatus.IN_PROGRESS.value:
        trigger_execution(card_id)

    logger.info("comment created: card=%s author=user len=%s", card_id, len(content))
    return comment
