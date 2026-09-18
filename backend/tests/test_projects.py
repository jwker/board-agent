"""项目 API 测试：列表/新建/重名/归档恢复/详情/统计/AGENT.md 写入/无删除接口。"""

from app.db.enums import CardStatus, ProjectStatus
from tests.factories import make_card, make_project


async def test_create_and_list(session, client):
    """新建项目后列表可见。"""
    resp = await client.post(
        "/api/projects", json={"name": "新项目", "description": "描述", "directory": "/tmp/demo"}
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "新项目"
    assert created["directory"] == "/tmp/demo"
    assert created["status"] == ProjectStatus.ACTIVE.value
    assert "created_at" in created

    items = (await client.get("/api/projects")).json()
    assert any(p["name"] == "新项目" for p in items)


async def test_list_includes_stats(session, client):
    """列表带卡片统计（总数/进行中/已完成）。"""
    project = await make_project(session, name="统计项目")
    await make_card(session, project=project, title="待办卡", status=CardStatus.TODO.value)
    await make_card(session, project=project, title="进行中卡", status=CardStatus.IN_PROGRESS.value)
    await make_card(session, project=project, title="完成卡", status=CardStatus.DONE.value)
    await session.commit()

    items = (await client.get("/api/projects")).json()
    target = next(p for p in items if p["name"] == "统计项目")
    assert target["stats"] == {"total": 3, "in_progress": 1, "done": 1}


async def test_agent_md_written_to_directory(session, client, tmp_path):
    """授权目录存在且填了 AGENT.md 时，写入目录根。"""
    resp = await client.post(
        "/api/projects",
        json={
            "name": "带规范项目",
            "directory": str(tmp_path),
            "agent_md": "# 项目规范\n技术栈：Python",
        },
    )
    assert resp.status_code == 201
    assert (tmp_path / "AGENT.md").read_text(encoding="utf-8") == "# 项目规范\n技术栈：Python"


async def test_agent_md_skipped_when_dir_missing(session, client):
    """授权目录不存在时创建成功但不写文件。"""
    resp = await client.post(
        "/api/projects",
        json={"name": "无目录项目", "directory": "/nonexistent/path/xyz", "agent_md": "# x"},
    )
    assert resp.status_code == 201
    assert resp.json()["directory"] == "/nonexistent/path/xyz"


async def test_duplicate_name_conflict(session, client):
    """重名项目返回 409。"""
    await make_project(session, name="唯一名")
    await session.commit()
    resp = await client.post("/api/projects", json={"name": "唯一名"})
    assert resp.status_code == 409


async def test_archive_and_restore(session, client):
    """归档后状态 archived；可恢复为 active。"""
    project = await make_project(session, name="要归档")
    await session.commit()

    archived = await client.patch(f"/api/projects/{project.id}", json={"status": "archived"})
    assert archived.status_code == 200
    assert archived.json()["status"] == ProjectStatus.ARCHIVED.value

    restored = await client.patch(f"/api/projects/{project.id}", json={"status": "active"})
    assert restored.json()["status"] == ProjectStatus.ACTIVE.value


async def test_archive_filter(session, client):
    """include_archived=false 只返回 active 项目。"""
    await make_project(session, name="活跃项目")
    await make_project(session, name="归档项目", status=ProjectStatus.ARCHIVED.value)
    await session.commit()

    items = (await client.get("/api/projects?include_archived=false")).json()
    names = {p["name"] for p in items}
    assert "活跃项目" in names
    assert "归档项目" not in names


async def test_invalid_status_rejected(session, client):
    """非法状态返回 422。"""
    project = await make_project(session, name="状态测试")
    await session.commit()
    resp = await client.patch(f"/api/projects/{project.id}", json={"status": "deleted"})
    assert resp.status_code == 422


async def test_get_detail_and_missing(session, client):
    """详情查询与 404。"""
    project = await make_project(session, name="详情项目")
    await session.commit()
    detail = await client.get(f"/api/projects/{project.id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "详情项目"

    missing = await client.get("/api/projects/99999")
    assert missing.status_code == 404
