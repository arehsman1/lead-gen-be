from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import SearchHistoryEntry, SearchRequest
from app.services.dedup_service import merge_results
from app.services.scraping_service import search_apify, search_serpapi

router = APIRouter(prefix="/search", tags=["search"])


async def _resolve_api_key(db, user_id: str, key_id, provider: str, fallback: str) -> str:
    """Returns the key value to actually use for `provider`: the saved key
    named by `key_id` if one was picked at search time, otherwise the
    single legacy key from Settings (`fallback`) — unchanged behavior for
    searches that don't pick a saved key at all."""
    if not key_id:
        return fallback
    row = (
        db.table("saved_api_keys")
        .select("key_value")
        .eq("id", str(key_id))
        .eq("user_id", user_id)
        .eq("provider", provider)
        .limit(1)
        .execute()
        .data
    )
    if not row:
        # Picked a key that's since been deleted, or belongs to another
        # user/provider — fail loudly rather than silently falling back
        # to a different key than the one actually selected.
        raise ValueError(f"Saved {provider} key not found — it may have been deleted since this search was started.")
    return row[0]["key_value"]


async def _run_search_job(user_id: str, search_id: str, request: SearchRequest):
    """Background job: scrape, merge, persist. Runs after the response returns.

    Everything from here to the end is wrapped in one broad try/except.
    That's deliberate: this used to only catch ScraperConfigError, so any
    other failure (a bad API response, a rate limit, a malformed payload,
    a Supabase write failing) crashed the background task silently —
    search_history stayed 'running' and the "Search Started" activity log
    entry stayed 'pending' forever, with zero indication anything had gone
    wrong. A background task's exceptions don't propagate anywhere a user
    would see them, so this function must account for its own failures
    completely rather than relying on a caller to notice.
    """
    db = get_supabase()
    started_at = datetime.now(timezone.utc)

    try:
        settings_row = db.table("settings").select("*").eq("user_id", user_id).single().execute().data or {}

        serp_results, apify_results = [], []
        if request.apis in ("serpapi", "both") and settings_row.get("serpapi_enabled"):
            serpapi_key = await _resolve_api_key(
                db, user_id, request.serpapi_key_id, "serpapi", settings_row.get("serpapi_key", "")
            )
            serp_results = await search_serpapi(request.keyword, request.location, serpapi_key)
        if request.apis in ("apify", "both") and settings_row.get("apify_enabled"):
            apify_token = await _resolve_api_key(
                db, user_id, request.apify_key_id, "apify", settings_row.get("apify_token", "")
            )
            apify_results = await search_apify(request.keyword, request.location, apify_token)

        merged = merge_results(serp_results, apify_results)

        rows = [
            {
                "user_id": user_id,
                "search_id": search_id,
                "name": m.name,
                "industry": m.industry,
                "location": request.location,
                "website": m.website,
                "phone": m.phone,
                "address": m.address,
                "google_maps_url": m.google_maps_url,
                "google_place_id": m.google_place_id,
                "rating": m.rating,
                "review_count": m.review_count,
                "source_api": m.source_api,
                "raw_serpapi_data": m.raw_serpapi_data,
                "raw_apify_data": m.raw_apify_data,
                "date_found": datetime.now(timezone.utc).isoformat(),
                "audit_status": "not_started",
                "pdf_status": "not_generated",
                "email_status": "not_generated",
            }
            for m in merged
        ]

        if rows:
            db.table("businesses").insert(rows).execute()

        finished_at = datetime.now(timezone.utc)
        db.table("search_history").update(
            {
                "status": "complete",
                "result_count": len(rows),
                "finished_at": finished_at.isoformat(),
            }
        ).eq("id", search_id).execute()

        db.table("activity_log").insert(
            {
                "user_id": user_id,
                "action": "Search Completed",
                "status": "success",
                "detail": (
                    f"{len(rows)} results for '{request.keyword}' in {request.location} "
                    f"({(finished_at - started_at).total_seconds():.0f}s)"
                ),
            }
        ).execute()

    except Exception as e:
        finished_at = datetime.now(timezone.utc)
        error_detail = str(e) or type(e).__name__

        # Best-effort: if the DB itself is what failed, these will also
        # fail, but there's nothing further to fall back to — logging is
        # the last resort at that point.
        try:
            db.table("search_history").update(
                {
                    "status": "failed",
                    "finished_at": finished_at.isoformat(),
                    "error_detail": error_detail,
                }
            ).eq("id", search_id).execute()
            db.table("activity_log").insert(
                {
                    "user_id": user_id,
                    "action": "Search Completed",
                    "status": "error",
                    "detail": (
                        f"{request.keyword} in {request.location} failed after "
                        f"{(finished_at - started_at).total_seconds():.0f}s: {error_detail}"
                    ),
                }
            ).execute()
        except Exception:
            pass


@router.post("", response_model=SearchHistoryEntry, status_code=202)
async def start_search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()

    inserted = (
        db.table("search_history")
        .insert(
            {
                "user_id": user_id,
                "keyword": request.keyword,
                "location": request.location,
                "apis_used": request.apis,
                "status": "running",
                "result_count": 0,
            }
        )
        .execute()
    )
    if not inserted.data:
        raise HTTPException(status_code=500, detail="Could not create search record")

    search_row = inserted.data[0]

    db.table("activity_log").insert(
        {
            "user_id": user_id,
            "action": "Search Started",
            "status": "pending",
            "detail": f"{request.keyword} in {request.location}",
        }
    ).execute()

    background_tasks.add_task(_run_search_job, user_id, search_row["id"], request)

    return search_row


@router.get("/history", response_model=list[SearchHistoryEntry])
def get_search_history(user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    result = (
        db.table("search_history")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/{search_id}", response_model=SearchHistoryEntry)
def get_search_status(search_id: str, user_id: str = Depends(get_current_user_id)):
    """Single-search status/duration lookup — the frontend polls this while
    a search is 'running' to show live progress instead of a static
    "search started, check back later" message."""
    db = get_supabase()
    result = (
        db.table("search_history")
        .select("*")
        .eq("id", search_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Search not found")
    return result.data
