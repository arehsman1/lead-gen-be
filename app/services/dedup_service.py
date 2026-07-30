"""
Merges business records found by SerpApi and Apify for the same search.

Dedup key priority (per spec): Google Maps Place ID > Google Maps URL >
business name + address. Two records are the same business if they match on
ANY of those three, in that priority order.

Merge priority (per spec): when a business was found by both APIs, SerpApi
is the source of truth for rating, review count, phone, and other
overlapping fields. Apify fields are used only to fill in gaps SerpApi left
empty.
"""

from dataclasses import dataclass, field
from typing import Literal

RawSource = Literal["serpapi", "apify"]


@dataclass
class RawBusiness:
    """Normalized shape a scraper adapter must produce before merging."""

    source: RawSource
    name: str
    industry: str | None = None
    location: str | None = None
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    google_maps_url: str | None = None
    google_place_id: str | None = None
    rating: float | None = None
    review_count: int | None = None
    raw_data: dict | None = None  # the original, un-normalized API response item


@dataclass
class MergedBusiness:
    name: str
    industry: str | None
    location: str | None
    website: str | None
    phone: str | None
    address: str | None
    google_maps_url: str | None
    google_place_id: str | None
    rating: float | None
    review_count: int | None
    source_api: Literal["serpapi", "apify", "both"]
    matched_on: list[str] = field(default_factory=list)
    raw_serpapi_data: dict | None = None
    raw_apify_data: dict | None = None


def _normalize(s: str | None) -> str:
    return (s or "").strip().lower()


def _same_business(a: RawBusiness, b: RawBusiness) -> str | None:
    """Returns the matched key name if a and b are the same business, else None."""
    if a.google_place_id and b.google_place_id and a.google_place_id == b.google_place_id:
        return "place_id"
    if a.google_maps_url and b.google_maps_url and a.google_maps_url == b.google_maps_url:
        return "maps_url"
    if (
        _normalize(a.name)
        and _normalize(a.address)
        and _normalize(a.name) == _normalize(b.name)
        and _normalize(a.address) == _normalize(b.address)
    ):
        return "name_address"
    return None


def _merge_pair(serp: RawBusiness | None, apify: RawBusiness | None, matched_on: list[str]) -> MergedBusiness:
    if serp and apify:
        source_api: Literal["serpapi", "apify", "both"] = "both"
        primary, secondary = serp, apify
    elif serp:
        source_api = "serpapi"
        primary, secondary = serp, None
    else:
        assert apify is not None
        source_api = "apify"
        primary, secondary = apify, None

    def pick(field_name: str):
        primary_val = getattr(primary, field_name)
        if primary_val not in (None, ""):
            return primary_val
        if secondary is not None:
            return getattr(secondary, field_name)
        return None

    return MergedBusiness(
        name=pick("name"),
        industry=pick("industry"),
        location=pick("location"),
        website=pick("website"),
        phone=pick("phone"),
        address=pick("address"),
        google_maps_url=pick("google_maps_url"),
        google_place_id=pick("google_place_id"),
        rating=pick("rating"),
        review_count=pick("review_count"),
        source_api=source_api,
        matched_on=matched_on,
        raw_serpapi_data=serp.raw_data if serp else None,
        raw_apify_data=apify.raw_data if apify else None,
    )


def merge_results(
    serpapi_results: list[RawBusiness],
    apify_results: list[RawBusiness],
) -> list[MergedBusiness]:
    """
    Deduplicates and merges two result sets. SerpApi is always treated as
    primary for overlapping fields, per spec, regardless of call order.
    """
    unmatched_apify = list(apify_results)
    merged: list[MergedBusiness] = []

    for serp_biz in serpapi_results:
        match_idx = None
        matched_on = None
        for i, apify_biz in enumerate(unmatched_apify):
            key = _same_business(serp_biz, apify_biz)
            if key:
                match_idx = i
                matched_on = key
                break

        if match_idx is not None:
            apify_biz = unmatched_apify.pop(match_idx)
            merged.append(_merge_pair(serp_biz, apify_biz, matched_on=[matched_on]))
        else:
            merged.append(_merge_pair(serp_biz, None, matched_on=[]))

    # Anything left in apify_results had no SerpApi match — keep as apify-only.
    for apify_biz in unmatched_apify:
        merged.append(_merge_pair(None, apify_biz, matched_on=[]))

    return merged
