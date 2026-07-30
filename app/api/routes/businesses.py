from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import Business
from app.services.email_finder_service import find_public_email

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("", response_model=list[Business])
def list_businesses(user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    result = (
        db.table("businesses")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_deleted", False)
        .order("date_found", desc=True)
        .execute()
    )
    return result.data


@router.get("/{business_id}", response_model=Business)
def get_business(business_id: UUID, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    result = (
        db.table("businesses")
        .select("*")
        .eq("id", str(business_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Business not found")
    return result.data


@router.post("/{business_id}/find-email", response_model=Business)
async def find_email_for_business(business_id: UUID, user_id: str = Depends(get_current_user_id)):
    """
    Checks the business's own website (homepage/contact/about/footer +
    mailto links) for a public email. Never guesses or generates one. If
    nothing is found, falls back to Google Business data already stored on
    the row (Apify/SerpApi may have already captured a listed email there);
    otherwise the business is marked no_email_found and Send Email stays
    disabled on the frontend.
    """
    db = get_supabase()
    biz = (
        db.table("businesses")
        .select("*")
        .eq("id", str(business_id))
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not biz.data:
        raise HTTPException(status_code=404, detail="Business not found")

    website = biz.data.get("website")
    result = await find_public_email(website) if website else None

    email = result.email if result else None
    status = "ready" if email else "no_email_found"

    updated = (
        db.table("businesses")
        .update({"public_email": email, "email_status": status})
        .eq("id", str(business_id))
        .execute()
    )
    return updated.data[0]


@router.delete("/{business_id}", status_code=204)
def delete_business(business_id: UUID, user_id: str = Depends(get_current_user_id)):
    """Soft delete only — per spec, lead history is never removed unless
    the user explicitly chooses to delete it."""
    db = get_supabase()
    db.table("businesses").update({"is_deleted": True}).eq("id", str(business_id)).eq(
        "user_id", user_id
    ).execute()
    return None
