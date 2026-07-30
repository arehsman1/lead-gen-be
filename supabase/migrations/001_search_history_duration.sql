-- Run this in the Supabase SQL editor on an already-deployed database.
-- schema.sql is only for a fresh install — it now includes these columns,
-- so this migration exists purely to bring an existing DB in line with it.

alter table search_history
  add column if not exists error_detail text,
  add column if not exists started_at timestamptz not null default now(),
  add column if not exists finished_at timestamptz;

-- Backfill: for any row already sitting in 'running' from before this fix
-- (the exact "stuck on pending" bug this migration exists to fix), mark it
-- failed so it stops showing as perpetually in-progress. Anything genuinely
-- still running will just get re-run by the user.
update search_history
set status = 'failed', finished_at = now(), error_detail = 'Marked failed by migration 001 — was stuck in "running" from before background-task error handling was fixed.'
where status = 'running';
