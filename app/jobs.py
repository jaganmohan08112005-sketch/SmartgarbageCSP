"""Background job queue (RQ over the already-required Redis).

Long-running / externally-blocking work — Twilio SMS/WhatsApp sends, webhook
delivery, PDF/CSV export generation and PAYT dunning — is enqueued here so
request handlers (bin_telemetry, complaint resolution, login) never block on
network I/O.

When REDIS_URL is not configured (local dev, pytest) the queue degrades
gracefully: enqueue() runs the job inline in the calling process, preserving
existing behaviour without a broker.
"""
import os
import json
import base64
import functools
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

import structlog

logger = structlog.get_logger("smartgarbage.jobs")

# Lazily-built singletons (mirrors the Redis cache client pattern in app/routes/).
_QUEUE = None
_QUEUE_TRIED = False
_REDIS = None
_REDIS_TRIED = False
_INLINE_EXPORTS = {}  # job_id -> artifact record (no-Redis fallback)


def _redis():
    global _REDIS, _REDIS_TRIED
    if _REDIS_TRIED:
        return _REDIS
    _REDIS_TRIED = True
    url = os.environ.get('REDIS_URL')
    if not url:
        return None
    try:
        import redis
        _REDIS = redis.Redis.from_url(url, socket_timeout=2, decode_responses=False)
    except Exception as e:
        logger.warning("jobs_redis_unavailable", error=str(e))
        _REDIS = None
    return _REDIS


def _get_queue():
    """Lazily build the shared RQ Queue bound to REDIS_URL (None when unset)."""
    global _QUEUE, _QUEUE_TRIED
    if _QUEUE_TRIED:
        return _QUEUE
    _QUEUE_TRIED = True
    url = os.environ.get('REDIS_URL')
    if not url:
        return None
    try:
        import redis
        from rq import Queue
        _QUEUE = Queue('smartgarbage', connection=redis.Redis.from_url(url, socket_timeout=2))
    except Exception as e:
        logger.warning("rq_queue_unavailable", error=str(e))
        _QUEUE = None
    return _QUEUE


# ──────────────────────────────────────────────
# PER-JOB RETRY POLICIES (exponential backoff)
# ──────────────────────────────────────────────
# Job function name -> (max_retries, backoff_seconds). RQ re-enqueues the job
# after each failure with the next interval from the list (rq.Retry). Jobs not
# listed here run with RQ's default (no automatic retry).
JOB_RETRY_POLICIES = {
    'send_sms_job': (3, [30, 60, 120]),                 # Twilio hiccups: 30s, 1m, 2m
    'send_email_job': (3, [30, 60, 120]),
    'send_otp_job': (3, [30, 60, 120]),
    'notify_status_change_job': (3, [30, 60, 120]),
    'send_tracking_link_job': (3, [30, 60, 120]),       # complaint tracking link SMS
    'dispatch_webhooks_job': (4, [10, 30, 60, 120]),    # external webhooks: fast first retries
    'payt_reminder_job': (3, [60, 300, 900]),           # dunning SMS: 1m, 5m, 15m
    'generate_export_job': (2, [30, 120]),              # heavy report builds: 30s, 2m
    'dunning_job': (1, [300]),                          # periodic sweep: single 5m retry
    'sweep_failed_jobs_alerts_job': (1, [300]),         # dead-letter alert sweep: single 5m retry
    'payt_receipt_job': (2, [60, 300]),                 # receipt PDF + SMTP: 1m, 5m
    'maintenance_job': (1, [300]),                      # sensor/decomp sweep: single 5m retry
    'maintenance_overdue_escalation_job': (1, [300]),   # overdue work-order escalation: single 5m retry
    'payt_reconciliation_job': (1, [300]),              # billing reconcile: single 5m retry
    'model_retraining_job': (1, [600]),                 # ML retrain: single 10m retry
    'photo_gate_canary_job': (1, [120]),                # gate canary: single 2m retry before next sweep
}


def _retry_for(fn):
    """Build an rq.Retry for a job function per its declared policy.

    Returns None when rq isn't installed (local dev / pytest) or the job has no
    policy — callers then enqueue without retries."""
    policy = JOB_RETRY_POLICIES.get(getattr(fn, '__name__', ''))
    if policy is None:
        return None
    max_retries, intervals = policy
    try:
        from rq import Retry
        return Retry(max=max_retries, interval=list(intervals))
    except Exception:
        return None


def worker_health():
    """Whether queued jobs are actually being CONSUMED — not just brokered.

    "REDIS_URL is set" does not mean jobs run: RQ only executes what a worker
    polls for. With REDIS_URL set, RQ_IN_PROCESS_WORKER=false and no worker
    service, every send is written into Redis and never delivered — mail/SMS
    vanish silently while the site looks perfectly healthy. This reports the
    live worker count so operators can see that state. RQ registers workers via
    heartbeats, so the in-process thread started by wsgi.py shows up here too.

    Returns {'backend', 'workers', 'starved'}: workers is None when the answer
    is unknown (no Redis, or rq unavailable) — unknown never cries wolf.
    """
    r = _redis()
    if r is None:
        return {'backend': 'inline', 'workers': None, 'starved': False}
    try:
        from rq import Worker
        workers = len(Worker.all(connection=r))
    except Exception as e:
        logger.warning("worker_health_error", error=str(e))
        return {'backend': 'redis', 'workers': None, 'starved': False}
    return {'backend': 'redis', 'workers': workers, 'starved': workers == 0}


def enqueue(fn, *args, retry=None, **kwargs):
    """Run fn through RQ when Redis is configured; otherwise run it inline.

    Applies the job's declared JOB_RETRY_POLICIES backoff automatically unless
    retry is given explicitly (pass retry=False to disable). Returns the RQ Job
    when queued, or fn's return value when executed inline (so callers can
    branch on whether the work ran synchronously)."""
    q = _get_queue()
    if q is not None:
        if retry is None:
            retry = _retry_for(fn)
        # rq.Retry objects are truthy; None (no policy) and False (explicit
        # opt-out) both mean "enqueue without retries".
        if retry:
            return q.enqueue(fn, *args, retry=retry, **kwargs)
        return q.enqueue(fn, *args, **kwargs)
    return fn(*args, **kwargs)


# ──────────────────────────────────────────────
# OBSERVABILITY: Prometheus-style job counters
# ──────────────────────────────────────────────
# Every job run bumps a monotonic counter keyed by (function, outcome) and
# accumulates wall-clock seconds. With Redis the counters live in shared keys
# (`sg:metric:<func>:<suffix>`) so a scrape from any process sees every worker;
# without a broker they accumulate in this in-process dict (tests, local dev).
_METRICS = {}  # 'func:outcome' -> count, 'func:duration_s' -> seconds


def record_outcome(func_name, outcome, seconds):
    """Increment the counter for a finished job run and add its duration."""
    r = _redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incr(f"sg:metric:{func_name}:{outcome}")
            pipe.incrbyfloat(f"sg:metric:{func_name}:duration_s", seconds)
            pipe.execute()
        except Exception:
            pass  # metrics must never break the job itself
        return
    key = f"{func_name}:{outcome}"
    _METRICS[key] = _METRICS.get(key, 0) + 1
    dkey = f"{func_name}:duration_s"
    _METRICS[dkey] = _METRICS.get(dkey, 0.0) + seconds


def record_retry(func_name):
    """Count one retry attempt for a job function.

    Incremented by instrument() whenever a run of a job that declares a retry
    policy fails (RQ re-enqueues it unless the budget is exhausted). The
    dead-letter sweep subtracts the terminal failure later, so the counter ends
    up as the number of retries ACTUALLY performed."""
    r = _redis()
    if r is not None:
        try:
            r.incr(f"sg:metric:{func_name}:retries")
        except Exception:
            pass  # metrics must never break the job itself
        return
    key = f"{func_name}:retries"
    _METRICS[key] = _METRICS.get(key, 0) + 1


