from datetime import datetime, timedelta, timezone

from app.services.cleanup_service import find_expired_pdfs

NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def _pdf(days_old: int, status: str = "ready", storage_path: str | None = "biz/audit.pdf") -> dict:
    created = NOW - timedelta(days=days_old)
    return {
        "id": f"pdf-{days_old}",
        "status": status,
        "storage_path": storage_path,
        "created_at": created.isoformat(),
        "business_id": "biz-1",
    }


def test_pdf_older_than_retention_is_expired():
    pdfs = [_pdf(days_old=20)]
    expired = find_expired_pdfs(pdfs, retention_days=14, now=NOW)
    assert len(expired) == 1


def test_pdf_within_retention_is_not_expired():
    pdfs = [_pdf(days_old=5)]
    expired = find_expired_pdfs(pdfs, retention_days=14, now=NOW)
    assert expired == []


def test_pdf_exactly_at_boundary_is_not_yet_expired():
    # Exactly `retention_days` old — cutoff is now - retention_days, and
    # created == cutoff should not be strictly less than cutoff.
    pdfs = [_pdf(days_old=14)]
    expired = find_expired_pdfs(pdfs, retention_days=14, now=NOW)
    assert expired == []


def test_non_ready_pdfs_are_never_expired_regardless_of_age():
    pdfs = [_pdf(days_old=100, status="generating"), _pdf(days_old=100, status="failed")]
    expired = find_expired_pdfs(pdfs, retention_days=14, now=NOW)
    assert expired == []


def test_pdf_without_storage_path_is_skipped():
    pdfs = [_pdf(days_old=100, storage_path=None)]
    expired = find_expired_pdfs(pdfs, retention_days=14, now=NOW)
    assert expired == []


def test_mixed_batch_only_returns_the_expired_ones():
    pdfs = [_pdf(days_old=30), _pdf(days_old=3), _pdf(days_old=15), _pdf(days_old=1)]
    expired = find_expired_pdfs(pdfs, retention_days=14, now=NOW)
    expired_ids = {p["id"] for p in expired}
    assert expired_ids == {"pdf-30", "pdf-15"}


def test_retention_days_is_configurable():
    pdfs = [_pdf(days_old=10)]
    assert find_expired_pdfs(pdfs, retention_days=14, now=NOW) == []
    assert len(find_expired_pdfs(pdfs, retention_days=8, now=NOW)) == 1
