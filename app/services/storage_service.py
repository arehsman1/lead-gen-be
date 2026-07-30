"""
Uploads generated PDF bytes to the Supabase Storage bucket and returns the
storage path to persist on the generated_pdfs row. Requires the 'audit-pdfs'
bucket to exist (create it once in the Supabase dashboard, private by
default — serve via signed URLs, not public access, since these reports
contain a business's contact info and audit findings).
"""

from app.core.supabase import get_supabase

BUCKET = "audit-pdfs"


def upload_pdf(business_id: str, audit_id: str, pdf_bytes: bytes) -> str:
    db = get_supabase()
    path = f"{business_id}/{audit_id}.pdf"

    db.storage.from_(BUCKET).upload(
        path,
        pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return path


def get_signed_url(storage_path: str, expires_in_seconds: int = 3600) -> str:
    db = get_supabase()
    result = db.storage.from_(BUCKET).create_signed_url(storage_path, expires_in_seconds)
    return result["signedURL"]
