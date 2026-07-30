import pytest

from app.services.telegram_service import (
    format_email_notification,
    notify_email_result,
    send_telegram_message,
)


def test_sent_notification_format():
    msg = format_email_notification("sent", "Kogi Comfort HVAC", "info@kogicomforthvac.com")
    assert "\u2705" in msg
    assert "Kogi Comfort HVAC" in msg
    assert "info@kogicomforthvac.com" in msg
    assert "Reason" not in msg


def test_failed_notification_format_includes_reason():
    msg = format_email_notification("failed", "Bright Smile Dental", "info@brightsmile.com", "Invalid recipient")
    assert "\u274c" in msg
    assert "Bright Smile Dental" in msg
    assert "Invalid recipient" in msg


def test_failed_notification_without_detail_has_fallback_text():
    msg = format_email_notification("failed", "Biz", "a@b.com", None)
    assert "Unknown error" in msg


@pytest.mark.asyncio
async def test_send_returns_false_without_credentials():
    ok, error_detail = await send_telegram_message("", "", "hello")
    assert ok is False
    assert error_detail == "Bot token and chat ID are both required"


@pytest.mark.asyncio
async def test_notify_is_a_noop_when_not_configured():
    # Should not raise even with no bot_token/chat_id — Telegram is opt-in.
    await notify_email_result(None, None, "sent", "Biz", "a@b.com")
    await notify_email_result("", "", "sent", "Biz", "a@b.com")
