-- ===========================================================================
-- CalebReview Lead Intelligence Platform — Supabase schema
-- Run this in the Supabase SQL editor (or via `supabase db push`) on a fresh
-- project. This schema does NOT use Supabase Auth — there is no login
-- system. Every table is scoped to one fixed user row you create once
-- (see the bottom of this file). Service-role key only; RLS policies
-- below are kept as defense-in-depth but are never actually exercised
-- since the backend never connects with an end-user JWT.
-- ===========================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

create type source_api as enum ('serpapi', 'apify', 'both');
create type audit_status as enum ('not_started', 'queued', 'running', 'complete', 'failed');
create type pdf_status as enum ('not_generated', 'generating', 'ready', 'failed');
create type email_status as enum ('no_email_found', 'not_generated', 'draft', 'ready', 'sent', 'failed');
create type search_status as enum ('running', 'complete', 'failed');
create type finding_category as enum (
  'website_foundation', 'lead_generation', 'business_trust', 'technical_seo',
  'google_business', 'reviews_trust', 'local_seo'
);
create type finding_severity as enum ('strong', 'watch', 'critical');
create type delivery_status as enum ('Draft', 'Ready', 'Sent', 'Failed');
create type activity_action as enum (
  'Search Started', 'Search Completed', 'Audit Generated', 'PDF Generated',
  'Email Generated', 'Email Sent', 'Email Failed'
);
create type activity_status as enum ('success', 'error', 'pending');
create type api_key_provider as enum ('serpapi', 'apify');

-- ---------------------------------------------------------------------------
-- Geography (countries, states) — shared reference data, not per-user.
-- Seeded once via `python -m app.scripts.seed_geography` (uses pycountry's
-- ISO 3166-1/3166-2 data — no GeoNames download needed, no external API
-- calls at search time). No RLS: this isn't owned by any one user, and the
-- backend's service-role client bypasses RLS anyway.
-- ---------------------------------------------------------------------------

create table countries (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  iso2 text not null unique,
  iso3 text not null unique
);

create index idx_countries_iso2 on countries(iso2);

create table states (
  id uuid primary key default gen_random_uuid(),
  country_id uuid not null references countries(id) on delete cascade,
  name text not null,
  state_code text not null,
  unique (country_id, state_code)
);

create index idx_states_country_id on states(country_id);
create index idx_states_state_code on states(state_code);

-- ---------------------------------------------------------------------------
-- Users  (a single row for the one operator — no Supabase Auth involved)
-- ---------------------------------------------------------------------------

create table users (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  full_name text,
  agency_name text,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Search_History
-- ---------------------------------------------------------------------------

create table search_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  keyword text not null,
  location text not null,
  apis_used source_api not null,
  result_count integer not null default 0,
  status search_status not null default 'running',
  error_detail text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  created_at timestamptz not null default now()
);

create index idx_search_history_user on search_history(user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Businesses
-- ---------------------------------------------------------------------------

create table businesses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  search_id uuid references search_history(id) on delete set null,

  name text not null,
  industry text,
  location text,
  website text,
  phone text,
  address text,
  google_maps_url text,
  google_place_id text,
  rating numeric(2,1),
  review_count integer,

  source_api source_api not null,
  date_found timestamptz not null default now(),

  public_email text,

  raw_serpapi_data jsonb,  -- full SerpApi response item, for the audit engine
  raw_apify_data jsonb,    -- full Apify response item, for the audit engine

  audit_status audit_status not null default 'not_started',
  pdf_status pdf_status not null default 'not_generated',
  email_status email_status not null default 'not_generated',

  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_businesses_user on businesses(user_id, created_at desc);
create index idx_businesses_search on businesses(search_id);
-- Dedup lookups: Place ID, Maps URL, and name+address are the three merge keys.
create index idx_businesses_place_id on businesses(google_place_id) where google_place_id is not null;
create index idx_businesses_maps_url on businesses(google_maps_url) where google_maps_url is not null;
create index idx_businesses_name_address on businesses(user_id, name, address);

-- ---------------------------------------------------------------------------
-- Audits + Audit_Findings
-- ---------------------------------------------------------------------------

create table audits (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  has_website boolean not null,

  website_score integer,           -- null = N/A (no website)
  google_business_score integer,
  overall_score integer,
  opportunity_score integer,

  recommended_services text[] not null default '{}',
  created_at timestamptz not null default now(),

  constraint score_range check (
    (website_score is null or website_score between 0 and 100) and
    (google_business_score between 0 and 100) and
    (overall_score between 0 and 100) and
    (opportunity_score between 0 and 100)
  )
);

create index idx_audits_business on audits(business_id, created_at desc);

create table audit_findings (
  id uuid primary key default gen_random_uuid(),
  audit_id uuid not null references audits(id) on delete cascade,
  category finding_category not null,
  item_key text,              -- maps to a specific checklist item, e.g. 'https', 'schema'
  label text not null,
  detail text not null,
  recommendation text,
  severity finding_severity not null
);

create index idx_audit_findings_audit on audit_findings(audit_id);

-- ---------------------------------------------------------------------------
-- Generated_PDFs
-- ---------------------------------------------------------------------------

create table generated_pdfs (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  audit_id uuid not null references audits(id) on delete cascade,
  storage_path text,               -- path within the Supabase Storage bucket
  status pdf_status not null default 'not_generated',
  created_at timestamptz not null default now()
);

create index idx_generated_pdfs_business on generated_pdfs(business_id);

-- ---------------------------------------------------------------------------
-- Generated_Emails + Email_History
-- ---------------------------------------------------------------------------

create table generated_emails (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  pdf_id uuid references generated_pdfs(id) on delete set null,
  subject text,
  body text,
  status email_status not null default 'not_generated',
  created_at timestamptz not null default now()
);

create index idx_generated_emails_business on generated_emails(business_id);

create table email_history (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references businesses(id) on delete cascade,
  email_id uuid references generated_emails(id) on delete set null,
  recipient text not null,
  subject text,
  date_generated timestamptz not null default now(),
  date_sent timestamptz,
  delivery_status delivery_status not null default 'Draft'
);

create index idx_email_history_business on email_history(business_id);

-- ---------------------------------------------------------------------------
-- Settings  (one row per user)
-- ---------------------------------------------------------------------------

create table settings (
  user_id uuid primary key references users(id) on delete cascade,
  -- API keys are stored via Supabase Vault / encrypted column in production;
  -- plain text here is a placeholder for local development only.
  openai_api_key text,
  claude_api_key text,
  gemini_api_key text,
  grok_api_key text,
  -- Which provider/model actually writes audit summaries and outreach
  -- emails — chosen on the Settings page (provider first, then a model
  -- dropdown scoped to that provider) rather than hardcoded to OpenAI.
  ai_provider text not null default 'openai',
  ai_model text,
  serpapi_key text,
  apify_token text,
  resend_api_key text,
  telegram_bot_token text,
  telegram_chat_id text,
  default_industry text,
  default_location text,
  serpapi_enabled boolean not null default true,
  apify_enabled boolean not null default true,
  brand_name text default 'CalebReview',
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Saved API keys — multiple named SerpApi/Apify keys per user, picked from
-- at search time (Lead Search page) instead of the single serpapi_key/
-- apify_token above. Those two columns on `settings` still exist and still
-- work as a fallback default when no saved key is picked for a search, so
-- existing setups aren't broken by this — this table is additive.
-- ---------------------------------------------------------------------------

create table saved_api_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  provider api_key_provider not null,
  name text not null,
  key_value text not null,
  created_at timestamptz not null default now(),
  unique (user_id, provider, name)
);

create index idx_saved_api_keys_user_provider on saved_api_keys(user_id, provider);

-- ---------------------------------------------------------------------------
-- Activity_Log
-- ---------------------------------------------------------------------------

create table activity_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  business_id uuid references businesses(id) on delete set null,
  action activity_action not null,
  status activity_status not null,
  detail text,
  created_at timestamptz not null default now()
);

