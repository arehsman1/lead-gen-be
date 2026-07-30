"""
Sends a Telegram notification whenever an outreach email is sent or fails
to send. Uses the Telegram Bot API directly (no SDK needed — it's one
POST request). Message formatting is a pure function so it's fully
testable without hitting Telegram's API.

Setup (same pattern as Caleb's existing branding bot):
1. Message @BotFather on Telegram, /newbot, get the bot token.
2. Message your new bot once (anything), then hit
   https://api.telegram.org/bot<TOKEN>/getUpdates to find your chat_id
   in the response.
3. Put both in Settings — bot token and chat ID.
"""

import httpx

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def format_email_notification(
    status: str,  # "sent" | "failed"
    business_name: str,
    recipient: str,
    error_detail: str | None = None,
) -> str:
    if status == "sent":
        return (
            f"\u2705 Email sent\n"
            f"Business: {business_name}\n"
            f"To: {recipient}"
        )
    return (
        f"\u274c Email failed\n"
        f"Business: {business_name}\n"
        f"To: {recipient}\n"
        f"Reason: {error_detail or 'Unknown error'}"
    )


async def send_telegram_message(
    bot_token: str, chat_id: str, text: str, timeout: float = 10.0
) -> tuple[bool, str | None]:
    """Returns (ok, error_detail) rather than a bare bool. Previously this
    only ever returned True/False, which meant a bad bot token, a bad
    chat_id, and a network error all looked identical to the caller — the
    Settings "test connection" flow could only ever say "Failed to send
    test message" with no way to tell the user what was actually wrong.
    error_detail is Telegram's own error description when available (e.g.
    "Unauthorized" for a bad token, "Bad Request: chat not found" for a
    bad chat_id). Callers that don't care (the fire-and-forget email
    notification flow) can just ignore the second value."""
    if not bot_token or not chat_id:
        return False, "Bot token and chat ID are both required"

    url = TELEGRAM_API_URL.format(token=bot_token)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
    except httpx.HTTPError as e:
        return False, f"Network error reaching Telegram: {e}"

    if resp.status_code == 200:
        return True, None

    try:
        detail = resp.json().get("description") or f"HTTP {resp.status_code}"
    except ValueError:
        detail = f"HTTP {resp.status_code}"
    return False, detail


async def notify_email_result(
    bot_token: str | None,
    chat_id: str | None,
    status: str,
    business_name: str,
    recipient: str,
    error_detail: str | None = None,
) -> None:
    """Convenience wrapper: builds the message and sends it, doing nothing
    if Telegram isn't configured for this user."""
    if not bot_token or not chat_id:
        return
    message = format_email_notification(status, business_name, recipient, error_detail)
    await send_telegram_message(bot_token, chat_id, message)
