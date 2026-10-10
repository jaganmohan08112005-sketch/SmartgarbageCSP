"""Tests for scripts/ingest_retrain_batch.py.

Pins the retrain-loop ingest contract: a retrain-batch ZIP lands its
garbage/rejection_<id>.jpg images in _dataset/train/garbage (NEVER val/),
foreign or traversal members are rejected unread, a re-run is idempotent via
the ledger, and the new model is promoted only when the validation-accuracy
gate passes. No torch required — training itself is not exercised here.
"""
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / 'scripts' / 'ingest_retrain_batch.py'


def _load_module():
    spec = importlib.util.spec_from_file_location('ingest_retrain_batch', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _jpeg_bytes(size=(120, 120)):
    buf = io.BytesIO()
    Image.new('RGB', size, (120, 30, 30)).save(buf, 'JPEG')
    return buf.getvalue()


def _make_zip(path, members):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, blob in members.items():
            zf.writestr(name, blob)
    return path


def _dataset(tmp_path):
    root = tmp_path / '_dataset'
    for cls in ('garbage', 'non_garbage'):
        (root / 'train' / cls).mkdir(parents=True)
        (root / 'val' / cls).mkdir(parents=True)
    return root


def test_ingest_places_images_in_train_garbage(tmp_path):
    mod = _load_module()
    ds = _dataset(tmp_path)
    zf = _make_zip(tmp_path / 'retrain_batch_x.zip', {
        'garbage/rejection_11.jpg': _jpeg_bytes(),
        'garbage/rejection_12.jpg': _jpeg_bytes(),
        'manifest.csv': b'id,surface,stage\n11,report,classifier\n12,report,classifier\n',
    })
    stats, ledger, err = mod.ingest(zf, ds, ds / 'retrain_ingested.json')
    assert err is None
    assert sorted(stats['ingested']) == ['11', '12']
    assert stats['manifest_rows'] == 2
    assert (ds / 'train' / 'garbage' / 'rejection_11.jpg').exists()
    assert (ds / 'train' / 'garbage' / 'rejection_12.jpg').exists()
    # The evaluation set must never receive retrain images.
    assert list((ds / 'val' / 'garbage').iterdir()) == []
    assert set(ledger) == {'11', '12'}


def test_zip_slip_and_foreign_members_are_rejected(tmp_path):
    mod = _load_module()
    ds = _dataset(tmp_path)
    zf = _make_zip(tmp_path / 'retrain_batch_slip.zip', {
        'garbage/ok.jpg': _jpeg_bytes(),
        '../evil.jpg': _jpeg_bytes(),
        '/abs.jpg': _jpeg_bytes(),
        'val/garbage/sneaky.jpg': _jpeg_bytes(),
        'non_garbage/other.jpg': _jpeg_bytes(),
    })
    stats, _ledger, err = mod.ingest(zf, ds, ds / 'retrain_ingested.json')
    assert err is None
    assert stats['ingested'] == ['ok.jpg']
    assert set(stats['rejected']) == {'../evil.jpg', '/abs.jpg',
                                      'val/garbage/sneaky.jpg', 'non_garbage/other.jpg'}
    # train/garbage holds exactly the one accepted image; nothing escaped.
    assert [p.name for p in (ds / 'train' / 'garbage').iterdir()] == ['ok.jpg']
    assert not (tmp_path / 'evil.jpg').exists()
    assert list((ds / 'val' / 'garbage').iterdir()) == []


def test_second_run_is_idempotent(tmp_path):
    mod = _load_module()
    ds = _dataset(tmp_path)
    zf = _make_zip(tmp_path / 'retrain_batch_idem.zip', {
        'garbage/rejection_21.jpg': _jpeg_bytes(),
    })
    ledger_path = ds / 'retrain_ingested.json'
    first, _l, _e = mod.ingest(zf, ds, ledger_path)
    assert first['ingested'] == ['21']
    second, _l2, _e2 = mod.ingest(zf, ds, ledger_path)
    assert second['ingested'] == []
    assert second['skipped_known'] == ['21']


def test_invalid_image_member_is_skipped_not_written(tmp_path):
    mod = _load_module()
    ds = _dataset(tmp_path)
    zf = _make_zip(tmp_path / 'retrain_batch_bad.zip', {
        'garbage/rejection_31.jpg': b'this is not a jpeg',
    })
    stats, _l, err = mod.ingest(zf, ds, ds / 'retrain_ingested.json')
    assert err is None
    assert stats['ingested'] == []
    assert stats['invalid'] == ['rejection_31.jpg']
    assert not (ds / 'train' / 'garbage' / 'rejection_31.jpg').exists()


def test_zip_with_no_garbage_members_reports_layout_error(tmp_path):
    mod = _load_module()
    ds = _dataset(tmp_path)
    zf = _make_zip(tmp_path / 'retrain_batch_empty.zip', {
        'manifest.csv': b'id,surface\n',
        'val/garbage/x.jpg': _jpeg_bytes(),
    })
    _stats, _l, err = mod.ingest(zf, ds, ds / 'retrain_ingested.json')
    assert err and 'no garbage' in err


def test_parse_val_acc_and_gate():
    mod = _load_module()
    text = '[ep2] val_acc=0.960 ...\nOK best_val_acc=0.966\n'
    assert mod.parse_val_acc(text) == 0.966
    assert mod.parse_val_acc('no marker here') is None
    assert mod.gate_ok(0.966, 0.90) is True
    assert mod.gate_ok(0.825, 0.90) is False       # the discarded retrain
    assert mod.gate_ok(None, 0.90) is False        # unmeasurable → refuse
    assert mod.gate_ok(None, 0) is True            # gate disabled
    assert mod.gate_ok(0.10, 0) is True


def test_promote_copies_artifacts(tmp_path):
    mod = _load_module()
    tmp_out = tmp_path / 'photo_classifier.onnx'
    tmp_out.write_bytes(b'onnx-bytes')
    tmp_out.with_suffix('.onnx.json').write_text('{"labels": []}', encoding='utf-8')
    tmp_out.with_suffix('.pt').write_bytes(b'ckpt')
    app_dir = tmp_path / 'app'
    app_dir.mkdir()
    moved = mod.promote(tmp_out, app_dir)
    assert set(moved) == {'photo_classifier.onnx', 'photo_classifier.onnx.json',
                          'photo_classifier.pt'}
    assert (app_dir / 'photo_classifier.onnx').read_bytes() == b'onnx-bytes'
    assert (app_dir / 'photo_classifier.onnx.json').exists()


def test_classify_members_ignores_directories_and_manifest():
    mod = _load_module()
    images, manifest, rejected = mod.classify_members([
        'garbage/', 'garbage/a.jpg', 'garbage/b.JPEG', 'manifest.csv',
        'readme.txt', 'garbage/c.txt',
    ])
    assert set(images) == {'garbage/a.jpg', 'garbage/b.JPEG'}
    assert manifest == 'manifest.csv'
    assert set(rejected) == {'readme.txt', 'garbage/c.txt'}


def test_find_zip_picks_newest(tmp_path):
    mod = _load_module()
    import os
    import time
    old = _make_zip(tmp_path / 'retrain_batch_old.zip', {})
    new = _make_zip(tmp_path / 'retrain_batch_new.zip', {})
    os.utime(old, (1, 1))                       # epoch — unmistakably stale
    future = time.time() + 3600
    os.utime(new, (future, future))             # newest, even against repo zips
    found = mod.find_zip(extra_dirs=[str(tmp_path)])
    assert found == new


# --- baseline auto-refresh -------------------------------------------------

def test_read_canary_probe_from_real_jobs_source():
    """The drift baseline's canary block is the non-garbage probe embedded in
    app/jobs.py; extraction must yield a decodable JPEG without importing the
    app (ast folds the adjacent string literals)."""
    mod = _load_module()
    jobs = HERE.parent / 'app' / 'jobs.py'
    if not jobs.exists():
        pytest.skip('app/jobs.py not present')
    probe = mod.read_probe_jpeg(jobs, '_PHOTO_GATE_PROBE_JPEG_B64')
    assert probe and probe[:2] == b'\xff\xd8' and len(probe) > 1000
    assert mod.read_probe_b64(jobs, 'NO_SUCH_CONSTANT') is None


def test_build_baseline_fields_and_tolerance():
    mod = _load_module()
    existing = {'tolerance': {'mean_abs': 0.02, 'min_abs': 0.01, 'floor': 0.85}}
    data = mod.build_baseline(existing, [0.9998], [0.9, 0.95], 0.7, 'deadbeef')
    assert data['threshold'] == 0.7
    assert data['model_sha256'] == 'deadbeef'
    assert data['canary_p_reject']['mean'] == pytest.approx(0.9998)
    assert data['classifier_p_reject']['n'] == 2
    # operator-set tolerance must survive the refresh
    assert data['tolerance']['mean_abs'] == 0.02
    assert data['tolerance']['floor'] == 0.85


def test_build_baseline_keeps_canary_when_probe_unavailable():
    """If the probe can't be read, the previous canary block is preserved
    rather than zeroed (which would silently disable the primary check)."""
    mod = _load_module()
    existing = {'canary_p_reject': {'n': 20, 'mean': 0.9999, 'min': 0.9998,
                                    'max': 1.0, 'p50': 0.9999}}
    data = mod.build_baseline(existing, [], [0.9], 0.7, 'x')
    assert data['canary_p_reject']['mean'] == pytest.approx(0.9999)


def test_refresh_baseline_orchestration(tmp_path, monkeypatch):
    """refresh_baseline scores the canary probe + the rejected val images and
    writes the merged baseline (fake session — no onnxruntime needed)."""
    mod = _load_module()
    ds = _dataset(tmp_path)
    for cls in ('garbage', 'non_garbage'):
        for i in range(2):
            (ds / 'val' / cls / f'{cls}_{i}.jpg').write_bytes(_jpeg_bytes())
    model = tmp_path / 'photo_classifier.onnx'
    model.write_bytes(b'fake-model')
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'tolerance': {'mean_abs': 0.02, 'min_abs': 0.01,
                                                  'floor': 0.85}}), encoding='utf-8')
    monkeypatch.setattr(mod, 'load_onnx_session', lambda p: {
        'sess': None, 'in_name': 'i', 'out_name': 'o', 'reject_idx': 1,
        'size': (224, 224), 'labels': ['garbage', 'non_garbage']})
    monkeypatch.setattr(mod, 'read_probe_jpeg',
                        lambda jobs, name: b'\xff\xd8probe' if 'ACCEPT' not in name else None)
    monkeypatch.setattr(mod, 'score_jpeg',
                        lambda clf, blob: 0.9998 if blob == b'\xff\xd8probe' else 0.80)
    data, err = mod.refresh_baseline(model, ds, baseline)
    assert err is None
    assert data['canary_p_reject']['mean'] == pytest.approx(0.9998)
    assert data['val_n'] == 4 and data['val_rejected_n'] == 4  # 0.80 > 0.7 threshold
    assert data['threshold'] == 0.7
    on_disk = json.loads(baseline.read_text(encoding='utf-8'))
    assert on_disk['canary_p_reject']['mean'] == pytest.approx(0.9998)
    assert on_disk['tolerance']['mean_abs'] == 0.02
    assert 'model_sha256' in on_disk


