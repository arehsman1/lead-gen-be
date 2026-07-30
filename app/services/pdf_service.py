"""
Generates the branded audit PDF report. Structure follows the 13-section
spec: cover -> table of contents -> executive summary -> business info ->
overall scores -> website audit -> Google Business Profile audit ->
reviews & trust -> local SEO -> revenue opportunity -> priority fixes ->
90-day action plan -> recommended services -> pricing -> next steps.

Dynamic per spec: no website skips the website audit checklist (shows a
short N/A note instead); pricing only shows if Website Design was actually
recommended; every checklist item's status is either backed by a specific
finding or explicitly marked "Not Assessed" — never assumed good, per
Caleb's evidence standard of not presenting unverified claims as fact.

Output is raw PDF bytes — the caller uploads to Supabase Storage (see
app/api/routes/pdfs.py), so this module has zero I/O dependencies and is
fully unit-testable.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.models.schemas import Audit, AuditFinding, Business, FindingCategory, FindingSeverity
from app.services.checklist_catalog import CATEGORY_SECTION_TITLES, CHECKLIST_CATALOG
from app.services.pricing_catalog import PACKAGE_NAMES, PACKAGE_STARTING_PRICES, PRICING_NOTE, PRICING_ROWS

# ---------------------------------------------------------------------------
# Brand tokens — must match calebreview-brand-colors / frontend globals.css
# ---------------------------------------------------------------------------

NAVY = colors.HexColor("#0B1F3A")
ACTION = colors.HexColor("#2563EB")
SKY = colors.HexColor("#38BDF8")
INK = colors.HexColor("#111827")
INK_SOFT = colors.HexColor("#475569")
LINE = colors.HexColor("#E2E8F0")
WHITE = colors.white

STRONG = colors.HexColor("#059669")
STRONG_BG = colors.HexColor("#ECFDF5")
WATCH = colors.HexColor("#D97706")
WATCH_BG = colors.HexColor("#FFFBEB")
CRITICAL = colors.HexColor("#DC2626")
CRITICAL_BG = colors.HexColor("#FEF2F2")
NA_GREY = colors.HexColor("#94A3B8")
NA_BG = colors.HexColor("#F1F5F9")

PAGE_W, PAGE_H = letter
MARGIN = 0.75 * inch
CONTENT_WIDTH = PAGE_W - 2 * MARGIN

SEVERITY_STATUS = {
    FindingSeverity.strong: ("Confirmed Good", STRONG, STRONG_BG),
    FindingSeverity.watch: ("Needs Improvement", WATCH, WATCH_BG),
    FindingSeverity.critical: ("Missing / Critical", CRITICAL, CRITICAL_BG),
}
NOT_ASSESSED_STATUS = ("Not Assessed", NA_GREY, NA_BG)

SERVICE_DESCRIPTIONS = {
    "Website Design": "A new or rebuilt website addressing the foundation, trust, and technical issues found in this audit.",
    "Google Business Optimization": "Filling in the profile gaps and review-response habits that most directly affect local visibility.",
    "Local SEO": "On-page and structured-data work so the business shows up for the searches it's currently missing.",
    "Lead Generation Setup": "Contact forms, click-to-call, and booking flows that turn visits into inquiries.",
}


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker", parent=base["Normal"], textColor=SKY, fontSize=10.5,
            leading=14, alignment=TA_CENTER, spaceAfter=10, fontName="Helvetica-Bold",
        ),
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"], textColor=WHITE, fontSize=26,
            leading=32, alignment=TA_CENTER, fontName="Helvetica-Bold",
        ),
        "cover_business": ParagraphStyle(
            "cover_business", parent=base["Normal"], textColor=WHITE, fontSize=16,
            leading=22, alignment=TA_CENTER, spaceBefore=16, fontName="Helvetica",
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", parent=base["Normal"], textColor=colors.HexColor("#CBD5E1"),
            fontSize=9.5, alignment=TA_CENTER, spaceBefore=4,
        ),
        "toc_title": ParagraphStyle(
            "toc_title", parent=base["Heading1"], textColor=NAVY, fontSize=18,
            spaceAfter=16, fontName="Helvetica-Bold",
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], textColor=NAVY, fontSize=17,
            spaceBefore=4, spaceAfter=11, fontName="Helvetica-Bold", keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], textColor=NAVY, fontSize=13,
            spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold", keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], textColor=ACTION, fontSize=11,
            spaceBefore=11, spaceAfter=5, fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], textColor=INK, fontSize=10.5,
            leading=16, spaceAfter=7,
        ),
        "body_soft": ParagraphStyle(
            "body_soft", parent=base["Normal"], textColor=INK_SOFT, fontSize=10,
            leading=15,
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"], textColor=INK_SOFT, fontSize=8.5,
            leading=12, fontName="Helvetica-Bold",
        ),
        "item_label": ParagraphStyle(
            "item_label", parent=base["Normal"], textColor=INK, fontSize=10.5,
            leading=14, fontName="Helvetica-Bold",
        ),
        "finding_detail": ParagraphStyle(
            "finding_detail", parent=base["Normal"], textColor=INK_SOFT, fontSize=9.5,
            leading=14,
        ),
        "recommendation": ParagraphStyle(
            "recommendation", parent=base["Normal"], textColor=ACTION, fontSize=9.5,
            leading=14, fontName="Helvetica-Oblique",
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", parent=base["Normal"], textColor=INK_SOFT, fontSize=9,
            leading=13, fontName="Helvetica-Oblique",
        ),
        "closing": ParagraphStyle(
            "closing", parent=base["Normal"], textColor=INK, fontSize=11,
            leading=18, spaceAfter=11,
        ),
        "signature": ParagraphStyle(
            "signature", parent=base["Normal"], textColor=NAVY, fontSize=12,
            leading=16, fontName="Helvetica-Bold", spaceBefore=16,
        ),
    }


# ---------------------------------------------------------------------------
# Small drawn flowables
# ---------------------------------------------------------------------------

class ScoreBadge(Flowable):
    def __init__(self, label: str, score: int | None, width: float = 1.55 * inch, height: float = 0.85 * inch):
        super().__init__()
        self.label = label
        self.score = score
        self.width = width
        self.height = height

    def _band(self):
        if self.score is None:
            return NA_GREY, NA_BG
        if self.score >= 75:
            return STRONG, STRONG_BG
        if self.score >= 50:
            return WATCH, WATCH_BG
        return CRITICAL, CRITICAL_BG

    def draw(self):
        fg, bg = self._band()
        c = self.canv
        c.setFillColor(bg)
        c.roundRect(0, 0, self.width, self.height, 6, fill=1, stroke=0)
        c.setFillColor(INK_SOFT)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(10, self.height - 17, self.label.upper())
        c.setFillColor(fg)
        c.setFont("Helvetica-Bold", 22)
        score_text = "N/A" if self.score is None else str(self.score)
        c.drawString(10, 12, score_text)
        if self.score is not None:
            c.setFont("Helvetica", 8.5)
            offset = c.stringWidth(score_text, "Helvetica-Bold", 22)
            c.drawString(10 + offset + 3, 14, "/100")


def _status_chip(label: str, fg, bg, width: float = 1.3 * inch) -> Table:
    t = Table([[label]], colWidths=[width], rowHeights=[0.27 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TEXTCOLOR", (0, 0), (-1, -1), fg),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

def _draw_watermark(canvas, alpha: float, text_color):
    """Diagonal, low-opacity 'calebreview.com' watermark, centered on the page."""
    canvas.saveState()
    canvas.translate(PAGE_W / 2, PAGE_H / 2)
    canvas.rotate(38)
    canvas.setFillColor(text_color)
    try:
        canvas.setFillAlpha(alpha)
    except AttributeError:
        pass  # older reportlab without alpha support — falls back to a very light color instead
    canvas.setFont("Helvetica-Bold", 34)
    canvas.drawCentredString(0, 0, "calebreview.com")
    canvas.restoreState()


def _cover_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(SKY)
    canvas.rect(0, PAGE_H - 0.12 * inch, PAGE_W, 0.12 * inch, fill=1, stroke=0)
    canvas.restoreState()
    _draw_watermark(canvas, alpha=0.05, text_color=WHITE)


def _content_frame_decorations(canvas, doc):
    _draw_watermark(canvas, alpha=0.06, text_color=NAVY)
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN, PAGE_H - 0.55 * inch, "CALEBREVIEW Lead Gen")
    canvas.setFillColor(INK_SOFT)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.55 * inch, "Digital Presence Audit Report")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.75)
    canvas.line(MARGIN, PAGE_H - 0.62 * inch, PAGE_W - MARGIN, PAGE_H - 0.62 * inch)

    canvas.setFillColor(INK_SOFT)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(MARGIN, 0.5 * inch, "CALEBREVIEW Lead Gen \u00b7 calebreview.com")
    canvas.drawRightString(PAGE_W - MARGIN, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


class _CalebDocTemplate(BaseDocTemplate):
    """Registers each numbered section heading as a TOC entry with its real
    page number, resolved via reportlab's standard multiBuild pass."""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "h1" and getattr(flowable, "_toc_entry", False):
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))


