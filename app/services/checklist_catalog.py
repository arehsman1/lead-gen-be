"""
Static reference content for every checklist item the audit covers. The
"why it matters" copy doesn't change per business — it's the same reason
a missing H1 matters for any business — so it lives here once rather than
being regenerated per report. Per-business specifics (status, detail,
recommendation) come from AuditFinding rows keyed by item_key.
"""

from app.models.schemas import FindingCategory

# category -> ordered list of (item_key, label, why_it_matters)
CHECKLIST_CATALOG: dict[FindingCategory, list[tuple[str, str, str]]] = {
    FindingCategory.website_foundation: [
        ("website_found", "Website Found", "A working website is the base every other channel points back to."),
        ("https", "HTTPS", "Browsers flag non-HTTPS sites as 'Not Secure,' which drives visitors away before they read a word."),
        ("mobile_friendly", "Mobile Friendly", "Most local searches happen on a phone — a site that doesn't adapt loses those visitors immediately."),
        ("speed", "Speed", "Every extra second of load time measurably increases the chance a visitor leaves before the page finishes loading."),
        ("navigation", "Navigation", "Visitors who can't quickly find what they need leave for a competitor's site instead."),
        ("homepage_quality", "Homepage Quality", "The homepage is often the only page a visitor sees — it has to make the case in seconds."),
        ("website_structure", "Website Structure", "A clear structure helps both visitors and search engines understand what the business offers."),
    ],
    FindingCategory.lead_generation: [
        ("contact_form", "Contact Form", "A contact form captures visitors who aren't ready to call but are ready to reach out."),
        ("click_to_call", "Click-to-Call", "On mobile, a tappable phone number turns interest into a call with zero friction."),
        ("booking_system", "Booking System", "Online booking captures leads outside business hours, when staff aren't available to answer the phone."),
        ("quote_request_form", "Quote Request Form", "A dedicated quote request lowers the barrier for price-sensitive visitors to engage."),
        ("ctas", "Calls-to-Action", "Without a clear next step, interested visitors leave without taking any action at all."),
    ],
    FindingCategory.business_trust: [
        ("about_page", "About Page", "Visitors size up a business by who's behind it before they decide to trust it with their money."),
        ("contact_page", "Contact Page", "A dedicated contact page signals a real, reachable business rather than a fly-by-night site."),
        ("privacy_policy", "Privacy Policy", "A missing privacy policy is a red flag for visitors and can affect ad platform and SEO eligibility."),
        ("testimonials", "Testimonials", "Third-party proof is one of the strongest drivers of a first-time visitor's decision to convert."),
        ("trust_signals", "Trust Signals", "Certifications, guarantees, and badges reduce the perceived risk of trying a new business."),
    ],
    FindingCategory.technical_seo: [
        ("title_tag", "Title Tag", "The title tag is the first thing a searcher reads in results — a weak one gets skipped over."),
        ("meta_description", "Meta Description", "A good meta description is free ad copy that improves click-through from search results."),
        ("h1", "H1 Heading", "The H1 tells both visitors and search engines what the page is actually about."),
        ("alt_text", "Alt Text", "Alt text helps images rank in search and keeps the site usable for visitors using screen readers."),
        ("sitemap", "Sitemap", "A sitemap helps search engines find and index every page, not just the homepage."),
        ("robots_txt", "Robots.txt", "A misconfigured robots.txt can accidentally block search engines from indexing the site at all."),
        ("schema", "Schema Markup", "Schema markup helps the business show up with rich results — hours, ratings, and pricing — right in search."),
        ("broken_links", "Broken Links", "Broken links waste the visits a business worked to earn and quietly hurt search rankings."),
    ],
    FindingCategory.google_business: [
        ("business_description", "Business Description", "A clear description helps Google match the listing to the right searches."),
        ("categories", "Categories", "Accurate categories are one of the strongest factors in whether a business shows up for a given search."),
        ("opening_hours", "Opening Hours", "Wrong or missing hours send customers to a competitor when they show up and the business isn't open."),
        ("photos", "Photos", "Listings with more photos get meaningfully more clicks and calls than listings without."),
        ("logo", "Logo", "A logo makes a listing look like an established, trustworthy business at a glance."),
        ("cover_image", "Cover Image", "The cover image is the first visual impression a searcher gets — a blank one looks unfinished."),
        ("website_link", "Website Link", "Without a linked website, Google Business traffic has nowhere to go but the phone."),
        ("appointment_link", "Appointment Link", "A direct booking link turns a listing view into a booked appointment without a phone call."),
        ("qna", "Questions & Answers", "Unanswered public questions sit on the listing forever, visible to every future searcher."),
        ("service_areas", "Service Areas", "Defined service areas keep the listing showing up for the right nearby searches."),
    ],
    FindingCategory.reviews_trust: [
        ("average_rating", "Average Rating", "Rating is one of the first things a searcher compares between competing businesses."),
        ("total_reviews", "Total Reviews", "A low review count reads as 'new or unproven,' even for an established business."),
        ("recent_reviews", "Recent Reviews", "A gap in recent reviews can make an active business look inactive."),
        ("owner_replies", "Owner Replies", "Replying to reviews, especially critical ones, shows future customers the business is engaged."),
        ("review_activity", "Review Activity", "A steady trickle of new reviews signals an active, trusted business to both customers and Google."),
        ("website_testimonials", "Website Testimonials", "Pulling reviews onto the website reinforces trust right where visitors are deciding."),
        ("trust_opportunities", "Trust Opportunities", "Simple, low-cost ways to collect more social proof are often sitting unused."),
    ],
    FindingCategory.local_seo: [
        ("local_visibility", "Local Visibility", "This measures how often the business actually appears in local search results for its category."),
        ("business_info_consistency", "Business Information Consistency", "Mismatched name/address/phone across directories confuses both customers and Google's ranking algorithm."),
        ("metadata", "Metadata", "Location-aware metadata is what helps a page rank for 'near me' and city-specific searches."),
        ("local_keywords", "Local Keywords", "Content that never mentions the service area is competing for the wrong searches."),
        ("schema", "Local Schema", "LocalBusiness schema gives search engines explicit, structured location data to rank on."),
        ("gbp_optimization", "Google Business Optimization", "An optimized profile compounds every other local SEO effort — it's the anchor of local visibility."),
    ],
}

CATEGORY_SECTION_TITLES = {
    FindingCategory.website_foundation: "Website Foundation",
    FindingCategory.lead_generation: "Lead Generation",
    FindingCategory.business_trust: "Trust",
    FindingCategory.technical_seo: "Technical SEO",
}
