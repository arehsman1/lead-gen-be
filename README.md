# CalebReview Lead Intelligence — Backend

FastAPI backend for the Lead Intelligence Platform. Built against the
Supabase schema in `supabase/schema.sql`, and against the frontend types in
`src/lib/types.ts` from the frontend phase — all three stay in lockstep
field-for-field.

## What's real vs. what needs your keys

**Real and tested right now, with no external credentials** (92 tests total):
- The dedup/merge engine (`app/services/dedup_service.py`) — Place ID → Maps
  URL → name+address priority, SerpApi-wins-on-overlap merge rule. 7 tests.
- The real audit engine (`app/services/evaluators/`) — see Phase 4 below.
  47 tests across website, GBP, reviews, and local SEO evaluators
  (website includes the SSRF guard tests).
- The scoring engine (`app/services/scoring_service.py`) — deterministic,
  per-item weighted average, correctly returns `N/A` for Website Score
  when there's no website. 8 tests.
- The PDF report generator (`app/services/pdf_service.py`) — see Phase 3
  below. 13 tests.
- Public email extraction (`app/services/email_finder_service.py`) — parses
  real HTML for mailto: links and footer text, ignores junk/placeholder
  domains, never invents an address. 5 tests.
- PDF retention cleanup (`app/services/cleanup_service.py`) — see "Auth"
  below (PDF retention is documented in that section). 7 tests.
- Telegram notification formatting (`app/services/telegram_service.py`) —
  see Phase 6 below. 5 tests.
- The full FastAPI app boots and routes correctly (verified with
  `TestClient`). No login system — see "Auth" below.

**Structurally complete, but needs your API keys to actually run against
live services** (no network access to these providers from here, so
treat as unverified against real traffic until you run it):
- `app/services/scraping_service.py` — SerpApi (`engine=google_maps`) and
  Apify (Google Maps actor) calls.
- `app/services/evaluators/gbp_evaluator.py` — field names are an
  unverified guess at SerpApi/Apify's actual response schema; verify
  against one real response before trusting it (flagged in the module
  docstring).
- `app/services/ai_service.py` — OpenAI chat completions for audit summaries
  and outreach emails, JSON-mode, prompted to only use supplied facts and
  never guarantee outcomes.
- `app/api/routes/emails.py` — Resend send call.
- `app/api/routes/settings.py` — per-provider connection tests.
- Every Supabase read/write — needs a real Supabase project.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DEFAULT_USER_ID

# 1. Create a Supabase project.
# 2. Run supabase/schema.sql in the SQL editor (or `supabase db push`).
# 3. Create a private "audit-pdfs" bucket in Supabase Storage.
# 4. Fill in .env from Project Settings → API.

uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Run tests:
```bash
pytest -v          # 92 tests, all pure logic + fixtures, no external calls needed
ruff check app tests
```

## Architecture

```
app/
  core/
    config.py           # env-driven settings
    supabase.py          # service-role client (server-side only, bypasses RLS —
                          # every query manually filters by user_id)
    auth.py               # no login — returns fixed DEFAULT_USER_ID
  models/
    schemas.py            # Pydantic models — mirror supabase/schema.sql + frontend types.ts
  services/
    dedup_service.py            # merge/dedupe logic (pure, tested)
    scoring_service.py          # per-item weighted score calculation (pure, tested)
    scraping_service.py         # SerpApi + Apify adapters
    email_finder_service.py     # public email extraction (pure parsing, tested)
    ai_service.py                # OpenAI: summaries + outreach emails only
    pdf_service.py                # 13-section branded PDF report (tested)
    storage_service.py             # Supabase Storage upload + signed URLs
    checklist_catalog.py            # static "why it matters" copy, ~45 items
    pricing_catalog.py               # static website package pricing
    evaluators/
      website_evaluator.py           # fetches + evaluates the homepage (tested)
      gbp_evaluator.py                # evaluates raw GBP payload (tested)
      reviews_evaluator.py             # evaluates rating/reviews (tested)
      local_seo_evaluator.py            # NAP consistency + local signals (tested)
  api/routes/
    search.py        # POST /api/search (kicks off background scrape+merge job)
    businesses.py     # list/get/find-email/soft-delete
    audits.py          # runs the real evaluators, computes scores, stores findings
    pdfs.py              # generates + uploads the PDF report
    emails.py             # generate outreach email, send via Resend
    settings.py            # API keys, scraper toggles, connection tests
    activity.py              # activity log read
    dashboard.py               # totals for the 6 dashboard cards
  main.py            # app wiring: CORS, rate limiting, request-ID logging,
                       # global error handler
supabase/
  schema.sql          # full DDL: tables, enums, indexes, RLS policies,
                        # raw payload columns, auto-provisioning trigger
tests/
  test_dedup_service.py
  test_scoring_service.py
  test_email_finder_service.py
  test_pdf_service.py
  test_website_evaluator.py
  test_gbp_evaluator.py
  test_reviews_evaluator.py
  test_local_seo_evaluator.py
```

