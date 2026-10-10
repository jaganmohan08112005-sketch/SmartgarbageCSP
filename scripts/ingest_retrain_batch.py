#!/usr/bin/env python3
"""Ingest a retrain-batch.zip into _dataset/train and retrain automatically.

Closes the loop that docs/PHOTO_GATE_RUNBOOK.md §6 previously left to a human:

    1. relabel false positives in the admin panel (♻️ on /admin/photo-rejections)
    2. download the retrain-batch_*.zip export
    3. run THIS script — it extracts garbage/rejection_<id>.jpg into
       _dataset/train/garbage/ and then runs scripts/train_photo_classifier.py,
       gating the result on validation accuracy before promoting the model.

Safety properties
-----------------
* **zip-slip**: only members shaped `garbage/<basename>` are accepted. Absolute
  paths, `..` traversal, and any foreign prefix (`val/`, `non_garbage/`, ...)
  are rejected and never written.
* **val-contamination guard**: extraction writes ONLY into `train/garbage/`.
  The evaluation set is never touched (the ZIP's own `garbage/` prefix is the
  training class directory).
* **exactly-once / idempotent**: a ledger (_dataset/retrain_ingested.json)
  records each ingested rejection id, so re-running the same ZIP is a no-op —
  mirroring the server-side `batched_at` export semantics.
* **evaluate-before-ship**: training writes to a temp dir; the new ONNX is
  promoted over app/photo_classifier.onnx only when `best_val_acc` clears
  `--min-val-acc` (default 0.90). An earlier retrain hit 0.825 and was
  discarded by hand — that decision is this gate now.

Exit codes
----------
0  ingest + train + promote succeeded (or --no-train ingest succeeded)
2  preflight/usage error (no ZIP, missing dataset, unusable ZIP layout)
3  training ran but the validation-accuracy gate rejected the model
4  the training subprocess failed
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
TRAIN_SCRIPT = HERE / 'train_photo_classifier.py'
DEFAULT_DATASET = REPO_ROOT / '_dataset'
DEFAULT_LEDGER = '_dataset/retrain_ingested.json'
BASELINE_PATH = REPO_ROOT / 'scripts' / 'photo_classifier_baseline.json'
DEFAULT_GATE = 0.90
MIN_IMAGE_PX = 48
IMAGE_EXTS = ('.jpg', '.jpeg', '.png')

_VAL_ACC_RE = re.compile(r'OK best_val_acc=([0-9]*\.?[0-9]+)')


def _log(msg):
    print(msg, flush=True)


# ── ZIP discovery + member classification ──────────────────────────────
def find_zip(explicit=None, extra_dirs=()):
    """Return the newest retrain_batch_*.zip, or an explicit path.

    Search order: the --zip argument, the current directory, the repo root,
    the dataset root, then ~/Downloads. The newest by mtime wins so the most
    recent export is always the one ingested.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None
    roots = [Path.cwd(), REPO_ROOT, DEFAULT_DATASET] + [Path(d).expanduser() for d in extra_dirs]
    try:
        roots.append(Path.home() / 'Downloads')
    except Exception:
        pass
    candidates = []
    for root in roots:
        try:
            candidates.extend(root.glob('retrain_batch_*.zip'))
        except Exception:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def classify_members(names):
    """Split ZIP member names into (images, manifest_name, rejected).

    images maps the archive member name -> a safe destination basename.
    Only `garbage/<basename>` with a known image extension is accepted; every
    other member (including `manifest.csv`) is either returned as the manifest
    or listed in `rejected`. Rejection never writes anything.
    """
    images, manifest, rejected = {}, None, []
    for raw in names:
        name = raw.replace('\\', '/')
        if name.endswith('/'):
            continue
        if name == 'manifest.csv':
            manifest = raw
            continue
        parts = name.split('/')
        bad = (name.startswith('/') or '..' in parts
               or len(parts) != 2 or parts[0] != 'garbage'
               or not parts[1].lower().endswith(IMAGE_EXTS))
        if bad:
            rejected.append(raw)
            continue
        images[raw] = parts[1]
    return images, manifest, rejected


