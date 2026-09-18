"""通知服务（TECH-DESIGN §9）。

- 业务事件 → 写通知表（类别/内容/卡片/已读）→ 发 NOTIFICATION 事件（WS 推送由订阅者做）。
- 五类勾选过滤：全局配置 notification_prefs（默认全量开启）；勾掉的类不写通知不推送。
- 审批 30 分钟提醒是强制行为：force=True 无视勾选，站内始终发。
"""

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import Event, EventType, bus
from app.db.enums import NoticeCategory, SettingScope
from app.db.models import Notice, Setting

logger = logging.getLogger(__name__)

PREFS_KEY = "notification_prefs"
_ALL_CATEGORIES = [c.value for c in NoticeCategory]


def default_prefs() -> dict:
    """默认全量开启（用户拍板：默认全量）。"""
    return {c: True for c in _ALL_CATEGORIES}


async def get_prefs(session: AsyncSession) -> dict:
    """读取全局通知勾选；未配置时返回全量。"""
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == SettingScope.GLOBAL.value, Setting.key == PREFS_KEY
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return default_prefs()
    merged = default_prefs()
    merged.update({k: bool(v) for k, v in row.value.items() if k in merged})
    return merged


async def set_prefs(session: AsyncSession, prefs: dict) -> dict:
    """保存通知勾选（只接受已知类别）。"""
    clean = {k: bool(v) for k, v in prefs.items() if k in _ALL_CATEGORIES}
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == SettingScope.GLOBAL.value, Setting.key == PREFS_KEY
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = Setting(scope=SettingScope.GLOBAL.value, key=PREFS_KEY, value=clean)
        session.add(row)
    else:
        row.value = clean
    await session.commit()
    return clean


async def notify(
    session: AsyncSession,
    *,
    category: str,
    content: str,
    project_id: int | None = None,
    card_id: int | None = None,
    force: bool = False,
) -> Notice | None:
    """发一条站内通知。

    force=True（审批 30 分钟提醒）无视勾选；否则按五类勾选过滤。
    写库后发布 NOTIFICATION 事件，由订阅者（WS 推送）消费。
    """
    if not force:
        prefs = await get_prefs(session)
        if not prefs.get(category, True):
            logger.info("notice skipped by prefs: %s", category)
            return None

    notice = Notice(category=category, content=content, project_id=project_id, card_id=card_id)
    session.add(notice)
    await session.commit()
    await session.refresh(notice)

    await bus.publish(
        Event(
            EventType.NOTIFICATION,
            {
                "notice_id": notice.id,
                "category": notice.category,
                "content": notice.content,
                "project_id": notice.project_id,
                "card_id": notice.card_id,
            },
        )
    )
    logger.info("notice created: %s (card=%s)", category, card_id)
    return notice


async def list_unread(session: AsyncSession, limit: int = 50) -> Sequence[Notice]:
    """未读通知（通知中心按时间倒序）。"""
    result = await session.execute(
        select(Notice).where(Notice.read.is_(False)).order_by(Notice.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def mark_read(session: AsyncSession, notice_ids: Sequence[int]) -> int:
    """批量标记已读，返回实际更新的条数。"""
    result = await session.execute(
        Notice.__table__.update().where(Notice.id.in_(notice_ids)).values(read=True)
    )
    await session.commit()
    return result.rowcount or 0
