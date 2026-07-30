from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache
def get_supabase() -> Client:
    """
    Server-side Supabase client using the service role key. This bypasses
    Row Level Security, so every query built on top of this client MUST
    manually filter by the operator's user_id (see app.core.auth). Never
    expose this key to the frontend. There's no login system, so the
    frontend doesn't talk to Supabase at all — everything goes through
    this API.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the "
            "environment before the app can talk to the database."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
