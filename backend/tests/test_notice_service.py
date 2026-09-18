"""A7 通知服务测试：勾选过滤、强制通知、事件发布、未读/已读。"""

from app.core.event_bus import EventType
from app.db.enums import NoticeCategory
from app.services import notice_service
from tests.factories import make_card, make_project


async def test_notify_creates_and_publishes(session, client, tmp_path, monkeypatch):
    """发通知：写库 + 发布 NOTIFICATION 事件（payload 携带上下文）。"""
    project = await make_project(session)
    card = await make_card(session, project=project)
    await session.commit()

    received: list[dict] = []

    async def handler(event):
        received.append(event.payload)

    from app.core.event_bus import bus

    unsub = bus.subscribe(EventType.NOTIFICATION, handler)
    try:
        notice = await notice_service.notify(
            session,
            category=NoticeCategory.COMPLETED.value,
            content="任务完成",
            project_id=project.id,
            card_id=card.id,
        )
    finally:
        unsub()

    assert notice is not None
    assert notice.read is False
    assert len(received) == 1
    assert received[0]["card_id"] == card.id
    assert received[0]["category"] == NoticeCategory.COMPLETED.value


async def test_prefs_filter_skips_notice(session):
    """关闭某类勾选后，该类通知不写库不发布。"""
    await notice_service.set_prefs(session, {NoticeCategory.FAILED.value: False})
    notice = await notice_service.notify(
        session, category=NoticeCategory.FAILED.value, content="任务失败"
    )
    assert notice is None

    # 未读列表为空
    assert await notice_service.list_unread(session) == []


async def test_force_ignores_prefs(session):
    """force=True（审批 30 分钟提醒）无视勾选，站内始终发。"""
    await notice_service.set_prefs(session, {NoticeCategory.APPROVAL_WAITING.value: False})
    notice = await notice_service.notify(
        session,
        category=NoticeCategory.APPROVAL_WAITING.value,
        content="有审批等待中",
        force=True,
    )
    assert notice is not None
    assert notice.category == NoticeCategory.APPROVAL_WAITING.value


async def test_prefs_default_all_on_and_roundtrip(session):
    """默认全量开启；保存后可读回且只收已知类别。"""
    prefs = await notice_service.get_prefs(session)
    assert all(v is True for v in prefs.values())
    assert set(prefs) == {c.value for c in NoticeCategory}

    saved = await notice_service.set_prefs(
        session, {NoticeCategory.CLARIFY.value: False, "unknown": True}
    )
    assert saved == {NoticeCategory.CLARIFY.value: False}

    got = await notice_service.get_prefs(session)
    assert got[NoticeCategory.CLARIFY.value] is False
    assert got[NoticeCategory.COMPLETED.value] is True  # 其余默认全量


async def test_mark_read_updates_count(session):
    """批量标记已读返回更新条数。"""
    n1 = await notice_service.notify(session, category=NoticeCategory.COMPLETED.value, content="a")
    n2 = await notice_service.notify(session, category=NoticeCategory.FAILED.value, content="b")
    assert n1 and n2
    assert len(await notice_service.list_unread(session)) == 2

    updated = await notice_service.mark_read(session, [n1.id])
    assert updated == 1
    unread = await notice_service.list_unread(session)
    assert len(unread) == 1
    assert unread[0].id == n2.id