def instrument(fn):
    """Record a job's outcome (success/failed), duration and retries.

    Wraps a job function so every run — inline (no broker) or under an RQ
    worker — bumps the metrics. functools.wraps keeps __name__/__qualname__
    intact, so retry policies and RQ's pickle-by-qualname both still resolve
    to the same module-level name."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            record_outcome(fn.__name__, 'success', time.monotonic() - t0)
            return result
        except Exception:
            record_outcome(fn.__name__, 'failed', time.monotonic() - t0)
            # A failed run of a retry-policy job is a retry event (RQ re-runs
            # it); the dead-letter sweep corrects the final terminal failure.
            if fn.__name__ in JOB_RETRY_POLICIES:
                record_retry(fn.__name__)
            raise
    return wrapper


def _counter_snapshot():
    """Current Prometheus-style counters as {'jobs_run_total', 'job_duration_s_total'}.

    Each function's bucket carries 'success', 'failed', 'retries' and
    'dead_lettered' outcome suffixes plus a 'duration_s' total."""
    jobs_run = {}
    durations = {}
    r = _redis()
    if r is not None:
        try:
            for key in r.scan_iter(match='sg:metric:*', count=200):
                key = key.decode('utf-8') if isinstance(key, bytes) else key
                # sg:metric:<func>:<suffix> — func names never contain ':'
                _prefix, _ns, func, suffix = key.split(':')
                value = float(r.get(key) or 0)
                if suffix == 'duration_s':
                    durations[func] = value
                else:
                    jobs_run.setdefault(func, {})[suffix] = int(value)
        except Exception as e:
            logger.warning("counter_snapshot_error", error=str(e))
    else:
        for key, value in _METRICS.items():
            func, suffix = key.rsplit(':', 1)
            value = float(value)
            if suffix == 'duration_s':
                durations[func] = value
            else:
                jobs_run.setdefault(func, {})[suffix] = int(value)
    return {'jobs_run_total': jobs_run, 'job_duration_s_total': durations}


def _job_kpis(counters):
    """Derive admin-facing KPIs from a counter snapshot.

    Aggregates totals across every instrumented job function: how many jobs ran
    and failed, retry attempts, dead-lettered jobs, the dead-letter rate (share
    of runs that exhausted their retry budget) and the average wall-clock
    duration per run. Per-function rows are included for the dashboard table.
    """
    jobs_run = counters.get('jobs_run_total', {})
    durations = counters.get('job_duration_s_total', {})
    total_runs = total_failed = total_retries = total_dead = 0
    total_duration = 0.0
    per_function = []
    for func, outcomes in jobs_run.items():
        success = int(outcomes.get('success', 0))
        failed = int(outcomes.get('failed', 0))
        retries = int(outcomes.get('retries', 0))
        dead = int(outcomes.get('dead_lettered', 0))
        dur = float(durations.get(func, 0.0))
        runs = success + failed
        total_runs += runs
        total_failed += failed
        total_retries += retries
        total_dead += dead
        total_duration += dur
        if runs:
            per_function.append({
                'func': func,
                'runs': runs,
                'failed': failed,
                'retries': retries,
                'dead_lettered': dead,
                'avg_duration_s': round(dur / runs, 3),
                'dead_letter_rate': round((dead / runs) * 100, 2),
            })
    per_function.sort(key=lambda f: -f['runs'])
    return {
        'jobs_run': total_runs,
        'jobs_failed': total_failed,
        'retries': total_retries,
        'dead_lettered': total_dead,
        'dead_letter_rate': round((total_dead / total_runs) * 100, 2) if total_runs else 0.0,
        'avg_duration_s': round(total_duration / total_runs, 3) if total_runs else 0.0,
        'per_function': per_function[:20],
    }


def prometheus_exposition(counters):
    """Render counters as Prometheus text exposition (scrapable by /metrics)."""
    lines = [
        "# HELP smartgarbage_jobs_run_total Jobs executed, by function and outcome.",
        "# TYPE smartgarbage_jobs_run_total counter",
    ]
    jobs_run = counters.get('jobs_run_total', {})
    for func in sorted(jobs_run):
        for outcome in ('success', 'failed'):
            count = jobs_run[func].get(outcome, 0)
            if count:
                lines.append(f'smartgarbage_jobs_run_total{{job="{func}",outcome="{outcome}"}} {count}')
    lines.append("# HELP smartgarbage_job_retries_total Retry attempts performed per job.")
    lines.append("# TYPE smartgarbage_job_retries_total counter")
    for func in sorted(jobs_run):
        count = jobs_run[func].get('retries', 0)
        if count:
            lines.append(f'smartgarbage_job_retries_total{{job="{func}"}} {count}')
    lines.append("# HELP smartgarbage_job_dead_lettered_total Jobs that exhausted their retry budget.")
    lines.append("# TYPE smartgarbage_job_dead_lettered_total counter")
    for func in sorted(jobs_run):
        count = jobs_run[func].get('dead_lettered', 0)
        if count:
            lines.append(f'smartgarbage_job_dead_lettered_total{{job="{func}"}} {count}')
    lines.append("# HELP smartgarbage_job_duration_s_total Cumulative job runtime seconds.")
    lines.append("# TYPE smartgarbage_job_duration_s_total counter")
    for func in sorted(counters.get('job_duration_s_total', {})):
        lines.append(f'smartgarbage_job_duration_s_total{{job="{func}"}} '
                     f'{counters["job_duration_s_total"][func]:.3f}')
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────
# QUEUE STATUS SNAPSHOT (admin /api/jobs/status)
# ──────────────────────────────────────────────
def _iso(dt):
    return dt.isoformat() if dt else None


def _job_duration_s(job):
    """Wall-clock seconds a finished/failed job ran, from RQ's timestamps."""
    if job.ended_at and job.started_at:
        return round((job.ended_at - job.started_at).total_seconds(), 3)
    return None


def _job_func_name(job):
    func = getattr(job, 'func_name', '') or ''
    return func.rsplit('.', 1)[-1]


def queue_status(limit=20):
    """Snapshot for the admin endpoint: queue depth, active workers, recent
    job outcomes with per-job durations, and accumulated counters.

    Depth = queued + started + scheduled + deferred. Recent jobs come from the
    started / finished / failed registries, each entry carrying its outcome and
    wall-clock duration. Degrades to the inline (no-broker) picture without
    Redis and never raises."""
    q = _get_queue()
    if q is None:
        counters = _counter_snapshot()
        return {
            'broker': 'inline',
            'queue_depth': 0,
            'workers': 0,
            'recent_jobs': [],
            'counters': counters,
            'kpis': _job_kpis(counters),
        }
    try:
        from rq.job import Job
        queue_depth = q.count  # jobs waiting to be picked up
        for registry in (q.started_job_registry, q.scheduled_job_registry,
                         q.deferred_job_registry):
            queue_depth += len(registry)

        workers = 0
        try:
            from rq import Worker
            workers = len(Worker.all(connection=q.connection))
        except Exception:
            pass  # worker discovery is best-effort

        recent = []
        for jid in q.started_job_registry.get_job_ids()[:limit]:
            try:
                job = Job.fetch(jid, connection=q.connection)
                recent.append({'job_id': job.id, 'func': _job_func_name(job),
                               'outcome': 'running', 'duration_s': None,
                               'enqueued_at': _iso(job.enqueued_at),
                               'ended_at': None})
            except Exception:
                continue  # job vanished mid-scan — skip, don't abort
        for registry, outcome in ((q.finished_job_registry, 'finished'),
                                  (q.failed_job_registry, 'failed')):
            for jid in registry.get_job_ids()[:limit]:
                try:
                    job = Job.fetch(jid, connection=q.connection)
                    recent.append({'job_id': job.id, 'func': _job_func_name(job),
                                   'outcome': outcome, 'duration_s': _job_duration_s(job),
                                   'enqueued_at': _iso(job.enqueued_at),
                                   'ended_at': _iso(job.ended_at)})
                except Exception:
                    continue
        recent.sort(key=lambda j: (j['ended_at'] or j['enqueued_at'] or ''), reverse=True)
        counters = _counter_snapshot()
        return {
            'broker': 'redis',
            'queue_depth': queue_depth,
            'workers': workers,
            'recent_jobs': recent[:limit],
            'counters': counters,
            'kpis': _job_kpis(counters),
        }
    except Exception as e:
        logger.warning("queue_status_error", error=str(e))
        counters = _counter_snapshot()
        return {'broker': 'redis', 'queue_depth': 0, 'workers': 0,
                'recent_jobs': [], 'counters': counters,
                'kpis': _job_kpis(counters), 'error': str(e)}


@contextmanager
def _app_ctx():
    """Enter an app context for jobs that touch the DB.

    Inline execution already happens inside a request/app context (pytest,
    local dev) so we reuse it; RQ workers run with no context and create one.
    """
    from flask import has_app_context
    from app import create_app
    if has_app_context():
        yield
    else:
        with create_app().app_context():
            yield


