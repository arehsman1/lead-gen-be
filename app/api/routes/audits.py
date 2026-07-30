from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import Audit, AuditCreateRequest, AuditFinding
from app.services.evaluators.gbp_evaluator import evaluate_google_business
from app.services.evaluators.local_seo_evaluator import evaluate_local_seo
from app.services.evaluators.reviews_evaluator import evaluate_reviews
from app.services.evaluators.website_evaluator import evaluate_website_html, fetch_website
from app.services.scoring_service import compute_scores

router = APIRouter(prefix="/audits", tags=["audits"])

# Services matched to which findings triggered them. Per spec: never list
# all services, only ones the audit actually surfaced a need for.
SERVICE_TRIGGERS = {
    "website_foundation": "Website Design",
    "lead_generation": "Lead Generation Setup",
    "business_trust": "Website Design",
    "technical_seo": "Local SEO",
    "google_business": "Google Business Optimization",
    "reviews_trust": "Google Business Optimization",
    "local_seo": "Local SEO",
}


def _match_services(findings: list[AuditFinding]) -> list[str]:
    services = set()
    for f in findings:
        if f.severity in ("critical", "watch") and f.category in SERVICE_TRIGGERS:
            services.add(SERVICE_TRIGGERS[f.category])
    return sorted(services)


async def _run_website_evaluation(website: str) -> tuple[list[AuditFinding], str | None]:
    """Returns (findings, title_text). Falls back to a single 'could not
    be checked' finding rather than failing the whole audit if the site is
    unreachable — the rest of the audit (GBP, reviews) should still run."""
    try:
        fetched = await fetch_website(website)
    except Exception as e:
        return (
            [
                AuditFinding(
                    category="website_foundation",
                    item_key="website_found",
                    label="Website could not be checked",
                    detail=f"The website did not respond to a request: {e}",
                    severity="critical",
                    recommendation="Confirm the site is live and not blocking automated requests.",
                )
            ],
            None,
        )

    findings = evaluate_website_html(
        html=fetched["html"],
        final_url=fetched["final_url"],
        fetch_ms=fetched["fetch_ms"],
        sitemap_found=fetched["sitemap_found"],
        robots_found=fetched["robots_found"],
    )
    return findings, fetched["title_text"]


@router.post("", response_model=Audit, status_code=201)
async def run_audit(request: AuditCreateRequest, user_id: str = Depends(get_current_user_id)):
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

    db.table("businesses").update({"audit_status": "running"}).eq("id", str(request.business_id)).execute()

    has_website = bool(biz.data.get("website"))
    findings: list[AuditFinding] = []
    website_title_text = None

    if has_website:
        website_findings, website_title_text = await _run_website_evaluation(biz.data["website"])
        findings += website_findings

    findings += evaluate_google_business(biz.data.get("raw_serpapi_data"), biz.data.get("raw_apify_data"))

    website_findings_for_reviews = [f for f in findings if f.category == "business_trust" and f.item_key == "testimonials"]
    testimonials_present = (
        website_findings_for_reviews[0].severity == "strong" if website_findings_for_reviews else None
    )
    findings += evaluate_reviews(
        rating=biz.data.get("rating"),
        review_count=biz.data.get("review_count"),
        individual_reviews=(biz.data.get("raw_serpapi_data") or {}).get("reviews_results"),
        has_website=has_website,
        website_has_testimonials_finding=testimonials_present,
    )

    findings += evaluate_local_seo(
        business_name=biz.data["name"],
        location=biz.data.get("location"),
        raw_serpapi_data=biz.data.get("raw_serpapi_data"),
        raw_apify_data=biz.data.get("raw_apify_data"),
        website_findings=findings,
        website_title_text=website_title_text,
    )

    scores = compute_scores(findings, has_website=has_website)
    recommended_services = _match_services(findings)

    audit_row = (
        db.table("audits")
        .insert(
            {
                "business_id": str(request.business_id),
                "has_website": has_website,
                "website_score": scores.website_score,
                "google_business_score": scores.google_business_score,
                "overall_score": scores.overall_score,
                "opportunity_score": scores.opportunity_score,
                "recommended_services": recommended_services,
            }
        )
        .execute()
        .data[0]
    )

    if findings:
        db.table("audit_findings").insert(
            [{"audit_id": audit_row["id"], **f.model_dump(exclude={"id"})} for f in findings]
        ).execute()

    db.table("businesses").update({"audit_status": "complete"}).eq("id", str(request.business_id)).execute()
    db.table("activity_log").insert(
        {
            "user_id": user_id,
            "business_id": str(request.business_id),
            "action": "Audit Generated",
            "status": "success",
        }
    ).execute()

    return {
        **audit_row,
        "scores": scores.model_dump(),
        "findings": [f.model_dump() for f in findings],
    }


@router.get("/business/{business_id}", response_model=Audit | None)
def get_latest_audit(business_id: UUID, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()

    audit = (
        db.table("audits")
        .select("*, businesses!inner(user_id)")
        .eq("business_id", str(business_id))
        .eq("businesses.user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not audit.data:
        return None

    row = audit.data[0]
    findings = db.table("audit_findings").select("*").eq("audit_id", row["id"]).execute()

    return {
        **row,
        "scores": {
            "website_score": row["website_score"],
            "google_business_score": row["google_business_score"],
            "overall_score": row["overall_score"],
            "opportunity_score": row["opportunity_score"],
        },
        "findings": findings.data,
    }
