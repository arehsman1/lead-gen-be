"""
The AI layer's job is strictly narrow, per spec: it writes audit summaries,
finding explanations, recommendations, and outreach emails FROM data this
service is handed. It never scrapes, never finds or guesses emails, never
sends anything, and never invents business facts — every prompt below is
built entirely from structured audit data already stored in the database.

Supports four providers (OpenAI, Anthropic/Claude, Google/Gemini, xAI/Grok)
rather than being hardcoded to OpenAI — which provider and model actually
runs is chosen on the Settings page and passed in per call, not fixed here.
Each provider has a genuinely different request/response shape (OpenAI-style
chat completions vs Anthropic's Messages API vs Gemini's generateContent vs
Grok, which is OpenAI-compatible) — the four `_call_*` functions below own
that difference; everything above them works with one plain (text, None)
or raises AIServiceError either way.
"""

import json
import re

import httpx

from app.models.schemas import AiProvider, Audit, Business

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROK_URL = "https://api.x.ai/v1/chat/completions"
CLAUDE_API_VERSION = "2023-06-01"

# Curated defaults shown in the Settings model dropdown per provider — not
# an enforced allowlist. Any model string the provider actually accepts
# will work; the frontend also offers a free-text "custom" option since
# providers ship new models faster than this list can be kept current.
PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-4o", "gpt-4o-mini"],
    "claude": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "gemini": ["gemini-3.5-flash", "gemini-3.1-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "grok": ["grok-4.5", "grok-4.3", "grok-4.20", "grok-4.1-fast"],
}
DEFAULT_MODEL: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "claude": "claude-haiku-4-5-20251001",
    "gemini": "gemini-2.5-flash",
    "grok": "grok-4.1-fast",
}

OUTREACH_SYSTEM_PROMPT = """You write short, personalized outreach emails for a digital marketing \
agency reaching out to local businesses after auditing their online presence. \
Rules:
- Use only the facts provided in the audit data below. Never invent statistics, \
  claims, or business details.
- Never guarantee specific revenue, traffic, leads, or ranking outcomes.
- Tone: collaborative and specific, not salesy. Reference one or two concrete, \
  real findings rather than generic praise or generic criticism.
- Keep the email under 150 words. End with a low-pressure call to action \
  (a quick call or reply), not a hard sell.
- Return ONLY a strict JSON object and nothing else — no markdown code fences, \
  no commentary before or after it: {"subject": "...", "body": "..."}"""

SUMMARY_SYSTEM_PROMPT = """You write a 2-3 sentence executive summary for a website/Google \
Business audit report, based only on the structured findings provided. Do not invent \
facts. Do not guarantee outcomes. Plain, direct language a business owner with no \
marketing background can understand."""


class AIServiceError(RuntimeError):
    pass


def _build_outreach_context(business: Business, audit: Audit) -> dict:
    return {
        "business_name": business.name,
        "industry": business.industry,
        "location": business.location,
        "has_website": audit.has_website,
        "scores": audit.scores.model_dump(),
        "positive_findings": [f.label for f in audit.findings if f.severity == "strong"],
        "issues": [
            {"label": f.label, "detail": f.detail, "severity": f.severity}
            for f in audit.findings
            if f.severity != "strong"
        ],
        "recommended_services": audit.recommended_services,
    }


def _extract_json(text: str) -> dict:
    """OpenAI's json_object response_format guarantees clean JSON with no
    wrapping; Claude/Gemini/Grok don't all support that mode the same way,
    so despite the prompt asking for raw JSON, a model can still wrap its
    answer in ```json fences or add a stray sentence. Strip fences first,
    then fall back to grabbing the first {...} block before giving up."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise AIServiceError(f"Model did not return valid JSON: {text[:200]!r}")


async def _call_openai_compatible(
    url: str, model: str, system_prompt: str, user_content: str, api_key: str, timeout: float, json_mode: bool
) -> str:
    """Shared by OpenAI and Grok — Grok's API is intentionally OpenAI Chat
    Completions-compatible, same request/response shape, different host."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.5,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


async def _call_claude(model: str, system_prompt: str, user_content: str, api_key: str, timeout: float) -> str:
    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": CLAUDE_API_VERSION,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(CLAUDE_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["content"][0]["text"]


