"""Static CALEBREVIEW Lead Gen website package pricing, structured as comparison-table
rows (feature, Starter value, Growth value, Professional value) rather than
per-package bullet lists, so the PDF can render it as an actual table."""

PACKAGE_NAMES = ["Starter", "Growth", "Professional"]
PACKAGE_STARTING_PRICES = [299, 499, 799]

# Each row: (feature label, Starter, Growth, Professional).
# "\u2713" renders as a checkmark; "\u2014" renders as an em dash (not included).
PRICING_ROWS = [
    ("Pages", "5-page website", "Up to 9 pages", "Up to 20 pages"),
    ("Mobile responsive", "\u2713", "\u2713", "\u2713"),
    ("Contact form", "\u2713", "\u2713", "\u2713"),
    ("Click-to-call", "\u2713", "\u2713", "\u2713"),
    ("SSL", "\u2713", "\u2713", "\u2713"),
    ("Google Business setup", "\u2713", "\u2713", "\u2713"),
    ("Local SEO", "Basic", "Basic", "Advanced"),
    ("Portfolio / Gallery", "\u2014", "\u2713", "\u2713"),
    ("Service pages", "\u2014", "\u2713", "\u2713"),
    ("Review integration", "\u2014", "\u2713", "\u2713"),
    ("Google Analytics & Search Console", "\u2014", "\u2713", "\u2713"),
    ("Speed optimization", "\u2014", "\u2713", "\u2713"),
    ("Lead capture forms", "\u2014", "\u2713", "\u2713"),
    ("Competitor keyword research", "\u2014", "\u2014", "\u2713"),
    ("On-page SEO", "\u2014", "\u2014", "\u2713"),
    ("FAQ section", "\u2014", "\u2014", "\u2713"),
    ("Schema markup", "\u2014", "\u2014", "\u2713"),
    ("Sitemap & robots.txt", "\u2014", "\u2014", "\u2713"),
    ("Monthly performance reports", "\u2014", "\u2014", "\u2713"),
    ("Support included", "\u2014", "3 months", "6 months"),
]

PRICING_NOTE = "Prices shown are starting prices and may vary depending on project scope and business requirements."
