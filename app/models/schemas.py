from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enums — must stay in lockstep with supabase/schema.sql and frontend types.ts
# ---------------------------------------------------------------------------

class SourceApi(str, Enum):
    serpapi = "serpapi"
    apify = "apify"
    both = "both"


class AuditStatus(str, Enum):
    not_started = "not_started"
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class PdfStatus(str, Enum):
    not_generated = "not_generated"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class EmailStatus(str, Enum):
    no_email_found = "no_email_found"
    not_generated = "not_generated"
    draft = "draft"
    ready = "ready"
    sent = "sent"
    failed = "failed"


class SearchStatus(str, Enum):
    running = "running"
    complete = "complete"
    failed = "failed"


class FindingCategory(str, Enum):
    website_foundation = "website_foundation"
    lead_generation = "lead_generation"
    business_trust = "business_trust"
    technical_seo = "technical_seo"
    google_business = "google_business"
    reviews_trust = "reviews_trust"
    local_seo = "local_seo"


class FindingSeverity(str, Enum):
    strong = "strong"
    watch = "watch"
    critical = "critical"


class DeliveryStatus(str, Enum):
    draft = "Draft"
    ready = "Ready"
    sent = "Sent"
    failed = "Failed"


class ActivityAction(str, Enum):
    search_started = "Search Started"
    search_completed = "Search Completed"
    audit_generated = "Audit Generated"
    pdf_generated = "PDF Generated"
    email_generated = "Email Generated"
    email_sent = "Email Sent"
    email_failed = "Email Failed"


class ActivityStatus(str, Enum):
    success = "success"
    error = "error"
    pending = "pending"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)
    apis: SourceApi = SourceApi.both
    # Optional: pick one of several saved, named keys (see api_keys.py)
    # instead of the single serpapi_key/apify_token on Settings. None
    # falls back to that Settings key — existing behavior, unchanged.
    serpapi_key_id: Optional[UUID] = None
    apify_key_id: Optional[UUID] = None


class SearchHistoryEntry(BaseModel):
    id: UUID
    user_id: UUID
    keyword: str
    location: str
    apis_used: SourceApi
    result_count: int
    status: SearchStatus
    error_detail: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Business
# ---------------------------------------------------------------------------

class BusinessBase(BaseModel):
    name: str
    industry: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_place_id: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    source_api: SourceApi
    public_email: Optional[EmailStr] = None


class Business(BusinessBase):
    id: UUID
    user_id: UUID
    search_id: Optional[UUID] = None
    date_found: datetime
    audit_status: AuditStatus
    pdf_status: PdfStatus
    email_status: EmailStatus
    is_deleted: bool = False
    raw_serpapi_data: Optional[dict] = None
    raw_apify_data: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class BusinessUpdate(BaseModel):
    audit_status: Optional[AuditStatus] = None
    pdf_status: Optional[PdfStatus] = None
    email_status: Optional[EmailStatus] = None
    public_email: Optional[EmailStr] = None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditFinding(BaseModel):
    id: Optional[UUID] = None
    category: FindingCategory
    item_key: Optional[str] = None  # maps to a specific checklist item, e.g. "https", "schema"
    label: str
    detail: str
    recommendation: Optional[str] = None
    severity: FindingSeverity


class AuditScores(BaseModel):
    website_score: Optional[int] = Field(default=None, ge=0, le=100)
    google_business_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    opportunity_score: int = Field(ge=0, le=100)


class Audit(BaseModel):
    id: UUID
    business_id: UUID
    has_website: bool
    scores: AuditScores
    findings: list[AuditFinding] = []
    recommended_services: list[str] = []
    created_at: datetime


class AuditCreateRequest(BaseModel):
    business_id: UUID


class WebsiteAuditPayload(BaseModel):
    """
    Structured website signals the audit engine scores against. Per spec,
    this must be sourced from a third-party API response — e.g. an Apify
    site-crawl/SEO-audit actor, or a PageSpeed-style API — never from the
    backend fetching the business's website directly. Every field is
    optional: whatever the source API didn't return, the engine leaves
    unassessed rather than guessing.
    """

    https: Optional[bool] = None
    mobile_friendly: Optional[bool] = None
    load_time_ms: Optional[int] = None
    nav_menu_found: Optional[bool] = None
    homepage_word_count: Optional[int] = None
    internal_link_count: Optional[int] = None

    has_contact_form: Optional[bool] = None
    has_tel_link: Optional[bool] = None
    has_booking_widget: Optional[bool] = None
    has_quote_form: Optional[bool] = None
    cta_count: Optional[int] = None

    has_about_page: Optional[bool] = None
    has_contact_page: Optional[bool] = None
    has_privacy_policy: Optional[bool] = None
    testimonial_count: Optional[int] = None
    trust_badge_count: Optional[int] = None

    title_tag: Optional[str] = None
    meta_description: Optional[str] = None
    h1_count: Optional[int] = None
    alt_text_coverage_pct: Optional[float] = None
    sitemap_found: Optional[bool] = None
    robots_txt_found: Optional[bool] = None
    robots_blocks_everything: Optional[bool] = None
    schema_types_found: Optional[list[str]] = None
    broken_link_count: Optional[int] = None

    title_contains_location: Optional[bool] = None
    local_keyword_mentions: Optional[int] = None
    local_business_schema_found: Optional[bool] = None


