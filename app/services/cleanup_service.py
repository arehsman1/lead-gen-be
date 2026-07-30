"""
Deletes generated PDFs older than PDF_RETENTION_DAYS from both Supabase
Storage and the generated_pdfs table. Meant to run on a schedule (cron on
the VPS — see deploy/DEPLOYMENT.md) rather than inside a web request,
since deleting many files can take a while and has nothing to do with
serving traffic.

find_expired_pdfs is pure (list in, list out) so it's fully testable
without a database. delete_expired_pdfs does the actual I/O and is
exercised by the cleanup script, not by tests.
"""

from datetime import datetime, timedelta, timezone


def find_expired_pdfs(pdfs: list[dict], retention_days: int, now: datetime | None = None) -> list[dict]:
    """
    pdfs: rows shaped like generated_pdfs (must have 'created_at' as an
    ISO string and 'storage_path'). Only 'ready' PDFs with a storage_path
    are eligible — anything still generating or already failed has
    nothing in Storage to clean up.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    expired = []
    for pdf in pdfs:
        if pdf.get("status") != "ready" or not pdf.get("storage_path"):
            continue
        created_at = pdf.get("created_at")
        if not created_at:
            continue
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created < cutoff:
            expired.append(pdf)
    return expired


def delete_expired_pdfs(db, retention_days: int) -> dict:
    """Fetches all ready PDFs, deletes the expired ones from Storage and
    the DB, resets the owning business's pdf_status. Returns a summary
    dict for logging."""
    from app.services.storage_service import BUCKET

    all_pdfs = db.table("generated_pdfs").select("*").eq("status", "ready").execute().data or []
    expired = find_expired_pdfs(all_pdfs, retention_days)

    deleted, failed = [], []
    for pdf in expired:
        try:
            db.storage.from_(BUCKET).remove([pdf["storage_path"]])
            db.table("generated_pdfs").update({"status": "not_generated", "storage_path": None}).eq(
                "id", pdf["id"]
            ).execute()
            db.table("businesses").update({"pdf_status": "not_generated"}).eq(
                "id", pdf["business_id"]
            ).execute()
            deleted.append(pdf["id"])
        except Exception as e:  # noqa: BLE001 — log and keep going, one bad row shouldn't stop the batch
            failed.append({"id": pdf["id"], "error": str(e)})

    return {"checked": len(all_pdfs), "expired": len(expired), "deleted": deleted, "failed": failed}