async def _call_gemini(model: str, system_prompt: str, user_content: str, api_key: str, timeout: float) -> str:
    url = GEMINI_URL_TEMPLATE.format(model=model)
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
    }
    headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def _generate_text(
    provider: str,
    model: str,
    system_prompt: str,
    user_content: str,
    api_key: str,
    timeout: float,
    json_mode: bool = False,
) -> str:
    if not api_key:
        raise AIServiceError(f"{provider} API key is not configured")
    model = model or DEFAULT_MODEL.get(provider, "")

    try:
        if provider == AiProvider.openai or provider == "openai":
            return await _call_openai_compatible(OPENAI_URL, model, system_prompt, user_content, api_key, timeout, json_mode)
        if provider == AiProvider.grok or provider == "grok":
            return await _call_openai_compatible(GROK_URL, model, system_prompt, user_content, api_key, timeout, json_mode)
        if provider == AiProvider.claude or provider == "claude":
            return await _call_claude(model, system_prompt, user_content, api_key, timeout)
        if provider == AiProvider.gemini or provider == "gemini":
            return await _call_gemini(model, system_prompt, user_content, api_key, timeout)
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:300]
        raise AIServiceError(f"{provider} API error ({e.response.status_code}): {detail}") from e
    except httpx.HTTPError as e:
        raise AIServiceError(f"Network error reaching {provider}: {e}") from e

    raise AIServiceError(f"Unknown AI provider: {provider!r}")


async def generate_outreach_email(
    business: Business,
    audit: Audit,
    api_key: str,
    provider: str = "openai",
    model: str | None = None,
    timeout: float = 30.0,
) -> dict:
    context = _build_outreach_context(business, audit)
    text = await _generate_text(
        provider, model, OUTREACH_SYSTEM_PROMPT, json.dumps(context), api_key, timeout, json_mode=True
    )
    parsed = _extract_json(text)

    if "subject" not in parsed or "body" not in parsed:
        raise AIServiceError("Model response missing subject/body")

    return {"subject": parsed["subject"], "body": parsed["body"]}


async def generate_audit_summary(
    audit: Audit,
    api_key: str,
    provider: str = "openai",
    model: str | None = None,
    timeout: float = 30.0,
) -> str:
    text = await _generate_text(
        provider,
        model,
        SUMMARY_SYSTEM_PROMPT,
        json.dumps(audit.model_dump(mode="json")),
        api_key,
        timeout,
    )
    return text.strip()


# Substrings that mark an OpenAI/Grok model id as NOT a text chat model —
# their /v1/models list mixes in embeddings, audio, image, and moderation
# models with no separate "type" field to filter on cleanly, so this is a
# deliberate heuristic rather than an exact classification.
_NON_CHAT_MARKERS = ("embedding", "audio", "realtime", "transcribe", "tts", "whisper", "dall-e", "moderation", "image")


async def list_available_models(provider: str, api_key: str, timeout: float = 15.0) -> list[str]:
    """Queries the provider directly for which models this specific key can
    actually use, rather than relying on PROVIDER_MODELS' curated (and
    inevitably staleness-prone) defaults. Used by the Settings page's
    "Refresh from account" button — the curated list stays as the default
    shown before this has ever been run, since it needs a real key to call."""
    if not api_key:
        raise AIServiceError(f"{provider} API key is not configured")

    try:
        if provider in ("openai", "grok"):
            url = OPENAI_URL.replace("/chat/completions", "/models") if provider == "openai" else GROK_URL.replace(
                "/chat/completions", "/models"
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
                resp.raise_for_status()
                data = resp.json()
            ids = [m["id"] for m in data.get("data", [])]
            return sorted(m for m in ids if not any(marker in m.lower() for marker in _NON_CHAT_MARKERS))

        if provider == "claude":
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": CLAUDE_API_VERSION},
                )
                resp.raise_for_status()
                data = resp.json()
            # Anthropic's /v1/models list is all text/chat models already —
            # no mixed-in embedding/audio/image types to filter out here.
            models = data.get("data", [])
            models.sort(key=lambda m: m.get("created_at", ""), reverse=True)
            return [m["id"] for m in models]

        if provider == "gemini":
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
            return sorted(
                m["name"].removeprefix("models/")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            )
    except httpx.HTTPStatusError as e:
        raise AIServiceError(f"{provider} API error ({e.response.status_code}): {e.response.text[:300]}") from e
    except httpx.HTTPError as e:
        raise AIServiceError(f"Network error reaching {provider}: {e}") from e

    raise AIServiceError(f"Unknown AI provider: {provider!r}")