class GbpAuditPayload(BaseModel):
    """
    Structured Google Business Profile signals, sourced from SerpApi's
    google_maps engine and/or an Apify Google Maps actor — never scraped
    directly. Optional fields mirror WebsiteAuditPayload's philosophy:
    missing data stays unassessed.
    """

    description: Optional[str] = None
    category_count: Optional[int] = None
    hours_complete: Optional[bool] = None
    photo_count: Optional[int] = None
    has_logo: Optional[bool] = None
    has_cover_image: Optional[bool] = None
    website_linked: Optional[bool] = None
    appointment_link_present: Optional[bool] = None
    unanswered_questions_count: Optional[int] = None
    service_area_count: Optional[int] = None

    days_since_last_review: Optional[int] = None
    owner_reply_rate_pct: Optional[float] = None
    reviews_last_90_days: Optional[int] = None

    local_pack_appearances: Optional[int] = None
    nap_consistent: Optional[bool] = None


# ---------------------------------------------------------------------------
# PDF / Email
# ---------------------------------------------------------------------------

class GeneratedPdf(BaseModel):
    id: UUID
    business_id: UUID
    audit_id: UUID
    storage_path: Optional[str] = None
    status: PdfStatus
    created_at: datetime


class GeneratedEmail(BaseModel):
    id: UUID
    business_id: UUID
    pdf_id: Optional[UUID] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    status: EmailStatus
    created_at: datetime


class GenerateEmailRequest(BaseModel):
    business_id: UUID


class SendEmailRequest(BaseModel):
    email_id: UUID


class EmailHistoryEntry(BaseModel):
    id: UUID
    business_id: UUID
    email_id: Optional[UUID] = None
    recipient: str
    subject: Optional[str] = None
    date_generated: datetime
    date_sent: Optional[datetime] = None
    delivery_status: DeliveryStatus


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class AiProvider(str, Enum):
    openai = "openai"
    claude = "claude"
    gemini = "gemini"
    grok = "grok"


class SettingsIn(BaseModel):
    openai_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    grok_api_key: Optional[str] = None
    ai_provider: AiProvider = AiProvider.openai
    ai_model: Optional[str] = None
    serpapi_key: Optional[str] = None
    apify_token: Optional[str] = None
    resend_api_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    default_industry: Optional[str] = None
    default_location: Optional[str] = None
    serpapi_enabled: bool = True
    apify_enabled: bool = True
    brand_name: str = "CALEBREVIEW Lead Gen"


class SettingsOut(BaseModel):
    # Keys are masked, never returned in full once saved.
    openai_api_key_set: bool
    claude_api_key_set: bool
    gemini_api_key_set: bool
    grok_api_key_set: bool
    ai_provider: AiProvider
    ai_model: Optional[str] = None
    serpapi_key_set: bool
    apify_token_set: bool
    resend_api_key_set: bool
    telegram_bot_token_set: bool
    telegram_chat_id: Optional[str] = None  # not a secret — fine to echo back for confirmation
    default_industry: Optional[str] = None
    default_location: Optional[str] = None
    serpapi_enabled: bool
    apify_enabled: bool
    brand_name: str


class TestConnectionRequest(BaseModel):
    provider: str  # "openai" | "serpapi" | "apify" | "resend" | "telegram"


class TestConnectionResult(BaseModel):
    provider: str
    ok: bool
    message: str


class ListModelsRequest(BaseModel):
    provider: AiProvider
    # Optional: check an unsaved, just-typed key without requiring it be
    # saved to Settings first. None falls back to the saved key for that
    # provider.
    api_key: Optional[str] = None


class ListModelsResult(BaseModel):
    provider: AiProvider
    models: list[str]


# ---------------------------------------------------------------------------
# Saved API keys — multiple named SerpApi/Apify keys, picked from at search
# time instead of the single serpapi_key/apify_token on Settings.
# ---------------------------------------------------------------------------


class ApiKeyProvider(str, Enum):
    serpapi = "serpapi"
    apify = "apify"


class SavedApiKeyIn(BaseModel):
    provider: ApiKeyProvider
    name: str
    key_value: str


class SavedApiKeyOut(BaseModel):
    # key_value is deliberately never returned once saved — same masking
    # convention as the single-key fields on SettingsOut.
    id: UUID
    provider: ApiKeyProvider
    name: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

class ActivityLogEntry(BaseModel):
    id: UUID
    business_id: Optional[UUID] = None
    action: ActivityAction
    status: ActivityStatus
    detail: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardTotals(BaseModel):
    total_businesses: int
    total_audits: int
    total_pdfs: int
    total_emails_generated: int
    total_emails_sent: int
    total_leads_processed: int


# ---------------------------------------------------------------------------
# Geography (countries, states) — shared reference data
# ---------------------------------------------------------------------------

class Country(BaseModel):
    id: UUID
    name: str
    iso2: str
    iso3: str


class State(BaseModel):
    id: UUID
    country_id: UUID
    name: str
    state_code: str
