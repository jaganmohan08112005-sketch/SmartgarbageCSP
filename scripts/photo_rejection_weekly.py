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

p_reject DRIFT: the classifier's non-garbage score (p_reject) is also tracked
against a committed training baseline (scripts/photo_classifier_baseline.json,
written from the validation-set ROC + the first-24h canary reference). The
canary re-uploads one byte-identical probe, so its logged p_reject is
deterministic for a given model + preprocessing + threshold — a shift there
alerts on an unexpected model swap, a preprocessing change, or a moved
operating threshold WITHOUT waiting for a citizen complaint (the same failure
class as the 2026-09-29 over-strict threshold slip).

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
HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(HERE, 'photo_classifier_baseline.json')

# Embedded fallback mirroring scripts/photo_classifier_baseline.json so a
# missing/unreadable baseline degrades to a working check instead of crashing.
DEFAULT_BASELINE = {
    'schema': 'photo_classifier_baseline/1',
    'model': 'photo_classifier.onnx',
    'threshold': 0.7,
    'canary_p_reject': {'n': 20, 'mean': 0.9999, 'min': 0.9998, 'max': 1.0},
    'classifier_p_reject': {'n': 25, 'mean': 0.9996, 'min': 0.9998, 'max': 1.0},
    'tolerance': {'mean_abs': 0.01, 'min_abs': 0.005, 'floor': 0.9},
}


def load_baseline(path=None):
    """Read the committed training baseline; fall back to the embedded copy.

    Returns (baseline_dict, source_label). Never raises: a missing or corrupt
    file is a degraded, not fatal, state — the drift check still runs against
    the embedded reference values.
    """
    path = path or BASELINE_PATH
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get('canary_p_reject'):
            data['_source'] = path
            return data, path
        print('baseline file %s lacks canary_p_reject — using embedded baseline' % path)
    except FileNotFoundError:
        print('baseline file %s not found — using embedded baseline' % path)
    except Exception as e:
        print('baseline file %s unreadable (%s) — using embedded baseline' % (path, e))
    fallback = dict(DEFAULT_BASELINE)
    fallback['_source'] = 'embedded-default'
    return fallback, 'embedded-default'


