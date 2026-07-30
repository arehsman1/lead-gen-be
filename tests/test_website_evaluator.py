import pytest

from app.services.evaluators.website_evaluator import (
    UnsafeWebsiteURLError,
    _assert_safe_url,
    _is_blocked_ip,
    evaluate_website_html,
)

GOOD_HTML = """
<html>
<head>
<title>Kogi Comfort HVAC — AC Repair in Lokoja</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Kogi Comfort HVAC provides fast, reliable air conditioning repair and installation across Lokoja, Kogi State. Licensed and insured.">
<script type="application/ld+json">{"@type": "LocalBusiness"}</script>
</head>
<body>
<nav><a href="/">Home</a><a href="/about">About</a><a href="/contact">Contact</a><a href="/privacy">Privacy Policy</a></nav>
<h1>Kogi Comfort HVAC</h1>
<p>We are a certified, licensed, and insured HVAC company serving Lokoja for over 10 years with a satisfaction guarantee on every job we do for local families and businesses.</p>
<img src="hero.jpg" alt="Technician repairing an AC unit">
<img src="team.jpg" alt="Our team">
<p>Read what our customers say:</p>
<blockquote>"Fast and professional!" - a happy customer</blockquote>
<a href="tel:+2348035550142">Call us now</a>
<form action="/contact"><input type="email"><textarea></textarea></form>
<a href="/quote">Get a Free Quote</a>
<a href="https://calendly.com/kogicomfort">Book Now</a>
<a href="/services">Services</a>
<a href="/gallery">Gallery</a>
<a href="/reviews">Reviews</a>
</body>
</html>
"""

BARE_HTML = "<html><head></head><body><p>Coming soon.</p></body></html>"


def test_good_site_scores_mostly_strong():
    findings = evaluate_website_html(GOOD_HTML, "https://kogicomforthvac.com", fetch_ms=800, sitemap_found=True, robots_found=True)
    by_key = {f.item_key: f for f in findings}

    assert by_key["https"].severity == "strong"
    assert by_key["mobile_friendly"].severity == "strong"
    assert by_key["title_tag"].severity == "strong"
    assert by_key["meta_description"].severity == "strong"
    assert by_key["h1"].severity == "strong"
    assert by_key["schema"].severity == "strong"
    assert by_key["click_to_call"].severity == "strong"
    assert by_key["contact_form"].severity == "strong"
    assert by_key["testimonials"].severity == "strong"
    assert by_key["trust_signals"].severity == "strong"
    assert by_key["about_page"].severity == "strong"
    assert by_key["contact_page"].severity == "strong"
    assert by_key["privacy_policy"].severity == "strong"
    assert by_key["sitemap"].severity == "strong"
    assert by_key["robots_txt"].severity == "strong"


def test_bare_site_flags_critical_issues():
    findings = evaluate_website_html(BARE_HTML, "http://barebones.example", fetch_ms=None, sitemap_found=False, robots_found=False)
    by_key = {f.item_key: f for f in findings}

    assert by_key["https"].severity == "critical"
    assert by_key["mobile_friendly"].severity == "critical"
    assert by_key["title_tag"].severity == "critical"
    assert by_key["meta_description"].severity == "critical"
    assert by_key["h1"].severity == "critical"
    assert by_key["schema"].severity == "critical"
    assert by_key["ctas"].severity == "critical"
    # No <img> tags at all — alt_text shouldn't produce a misleading finding.
    assert "alt_text" not in by_key


def test_speed_omitted_when_not_measured():
    findings = evaluate_website_html(GOOD_HTML, "https://kogicomforthvac.com", fetch_ms=None)
    by_key = {f.item_key: f for f in findings}
    assert "speed" not in by_key


def test_speed_bands_are_deterministic():
    fast = evaluate_website_html(GOOD_HTML, "https://x.com", fetch_ms=500)
    slow = evaluate_website_html(GOOD_HTML, "https://x.com", fetch_ms=6000)
    fast_speed = next(f for f in fast if f.item_key == "speed")
    slow_speed = next(f for f in slow if f.item_key == "speed")
    assert fast_speed.severity == "strong"
    assert slow_speed.severity == "critical"


def test_website_found_always_present_when_evaluated():
    findings = evaluate_website_html(BARE_HTML, "https://x.com")
    assert any(f.item_key == "website_found" and f.severity == "strong" for f in findings)


def test_alt_text_ratio_bands():
    html_partial_alt = GOOD_HTML.replace('alt="Our team"', 'alt=""')
    findings = evaluate_website_html(html_partial_alt, "https://x.com")
    alt_finding = next(f for f in findings if f.item_key == "alt_text")
    # 1 of 2 images has alt text -> 50%, lands in the "watch" band.
    assert alt_finding.severity == "watch"


def test_every_finding_belongs_to_a_website_category():
    findings = evaluate_website_html(GOOD_HTML, "https://x.com", fetch_ms=1000, sitemap_found=True, robots_found=True)
    allowed = {"website_foundation", "lead_generation", "business_trust", "technical_seo"}
    assert all(f.category in allowed for f in findings)


# --- SSRF guard (_is_blocked_ip / _assert_safe_url) -------------------------
# Pure logic, no network needed — these back fetch_website's protection
# against a scraped `website` field pointing at internal infrastructure.


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "169.254.169.254",  # link-local / cloud metadata endpoint
        "10.0.0.1",  # private (RFC1918)
        "172.16.0.1",  # private (RFC1918)
        "192.168.1.1",  # private (RFC1918)
        "0.0.0.0",  # unspecified
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 unique local (private)
    ],
)
def test_is_blocked_ip_flags_internal_addresses(ip):
    assert _is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
def test_is_blocked_ip_allows_public_addresses(ip):
    assert _is_blocked_ip(ip) is False


def test_is_blocked_ip_rejects_unparseable_input():
    assert _is_blocked_ip("not-an-ip") is True


def test_assert_safe_url_rejects_non_http_scheme():
    with pytest.raises(UnsafeWebsiteURLError):
        _assert_safe_url("file:///etc/passwd")


def test_assert_safe_url_rejects_url_with_no_hostname():
    with pytest.raises(UnsafeWebsiteURLError):
        _assert_safe_url("https://")


def test_assert_safe_url_rejects_localhost_hostname():
    with pytest.raises(UnsafeWebsiteURLError):
        _assert_safe_url("http://localhost/")


def test_assert_safe_url_allows_public_hostname():
    # example.com is reserved by IANA specifically for documentation/testing
    # and always resolves to a stable public IP — safe for a real DNS lookup.
    _assert_safe_url("https://example.com/")
