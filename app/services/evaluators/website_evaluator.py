"""
Turns a fetched homepage into AuditFinding rows for the four website
categories (Foundation, Lead Generation, Trust, Technical SEO).

Deliberately NOT implemented, rather than faked:
- broken_links: checking every link's HTTP status is a multi-request job
  suited to a background worker, not a single-page audit pass. Returns no
  finding (renders "Not Assessed" in the PDF) until that job exists.
- speed is a rough proxy (homepage fetch time), not a real Core Web Vitals
  / Lighthouse score. Labeled as such in the finding detail so it's never
  mistaken for one.

Every check here is a heuristic against static HTML — sites that render
their contact form, nav, or CTAs via client-side JavaScript will under-
report on those items. This is disclosed in the module docstring rather
than silently presented as a definitive crawl.
"""

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.schemas import AuditFinding

BOOKING_KEYWORDS = ["calendly", "book now", "book an appointment", "schedule an appointment", "acuityscheduling", "squarespacescheduling"]
QUOTE_KEYWORDS = ["get a quote", "request a quote", "free quote", "get an estimate"]
CTA_KEYWORDS = ["call now", "book now", "contact us", "get started", "request a quote", "buy now", "shop now", "schedule now", "get a free quote"]
TRUST_KEYWORDS = ["certified", "licensed", "insured", "guarantee", "accredited", "bbb", "trusted by", "award-winning"]
NAV_KEYWORDS = {"about": "about_page", "contact": "contact_page", "privacy": "privacy_policy"}


def _f(category, item_key, label, detail, severity, recommendation=None) -> AuditFinding:
    return AuditFinding(
        category=category, item_key=item_key, label=label, detail=detail,
        severity=severity, recommendation=recommendation,
    )


def _contains_any(haystack: str, needles: list[str]) -> bool:
    return any(n in haystack for n in needles)


