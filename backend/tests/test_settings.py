"""设置 API 测试：大模型 / 向量 / 通知勾选 / 邮件 / 项目默认模型。"""


async def test_llm_provider_crud(session, client):
    """新增/删除 provider；删除默认 provider 时清默认。"""
    r = await client.post(
        "/api/settings/llm/providers",
        json={"name": "DeepSeek", "base_url": "https://api.deepseek.com", "api_key": "sk-1", "models": ["deepseek-chat"]},
    )
    assert r.status_code == 200
    providers = r.json()["providers"]
    assert len(providers) == 1
    pid = providers[0]["id"]
    assert providers[0]["api_key"] == "sk-1"

    # 设为默认
    r = await client.put("/api/settings/llm", json={"providers": providers, "default": {"provider_id": pid, "model": "deepseek-chat"}})
    assert r.json()["default"]["provider_id"] == pid

    # 删除 → 默认清空
    r = await client.delete(f"/api/settings/llm/providers/{pid}")
    assert r.json()["providers"] == []
    assert r.json()["default"] is None


async def test_llm_provider_validation(session, client):
    r = await client.post("/api/settings/llm/providers", json={"name": "", "base_url": ""})
    assert r.status_code == 422


async def test_vector_settings(session, client):
    body = {"provider": "milvus", "base_url": "http://localhost:19531", "api_key": "", "model": "bge-m3", "dims": 1024}
    r = await client.put("/api/settings/vector", json=body)
    assert r.status_code == 200
    assert r.json()["model"] == "bge-m3"

    r = await client.get("/api/settings/vector")
    assert r.json()["dims"] == 1024


async def test_email_settings(session, client):
    body = {"smtp_host": "smtp.example.com", "smtp_port": 465, "smtp_user": "u", "smtp_pass": "p", "from_addr": "a@b.com", "to_addr": "me@b.com"}
    r = await client.put("/api/settings/email", json=body)
    assert r.status_code == 200
    assert r.json()["to_addr"] == "me@b.com"

    r = await client.get("/api/settings/email")
    assert r.json()["smtp_host"] == "smtp.example.com"


async def test_notification_prefs(session, client):
    r = await client.put("/api/settings/notification-prefs", json={"completed": False, "unknown": True})
    assert r.status_code == 200
    prefs = r.json()
    assert prefs["completed"] is False  # 可关
    assert "unknown" not in prefs  # 未知类别被过滤
    assert prefs["failed"] is True  # 默认全量保留


async def test_project_model(session, client):
    from tests.factories import make_project

    project = await make_project(session, name="模型项目")
    await session.commit()

    body = {"provider_id": "p_1", "model": "deepseek-reasoner"}
    r = await client.put(f"/api/projects/{project.id}/settings/model", json=body)
    assert r.status_code == 200
    assert r.json()["model"] == "deepseek-reasoner"

    r = await client.get(f"/api/projects/{project.id}/settings/model")
    assert r.json()["provider_id"] == "p_1"

    r = await client.get("/api/projects/99999/settings/model")
    assert r.status_code == 404


async def test_auto_claim_default_and_update(session, client):
    """项目级自动领取配置：默认关闭；可开启并设置时间段。"""
    from tests.factories import make_project

    project = await make_project(session, name="领取项目")
    await session.commit()

    r = await client.get(f"/api/projects/{project.id}/settings/auto-claim")
    assert r.json()["enabled"] is False
    assert r.json()["start_time"] == "22:00"

    r = await client.put(
        f"/api/projects/{project.id}/settings/auto-claim",
        json={"enabled": True, "start_time": "23:30", "end_time": "07:00"},
    )
    assert r.json()["enabled"] is True
    assert r.json()["start_time"] == "23:30"
    assert r.json()["end_time"] == "07:00"

    r = await client.get(f"/api/projects/{project.id}/settings/auto-claim")
    assert r.json()["enabled"] is True


async def test_llm_provider_update(session, client):
    """编辑 provider：改名称/URL/模型，API key 可单独更新。"""
    r = await client.post(
        "/api/settings/llm/providers",
        json={"name": "DeepSeek", "base_url": "https://api.deepseek.com", "api_key": "sk-1", "models": [{"display": "快版", "request": "deepseek-chat"}]},
    )
    pid = r.json()["providers"][0]["id"]

    r = await client.put(
        f"/api/settings/llm/providers/{pid}",
        json={"name": "DeepSeek 新版", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-2", "models": [{"display": "快版", "request": "deepseek-chat"}, {"display": "推理版", "request": "deepseek-reasoner"}]},
    )
    assert r.status_code == 200
    p = r.json()["providers"][0]
    assert p["name"] == "DeepSeek 新版"
    assert p["api_key"] == "sk-2"
    assert p["models"] == [
        {"display": "快版", "request": "deepseek-chat"},
        {"display": "推理版", "request": "deepseek-reasoner"},
    ]

    r = await client.put(f"/api/settings/llm/providers/{pid}", json={"api_key": "sk-3"})
    assert r.json()["providers"][0]["api_key"] == "sk-3"
    assert r.json()["providers"][0]["name"] == "DeepSeek 新版"  # 其余字段不变

    r = await client.put("/api/settings/llm/providers/nope", json={"name": "x"})
    assert r.status_code == 404


async def test_llm_provider_legacy_string_models(session, client):
    """兼容旧版 string[] 模型列表：自动转 {display, request}。"""
    r = await client.post(
        "/api/settings/llm/providers",
        json={"name": "旧厂商", "base_url": "https://x.com", "api_key": "", "models": ["m1", "m2"]},
    )
    assert r.status_code == 200
    p = r.json()["providers"][0]
    assert p["models"] == [{"display": "m1", "request": "m1"}, {"display": "m2", "request": "m2"}]
