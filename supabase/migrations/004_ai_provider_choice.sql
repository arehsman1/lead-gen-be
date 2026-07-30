-- Run this in the Supabase SQL editor on an already-deployed database.
-- schema.sql now includes these columns for fresh installs; this
-- migration brings an existing DB in line with it.

alter table settings
  add column if not exists claude_api_key text,
  add column if not exists gemini_api_key text,
  add column if not exists grok_api_key text,
  add column if not exists ai_provider text not null default 'openai',
  add column if not exists ai_model text;
