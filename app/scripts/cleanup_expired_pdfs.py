"""
Deletes PDFs older than PDF_RETENTION_DAYS (from Storage + the DB row).
Run manually or on a schedule:

    python -m app.scripts.cleanup_expired_pdfs

Add to crontab for daily automatic cleanup — see deploy/DEPLOYMENT.md for
the exact line. Logs a one-line summary to stdout either way, so cron's
output (redirected to a log file) gives you a running history.
"""

import sys
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.supabase import get_supabase
from app.services.cleanup_service import delete_expired_pdfs


def main():
    settings = get_settings()
    db = get_supabase()

    result = delete_expired_pdfs(db, settings.pdf_retention_days)

    timestamp = datetime.now(timezone.utc).isoformat()
    print(
        f"[{timestamp}] PDF cleanup (retention={settings.pdf_retention_days}d): "
        f"checked={result['checked']} expired={result['expired']} "
        f"deleted={len(result['deleted'])} failed={len(result['failed'])}"
    )
    for f in result["failed"]:
        print(f"  FAILED pdf_id={f['id']}: {f['error']}")

    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
