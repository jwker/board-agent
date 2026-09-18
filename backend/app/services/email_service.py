"""邮件服务（TECH-DESIGN §9）。

- 仅审批等待提醒（30 分钟）走 SMTP；配置存全局设置（收件邮箱 + SMTP 服务器/端口/账号/授权码，仅存本机）。
- 由"审批邮件提醒"开关控制（approval_email_enabled）。
- 发送失败退避重试 2-3 次，仍失败记日志 + 站内补提示（邮件是兜底通道，失败不静默）。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import NoticeCategory, SettingScope
from app.db.models import Setting
from app.services import notice_service

logger = logging.getLogger(__name__)

SMTP_KEY = "smtp"
ENABLED_KEY = "approval_email_enabled"

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)  # 第 2/3 次尝试前等待

# 底层发送实现（测试可替换）
SendFunc = Callable[["SmtpConfig", str, str, str], Awaitable[None]]


@dataclass(slots=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    to_email: str


async def get_smtp_config(session: AsyncSession) -> SmtpConfig | None:
    """读取全局 SMTP 配置；缺字段视为未配置。"""
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == SettingScope.GLOBAL.value, Setting.key == SMTP_KEY
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    v = row.value
    try:
        return SmtpConfig(
            host=str(v["host"]),
            port=int(v.get("port", 465)),
            user=str(v["user"]),
            password=str(v["password"]),
            to_email=str(v["to_email"]),
        )
    except (KeyError, TypeError, ValueError):
        logger.warning("SMTP 配置不完整，忽略: %s", v)
        return None


async def set_smtp_config(session: AsyncSession, cfg: SmtpConfig) -> None:
    """保存 SMTP 配置（授权码仅存本机）。"""
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == SettingScope.GLOBAL.value, Setting.key == SMTP_KEY
            )
        )
    ).scalar_one_or_none()
    value = {
        "host": cfg.host,
        "port": cfg.port,
        "user": cfg.user,
        "password": cfg.password,
        "to_email": cfg.to_email,
    }
    if row is None:
        session.add(Setting(scope=SettingScope.GLOBAL.value, key=SMTP_KEY, value=value))
    else:
        row.value = value
    await session.commit()


async def is_approval_email_enabled(session: AsyncSession) -> bool:
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == SettingScope.GLOBAL.value, Setting.key == ENABLED_KEY
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    return bool(row.value.get("enabled", False))


async def set_approval_email_enabled(session: AsyncSession, enabled: bool) -> None:
    row = (
        await session.execute(
            select(Setting).where(
                Setting.scope == SettingScope.GLOBAL.value, Setting.key == ENABLED_KEY
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            Setting(scope=SettingScope.GLOBAL.value, key=ENABLED_KEY, value={"enabled": enabled})
        )
    else:
        row.value = {"enabled": enabled}
    await session.commit()


async def _smtp_send(cfg: SmtpConfig, subject: str, body: str) -> None:
    """真实发送：aiosmtplib STARTTLS/SSL 由端口推断。"""

    from aiosmtplib import SMTP

    use_tls = cfg.port == 465
    smtp = SMTP(hostname=cfg.host, port=cfg.port, use_tls=use_tls)
    async with smtp:
        if not use_tls:
            await smtp.starttls(validate_certs=False)
        await smtp.login(cfg.user, cfg.password)
        await smtp.sendmail(cfg.user, [cfg.to_email], f"Subject: {subject}\r\n\r\n{body}")


async def send_approval_reminder(
    session: AsyncSession,
    *,
    card_title: str,
    project_name: str | None = None,
    send_impl: SendFunc = _smtp_send,
    backoff: tuple[float, float] = BACKOFF_SECONDS,
) -> bool:
    """发送审批 30 分钟提醒邮件。

    前置：开关开启 + SMTP 已配置，否则仅记日志（不补站内，避免重复打扰）。
    失败退避重试 MAX_ATTEMPTS 次；全部失败记日志 + 站内补提示（force=True）。
    返回是否成功。
    """
    if not await is_approval_email_enabled(session):
        logger.info("审批邮件提醒未开启，跳过")
        return False
    cfg = await get_smtp_config(session)
    if cfg is None:
        logger.warning("审批邮件提醒已开启但 SMTP 未配置，跳过")
        return False

    subject = "看板 Agent：有审批等待中"
    body = (
        f"卡片「{card_title}」有审批等待中"
        + (f"（项目：{project_name}）" if project_name else "")
        + "，请及时处理。"
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await send_impl(cfg, subject, body)
            logger.info("审批提醒邮件已发送至 %s（第 %d 次）", cfg.to_email, attempt)
            return True
        except Exception as exc:  # noqa: BLE001 - 重试由本函数管理
            last_error = exc
            logger.warning("邮件发送失败（第 %d/%d 次）: %s", attempt, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(backoff[attempt - 1])

    # 全部失败：站内补提示（force=True，不受勾选控制），不静默
    logger.error("审批提醒邮件发送失败，站内补提示: %s", last_error)
    await notice_service.notify(
        session,
        category=NoticeCategory.APPROVAL_WAITING.value,
        content=f"审批提醒邮件发送失败（{card_title}），请在本机检查 SMTP 配置。",
        force=True,
    )
    return False
