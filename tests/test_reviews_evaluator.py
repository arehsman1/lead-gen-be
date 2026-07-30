from datetime import datetime, timedelta, timezone

from app.services.evaluators.reviews_evaluator import evaluate_reviews


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_strong_rating_and_volume():
    findings = evaluate_reviews(rating=4.6, review_count=50)
    by_key = {f.item_key: f for f in findings}
    assert by_key["average_rating"].severity == "strong"
    assert by_key["total_reviews"].severity == "strong"


def test_low_rating_and_volume_flagged_critical():
    findings = evaluate_reviews(rating=2.8, review_count=2)
    by_key = {f.item_key: f for f in findings}
    assert by_key["average_rating"].severity == "critical"
    assert by_key["total_reviews"].severity == "critical"


def test_no_rating_data_produces_no_rating_findings():
    findings = evaluate_reviews(rating=None, review_count=None)
    by_key = {f.item_key: f for f in findings}
    assert "average_rating" not in by_key
    assert "total_reviews" not in by_key


def test_owner_replies_all_present():
    reviews = [{"date": _iso(10), "owner_response": "Thanks!"}, {"date": _iso(20), "owner_response": "Appreciated!"}]
    findings = evaluate_reviews(rating=4.5, review_count=30, individual_reviews=reviews)
    reply_finding = next(f for f in findings if f.item_key == "owner_replies")
    assert reply_finding.severity == "strong"


def test_owner_replies_none_present_is_critical():
    reviews = [{"date": _iso(10), "owner_response": None}, {"date": _iso(20), "owner_response": None}]
    findings = evaluate_reviews(rating=4.5, review_count=30, individual_reviews=reviews)
    reply_finding = next(f for f in findings if f.item_key == "owner_replies")
    assert reply_finding.severity == "critical"


def test_recent_reviews_detected():
    reviews = [{"date": _iso(5)}]
    findings = evaluate_reviews(rating=4.5, review_count=30, individual_reviews=reviews)
    recent_finding = next(f for f in findings if f.item_key == "recent_reviews")
    assert recent_finding.severity == "strong"


def test_stale_reviews_flagged():
    reviews = [{"date": _iso(400)}]
    findings = evaluate_reviews(rating=4.5, review_count=30, individual_reviews=reviews)
    recent_finding = next(f for f in findings if f.item_key == "recent_reviews")
    assert recent_finding.severity == "watch"


def test_no_individual_reviews_skips_detail_items_honestly():
    # Only rating + count are known — recent_reviews/owner_replies/review_activity
    # should not appear rather than being guessed.
    findings = evaluate_reviews(rating=4.5, review_count=30, individual_reviews=None)
    by_key = {f.item_key: f for f in findings}
    assert "recent_reviews" not in by_key
    assert "owner_replies" not in by_key
    assert "review_activity" not in by_key


def test_website_testimonials_reflects_website_finding():
    with_testimonials = evaluate_reviews(rating=4.5, review_count=30, has_website=True, website_has_testimonials_finding=True)
    without_testimonials = evaluate_reviews(rating=4.5, review_count=30, has_website=True, website_has_testimonials_finding=False)

    assert next(f for f in with_testimonials if f.item_key == "website_testimonials").severity == "strong"
    assert next(f for f in without_testimonials if f.item_key == "website_testimonials").severity == "watch"


def test_trust_opportunity_flagged_for_low_review_count():
    findings = evaluate_reviews(rating=4.5, review_count=8)
    assert any(f.item_key == "trust_opportunities" for f in findings)
