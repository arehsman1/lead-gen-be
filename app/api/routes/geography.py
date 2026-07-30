"""
Countries/states for the Lead Search form's dependent dropdowns. This is
shared reference data (not per-user), seeded once via
`python -m app.scripts.seed_geography` — see supabase/schema.sql. No auth
dependency here on purpose: unlike every other route, this data isn't
scoped to a user at all, so there's nothing for get_current_user_id to
filter by.
"""

from fastapi import APIRouter, Query

from app.core.supabase import get_supabase
from app.models.schemas import Country, State

router = APIRouter(tags=["geography"])


@router.get("/countries", response_model=list[Country])
def list_countries():
    db = get_supabase()
    result = db.table("countries").select("*").order("name").execute()
    return result.data


@router.get("/states", response_model=list[State])
def list_states(country: str = Query(..., description="Country ISO2 code, e.g. 'US'")):
    db = get_supabase()
    country_rows = db.table("countries").select("id").eq("iso2", country.upper()).limit(1).execute().data
    if not country_rows:
        return []
    result = (
        db.table("states")
        .select("*")
        .eq("country_id", country_rows[0]["id"])
        .order("name")
        .execute()
    )
    return result.data