def evaluate_website_html(
    html: str,
    final_url: str,
    fetch_ms: float | None = None,
    sitemap_found: bool | None = None,
    robots_found: bool | None = None,
) -> list[AuditFinding]:
    soup = BeautifulSoup(html, "html.parser")
    lower_html = html.lower()
    findings: list[AuditFinding] = []

    # ---- Website Foundation ----------------------------------------------
    findings.append(_f(
        "website_foundation", "website_found", "Website found",
        "A website was located and successfully fetched for this business.", "strong",
    ))

    if final_url.startswith("https://"):
        findings.append(_f("website_foundation", "https", "HTTPS enabled", "Site loads over HTTPS.", "strong"))
    else:
        findings.append(_f(
            "website_foundation", "https", "Not using HTTPS",
            "Site loads over plain HTTP.", "critical",
            "Move to HTTPS with a free certificate (e.g. Let's Encrypt) — most hosts enable this in one click.",
        ))

    if soup.find("meta", attrs={"name": "viewport"}):
        findings.append(_f("website_foundation", "mobile_friendly", "Mobile viewport configured", "A responsive viewport meta tag is present.", "strong"))
    else:
        findings.append(_f(
            "website_foundation", "mobile_friendly", "No mobile viewport tag",
            "No viewport meta tag found — the site likely doesn't adapt to phone screens.", "critical",
            "Add a responsive viewport meta tag and confirm the layout adapts on a real phone.",
        ))

    if fetch_ms is not None:
        if fetch_ms < 1500:
            findings.append(_f("website_foundation", "speed", "Fast homepage load", f"Homepage responded in {fetch_ms:.0f}ms (rough proxy, not a full Lighthouse score).", "strong"))
        elif fetch_ms < 3500:
            findings.append(_f("website_foundation", "speed", "Moderate homepage load time", f"Homepage responded in {fetch_ms:.0f}ms.", "watch", "Compress images and enable caching to bring this down."))
        else:
            findings.append(_f("website_foundation", "speed", "Slow homepage load", f"Homepage took {fetch_ms:.0f}ms to respond.", "critical", "Investigate hosting, image sizes, and unused scripts — this is costing visitors."))

    nav = soup.find("nav")
    if nav and len(nav.find_all("a")) >= 3:
        findings.append(_f("website_foundation", "navigation", "Clear navigation menu", f"Nav menu found with {len(nav.find_all('a'))} links.", "strong"))
    else:
        findings.append(_f("website_foundation", "navigation", "No clear navigation menu detected", "No <nav> element with multiple links was found.", "watch", "Add a consistent navigation menu so visitors can find key pages."))

    word_count = len(soup.get_text(" ").split())
    has_image = bool(soup.find("img"))
    has_h1 = bool(soup.find("h1"))
    if word_count >= 150 and has_image and has_h1:
        findings.append(_f("website_foundation", "homepage_quality", "Homepage has substantive content", f"~{word_count} words, at least one image, and a clear heading.", "strong"))
    else:
        findings.append(_f("website_foundation", "homepage_quality", "Thin homepage content", f"~{word_count} words detected; missing image or heading.", "watch", "Flesh out the homepage with a clear headline, supporting copy, and imagery."))

    internal_links = {a["href"] for a in soup.find_all("a", href=True) if a["href"].startswith("/") or final_url in a["href"]}
    if len(internal_links) >= 5:
        findings.append(_f("website_foundation", "website_structure", "Multiple internal pages linked", f"{len(internal_links)} distinct internal links found from the homepage.", "strong"))
    else:
        findings.append(_f("website_foundation", "website_structure", "Limited site structure", f"Only {len(internal_links)} distinct internal links found.", "watch", "Build out dedicated pages (services, about, contact) and link to them from the homepage."))

    # ---- Lead Generation ---------------------------------------------------
    has_form = bool(soup.find("form"))
    if has_form:
        findings.append(_f("lead_generation", "contact_form", "Contact form found", "A <form> element was found on the homepage.", "strong"))
    else:
        findings.append(_f("lead_generation", "contact_form", "No contact form on homepage", "No <form> element was found (may exist on a subpage not checked here).", "watch", "Add a contact form so visitors who aren't ready to call can still reach out."))

    if "tel:" in lower_html:
        findings.append(_f("lead_generation", "click_to_call", "Click-to-call link present", "A tel: link was found.", "strong"))
    else:
        findings.append(_f("lead_generation", "click_to_call", "No click-to-call link", "No tel: link found — the phone number likely isn't tappable on mobile.", "watch", "Make the phone number a tel: link so mobile visitors can call with one tap."))

    if _contains_any(lower_html, BOOKING_KEYWORDS):
        findings.append(_f("lead_generation", "booking_system", "Online booking detected", "A booking/scheduling tool reference was found.", "strong"))
    else:
        findings.append(_f("lead_generation", "booking_system", "No online booking detected", "No booking/scheduling tool reference found.", "watch", "Consider adding online booking to capture leads outside business hours."))

    if _contains_any(lower_html, QUOTE_KEYWORDS):
        findings.append(_f("lead_generation", "quote_request_form", "Quote request option found", "Quote/estimate request language was found on the page.", "strong"))
    else:
        findings.append(_f("lead_generation", "quote_request_form", "No quote request option found", "No quote/estimate request language found.", "watch", "Add a low-friction 'Get a Quote' form for price-sensitive visitors."))

    if _contains_any(lower_html, CTA_KEYWORDS):
        findings.append(_f("lead_generation", "ctas", "Clear calls-to-action found", "Common CTA language was found on the homepage.", "strong"))
    else:
        findings.append(_f("lead_generation", "ctas", "No clear call-to-action found", "No common CTA language (e.g. 'Contact Us', 'Book Now') was found.", "critical", "Add a clear, specific call-to-action above the fold."))

    # ---- Trust ---------------------------------------------------------
    nav_text_and_hrefs = " ".join(
        f"{a.get_text(' ').lower()} {a.get('href', '').lower()}" for a in soup.find_all("a")
    )
    for keyword, item_key in NAV_KEYWORDS.items():
        label = item_key.replace("_", " ").title()
        if keyword in nav_text_and_hrefs:
            findings.append(_f("business_trust", item_key, f"{label} found", f"A link referencing '{keyword}' was found.", "strong"))
        else:
            findings.append(_f("business_trust", item_key, f"No {label.lower()} found", f"No link referencing '{keyword}' was found in the page's links.", "watch", f"Add a dedicated {label.lower()}, linked from the main navigation or footer."))

    if "testimonial" in lower_html or len(soup.find_all("blockquote")) >= 1:
        findings.append(_f("business_trust", "testimonials", "Testimonials present", "Testimonial content or blockquotes were found.", "strong"))
    else:
        findings.append(_f("business_trust", "testimonials", "No testimonials found", "No testimonial content was found on the homepage.", "watch", "Add 2-3 real customer testimonials near the top of the homepage."))

    if _contains_any(lower_html, TRUST_KEYWORDS):
        findings.append(_f("business_trust", "trust_signals", "Trust signals present", "Trust-related language (certified/licensed/guarantee, etc.) was found.", "strong"))
    else:
        findings.append(_f("business_trust", "trust_signals", "No trust signals found", "No certifications, guarantees, or similar trust language found.", "watch", "Highlight any licenses, certifications, or guarantees the business has."))

    # ---- Technical SEO ---------------------------------------------------
    title_tag = soup.find("title")
    title_text = title_tag.get_text().strip() if title_tag else ""
    if 10 <= len(title_text) <= 70:
        findings.append(_f("technical_seo", "title_tag", "Title tag looks good", f"Title tag: \u201c{title_text}\u201d ({len(title_text)} chars).", "strong"))
    elif title_text:
        findings.append(_f("technical_seo", "title_tag", "Title tag needs adjustment", f"Title tag is {len(title_text)} characters \u2014 outside the ideal 10-70 range.", "watch", "Rewrite the title tag to clearly state the business, service, and city in 10-70 characters."))
    else:
        findings.append(_f("technical_seo", "title_tag", "Missing title tag", "No <title> tag found.", "critical", "Add a descriptive title tag naming the business, service, and city."))

    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc_content = meta_desc.get("content", "").strip() if meta_desc else ""
    if len(desc_content) >= 50:
        findings.append(_f("technical_seo", "meta_description", "Meta description present", f"{len(desc_content)} characters.", "strong"))
    elif desc_content:
        findings.append(_f("technical_seo", "meta_description", "Meta description too short", f"Only {len(desc_content)} characters.", "watch", "Expand the meta description to 50-160 characters describing the offer."))
    else:
        findings.append(_f("technical_seo", "meta_description", "Missing meta description", "No meta description found.", "critical", "Add a meta description \u2014 it's effectively free ad copy in search results."))

    h1s = soup.find_all("h1")
    if len(h1s) == 1:
        findings.append(_f("technical_seo", "h1", "Single H1 heading", f"One H1 found: \u201c{h1s[0].get_text().strip()[:60]}\u201d.", "strong"))
    elif len(h1s) == 0:
        findings.append(_f("technical_seo", "h1", "Missing H1 heading", "No H1 tag found on the homepage.", "critical", "Add one clear H1 stating what the business does."))
    else:
        findings.append(_f("technical_seo", "h1", "Multiple H1 headings", f"{len(h1s)} H1 tags found \u2014 should typically be one.", "watch", "Reduce to a single H1 per page."))

    images = soup.find_all("img")
    if images:
        with_alt = sum(1 for img in images if img.get("alt", "").strip())
        ratio = with_alt / len(images)
        if ratio >= 0.8:
            findings.append(_f("technical_seo", "alt_text", "Most images have alt text", f"{with_alt}/{len(images)} images have alt text.", "strong"))
        elif ratio >= 0.4:
            findings.append(_f("technical_seo", "alt_text", "Some images missing alt text", f"{with_alt}/{len(images)} images have alt text.", "watch", "Add descriptive alt text to the remaining images."))
        else:
            findings.append(_f("technical_seo", "alt_text", "Most images missing alt text", f"Only {with_alt}/{len(images)} images have alt text.", "critical", "Add alt text to images \u2014 it affects both accessibility and image search."))

    if sitemap_found is True:
        findings.append(_f("technical_seo", "sitemap", "Sitemap found", "sitemap.xml responded successfully.", "strong"))
    elif sitemap_found is False:
        findings.append(_f("technical_seo", "sitemap", "No sitemap found", "sitemap.xml was not found at the expected location.", "watch", "Generate and submit an XML sitemap to Google Search Console."))

    if robots_found is True:
        findings.append(_f("technical_seo", "robots_txt", "robots.txt found", "robots.txt responded successfully.", "strong"))
    elif robots_found is False:
        findings.append(_f("technical_seo", "robots_txt", "No robots.txt found", "robots.txt was not found at the expected location.", "watch", "Add a robots.txt file \u2014 even a permissive default is better than none."))

    if soup.find("script", attrs={"type": "application/ld+json"}) or soup.find(attrs={"itemtype": True}):
        findings.append(_f("technical_seo", "schema", "Schema markup found", "Structured data (JSON-LD or microdata) was found.", "strong"))
    else:
        findings.append(_f(
            "technical_seo", "schema", "Missing schema markup",
            "No LocalBusiness schema (JSON-LD or microdata) detected; local pack visibility likely reduced.",
            "critical", "Add LocalBusiness JSON-LD schema to the homepage.",
        ))

    # broken_links intentionally omitted — see module docstring.

    return findings


