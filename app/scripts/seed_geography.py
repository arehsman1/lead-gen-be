"""
One-time seed for the countries/states reference tables, using pycountry's
bundled ISO 3166-1 (countries) and ISO 3166-2 (subdivisions/states) data —
no GeoNames download, no external API calls, no network access at all once
pycountry itself is installed. Run once after applying
supabase/migrations/002_countries_and_states.sql (or a fresh schema.sql):

    python -m app.scripts.seed_geography

Safe to re-run — upserts on the unique constraints (countries.iso2,
states (country_id, state_code)) rather than blindly inserting, so running
it again just no-ops instead of creating duplicates.
"""

import sys

try:
    import pycountry
except ImportError:
    print("pycountry is not installed. Run: pip install pycountry")
    sys.exit(1)

from app.core.supabase import get_supabase


def build_country_rows() -> list[dict]:
    return [{"name": c.name, "iso2": c.alpha_2, "iso3": c.alpha_3} for c in pycountry.countries]


def build_state_rows(id_by_iso2: dict[str, str]) -> tuple[list[dict], int]:
    """Returns (rows, skipped_count). skipped_count should always be 0 in
    practice — pycountry's own subdivision codes are always prefixed with
    one of its own country codes — but it's cheap to guard rather than
    assume, and the count doubles as a sanity check when this runs."""
    states = []
    skipped = 0
    for sub in pycountry.subdivisions:
        country_iso2 = sub.code.split("-")[0]
        country_id = id_by_iso2.get(country_iso2)
        if not country_id:
            skipped += 1
            continue
        states.append({"country_id": country_id, "name": sub.name, "state_code": sub.code})
    return states, skipped


def main():
    db = get_supabase()

    countries = build_country_rows()
    db.table("countries").upsert(countries, on_conflict="iso2").execute()
    print(f"Seeded {len(countries)} countries.")

    country_rows = db.table("countries").select("id, iso2").execute().data
    id_by_iso2 = {row["iso2"]: row["id"] for row in country_rows}

    states, skipped = build_state_rows(id_by_iso2)

    # Batch to stay well under Supabase/PostgREST's request size limits —
    # ~5,000 subdivisions worldwide is small, but this keeps it safe if
    # pycountry's dataset grows.
    batch_size = 500
    for i in range(0, len(states), batch_size):
        batch = states[i : i + batch_size]
        db.table("states").upsert(batch, on_conflict="country_id,state_code").execute()

    print(f"Seeded {len(states)} states/provinces across {len(country_rows)} countries.")
    if skipped:
        print(f"Skipped {skipped} subdivisions with no matching country (unexpected — worth checking).")


if __name__ == "__main__":
    main()