# ──────────────────────────────────────────────
# SMS / EMAIL / WEBHOOK JOBS
# ──────────────────────────────────────────────
@instrument
def send_sms_job(to_number, body):
    """Deliver a phone message through the free-first channel chain:

    1. Meta WhatsApp Cloud API (text replies inside the citizen's 24h
       service window: free with no cap through Sep 30, 2026; from Oct 1,
       2026 billed per delivered message but with 1,000 free service
       messages per number per month — a gram-panchayat's volume stays at
       Rs 0. No sandbox, no DLT, works to any country) — used when
       WHATSAPP_CLOUD_* is configured.
    2. Twilio (WhatsApp if TWILIO_WHATSAPP_NUMBER is set, else SMS) — paid
       per message, kept as the business-initiated fallback.

    Returns False when both channels are unconfigured or reject the send so
    the caller (send_otp_job, notify_status_change_job, …) falls back to
    email instead of silently dropping the message.
    """
    from .routes import send_whatsapp_cloud, send_sms_via_twilio
    if send_whatsapp_cloud(to_number, body):
        return True
    return send_sms_via_twilio(to_number, body)


@instrument
def send_email_job(to_email, subject, body):
    from .routes import send_email_via_smtp
    return send_email_via_smtp(to_email, subject, body)


def _otp_email_recipient(recipient):
    """Resolve the OTP *email* recipient from the OTP recipient.

    Callers pass either an email address or a phone number (staff MFA passes
    user.phone). When SMS/WhatsApp is unavailable the email fallback must not
    target the phone string — it is not a valid address and the OTP would be
    silently dropped. A phone-shaped recipient is therefore resolved to the
    user's email on file; users without an email fall back to the civic
    contact inbox (_otp_recipient_fallback's semantics) so the OTP is never
    silently lost. Valid email recipients pass through unchanged.
    """
    if recipient and '@' in recipient:
        return recipient
    from flask import current_app
    from .models import User
    from .routes import _otp_recipient_fallback, validate_indian_phone
    with _app_ctx():
        normalized = validate_indian_phone(recipient) if recipient else None
        user = None
        if recipient:
            user = User.query.filter_by(phone=recipient).first()
            if user is None and normalized and normalized != recipient:
                user = User.query.filter_by(phone=normalized).first()
        if user and user.email:
            return user.email
        return _otp_recipient_fallback()


@instrument
def send_otp_job(recipient, otp_val, subject='SmartGarbage OTP', channel='auto'):
    """Send an OTP via SMS, then email if SMS is unavailable — off the request path.

    The email fallback resolves a phone-shaped recipient to the user's email
    on file (see _otp_email_recipient) instead of mailing the phone string,
    which no SMTP server accepts.

    channel='email' skips the SMS/WhatsApp attempt entirely and delivers
    straight to the resolved email address — the staff (admin/worker) "email
    me the code" MFA option, so a deployment without Twilio/WhatsApp
    credentials can still complete staff logins.

    Note: it calls the decorated send_sms_job/send_email_job directly, so one
    OTP delivery counts as multiple job runs in the metrics (function-level
    accounting — each helper genuinely executed)."""
    if channel == 'email':
        send_email_job(_otp_email_recipient(recipient), subject,
                       f"Your SmartGarbage OTP is: {otp_val}\n\nThis code expires in 5 minutes.")
        return
    sms_sent = send_sms_job(recipient, f"SmartGarbage OTP: {otp_val}")
    if not sms_sent:
        send_email_job(_otp_email_recipient(recipient), subject,
                       f"Your SmartGarbage OTP is: {otp_val}\n\nThis code expires in 5 minutes.")


@instrument
def notify_status_change_job(complaint_id, phone, email, area, status):
    """Send a complaint status alert (WhatsApp/SMS with email fallback).

    Runs in the background so resolving a complaint never blocks on Twilio.
    Localhost filtering is done by the caller (it needs request context).
    """
    message = (f"SmartGarbage: Your complaint #{complaint_id} in {area} "
               f"is now {status}. Thank you!")
    sent = False
    if phone:
        sent = send_sms_job(phone, message)
        if not sent and email:
            sent = send_email_job(email, "SmartGarbage — Complaint Update", message)
    elif email:
        sent = send_email_job(email, "SmartGarbage — Complaint Update", message)
    logger.info("status_notify_delivered", complaint_id=complaint_id,
                status=status, delivered=sent)
    return sent


@instrument
def send_tracking_link_job(phone, email, complaint_id, area, track_url):
    """Send a citizen their complaint's signed tracking link.

    SMS/WhatsApp first with email fallback, mirroring notify_status_change_job.
    The URL carries a signed token (90-day expiry) so the complaint can't be
    enumerated — only the reporter (who got the link) can open it.
    """
    message = (f"SmartGarbage: Your complaint #{complaint_id} in {area} was "
               f"received. Track its status live: {track_url}")
    sent = False
    if phone:
        sent = send_sms_job(phone, message)
        if not sent and email:
            sent = send_email_job(email, "SmartGarbage — Complaint Tracking", message)
    elif email:
        sent = send_email_job(email, "SmartGarbage — Complaint Tracking", message)
    logger.info("tracking_link_delivered", complaint_id=complaint_id, delivered=sent)
    return sent


@instrument
def dispatch_webhooks_job(urls, event, payload):
    """POST an event to every registered webhook URL (best-effort, never raises)."""
    import requests
    for wh in urls:
        try:
            requests.post(wh, json=dict(payload, event=event,
                                        timestamp=datetime.now(timezone.utc).isoformat()), timeout=3)
        except Exception as e:
            logger.warning("webhook_delivery_failed", error=str(e))


# ──────────────────────────────────────────────
# EXPORT ARTIFACTS (PDF / CSV / JSON)
# ──────────────────────────────────────────────
_INLINE_EXPORT_CAP = 20  # keep the newest artifacts only (no-Redis fallback)


def _store_artifact(job_id, content, content_type, filename):
    record = {'content': base64.b64encode(content).decode('ascii'),
              'content_type': content_type, 'filename': filename}
    r = _redis()
    if r is not None:
        try:
            r.set(f"sg:export:{job_id}", json.dumps(record), ex=1800)
        except Exception:
            pass
    else:
        _INLINE_EXPORTS[job_id] = record
        # Bound the in-process fallback store so a long-lived no-Redis process
        # can't leak memory — drop the oldest entries past the cap.
        while len(_INLINE_EXPORTS) > _INLINE_EXPORT_CAP:
            _INLINE_EXPORTS.pop(next(iter(_INLINE_EXPORTS)))


def fetch_artifact(job_id):
    """Return (content_bytes, content_type, filename) or None if not ready."""
    r = _redis()
    if r is not None:
        try:
            raw = r.get(f"sg:export:{job_id}")
        except Exception:
            raw = None
        if raw:
            rec = json.loads(raw)
            return base64.b64decode(rec['content']), rec['content_type'], rec['filename']
        return None
    rec = _INLINE_EXPORTS.get(job_id)
    if rec:
        return base64.b64decode(rec['content']), rec['content_type'], rec['filename']
    return None


@instrument
def generate_export_job(job_id, kind, fmt='json'):
    """Build a PDF/CSV/JSON export artifact in the background and store it."""
    import csv
    import io as _io
    with _app_ctx():
        from .routes import _state_portal_indicators, _csrd_payload, _performance_pdf_bytes
        content = content_type = filename = None
        if kind == 'state-portal':
            indicators = _state_portal_indicators()
            if fmt == 'csv':
                buf = _io.StringIO()
                w = csv.writer(buf)
                w.writerow(['indicator', 'value'])
                for k, v in indicators.items():
                    w.writerow([k, v])
                content = buf.getvalue().encode('utf-8')
                content_type = 'text/csv'
                filename = 'state_portal_compliance.csv'
            else:
                payload = {
                    'report_title': 'State Portal SWM Compliance Return',
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'indicators': indicators,
                }
                content = json.dumps(payload).encode('utf-8')
                content_type = 'application/json'
                filename = 'state_portal_compliance.json'
        elif kind == 'csrd':
            content = json.dumps(_csrd_payload()).encode('utf-8')
            content_type = 'application/json'
            filename = 'csrd_report.json'
        elif kind == 'performance-pdf':
            content, filename = _performance_pdf_bytes()
            content_type = 'application/pdf'
        if content is None:
            return None
        _store_artifact(job_id, content, content_type, filename)
    return job_id


