from app.scripts.seed_geography import build_country_rows, build_state_rows


def test_build_country_rows_includes_known_countries():
    rows = build_country_rows()
    by_iso2 = {r["iso2"]: r for r in rows}
    assert by_iso2["US"]["name"] == "United States"
    assert by_iso2["US"]["iso3"] == "USA"
    assert by_iso2["CA"]["iso3"] == "CAN"
    # Sanity check on scale — pycountry's ISO 3166-1 list is ~249 entries;
    # this isn't pinned to an exact number since it can change with the
    # pycountry version, just checked as "roughly right, not empty/tiny".
    assert len(rows) > 200


def test_build_country_rows_have_unique_iso2():
    rows = build_country_rows()
    iso2s = [r["iso2"] for r in rows]
    assert len(iso2s) == len(set(iso2s))


def test_build_state_rows_maps_to_correct_country():
    country_rows = build_country_rows()
    id_by_iso2 = {r["iso2"]: f"fake-id-{r['iso2']}" for r in country_rows}

    states, skipped = build_state_rows(id_by_iso2)

    assert skipped == 0
    us_states = [s for s in states if s["country_id"] == "fake-id-US"]
    us_state_names = {s["name"] for s in us_states}
    assert "Texas" in us_state_names
    assert "California" in us_state_names
    # US has 50 states + DC + 5 territories = 56, but pycountry may list a
    # slightly different count depending on version — just check it's in
    # a sane range rather than pinning an exact number.
    assert 50 <= len(us_states) <= 60


def test_build_state_rows_skips_unmapped_countries():
    # Deliberately omit every country from the id map — every subdivision
    # should be skipped rather than crash on a missing lookup.
    states, skipped = build_state_rows({})
    assert states == []
    assert skipped > 0


def test_build_state_rows_state_codes_are_unique_per_country():
    country_rows = build_country_rows()
    id_by_iso2 = {r["iso2"]: f"fake-id-{r['iso2']}" for r in country_rows}
    states, _ = build_state_rows(id_by_iso2)

    seen = set()
    for s in states:
        key = (s["country_id"], s["state_code"])
        assert key not in seen, f"duplicate state_code within country: {key}"
        seen.add(key)