def _build_doc(buffer: io.BytesIO) -> _CalebDocTemplate:
    doc = _CalebDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="CALEBREVIEW Lead Gen \u2014 Digital Presence Audit Report",
    )
    cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    content_frame = Frame(MARGIN, MARGIN, CONTENT_WIDTH, PAGE_H - 1.4 * inch, id="content")
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=_cover_background),
        PageTemplate(id="Content", frames=[content_frame], onPage=_content_frame_decorations),
    ])
    return doc


def _toc_heading(text: str, styles: dict) -> Paragraph:
    """An h1 heading flagged for TOC capture."""
    p = Paragraph(text, styles["h1"])
    p._toc_entry = True
    return p


# ---------------------------------------------------------------------------
# Checklist rendering — shared by Website / GBP / Reviews & Trust / Local SEO
# ---------------------------------------------------------------------------

def _findings_by_item_key(findings: list[AuditFinding], category: FindingCategory) -> dict[str, AuditFinding]:
    return {f.item_key: f for f in findings if f.category == category and f.item_key}


def _checklist_table(category: FindingCategory, findings: list[AuditFinding], styles: dict) -> list:
    """Compact scan table: every catalog item for this category with its status."""
    by_key = _findings_by_item_key(findings, category)
    rows = []
    for item_key, label, _why in CHECKLIST_CATALOG[category]:
        finding = by_key.get(item_key)
        if finding:
            status_label, fg, bg = SEVERITY_STATUS[finding.severity]
        else:
            status_label, fg, bg = NOT_ASSESSED_STATUS
        rows.append([Paragraph(label, styles["item_label"]), _status_chip(status_label, fg, bg)])

    table = Table(rows, colWidths=[CONTENT_WIDTH - 1.3 * inch, 1.3 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    return [table]


def _issues_callouts(category: FindingCategory, findings: list[AuditFinding], catalog_labels: dict, styles: dict) -> list:
    """Detail blocks (why it matters + recommendation) for anything not
    'Confirmed Good' in this category — the flagged issues worth a business
    owner's attention, rather than repeating the full checklist twice."""
    catalog_by_key = {key: (label, why) for key, label, why in CHECKLIST_CATALOG[category]}
    issues = [
        f for f in findings
        if f.category == category and f.item_key in catalog_by_key and f.severity != FindingSeverity.strong
    ]
    if not issues:
        return []

    story = [Paragraph("What needs attention", styles["h3"])]
    for f in issues:
        _label, why = catalog_by_key[f.item_key]
        status_label, fg, bg = SEVERITY_STATUS[f.severity]
        header = Table(
            [[Paragraph(f.label, styles["item_label"]), _status_chip(status_label, fg, bg)]],
            colWidths=[CONTENT_WIDTH - 1.3 * inch, 1.3 * inch],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(header)
        story.append(Paragraph(f.detail, styles["finding_detail"]))
        story.append(Paragraph(f"Why it matters: {why}", styles["finding_detail"]))
        if f.recommendation:
            story.append(Paragraph(f"Recommendation: {f.recommendation}", styles["recommendation"]))
        story.append(Spacer(1, 8))
    return story


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _cover_story(business: Business, audit: Audit, styles: dict) -> list:
    opp = audit.scores.opportunity_score
    return [
        Spacer(1, 2.2 * inch),
        Paragraph("PREPARED BY CALEBREVIEW", styles["cover_kicker"]),
        Paragraph("Digital Presence Audit Report", styles["cover_title"]),
        Paragraph(business.name, styles["cover_business"]),
        Paragraph(
            f"{business.industry or ''}{' · ' if business.industry and business.location else ''}{business.location or ''}",
            styles["cover_meta"],
        ),
        Paragraph(datetime.now().strftime("Audit Date: %B %d, %Y"), styles["cover_meta"]),
        Spacer(1, 0.35 * inch),
        Paragraph(f"Opportunity Score: {opp}/100", styles["cover_kicker"]),
    ]


def _toc_story(styles: dict) -> list:
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOCLevel0", fontSize=10.5, leading=20, textColor=INK, fontName="Helvetica"),
    ]
    toc.dotsMinLevel = 0
    return [Paragraph("Table of Contents", styles["toc_title"]), toc]


def _executive_summary(audit: Audit, styles: dict) -> list:
    critical_count = sum(1 for f in audit.findings if f.severity == FindingSeverity.critical)
    watch_count = sum(1 for f in audit.findings if f.severity == FindingSeverity.watch)
    strong_count = sum(1 for f in audit.findings if f.severity == FindingSeverity.strong)

    summary = (
        f"This audit reviewed the business's online presence across "
        f"{'its website, ' if audit.has_website else ''}Google Business Profile, and customer reviews. "
        f"It confirmed {strong_count} area{'s' if strong_count != 1 else ''} already working well, found "
        f"{watch_count} worth addressing soon, and {critical_count} that need attention first. Everything "
        f"else in the checklist sections below is marked 'Not Assessed' rather than assumed fine — this "
        f"report only claims what it actually checked."
    )
    return [_toc_heading("1. Executive Summary", styles), Paragraph(summary, styles["body"]), Spacer(1, 6)]


def _business_information(business: Business, styles: dict) -> list:
    rows = [
        ["Business Name", business.name],
        ["Industry", business.industry or "—"],
        ["Location", business.location or "—"],
        ["Website", business.website or "No website on file"],
        ["Phone", business.phone or "—"],
        ["Public Email", business.public_email or "No public email found"],
        ["Google Maps URL", business.google_maps_url or "—"],
        ["Rating", f"{business.rating} \u2605" if business.rating else "—"],
        ["Review Count", str(business.review_count) if business.review_count is not None else "—"],
    ]
    table = Table(rows, colWidths=[1.7 * inch, CONTENT_WIDTH - 1.7 * inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), INK_SOFT),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]))
    return [_toc_heading("2. Business Information", styles), table, Spacer(1, 12)]