## Security notes for a commercial deployment

- **No login system** — see "Auth" above. The service-role Supabase key
  never leaves the server; the frontend doesn't talk to Supabase at all,
  it only calls this API.
- Every route filters by the fixed `DEFAULT_USER_ID` from settings —
  there's only one user, so there's nothing to isolate between users, but
  the query pattern (`user_id` filter on every read/write) is unchanged
  from when it came from a verified JWT, so re-adding real per-user auth
  later is a smaller diff than it'd otherwise be.
- RLS is still enabled on every table as defense in depth, in case
  anything ever queries Supabase directly instead of through the
  service-role client.
- Rate limiting (slowapi) is wired at the app level; tune
  `RATE_LIMIT_PER_MINUTE` per your plan.
- **Add a layer in front before any public exposure** — nginx basic
  auth, a firewall allowlist, or a VPN. See "Auth" above for why.
- Provider API keys are stored per-user in `settings`; in production, put
  them behind Supabase Vault or an encrypted column rather than plain text —
  the schema has a comment flagging this.

## PDF report generation (Phase 3)

`app/services/pdf_service.py` builds the full branded report to the
13-section cold-outreach spec: cover (with Opportunity Score) → real table
of contents (page numbers resolved via reportlab's `multiBuild`, not
hand-counted) → executive summary → business info → the four score cards →
Website Audit (Foundation/Lead Gen/Trust/Technical SEO checklist, skipped
with an N/A note if there's no website) → Google Business Profile audit →
Reviews & Trust audit → Local SEO audit → Revenue Opportunity (5 estimate
line items, explicitly labeled and disclaimed) → Priority Fixes
(High/Medium/Low) → 90-Day Action Plan → Recommended Services (only ones
the audit actually flagged) → Pricing (only shown if Website Design was
recommended — otherwise a custom-quote note naming the actual relevant
services) → Next Steps.

**Every checklist item's status is either backed by a specific finding or
explicitly marked "Not Assessed"** — nothing is assumed to have passed
just because it wasn't flagged. `app/services/checklist_catalog.py` holds
the full item list (7 categories, ~45 items total) with static "why it
matters" copy; `AuditFinding` carries an `item_key` (which catalog item it
evaluates) and a `recommendation` (the specific fix) alongside the
category/label/detail/severity.

`app/api/routes/pdfs.py` wires it to Supabase: loads the business + latest
audit, generates the PDF, uploads to Storage
(`app/services/storage_service.py`), records the `storage_path`, and
returns a signed download URL on request.

## Real audit engine (Phase 4)

`audits.py` calls four real evaluators instead of placeholder findings:

- **`website_evaluator.py`** — fetches the homepage (+ /sitemap.xml +
  /robots.txt, three lightweight requests, no crawling beyond that) and
  checks all ~24 Website Foundation/Lead Generation/Trust/Technical SEO
  items against the actual HTML. Pure, testable function
  (`evaluate_website_html`) separated from the async fetch.
- **`gbp_evaluator.py`** — evaluates the 10 Google Business Profile items
  from the raw SerpApi/Apify payload stored on the business row.
  **Field names are flagged as unverified against a live response** —
  based on SerpApi's documented schema, not confirmed live.
- **`reviews_evaluator.py`** — rating/review count always evaluated;
  recent-reviews/owner-replies/review-activity only evaluated if an
  individual-reviews array is present, otherwise honestly omitted.
- **`local_seo_evaluator.py`** — NAP consistency between SerpApi and
  Apify when both found the business, local keyword presence in the
  title tag, reuses the website evaluator's schema finding.
  `local_visibility` is intentionally left unassessed — needs real
  rank-tracking data this system doesn't have.

Every item without a specific finding renders "Not Assessed" in the PDF,
never assumed to have passed.

Data plumbing: `RawBusiness`/`MergedBusiness` (dedup_service) and the
SerpApi/Apify adapters carry the original API response item through to
`businesses.raw_serpapi_data` / `raw_apify_data` (jsonb), so the audit
route has real data to evaluate instead of just the normalized fields.

