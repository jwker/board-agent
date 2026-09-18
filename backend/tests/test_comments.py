"""评论 API 测试：列表/创建/空内容/404。"""

from app.db.enums import CommentAuthor
from tests.factories import make_card, make_comment, make_project


async def test_create_and_list_comments(session, client):
    """创建评论后按时间正序可见。"""
    project = await make_project(session, name="评论项目")
    card = await make_card(session, project=project, title="讨论卡")
    await session.commit()

    first = await client.post(f"/api/cards/{card.id}/comments", json={"content": "第一条"})
    assert first.status_code == 201, first.text
    assert first.json()["author"] == CommentAuthor.USER.value
    assert "created_at" in first.json()

    second = await client.post(f"/api/cards/{card.id}/comments", json={"content": "第二条"})
    assert second.status_code == 201

    comments = (await client.get(f"/api/cards/{card.id}/comments")).json()
    assert [c["content"] for c in comments] == ["第一条", "第二条"]


async def test_comment_validation(session, client):
    """空评论 422；卡片不存在 404。"""
    project = await make_project(session, name="校验评论")
    card = await make_card(session, project=project, title="卡")
    await session.commit()

    empty = await client.post(f"/api/cards/{card.id}/comments", json={"content": "   "})
    assert empty.status_code == 422

    missing = await client.post("/api/cards/99999/comments", json={"content": "x"})
    assert missing.status_code == 404


async def test_existing_comments_from_factory(session, client):
    """工厂预置评论可读出（含 AI 评论 thread_id）。"""
    project = await make_project(session, name="预置评论")
    card = await make_card(session, project=project, title="卡")
    await make_comment(session, card=card, author=CommentAuthor.USER.value, content="用户评论")
    await make_comment(
        session, card=card, author=CommentAuthor.AI.value, thread_id="ABC1", content="AI 评论"
    )
    await session.commit()

    comments = (await client.get(f"/api/cards/{card.id}/comments")).json()
    assert len(comments) == 2
    assert comments[1]["thread_id"] == "ABC1"
    assert comments[1]["author"] == "ai"
