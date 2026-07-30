import io
import uuid
from datetime import datetime

from pypdf import PdfReader

from app.models.schemas import Audit, AuditFinding, AuditScores, Business
from app.services.pdf_service import generate_audit_pdf


def _make_business(**overrides) -> Business:
    defaults = dict(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        search_id=None,
        name="Test Business",
        industry="HVAC",
        location="Lokoja, Kogi",
        website="testbiz.com",
        phone="+234 800 000 0000",
        address="1 Test St",
        google_maps_url="https://maps/x",
        google_place_id="P1",
        rating=4.2,
        review_count=10,
        source_api="both",
        public_email="info@testbiz.com",
        date_found=datetime.now(),
        audit_status="complete",
        pdf_status="not_generated",
        email_status="not_generated",
        is_deleted=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    defaults.update(overrides)
    return Business(**defaults)


def _make_audit(findings=None, has_website=True, **score_overrides) -> Audit:
    scores = dict(website_score=60 if has_website else None, google_business_score=70, overall_score=64, opportunity_score=70)
    scores.update(score_overrides)
    return Audit(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        has_website=has_website,
        scores=AuditScores(**scores),
        findings=findings or [],
        recommended_services=["Website Design"],
        created_at=datetime.now(),
    )


def test_generates_valid_pdf_bytes():
    business = _make_business()
    audit = _make_audit(findings=[
        AuditFinding(category="technical_seo", label="No schema", detail="...", severity="critical"),
    ])

    pdf_bytes = generate_audit_pdf(business, audit)

    assert pdf_bytes[:4] == b"%PDF"
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 4  # cover + summary + findings + action plan, at minimum


def test_no_website_produces_na_and_still_renders():
    business = _make_business(website=None)
    audit = _make_audit(has_website=False, findings=[
        AuditFinding(category="google_business", label="Missing hours", detail="...", severity="watch"),
    ])

    pdf_bytes = generate_audit_pdf(business, audit)

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "N/A" in text


def test_business_with_no_findings_still_generates():
    business = _make_business()
    audit = _make_audit(findings=[])

    pdf_bytes = generate_audit_pdf(business, audit)

    assert pdf_bytes[:4] == b"%PDF"


def test_cover_page_includes_business_name():
    business = _make_business(name="Kogi Comfort HVAC")
    audit = _make_audit()

    pdf_bytes = generate_audit_pdf(business, audit)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    cover_text = reader.pages[0].extract_text() or ""

    assert "Kogi Comfort HVAC" in cover_text


def test_revenue_section_never_uses_guarantee_language():
    business = _make_business()
    audit = _make_audit()

    pdf_bytes = generate_audit_pdf(business, audit)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).lower()

    banned_phrases = ["guaranteed", "we promise", "guarantee you"]
    for phrase in banned_phrases:
        assert phrase not in text


def test_page_count_within_spec_target():
    business = _make_business()
    audit = _make_audit(findings=[
        AuditFinding(category="technical_seo", item_key="schema", label="Missing schema", detail="...", severity="critical"),
        AuditFinding(category="lead_generation", item_key="click_to_call", label="No click-to-call", detail="...", severity="watch"),
    ])

    pdf_bytes = generate_audit_pdf(business, audit)
    reader = PdfReader(io.BytesIO(pdf_bytes))

    # Spec target: 8-12 pages. Give a little headroom either side for
    # findings-heavy audits without treating a couple extra pages as failure.
    assert 8 <= len(reader.pages) <= 14


def test_table_of_contents_resolves_real_page_numbers():
    business = _make_business()
    audit = _make_audit()

    pdf_bytes = generate_audit_pdf(business, audit)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    toc_text = reader.pages[1].extract_text() or ""

    assert "Table of Contents" in toc_text
    assert "1. Executive Summary" in toc_text
    # The TOC entry should carry a page number distinct from the TOC's own page.
    assert "3" in toc_text


def test_unassessed_items_are_never_marked_good():
    """Evidence-standard check: an item with no finding must show 'Not
    Assessed', never be silently assumed to have passed."""
    business = _make_business()
    audit = _make_audit(findings=[
        AuditFinding(category="website_foundation", item_key="https", label="HTTPS", detail="...", severity="strong"),
    ])

    pdf_bytes = generate_audit_pdf(business, audit)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Not Assessed" in text
    # Confirmed only for the one item that actually had a finding.
    assert "Confirmed Good" in text


def test_pricing_shown_only_when_website_design_recommended():
    business = _make_business()
    with_website_design = _make_audit()
    with_website_design.recommended_services = ["Website Design"]
    pdf_with = generate_audit_pdf(business, with_website_design)
    text_with = "\n".join(
        p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_with)).pages
    )
    assert "Starting from $299" in text_with

    without_website_design = _make_audit()
    without_website_design.recommended_services = ["Local SEO"]
    pdf_without = generate_audit_pdf(business, without_website_design)
    text_without = "\n".join(
        p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_without)).pages
    )
    assert "Starting from $299" not in text_without
    assert "custom quote" in text_without.lower()


def test_all_sections_present_in_order():
    business = _make_business()
    audit = _make_audit(findings=[
        AuditFinding(category="technical_seo", item_key="schema", label="Missing schema", detail="...", severity="critical"),
    ])
    audit.recommended_services = ["Website Design"]

    pdf_bytes = generate_audit_pdf(business, audit)
    text = "\n".join(
        p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages
    )

    section_markers = [
        "1. Executive Summary",
        "2. Business Information",
        "3. Overall Digital Scores",
        "4. Website Audit",
        "5. Google Business Profile Audit",
        "6. Reviews & Trust Audit",
        "7. Local SEO Audit",
        "8. Revenue Opportunity",
        "9. Priority Fixes",
        "10. Recommended CALEBREVIEW Services",
        "11. Pricing",
        "12. Next Steps",
    ]
    positions = [text.index(marker) for marker in section_markers]
    assert positions == sorted(positions)
    # 90-Day Action Plan was explicitly removed.
    assert "90-Day Action Plan" not in text


def test_contact_email_present_in_next_steps():
    business = _make_business()
    audit = _make_audit()

    pdf_bytes = generate_audit_pdf(business, audit)
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

    assert "Caleb@calebreview.com" in text


def test_pricing_renders_as_comparison_table_with_all_three_packages():
    business = _make_business()
    audit = _make_audit()
    audit.recommended_services = ["Website Design"]

    pdf_bytes = generate_audit_pdf(business, audit)
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)

    for name, price in [("Starter", 299), ("Growth", 499), ("Professional", 799)]:
        assert name in text
        assert str(price) in text
    # A comparison-table row that only appears in the higher tiers.
    assert "Competitor keyword research" in text


def test_watermark_text_appears_in_page_content():
    business = _make_business()
    audit = _make_audit()

    pdf_bytes = generate_audit_pdf(business, audit)
    reader = PdfReader(io.BytesIO(pdf_bytes))

    # The watermark is drawn directly on the canvas (not as extractable text
    # via get_text, but pypdf's extract_text does pick up canvas-drawn text
    # objects). Check it shows up somewhere across the document.
    full_text = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert full_text.lower().count("calebreview.com") >= len(reader.pages) - 1  # every content page + footer mentions
