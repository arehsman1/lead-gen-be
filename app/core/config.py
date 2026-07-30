from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Loaded from environment variables / .env. Nothing here is a secret
    default — every credential must be supplied by the deployer.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase — server-side client used as the database (bypasses RLS,
    # so every route manually filters by user_id — see app.core.auth).
    # There's no login system, so this is not used to validate sessions.
    #
    # SUPABASE_SERVICE_ROLE_KEY accepts either key type Supabase issues:
    # the legacy "service_role" key, or the newer "secret" key
    # (sb_secret_...). They're interchangeable — paste whichever one your
    # project has into this same variable.
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # No login system — see app/core/auth.py. Every request acts as this
    # one fixed user, provisioned once via the one-time SQL at the bottom
    # of supabase/schema.sql.
    default_user_id: str = ""

    # App
    environment: str = "development"
    cors_origins: str = "http://localhost:3000"
    api_prefix: str = "/api"

    # Rate limiting
    rate_limit_per_minute: int = 60

    # How long a generated PDF stays in Storage before the cleanup script
    # deletes it (see app/scripts/cleanup_expired_pdfs.py). Editable from
    # Settings in the dashboard; this is just the fallback default.
    pdf_retention_days: int = 14

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
