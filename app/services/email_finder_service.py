"""
Finds a public email address on a business's own website. Per spec, this
NEVER guesses or generates an address (e.g. info@domain.com patterns) — it
only returns an address it actually found in page content or a mailto:
link. If nothing is found, the caller should fall back to Google Business
data, and if that's also empty, the business is marked "no public email
found" and the Send Email button stays disabled.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Patterns that indicate an address is a placeholder/asset artifact, not a
# real contact email (e.g. image filenames, tracking pixels, obfuscation
# libraries that leave literal "@example.com" in their source).
JUNK_DOMAINS = {"example.com", "sentry.io", "wixpress.com", "godaddy.com"}

CANDIDATE_PATHS = ["", "/contact", "/contact-us", "/about", "/about-us"]


@dataclass
class EmailFindResult:
    email: str | None
    found_on: str | None  # which page it was found on, for audit-trail purposes


def _is_plausible(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    if domain in JUNK_DOMAINS:
        return False
    if len(email) > 254:
        return False
    return True


def extract_emails_from_html(html: str, base_url: str) -> list[str]:
    """Pulls emails from visible text and mailto: links in a single page."""
    soup = BeautifulSoup(html, "html.parser")

    found: set[str] = set()

    # mailto: links are the highest-confidence signal.
    for a in soup.select("a[href^='mailto:']"):
        href = a.get("href", "")
        addr = href.replace("mailto:", "").split("?")[0].strip()
        if addr and EMAIL_RE.fullmatch(addr) and _is_plausible(addr):
            found.add(addr)

    # Footer / body text as a fallback signal.
    text = soup.get_text(" ")
    for match in EMAIL_RE.findall(text):
        if _is_plausible(match):
            found.add(match)

    return sorted(found)


async def find_public_email(website_url: str, timeout: float = 8.0) -> EmailFindResult:
    """
    Checks homepage, /contact, /contact-us, /about, /about-us in that order
    and returns the first plausible email found. Stops as soon as one is
    found — this is a "does a public email exist", not an exhaustive crawl.
    """
    if not website_url:
        return EmailFindResult(email=None, found_on=None)

    base = website_url if website_url.startswith("http") else f"https://{website_url}"

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for path in CANDIDATE_PATHS:
            url = urljoin(base, path)
            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            emails = extract_emails_from_html(resp.text, url)
            if emails:
                return EmailFindResult(email=emails[0], found_on=url)

    return EmailFindResult(email=None, found_on=None)
