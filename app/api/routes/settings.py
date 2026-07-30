import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import (
    ListModelsRequest,
    ListModelsResult,
    SettingsIn,
    SettingsOut,
    TestConnectionRequest,
    TestConnectionResult,
)
from app.services.ai_service import AIServiceError, list_available_models
from app.services.telegram_service import send_telegram_message

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings_route(user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    row = db.table("settings").select("*").eq("user_id", user_id).single().execute().data or {}
    return SettingsOut(
        openai_api_key_set=bool(row.get("openai_api_key")),
        claude_api_key_set=bool(row.get("claude_api_key")),
        gemini_api_key_set=bool(row.get("gemini_api_key")),
        grok_api_key_set=bool(row.get("grok_api_key")),
        ai_provider=row.get("ai_provider", "openai"),
        ai_model=row.get("ai_model"),
        serpapi_key_set=bool(row.get("serpapi_key")),
        apify_token_set=bool(row.get("apify_token")),
        resend_api_key_set=bool(row.get("resend_api_key")),
        telegram_bot_token_set=bool(row.get("telegram_bot_token")),
        telegram_chat_id=row.get("telegram_chat_id"),
        default_industry=row.get("default_industry"),
        default_location=row.get("default_location"),
        serpapi_enabled=row.get("serpapi_enabled", True),
        apify_enabled=row.get("apify_enabled", True),
        brand_name=row.get("brand_name", "CALEBREVIEW Lead Gen"),
    )


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()

    # Only overwrite a key field if a non-empty value was actually sent —
    # this lets the frontend save other fields without blanking out a key
    # the user isn't touching this time.
    update = {
        "default_industry": body.default_industry,
        "default_location": body.default_location,
        "serpapi_enabled": body.serpapi_enabled,
        "apify_enabled": body.apify_enabled,
        "brand_name": body.brand_name,
        # Not a secret, and unlike a key field there's no "leave blank to
        # keep the old value" case that makes sense here — the picker
        # always has a value, so this always overwrites.
        "ai_provider": body.ai_provider.value,
    }
    if body.ai_model is not None:
        update["ai_model"] = body.ai_model
    # telegram_chat_id isn't a secret, so it's always overwritten (empty
    # string clears it) rather than only-if-non-empty like the API keys.
    if body.telegram_chat_id is not None:
        update["telegram_chat_id"] = body.telegram_chat_id

    for key_field in (
        "openai_api_key",
        "claude_api_key",
        "gemini_api_key",
        "grok_api_key",
        "serpapi_key",
        "apify_token",
        "resend_api_key",
        "telegram_bot_token",
    ):
        value = getattr(body, key_field)
        if value:
            update[key_field] = value

    db.table("settings").update(update).eq("user_id", user_id).execute()
    return get_settings_route(user_id)


@router.post("/test-connection", response_model=TestConnectionResult)
async def test_connection(body: TestConnectionRequest, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    row = db.table("settings").select("*").eq("user_id", user_id).single().execute().data or {}

    checks = {
        "openai": ("openai_api_key", "https://api.openai.com/v1/models"),
        "grok": ("grok_api_key", "https://api.x.ai/v1/models"),
        "serpapi": ("serpapi_key", "https://serpapi.com/account"),
        "resend": ("resend_api_key", "https://api.resend.com/domains"),
    }

    if body.provider == "claude":
        key = row.get("claude_api_key")
        if not key:
            return TestConnectionResult(provider="claude", ok=False, message="No key saved")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            )
        return TestConnectionResult(
            provider="claude",
            ok=resp.status_code == 200,
            message="Connected" if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )

    if body.provider == "gemini":
        key = row.get("gemini_api_key")
        if not key:
            return TestConnectionResult(provider="gemini", ok=False, message="No key saved")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key},
            )
        return TestConnectionResult(
            provider="gemini",
            ok=resp.status_code == 200,
            message="Connected" if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )

    if body.provider == "apify":
        token = row.get("apify_token")
        if not token:
            return TestConnectionResult(provider="apify", ok=False, message="No Apify token saved")
        url = f"https://api.apify.com/v2/users/me?token={token}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        return TestConnectionResult(provider="apify", ok=resp.status_code == 200, message=str(resp.status_code))

    if body.provider == "telegram":
        bot_token = row.get("telegram_bot_token")
        chat_id = row.get("telegram_chat_id")
        if not bot_token or not chat_id:
            return TestConnectionResult(provider="telegram", ok=False, message="Bot token and chat ID both required")
        # send_telegram_message returns (ok, error_detail) rather than a
        # bare bool specifically so failures can say *why* — a bad token,
        # a bad chat ID, and a network error all used to look identical
        # ("Failed to send test message"). This used to pass the whole
        # tuple into `ok: bool` below, which raised a Pydantic
        # ValidationError on every single call regardless of whether the
        # credentials were actually right — the exact "keeps failing, no
        # idea why" symptom, since the error was in this wiring, not
        # necessarily in whatever token the user typed in.
        ok, error_detail = await send_telegram_message(
            bot_token, chat_id, "\u2705 CALEBREVIEW notifications are connected."
        )
        return TestConnectionResult(
            provider="telegram",
            ok=ok,
            message="Test message sent — check Telegram" if ok else (error_detail or "Failed to send test message"),
        )

    if body.provider not in checks:
        return TestConnectionResult(provider=body.provider, ok=False, message="Unknown provider")

    key_field, url = checks[body.provider]
    key = row.get(key_field)
    if not key:
        return TestConnectionResult(provider=body.provider, ok=False, message="No key saved")

    headers = {"Authorization": f"Bearer {key}"} if body.provider != "serpapi" else {}
    params = {"api_key": key} if body.provider == "serpapi" else {}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers, params=params)

    return TestConnectionResult(
        provider=body.provider,
        ok=resp.status_code == 200,
        message="Connected" if resp.status_code == 200 else f"HTTP {resp.status_code}",
    )


AI_KEY_FIELD = {"openai": "openai_api_key", "claude": "claude_api_key", "gemini": "gemini_api_key", "grok": "grok_api_key"}


@router.post("/list-models", response_model=ListModelsResult)
async def list_models_route(body: ListModelsRequest, user_id: str = Depends(get_current_user_id)):
    """Backs the Settings page's "Refresh from account" button — asks the
    provider directly which models this key can use, rather than relying
    on ai_service.PROVIDER_MODELS' curated (and inevitably stale) defaults.
    Accepts an unsaved, just-typed key via body.api_key so you can check
    before saving; falls back to the saved key for that provider otherwise."""
    api_key = body.api_key
    if not api_key:
        db = get_supabase()
        row = db.table("settings").select("*").eq("user_id", user_id).single().execute().data or {}
        api_key = row.get(AI_KEY_FIELD[body.provider.value])

    try:
        models = await list_available_models(body.provider.value, api_key or "")
    except AIServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return ListModelsResult(provider=body.provider, models=models)
