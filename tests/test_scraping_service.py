from app.services.scraping_service import build_apify_payload, build_serpapi_params


def test_build_serpapi_params_includes_required_type():
    # Missing `type` was the primary cause of a real 400 Bad Request from
    # SerpApi in production — `type` is a required parameter for the
    # google_maps engine per https://serpapi.com/google-maps-api.
    params = build_serpapi_params("plumber", "Arkansas, United States", "fake-key")
    assert params["type"] == "search"


def test_build_serpapi_params_location_has_companion_zoom():
    # SerpApi's docs: `location` "should be used with z or m parameter" —
    # using it alone was the second cause of the same 400.
    params = build_serpapi_params("plumber", "Arkansas, United States", "fake-key")
    assert "z" in params or "m" in params


def test_build_serpapi_params_does_not_mix_location_with_ll():
    # location "can't be used with ll, lat or lon parameters" per the docs.
    params = build_serpapi_params("plumber", "Arkansas, United States", "fake-key")
    assert "ll" not in params
    assert "lat" not in params
    assert "lon" not in params


def test_build_serpapi_params_passes_through_query_and_key():
    params = build_serpapi_params("hvac repair", "Texas, United States", "secret-key-123")
    assert params["engine"] == "google_maps"
    assert params["q"] == "hvac repair"
    assert params["location"] == "Texas, United States"
    assert params["api_key"] == "secret-key-123"


def test_build_apify_payload_basic_fields():
    payload = build_apify_payload("hvac repair", "Texas, United States")
    assert payload["searchStringsArray"] == ["hvac repair"]
    assert payload["locationQuery"] == "Texas, United States"
    assert payload["maxCrawledPlaces"] == 50


def test_build_apify_payload_respects_custom_max_places():
    payload = build_apify_payload("plumber", "Arkansas, United States", max_places=100)
    assert payload["maxCrawledPlaces"] == 100
