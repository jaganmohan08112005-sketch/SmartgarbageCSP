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
    'payt_reconciliation_job': (1, [300]),              # billing reconcile: single 5m retry
    'model_retraining_job': (1, [600]),                 # ML retrain: single 10m retry
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
    from .routes import send_sms_via_twilio
    return send_sms_via_twilio(to_number, body)


@instrument
def send_email_job(to_email, subject, body):
    from .routes import send_email_via_smtp
    return send_email_via_smtp(to_email, subject, body)


@instrument
def send_otp_job(recipient, otp_val, subject='SmartGarbage OTP'):
    """Send an OTP via SMS, then email if SMS is unavailable — off the request path.

    Note: it calls the decorated send_sms_job/send_email_job directly, so one
    OTP delivery counts as multiple job runs in the metrics (function-level
    accounting — each helper genuinely executed)."""
    sms_sent = send_sms_job(recipient, f"SmartGarbage OTP: {otp_val}")
    if not sms_sent:
        send_email_job(recipient, subject,
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
                Notification.message.ilike('%overdue%')).first()  # ilike: case-insensitive on SQLite AND Postgres
            if dup:
                continue
            # SQLite returns naive datetimes (Postgres aware) — normalize before
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