# ──────────────────────────────────────────────
# PAYT DUNNING (overdue invoice reminders)
# ──────────────────────────────────────────────
@instrument
def payt_reminder_job(user_id, invoice_id, period, amount, days):
    """Send an overdue-invoice reminder (SMS/WhatsApp with email fallback)."""
    with _app_ctx():
        from .models import User
        from .routes import send_sms_via_twilio, send_email_via_smtp
        user = User.query.get(user_id)
        if not user:
            return False
        message = (f"SmartGarbage: PAYT invoice #{invoice_id} ({period}) is {days} days "
                   f"overdue. Please pay ₹{amount:.2f} to keep service running.")
        sent = False
        if user.phone:
            sent = send_sms_via_twilio(user.phone, message)
            if not sent and user.email:
                sent = send_email_via_smtp(user.email, "SmartGarbage — PAYT Invoice Overdue", message)
        elif user.email:
            sent = send_email_via_smtp(user.email, "SmartGarbage — PAYT Invoice Overdue", message)
        logger.info("payt_dunning_reminder", invoice_id=invoice_id, delivered=sent)
        return sent


@instrument
def payt_receipt_job(invoice_id):
    """Build and email the PAYT payment receipt PDF for a paid invoice.

    Runs after the Razorpay webhook captures payment, off the webhook request
    path (reportlab rendering + SMTP round-trip must never block webhook
    acknowledgement). Generates the receipt via _payt_receipt_pdf_bytes and
    sends it as a PDF attachment through send_email_via_smtp. Best-effort and
    never raises: a missing user email or unconfigured SMTP just logs and
    returns False. Returns True when the email was accepted by the gateway."""
    with _app_ctx():
        from .models import PAYTInvoice
        from .routes import _payt_receipt_pdf_bytes, send_email_via_smtp
        invoice = PAYTInvoice.query.get(invoice_id)
        if not invoice or invoice.status != 'Paid':
            return False
        user = invoice.user
        if not user or not user.email:
            logger.info("payt_receipt_no_email", invoice_id=invoice_id)
            return False
        try:
            pdf_bytes, filename = _payt_receipt_pdf_bytes(invoice)
        except Exception as e:
            logger.warning("payt_receipt_pdf_error", invoice_id=invoice_id, error=str(e))
            return False
        subject = f"SmartGarbage PAYT Receipt — Invoice #{invoice.id}"
        body = (f"Dear {user.username},\n\n"
                f"Thank you for your payment of ₹{invoice.amount_rs:.2f} "
                f"for {invoice.period}. Your receipt is attached.\n\n"
                f"Payment ID: {invoice.transaction_ref or '—'}\n"
                f"SmartGarbage — Chintalavalasa")
        sent = send_email_via_smtp(user.email, subject, body,
                                   attachment_bytes=pdf_bytes,
                                   attachment_filename=filename)
        logger.info("payt_receipt_sent", invoice_id=invoice_id, delivered=sent)
        return sent


@instrument
def dunning_job(grace_days=30):
    """Find overdue unpaid PAYT invoices and queue reminders (deduped).

    Returns the number of reminders created so callers (and tests) can assert
    on the inline fallback path."""
    with _app_ctx():
        from app import db
        from .models import PAYTInvoice, Notification, utcnow
        cutoff = utcnow() - timedelta(days=grace_days)  # naive UTC: matches issued_at storage
        overdue = PAYTInvoice.query.filter(
            PAYTInvoice.status == 'Unpaid',
            PAYTInvoice.issued_at < cutoff).all()
        reminded = 0
        pushed = []  # (user_id, message) — SSE-pushed only AFTER the commit
        for inv in overdue:
            dup = Notification.query.filter(
                Notification.user_id == inv.user_id,
                Notification.link == f'/payt/pay/{inv.id}',
                Notification.message.ilike('%overdue%')).first()  # ilike: case-insensitive on Postgres
            if dup:
                continue
            # Defensive: normalize naive datetimes before
            # subtraction so the age computation never raises.
            issued = inv.issued_at
            if issued is not None and issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - issued).days if issued else grace_days
            note = Notification(
                user_id=inv.user_id,
                message=(f"PAYT invoice #{inv.id} ({inv.period}) is {days} days overdue. "
                         f"Please pay ₹{inv.amount_rs:.2f} to avoid service disruption."),
                link=f'/payt/pay/{inv.id}',
            )
            db.session.add(note)
            pushed.append((inv.user_id, note.message))
            enqueue(payt_reminder_job, inv.user_id, inv.id, inv.period, inv.amount_rs, days)
            reminded += 1
        db.session.commit()
        # Real-time SSE push AFTER the commit: a toast must never announce a
        # notification that failed to persist (no-op without Redis — the
        # stream's DB-poll fallback covers dev/tests).
        if pushed:
            try:
                from .routes import _publish_user_event
                for uid, msg in pushed:
                    _publish_user_event(uid, msg)
            except Exception:
                pass
        logger.info("dunning_run", overdue=len(overdue), reminded=reminded)
        return reminded


# ──────────────────────────────────────────────
# DEAD-LETTER HANDLING (failed-job registry)
# ──────────────────────────────────────────────
def failed_jobs(limit=100):
    """List dead-lettered (failed) RQ jobs with metadata; [] without Redis.

    RQ moves a job into the failed registry once it exhausts its retry budget.
    Each entry exposes the id, function, timestamps, retries left and a
    truncated traceback so the admin dashboard can explain the failure."""
    q = _get_queue()
    if q is None:
        return []
    try:
        from rq.job import Job
        registry = q.failed_job_registry
        jobs = []
        for jid in registry.get_job_ids()[:limit]:
            try:
                job = Job.fetch(jid, connection=q.connection)
                jobs.append({
                    'id': job.id,
                    'func': getattr(job, 'func_name', None),
                    'enqueued_at': job.enqueued_at,
                    'ended_at': job.ended_at,
                    'retries_left': getattr(job, 'retries_left', None),
                    'exc_info': (job.exc_info or '')[-2000:],
                })
            except Exception:
                continue  # job vanished mid-scan — skip, don't abort the page
        return jobs
    except Exception as e:
        logger.warning("failed_jobs_list_error", error=str(e))
        return []


def _restore_retry_budget(job):
    """Restore a dead-lettered job's automatic-backoff budget from its policy.

    RQ keeps `retries_left` exhausted once a job lands in the failed registry
    and FailedJobRegistry.requeue does NOT reset it, so a plain manual requeue
    runs once more with zero retries and dead-letters again on its very next
    failure. This re-applies the job's declared JOB_RETRY_POLICIES entry
    (retries_left + retry_intervals, exactly as Queue.enqueue would set them)
    so the requeued job gets full exponential backoff again. Returns True when
    a policy was applied, False for jobs without one (they keep RQ's default)."""
    func = _job_func_name(job)
    policy = JOB_RETRY_POLICIES.get(func)
    if not policy:
        return False
    max_retries, intervals = policy
    job.retries_left = max_retries
    job.retry_intervals = list(intervals)
    return True


def requeue_failed_job(job_id):
    """Move a dead-lettered job back to its original queue for another attempt.

    Before requeueing, the job's auto-retry budget is restored from its
    declared JOB_RETRY_POLICIES entry (via _restore_retry_budget) so the
    requeued job gets the full exponential backoff again — a plain RQ requeue
    would keep retries_left exhausted and dead-letter on the very next failure.
    Returns True on success, False when Redis is absent or the job is unknown."""
    q = _get_queue()
    if q is None:
        return False
    try:
        from rq.job import Job
        job = Job.fetch(job_id, connection=q.connection)
        _restore_retry_budget(job)
        job.save()  # persist the restored budget before requeueing
        # Pass the job object (not just the id) so RQ's requeue uses the
        # restored in-memory budget directly instead of re-fetching.
        q.failed_job_registry.requeue(job)
        return True
    except Exception as e:
        logger.warning("failed_job_requeue_error", job_id=job_id, error=str(e))
        return False


def delete_failed_job(job_id):
    """Permanently purge a single dead-lettered job (and its traceback)."""
    q = _get_queue()
    if q is None:
        return False
    try:
        from rq.job import Job
        registry = q.failed_job_registry
        job = Job.fetch(job_id, connection=q.connection)
        registry.remove(job, delete_job=True)
        return True
    except Exception as e:
        logger.warning("failed_job_delete_error", job_id=job_id, error=str(e))
        return False


