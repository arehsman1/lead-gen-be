"""
No login system. This is a single-operator tool, not a multi-tenant
product — every request is treated as the one fixed user configured via
DEFAULT_USER_ID in .env, provisioned once via the one-time SQL at the
bottom of supabase/schema.sql rather than a signup flow.

Every route's `Depends(get_current_user_id)` is unchanged from when this
verified a real Supabase session token — only what this function does
internally changed, so no route file needed to be touched.

Worth being clear-eyed about: this means the API has no access control
of its own. Anyone who can reach it can use it — run searches (spending
your SerpApi/Apify credits), view business data, trigger email sends.
Fine behind 127.0.0.1/your own VPN/a firewall allowlist; add a layer in
front (nginx basic auth, a firewall allowlist, a VPN) before this ever
sits on an open public IP or domain.
"""

from fastapi import Depends, HTTPException, status

from app.core.config import get_settings


class AuthError(HTTPException):
    def __init__(self, detail: str = "Not configured"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )


def get_current_user_id() -> str:
    """
    Returns the fixed operator's user id from settings. Raises if it
    hasn't been configured yet, rather than silently proceeding with an
    empty string that would fail confusingly deeper in a query.
    """
    user_id = get_settings().default_user_id

    if not user_id:
        raise AuthError(
            "DEFAULT_USER_ID is not set in .env — see the README's "
            "'Auth' section and supabase/schema.sql for one-time setup."
        )

    return user_id


CurrentUserId = Depends(get_current_user_id)
