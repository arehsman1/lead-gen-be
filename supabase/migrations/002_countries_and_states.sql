-- Run this in the Supabase SQL editor on an already-deployed database.
-- schema.sql now includes these tables for fresh installs; this migration
-- brings an existing DB in line with it. After running this, seed the
-- data with: python -m app.scripts.seed_geography

create table if not exists countries (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  iso2 text not null unique,
  iso3 text not null unique
);

create index if not exists idx_countries_iso2 on countries(iso2);

create table if not exists states (
  id uuid primary key default gen_random_uuid(),
  country_id uuid not null references countries(id) on delete cascade,
  name text not null,
  state_code text not null,
  unique (country_id, state_code)
);

create index if not exists idx_states_country_id on states(country_id);
create index if not exists idx_states_state_code on states(state_code);
