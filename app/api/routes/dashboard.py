from fastapi import APIRouter, Depends

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import DashboardTotals

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/totals", response_model=DashboardTotals)
def get_dashboard_totals(user_id: str = Depends(get_current_user_id)):
    db = get_supabase()

    businesses = (
        db.table("businesses").select("id", count="exact").eq("user_id", user_id).eq("is_deleted", False).execute()
    )
    audits = (
        db.table("audits")
        .select("id, businesses!inner(user_id)", count="exact")
        .eq("businesses.user_id", user_id)
        .execute()
    )
    pdfs_ready = (
        db.table("businesses")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("pdf_status", "ready")
        .execute()
    )
    emails_generated = (
        db.table("generated_emails")
        .select("id, businesses!inner(user_id)", count="exact")
        .eq("businesses.user_id", user_id)
        .execute()
    )
    emails_sent = (
        db.table("email_history")
        .select("id, businesses!inner(user_id)", count="exact")
        .eq("businesses.user_id", user_id)
        .eq("delivery_status", "Sent")
        .execute()
    )
    leads_processed = (
        db.table("businesses")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("audit_status", "complete")
        .execute()
    )

    return DashboardTotals(
        total_businesses=businesses.count or 0,
        total_audits=audits.count or 0,
        total_pdfs=pdfs_ready.count or 0,
        total_emails_generated=emails_generated.count or 0,
        total_emails_sent=emails_sent.count or 0,
        total_leads_processed=leads_processed.count or 0,
    )