**Two real bugs found and fixed while wiring this together, both caught
by tests before they'd have shipped:**

1. `gbp_evaluator`: an empty-but-present payload (`{}`) was treated
   identically to "no payload at all" (`None`) and silently skipped
   instead of flagging every missing field.
2. **Scoring model bug**: the original flat "-10 per watch, -22 per
   critical" model was designed against 1-2 placeholder findings. Once
   the real evaluators started producing 20-30 granular findings per
   audit, watch-level penalties stacked past zero — an end-to-end smoke
   test with a mostly-solid mock site (14 of 24 items "strong") returned
   a **website score of 0**. Rewrote scoring to a per-item weighted
   average (strong=1.0, watch=0.5, critical=0.0, averaged across assessed
   items) so the score scales correctly regardless of item count. Same
   smoke test after the fix: 75/73/74/26 instead of 0/18/7/93 — matches
   what a human looking at the same site would actually conclude.

**Verified without needing your keys:** all evaluator logic (30 tests)
via crafted HTML/payload fixtures, plus an end-to-end smoke test
(evaluators → scoring → PDF) confirming the whole pipeline composes
correctly, not just each piece in isolation.

**Still unverified against live traffic:** the GBP field-name mapping,
and the website evaluator's heuristics on real-world JS-heavy sites
(forms/CTAs/nav rendered client-side will under-report, since this only
fetches static HTML).

## Deploying to a VPS

`deploy/DEPLOYMENT.md` is a full walkthrough — fresh Ubuntu VPS to both
apps live behind nginx with SSL, roughly 30-45 minutes. Includes:
- `deploy/caleb-backend.service` — systemd unit (runs uvicorn on
  `127.0.0.1:8000`, not exposed publicly — nginx handles that)
- `deploy/caleb-review.conf` — nginx reverse proxy for both apps, sets up
  cleanly for certbot's automatic HTTPS
- `deploy/redeploy.sh` — pulls latest, reinstalls deps, restarts the
  service, checks `/health` came back up

## Telegram notifications (Phase 6)

Every time an outreach email is sent or fails to send, a Telegram message
goes out — same pattern as Caleb's existing branding bot, just for delivery
notifications instead of watermarking.

- `app/services/telegram_service.py` — pure message formatting
  (`format_email_notification`, fully tested with no network) plus a
  thin `send_telegram_message` wrapper that **never raises**: a
  notification failure should never take down the email-send flow that
  triggered it. Tested that it returns `False` gracefully with no
  credentials rather than throwing.
- Wired into `app/api/routes/emails.py`'s `send_email` — fires after
  both the success and failure paths, using whichever `telegram_bot_token`
  / `telegram_chat_id` are saved in that user's `settings` row.
- `app/api/routes/settings.py` — new `telegram` branch in
  `/test-connection` that sends a real "connected" message so you can
  confirm setup without waiting for a live email.
