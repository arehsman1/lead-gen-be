"""
Multiple named SerpApi/Apify keys per user, picked from at search time
instead of the single serpapi_key/apify_token on Settings. Lets someone
juggling several client accounts (or working around per-key rate limits)
save each key under a name and choose which one to use per search.

Key values are write-only, same masking convention as Settings — once
saved, GET /api-keys never returns key_value, only id/provider/name/
created_at. There's nothing to "test connection" against here directly;
that still happens through the existing /settings/test-connection flow
using whichever key search.py actually picks for a given search.
"""

from postgrest.exceptions import APIError

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import ApiKeyProvider, SavedApiKeyIn, SavedApiKeyOut

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[SavedApiKeyOut])
def list_saved_api_keys(
    provider: ApiKeyProvider | None = None,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    query = db.table("saved_api_keys").select("id, provider, name, created_at").eq("user_id", user_id)
    if provider:
        query = query.eq("provider", provider.value)
    result = query.order("name").execute()
    return result.data


@router.post("", response_model=SavedApiKeyOut, status_code=201)
def create_saved_api_key(body: SavedApiKeyIn, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    try:
        result = (
            db.table("saved_api_keys")
            .insert(
                {
                    "user_id": user_id,
                    "provider": body.provider.value,
                    "name": body.name,
                    "key_value": body.key_value,
                }
            )
            .execute()
        )
    except APIError as e:
        # Postgres unique_violation — this user already has a key with
        # this name for this provider (schema.sql's unique constraint).
        if e.code == "23505":
            raise HTTPException(
                status_code=409,
                detail=f"You already have a {body.provider.value} key named '{body.name}'.",
            ) from e
        raise
    row = result.data[0]
    return SavedApiKeyOut(id=row["id"], provider=row["provider"], name=row["name"], created_at=row["created_at"])


@router.delete("/{key_id}", status_code=204)
def delete_saved_api_key(key_id: str, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    existing = (
        db.table("saved_api_keys").select("id").eq("id", key_id).eq("user_id", user_id).limit(1).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Saved API key not found")
    db.table("saved_api_keys").delete().eq("id", key_id).eq("user_id", user_id).execute()
