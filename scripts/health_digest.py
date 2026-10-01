#!/usr/bin/env python3
"""Daily /health digest: ping prod, email a summary of job stats.

Designed to run from GitHub Actions (see .github/workflows/health-digest.yml)
as a Rs. 0 complement to the 15-minute uptime.yml monitor: uptime.yml alerts
when the site is DOWN, this answers the daily "is everything STILL working"
question with numbers — job counters, per-function canary stats, classifier
posture — delivered straight to the panchayat inbox.

How it works:
  1. GET $HEALTH_URL (default https://smartgarbage.onrender.com/health).
  2. Build a markdown digest: checks (database / photo_classifier / mail /
     storage / queue), job counters, per-function table, notes.
  3. Send it via SMTP using the same env-var contract the app's mail chain
     documents (MAIL_SERVER/MAIL_PORT/MAIL_USE_TLS/MAIL_USERNAME/MAIL_PASSWORD,
     recipient DIGEST_TO). SMTP creds are only needed at send time.
  4. Write digest_stats.json (+ digest_email.md) for CI to attach to the job
     summary. Exit codes: 0 healthy, 1 degraded, 2 /health unreachable,
     3 digest built but the email send failed, 4 email skipped because the
     SMTP/DIGEST_* env vars are not configured (nothing failed).

Env:
  HEALTH_URL     target /health URL (default prod)
  SMTP_HOST / SMTP_PORT / SMTP_USE_TLS / SMTP_USERNAME / SMTP_PASSWORD
  DIGEST_FROM    From address (falls back to SMTP_USERNAME)
  DIGEST_TO      comma-separated recipients (required for sending)
  --dry-run      build + print the digest, never send

NOTE on numbers: /health job counters are per-Render-process (they reset on
every deploy). A digest after a deploy shows a young process; the digest text
says so instead of pretending the counters are 24h aggregates.
"""
import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText

import requests

DEFAULT_HEALTH_URL = 'https://smartgarbage.onrender.com/health'
_SMTP_UNCONFIGURED_MSG = ('SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/DIGEST_TO '
                          'not fully set — not sending')


def fetch_health(url):
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    return r.json()


def _fmt(v, dash='—'):
    return dash if v is None else str(v)


