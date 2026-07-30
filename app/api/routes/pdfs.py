from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import Audit, AuditScores, Business, GeneratedPdf
from app.services.pdf_service import generate_audit_pdf
from app.services.storage_service import get_signed_url, upload_pdf

router = APIRouter(prefix="/pdfs", tags=["pdfs"])


@router.post("/business/{business_id}", response_model=GeneratedPdf, status_code=201)
def generate_pdf_for_business(business_id: UUID, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()

    biz_row = (
        db.table("businesses")
        .select("*")
        .eq("id", str(business_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not biz_row.data:
        raise HTTPException(status_code=404, detail="Business not found")

    audit_row = (
        db.table("audits")
        .select("*")
        .eq("business_id", str(business_id))
        .order("created_at", desc=True)
        .limit(1)
        .single()
        .execute()
    )
    if not audit_row.data:
        raise HTTPException(status_code=400, detail="Run an audit before generating a PDF")

    findings = db.table("audit_findings").select("*").eq("audit_id", audit_row.data["id"]).execute()

    business = Business(**biz_row.data)
    audit = Audit(
        **audit_row.data,
        scores=AuditScores(
            website_score=audit_row.data["website_score"],
            google_business_score=audit_row.data["google_business_score"],
            overall_score=audit_row.data["overall_score"],
            opportunity_score=audit_row.data["opportunity_score"],
        ),
        findings=findings.data,
    )

    db.table("businesses").update({"pdf_status": "generating"}).eq("id", str(business_id)).execute()

    pdf_row = (
        db.table("generated_pdfs")
        .insert({"business_id": str(business_id), "audit_id": audit.id.hex, "status": "generating"})
        .execute()
        .data[0]
    )

    try:
        pdf_bytes = generate_audit_pdf(business, audit)
        storage_path = upload_pdf(str(business_id), str(audit.id), pdf_bytes)
    except Exception as e:
        db.table("generated_pdfs").update({"status": "failed"}).eq("id", pdf_row["id"]).execute()
        db.table("businesses").update({"pdf_status": "failed"}).eq("id", str(business_id)).execute()
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    updated = (
        db.table("generated_pdfs")
        .update({"status": "ready", "storage_path": storage_path})
        .eq("id", pdf_row["id"])
        .execute()
        .data[0]
    )
    db.table("businesses").update({"pdf_status": "ready"}).eq("id", str(business_id)).execute()
    db.table("activity_log").insert(
        {
            "user_id": user_id,
            "business_id": str(business_id),
            "action": "PDF Generated",
            "status": "success",
        }
    ).execute()

    return updated


@router.get("/{pdf_id}/download-url")
def get_pdf_download_url(pdf_id: UUID, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    pdf_row = (
        db.table("generated_pdfs")
        .select("*, businesses!inner(user_id)")
        .eq("id", str(pdf_id))
        .eq("businesses.user_id", user_id)
        .single()
        .execute()
    )
    if not pdf_row.data or not pdf_row.data.get("storage_path"):
        raise HTTPException(status_code=404, detail="PDF not found or not ready")

    url = get_signed_url(pdf_row.data["storage_path"])
    return {"url": url}
