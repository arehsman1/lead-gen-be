"""
Adapters that call SerpApi and Apify and normalize their responses into
RawBusiness records the dedup_service can merge. Requires real API keys in
Settings — with no key configured, each function raises rather than
silently returning empty results, so a misconfigured source fails loudly
instead of just looking like "no results."
"""

import asyncio

import httpx

from app.services.dedup_service import RawBusiness

SERPAPI_URL = "https://serpapi.com/search"
APIFY_BASE_URL = "https://api.apify.com/v2"

# Google Maps scraper actor — swap for whichever Apify actor the account uses.
DEFAULT_APIFY_ACTOR = "compass~crawler-google-places"


class ScraperConfigError(RuntimeError):
    pass


def build_serpapi_params(keyword: str, location: str, api_key: str) -> dict:
    """Pure param-building, split out from search_serpapi so it's testable
    without a live network call. Two real bugs lived here before this was
    fixed, both confirmed against SerpApi's current docs
    (https://serpapi.com/google-maps-api) rather than assumed:

    1. `type` is a required parameter for this engine and was missing
       entirely — every request was rejected with a 400 regardless of
       anything else.
    2. `location` is a valid parameter, but SerpApi's docs say it "should
       be used with z or m parameter" (zoom level or map height) — used
       alone, without either, it was also rejected. `z=6` is a broad
       enough zoom to cover a whole state/province rather than a single
       city, matching this app's country+state (not city-level) search
       granularity.
    """
    return {
        "engine": "google_maps",
        "type": "search",
        "q": keyword,
        "location": location,
        "z": "6",
        "api_key": api_key,
    }


async def search_serpapi(keyword: str, location: str, api_key: str, timeout: float = 15.0) -> list[RawBusiness]:
    if not api_key:
        raise ScraperConfigError("SerpApi key is not configured")

    params = build_serpapi_params(keyword, location, api_key)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(SERPAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for item in data.get("local_results", []):
        results.append(
            RawBusiness(
                source="serpapi",
                name=item.get("title", ""),
                website=item.get("website"),
                phone=item.get("phone"),
                address=item.get("address"),
                google_maps_url=item.get("place_id_search") or item.get("link"),
                google_place_id=item.get("place_id"),
                rating=item.get("rating"),
                review_count=item.get("reviews"),
                raw_data=item,
            )
        )
    return results


def build_apify_payload(keyword: str, location: str, max_places: int = 50) -> dict:
    """Pure, testable without a live network call."""
    return {
        "searchStringsArray": [keyword],
        "locationQuery": location,
        "maxCrawledPlaces": max_places,
    }


async def search_apify(
    keyword: str,
    location: str,
    api_token: str,
    actor_id: str = DEFAULT_APIFY_ACTOR,
    poll_interval: float = 5.0,
    max_wait: float = 600.0,
) -> list[RawBusiness]:
    """
    Starts an Apify actor run asynchronously and polls until it finishes,
    instead of the previous approach of calling the run-sync-get-dataset-
    items endpoint and waiting on one open HTTP connection.

    That endpoint has a hard ~300s server-side cap on Apify's side — and
    this code's own client-side timeout was set even shorter, at 60s.
    Critically, when that cap is hit, Apify does NOT cancel the actor run
    — it keeps running and completes independently, saving its results to
    a dataset. This code just never came back to collect them: the run-
    sync request timed out, the exception propagated, and the successful
    results sat in Apify's dataset unread. That's the exact bug reported —
    "the job run and the leads was saved on apify but I didn't get them in
    my app." Starting the run separately from polling its status removes
    the artificial cap entirely; max_wait here is this app's own choice
    (10 minutes by default), not a limit imposed by Apify's sync endpoint.
    """
    if not api_token:
        raise ScraperConfigError("Apify token is not configured")

    payload = build_apify_payload(keyword, location)

    async with httpx.AsyncClient(timeout=30.0) as client:
        start_resp = await client.post(
            f"{APIFY_BASE_URL}/acts/{actor_id}/runs",
            params={"token": api_token},
            json=payload,
        )
        start_resp.raise_for_status()
        run = start_resp.json()["data"]
        run_id = run["id"]

        elapsed = 0.0
        status = run["status"]
        while status in ("READY", "RUNNING") and elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            status_resp = await client.get(
                f"{APIFY_BASE_URL}/actor-runs/{run_id}", params={"token": api_token}
            )
            status_resp.raise_for_status()
            run = status_resp.json()["data"]
            status = run["status"]

        if status != "SUCCEEDED":
            raise RuntimeError(
                f"Apify run {run_id} did not complete successfully "
                f"(status: {status}) after waiting {elapsed:.0f}s. "
                f"Check the run in your Apify console for details."
            )

        dataset_id = run["defaultDatasetId"]
        items_resp = await client.get(
            f"{APIFY_BASE_URL}/datasets/{dataset_id}/items", params={"token": api_token}
        )
        items_resp.raise_for_status()
        items = items_resp.json()

    results = []
    for item in items:
        results.append(
            RawBusiness(
                source="apify",
                name=item.get("title", ""),
                website=item.get("website"),
                phone=item.get("phone"),
                address=item.get("address"),
                google_maps_url=item.get("url"),
                google_place_id=item.get("placeId"),
                rating=item.get("totalScore"),
                review_count=item.get("reviewsCount"),
                raw_data=item,
            )
        )
    return results