- Setup (same steps as any Telegram bot): message @BotFather, `/newbot`,
  get the token; message your new bot once, then hit
  `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID.
  Both go in Settings → Notifications, same place as the other keys.

**Verified without needing your keys:** message formatting and the
graceful-failure behavior (5 tests). Sending a real message needs a real
bot token — untested against live Telegram from here, same caveat as
every other provider integration.

## Auth

**No login system.** This is a single-operator tool, not a multi-tenant
product. Every request is treated as one fixed user
(`DEFAULT_USER_ID` in `.env`), created once via a one-time SQL snippet
at the bottom of `supabase/schema.sql` rather than a signup flow.
`app/core/auth.py` just returns that fixed id — every route's
`Depends(get_current_user_id)` is unchanged, only what that function
does internally changed, so no route file needed to be touched.

**Note on history:** an earlier session removed Supabase Auth in favor
of this same `DEFAULT_USER_ID` approach, then a later session restored
real login (delegating JWT verification to Supabase's own
`/auth/v1/user` endpoint rather than verifying locally, to sidestep a
signing-scheme mismatch bug — see git history / prior session notes if
you need the full story). This session removed the login system again,
at explicit request — `app/core/auth.py`, `src/proxy.ts`, `/login`, and
the `@supabase/ssr`/`@supabase/supabase-js` frontend dependencies are
all gone. If you want real per-user login back, the JWT-delegation
approach (rather than local verification) is the one that actually
worked — don't reintroduce local `SUPABASE_JWT_SECRET` verification.

**Worth being clear-eyed about:** removing auth means anyone who reaches
the dashboard's URL can use it — run searches (spending your SerpApi/
Apify credits), view business data, trigger email sends. Fine for
`127.0.0.1`-only or behind your own VPN; if this ever sits on a public
IP or domain without another layer in front of it (nginx basic auth,
a firewall allowlist, a VPN), that's worth adding.

**PDF retention**: `app/services/cleanup_service.py` (pure, tested —
7 tests) finds PDFs older than `PDF_RETENTION_DAYS` (default 14) and
`app/scripts/cleanup_expired_pdfs.py` deletes them from both Storage and
the DB row, resetting the owning business's `pdf_status`. Doesn't run on
its own — needs a cron entry (see `deploy/DEPLOYMENT.md` step 12).
14 days was picked as a reasonable middle ground for cold-outreach
reports (long enough to cover a follow-up window, short enough to keep
Storage costs down) — it's one config value, change it to 8 or 30 or
anything else in `.env`.

**Verified without needing your keys:** booted the real backend with a
dummy `.env` (fake Supabase URL/key, real `DEFAULT_USER_ID`) via
`TestClient` and confirmed the request sailed through
`get_current_user_id()` with zero auth-related errors, failing only at
the expected point — Supabase client creation rejecting the
not-validly-shaped dummy key. 92/92 backend tests pass; frontend builds
clean with no `/login` route and no Supabase packages in
`package.json`.

## Known gaps to close before this is truly "production-ready"

- **New: choice of AI provider/model for outreach emails.** Previously
  hardcoded to OpenAI (`gpt-4o-mini`). `app/services/ai_service.py` now
  dispatches to OpenAI, Claude, Gemini, or Grok based on `ai_provider`/
  `ai_model` on Settings — each has a genuinely different request/response
  shape (OpenAI-style chat completions vs Anthropic's Messages API vs
  Gemini's `generateContent` vs Grok, which is OpenAI-compatible). Picking
  a provider on the Settings page (button row) reveals that provider's own
  API key input and a model dropdown scoped to just its own models, so a
  key and model from different providers can't get paired by accident.
  Model lists in `PROVIDER_MODELS` are curated defaults, not an enforced
  allowlist — there's a free-text "custom model" escape hatch since
  providers ship new models faster than any hardcoded list stays current.
  `_extract_json` handles the fact that not every provider supports a
  strict JSON response mode the way OpenAI's `response_format` does — a
  model can still wrap its answer in ```` ```json ```` fences despite the
  prompt asking for raw JSON. If upgrading an existing DB, run
  `supabase/migrations/004_ai_provider_choice.sql`.
- **New: "Refresh from account" live model list.** The Model dropdown on
  Settings defaults to `PROVIDER_MODELS`' curated list, but a Refresh
  button next to it calls `POST /settings/list-models`, which asks the
  provider directly which models this specific key can actually use
  (`list_available_models` in `ai_service.py`) — catches both "my curated
  list went stale" and "this account doesn't have access to that model
  yet". OpenAI/Grok's `/v1/models` list mixes in embeddings, audio, image,
  and moderation models with no separate "type" field to filter on, so
  `_NON_CHAT_MARKERS` is a deliberate (tested) heuristic rather than an
  exact classification; Claude and Gemini's model-list endpoints are
  cleaner and need no such filtering.

- **Fixed: Telegram test-connection always failed regardless of whether
  the bot token was actually right.** `telegram_service.py`'s
  `send_telegram_message` was updated to return `(ok, error_detail)`
  instead of a bare bool, specifically so a bad token, a bad chat ID, and
  a network error would stop looking identical to the user. But
  `app/api/routes/settings.py`'s `test_connection` route was never
  updated to match — it still assigned the whole tuple to `ok` and passed
  it into `TestConnectionResult(ok: bool, ...)`, which raised a Pydantic
  `ValidationError` on every single call. Confirmed directly: constructing
  `TestConnectionResult(ok=(False, "Unauthorized"), ...)` throws
  `Input should be a valid boolean [type=bool_type]`. Fixed by unpacking
  the tuple properly; failures now surface the real reason (e.g.
  "Unauthorized", "Bad Request: chat not found") both in the API response
  and on the Settings page UI.
- **Confirmed working: Apify runs that timed out but still saved leads.**
  `search_apify` already starts the actor run and polls its status
  separately rather than using the run-sync-get-dataset-items endpoint
  (which has a hard ~300s server-side cap that doesn't cancel the run —
  it keeps going and saves results Apify-side, just never comes back for
  them). No further changes needed here, just confirmed via the existing
  tests and docstring that this was already the fix in place.
