# Monitoring & Alerting — Rs. 0 stack

Failures on `https://smartgarbage.onrender.com` surface on their own. You do
not need to check anything: **GitHub emails you** when a probe fails and when
an issue is opened, commented, or closed (watch the repo, or rely on default
participation notifications — you are the repo owner).

Three free layers, no paid service, no external accounts:

| Layer | Detects | Where | Alert arrives as |
|---|---|---|---|
| **Uptime probe** | Site down, `/health` unhealthy, DB check failing, queue starvation | `.github/workflows/uptime.yml` (GitHub Actions, cron) | GitHub issue `[uptime] site is DOWN — <timestamp>` + email |
| **Runtime errors (500s)** | Unhandled exceptions inside requests (invisible to any external probe) | `app/alerting.py`, wired into the 500 handler | GitHub issue `[500] <type> — <day>` + email |
| **Sentry (optional)** | Same as above, plus perf/tracebacks with full context | `SENTRY_DSN` env var — already wired in `app/__init__.py` | Sentry dashboard/emails |

Both GitHub-issue layers are **fail-soft**: an alerting outage can never take
the site down or change what a visitor sees.

## 1. Uptime probe (GitHub Actions)

`.github/workflows/uptime.yml` probes `GET /health` every 15 minutes
(3 attempts, 45 s timeout each) and classifies the result:

- **healthy** — HTTP 200, `status: healthy`, `checks.database.status: pass`,
  and no queue starvation → any open `[uptime]` issue gets an auto-resolve
  comment and is closed.
- **degraded** — HTTP 200 but `status != healthy` / DB failing, **or**
  `queue.backend: redis` with `queue.workers: 0` (jobs queued but never
  consumed — OTP mail, status alerts and receipts silently vanish; the state
  PR #10 made visible). Opens `[uptime] site is DOWN — <timestamp>` with the
  `degraded` label.
- **down** — unreachable, non-200, or invalid JSON after 3 attempts. Opens the
  same issue without the label.

Consecutive bad probes **comment on the same issue** instead of opening
duplicates; the title pins the outage window. Healthy probe auto-closes by
the `uptime-alert` label.

### Honest limitations (read once, then forget)

- **GitHub's scheduler is loose.** Free-tier `schedule` events on low-activity
  repos are delayed — the 5-minute keepalive workflow verifiably fires about
  hourly, so treat this probe as "every 15–60 minutes", not exactly 15. The
  exact-cadence path is the Supabase pg_cron job (`sg-keepalive-render`,
  every 5 min, confirmed live in the database) — but that one is silent: it
  keeps the site warm and does not alert. This workflow is the alerting path.
- **The probe only sees what an anonymous visitor sees.** A bug that 500s on
  one logged-in page (or one specific request) never trips it — that is what
  layer 2 is for.
- **A "still failing" probe within the first minutes of recovery** can close
  the alert before a bad probe reopens it; the auto-resolve comment notes the
  grace window. Missed alerts from scheduler gaps self-heal on the next run.

## 2. Runtime-error alerts (`app/alerting.py`)

The 500 handler in `app/__init__.py` calls `app.alerting.report_exception()`,
which files or updates a GitHub issue (`runtime-error` label) with the
exception type, path, timestamp, and a pointer to the full traceback in the
Render logs.

Deduplicated per **outage window** = exception type + UTC day: the first
occurrence opens the issue, later occurrences add a `🔁 Recurred` comment.
The uptime workflow never closes these — resolve manually after a fix ships.

### Enabling it (user action, on Render)

The reporter is **off by default** so local dev, tests, and CI never file
issues. To enable in production, add to the Render web service environment:

```
ALERT_ISSUES=1
ALERT_GITHUB_TOKEN=github_pat_…   (free PAT — see below)
```

**Minting the PAT (one time, ~2 minutes, free):** GitHub → Settings →
Developer settings → Fine-grained tokens → Generate new token → Repository
access: *only* `SmartgarbageCSP` → Permissions: **Issues: Read and write**.
Paste it as `ALERT_GITHUB_TOKEN` on Render and deploy.

Locally no token is needed: when `ALERT_GITHUB_TOKEN` is unset, the reporter
falls back to the machine's stored `https://github.com` git credential (the
same one used to open PRs). On Render only the env var exists, which is why
the PAT is required there. `ALERT_GITHUB_REPO` (optional) overrides the
target repo if you ever want issues filed elsewhere.

### Optional: Sentry instead / as well

`sentry-sdk` is already in `requirements.txt` and `app/__init__.py` wires it
when `SENTRY_DSN` is set. Note: the existing init uses `auto_setup=False`,
which means Flask's own error handler path is not instrumented — with Sentry
you get request/traceback context for errors that are captured, but this
project's 500 handler still needs the `report_exception` call to know a 500
happened. Sentry's free tier (5k errors/month) is the richer option if you
ever outgrow GitHub-issue alerting; it requires creating a Sentry account,
so it is optional, not part of the default stack.

## 3. What each failure looks like

| Symptom | Which layer fires | First thing to check |
|---|---|---|
| Issue `[uptime] site is DOWN` | Uptime probe | Render dashboard → web service → Events/Logs; is the service crashed or paused? |
| Issue `[uptime] …` + `degraded` label, body says DB failing | Uptime probe | Supabase paused? (free tier pauses after 7 days idle — pg_cron keepalive prevents this) |
| Issue `[uptime] …` + `degraded` label, body says queue starvation | Uptime probe | `REDIS_URL` set but no worker consuming → enable the in-process worker (`wsgi.py`) or run `worker.py` |
| Issue `[500] <ExceptionName> …` | `app/alerting.py` | Render logs at the timestamp in the issue body |

## 4. Testing the wiring (no waiting for a real outage)

```bash
# Uptime probe, happy path (should classify healthy and resolve nothing):
#   GitHub → Actions → "Uptime monitor" → Run workflow (workflow_dispatch)

# Local: the reporter is a no-op without ALERT_ISSUES:
python -c "from app.alerting import report_exception; report_exception(ValueError('x'), '/x')"

# Local: with ALERT_ISSUES=1 and a repo override, it files into a scratch
# repo without touching production issues:
ALERT_ISSUES=1 ALERT_GITHUB_REPO=<you>/scratch python -c \
  "from app.alerting import report_exception; report_exception(ValueError('probe'), '/probe')"
# delete the probe issue afterwards
```

CI never has `ALERT_ISSUES` set, so the full test suite proves the no-op path
(see `tests/test_features.py` for the regression tests).
