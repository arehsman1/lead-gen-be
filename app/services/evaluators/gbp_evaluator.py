"""
Evaluates Google Business Profile completeness from the raw SerpApi/Apify
payload already stored on the business row (per spec: no live crawling for
this section — it's all API data that was already captured at search time).

IMPORTANT — unverified field names: the key names below (description,
hours, photos, thumbnail, website, etc.) are based on SerpApi's publicly
documented Google Maps response schema, but this hasn't been checked
against a real live response — I don't have network access to SerpApi to
confirm it. Before relying on this in production, run one real search and
diff the actual JSON keys against GBP_FIELD_MAP below; adjust as needed.
Apify's Google Maps actor uses different key names entirely (e.g.
'categoryName' vs SerpApi's 'type') — apify_field_map is a second, equally
unverified guess for when only Apify data is available.
"""

from app.models.schemas import AuditFinding

# SerpApi-shaped keys (unverified against a live response — see docstring)
SERPAPI_FIELD_MAP = {
    "description": "description",
    "categories": "type",
    "hours": "hours",
    "photos": "photos",
    "thumbnail": "thumbnail",
    "website": "website",
    "appointment_link": "links",  # SerpApi nests booking links under 'links'; verify key name live
    "qna": "questions_and_answers",
    "service_areas": "service_options",
}

# Apify Google Maps actor-shaped keys (unverified — see docstring)
APIFY_FIELD_MAP = {
    "description": "description",
    "categories": "categoryName",
    "hours": "openingHours",
    "photos": "imageUrls",
    "thumbnail": "imageUrl",
    "website": "website",
    "appointment_link": "bookingLinks",
    "qna": "questionsAndAnswers",
    "service_areas": "additionalInfo",
}


def _f(item_key, label, detail, severity, recommendation=None) -> AuditFinding:
    return AuditFinding(category="google_business", item_key=item_key, label=label, detail=detail, severity=severity, recommendation=recommendation)


def _get(payload: dict, field_map: dict, key: str):
    return payload.get(field_map.get(key, key))


def evaluate_google_business(raw_serpapi_data: dict | None, raw_apify_data: dict | None) -> list[AuditFinding]:
    """Prefers SerpApi data when both are present, per the same source-of-
    truth priority used everywhere else in the pipeline."""
    payload = raw_serpapi_data if raw_serpapi_data is not None else raw_apify_data
    field_map = SERPAPI_FIELD_MAP if raw_serpapi_data is not None else APIFY_FIELD_MAP

    if payload is None:
        return []

    findings: list[AuditFinding] = []

    description = _get(payload, field_map, "description")
    if description and len(str(description).strip()) >= 30:
        findings.append(_f("business_description", "Business description present", f"{len(description)} characters.", "strong"))
    else:
        findings.append(_f("business_description", "Missing or thin business description", "No substantive description found on the profile.", "critical", "Write a clear 200-750 character description covering services and service area."))

    categories = _get(payload, field_map, "categories")
    if categories:
        cat_display = categories if isinstance(categories, str) else ", ".join(str(c) for c in categories[:3])
        findings.append(_f("categories", "Categories set", f"Categories: {cat_display}.", "strong"))
    else:
        findings.append(_f("categories", "No categories found", "No business categories found on the profile.", "critical", "Set a specific primary category plus relevant secondary categories."))

    hours = _get(payload, field_map, "hours")
    if hours:
        findings.append(_f("opening_hours", "Hours listed", "Opening hours are set on the profile.", "strong"))
    else:
        findings.append(_f("opening_hours", "No hours listed", "No opening hours found on the profile.", "critical", "Add complete opening hours, including holiday hours."))

    photos = _get(payload, field_map, "photos")
    photo_count = len(photos) if isinstance(photos, list) else (1 if photos else 0)
    if photo_count >= 10:
        findings.append(_f("photos", "Strong photo count", f"{photo_count} photos found.", "strong"))
    elif photo_count > 0:
        findings.append(_f("photos", "Low photo count", f"Only {photo_count} photos found.", "watch", "Add more photos \u2014 listings with more photos get meaningfully more clicks."))
    else:
        findings.append(_f("photos", "No photos found", "No photos found on the profile.", "critical", "Upload at least 10 photos covering the storefront, team, and work."))

    thumbnail = _get(payload, field_map, "thumbnail")
    findings.append(
        _f("logo", "Logo/thumbnail set", "A profile thumbnail image is set.", "strong")
        if thumbnail else
        _f("logo", "No logo found", "No profile thumbnail/logo image found.", "watch", "Upload a clear logo as the profile image.")
    )

    website = _get(payload, field_map, "website")
    findings.append(
        _f("website_link", "Website linked", "The profile links to a website.", "strong")
        if website else
        _f("website_link", "No website linked", "The profile doesn't link to a website.", "critical", "Add the website URL to the Google Business Profile.")
    )

    appointment_link = _get(payload, field_map, "appointment_link")
    findings.append(
        _f("appointment_link", "Appointment link present", "A booking/appointment link is set on the profile.", "strong")
        if appointment_link else
        _f("appointment_link", "No appointment link", "No booking/appointment link found on the profile.", "watch", "Add a direct booking link if the business takes appointments.")
    )

    qna = _get(payload, field_map, "qna")
    qna_count = len(qna) if isinstance(qna, list) else 0
    unanswered = sum(1 for q in qna if isinstance(q, dict) and not q.get("answer")) if isinstance(qna, list) else 0
    if qna_count == 0:
        findings.append(_f("qna", "No public Q&A yet", "No questions have been asked on the profile.", "watch"))
    elif unanswered > 0:
        findings.append(_f("qna", "Unanswered questions on profile", f"{unanswered} of {qna_count} questions have no answer.", "watch", "Answer outstanding questions \u2014 they're visible to every future searcher."))
    else:
        findings.append(_f("qna", "All questions answered", f"All {qna_count} questions have answers.", "strong"))

    service_areas = _get(payload, field_map, "service_areas")
    findings.append(
        _f("service_areas", "Service area set", "A service area is defined on the profile.", "strong")
        if service_areas else
        _f("service_areas", "No service area set", "No service area found on the profile.", "watch", "Define the service area so the listing surfaces for nearby searches.")
    )

    return findings
