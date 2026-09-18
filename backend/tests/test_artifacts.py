"""A6 产物服务测试：上传落盘、元数据、列表、预览下载、路径安全。"""

from app.core.config import settings
from app.db.enums import ArtifactType
from tests.factories import make_card, make_project

TEST_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # 伪 PNG 头 + 填充
TEST_PDF = b"%PDF-1.4\n" + b"%%EOF\n"


async def test_upload_creates_file_and_metadata(session, client, tmp_path, monkeypatch):
    """上传：文件落盘到产物目录，PG 元数据正确（类型/size/路径）。"""
    monkeypatch.setattr(settings, "artifacts_root", str(tmp_path))
    project = await make_project(session)
    card = await make_card(session, project=project, title="产物卡")
    await session.commit()

    resp = await client.post(
        "/api/artifacts",
        data={"card_id": card.id, "project_id": project.id},
        files={"file": ("diagram.pdf", TEST_PDF, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["size"] == len(TEST_PDF)

    # 文件落盘在 项目/卡片/文件名
    disk = tmp_path / str(project.id) / str(card.id) / "diagram.pdf"
    assert disk.read_bytes() == TEST_PDF


async def test_list_returns_previewable_flag(session, client, tmp_path, monkeypatch):
    """列表：返回卡片产物，pdf/图片/html 标记可预览，代码不可。"""
    monkeypatch.setattr(settings, "artifacts_root", str(tmp_path))
    project = await make_project(session)
    card = await make_card(session, project=project)
    await session.commit()

    await client.post(
        "/api/artifacts",
        data={"card_id": card.id, "project_id": project.id},
        files={"file": ("report.pdf", TEST_PDF, "application/pdf")},
    )
    await client.post(
        "/api/artifacts",
        data={"card_id": card.id, "project_id": project.id},
        files={"file": ("main.py", b"print('hi')", "text/plain")},
    )

    resp = await client.get(f"/api/artifacts?card_id={card.id}")
    items = resp.json()
    by_name = {i["filename"]: i for i in items}
    assert by_name["report.pdf"]["file_type"] == ArtifactType.PDF.value
    assert by_name["report.pdf"]["previewable"] is True
    assert by_name["main.py"]["file_type"] == ArtifactType.CODE.value
    assert by_name["main.py"]["previewable"] is False


async def test_download_returns_content(session, client, tmp_path, monkeypatch):
    """下载：默认附件；inline=1 且可预览时内联。"""
    monkeypatch.setattr(settings, "artifacts_root", str(tmp_path))
    project = await make_project(session)
    card = await make_card(session, project=project)
    await session.commit()
    artifact_id = (
        await client.post(
            "/api/artifacts",
            data={"card_id": card.id, "project_id": project.id},
            files={"file": ("diagram.png", TEST_PNG, "image/png")},
        )
    ).json()["id"]

    att = await client.get(f"/api/artifacts/{artifact_id}/file")
    assert att.status_code == 200
    assert att.content == TEST_PNG
    assert att.headers["content-disposition"].startswith("attachment")

    inline = await client.get(f"/api/artifacts/{artifact_id}/file?inline=1")
    assert inline.headers["content-disposition"].startswith("inline")


async def test_rejects_traversal_filename(session, client, tmp_path, monkeypatch):
    """安全：文件名含路径穿越直接拒绝。"""
    monkeypatch.setattr(settings, "artifacts_root", str(tmp_path))
    project = await make_project(session)
    card = await make_card(session, project=project)
    await session.commit()

    resp = await client.post(
        "/api/artifacts",
        data={"card_id": card.id, "project_id": project.id},
        files={"file": ("../evil.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 400

    # 产物目录里没有任何文件被写出
    assert list(tmp_path.rglob("*")) == []


async def test_missing_artifact_returns_404(session, client, tmp_path, monkeypatch):
    """不存在的产物/缺失文件返回 404。"""
    monkeypatch.setattr(settings, "artifacts_root", str(tmp_path))
    resp = await client.get("/api/artifacts/99999/file")
    assert resp.status_code == 404
