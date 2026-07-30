from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import GenerateEmailRequest, GeneratedEmail
from app.services.ai_service import AIServiceError, generate_outreach_email
from app.services.telegram_service import notify_email_result

router = APIRouter(prefix="/emails", tags=["emails"])

RESEND_URL = "https://api.resend.com/emails"


@router.get("/history")
def list_email_history(user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    result = (
        db.table("email_history")
        .select("*, businesses!inner(user_id, name)")
        .eq("businesses.user_id", user_id)
        .order("date_generated", desc=True)
        .execute()
    )
    return result.data


@router.post("/generate", response_model=GeneratedEmail, status_code=201)
async def generate_email(request: GenerateEmailRequest, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()

    biz = (
        db.table("businesses")
        .select("*")
        .eq("id", str(request.business_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not biz.data:
        raise HTTPException(status_code=404, detail="Business not found")
    if not biz.data.get("public_email"):
        raise HTTPException(status_code=400, detail="No public email on file — cannot generate outreach yet")

    audit = (
        db.table("audits")
        .select("*")
        .eq("business_id", str(request.business_id))
        .order("created_at", desc=True)
        .limit(1)
        .single()
        .execute()
    )
    if not audit.data:
        raise HTTPException(status_code=400, detail="Run an audit before generating an email")

    findings = db.table("audit_findings").select("*").eq("audit_id", audit.data["id"]).execute()
    settings_row = (
        db.table("settings")
        .select("ai_provider, ai_model, openai_api_key, claude_api_key, gemini_api_key, grok_api_key")
        .eq("user_id", user_id)
        .single()
        .execute()
        .data
        or {}
    )
    provider = settings_row.get("ai_provider", "openai")
    key_field = {"openai": "openai_api_key", "claude": "claude_api_key", "gemini": "gemini_api_key", "grok": "grok_api_key"}.get(
        provider, "openai_api_key"
    )
    api_key = settings_row.get(key_field, "")

    from app.models.schemas import Audit, AuditScores, Business

    audit_model = Audit(
        **audit.data,
        scores=AuditScores(
            website_score=audit.data["website_score"],
            google_business_score=audit.data["google_business_score"],
            overall_score=audit.data["overall_score"],
            opportunity_score=audit.data["opportunity_score"],
        ),
        findings=findings.data,
    )
    business_model = Business(**biz.data)

    try:
        content = await generate_outreach_email(
            business_model,
            audit_model,
            api_key,
            provider=provider,
            model=settings_row.get("ai_model"),
        )
    except AIServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))

    email_row = (
        db.table("generated_emails")
        .insert(
            {
                "business_id": str(request.business_id),
                "subject": content["subject"],
                "body": content["body"],
                "status": "draft",
            }
        )
        .execute()
        .data[0]
    )
    db.table("businesses").update({"email_status": "draft"}).eq("id", str(request.business_id)).execute()
    db.table("activity_log").insert(
        {
            "user_id": user_id,
            "business_id": str(request.business_id),
            "action": "Email Generated",
            "status": "success",
        }
    ).execute()

    return email_row


@router.post("/{email_id}/send", status_code=200)
async def send_email(email_id: UUID, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()

    email_row = db.table("generated_emails").select("*").eq("id", str(email_id)).single().execute()
    if not email_row.data:
        raise HTTPException(status_code=404, detail="Email not found")

    biz = (
        db.table("businesses")
        .select("*")
        .eq("id", email_row.data["business_id"])
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not biz.data:
        raise HTTPException(status_code=404, detail="Business not found")
    if not biz.data.get("public_email"):
        raise HTTPException(status_code=400, detail="No verified public email — cannot send")

    settings_row = (
        db.table("settings")
        .select("resend_api_key, telegram_bot_token, telegram_chat_id")
        .eq("user_id", user_id)
        .single()
        .execute()
        .data
        or {}
    )
    resend_key = settings_row.get("resend_api_key")
    if not resend_key:
        raise HTTPException(status_code=400, detail="Resend API key not configured")

    payload = {
        "from": "outreach@calebreview.com",
        "to": [biz.data["public_email"]],
        "subject": email_row.data["subject"],
        "text": email_row.data["body"],
    }
    headers = {"Authorization": f"Bearer {resend_key}"}

    status = "Sent"
    detail = None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(RESEND_URL, json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        status = "Failed"
        detail = str(e)

    now = datetime.now(timezone.utc).isoformat()
    db.table("email_history").insert(
        {
            "business_id": biz.data["id"],
            "email_id": str(email_id),
            "recipient": biz.data["public_email"],
            "subject": email_row.data["subject"],
            "date_sent": now if status == "Sent" else None,
            "delivery_status": status,
        }
    ).execute()
    db.table("generated_emails").update(
        {"status": "sent" if status == "Sent" else "failed"}
    ).eq("id", str(email_id)).execute()
    db.table("businesses").update(
        {"email_status": "sent" if status == "Sent" else "failed"}
    ).eq("id", biz.data["id"]).execute()
    db.table("activity_log").insert(
        {
            "user_id": user_id,
            "business_id": biz.data["id"],
            "action": "Email Sent" if status == "Sent" else "Email Failed",
            "status": "success" if status == "Sent" else "error",
            "detail": detail,
        }
    ).execute()

    # Telegram notification — best-effort, never blocks or fails the request.
    await notify_email_result(
        bot_token=settings_row.get("telegram_bot_token"),
        chat_id=settings_row.get("telegram_chat_id"),
        status="sent" if status == "Sent" else "failed",
        business_name=biz.data["name"],
        recipient=biz.data["public_email"],
        error_detail=detail,
    )

    if status == "Failed":
        raise HTTPException(status_code=502, detail=f"Resend delivery failed: {detail}")

    return {"status": status}
