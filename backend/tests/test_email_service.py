"""邮件服务测试：开关、配置缺失、成功发送、失败重试与站内补提示。"""

from app.db.enums import NoticeCategory
from app.services import email_service, notice_service

CFG = email_service.SmtpConfig(
    host="smtp.test", port=465, user="u", password="p", to_email="me@test"
)


async def _configure(session, enabled: bool = True) -> None:
    await email_service.set_smtp_config(session, CFG)
    await email_service.set_approval_email_enabled(session, enabled)


async def test_disabled_skips(session):
    """开关关闭：不发送不补站内。"""
    await email_service.set_smtp_config(session, CFG)
    sent: list = []

    async def fake(cfg, subject, body):
        sent.append(cfg)

    ok = await email_service.send_approval_reminder(session, card_title="卡A", send_impl=fake)
    assert ok is False
    assert sent == []
    assert await notice_service.list_unread(session) == []


async def test_missing_config_skips(session):
    """开启但未配置 SMTP：跳过且不报错。"""
    await email_service.set_approval_email_enabled(session, True)
    ok = await email_service.send_approval_reminder(session, card_title="卡A")
    assert ok is False


async def test_send_success(session):
    """配置齐全 + 开关开启：调用发送实现，返回成功。"""
    await _configure(session)
    calls: list[str] = []

    async def fake(cfg, subject, body):
        calls.append(subject)
        assert cfg.to_email == "me@test"
        assert "卡A" in body

    ok = await email_service.send_approval_reminder(session, card_title="卡A", send_impl=fake)
    assert ok is True
    assert len(calls) == 1


async def test_retries_then_succeeds(session):
    """前两次失败、第三次成功：共尝试 3 次，最终成功。"""
    await _configure(session)
    attempts = 0

    async def flaky(cfg, subject, body):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("smtp down")

    ok = await email_service.send_approval_reminder(
        session, card_title="卡A", send_impl=flaky, backoff=(0, 0)
    )
    assert ok is True
    assert attempts == 3


async def test_all_fail_adds_internal_notice(session):
    """全部失败：站内补一条 force 通知（审批类，不受勾选影响）。"""
    await _configure(session)

    async def always_fail(cfg, subject, body):
        raise ConnectionError("always down")

    ok = await email_service.send_approval_reminder(
        session, card_title="卡A", send_impl=always_fail, backoff=(0, 0)
    )
    assert ok is False
    notices = await notice_service.list_unread(session)
    assert len(notices) == 1
    assert notices[0].category == NoticeCategory.APPROVAL_WAITING.value
    assert "发送失败" in notices[0].content
