from app.services.evaluators.gbp_evaluator import evaluate_google_business

COMPLETE_SERPAPI_PAYLOAD = {
    "description": "A full-service HVAC company serving Lokoja and the surrounding area for over ten years.",
    "type": ["HVAC contractor", "Air conditioning repair service"],
    "hours": {"monday": "8AM-6PM"},
    "photos": [f"photo{i}.jpg" for i in range(15)],
    "thumbnail": "logo.jpg",
    "website": "https://kogicomforthvac.com",
    "links": {"book": "https://kogicomforthvac.com/book"},
    "questions_and_answers": [{"question": "Do you offer emergency service?", "answer": "Yes, 24/7."}],
    "service_options": {"area": "Lokoja and surrounding LGAs"},
}

EMPTY_PAYLOAD = {}


def test_complete_profile_returns_mostly_strong():
    findings = evaluate_google_business(COMPLETE_SERPAPI_PAYLOAD, None)
    by_key = {f.item_key: f for f in findings}

    assert by_key["business_description"].severity == "strong"
    assert by_key["categories"].severity == "strong"
    assert by_key["opening_hours"].severity == "strong"
    assert by_key["photos"].severity == "strong"
    assert by_key["logo"].severity == "strong"
    assert by_key["website_link"].severity == "strong"
    assert by_key["appointment_link"].severity == "strong"
    assert by_key["qna"].severity == "strong"
    assert by_key["service_areas"].severity == "strong"


def test_empty_profile_flags_critical_gaps():
    findings = evaluate_google_business(EMPTY_PAYLOAD, None)
    by_key = {f.item_key: f for f in findings}

    assert by_key["business_description"].severity == "critical"
    assert by_key["categories"].severity == "critical"
    assert by_key["opening_hours"].severity == "critical"
    assert by_key["photos"].severity == "critical"
    assert by_key["website_link"].severity == "critical"


def test_no_payload_at_all_returns_no_findings():
    # Neither source found this business's GBP data — honest "nothing to
    # evaluate" rather than fabricating critical findings from nothing.
    findings = evaluate_google_business(None, None)
    assert findings == []


def test_serpapi_preferred_over_apify_when_both_present():
    apify_payload = {"categoryName": "HVAC"}
    findings = evaluate_google_business(COMPLETE_SERPAPI_PAYLOAD, apify_payload)
    by_key = {f.item_key: f for f in findings}
    # Description only exists in the SerpApi payload — confirms SerpApi's
    # field map was used, not Apify's.
    assert by_key["business_description"].severity == "strong"


def test_falls_back_to_apify_when_no_serpapi_data():
    apify_payload = {
        "categoryName": "HVAC contractor",
        "description": "Apify-sourced description of sufficient length to pass the threshold check here.",
    }
    findings = evaluate_google_business(None, apify_payload)
    by_key = {f.item_key: f for f in findings}
    assert by_key["categories"].severity == "strong"
    assert by_key["business_description"].severity == "strong"


def test_unanswered_questions_flagged():
    payload = dict(COMPLETE_SERPAPI_PAYLOAD)
    payload["questions_and_answers"] = [
        {"question": "Q1", "answer": "A1"},
        {"question": "Q2", "answer": None},
    ]
    findings = evaluate_google_business(payload, None)
    qna_finding = next(f for f in findings if f.item_key == "qna")
    assert qna_finding.severity == "watch"
    assert "1 of 2" in qna_finding.detail
