-- Run this in the Supabase SQL editor on an already-deployed database.
-- schema.sql now includes this table for fresh installs; this migration
-- brings an existing DB in line with it.

do $$ begin
  create type api_key_provider as enum ('serpapi', 'apify');
exception when duplicate_object then null;
end $$;

create table if not exists saved_api_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  provider api_key_provider not null,
  name text not null,
  key_value text not null,
  created_at timestamptz not null default now(),
  unique (user_id, provider, name)
);

create index if not exists idx_saved_api_keys_user_provider on saved_api_keys(user_id, provider);

alter table saved_api_keys enable row level security;

do $$ begin
  create policy "own saved api keys" on saved_api_keys for all
    using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null;
end $$;
