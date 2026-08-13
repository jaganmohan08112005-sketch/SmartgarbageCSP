-- =====================================================================
-- SmartGarbage — Supabase keep-alive
-- (Cloudflare-free replacement for keepalive/worker.js + wrangler.toml)
-- =====================================================================
--
-- WHY: Render free web services spin down after 15 min of idle traffic
-- (and while spun down, /robots.txt auto-responds "disallow all" so
-- crawlers never reach the real file), and Supabase free projects pause
-- after 7 days without activity. This ONE job keeps BOTH warm:
--
--   * every 5 minutes pg_net fires net.http_get() at Render's /health
--     -> Render wakes on the inbound request (spin-up ~1 min; the ping
--        itself may time out at pg_net's 2s default timeout — that's fine, the
--        instance is now up and the next ping is a normal 200);
--   * /health runs `SELECT 1` against THIS Supabase Postgres
--     -> the external DB connection counts as activity, so the project
--        never enters the 7-day pause window.
--
-- It is fully integrated with technology the project already uses
-- (Supabase Postgres) — no Cloudflare account or zone required.
--
-- HOW TO RUN: Supabase Dashboard → SQL Editor → paste → Run
-- (the SQL editor runs as the postgres role, so cron.schedule is allowed).
-- Idempotent: safe to re-run after every deploy.
--
-- COST / LIMITS:
--   * pg_cron + pg_net are included on the Supabase free tier.
--   * Render free grants 750 instance-hours/month. A strict 5-minute
--     keep-alive keeps the instance running ~720 h/month — just under
--     the cap, so the free instance never suspends. If you want margin,
--     the GitHub Actions keepalive (fires ~hourly, enough to beat the
--     15-min sleep) already covers the gap, or upgrade Render to Starter
--     ($7/mo) which removes spin-down entirely and adds edge caching.

-- 1. Enable the two extensions (no-ops when already enabled)
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 2. (Re)create the job — unschedule first so re-runs never duplicate
select cron.unschedule('sg-keepalive-render')
where exists (select 1 from cron.job where jobname = 'sg-keepalive-render');

select cron.schedule(
    'sg-keepalive-render',   -- unique job name (visible in cron.job)
    '*/5 * * * *',           -- every 5 minutes -> 288 runs/day
    $$
    select net.http_get(
        'https://smartgarbage.onrender.com/health',
        headers := '{"user-agent": "sg-keepalive-pgcron"}'::jsonb
    );
    $$
);

-- 3. Verify the schedule
select jobname, schedule, command
from cron.job
where jobname = 'sg-keepalive-render';

-- Monitor runs (optional):
--   select status, start_time, return_message
--   from cron.job_run_details
--   where jobname = 'sg-keepalive-render'
--   order by start_time desc
--   limit 5;
-- (job_run_details is retained for 24h; the dashboard "Integrations → Cron"
--  UI also shows run history without SQL.)
