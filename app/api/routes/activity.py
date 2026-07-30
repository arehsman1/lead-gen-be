from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.models.schemas import ActivityLogEntry

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=list[ActivityLogEntry])
def get_activity_log(
    limit: int = Query(default=50, le=200),
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    result = (
        db.table("activity_log")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
