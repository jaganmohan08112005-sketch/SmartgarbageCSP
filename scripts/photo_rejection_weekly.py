#!/usr/bin/env python3
"""Append a weekly reliability row to docs/PHOTO_GATE_RELIABILITY_REPORT.md.

Runs from GitHub Actions (.github/workflows/reliability-report.yml) with the
production DATABASE_URL as a secret. Reads the admin rejection panel's data
source — the `photo_rejection` table — for the trailing 7 days via a plain
SQLAlchemy connection (no Flask app / model imports needed), plus /health for
the current job counters, and appends a dated section to the report.
Optionally opens/updates a GitHub issue when human action is pending.

What counts as a canary probe row: the canary uploads the SAME probe JPEG on
every sweep, so a classifier-stage row is canary-attributed when its exact
thumbnail hash repeats anywhere in the panel. Note text canNOT be used for
attribution: probe rows and citizen rows share the same generated rejection
message ("Rejected: does not look like waste (non_garbage p=…)"). Known
caveat: a citizen re-submitting one byte-identical photo would cluster the
same way — rare, and the issue text names row ids so a human can tell
instantly.

The appended section is additive and idempotent per ISO week: the script
checks for its own heading and skips if that week was already recorded.

Env:
  DATABASE_URL       required — production Postgres (Supabase) URL
  HEALTH_URL         optional — /health for job counters (skipped if unset)
  GH_REPOSITORY      optional — 'owner/repo' for the follow-up issue
  GH_TOKEN           optional — token to create/update the follow-up issue
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
import sqlalchemy as sa

REPORT = os.path.join('docs', 'PHOTO_GATE_RELIABILITY_REPORT.md')


def _db_url():
    url = os.environ.get('DATABASE_URL') or ''
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)  # SQLAlchemy 1.4+
    if 'supabase' in url and 'sslmode=' not in url:
        url += ('&' if '?' in url else '?') + 'sslmode=require'
    return url


def collect(conn):
    """All panel metrics for the trailing 7 days, in one pass."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    cols = {c['name'] for c in sa.inspect(conn).get_columns('photo_rejection')}
    time_col = 'timestamp' if 'timestamp' in cols else 'created_at'

    rows = conn.execute(sa.text(
        'SELECT id, surface, stage, note, p_reject, relabel_status, '
        'relabeled_at, batched_at, (thumbnail IS NOT NULL) AS has_thumb, '
        'thumbnail, '
        f'{time_col} AS ts FROM photo_rejection WHERE {time_col} >= :since '
        'ORDER BY id'
    ), {'since': since}).mappings().all()

    # Canary attribution: hash EVERY classifier-stage thumbnail in the panel
    # (not just the window — a probe cluster keeps identifying rows after the
    # probe started before the window) and treat any hash seen 2+ times as a
    # canary probe. Computed in Python so the check is portable (no SQL md5).
    thumb_hashes = Counter(
        hashlib.md5(r['thumbnail']).hexdigest()
        for r in conn.execute(sa.text(
            'SELECT thumbnail FROM photo_rejection '
            "WHERE stage = 'classifier' AND thumbnail IS NOT NULL")).mappings()
        if r['thumbnail'])
    probe_hashes = {h for h, n in thumb_hashes.items() if n > 1}

    is_canary = lambda r: (r['stage'] == 'classifier' and r['has_thumb']
                           and hashlib.md5(r['thumbnail']).hexdigest() in probe_hashes)
    citizen = [r for r in rows if not is_canary(r)]
    canary = [r for r in rows if is_canary(r)]
    statuses = Counter(r['relabel_status'] for r in rows)

    total_rejections = conn.execute(
        sa.text('SELECT COUNT(*) FROM photo_rejection')).scalar()

    pending_rows = [r for r in rows if r['relabel_status'] == 'pending']
    return {
        'window_days': 7,
        'time_column': time_col,
        'canary_method': 'thumbnail-cluster',
        'rows': len(rows),
        'citizen_rejections': len(citizen),
        'canary_rows': len(canary),
        'p_reject_min': min((r['p_reject'] for r in rows if r['p_reject'] is not None), default=None),
        'p_reject_max': max((r['p_reject'] for r in rows if r['p_reject'] is not None), default=None),
        'status_counts': dict(statuses),
        'pending_ids': [r['id'] for r in pending_rows],
        'relabeled_count': sum(1 for r in rows if r['relabeled_at'] is not None),
        'batched_count': sum(1 for r in rows if r['batched_at'] is not None),
        'rows_with_thumbnail': sum(1 for r in rows if r['has_thumb']),
        'total_rows_all_time': total_rejections,
    }


def collect_health(url):
    try:
        h = requests.get(url, timeout=30).json()
    except Exception as e:
        return {'error': str(e)}
    jobs = h.get('jobs', {}) or {}
    canary = next((f for f in jobs.get('per_function', []) if f.get('func') == 'photo_gate_canary_job'), None)
    return {
        'status': h.get('status'),
        'classifier': (h.get('checks', {}).get('photo_classifier', {}) or {}).get('status'),
        'jobs_run': jobs.get('jobs_run'),
        'jobs_failed': jobs.get('jobs_failed'),
        'dead_lettered': jobs.get('dead_lettered'),
        'canary_runs_process': (canary or {}).get('runs'),
        'canary_failed_process': (canary or {}).get('failed'),
    }


