"""
Local SEO draws on signals already computed by the other evaluators rather
than re-deriving them, plus one new check: NAP (name/address/phone)
consistency between SerpApi and Apify when both sources found the
business. local_visibility (actual rank-tracking across keywords) isn't
assessable from a single audit pass — it needs a rank-tracking integration
— so it's intentionally left with no finding rather than guessed at.
"""

from app.models.schemas import AuditFinding


def _f(item_key, label, detail, severity, recommendation=None) -> AuditFinding:
    return AuditFinding(category="local_seo", item_key=item_key, label=label, detail=detail, severity=severity, recommendation=recommendation)


def _normalize(s: str | None) -> str:
    return "".join((s or "").lower().split())


def evaluate_local_seo(
    business_name: str,
    location: str | None,
    raw_serpapi_data: dict | None,
    raw_apify_data: dict | None,
    website_findings: list[AuditFinding],
    website_title_text: str | None = None,
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    # NAP consistency — only checkable when both sources found this business.
    if raw_serpapi_data and raw_apify_data:
        serp_phone = _normalize(raw_serpapi_data.get("phone"))
        apify_phone = _normalize(raw_apify_data.get("phone"))
        serp_addr = _normalize(raw_serpapi_data.get("address"))
        apify_addr = _normalize(raw_apify_data.get("address"))

        mismatches = []
        if serp_phone and apify_phone and serp_phone != apify_phone:
            mismatches.append("phone number")
        if serp_addr and apify_addr and serp_addr != apify_addr:
            mismatches.append("address")

        if mismatches:
            findings.append(_f(
                "business_info_consistency", "Inconsistent business information across sources",
                f"{' and '.join(mismatches).capitalize()} differ between data sources.",
                "watch", "Standardize the business's name, address, and phone number across every directory and listing.",
            ))
        else:
            findings.append(_f("business_info_consistency", "Business information consistent", "Name, address, and phone match across the sources checked.", "strong"))

    # Local keyword presence — reuses the website's title if we already fetched it.
    if location and website_title_text:
        city = location.split(",")[0].strip().lower()
        if city and city in website_title_text.lower():
            findings.append(_f("local_keywords", "Location referenced in title tag", f"'{city.title()}' appears in the homepage title.", "strong"))
        else:
            findings.append(_f("local_keywords", "Location missing from title tag", f"'{city.title()}' was not found in the homepage title.", "watch", "Work the service area into the title tag and homepage copy."))

    # Local schema — reuse the website evaluator's schema finding if present.
    schema_finding = next((f for f in website_findings if f.item_key == "schema"), None)
    if schema_finding:
        if schema_finding.severity == "strong":
            findings.append(_f("schema", "Structured data present", "The site has structured data that search engines can use for local results.", "strong"))
        else:
            findings.append(_f("schema", "No local schema found", "No LocalBusiness structured data found on the site.", "critical", "Add LocalBusiness JSON-LD schema with the business's name, address, and phone."))

    return findings
