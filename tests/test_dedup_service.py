from app.services.dedup_service import RawBusiness, merge_results


def test_no_overlap_keeps_both_sources_separate():
    serp = [RawBusiness(source="serpapi", name="A Plumbing", address="1 Main St")]
    apify = [RawBusiness(source="apify", name="B Dental", address="2 Oak St")]

    merged = merge_results(serp, apify)

    assert len(merged) == 2
    sources = {m.source_api for m in merged}
    assert sources == {"serpapi", "apify"}


def test_matches_on_place_id_and_marks_both():
    serp = [RawBusiness(source="serpapi", name="A Plumbing", google_place_id="P1", rating=4.5, review_count=20)]
    apify = [RawBusiness(source="apify", name="A Plumbing LLC", google_place_id="P1", phone="+1234")]

    merged = merge_results(serp, apify)

    assert len(merged) == 1
    assert merged[0].source_api == "both"
    assert merged[0].matched_on == ["place_id"]


def test_matches_on_maps_url_when_no_place_id():
    serp = [RawBusiness(source="serpapi", name="A Plumbing", google_maps_url="https://maps/x")]
    apify = [RawBusiness(source="apify", name="A Plumbing", google_maps_url="https://maps/x")]

    merged = merge_results(serp, apify)

    assert len(merged) == 1
    assert merged[0].matched_on == ["maps_url"]


def test_matches_on_name_and_address_as_last_resort():
    serp = [RawBusiness(source="serpapi", name="A Plumbing", address="1 Main St, Lokoja")]
    apify = [RawBusiness(source="apify", name="a plumbing", address="1 MAIN ST, LOKOJA")]

    merged = merge_results(serp, apify)

    assert len(merged) == 1
    assert merged[0].matched_on == ["name_address"]


def test_serpapi_wins_for_overlapping_fields():
    serp = [
        RawBusiness(
            source="serpapi",
            name="A Plumbing",
            google_place_id="P1",
            rating=4.8,
            review_count=50,
            phone="+1-serp",
        )
    ]
    apify = [
        RawBusiness(
            source="apify",
            name="A Plumbing",
            google_place_id="P1",
            rating=3.0,
            review_count=5,
            phone="+1-apify",
            website="https://a-plumbing.example",
        )
    ]

    merged = merge_results(serp, apify)
    result = merged[0]

    # SerpApi is source of truth for overlapping fields...
    assert result.rating == 4.8
    assert result.review_count == 50
    assert result.phone == "+1-serp"
    # ...but Apify fills in fields SerpApi didn't have.
    assert result.website == "https://a-plumbing.example"


def test_apify_only_result_is_kept():
    serp: list[RawBusiness] = []
    apify = [RawBusiness(source="apify", name="Solo Apify Biz", address="9 Side St")]

    merged = merge_results(serp, apify)

    assert len(merged) == 1
    assert merged[0].source_api == "apify"


def test_multiple_businesses_dedupe_independently():
    serp = [
        RawBusiness(source="serpapi", name="A Plumbing", google_place_id="P1"),
        RawBusiness(source="serpapi", name="C Roofing", google_place_id="P2"),
    ]
    apify = [
        RawBusiness(source="apify", name="A Plumbing", google_place_id="P1"),
        RawBusiness(source="apify", name="D Electric", google_place_id="P3"),
    ]

    merged = merge_results(serp, apify)

    assert len(merged) == 3
    names = {m.name for m in merged}
    assert names == {"A Plumbing", "C Roofing", "D Electric"}
