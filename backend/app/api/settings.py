"""设置 API：全局设置（大模型 / 向量 / 通知勾选 / 邮件）与项目默认模型。

存储：Setting 表 JSONB（scope=global 或 scope=project+project_id）。
API key 本地明文存储（本地单机，用户拍板 API key 本地配置）。
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.enums import SettingScope
from app.db.models import Project, Setting
from app.schemas.setting import (
    EmailSettingsIn,
    LLMSettingsIn,
    ProjectModelIn,
    VectorSettingsIn,
)
from app.services.notice_service import get_prefs, set_prefs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])

DEFAULT_LLM = {"providers": [], "default": None}
DEFAULT_VECTOR = {"provider": "", "base_url": "", "api_key": "", "model": "", "dims": 0}
DEFAULT_EMAIL = {
    "smtp_host": "",
    "smtp_port": 465,
    "smtp_user": "",
    "smtp_pass": "",
    "from_addr": "",
    "to_addr": "",  # 审批挂起 30 分钟提醒的收件邮箱
}


def _norm_models(models) -> list[dict]:
    """模型列表规范化：统一为 [{display, request}]；兼容旧 string[] 数据。"""
    out = []
    for m in models or []:
        if isinstance(m, str) and m.strip():
            name = m.strip()
            out.append({"display": name, "request": name})
        elif isinstance(m, dict) and (m.get("request") or "").strip():
            request = str(m["request"]).strip()
            out.append({"display": str(m.get("display") or request).strip(), "request": request})
    return out


def _normalize_llm(value: dict) -> dict:
    """返回规范化后的完整大模型配置（旧数据兼容）。"""
    providers = []
    for p in value.get("providers", []):
        providers.append({**p, "models": _norm_models(p.get("models"))})
    return {"providers": providers, "default": value.get("default")}


async def _get_setting(session: AsyncSession, scope: str, key: str, project_id: int | None = None) -> dict:
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == scope,
                Setting.project_id == project_id,
                Setting.key == key,
            )
        )
    ).scalar_one_or_none()
    return row.value if row is not None else {}


async def _save_setting(
    session: AsyncSession, scope: str, key: str, value: dict, project_id: int | None = None
) -> None:
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == scope,
                Setting.project_id == project_id,
                Setting.key == key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = Setting(scope=scope, project_id=project_id, key=key, value=value)
        session.add(row)
    else:
        row.value = value
    await session.commit()


# ---------- 大模型（全局） ----------


@router.get("/settings/llm")
async def get_llm_settings(session: AsyncSession = Depends(get_session)) -> dict:
    value = await _get_setting(session, SettingScope.GLOBAL.value, "llm")
    return {**DEFAULT_LLM, **_normalize_llm(value)}


@router.put("/settings/llm")
async def put_llm_settings(
    body: LLMSettingsIn, session: AsyncSession = Depends(get_session)
) -> dict:
    value = body.model_dump()
    value["providers"] = [
        {**p, "models": _norm_models(p.get("models"))} for p in value.get("providers", [])
    ]
    await _save_setting(session, SettingScope.GLOBAL.value, "llm", value)
    return {**DEFAULT_LLM, **_normalize_llm(value)}


@router.post("/settings/llm/providers")
async def add_llm_provider(
    body: dict, session: AsyncSession = Depends(get_session)
) -> dict:
    """新增自定义大模型 provider。body: {name, base_url, api_key, models[]}"""
    name = (body.get("name") or "").strip()
    base_url = (body.get("base_url") or "").strip()
    if not name or not base_url:
        raise HTTPException(status_code=422, detail="名称与 Base URL 必填")
    value = await _get_setting(session, SettingScope.GLOBAL.value, "llm")
    providers = value.get("providers", [])
    providers.append(
        {
            "id": f"p_{uuid.uuid4().hex[:8]}",
            "name": name,
            "base_url": base_url,
            "api_key": (body.get("api_key") or "").strip(),
            "models": _norm_models(body.get("models")),
        }
    )
    value["providers"] = providers
    await _save_setting(session, SettingScope.GLOBAL.value, "llm", value)
    return {**DEFAULT_LLM, **_normalize_llm(value)}


@router.put("/settings/llm/providers/{provider_id}")
async def update_llm_provider(
    provider_id: str, body: dict, session: AsyncSession = Depends(get_session)
) -> dict:
    """更新自定义大模型 provider（编辑）。"""
    value = await _get_setting(session, SettingScope.GLOBAL.value, "llm")
    providers = value.get("providers", [])
    for p in providers:
        if p["id"] == provider_id:
            if body.get("name") is not None:
                name = str(body["name"]).strip()
                if not name:
                    raise HTTPException(status_code=422, detail="名称不能为空")
                p["name"] = name
            if body.get("base_url") is not None:
                base_url = str(body["base_url"]).strip()
                if not base_url:
                    raise HTTPException(status_code=422, detail="Base URL 不能为空")
                p["base_url"] = base_url
            if body.get("api_key") is not None:
                p["api_key"] = str(body["api_key"]).strip()
            if body.get("models") is not None:
                p["models"] = _norm_models(body.get("models"))
            await _save_setting(session, SettingScope.GLOBAL.value, "llm", value)
            return {**DEFAULT_LLM, **_normalize_llm(value)}
    raise HTTPException(status_code=404, detail="模型不存在")


@router.delete("/settings/llm/providers/{provider_id}")
async def delete_llm_provider(
    provider_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    value = await _get_setting(session, SettingScope.GLOBAL.value, "llm")
    value["providers"] = [p for p in value.get("providers", []) if p["id"] != provider_id]
    if value.get("default") and value["default"].get("provider_id") == provider_id:
        value["default"] = None
    await _save_setting(session, SettingScope.GLOBAL.value, "llm", value)
    return {**DEFAULT_LLM, **_normalize_llm(value)}


# ---------- 项目默认模型（scope=project） ----------


@router.get("/projects/{project_id}/settings/model")
async def get_project_model(
    project_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    value = await _get_setting(session, SettingScope.PROJECT.value, "model", project_id)
    return value or {}


@router.put("/projects/{project_id}/settings/model")
async def put_project_model(
    project_id: int, body: ProjectModelIn, session: AsyncSession = Depends(get_session)
) -> dict:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    value = body.model_dump()
    await _save_setting(session, SettingScope.PROJECT.value, "model", value, project_id)
    return value


# ---------- 向量（全局） ----------


@router.get("/settings/vector")
async def get_vector_settings(session: AsyncSession = Depends(get_session)) -> dict:
    value = await _get_setting(session, SettingScope.GLOBAL.value, "vector")
    return {**DEFAULT_VECTOR, **value}


@router.put("/settings/vector")
async def put_vector_settings(
    body: VectorSettingsIn, session: AsyncSession = Depends(get_session)
) -> dict:
    value = body.model_dump()
    await _save_setting(session, SettingScope.GLOBAL.value, "vector", value)
    return {**DEFAULT_VECTOR, **value}


# ---------- 自动领取（项目级，配置存储；调度在阶段 4 接入） ----------

DEFAULT_AUTO_CLAIM = {"enabled": False, "start_time": "22:00", "end_time": "08:00"}


@router.get("/projects/{project_id}/settings/auto-claim")
async def get_auto_claim(
    project_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    value = await _get_setting(session, SettingScope.PROJECT.value, "auto_claim", project_id)
    return {**DEFAULT_AUTO_CLAIM, **value}


@router.put("/projects/{project_id}/settings/auto-claim")
async def put_auto_claim(
    project_id: int, body: dict, session: AsyncSession = Depends(get_session)
) -> dict:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    value = {**DEFAULT_AUTO_CLAIM, "enabled": bool(body.get("enabled", False))}
    if body.get("start_time"):
        value["start_time"] = str(body["start_time"])
    if body.get("end_time"):
        value["end_time"] = str(body["end_time"])
    await _save_setting(session, SettingScope.PROJECT.value, "auto_claim", value, project_id)
    return value


# ---------- 通知勾选（全局） ----------


@router.get("/settings/notification-prefs")
async def get_notification_prefs(session: AsyncSession = Depends(get_session)) -> dict:
    return await get_prefs(session)


@router.put("/settings/notification-prefs")
async def put_notification_prefs(body: dict, session: AsyncSession = Depends(get_session)) -> dict:
    return await set_prefs(session, body)


# ---------- 邮件（全局） ----------


@router.get("/settings/email")
async def get_email_settings(session: AsyncSession = Depends(get_session)) -> dict:
    value = await _get_setting(session, SettingScope.GLOBAL.value, "email")
    return {**DEFAULT_EMAIL, **value}


@router.put("/settings/email")
async def put_email_settings(
    body: EmailSettingsIn, session: AsyncSession = Depends(get_session)
) -> dict:
    value = body.model_dump()
    await _save_setting(session, SettingScope.GLOBAL.value, "email", value)
    return {**DEFAULT_EMAIL, **value}