def test_refresh_baseline_missing_model_returns_error(tmp_path):
    mod = _load_module()
    data, err = mod.refresh_baseline(tmp_path / 'nope.onnx', tmp_path,
                                     tmp_path / 'b.json')
    assert data is None and 'not found' in err


def test_real_model_canary_score_matches_documented_range():
    """Integration: scoring the embedded non-garbage probe with the bundled
    ONNX must reproduce the documented live canary p_reject (0.9998-1.0000)."""
    pytest.importorskip('onnxruntime')
    mod = _load_module()
    model = HERE.parent / 'app' / 'photo_classifier.onnx'
    jobs = HERE.parent / 'app' / 'jobs.py'
    if not model.exists() or not jobs.exists():
        pytest.skip('bundled model / jobs source not present')
    probe = mod.read_probe_jpeg(jobs, '_PHOTO_GATE_PROBE_JPEG_B64')
    clf = mod.load_onnx_session(model)
    assert mod.score_jpeg(clf, probe) > 0.99


def test_real_model_accept_probe_decodes_and_is_accepted():
    """Regression: the ACCEPT-path probe must decode strictly with Pillow and
    score BELOW the 0.7 p_reject threshold. A truncated embed (5196 bytes, no
    EOI) once made Pillow raise "broken data stream", so the accept half of
    the dual-probe canary silently never ran while the reject half stayed
    green — exactly the failure this test now guards."""
    pytest.importorskip('onnxruntime')
    mod = _load_module()
    model = HERE.parent / 'app' / 'photo_classifier.onnx'
    jobs = HERE.parent / 'app' / 'jobs.py'
    if not model.exists() or not jobs.exists():
        pytest.skip('bundled model / jobs source not present')
    probe = mod.read_probe_jpeg(jobs, '_PHOTO_GATE_ACCEPT_PROBE_JPEG_B64')
    assert probe, 'accept probe did not decode to a JPEG'
    assert probe[-2:] == b'\xff\xd9', 'accept probe is missing its JPEG EOI marker'
    # Strict decode: the same PIL path the /report form uses (no
    # LOAD_TRUNCATED_IMAGES leniency), which is where the old embed failed.
    Image.open(io.BytesIO(probe)).verify()
    im = Image.open(io.BytesIO(probe))
    im.load()
    assert im.format == 'JPEG'
    clf = mod.load_onnx_session(model)
    assert mod.score_jpeg(clf, probe) < 0.7