def clear_failed_jobs():
    """Purge every dead-lettered job; returns the number removed (0 without Redis)."""
    q = _get_queue()
    if q is None:
        return 0
    try:
        registry = q.failed_job_registry
        job_ids = registry.get_job_ids()
        for jid in job_ids:
            delete_failed_job(jid)
        return len(job_ids)
    except Exception as e:
        logger.warning("failed_jobs_clear_error", error=str(e))
        return 0


def schedule_dunning(interval_hours=24):
    """Enqueue the next dunning run as a delayed RQ job (no-op without Redis).

    Guarded by a Redis SET-NX key so repeated app restarts / multiple instances
    only ever schedule ONE pending dunning run."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:dunning:scheduled', '1', nx=True, ex=int(interval_hours * 3600)):
                return  # another instance already scheduled the run
        except Exception:
            pass
    q.enqueue_in(timedelta(hours=interval_hours), dunning_job, retry=_retry_for(dunning_job))


# ──────────────────────────────────────────────
# DEAD-LETTER ALERTING (failures surface on their own)
# ──────────────────────────────────────────────
# When a job exhausts its retry budget and lands in the failed registry, the
# periodic sweep below turns it into an in-app Notification for every approved
# admin (surfaced via the dashboard's existing notification stream) plus an
# optional JOB_DEAD_LETTERED webhook — so failures don't require someone
# watching the dead-letter dashboard.
DEAD_LETTER_LINK_PREFIX = "/admin/failed-jobs#"  # per-job marker used for dedupe
JOB_DEAD_LETTER_EVENT = "JOB_DEAD_LETTERED"

# Inline (no-Redis) dedupe set for the dead-letter counter — mirrors the
# Redis SET-NX marker so tests / local dev never double-count a dead-letter.
_DEAD_LETTER_COUNTED = set()


def _count_dead_letter(func_name, job_id):
    """Increment the dead-lettered counter once per dead-lettered job.

    The failed registry is scanned repeatedly by the alert sweep, so this is
    deduped per job_id — via a Redis SET-NX marker (TTL 30d) when a broker is
    configured, or an in-process set otherwise — so each dead-lettered job
    contributes exactly one to the counter. The terminal failure was already
    counted as a retry attempt by instrument(); subtracting it here keeps
    retries as "retries actually performed". Never raises."""
    r = _redis()
    if r is not None:
        try:
            marker = f"sg:dl-counted:{job_id}"
            if not r.set(marker, '1', nx=True, ex=86400 * 30):
                return  # already counted
            pipe = r.pipeline()
            pipe.incr(f"sg:metric:{func_name}:dead_lettered")
            if func_name in JOB_RETRY_POLICIES:
                # Only correct the retry counter when it actually exists and is
                # positive — a freshly-provisioned Redis (or jobs dead-lettered
                # before this feature deployed) has no retries key yet, and a
                # Prometheus counter must never go negative.
                cur = r.get(f"sg:metric:{func_name}:retries")
                if cur and int(cur) > 0:
                    pipe.decrby(f"sg:metric:{func_name}:retries", 1)
            pipe.execute()
        except Exception:
            pass  # metrics must never break the sweep
        return
    if job_id in _DEAD_LETTER_COUNTED:
        return
    _DEAD_LETTER_COUNTED.add(job_id)
    if len(_DEAD_LETTER_COUNTED) > 10000:  # bound long-lived no-Redis processes
        _DEAD_LETTER_COUNTED.clear()
    key = f"{func_name}:dead_lettered"
    _METRICS[key] = _METRICS.get(key, 0) + 1
    if func_name in JOB_RETRY_POLICIES:
        rkey = f"{func_name}:retries"
        _METRICS[rkey] = max(0, _METRICS.get(rkey, 0) - 1)


def _admin_user_ids():
    """Ids of every approved admin account (alert recipients)."""
    with _app_ctx():
        from .models import User
        return [u.id for u in User.query.filter_by(role='admin', is_approved=True).all()]


def alert_on_dead_letter(job_id, func_name, exc_info='', fire_webhook=True):
    """Notify admins that a job exhausted its retries and was dead-lettered.

    Creates one in-app Notification per approved admin, deduped by a per-job
    link marker (the same link pattern dunning uses for invoice reminders), and
    optionally fires a JOB_DEAD_LETTERED webhook event. Best-effort and never
    raises — alerting must never break the job lifecycle. Returns the number
    of notifications created (0 = already alerted / no admins)."""
    if not job_id:
        return 0
    marker = f"{DEAD_LETTER_LINK_PREFIX}{job_id}"
    created = 0
    try:
        with _app_ctx():
            from .models import Notification
            from app import db
            # Idempotent: a sweep re-run for the same job is a no-op.
            if Notification.query.filter_by(link=marker).first() is not None:
                return 0
            func = (func_name or 'unknown').rsplit('.', 1)[-1]
            message = (f"⚠️ Background job {func} ({job_id}) exhausted its retries "
                       f"and was dead-lettered. Requeue or purge it in the "
                       f"Failed Jobs queue.")
            pushed = []  # SSE-pushed only AFTER the commit below
            for uid in _admin_user_ids():
                db.session.add(Notification(user_id=uid, message=message, link=marker))
                pushed.append((uid, message))
                created += 1
            db.session.commit()
            # Real-time SSE push after the commit (no-op without Redis): a
            # dead-letter toast must never outlive a notification write that
            # rolled back.
            if pushed:
                try:
                    from .routes import _publish_user_event
                    for uid, msg in pushed:
                        _publish_user_event(uid, msg)
                except Exception:
                    pass
    except Exception as e:
        logger.warning("dead_letter_alert_error", job_id=job_id, error=str(e))
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return 0
    # Webhook is best-effort and fire-and-forget: a dispatch failure must NOT
    # zero the notification count (the in-app alerts are already committed and
    # deduped), so it gets its own guard and only logs.
    if fire_webhook and created:
        try:
            from .routes import _dispatch_webhooks  # lazy: avoids circular import
            _dispatch_webhooks(JOB_DEAD_LETTER_EVENT, {
                'job_id': job_id,
                'func': func_name,
                'exc_info': (exc_info or '')[-2000:],
            })
        except Exception as e:
            logger.warning("dead_letter_webhook_error", job_id=job_id, error=str(e))
    return created


def sweep_failed_jobs_alerts(limit=50):
    """Scan the failed registry and alert admins about every dead-lettered job.

    Returns the number of notifications created (0 without Redis, or when every
    failure was already alerted)."""
    q = _get_queue()
    if q is None:
        return 0
    created = 0
    try:
        from rq.job import Job
        registry = q.failed_job_registry
        for jid in registry.get_job_ids()[:limit]:
            try:
                job = Job.fetch(jid, connection=q.connection)
            except Exception:
                continue  # job vanished mid-scan — skip, don't abort the sweep
            # Instrumentation: count each dead-lettered job exactly once (the
            # dedupe marker lives in _count_dead_letter, independent of the
            # notification marker below).
            _count_dead_letter(_job_func_name(job), job.id)
            created += alert_on_dead_letter(
                job.id, getattr(job, 'func_name', None),
                getattr(job, 'exc_info', '') or '')
    except Exception as e:
        logger.warning("failed_jobs_sweep_error", error=str(e))
    return created


@instrument
def sweep_failed_jobs_alerts_job(interval_minutes=5):
    """Periodic dead-letter alert sweep; re-schedules itself for the next run.

    Runs in the RQ worker (with an app context for DB writes); without Redis
    the queue is absent and the sweep is a no-op (returns 0). The job enqueues
    the FOLLOWING run so alerts keep flowing without a manual reschedule — the
    SET-NX guard in schedule_failed_alert_sweep stops instances from stacking
    duplicates."""
    with _app_ctx():
        created = sweep_failed_jobs_alerts()
    schedule_failed_alert_sweep(interval_minutes=interval_minutes)
    logger.info("dead_letter_sweep", notifications_created=created,
                next_interval_minutes=interval_minutes)
    return created


def schedule_failed_alert_sweep(interval_minutes=5):
    """Enqueue the next dead-letter alert sweep (no-op without Redis).

    Guarded by a Redis SET-NX key so repeated app restarts / multiple instances
    only ever schedule ONE pending sweep; the sweep job itself re-schedules its
    own successor when it runs."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:failed-alert:sweep', '1', nx=True, ex=int(interval_minutes * 60)):
                return  # another instance already scheduled the sweep
        except Exception:
            pass
    q.enqueue_in(timedelta(minutes=interval_minutes), sweep_failed_jobs_alerts_job,
                 retry=_retry_for(sweep_failed_jobs_alerts_job))