def build_digest(health, url):
    """Turn the /health payload into (subject, markdown_body, state)."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    state = health.get('status') or 'unknown'
    checks = health.get('checks', {})
    db = checks.get('database', {})
    clf = checks.get('photo_classifier', {})
    mail = checks.get('mail', {}) or {}
    storage = checks.get('storage', {}) or {}
    queue = health.get('queue', {}) or {}
    jobs = health.get('jobs', {}) or {}
    per_fn = jobs.get('per_function', []) or []

    notes = []
    canary = next((f for f in per_fn if f.get('func') == 'photo_gate_canary_job'), None)
    expected_sweeps = 48  # 30-min cadence
    if canary and (canary.get('runs') or 0) < 20:
        notes.append('⚠️ Canary sweeps look low for a full day (%s runs vs ~%d expected) — '
                     'the process may be young (recent deploy) or the scheduler stalled.'
                     % (canary.get('runs'), expected_sweeps))
    if clf.get('status') != 'active':
        notes.append('⚠️ photo_classifier is NOT active (%s) — the gate is fail-open, '
                     'citizen photos are not being classified.' % _fmt(clf.get('status')))
    if mail.get('transport') in (None, 'unconfigured'):
        notes.append('ℹ️ No SMTP gateway configured (checks.mail: %s) — breach/alert emails '
                     'cannot leave the system until MAIL_* is set on Render.'
                     % _fmt(mail.get('detail')))
    if queue.get('backend') == 'redis' and queue.get('workers') == 0:
        notes.append('🚨 Queue starvation: REDIS_URL set but 0 workers consuming — '
                     'background mail will silently queue and never send.')

    subject = '[SmartGarbage] daily health digest — %s · %s jobs ok (%s)' % (
        state, _fmt(jobs.get('jobs_run')), now)

    lines = [
        '# SmartGarbage daily health digest', '',
        '**When:** %s  ' % now,
        '**Target:** `%s`  ' % url,
        '**Overall:** `%s`' % state, '',
        '## Checks', '',
        '| Check | Result |', '|---|---|',
        '| database | `%s` (%s ms) |' % (_fmt(db.get('status')), _fmt(db.get('response_time_ms'))),
        '| photo_classifier | `%s` — %s |' % (_fmt(clf.get('status')), _fmt(clf.get('detail'))),
        '| mail | `%s` — %s |' % (_fmt(mail.get('transport')), _fmt(mail.get('detail'))),
        '| storage | `%s` |' % _fmt(storage.get('backend')),
        '| queue | backend `%s`, workers `%s` |' % (_fmt(queue.get('backend')), _fmt(queue.get('workers'))),
        '',
        '## Job counters (process lifetime — resets on deploy)', '',
        '| Metric | Value |', '|---|---|',
        '| jobs run | %s |' % _fmt(jobs.get('jobs_run')),
        '| failed | %s |' % _fmt(jobs.get('jobs_failed')),
        '| dead-lettered | %s (rate %s) |' % (_fmt(jobs.get('dead_lettered')), _fmt(jobs.get('dead_letter_rate'))),
        '| avg duration | %s s |' % _fmt(jobs.get('avg_duration_s')),
        '',
        '## Per-function', '',
        '| Function | Runs | Failed | Retries | Dead | Avg s |', '|---|---|---|---|---|---|',
    ]
    for f in sorted(per_fn, key=lambda x: x.get('func') or ''):
        lines.append('| `%s` | %s | %s | %s | %s | %s |' % (
            f.get('func'), _fmt(f.get('runs')), _fmt(f.get('failed')),
            _fmt(f.get('retries')), _fmt(f.get('dead_lettered')), _fmt(f.get('avg_duration_s'))))
    if not per_fn:
        lines.append('| (no job metrics reported) | — | — | — | — | — |')
    if notes:
        lines += ['', '## Notes', ''] + ['- %s' % n for n in notes]
    lines += ['', '---', '',
              'Counters are per-Render-process: a deploy resets them to zero, so a young '
              'process shows small numbers. This digest is the daily companion of the '
              '15-min [uptime monitor](https://github.com/jaganmohan08112005-sketch/SmartgarbageCSP/blob/main/.github/workflows/uptime.yml) '
              '(which pages on downtime); generated by `scripts/health_digest.py`.']
    return subject, '\n'.join(lines), state, notes


def send_email(subject, body):
    host = os.environ.get('SMTP_HOST')
    user = os.environ.get('SMTP_USERNAME')
    password = os.environ.get('SMTP_PASSWORD')
    to = [r.strip() for r in
          (os.environ.get('DIGEST_TO') or '').replace(';', ',').split(',')
          if r.strip()]
    if not host or not user or not password or not to:
        return False, _SMTP_UNCONFIGURED_MSG
    from_addr = os.environ.get('DIGEST_FROM') or user
    port = int(os.environ.get('SMTP_PORT', 587))
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = ', '.join(to)
    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if os.environ.get('SMTP_USE_TLS', 'true').lower() in ('true', '1', 'yes'):
                server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, to, msg.as_string())
        return True, 'sent to %s' % ', '.join(to)
    except Exception as e:
        return False, 'SMTP send failed: %s' % e


def main():
    # Windows consoles default to cp1252 and choke on the digest's em-dashes/
    # emoji (UnicodeEncodeError) AFTER the files were written — force UTF-8
    # with replacement so printing can never crash the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--health-url', default=os.environ.get('HEALTH_URL', DEFAULT_HEALTH_URL))
    ap.add_argument('--stats-file', default='digest_stats.json')
    ap.add_argument('--dry-run', action='store_true',
                    help='build and print the digest; never send')
    args = ap.parse_args()

    try:
        health = fetch_health(args.health_url)
    except Exception as e:
        print('FATAL: /health unreachable at %s: %s' % (args.health_url, e))
        subject = '[SmartGarbage] daily health digest FAILED — /health unreachable (%s)' % (
            datetime.now(timezone.utc).strftime('%Y-%m-%d'))
        body = 'The daily digest could not reach %s (%s).\n\n' % (args.health_url, e)
        body += 'The site may be down or paused — check the Render dashboard and the\n'
        body += '15-minute uptime monitor issues. This failure notice was generated by\n'
        body += 'scripts/health_digest.py.'
        if not args.dry_run:
            ok, detail = send_email(subject, body)
            print('failure-notice email: %s (%s)' % ('sent' if ok else 'NOT sent', detail))
        sys.exit(2)

    subject, body, state, notes = build_digest(health, args.health_url)

    stats = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'health_url': args.health_url,
        'status': state,
        'jobs': health.get('jobs', {}),
        'checks': {k: health.get('checks', {}).get(k) for k in
                   ('database', 'photo_classifier', 'mail', 'storage')},
        'notes': notes,
    }
    with open(args.stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)
    md_file = os.path.splitext(args.stats_file)[0] + '_email.md'
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(body + '\n')

    print(subject)
    print()
    print(body)

    if args.dry_run:
        print('\n[dry-run] digest NOT sent (use SMTP_* env without --dry-run to send)')
        return 0 if state == 'healthy' else 1

    ok, detail = send_email(subject, body)
    print('\nsend: %s (%s)' % ('ok' if ok else 'FAILED', detail))
    if not ok and detail == _SMTP_UNCONFIGURED_MSG:
        return 4  # email skipped, not failed — nothing to alert on
    if state == 'healthy':
        return 0 if ok else 3
    return 1 if ok else 3


if __name__ == '__main__':
    sys.exit(main())