def _overall_scores(audit: Audit, styles: dict) -> list:
    row = Table(
        [[
            ScoreBadge("Website", audit.scores.website_score),
            ScoreBadge("Google Business", audit.scores.google_business_score),
            ScoreBadge("Overall", audit.scores.overall_score),
            ScoreBadge("Opportunity", audit.scores.opportunity_score),
        ]],
        colWidths=[1.6 * inch] * 4,
    )
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [_toc_heading("3. Overall Digital Scores", styles), row, Spacer(1, 14)]


def _website_audit(audit: Audit, styles: dict) -> list:
    story = [_toc_heading("4. Website Audit", styles)]
    if not audit.has_website:
        story.append(Paragraph(
            "N/A — this business does not have a website on file. The sections below cover Google Business "
            "Profile, Reviews &amp; Trust, and Local SEO instead, which apply regardless of website status.",
            styles["disclaimer"],
        ))
        story.append(Spacer(1, 10))
        return story

    for category in (
        FindingCategory.website_foundation,
        FindingCategory.lead_generation,
        FindingCategory.business_trust,
        FindingCategory.technical_seo,
    ):
        story.append(Paragraph(CATEGORY_SECTION_TITLES[category], styles["h2"]))
        story += _checklist_table(category, audit.findings, styles)
        story += _issues_callouts(category, audit.findings, CATEGORY_SECTION_TITLES, styles)
        story.append(Spacer(1, 8))
    return story


