"""卡片 CRUD API 测试：建卡/列表/详情/更新/校验/入列位置。"""

from app.db.enums import CardStatus, CardType
from tests.factories import make_project


async def test_create_card_and_list(session, client):
    """建卡后按项目列表可见。"""
    project = await make_project(session, name="卡片项目")
    await session.commit()

    resp = await client.post(
        f"/api/projects/{project.id}/cards",
        json={
            "title": "实现用户登录接口",
            "content": "说明需求背景",
            "card_type": "requirement",
            "priority": "high",
            "status": "todo",
            "acceptance_criteria": "登录成功返回 token",
            "due_date": "2026-12-31",
            "remark": "备注内容",
            "custom_tags": ["登录", "认证"],
            "read_only": False,
        },
    )
    assert resp.status_code == 201, resp.text
    card = resp.json()
    assert card["title"] == "实现用户登录接口"
    assert card["status"] == CardStatus.TODO.value
    assert card["card_type"] == CardType.REQUIREMENT.value
    assert card["custom_tags"] == ["登录", "认证"]
    assert card["due_date"] == "2026-12-31"
    assert card["read_only"] is False
    assert "created_at" in card

    cards = (await client.get(f"/api/projects/{project.id}/cards")).json()
    assert len(cards) == 1
    assert cards[0]["id"] == card["id"]


async def test_create_card_in_each_status(session, client):
    """入列位置可选全部四态。"""
    project = await make_project(session, name="入列位置")
    await session.commit()
    for status in ("backlog", "todo", "in_progress", "done"):
        resp = await client.post(
            f"/api/projects/{project.id}/cards",
            json={"title": f"卡-{status}", "content": "内容", "status": status},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == status


async def test_create_card_validation(session, client):
    """非法类型/优先级/状态返回 422；空内容 422（内容必填）；空标题可创建。"""
    project = await make_project(session, name="校验项目")
    await session.commit()

    bad_type = await client.post(
        f"/api/projects/{project.id}/cards", json={"title": "x", "content": "内容", "card_type": "nope"}
    )
    assert bad_type.status_code == 422

    bad_status = await client.post(
        f"/api/projects/{project.id}/cards", json={"title": "x", "content": "内容", "status": "deleted"}
    )
    assert bad_status.status_code == 422

    empty_content = await client.post(
        f"/api/projects/{project.id}/cards", json={"title": "有标题", "content": ""}
    )
    assert empty_content.status_code == 422

    no_content = await client.post(f"/api/projects/{project.id}/cards", json={"title": "x"})
    assert no_content.status_code == 422


async def test_create_card_without_title(session, client):
    """标题可选：留空可创建，标题存为空串（阶段 3 AI 自动总结）。"""
    project = await make_project(session, name="无标题项目")
    await session.commit()
    resp = await client.post(
        f"/api/projects/{project.id}/cards", json={"content": "这是卡片内容，标题应由此总结"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == ""


async def test_card_not_found_and_project_not_found(session, client):
    """卡片 404 / 项目 404。"""
    missing = await client.get("/api/cards/99999")
    assert missing.status_code == 404

    bad_project = await client.post("/api/projects/99999/cards", json={"title": "x", "content": "内容"})
    assert bad_project.status_code == 404


async def test_update_card_fields(session, client):
    """PATCH 只更新传入字段。"""
    project = await make_project(session, name="更新项目")
    await session.commit()
    created = (
        await client.post(
            f"/api/projects/{project.id}/cards", json={"title": "原标题", "content": "内容", "priority": "low"}
        )
    ).json()

    updated = await client.patch(
        f"/api/cards/{created['id']}", json={"title": "新标题", "read_only": True}
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "新标题"
    assert body["read_only"] is True
    assert body["priority"] == "low"  # 未传字段保持不变

    changed_status = await client.patch(
        f"/api/cards/{created['id']}", json={"status": "in_progress"}
    )
    assert changed_status.json()["status"] == "in_progress"

    bad = await client.patch(f"/api/cards/{created['id']}", json={"priority": "urgent"})
    assert bad.status_code == 422


async def test_update_missing_card(session, client):
    resp = await client.patch("/api/cards/99999", json={"title": "x"})
    assert resp.status_code == 404


async def test_state_machine_transitions(session, client):
    """状态机（2.3）：四态自由迁移；归档必须走专用接口；归档卡改状态 409。"""
    project = await make_project(session, name="状态机项目")
    await session.commit()
    cid = (
        await client.post(
            f"/api/projects/{project.id}/cards", json={"title": "迁移", "content": "内容", "status": "backlog"}
        )
    ).json()["id"]

    # 四态自由迁移（确认语义在前端，API 放行）
    for target in ("todo", "in_progress", "done", "in_progress", "backlog", "todo"):
        resp = await client.patch(f"/api/cards/{cid}", json={"status": target})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target

    # PATCH 直接改 archived → 409
    resp = await client.patch(f"/api/cards/{cid}", json={"status": "archived"})
    assert resp.status_code == 409

    # 归档走专用接口：记录归档前状态
    resp = await client.post(f"/api/cards/{cid}/archive")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "archived"
    assert body["archived_from"] == "todo"

    # 归档后 PATCH 状态 → 409
    resp = await client.patch(f"/api/cards/{cid}", json={"status": "backlog"})
    assert resp.status_code == 409

    # 重复归档 → 409
    resp = await client.post(f"/api/cards/{cid}/archive")
    assert resp.status_code == 409

    # 恢复：回到归档前状态
    resp = await client.post(f"/api/cards/{cid}/restore")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "todo"
    assert body["archived_from"] is None

    # 未归档卡片 restore → 409
    resp = await client.post(f"/api/cards/{cid}/restore")
    assert resp.status_code == 409


async def test_archive_in_progress_rejected(session, client):
    """进行中卡片不允许归档（409）。"""
    project = await make_project(session, name="归档限制项目")
    await session.commit()
    cid = (
        await client.post(
            f"/api/projects/{project.id}/cards", json={"title": "执行中", "content": "内容", "status": "in_progress"}
        )
    ).json()["id"]
    resp = await client.post(f"/api/cards/{cid}/archive")
    assert resp.status_code == 409
    # 移出进行中后可归档
    await client.patch(f"/api/cards/{cid}", json={"status": "todo"})
    resp = await client.post(f"/api/cards/{cid}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