@instrument
def sla_escalation_job():
    """Escalate complaints past their SLA deadline and illegal dump reports
    pending > 48h.

    Complaint lifecycle v3: complaints enter as 'Submitted' with a 48h
    sla_deadline. This job escalates any complaint still in an open state
    (Submitted / Under Review / Assigned / In Progress) past its deadline,
    and moves illegal dump reports pending > 48h to 'Escalated'. Admins are
    notified so nothing silently ages out of the queue."""
    with _app_ctx():
        from app import db
        from app.models import Complaint, IllegalDumpReport, User, Notification, AuditLog, utcnow
        now = utcnow()
        # Complaints: use the SLA deadline (48h from submission) — the old
        # 24h-from-created_at check didn't match the new lifecycle.
        stale = Complaint.query.filter(
            Complaint.status.in_(['Submitted', 'Under Review', 'Assigned', 'In Progress']),
            Complaint.sla_deadline.isnot(None),
            Complaint.sla_deadline < now
        ).all()
        admins = User.query.filter_by(role='admin', is_active=True).all()
        from .routes import record_complaint_event
        pushed = []  # (admin_id, message) — SSE-pushed only AFTER the commit
        for c in stale:
            c.status = 'Escalated'
            detail = (f"Auto-escalated past SLA deadline "
                      f"(filed {c.created_at.isoformat() if c.created_at else '?'}, "
                      f"deadline {c.sla_deadline.isoformat() if c.sla_deadline else '?'})")
            # Timeline event joins the single commit below (commit=False)
            record_complaint_event(c, 'Escalated',
                                   'Auto-escalated: SLA deadline crossed, control room notified.',
                                   commit=False)
            db.session.add(AuditLog(
                username='system', role='system', action='COMPLAINT_ESCALATED',
                target=c.ward, detail=detail))
            for a in admins:
                _msg = f"Complaint #{c.id} in {c.ward} escalated (SLA overdue)."
                db.session.add(Notification(user_id=a.id, message=_msg,
                                             link=f"/admin#{c.id}"))
                pushed.append((a.id, _msg))
        cutoff_i = utcnow() - timedelta(hours=48)
        stale_i = IllegalDumpReport.query.filter(
            IllegalDumpReport.status == 'Pending',
            IllegalDumpReport.timestamp < cutoff_i
        ).all()
        for r in stale_i:
            r.status = 'Escalated'
            db.session.add(AuditLog(
                username='system', role='system', action='ILLEGAL_REPORT_ESCALATED',
                target=r.category,
                detail=f"Auto-escalated after 48h (reported {r.timestamp.isoformat() if r.timestamp else '?'})"
            ))
            for a in admins:
                _msg = f"Illegal dump report #{r.id} ({r.category}) escalated (48h overdue)."
                db.session.add(Notification(user_id=a.id, message=_msg, link="/admin"))
                pushed.append((a.id, _msg))
        db.session.commit()
        # Real-time SSE push AFTER the commit (no-op without Redis): escalation
        # toasts must never outlive a rolled-back notification write.
        if pushed:
            try:
                from .routes import _publish_user_event
                for uid, msg in pushed:
                    _publish_user_event(uid, msg)
            except Exception:
                pass
        logger.info("sla_escalation", complaints=len(stale), illegal_reports=len(stale_i))
        return len(stale) + len(stale_i)


@instrument
def telemetry_retention_job(max_age_days=90):
    """Delete BinTelemetryLog rows older than max_age_days.

    Keeps the telemetry history table bounded so fill-rate estimation and ML
    retraining never scan unbounded history."""
    with _app_ctx():
        from app import db
        from app.models import BinTelemetryLog, utcnow
        cutoff = utcnow() - timedelta(days=max_age_days)
        deleted = BinTelemetryLog.query.filter(
            BinTelemetryLog.timestamp < cutoff
        ).delete(synchronize_session=False)
        db.session.commit()
        logger.info("telemetry_retention", deleted_rows=deleted, older_than_days=max_age_days)
        return deleted


def schedule_sla_escalation(interval_hours=6):
    """Enqueue the next SLA escalation sweep."""
    q = _get_queue()
    if q is None:
        return
    q.enqueue_in(timedelta(hours=interval_hours), sla_escalation_job,
                 retry=_retry_for(sla_escalation_job))


def schedule_telemetry_retention(interval_hours=24):
    """Enqueue the next telemetry retention sweep."""
    q = _get_queue()
    if q is None:
        return
    q.enqueue_in(timedelta(hours=interval_hours), telemetry_retention_job,
                 retry=_retry_for(telemetry_retention_job))


# ──────────────────────────────────────────────
# MAINTENANCE JOB (sensor faults + decomposition timers)
# ──────────────────────────────────────────────
# These two checks previously ran on EVERY admin page load — 2 full-table
# scans + 2N queries per visit. They now run on a 15-minute scheduled job so
# the admin dashboard stays fast while the checks still happen regularly.
@instrument
def maintenance_job():
    """Run sensor-fault + decomposition-timer maintenance on a 15-min cadence.

    Replaces the per-admin-load calls to check_sensor_faults() and
    check_decomposition_timers() — the admin dashboard no longer pays 2
    full-table scans + 2N queries on every render."""
    with _app_ctx():
        from .routes import check_sensor_faults, check_decomposition_timers
        check_sensor_faults()
        check_decomposition_timers()
        logger.info("maintenance_job_complete")
        return True


