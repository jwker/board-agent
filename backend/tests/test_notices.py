"""通知中心 API 测试。"""

import pytest
from sqlalchemy import select

from app.db.enums import NoticeCategory
from app.db.models import Notice
from app.services.notice_service import notify


async def test_notice_list_and_unread_count(session, client):
    """列表倒序 + 未读数 + 仅未读过滤。"""
    await notify(session, category=NoticeCategory.COMPLETED.value, content="第一条", force=True)
    await notify(session, category=NoticeCategory.FAILED.value, content="第二条", force=True)
    await notify(session, category=NoticeCategory.CLARIFY.value, content="第三条", force=True)
    await session.commit()

    resp = await client.get("/api/notices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["content"] == "第三条"  # 倒序

    cnt = (await client.get("/api/notices/unread-count")).json()
    assert cnt["count"] == 3

    only = (await client.get("/api/notices", params={"unread_only": True})).json()
    assert len(only) == 3


async def test_mark_read_and_read_all(session, client):
    """标记已读 / 全部已读。"""
    await notify(session, category=NoticeCategory.COMPLETED.value, content="a", force=True)
    await notify(session, category=NoticeCategory.COMPLETED.value, content="b", force=True)
    await session.commit()

    notices = (await client.get("/api/notices")).json()
    first_id = notices[0]["id"]

    r = (await client.post("/api/notices/read", json={"ids": [first_id]})).json()
    assert r["count"] == 1
    assert (await client.get("/api/notices/unread-count")).json()["count"] == 1

    r = (await client.post("/api/notices/read-all", json={})).json()
    assert r["count"] == 1
    assert (await client.get("/api/notices/unread-count")).json()["count"] == 0


async def test_mark_read_empty(session, client):
    resp = await client.post("/api/notices/read", json={"ids": []})
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_notice_carries_card_link(session, client):
    """通知携带 card_id，前端点击跳卡。"""
    from tests.factories import make_card, make_project

    project = await make_project(session)
    card = await make_card(session, project=project, title="关联卡")
    await session.commit()

    await notify(
        session,
        category=NoticeCategory.COMPLETED.value,
        content="完成",
        project_id=project.id,
        card_id=card.id,
        force=True,
    )
    await session.commit()

    data = (await client.get("/api/notices")).json()
    assert data[0]["card_id"] == card.id
    assert data[0]["project_id"] == project.id