def week_heading(now):
    iso = now.isocalendar()
    return '## Weekly snapshot — %04d-W%02d (window ending %s)' % (
        iso[0], iso[1], now.strftime('%Y-%m-%d %H:%M UTC'))


def append_report(path, m, h):
    now = datetime.now(timezone.utc)
    heading = week_heading(now)
    with open(path, encoding='utf-8') as f:
        existing = f.read()
    if heading in existing:
        print('SKIP: %s already present in the report (idempotent per ISO week)' % heading)
        return False

    def fmt_p(v):
        return '—' if v is None else '%.4f' % v

    sc = m['status_counts']
    section = '\n\n%s\n\n' % heading + '\n'.join([
        '| Metric | Value |', '|---|---|',
        '| Rows in window (7 d) | %d |' % m['rows'],
        '| Citizen uploads rejected | **%d** |' % m['citizen_rejections'],
        '| Canary-probe rows | %d |' % m['canary_rows'],
        '| p_reject range (logged rows) | %s – %s |' % (fmt_p(m['p_reject_min']), fmt_p(m['p_reject_max'])),
        '| Relabel: auto / pending / garbage / not_garbage / dismissed | %s |' % ' / '.join(
            str(sc.get(k, 0)) for k in ('auto', 'pending', 'garbage', 'not_garbage', 'dismissed')),
        '| Human relabel actions | %d |' % m['relabeled_count'],
        '| Exported into a retrain batch | %d rows |' % m['batched_count'],
        '| Rows with thumbnail (export-eligible) | %d / %d |' % (m['rows_with_thumbnail'], m['rows']),
        '| Panel size (all-time rows) | %d (pruned cap applies) |' % m['total_rows_all_time'],
        '| /health at snapshot | status `%s`, classifier `%s`, jobs %s run / %s failed / %s dead |' % (
            h.get('status', '—'), h.get('classifier', '—'),
            h.get('jobs_run', '—'), h.get('jobs_failed', '—'), h.get('dead_lettered', '—')),
        '| Canary sweeps (current process) | %s runs, %s failed |' % (
            h.get('canary_runs_process', '—'), h.get('canary_failed_process', '—')),
        '',
        'Auto-appended by `scripts/photo_rejection_weekly.py` '
        '(idempotent per ISO week). Canary rows are classifier-stage rows whose '
        'exact thumbnail repeats across the panel (the probe JPEG is byte-identical '
        'every sweep); note text is NOT used because probes and citizen rejections '
        'share the same generated message.',
    ])
    with open(path, 'a', encoding='utf-8') as f:
        f.write(section)
    print('APPENDED: %s' % heading)
    return True


def file_or_update_issue(m, added):
    """Open/refresh one 'weekly reliability follow-up' issue when humans must act.

    Best-effort: an issue-API failure is logged and swallowed — the report
    append has already succeeded by the time this runs and must not be lost.
    """
    repo = os.environ.get('GH_REPOSITORY')
    token = os.environ.get('GH_TOKEN')
    if not repo or not token:
        return
    needs = m['citizen_rejections'] > 0 or m['status_counts'].get('pending', 0) > 0
    if not needs:
        print('no human follow-up needed; no issue filed')
        return
    api = 'https://api.github.com/repos/%s' % repo
    hdr = {'Authorization': 'token %s' % token, 'Accept': 'application/vnd.github+json'}
    title = '[photo-gate] weekly reliability follow-up'
    body = ('Citizen rejections last 7d: **%d** · pending relabels: %d (ids %s)\n\n'
            'Review the admin panel → relabel or dismiss → export retrain-batch.zip.\n\n'
            '_Auto-filed by scripts/photo_rejection_weekly.py._') % (
        m['citizen_rejections'], m['status_counts'].get('pending', 0),
        ', '.join(map(str, m['pending_ids'])) or '—')
    try:
        existing = requests.get('%s/issues?state=open&per_page=50' % api,
                                headers=hdr, timeout=30).json()
        hit = next((i for i in existing if isinstance(i, dict) and i.get('title') == title), None)
        if hit:
            requests.post(hit['comments_url'], headers=hdr,
                          json={'body': body}, timeout=30)
            print('updated follow-up issue #%s' % hit['number'])
        elif added:
            r = requests.post('%s/issues' % api, headers=hdr,
                              json={'title': title, 'body': body, 'labels': ['photo-gate']},
                              timeout=30)
            print('opened follow-up issue #%s' % r.json().get('number'))
    except Exception as e:
        print('issue fan-out skipped (non-fatal): %s' % e)


def main():
    # Windows consoles default to cp1252 and can choke on unicode output
    # (—, emoji) — force UTF-8 with replacement so printing never crashes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--report', default=REPORT)
    ap.add_argument('--stats-file', default='weekly_stats.json')
    args = ap.parse_args()

    url = _db_url()
    if not url:
        print('FATAL: DATABASE_URL is required (production Supabase Postgres)')
        return 2

    engine = sa.create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            m = collect(conn)
    finally:
        engine.dispose()

    h = collect_health(os.environ['HEALTH_URL']) if os.environ.get('HEALTH_URL') else {}
    with open(args.stats_file, 'w', encoding='utf-8') as f:
        json.dump({'metrics': m, 'health': h}, f, indent=2, default=str)

    print(json.dumps(m, indent=2, default=str))
    added = append_report(args.report, m, h)
    file_or_update_issue(m, added)
    return 0


if __name__ == '__main__':
    sys.exit(main())