def schedule_maintenance(interval_minutes=15):
    """Enqueue the next maintenance sweep (no-op without Redis)."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:maintenance:scheduled', '1', nx=True,
                         ex=int(interval_minutes * 60)):
                return  # another instance already scheduled the run
        except Exception:
            pass
    q.enqueue_in(timedelta(minutes=interval_minutes), maintenance_job,
                 retry=_retry_for(maintenance_job))


# ──────────────────────────────────────────────
# MAINTENANCE WORK-ORDER OVERDUE ESCALATION
# ──────────────────────────────────────────────
# Work orders carry a due_date; when it passes without completion the bin is
# stuck in a maintenance-scheduled state that nobody is accountable for. This
# job escalates once per order (deduped by escalated_at): the assigned worker
# and every approved admin are notified via in-app Notification + the SSE
# stream, and a still-faulted bin is re-flagged so the control room keeps
# seeing it on the sensor-fault dashboard.
@instrument
def maintenance_overdue_escalation_job(grace_hours=0, interval_hours=24):
    """Escalate maintenance work orders whose due_date has passed.

    Deduped by the order's escalated_at column (set on first escalation), so a
    long-overdue order notifies exactly once. Notifies the assigned worker and
    the admin control room (in-app Notification + SSE push), and re-flags the
    bin's sensor fault / SensorHealth record if it is still faulted so it stays
    visible on the faulted-bin dashboard. Re-schedules its own successor (the
    sweep_failed_jobs_alerts_job pattern) so the daily cadence survives app
    restarts."""
    with _app_ctx():
        from app import db
        from app.models import (AuditLog, IncidentLog, MaintenanceWorkOrder,
                                Notification, SensorHealth, User, utcnow)
        from .routes import _notify_admins, _publish_admin_alerts
        now = utcnow()
        cutoff = now - timedelta(hours=grace_hours)
        stale = MaintenanceWorkOrder.query.filter(
            MaintenanceWorkOrder.status.in_(['Scheduled', 'In Progress']),
            MaintenanceWorkOrder.due_date.isnot(None),
            MaintenanceWorkOrder.due_date < cutoff,
            MaintenanceWorkOrder.escalated_at.is_(None),
        ).all()
        admin_ids = [u.id for u in User.query.filter_by(role='admin', is_approved=True).all()]
        pushed = []  # (user_id, message) — SSE-pushed only AFTER the commit
        escalated = 0
        for o in stale:
            b = o.bin
            o.escalated_at = now
            hw = b.hardware_id if b else '?'
            due = o.due_date.isoformat() if o.due_date else '?'
            db.session.add(AuditLog(
                username='system', role='system', action='MAINTENANCE_OVERDUE_ESCALATED',
                target=hw, detail=f"Work order #{o.id} past due ({due}) without completion."))
            # Assigned worker gets the nudge on their own task list.
            if o.worker_id:
                w_uid = o.worker.user_id if o.worker else None
                if w_uid:
                    w_msg = f"⏰ Maintenance work order #{o.id} for {hw} is overdue (due {due}). Please service it today."
                    db.session.add(Notification(user_id=w_uid, message=w_msg, link='/worker'))
                    pushed.append((w_uid, w_msg))
            # Control room sees the escalation too.
            admin_msg = (f"🚨 Maintenance work order #{o.id} for {hw} is overdue "
                         f"(due {due}) — escalation triggered.")
            pushed.extend(_notify_admins(admin_msg, link='/admin#sensor-fault-section',
                                         admin_ids=admin_ids))
            # Re-flag a bin that is STILL faulted (sensor never self-healed):
            # keep it on the faulted-bin dashboard and its health record marked
            # for maintenance instead of silently dropping off. Create the
            # SensorHealth row when the bin never had one (parity with
            # check_sensor_faults, which always ensures the record exists).
            if b and b.sensor_fault:
                sh = SensorHealth.query.filter_by(bin_id=b.id).first()
                if sh:
                    sh.fault_flag = True
                    sh.maintenance_scheduled = True
                else:
                    db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                                fault_reason=f"{hw} maintenance overdue — sensor still faulted",
                                                maintenance_scheduled=True))
                active = IncidentLog.query.filter_by(
                    bin_id=b.id, incident_type='Sensor Fault', status='Active').first()
                if not active:
                    db.session.add(IncidentLog(
                        bin_id=b.id, incident_type='Sensor Fault', severity='Warning',
                        status='Active',
                        description=f"{hw} maintenance overdue — sensor still faulted."))
            escalated += 1
        db.session.commit()
        # Real-time SSE push AFTER the commit (no-op without Redis): escalation
        # toasts must never outlive a rolled-back notification write.
        _publish_admin_alerts(pushed)
    # Re-arm the next sweep (the dead-letter sweep's self-rescheduling pattern).
    # Clear the stale SET-NX guard first: the startup-scheduled key (ex=24h)
    # expires at roughly the moment this run fires, and a still-live key would
    # block the reschedule from taking effect.
    try:
        r = _redis()
        if r is not None:
            r.delete('sg:maint-overdue:escalation')
    except Exception:
        pass
    schedule_maintenance_overdue_escalation(interval_hours=interval_hours)
    logger.info("maintenance_overdue_escalation", orders_escalated=escalated)
    return escalated


def schedule_maintenance_overdue_escalation(interval_hours=24):
    """Enqueue the next maintenance overdue-escalation sweep (no-op without Redis)."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:maint-overdue:escalation', '1', nx=True,
                         ex=int(interval_hours * 3600)):
                return  # another instance already scheduled the run
        except Exception:
            pass
    q.enqueue_in(timedelta(hours=interval_hours), maintenance_overdue_escalation_job,
                 retry=_retry_for(maintenance_overdue_escalation_job))


# ──────────────────────────────────────────────
# PAYT BILLING RECONCILIATION (verified weights drive invoices)
# ──────────────────────────────────────────────
# PAYT invoices are generated from SELF-REPORTED weights (WasteDeclaration /
# BWGDeclaration). The only trusted weight source is the worker-verified
# OffloadLog. This job matches offload weights to declarations per ward/period
# and flags discrepancies > 20% for admin audit, flipping the invoice's
# billing_status to 'Verified' (or 'Disputed').
@instrument
def payt_reconciliation_job():
    """Reconcile worker-verified OffloadLog weights against self-reported
    PAYT invoices per ward/period.

    For each 'Self-Reported' invoice, sum the worker-verified offload weights
    for the same ward in the same calendar month. If the verified total is
    within 20% of the declared weight, the invoice is marked 'Verified'
    (trusted). If the discrepancy exceeds 20%, it's marked 'Disputed' for
    admin audit — only verified weights should drive the final invoice amount.
    Returns the number of invoices reconciled."""
    with _app_ctx():
        from app import db
        from app.models import PAYTInvoice, OffloadLog
        from sqlalchemy import func
        from datetime import datetime as _dt
        # Only invoices still in the self-reported state are candidates.
        invoices = PAYTInvoice.query.filter_by(billing_status='Self-Reported').all()
        reconciled = 0
        for inv in invoices:
            # Sum worker-verified offload weights for the same ward in the
            # same calendar month as the invoice period.
            try:
                period_dt = _dt.strptime(inv.period, "%B %Y")
            except (ValueError, TypeError):
                continue
            month_start = period_dt.replace(day=1, tzinfo=timezone.utc)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)
            # OffloadLog doesn't carry a ward column — sum ALL worker-verified
            # offloads in the same calendar month and compare against the
            # invoice's declared weight. In a single-ward deployment this is
            # accurate; multi-ward deployments should extend OffloadLog with a
            # ward column and filter on it here.
            verified_total = (db.session.query(func.coalesce(
                func.sum(OffloadLog.weight_kg), 0.0))
                .filter(OffloadLog.verified == True,  # noqa: E712
                        OffloadLog.timestamp >= month_start,
                        OffloadLog.timestamp < month_end)
                .scalar())
            verified_total = float(verified_total or 0.0)
            declared = float(inv.weight_kg or 0.0)
            if declared <= 0:
                continue
            discrepancy = abs(verified_total - declared) / declared
            if discrepancy <= 0.20:
                inv.billing_status = 'Verified'
            else:
                inv.billing_status = 'Disputed'
            reconciled += 1
        db.session.commit()
        logger.info("payt_reconciliation", reconciled=reconciled)
        return reconciled


def schedule_payt_reconciliation(interval_hours=24):
    """Enqueue the next PAYT reconciliation sweep (no-op without Redis)."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:payt-recon:scheduled', '1', nx=True,
                         ex=int(interval_hours * 3600)):
                return  # another instance already scheduled the run
        except Exception:
            pass
    q.enqueue_in(timedelta(hours=interval_hours), payt_reconciliation_job,
                 retry=_retry_for(payt_reconciliation_job))


# ──────────────────────────────────────────────
# ML MODEL RETRAINING (weekly cadence)
# ──────────────────────────────────────────────
# Models are loaded at import time and never retrained. This job retrains on a
# weekly cadence using build_real_fill_rows() + synthetic priors, and
# hot-swaps the pickle with a versioned filename + atomic rename.
@instrument
def model_retraining_job():
    """Retrain the fill-rate + miss-prediction models on a weekly cadence.

    Uses train_model.py's build_real_fill_rows() + synthetic priors, then
    atomically swaps the versioned pickle files so the running app picks up
    the new model on the next import."""
    with _app_ctx():
        try:
            from train_model import build_real_fill_rows, train_and_save_models
        except ImportError:
            # train_model.py may not be importable in all environments — fall
            # back to a no-op with a log.
            logger.warning("model_retraining_skipped", reason="train_model not importable")
            return False
        try:
            # Build training rows from real telemetry + synthetic priors.
            rows = build_real_fill_rows()
            # train_and_save_models writes versioned pickles with atomic rename.
            train_and_save_models(rows)
            logger.info("model_retraining_complete", rows=len(rows))
            return True
        except Exception as e:
            logger.error("model_retraining_error", error=str(e))
            return False


def schedule_model_retraining(interval_days=7):
    """Enqueue the next model retraining run (no-op without Redis)."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:model-retrain:scheduled', '1', nx=True,
                         ex=int(interval_days * 86400)):
                return  # another instance already scheduled the run
        except Exception:
            pass
    q.enqueue_in(timedelta(days=interval_days), model_retraining_job,
                 retry=_retry_for(model_retraining_job))


