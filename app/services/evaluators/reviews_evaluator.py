"""
Evaluates review health from data already on the business row (rating,
review_count) plus, when available, an individual-reviews array from the
raw SerpApi/Apify payload. The reviews array's exact shape is another
unverified assumption (see gbp_evaluator.py's docstring for the same
caveat) — this expects a list of dicts with roughly {date, rating,
owner_response}. If that array isn't present, this still evaluates
average_rating and total_reviews from the fields we're confident about,
and marks the review-detail items (recent_reviews, owner_replies,
review_activity) as not assessed rather than guessing.
"""

from datetime import datetime, timedelta, timezone

from app.models.schemas import AuditFinding


def _f(item_key, label, detail, severity, recommendation=None) -> AuditFinding:
    return AuditFinding(category="reviews_trust", item_key=item_key, label=label, detail=detail, severity=severity, recommendation=recommendation)


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate_reviews(
    rating: float | None,
    review_count: int | None,
    individual_reviews: list[dict] | None = None,
    has_website: bool = False,
    website_has_testimonials_finding: bool | None = None,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    if rating is not None:
        if rating >= 4.3:
            findings.append(_f("average_rating", "Strong average rating", f"{rating} average rating.", "strong"))
        elif rating >= 3.5:
            findings.append(_f("average_rating", "Middling average rating", f"{rating} average rating.", "watch", "Focus on service recovery for recent negative reviews and actively request new ones."))
        else:
            findings.append(_f("average_rating", "Low average rating", f"{rating} average rating.", "critical", "Address the root causes behind recent negative reviews before investing in more visibility."))

    if review_count is not None:
        if review_count >= 25:
            findings.append(_f("total_reviews", "Healthy review volume", f"{review_count} total reviews.", "strong"))
        elif review_count >= 5:
            findings.append(_f("total_reviews", "Moderate review volume", f"{review_count} total reviews.", "watch", "Keep asking every satisfied customer for a review \u2014 more volume builds trust faster."))
        else:
            findings.append(_f("total_reviews", "Low review volume", f"Only {review_count} reviews found.", "critical", "Ask the last 5-10 satisfied customers directly for a review."))

    if individual_reviews:
        now = datetime.now(timezone.utc)
        dated = [(_parse_date(r.get("date"))) for r in individual_reviews]
        dated = [d for d in dated if d is not None]
        recent = [d for d in dated if (now - d) <= timedelta(days=90)]
        if dated:
            if recent:
                findings.append(_f("recent_reviews", "Recent review activity", f"{len(recent)} review(s) in the last 90 days.", "strong"))
            else:
                findings.append(_f("recent_reviews", "No recent reviews", "No reviews found in the last 90 days.", "watch", "Prompt recent customers for reviews to keep activity visibly current."))

            gap_days = (now - max(dated)).days
            if gap_days <= 30:
                findings.append(_f("review_activity", "Steady review activity", f"Most recent review is {gap_days} day(s) old.", "strong"))
            else:
                findings.append(_f("review_activity", "Review activity has slowed", f"Most recent review is {gap_days} days old.", "watch", "Build a habit of asking for a review after every job."))

        with_response = sum(1 for r in individual_reviews if r.get("owner_response"))
        if with_response == len(individual_reviews):
            findings.append(_f("owner_replies", "All reviews have owner replies", f"{with_response}/{len(individual_reviews)} reviews have a response.", "strong"))
        elif with_response > 0:
            findings.append(_f("owner_replies", "Some reviews missing owner replies", f"{with_response}/{len(individual_reviews)} reviews have a response.", "watch", "Reply to the remaining reviews, prioritizing any critical ones."))
        else:
            findings.append(_f("owner_replies", "No owner replies found", f"0 of {len(individual_reviews)} reviews have an owner response.", "critical", "Reply to at least the most recent 10 reviews this week."))

    if has_website:
        if website_has_testimonials_finding is True:
            findings.append(_f("website_testimonials", "Reviews reflected on website", "Testimonial content was found on the website.", "strong"))
        elif website_has_testimonials_finding is False:
            findings.append(_f("website_testimonials", "Reviews not reflected on website", "No testimonial content found on the website.", "watch", "Pull 2-3 of the best Google reviews onto the homepage."))

    if review_count is not None and review_count < 15:
        findings.append(_f(
            "trust_opportunities", "Low-cost trust opportunity available",
            "Review volume is low enough that a simple ask-for-a-review habit would move the needle quickly.",
            "watch", "Add a review-request step to the standard job-completion process.",
        ))

    return findings
