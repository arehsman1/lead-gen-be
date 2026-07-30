from app.models.schemas import AuditFinding
from app.services.scoring_service import compute_scores


def test_no_findings_gives_perfect_scores():
    scores = compute_scores([], has_website=True)
    assert scores.website_score == 100
    assert scores.google_business_score == 100
    assert scores.overall_score == 100
    # Opportunity is inverse of overall, floored at 15.
    assert scores.opportunity_score == 15


def test_no_website_marks_website_score_na():
    scores = compute_scores([], has_website=False)
    assert scores.website_score is None
    assert scores.google_business_score == 100
    assert scores.overall_score == 100


def test_critical_finding_lowers_relevant_category_only():
    findings = [
        AuditFinding(
            category="technical_seo",
            label="No schema markup",
            detail="...",
            severity="critical",
        )
    ]
    scores = compute_scores(findings, has_website=True)

    assert scores.website_score == 0  # only assessed item in this category is critical -> 0% weighted
    assert scores.google_business_score == 100  # untouched


def test_same_findings_always_produce_same_scores():
    findings = [
        AuditFinding(category="lead_generation", label="No CTA", detail="...", severity="watch"),
        AuditFinding(category="reviews_trust", label="No replies", detail="...", severity="critical"),
    ]

    first = compute_scores(findings, has_website=True)
    second = compute_scores(findings, has_website=True)

    assert first == second


def test_scores_never_go_below_zero():
    findings = [
        AuditFinding(category="technical_seo", label="x", detail="x", severity="critical")
        for _ in range(10)
    ]
    scores = compute_scores(findings, has_website=True)
    assert scores.website_score == 0


def test_opportunity_score_is_never_below_floor():
    findings = []
    scores = compute_scores(findings, has_website=True)
    # Perfect business still gets a non-zero opportunity score — there's
    # always an angle for outreach, per design intent.
    assert scores.opportunity_score >= 15


def test_score_scales_correctly_regardless_of_item_count():
    """Regression test for a real bug: a flat per-finding penalty model
    let watch-level items stack past zero once the real checklist evaluators
    started producing 20+ findings per audit, even for mostly-healthy sites.
    A site where most items are strong should score high regardless of how
    many total items were assessed."""
    mostly_good_small = (
        [AuditFinding(category="technical_seo", label="x", detail="x", severity="strong")] * 3
        + [AuditFinding(category="technical_seo", label="x", detail="x", severity="watch")]
    )
    mostly_good_large = (
        [AuditFinding(category="technical_seo", label="x", detail="x", severity="strong")] * 18
        + [AuditFinding(category="technical_seo", label="x", detail="x", severity="watch")] * 6
    )

    small_scores = compute_scores(mostly_good_small, has_website=True)
    large_scores = compute_scores(mostly_good_large, has_website=True)

    # Both are 75% strong / 25% watch -> same weighted score regardless of
    # raw item count.
    assert small_scores.website_score == large_scores.website_score
    assert large_scores.website_score >= 75  # should NOT be zeroed out by item count


def test_not_assessed_items_are_excluded_from_scoring():
    # An item with no finding at all contributes nothing either way —
    # scoring only reflects what was actually checked.
    all_strong = [AuditFinding(category="technical_seo", label="x", detail="x", severity="strong")] * 5
    scores = compute_scores(all_strong, has_website=True)
    assert scores.website_score == 100
