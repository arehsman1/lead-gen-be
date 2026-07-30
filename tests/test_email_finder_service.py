from app.services.email_finder_service import extract_emails_from_html


def test_extracts_mailto_link():
    html = '<a href="mailto:info@example-biz.com">Email us</a>'
    emails = extract_emails_from_html(html, "https://example-biz.com")
    assert "info@example-biz.com" in emails


def test_extracts_from_footer_text():
    html = "<footer>Reach us at contact@shopname.ng for orders</footer>"
    emails = extract_emails_from_html(html, "https://shopname.ng")
    assert "contact@shopname.ng" in emails


def test_ignores_junk_domains():
    html = '<a href="mailto:test@example.com">placeholder</a>'
    emails = extract_emails_from_html(html, "https://site.com")
    assert emails == []


def test_returns_empty_list_when_nothing_found():
    html = "<p>No contact info on this page.</p>"
    emails = extract_emails_from_html(html, "https://site.com")
    assert emails == []


def test_deduplicates_repeated_email():
    html = """
    <a href="mailto:hello@biz.com">Email</a>
    <footer>hello@biz.com</footer>
    """
    emails = extract_emails_from_html(html, "https://biz.com")
    assert emails.count("hello@biz.com") == 1