def _single_category_audit(toc_title: str, category: FindingCategory, audit: Audit, styles: dict) -> list:
    story = [_toc_heading(toc_title, styles)]
    story += _checklist_table(category, audit.findings, styles)
    story += _issues_callouts(category, audit.findings, {}, styles)
    story.append(Spacer(1, 10))
    return story


def _revenue_opportunity(audit: Audit, styles: dict) -> list:
    # Deterministic, transparent placeholder model — NOT real keyword or
    # market data. In production, "Estimated Monthly Searches" should come
    # from a real keyword-volume source (e.g. an Ahrefs/Ubersuggest-style
    # API) keyed to the business's industry + location; everything below it
    # is derived with generic, disclosed conversion-rate assumptions.
    opp = audit.scores.opportunity_score
    monthly_searches = max(50, opp * 8)
    potential_visitors = round(monthly_searches * 0.18)   # ~18% assumed local-pack CTR
    estimated_leads = max(1, round(potential_visitors * 0.08))  # ~8% assumed visitor-to-lead rate
    avg_deal_value = 150  # generic placeholder — swap for an industry-specific figure when available
    monthly_opportunity = estimated_leads * avg_deal_value
    annual_opportunity = monthly_opportunity * 12

    rows = [
        ["Estimated Monthly Searches", f"{monthly_searches:,}"],
        ["Estimated Potential Visitors", f"{potential_visitors:,}"],
        ["Estimated Leads", f"{estimated_leads:,}"],
        ["Estimated Monthly Opportunity", f"${monthly_opportunity:,}"],
        ["Estimated Annual Opportunity", f"${annual_opportunity:,}"],
    ]
    table = Table(rows, colWidths=[2.6 * inch, CONTENT_WIDTH - 2.6 * inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), INK_SOFT),
        ("TEXTCOLOR", (1, 0), (1, -1), NAVY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]))

    return [
        _toc_heading("8. Revenue Opportunity", styles),
        table,
        Spacer(1, 8),
        Paragraph(
            "These figures are estimates for planning purposes only, based on generic industry conversion "
            "assumptions applied to this audit's Opportunity Score \u2014 not a guarantee of revenue, traffic, "
            "leads, or search rankings. Actual results depend on execution, market conditions, and factors "
            "outside any single audit.",
            styles["disclaimer"],
        ),
        Spacer(1, 12),
    ]