def _dist(values):
    """min / mean / max / p50 / n over the non-None p_reject values."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {'n': 0, 'mean': None, 'min': None, 'max': None, 'p50': None}
    return {
        'n': len(vals),
        'mean': sum(vals) / len(vals),
        'min': vals[0],
        'max': vals[-1],
        'p50': vals[len(vals) // 2],
    }


def assess_drift(m, baseline):
    """Compare live p_reject scores against the training baseline.

    Basis: the CANARY rows when present (byte-identical fixed input → the
    cleanest drift signal), else all classifier rows. Returns a dict with a
    'status' of 'ok', 'drift', or 'insufficient-data', the numbers behind the
    verdict, and human-readable 'alerts'.
    """
    tol = baseline.get('tolerance') or {}
    mean_abs = float(tol.get('mean_abs', 0.01))
    min_abs = float(tol.get('min_abs', 0.005))
    floor = float(tol.get('floor', 0.9))

    live = m.get('canary_p_reject') or {}
    basis = 'canary'
    if not live.get('n'):
        live = m.get('classifier_p_reject') or {}
        basis = 'classifier'

    # Compare like with like: canary rows against the canary baseline block,
    # classifier rows against the classifier block.
    base = baseline.get('canary_p_reject' if basis == 'canary'
                         else 'classifier_p_reject') or {}
    base_mean, base_min = base.get('mean'), base.get('min')

    out = {
        'status': 'insufficient-data',
        'basis': basis,
        'baseline_source': baseline.get('_source', 'unknown'),
        'baseline_threshold': baseline.get('threshold'),
        'baseline_mean': base_mean,
        'baseline_min': base_min,
        'tolerance': {'mean_abs': mean_abs, 'min_abs': min_abs, 'floor': floor},
        'live_n': live.get('n', 0),
        'live_mean': live.get('mean'),
        'live_min': live.get('min'),
        'live_max': live.get('max'),
        'delta_mean': None,
        'alerts': [],
    }
    if not live.get('n'):
        out['alerts'] = ['no classifier p_reject values in the window — cannot assess drift']
        return out

    alerts = []
    live_mean, live_min = live.get('mean'), live.get('min')
    if base_mean is not None and live_mean is not None:
        out['delta_mean'] = live_mean - base_mean
        if abs(out['delta_mean']) > mean_abs:
            alerts.append(
                'p_reject %s mean shifted to %.4f from the training baseline %.4f '
                '(delta %+.4f, tolerance \u00b1%.4f)' % (
                    basis, live_mean, base_mean, out['delta_mean'], mean_abs))
    if base_min is not None and live_min is not None and live_min < base_min - min_abs:
        alerts.append(
            'p_reject floor dropped to %.4f from the training baseline min %.4f '
            '(tolerance %.4f)' % (live_min, base_min, min_abs))
    if live_min is not None and live_min < floor:
        alerts.append(
            'a %s rejection scored %.4f \u2014 below the %.2f sanity floor '
            '(model swap / preprocessing change / moved threshold)' % (basis, live_min, floor))
    out['alerts'] = alerts
    out['status'] = 'drift' if alerts else 'ok'
    return out


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
    classifier = [r for r in rows if r['stage'] == 'classifier']
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
        # Distribution stats for the drift tracker: canary rows are the
        # byte-identical probe (cleanest signal); classifier rows are the
        # fallback basis when the window holds no canary rejection.
        'canary_p_reject': _dist([r['p_reject'] for r in canary]),
        'classifier_p_reject': _dist([r['p_reject'] for r in classifier]),
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


def append_report(path, m, h, drift=None):
    now = datetime.now(timezone.utc)
    heading = week_heading(now)
    with open(path, encoding='utf-8') as f:
        existing = f.read()
    if heading in existing:
        print('SKIP: %s already present in the report (idempotent per ISO week)' % heading)
        return False

    def fmt_p(v):
        return '—' if v is None else '%.4f' % v

    drift = drift or {'status': 'insufficient-data', 'basis': 'canary',
                      'alerts': [], 'tolerance': {}}
    dstat = drift.get('status')
    verdict = {'ok': '✅ none', 'drift': '🚨 **DETECTED**'
               }.get(dstat, '⏭️ not enough data')
    tol_mean = (drift.get('tolerance') or {}).get('mean_abs')
    drift_line = ('| p_reject drift vs training baseline | %s — %s mean %s vs '
                  'baseline %s (tol ±%s) |') % (
        verdict, drift.get('basis', '—'), fmt_p(drift.get('live_mean')),
        fmt_p(drift.get('baseline_mean')), fmt_p(tol_mean))

    sc = m['status_counts']
    rows = [
        '| Metric | Value |', '|---|---|',
        '| Rows in window (7 d) | %d |' % m['rows'],
        '| Citizen uploads rejected | **%d** |' % m['citizen_rejections'],
        '| Canary-probe rows | %d |' % m['canary_rows'],
        '| p_reject range (logged rows) | %s – %s |' % (fmt_p(m['p_reject_min']), fmt_p(m['p_reject_max'])),
        drift_line,
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
    ]
    section = '\n\n%s\n\n' % heading + '\n'.join(rows)
    if dstat == 'drift':
        section += '\n\n**p_reject drift alerts** (training baseline `%s`):\n\n' % drift.get('baseline_source', '—')
        section += '\n'.join('- %s' % a for a in drift.get('alerts', [])) + '\n'
    with open(path, 'a', encoding='utf-8') as f:
        f.write(section)
    print('APPENDED: %s' % heading)
    return True


def _open_or_update_issue(api, hdr, title, body, added, label='photo-gate'):
    """Open the titled issue (once) or append the body as a new comment.

    Best-effort: an issue-API failure is logged and swallowed — the report
    append has already succeeded by the time this runs and must not be lost.
    """
    existing = requests.get('%s/issues?state=open&per_page=50' % api,
                            headers=hdr, timeout=30).json()
    hit = next((i for i in existing if isinstance(i, dict) and i.get('title') == title), None)
    if hit:
        requests.post(hit['comments_url'], headers=hdr,
                      json={'body': body}, timeout=30)
        print('updated issue #%s (%s)' % (hit['number'], title))
    elif added:
        r = requests.post('%s/issues' % api, headers=hdr,
                          json={'title': title, 'body': body, 'labels': [label]},
                          timeout=30)
        print('opened issue #%s (%s)' % (r.json().get('number'), title))
    else:
        print('issue %r not open and nothing new to append' % title)


def file_or_update_issue(m, added, drift=None):
    """File/refresh the weekly follow-up issue, plus a drift issue when needed."""
    repo = os.environ.get('GH_REPOSITORY')
    token = os.environ.get('GH_TOKEN')
    if not repo or not token:
        return
    api = 'https://api.github.com/repos/%s' % repo
    hdr = {'Authorization': 'token %s' % token, 'Accept': 'application/vnd.github+json'}
    try:
        needs = m['citizen_rejections'] > 0 or m['status_counts'].get('pending', 0) > 0
        if needs:
            title = '[photo-gate] weekly reliability follow-up'
            body = ('Citizen rejections last 7d: **%d** · pending relabels: %d (ids %s)\n\n'
                    'Review the admin panel → relabel or dismiss → export retrain-batch.zip.\n\n'
                    '_Auto-filed by scripts/photo_rejection_weekly.py._') % (
                m['citizen_rejections'], m['status_counts'].get('pending', 0),
                ', '.join(map(str, m['pending_ids'])) or '—')
            _open_or_update_issue(api, hdr, title, body, added)
        else:
            print('no relabel follow-up needed')

        drift = drift or {}
        if drift.get('status') == 'drift':
            dtitle = '[photo-gate] p_reject threshold drift detected'
            dbody = ('The weekly tracker found the live rejection scores have moved '
                     'away from the training baseline.\n\n'
                     '| Field | Value |\n|---|---|\n'
                     '| Basis | %s rows |\n'
                     '| Live mean p_reject | %s |\n'
                     '| Training baseline mean | %s |\n'
                     '| Delta | %s |\n'
                     '| Live min / max | %s / %s |\n'
                     '| Baseline min | %s |\n'
                     '| Baseline source | `%s` |\n\n'
                     '**Alerts:**\n\n%s\n\n'
                     'Investigate in order: (1) `PHOTO_CLASSIFIER_THRESHOLD` on Render '
                     '(a moved threshold changes which scores are logged — see the '
                     '2026-09-29 over-strict slip); (2) the bundled '
                     '`app/photo_classifier.onnx` — was a retrain shipped without '
                     'refreshing the baseline?; (3) the preprocessing/resize path in '
                     '`app/routes/__init__.py::_classify_garbage_photo`. The canary '
                     'probe is byte-identical every sweep, so a shift is never noise.\n\n'
                     '_Auto-filed by scripts/photo_rejection_weekly.py._') % (
                drift.get('basis', '—'), fmt_num(drift.get('live_mean')),
                fmt_num(drift.get('baseline_mean')), fmt_signed(drift.get('delta_mean')),
                fmt_num(drift.get('live_min')), fmt_num(drift.get('live_max')),
                fmt_num(drift.get('baseline_min')), drift.get('baseline_source', '—'),
                '\n'.join('- %s' % a for a in drift.get('alerts', [])) or '- (none)')
            # added=True: a drift alert must file even on a re-run so it is never
            # silently dropped; the open-issue check keeps it comment-only then.
            _open_or_update_issue(api, hdr, dtitle, dbody, True)
    except Exception as e:
        print('issue fan-out skipped (non-fatal): %s' % e)


def fmt_num(v):
    return '—' if v is None else '%.4f' % v


def fmt_signed(v):
    return '—' if v is None else '%+.4f' % v


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
    ap.add_argument('--baseline', default=None,
                    help='training baseline JSON (default scripts/photo_classifier_baseline.json; '
                         'falls back to the embedded copy if missing)')
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

    baseline, _src = load_baseline(args.baseline)
    drift = assess_drift(m, baseline)

    h = collect_health(os.environ['HEALTH_URL']) if os.environ.get('HEALTH_URL') else {}
    with open(args.stats_file, 'w', encoding='utf-8') as f:
        json.dump({'metrics': m, 'health': h, 'drift': drift}, f, indent=2, default=str)

    print(json.dumps(m, indent=2, default=str))
    print('DRIFT: %s (%s basis, live mean %s vs baseline %s)' % (
        drift['status'], drift.get('basis'), fmt_num(drift.get('live_mean')),
        fmt_num(drift.get('baseline_mean'))))
    for alert in drift.get('alerts', []):
        print('  - %s' % alert)
    added = append_report(args.report, m, h, drift)
    file_or_update_issue(m, added, drift)
    return 0


if __name__ == '__main__':
    sys.exit(main())