def _is_valid_image(blob):
    """True when the bytes decode as an image of at least MIN_IMAGE_PX square."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(blob)) as img:
            img.verify()
        with Image.open(io.BytesIO(blob)) as img:
            return min(img.size) >= MIN_IMAGE_PX
    except Exception:
        return False


def _rejection_id(basename):
    m = re.match(r'rejection_(\d+)\.', basename)
    return m.group(1) if m else basename


def load_ledger(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_ledger(path, ledger):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(ledger, f, indent=2, sort_keys=True)


# ── Ingest ─────────────────────────────────────────────────────────────
def ingest(zip_path, dataset, ledger_path, dry_run=False, verbose=True):
    """Extract the ZIP's garbage images into <dataset>/train/garbage.

    Returns a stats dict: ingested / skipped_known / skipped_existing /
    invalid / rejected listings. Never raises on a single bad member.
    """
    garbage_dir = Path(dataset) / 'train' / 'garbage'
    garbage_dir.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(ledger_path)
    stats = {'ingested': [], 'skipped_known': [], 'skipped_existing': [],
             'invalid': [], 'rejected': [], 'manifest_rows': 0}
    images = manifest = rejected = None
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        images, manifest, rejected = classify_members(names)
        stats['rejected'] = rejected
        if not images:
            return stats, ledger, 'no garbage/*.jpg members in the ZIP'
        if manifest:
            stats['manifest_rows'] = max(0, len(zf.read(manifest).decode('utf-8', 'replace').splitlines()) - 1)
        for member in sorted(images):
            dest_name = images[member]
            rid = _rejection_id(dest_name)
            dest = garbage_dir / dest_name
            if rid in ledger:
                stats['skipped_known'].append(rid)
                continue
            if dest.exists():
                # Present but unrecorded (e.g. a previous manual unzip) —
                # adopt it into the ledger rather than overwriting it.
                ledger[rid] = {'file': str(dest.relative_to(dataset)),
                               'source_zip': Path(zip_path).name,
                               'sha256': None, 'adopted': True,
                               'ingested_at': datetime.now(timezone.utc).isoformat()}
                stats['skipped_existing'].append(rid)
                continue
            blob = zf.read(member)
            if not _is_valid_image(blob):
                stats['invalid'].append(dest_name)
                continue
            if not dry_run:
                dest.write_bytes(blob)
                ledger[rid] = {'file': str(dest.relative_to(dataset)),
                               'source_zip': Path(zip_path).name,
                               'sha256': hashlib.sha256(blob).hexdigest(),
                               'ingested_at': datetime.now(timezone.utc).isoformat()}
            stats['ingested'].append(rid)
    if not dry_run:
        save_ledger(ledger_path, ledger)
    return stats, ledger, None


# ── Training + promotion ───────────────────────────────────────────────
def _dist(values):
    """min/mean/max/p50/n over the non-None values (matches the weekly script)."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {'n': 0, 'mean': None, 'min': None, 'max': None, 'p50': None}
    return {'n': len(vals), 'mean': sum(vals) / len(vals), 'min': vals[0],
            'max': vals[-1], 'p50': vals[len(vals) // 2]}


def parse_val_acc(text):
    m = _VAL_ACC_RE.search(text or '')
    return float(m.group(1)) if m else None


def gate_ok(acc, min_val_acc):
    """True when the trained model may be promoted over app/.

    A falsy `min_val_acc` disables the gate. Otherwise a missing accuracy is
    treated as a failure — we never promote a model we could not evaluate.
    """
    if not min_val_acc:
        return True
    return acc is not None and acc >= min_val_acc


def run_training(dataset, out_path, epochs=None, hard_neg_oversample=None,
                 train_script=TRAIN_SCRIPT):
    """Invoke train_photo_classifier.py, writing the model to out_path."""
    cmd = [sys.executable, str(train_script),
           '--data', str(dataset), '--out', str(out_path)]
    if epochs:
        cmd += ['--epochs', str(epochs)]
    if hard_neg_oversample:
        cmd += ['--hard-neg-oversample', str(hard_neg_oversample)]
    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'  # Windows consoles choke on the trainer's glyphs
    _log('[train] %s' % ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env,
                          capture_output=True, text=True, errors='replace')
    if proc.stdout:
        # Stream the tail so the operator sees progress without a wall of text.
        print(proc.stdout[-4000:], flush=True)
    if proc.stderr:
        print(proc.stderr[-2000:], file=sys.stderr, flush=True)
    return proc


def promote(tmp_out, app_dir):
    """Copy the trained artifacts over app/ and return the promoted names."""
    tmp_out = Path(tmp_out)
    artifacts = [tmp_out, tmp_out.with_suffix('.onnx.json'), tmp_out.with_suffix('.pt')]
    moved = []
    for src in artifacts:
        if src.exists() and src.stat().st_size > 0:
            dst = Path(app_dir) / src.name
            shutil.copy2(src, dst)
            moved.append(dst.name)
    return moved


# ── Training baseline auto-refresh ─────────────────────────────────────
# The weekly drift tracker (scripts/photo_rejection_weekly.py) compares live
# p_reject scores against scripts/photo_classifier_baseline.json. A retrain
# moves those scores, so the baseline must be refreshed in the same breath or
# the very next weekly run (correctly) alerts on the model the operator just
# shipped. This recomputes it from the NEW model:
#   * canary_p_reject   — p_reject of the embedded non-garbage probe (the
#                         byte-identical input the live canary uploads), and
#   * classifier_p_reject — p_reject of every val image the new model REJECTS.
# The probes are extracted from app/jobs.py directly (no app import needed).


def read_probe_b64(jobs_path, const_name):
    """Read an embedded base64 probe constant from app/jobs.py without importing
    the app (ast folds the adjacent string literals into one Constant)."""
    try:
        import ast
        tree = ast.parse(Path(jobs_path).read_text(encoding='utf-8', errors='replace'))
    except Exception:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == const_name:
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return None
    return None


def read_probe_jpeg(jobs_path, const_name):
    val = read_probe_b64(jobs_path, const_name)
    if not val:
        return None
    try:
        import base64
        blob = base64.b64decode(val)
        return blob if blob[:2] == b'\xff\xd8' else None
    except Exception:
        return None


def load_onnx_session(model_path):
    """Load a classifier with the SAME label/preprocess contract the runtime
    uses (app/routes/__init__.py::_load_photo_classifier)."""
    import onnxruntime as ort
    model_path = Path(model_path)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(model_path), sess_options=opts,
                                providers=['CPUExecutionProvider'])
    inp = sess.get_inputs()[0]
    dims = [d or 224 for d in inp.shape[2:]] or [224, 224]
    labels = None
    for sidecar in (model_path.with_suffix('.onnx.json'), model_path.with_suffix('.json')):
        if sidecar.exists():
            try:
                data = json.loads(sidecar.read_text(encoding='utf-8'))
                labels = data.get('labels') if isinstance(data, dict) else data
                if labels:
                    break
            except Exception:
                pass
    if not labels:
        labels = ['garbage', 'non_garbage']
    reject_idx = next((i for i, lab in enumerate(labels)
                       if any(w in str(lab).lower() for w in ('non', 'clean', 'not'))), 1)
    return {'sess': sess, 'in_name': inp.name, 'out_name': sess.get_outputs()[0].name,
            'reject_idx': reject_idx, 'size': (int(dims[0]), int(dims[1])),
            'labels': labels}


def score_jpeg(clf, blob):
    """p_reject for one encoded JPEG, using the runtime's resize/normalise path."""
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(blob)).convert('RGB').resize(clf['size'])
    arr = np.asarray(img, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    x = np.transpose(arr, (2, 0, 1))[np.newaxis, ...]
    logits = clf['sess'].run([clf['out_name']], {clf['in_name']: x})[0][0]
    exp = np.exp(logits - logits.max())
    return float((exp / exp.sum())[clf['reject_idx']])


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def build_baseline(existing, canary_vals, classifier_vals, threshold, model_sha256,
                   source=None):
    """Merge a refreshed baseline, preserving the operator-set tolerance and
    (when the probe could not be read) the existing canary block."""
    out = dict(existing or {})
    out['schema'] = 'photo_classifier_baseline/1'
    out['model'] = 'photo_classifier.onnx'
    out.setdefault('architecture', 'MobileNetV3-Small')
    out['recorded'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    out['threshold'] = threshold
    out['model_sha256'] = model_sha256
    if canary_vals or not out.get('canary_p_reject'):
        out['canary_p_reject'] = _dist(canary_vals)
    if classifier_vals:
        out['classifier_p_reject'] = _dist(classifier_vals)
    out.setdefault('tolerance', {'mean_abs': 0.01, 'min_abs': 0.005, 'floor': 0.9})
    out['source'] = source or ('auto-refreshed by scripts/ingest_retrain_batch.py '
                               'from the retrained model')
    return out


def refresh_baseline(model_path, dataset, baseline_path, threshold=None,
                     jobs_path=None, val_limit=0):
    """Recompute the training baseline from a freshly trained ONNX model.

    Returns (baseline_dict, error_or_None). Never raises to the caller beyond
    load/session errors, which the caller treats as non-fatal.
    """
    model_path = Path(model_path)
    if not model_path.exists():
        return None, 'model not found: %s' % model_path
    jobs_path = Path(jobs_path) if jobs_path else REPO_ROOT / 'app' / 'jobs.py'
    if threshold is None:
        threshold = float(os.environ.get('PHOTO_CLASSIFIER_THRESHOLD', '0.7'))
    clf = load_onnx_session(model_path)

    reject_probe = read_probe_jpeg(jobs_path, '_PHOTO_GATE_PROBE_JPEG_B64')
    canary_vals = [score_jpeg(clf, reject_probe)] if reject_probe else []

    val_vals = []
    for cls in ('non_garbage', 'garbage'):
        d = Path(dataset) / 'val' / cls
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                val_vals.append(score_jpeg(clf, p.read_bytes()))
            except Exception:
                continue
            if val_limit and len(val_vals) >= val_limit:
                break
        if val_limit and len(val_vals) >= val_limit:
            break
    rejected = [v for v in val_vals if v >= threshold]

    existing = {}
    try:
        with open(baseline_path, encoding='utf-8') as f:
            existing = json.load(f)
    except Exception:
        existing = {}

    data = build_baseline(existing, canary_vals, rejected, threshold,
                          _sha256(model_path))
    data['val_n'] = len(val_vals)
    data['val_rejected_n'] = len(rejected)
    accept_probe = read_probe_jpeg(jobs_path, '_PHOTO_GATE_ACCEPT_PROBE_JPEG_B64')
    if accept_probe:
        try:
            data['accept_probe_p_reject'] = round(score_jpeg(clf, accept_probe), 6)
        except Exception as e:
            # Record rather than hide: the accept-path probe has proven
            # undecodable with the strict Pillow path, which is itself worth
            # seeing in the refreshed artifact.
            data['accept_probe_error'] = ('%s: %s' % (type(e).__name__, e))[:160]
    if not canary_vals:
        data['refresh_warning'] = ('canary probe not found in app/jobs.py — kept the '
                                   'previous canary_p_reject block')
    Path(baseline_path).parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    return data, None


def _preflight(dataset):
    for cls in ('garbage', 'non_garbage'):
        d = Path(dataset) / 'train' / cls
        if not d.exists() or not any(d.iterdir()):
            return ('dataset "%s" is missing/empty — run '
                    'scripts/fetch_photo_dataset.py first' % d)
    if not TRAIN_SCRIPT.exists():
        return 'training script not found: %s' % TRAIN_SCRIPT
    return None


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--zip', default=None, help='retrain-batch zip (default: newest found)')
    ap.add_argument('--dataset', default=str(DEFAULT_DATASET))
    ap.add_argument('--ledger', default=None,
                    help='ingest ledger (default <dataset>/retrain_ingested.json)')
    ap.add_argument('--no-train', action='store_true',
                    help='ingest only; do not run the trainer')
    ap.add_argument('--min-val-acc', type=float, default=DEFAULT_GATE,
                    help='promote only when best_val_acc >= this (0 disables; default %(default)s)')
    ap.add_argument('--epochs', type=int, default=None, help='forwarded to the trainer')
    ap.add_argument('--hard-neg-oversample', type=int, default=1,
                    help='forwarded to the trainer (default 1, as in the runbook)')
    ap.add_argument('--baseline', default=str(BASELINE_PATH),
                    help='training baseline to refresh after a successful retrain')
    ap.add_argument('--no-refresh-baseline', action='store_true',
                    help='skip the baseline refresh (the weekly drift tracker will '
                         'then alert on the new model until it is refreshed by hand)')
    ap.add_argument('--refresh-val-limit', type=int, default=0,
                    help='cap val images scored during the refresh (0 = all)')
    ap.add_argument('--dry-run', action='store_true', help='report without writing')
    args = ap.parse_args()

    dataset = Path(args.dataset).resolve()
    ledger_path = Path(args.ledger) if args.ledger else dataset / 'retrain_ingested.json'

    zip_path = find_zip(args.zip)
    if zip_path is None:
        _log('FATAL: no retrain_batch_*.zip found — pass --zip or download one '
             'from /admin/photo-rejections/retrain-batch.zip')
        return 2
    _log('[zip] %s' % zip_path)

    err = _preflight(dataset)
    if err:
        _log('FATAL: %s' % err)
        return 2

    try:
        stats, _ledger, layout_err = ingest(zip_path, dataset, ledger_path,
                                            dry_run=args.dry_run)
    except zipfile.BadZipFile as e:
        _log('FATAL: %s is not a readable ZIP (%s)' % (zip_path, e))
        return 2
    if layout_err:
        _log('FATAL: %s' % layout_err)
        return 2

    _log('[ingest] +%d new, %d already-ingested, %d already-present, '
         '%d invalid, %d rejected member(s)%s' % (
             len(stats['ingested']), len(stats['skipped_known']),
             len(stats['skipped_existing']), len(stats['invalid']),
             len(stats['rejected']), ' (dry-run)' if args.dry_run else ''))
    for name in stats['invalid']:
        _log('  ! not a valid image, skipped: %s' % name)
    for name in stats['rejected']:
        _log('  ! rejected member (outside garbage/): %s' % name)

    if not stats['ingested'] and not stats['skipped_existing']:
        _log('nothing new to train on — the ledger already covers this ZIP; '
             'skipping training (idempotent).')
        return 0

    if args.no_train:
        _log('ingest complete (--no-train); run the trainer when ready.')
        return 0

    if args.dry_run:
        _log('dry-run: not training.')
        return 0

    tmp_dir = Path(tempfile.mkdtemp(prefix='retrain_'))
    tmp_out = tmp_dir / 'photo_classifier.onnx'
    try:
        proc = run_training(dataset, tmp_out, epochs=args.epochs,
                            hard_neg_oversample=args.hard_neg_oversample)
        if proc.returncode != 0:
            _log('FATAL: training failed (exit %s)' % proc.returncode)
            return 4
        if not tmp_out.exists():
            _log('FATAL: training produced no ONNX at %s' % tmp_out)
            return 4
        acc = parse_val_acc(proc.stdout)
        if not gate_ok(acc, args.min_val_acc):
            _log('[gate] best_val_acc=%s < --min-val-acc %s — model NOT promoted. '
                 'Inspect the run, then re-run with --min-val-acc 0 to ship '
                 'deliberately, or gather more data.' % (acc, args.min_val_acc))
            return 3
        moved = promote(tmp_out, REPO_ROOT / 'app')
        _log('[promote] best_val_acc=%s → app/: %s' % (acc, ', '.join(moved)))

        if not args.no_refresh_baseline:
            try:
                data, err = refresh_baseline(
                    REPO_ROOT / 'app' / 'photo_classifier.onnx', dataset,
                    Path(args.baseline), val_limit=args.refresh_val_limit)
                if err:
                    _log('[baseline] refresh skipped: %s' % err)
                else:
                    cn = (data.get('canary_p_reject') or {}).get('mean')
                    _log('[baseline] refreshed %s — canary p_reject mean %s, '
                         '%d/%d val images rejected (threshold %s)' % (
                             args.baseline, ('%.4f' % cn) if cn is not None else '—',
                             data.get('val_rejected_n', 0), data.get('val_n', 0),
                             data.get('threshold')))
                    _log('[baseline] the weekly drift tracker now compares live '
                         'scores against this retrained model.')
            except Exception as e:  # never fail a shipped model on a refresh snag
                _log('[baseline] refresh failed (non-fatal): %s' % e)

        _log('Next: evaluate per runbook §3 (ROC sweep) and commit '
             'app/photo_classifier.onnx + .onnx.json + scripts/photo_classifier_baseline.json.')
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