# ──────────────────────────────────────────────
# PHOTO-GATE CANARY (uptime check for the anti-fake-report classifier)
# ──────────────────────────────────────────────
# The classifier gate is load-bearing: a silent regression (bundled artifact
# missing from the image, ONNX runtime breakage, a bad deploy) would wave
# every fake report through with nobody noticing — /health alone cannot see
# it when the failure is in the REQUEST path rather than the model file.
# This canary exercises the REAL user flow end-to-end over HTTP: GET the
# form (CSRF), POST an embedded ~7 KB non-garbage probe photo to the
# anonymous /report-illegal surface, and verify the response lands on
# ?photo=rejected. Anything else (accepted, banner missing, HTTP error) is
# a canary failure → admin Notification + PHOTO_GATE_BREACH webhook + a
# log line. The probe self-identifies in the description so a human can
# tell canary traffic from abuse at a glance.
_PHOTO_GATE_PROBE_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAkGBwgHBgkIBwgKCgkLDRYPDQwMDRsUFRAWIB0iIiAdHx8kKDQsJCYxJx8fLT0tMTU3"
    "Ojo6Iys/RD84QzQ5Ojf/2wBDAQoKCg0MDRoPDxo3JR8lNzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3"
    "Nzc3Nzc3Nzf/wAARCACoAOADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDnLi2vLC4k1Brgy5O5QjYxx0OeDUttq012Zm1WFopQmYJn6KDx2qjpl/NdQG2Plvbqu3fK"
    "MknuB6j61nam11ZQG2lLyQIPklUcEGosVc6WwuLCKFLWFFIIO7Axk9+fWs6/gMkUk9rfiMRsN0bc7fQVzdql/wDejilWKQ+u3d9M"
    "1oNBcWE7XFvAZIXGGhzkg/4ZqrCuSXF7cHVFF/BkXIVVZGwNuRgjHX3Brp57eC0K3CQ5VF+cvzxjsK5i7SaS1jub+0mXyztSMEBR"
    "/WtOOTUn0plkiUGZSY/NbB2UmC3C40t59ThuNLEfluA5fO3aKj1Z9WhjlkiuInjVQHTuo9s0zTbySy06WO5Zo2j4jcDcp+hrLSaO"
    "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"
    "FFAH/9k="
)


PHOTO_GATE_BREACH_EVENT = "PHOTO_GATE_BREACH"


def alert_photo_gate_breach(note=''):
    """Notify admins that the photo gate stopped rejecting the canary probe.

    Mirrors alert_on_dead_letter: one in-app Notification per approved admin,
    deduped to at most ONE alert per UTC day via a per-day link marker (a
    persistent breach re-alerts daily, not every 30-minute sweep); SSE push
    after commit; best-effort PHOTO_GATE_BREACH webhook. Never raises.
    Returns the number of notifications created (0 = already alerted today)."""
    created = 0
    marker = f"/admin/photo-rejections#canary-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    try:
        with _app_ctx():
            from .models import Notification
            from app import db
            if Notification.query.filter_by(link=marker).first() is not None:
                return 0  # already alerted today
            message = ("🚨 Photo gate canary FAILED: the non-garbage probe was "
                       "NOT rejected by /report-illegal — fake reports may be "
                       "getting through. Check /health's photo_classifier and "
                       "the rejection panel.")
            pushed = []
            for uid in _admin_user_ids():
                db.session.add(Notification(user_id=uid, message=message, link=marker))
                pushed.append((uid, message))
                created += 1
            db.session.commit()
            if pushed:
                try:
                    from .routes import _publish_user_event
                    for uid, msg in pushed:
                        _publish_user_event(uid, msg)
                except Exception:
                    pass
    except Exception as e:
        logger.warning("photo_gate_breach_alert_error", error=str(e))
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return 0
    if created:
        try:
            from .routes import _dispatch_webhooks  # lazy: avoids circular import
            _dispatch_webhooks(PHOTO_GATE_BREACH_EVENT, {
                'check': 'photo_gate_canary',
                'note': (note or '')[-2000:],
            })
        except Exception as e:
            logger.warning("photo_gate_breach_webhook_error", error=str(e))
    return created


@instrument
def photo_gate_canary_job(base_url=None):
    """Uptime canary for the anti-fake-report photo gate (end-to-end).

    Exercises the real user flow over HTTP: GET /report-illegal (fresh CSRF),
    POST an embedded ~7 KB non-garbage probe photo (p(garbage)≈0.0002
    locally, ~1500x under the 0.3 threshold), then verify the redirect lands
    on ?photo=rejected. A canary failure means the gate stopped rejecting —
    file an admin Notification, dispatch a PHOTO_GATE_BREACH webhook, and
    raise so the RQ retry policy retries the probe before the next sweep.

    No-ops (returns False, no alert) outside a deployed RENDER environment
    so local dev / pytest / CI never probe production. Runs inside its own
    app context via _app_ctx() (RQ workers have none).
    """
    with _app_ctx():
        import io
        import re as _re
        import base64 as _b64
        import requests as _requests

        if os.environ.get('RENDER') != 'true' and not base_url:
            logger.info("photo_gate_canary_skipped", reason="not deployed")
            return False
        base = (base_url or os.environ.get('PHOTO_GATE_CANARY_URL')
                or 'https://smartgarbage.onrender.com').rstrip('/')
        timeout = int(os.environ.get('PHOTO_GATE_CANARY_TIMEOUT', '60'))

        s = _requests.Session()
        s.headers['User-Agent'] = 'SmartGarbage-canary/1.0 (uptime probe)'
        r0 = s.get(f'{base}/report-illegal', params={'canary': int(time.time())},
                   timeout=timeout)
        if r0.status_code != 200:
            raise RuntimeError(f'canary GET /report-illegal -> HTTP {r0.status_code}')
        m = _re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r0.text)
        if not m:
            raise RuntimeError('canary GET /report-illegal: csrf token not found')
        jpeg = _b64.b64decode(_PHOTO_GATE_PROBE_JPEG_B64)
        r = s.post(f'{base}/report-illegal',
                   data={'category': 'Other',
                         'description': 'PHOTO-GATE CANARY probe - non-garbage '
                                        'photo, self-verifying uptime check',
                         'latitude': '12.9716', 'longitude': '77.5946',
                         'ward': 'Test', 'csrf_token': m.group(1)},
                   files={'photo': ('canary_probe.jpg', io.BytesIO(jpeg),
                                    'image/jpeg')},
                   headers={'Referer': f'{base}/report-illegal',
                            'Origin': base},
                   allow_redirects=True, timeout=timeout)
        rejected = ('photo=rejected' in r.url) and \
                   ('does not look like a waste photo' in r.text)
        note = None
        if not rejected:
            rej = _re.search(r'Photo rejected[^<]{0,120}', r.text)
            note = (f'final URL {r.url}; flash: {rej.group(0) if rej else "none"}')

        # Outcome telemetry on /health jobs counters (success + failure both).
        if not rejected:
            alert_photo_gate_breach(note)
            raise RuntimeError(f'photo gate did NOT reject the probe photo ({note})')
        logger.info("photo_gate_canary_ok")
        return True


def schedule_photo_gate_canary(interval_minutes=30):
    """Enqueue the next photo-gate canary run (no-op without Redis)."""
    q = _get_queue()
    if q is None:
        return
    r = _redis()
    if r is not None:
        try:
            if not r.set('sg:photo-gate-canary:scheduled', '1', nx=True,
                         ex=int(interval_minutes * 60)):
                return  # another instance already scheduled the run
        except Exception:
            pass
    q.enqueue_in(timedelta(minutes=interval_minutes), photo_gate_canary_job,
                 retry=_retry_for(photo_gate_canary_job))


def _start_photo_gate_canary_thread(interval_minutes=30):
    """Redis-free fallback scheduler for the canary (deployed hosts only).

    This deployment runs with queue backend 'inline' (no REDIS_URL), so
    RQ-scheduled periodic jobs never fire there; a daemon thread per web
    worker runs the canary inline every PHOTO_GATE_CANARY_INTERVAL seconds
    instead (default 1800). The rejection log's same-client dedupe window
    and the per-day breach-alert marker keep multi-worker runs quiet.
    No-op outside RENDER=true so local dev / pytest / CI never probe prod."""
    if os.environ.get('RENDER') != 'true':
        return
    if _get_queue() is not None:
        return  # Redis broker present: the RQ scheduler owns the cadence
    interval = int(os.environ.get('PHOTO_GATE_CANARY_INTERVAL',
                                  interval_minutes * 60))
    if interval <= 0:
        return  # 0/negative disables the thread loop (RQ path still active)

    import threading

    def _loop():
        time.sleep(45)  # let boot settle (migrations, first requests)
        while True:
            try:
                photo_gate_canary_job()
            except Exception as e:
                # alert_photo_gate_breach already fired inside the job;
                # the next interval retries the probe.
                logger.warning("photo_gate_canary_thread_error", error=str(e))
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True,
                         name='sg-photo-gate-canary')
    t.start()
    logger.info("photo_gate_canary_thread_started", interval_s=interval)