MAX_REDIRECTS = 5


class UnsafeWebsiteURLError(ValueError):
    """Raised when a `website` value points somewhere this server shouldn't
    fetch: a non-http(s) scheme, or a hostname that resolves to a private/
    loopback/link-local/reserved address (e.g. cloud metadata endpoints,
    localhost services, internal-network hosts). `website` values here
    come from scraped third-party listing data (SerpApi/Apify), not direct
    user input, but should still never be trusted as a fetch target."""


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable — don't trust it
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _assert_safe_url(url: str) -> None:
    """Scheme + DNS-resolution check. Note: this doesn't fully close DNS
    rebinding (the resolved-safe host could theoretically re-resolve to a
    private IP by the time the socket actually connects) — closing that
    completely needs pinning the resolved IP into the actual connection via
    a custom transport, not just a pre-check. Given `website` comes from
    scraped listing data rather than attacker-supplied input, this level of
    guard is a reasonable tradeoff against that added complexity."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeWebsiteURLError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeWebsiteURLError("URL has no hostname")

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise UnsafeWebsiteURLError(f"Could not resolve host: {parsed.hostname}") from e

    resolved_ips = {info[4][0] for info in addrinfo}
    if not resolved_ips or any(_is_blocked_ip(ip) for ip in resolved_ips):
        raise UnsafeWebsiteURLError(f"Host resolves to a disallowed address: {parsed.hostname}")


async def _get_safe(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GETs `url`, validating scheme + resolved host before every request —
    including every redirect hop. httpx's built-in follow_redirects=True
    only validates (via a URL you supply) the *first* URL; a validated host
    could otherwise redirect to an internal address and httpx would follow
    it without another check. Manually walking redirects here closes that
    gap."""
    for _ in range(MAX_REDIRECTS + 1):
        _assert_safe_url(url)
        resp = await client.get(url, follow_redirects=False)
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return resp
            url = urljoin(str(resp.url), location)
            continue
        return resp
    raise UnsafeWebsiteURLError("Too many redirects")