def _priority_fixes(audit: Audit, styles: dict) -> list:
    story = [_toc_heading("9. Priority Fixes", styles)]
    tiers = [
        ("High Priority", "Critical improvements.", FindingSeverity.critical, CRITICAL, CRITICAL_BG),
        ("Medium Priority", "Important improvements.", FindingSeverity.watch, WATCH, WATCH_BG),
    ]
    catalog_lookup = {
        (cat, key): (label, why)
        for cat, items in CHECKLIST_CATALOG.items()
        for key, label, why in items
    }

    for tier_title, tier_desc, severity, fg, bg in tiers:
        items = [f for f in audit.findings if f.severity == severity]
        story.append(Paragraph(tier_title, styles["h2"]))
        story.append(Paragraph(tier_desc, styles["body_soft"]))
        if not items:
            story.append(Paragraph("No items flagged at this priority.", styles["body_soft"]))
            story.append(Spacer(1, 8))
            continue
        for f in items:
            _label, why = catalog_lookup.get((f.category, f.item_key), (f.label, ""))
            chip = _status_chip(tier_title.split()[0], fg, bg, width=1.0 * inch)
            header = Table(
                [[Paragraph(f.label, styles["item_label"]), chip]],
                colWidths=[CONTENT_WIDTH - 1.1 * inch, 1.1 * inch],
            )
            header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story.append(header)
            story.append(Paragraph(f"Problem: {f.detail}", styles["finding_detail"]))
            if why:
                story.append(Paragraph(f"Business impact: {why}", styles["finding_detail"]))
            if f.recommendation:
                story.append(Paragraph(f"Recommendation: {f.recommendation}", styles["recommendation"]))
            story.append(Spacer(1, 8))

    story.append(Paragraph("Low Priority", styles["h2"]))
    story.append(Paragraph("Nice-to-have improvements.", styles["body_soft"]))
    story.append(Paragraph("No low-priority items were surfaced by this audit.", styles["body_soft"]))
    story.append(Spacer(1, 10))
    return story


