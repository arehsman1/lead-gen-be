from app.models.schemas import AuditFinding
from app.services.evaluators.local_seo_evaluator import evaluate_local_seo


def test_nap_consistency_matched():
    serp = {"phone": "+234 803 555 0142", "address": "14 Ganaja Rd, Lokoja"}
    apify = {"phone": "+234 803 555 0142", "address": "14 Ganaja Rd, Lokoja"}
    findings = evaluate_local_seo("Kogi Comfort HVAC", "Lokoja, Kogi", serp, apify, [])
    consistency = next(f for f in findings if f.item_key == "business_info_consistency")
    assert consistency.severity == "strong"


def test_nap_consistency_mismatch_flagged():
    serp = {"phone": "+234 803 555 0142", "address": "14 Ganaja Rd, Lokoja"}
    apify = {"phone": "+234 809 111 2222", "address": "14 Ganaja Rd, Lokoja"}
    findings = evaluate_local_seo("Kogi Comfort HVAC", "Lokoja, Kogi", serp, apify, [])
    consistency = next(f for f in findings if f.item_key == "business_info_consistency")
    assert consistency.severity == "watch"
    assert "phone" in consistency.detail.lower()


def test_nap_check_skipped_when_only_one_source():
    findings = evaluate_local_seo("Biz", "Lokoja, Kogi", {"phone": "123"}, None, [])
    assert not any(f.item_key == "business_info_consistency" for f in findings)


def test_local_keyword_found_in_title():
    findings = evaluate_local_seo("Biz", "Lokoja, Kogi", None, None, [], website_title_text="Biz | HVAC Repair in Lokoja")
    keyword_finding = next(f for f in findings if f.item_key == "local_keywords")
    assert keyword_finding.severity == "strong"


def test_local_keyword_missing_from_title():
    findings = evaluate_local_seo("Biz", "Lokoja, Kogi", None, None, [], website_title_text="Biz | HVAC Repair")
    keyword_finding = next(f for f in findings if f.item_key == "local_keywords")
    assert keyword_finding.severity == "watch"


def test_schema_reuses_website_finding():
    website_findings = [
        AuditFinding(category="technical_seo", item_key="schema", label="Schema found", detail="...", severity="strong"),
    ]
    findings = evaluate_local_seo("Biz", "Lokoja, Kogi", None, None, website_findings)
    schema_finding = next(f for f in findings if f.item_key == "schema")
    assert schema_finding.severity == "strong"


def test_no_website_findings_means_no_schema_entry():
    findings = evaluate_local_seo("Biz", "Lokoja, Kogi", None, None, [])
    assert not any(f.item_key == "schema" for f in findings)