- **New: multiple named SerpApi/Apify keys.** `saved_api_keys` table +
  `/api/api-keys` (GET/POST/DELETE) let you save several keys per
  provider under a name and pick between them on the Lead Search page —
  useful for juggling multiple client accounts or per-key rate limits.
  Picking a saved key is optional; leaving it unset falls back to the
  single `serpapi_key`/`apify_token` on Settings, unchanged. If upgrading
  an existing DB, run `supabase/migrations/003_saved_api_keys.sql`.
- **No route-level tests for `settings.py`/`search.py`/`api_keys.py`** —
  matches this repo's existing convention (pure logic + fixtures only,
  no DB mocking), but it's exactly why the Telegram bug above shipped
  silently: nothing exercised the actual route function end-to-end. Worth
  a real look if this pattern of bug recurs.

- **New: country/state dropdowns.** The Lead Search form now has
  Country and State/Province dependent dropdowns instead of a free-text
  location field, backed by `countries`/`states` tables seeded from
  `pycountry` (no GeoNames download, no external API calls at search
  time). **If upgrading an already-deployed DB**, run
  `supabase/migrations/002_countries_and_states.sql` in the Supabase SQL
  editor, then seed it once:
  ```bash
  pip install -r requirements.txt   # picks up the new pycountry dependency
  python -m app.scripts.seed_geography
  ```
  The backend's `/api/search` endpoint itself didn't change — the
  frontend composes the picked country + state into the same free-text
  `location` string it always sent, so this is purely additive.

- **If upgrading an already-deployed DB**, run
  `supabase/migrations/001_search_history_duration.sql` in the Supabase
  SQL editor — `schema.sql` itself now includes these columns for fresh
  installs, but an existing database needs the `alter table` to catch up.
  This migration also fixes any search stuck permanently in "running"
  from before this session's fix (see below).
- **Fixed:** searches could get stuck showing "pending" in the Activity
  Log forever. `_run_search_job` in `app/api/routes/search.py` only
  caught one specific error type (`ScraperConfigError`) — any other
  failure (a bad API response, a rate limit, a malformed payload, a
  Supabase write failing) crashed the background task silently, since a
  background task's exceptions don't propagate anywhere a user would see
  them. Now wrapped in one broad try/except that always updates
  `search_history` and inserts a completion `activity_log` entry, success
  or failure. Also added `started_at`/`finished_at` to `search_history`
  (there was no way to compute duration before this) and a
  `GET /api/search/{id}` endpoint so the frontend can poll a single
  search's live status/duration instead of showing a static "search
  started, check back later" message with no way to tell if it's still
  running or silently died.

- **No access control at all** — see "Auth" above. Anyone who can reach
  this API can use it. Fine behind `127.0.0.1`/VPN/firewall allowlist;
  needs a real auth layer before any public exposure.
- ~~No SSRF guard on the website evaluator~~ — fixed:
  `fetch_website()` in `app/services/evaluators/website_evaluator.py` now
  validates scheme (http/https only) and resolved IP (rejects private/
  loopback/link-local/reserved ranges, e.g. cloud metadata endpoints)
  before every request, including every redirect hop — not just the
  first URL. `_is_blocked_ip`/`_assert_safe_url` are pure and unit
  tested (`tests/test_website_evaluator.py`). Known remaining caveat:
  this doesn't fully close DNS rebinding, since the IP is checked before
  the connection rather than pinned into it — acceptable here since
  `website` comes from scraped listing data (SerpApi/Apify), not direct
  user input; would need a custom transport to close completely.
- Verify the GBP field-name mapping against a live SerpApi/Apify response
  before trusting `gbp_evaluator.py` in production.
- The website evaluator only fetches static HTML — a headless-browser
  fetch (e.g. Playwright) would close the JS-rendered-content gap but
  adds real infrastructure cost.
- `broken_links` and `local_visibility` are intentionally left
  unassessed — they need a multi-request link-checker and a
  rank-tracking integration respectively, neither of which exists yet.
- No Celery/background-worker queue yet; `search.py` uses FastAPI's
  built-in `BackgroundTasks`. Fine for one business at a time; batch-
  auditing many leads at once should move to a real queue.
- No integration tests against a real Supabase instance (only unit tests
  against pure logic) — add those once you have a test project provisioned.
