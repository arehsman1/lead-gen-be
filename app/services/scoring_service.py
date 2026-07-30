"""
Turns a set of findings into the four audit scores. Deterministic: the same
findings always produce the same scores, per spec ("must be calculated
consistently, not randomly assigned").

Model: each assessed item contributes a weight (strong=1.0, watch=0.5,
critical=0.0) and the category score is the average weight across assessed
items, scaled to 100. This is a per-item weighted PASS RATE, not a flat
point-subtraction — it's what makes the score scale correctly whether an
audit produced 2 findings (the old placeholder logic) or 30 (the real
checklist evaluators). A flat "-10 per watch, -22 per critical" model
breaks down once there are enough items: a genuinely solid site with a
handful of watch-level items across ~24 checklist entries could subtract
past zero even though most of its items are fine. The weighted-average
model keeps the score bounded and proportionate to what was actually
found, no matter the item count.

Items with no finding at all ("Not Assessed") are excluded entirely —
they neither help nor hurt the score, since nothing was actually verified.
"""

from app.models.schemas import AuditFinding, AuditScores, FindingCategory, FindingSeverity

SEVERITY_WEIGHT = {
    FindingSeverity.strong: 1.0,
    FindingSeverity.watch: 0.5,
    FindingSeverity.critical: 0.0,
}

# Categories that roll up into the Website Score (only meaningful if the
# business has a website).
WEBSITE_CATEGORIES = {
    FindingCategory.website_foundation,
    FindingCategory.lead_generation,
    FindingCategory.business_trust,
    FindingCategory.technical_seo,
}

# Categories that roll up into the Google Business Score.
GOOGLE_BUSINESS_CATEGORIES = {
    FindingCategory.google_business,
    FindingCategory.reviews_trust,
    FindingCategory.local_seo,
}


def _category_score(findings: list[AuditFinding], categories: set[FindingCategory]) -> int:
    relevant = [f for f in findings if f.category in categories]
    if not relevant:
        return 100
    total_weight = sum(SEVERITY_WEIGHT[f.severity] for f in relevant)
    return round(100 * total_weight / len(relevant))


def compute_scores(findings: list[AuditFinding], has_website: bool) -> AuditScores:
    google_business_score = _category_score(findings, GOOGLE_BUSINESS_CATEGORIES)

    if has_website:
        website_score = _category_score(findings, WEBSITE_CATEGORIES)
        # Overall weights website presence higher, since it's the primary
        # conversion asset; Google Business still counts meaningfully.
        overall_score = round(website_score * 0.6 + google_business_score * 0.4)
    else:
        website_score = None
        # No website: overall is driven entirely by Google Business + trust
        # signals, since that's the business's only public-facing footprint.
        overall_score = google_business_score

    # Opportunity score is inverse of overall: more room to improve = more
    # opportunity for an agency pitch. Floored so it's never read as "zero
    # opportunity" even for a strong business — there's always an angle.
    opportunity_score = max(15, 100 - overall_score)

    return AuditScores(
        website_score=website_score,
        google_business_score=google_business_score,
        overall_score=overall_score,
        opportunity_score=opportunity_score,
    )