def _recommended_services(audit: Audit, styles: dict) -> list:
    story = [_toc_heading("10. Recommended CALEBREVIEW Services", styles)]
    if not audit.recommended_services:
        story.append(Paragraph(
            "This audit didn't surface issues that map to a specific service \u2014 the fundamentals here are solid.",
            styles["body"],
        ))
        return story
    for service in audit.recommended_services:
        story.append(Paragraph(service, styles["item_label"]))
        story.append(Paragraph(SERVICE_DESCRIPTIONS.get(service, ""), styles["body_soft"]))
        story.append(Spacer(1, 6))
    return story


def _pricing(audit: Audit, styles: dict) -> list:
    story = [_toc_heading("11. Pricing", styles)]

    if "Website Design" not in audit.recommended_services:
        other_services = [s for s in audit.recommended_services if s != "Website Design"]
        note = (
            f"This audit's priority services ({', '.join(other_services)}) are typically scoped individually "
            "based on the business's specific needs \u2014 reply to the email that accompanied this report for "
            "a custom quote."
            if other_services
            else "No services need pricing right now \u2014 reply to this report if anything changes down the line."
        )
        story.append(Paragraph(note, styles["body"]))
        return story

    story.append(Paragraph("Website Packages", styles["h2"]))

    header_style = ParagraphStyle(
        "pricing_header", fontName="Helvetica-Bold", fontSize=10.5, textColor=WHITE,
        alignment=TA_CENTER, leading=14,
    )
    header_row = [""] + [
        Paragraph(f"{name}<br/>Starting from ${price}", header_style)
        for name, price in zip(PACKAGE_NAMES, PACKAGE_STARTING_PRICES)
    ]
    table_data = [header_row]
    for label, starter, growth, professional in PRICING_ROWS:
        table_data.append([label, starter, growth, professional])

    col_widths = [2.3 * inch] + [(CONTENT_WIDTH - 2.3 * inch) / 3] * 3
    pricing_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    pricing_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 1), (0, -1), INK),
        ("TEXTCOLOR", (1, 1), (-1, -1), INK_SOFT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, NA_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 1, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
        ("BOX", (0, 0), (-1, -1), 0.75, LINE),
    ]))
    story.append(pricing_table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(PRICING_NOTE, styles["disclaimer"]))
    return story


def _next_steps(styles: dict) -> list:
    return [
        _toc_heading("12. Next Steps", styles),
        Paragraph(
            "Thank you for taking the time to review this audit. We hope these insights help you better "
            "understand your current online presence and highlight opportunities for growth.",
            styles["closing"],
        ),
        Paragraph(
            "If you have any questions about the findings or would like to discuss any of the "
            "recommendations, simply reply to the email that accompanied this report, or reach out "
            "directly at <b>Caleb@calebreview.com</b>.",
            styles["closing"],
        ),
        Paragraph("Prepared by CALEBREVIEW Lead Gen", styles["signature"]),
        Paragraph("Caleb@calebreview.com \u00b7 calebreview.com", styles["body_soft"]),
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_audit_pdf(business: Business, audit: Audit) -> bytes:
    """Builds the full branded 13-section PDF report and returns it as bytes."""
    buffer = io.BytesIO()
    doc = _build_doc(buffer)
    styles = _styles()

    story: list = []
    story += _cover_story(business, audit, styles)
    story.append(NextPageTemplate("Content"))
    story.append(PageBreak())

    story += _toc_story(styles)
    story.append(PageBreak())

    story += _executive_summary(audit, styles)
    story += _business_information(business, styles)
    story += _overall_scores(audit, styles)

    story += _website_audit(audit, styles)

    story += _single_category_audit("5. Google Business Profile Audit", FindingCategory.google_business, audit, styles)
    story += _single_category_audit("6. Reviews & Trust Audit", FindingCategory.reviews_trust, audit, styles)
    story += _single_category_audit("7. Local SEO Audit", FindingCategory.local_seo, audit, styles)
    story += _revenue_opportunity(audit, styles)
    story += _priority_fixes(audit, styles)

    story += _recommended_services(audit, styles)
    story += _pricing(audit, styles)
    story.append(Spacer(1, 16))
    story += _next_steps(styles)

    doc.multiBuild(story)
    return buffer.getvalue()