create index idx_activity_log_user on activity_log(user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at trigger for businesses
-- ---------------------------------------------------------------------------

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_businesses_updated_at
before update on businesses
for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security — every table is scoped to the owning user
-- ---------------------------------------------------------------------------

alter table users enable row level security;
alter table search_history enable row level security;
alter table businesses enable row level security;
alter table audits enable row level security;
alter table audit_findings enable row level security;
alter table generated_pdfs enable row level security;
alter table generated_emails enable row level security;
alter table email_history enable row level security;
alter table settings enable row level security;
alter table activity_log enable row level security;

create policy "users read own row" on users for select using (auth.uid() = id);
create policy "users update own row" on users for update using (auth.uid() = id);

create policy "own search history" on search_history for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own businesses" on businesses for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Child tables are scoped via their parent business's owner.
create policy "own audits" on audits for all
  using (exists (select 1 from businesses b where b.id = audits.business_id and b.user_id = auth.uid()))
  with check (exists (select 1 from businesses b where b.id = audits.business_id and b.user_id = auth.uid()));

create policy "own audit findings" on audit_findings for all
  using (exists (
    select 1 from audits a join businesses b on b.id = a.business_id
    where a.id = audit_findings.audit_id and b.user_id = auth.uid()
  ))
  with check (exists (
    select 1 from audits a join businesses b on b.id = a.business_id
    where a.id = audit_findings.audit_id and b.user_id = auth.uid()
  ));

create policy "own pdfs" on generated_pdfs for all
  using (exists (select 1 from businesses b where b.id = generated_pdfs.business_id and b.user_id = auth.uid()))
  with check (exists (select 1 from businesses b where b.id = generated_pdfs.business_id and b.user_id = auth.uid()));

create policy "own emails" on generated_emails for all
  using (exists (select 1 from businesses b where b.id = generated_emails.business_id and b.user_id = auth.uid()))
  with check (exists (select 1 from businesses b where b.id = generated_emails.business_id and b.user_id = auth.uid()));

create policy "own email history" on email_history for all
  using (exists (select 1 from businesses b where b.id = email_history.business_id and b.user_id = auth.uid()))
  with check (exists (select 1 from businesses b where b.id = email_history.business_id and b.user_id = auth.uid()));

create policy "own settings" on settings for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

alter table saved_api_keys enable row level security;
create policy "own saved api keys" on saved_api_keys for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own activity log" on activity_log for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- One-time setup: create your single user + settings row
-- ---------------------------------------------------------------------------
-- There's no signup flow — run this once after applying the schema above,
-- then copy the printed id into your backend's .env as DEFAULT_USER_ID.

-- insert into users (email, full_name, agency_name)
-- values ('caleb@calebreview.com', 'Caleb Areh', 'CalebReview')
-- returning id;  -- <-- copy this UUID into DEFAULT_USER_ID in .env

-- insert into settings (user_id) values ('paste-the-id-from-above-here');