async def fetch_website(website: str, timeout: float = 10.0) -> dict:
    """Fetches homepage + sitemap.xml + robots.txt. Returns raw ingredients
    for evaluate_website_html, plus the parsed title text for callers (like
    the local SEO evaluator) that need it without a second fetch."""
    base = website if website.startswith("http") else f"https://{website}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        start = time.perf_counter()
        resp = await _get_safe(client, base)
        fetch_ms = (time.perf_counter() - start) * 1000
        resp.raise_for_status()

        try:
            sitemap_resp = await _get_safe(client, f"{str(resp.url).rstrip('/')}/sitemap.xml")
            sitemap_found = sitemap_resp.status_code == 200
        except (httpx.HTTPError, UnsafeWebsiteURLError):
            sitemap_found = False
        try:
            robots_resp = await _get_safe(client, f"{str(resp.url).rstrip('/')}/robots.txt")
            robots_found = robots_resp.status_code == 200
        except (httpx.HTTPError, UnsafeWebsiteURLError):
            robots_found = False

    title_tag = BeautifulSoup(resp.text, "html.parser").find("title")
    return {
        "html": resp.text,
        "final_url": str(resp.url),
        "fetch_ms": fetch_ms,
        "sitemap_found": sitemap_found,
        "robots_found": robots_found,
        "title_text": title_tag.get_text().strip() if title_tag else "",
    }


async def fetch_and_evaluate_website(website: str, timeout: float = 10.0) -> list[AuditFinding]:
    """Convenience wrapper for callers that just want findings."""
    fetched = await fetch_website(website, timeout=timeout)
    return evaluate_website_html(
        html=fetched["html"],
        final_url=fetched["final_url"],
        fetch_ms=fetched["fetch_ms"],
        sitemap_found=fetched["sitemap_found"],
        robots_found=fetched["robots_found"],
    )
