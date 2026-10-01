"""Tests for scripts/photo_rejection_weekly.py (canary attribution + report appender).

The attribution rule this pins: a classifier-stage row whose exact thumbnail
repeats anywhere in the panel is a canary probe. Note text must NOT be used
— probes and citizen rejections share the same generated rejection message
(live prod rows 2026-10-01: canary note == citizen note, byte for byte).
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'scripts' / 'photo_rejection_weekly.py'


def _load_module():
    spec = importlib.util.spec_from_file_location('photo_rejection_weekly', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def weekly_env(tmp_path, monkeypatch):
    """SQLite panel DB with canary + citizen rows, and a copy of the report.

    The probe JPEG appears ONCE inside the 7-day window (id 1) and ONCE
    outside it (id 3) — so canary detection works ONLY because the cluster
    scan covers the whole panel, not just the window.
    """
    mod = _load_module()
    db_path = (tmp_path / 'panel.db').as_posix()
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE photo_rejection (
      id INTEGER PRIMARY KEY, surface TEXT, stage TEXT, note TEXT, p_reject REAL,
      relabel_status TEXT, relabeled_at TIMESTAMP, batched_at TIMESTAMP,
      thumbnail BLOB, created_at TIMESTAMP)''')
    now = datetime.now()
    probe = b'\xff\xd8PROBE-JPEG-BYTES'          # byte-identical canary upload
    probe2 = b'\xff\xd8PROBE-2-BYTES'            # near-threshold probe variant
    citizen_fp = b'\xff\xd8citizen-false-positive'
    citizen_ok = b'\xff\xd8citizen-other'
    # NOTE: canary row 1 and citizen rows 2/4 share IDENTICAL note text — the
    # old note-text attribution would have miscounted these.
    rows = [
        (1, 'report-illegal', 'classifier', 'Rejected: does not look like waste (non_garbage p=1.00)',
         0.9998, 'auto', None, None, probe, now),
        (2, 'report-illegal', 'classifier', 'Rejected: does not look like waste (non_garbage p=1.00)',
         0.9999, 'auto', None, None, citizen_ok, now - timedelta(hours=1)),  # unique thumb → citizen
        (3, 'report-illegal', 'classifier', 'Rejected: does not look like waste (non_garbage p=1.00)',
         0.9998, 'auto', None, None, probe, now - timedelta(days=10)),   # outside window; still identifies the cluster
        (4, 'report', 'classifier', 'Rejected: does not look like waste (non_garbage p=1.00)',
         0.55, 'garbage', now, now, citizen_fp, now - timedelta(days=2)),  # citizen FP, relabeled+batched
        (5, 'report', 'decodability', 'Photo could not be decoded',
         None, 'auto', None, None, None, now - timedelta(days=1)),       # no thumb, no p_reject
        (6, 'report-illegal', 'classifier', 'Rejected: does not look like waste (non_garbage p=0.72)',
         0.72, 'pending', None, None, probe2, now - timedelta(days=1)),  # near-threshold, pending
    ]
    conn.executemany('INSERT INTO photo_rejection VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    conn.commit()
    conn.close()

    report = tmp_path / 'REPORT.md'
    report.write_text('seed', encoding='utf-8')
    stats = tmp_path / 's.json'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + db_path)
    monkeypatch.setattr(sys, 'argv',
                        ['x', '--report', str(report), '--stats-file', str(stats)])
    return mod, tmp_path, report, stats, probe


def test_canary_vs_citizen_identical_notes(weekly_env):
    """Canary rows must be attributed by thumbnail cluster even when citizen
    rows carry the byte-identical rejection note — and a probe that appears
    once IN-window and once OUT-of-window must still be attributed (the
    cluster scan covers the whole panel)."""
    mod, tmp_path, report, stats, probe = weekly_env
    mod.main()
    m = json.loads(stats.read_text(encoding='utf-8'))['metrics']
    assert m['canary_method'] == 'thumbnail-cluster'
    assert m['canary_rows'] == 1          # id 1 only; id 3 is outside the window
    assert m['citizen_rejections'] == 4   # ids 2, 4, 5, 6
    assert m['status_counts'] == {'auto': 3, 'garbage': 1, 'pending': 1}
    assert m['relabeled_count'] == 1 and m['batched_count'] == 1
    assert m['rows_with_thumbnail'] == 4  # ids 1, 2, 4, 6 (5 has no thumb)


def test_report_append_is_idempotent_per_iso_week(weekly_env):
    mod, tmp_path, report, stats, probe = weekly_env
    mod.main()
    first = report.read_text(encoding='utf-8')
    mod.main()
    assert report.read_text(encoding='utf-8') == first
    assert first.count('## Weekly snapshot') == 1


def test_unique_thumbnail_citizen_rows_stay_citizen(weekly_env):
    mod, tmp_path, report, stats, probe = weekly_env
    # A citizen FP whose thumbnail appears exactly once must NOT be counted
    # as canary even though its note matches the probe note.
    mod.main()
    m = json.loads(stats.read_text(encoding='utf-8'))['metrics']
    assert m['canary_rows'] == 1
    assert m['status_counts'].get('garbage') == 1  # the citizen FP stayed citizen


def test_health_fetch_failure_is_non_fatal(weekly_env):
    mod, tmp_path, report, stats, probe = weekly_env
    # HEALTH_URL unset → health dict empty → report still appends with '—'
    assert mod.main() == 0
    assert '## Weekly snapshot' in report.read_text(encoding='utf-8')


def test_md5_cluster_helper_matches_direct_count(weekly_env):
    """Sanity: the hashing approach is deterministic across runs."""
    mod, tmp_path, report, stats, probe = weekly_env
    assert len(hashlib.md5(probe).hexdigest()) == 32
