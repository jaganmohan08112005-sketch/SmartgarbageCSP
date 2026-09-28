#!/usr/bin/env python3
"""Retrain the ML artifacts: app/ml_model.pkl and app/ml_fill_model.pkl.

Reproduces the two scikit-learn models the portal ships, with the exact
feature contracts the inference code uses:

- ``app/ml_model.pkl`` — RandomForestClassifier for ward miss-risk
  (1 = elevated risk of a missed collection) over
  ``[day_of_week, season_idx, complaints_last7, ward_id]``,
  consumed by ``app.ml_model.predict_miss()`` on the /schedule path.
- ``app/ml_fill_model.pkl`` — RandomForestRegressor for fill rate
  (%/hour) over ``[level, hours_since_reset, season_idx, ward_id,
  stream_id]``, consumed by ``predict_overflow_eta_hours()`` via
  ``_estimate_fill_rate_hour_pct()``.

Training data
-------------
Fill regressor: real per-ping fill-velocity samples derived from
BinTelemetryLog by ``build_fill_training_rows()`` (the same function the
tests use), merged with the physics-prior synthetic grid from
``build_synthetic_fill_rows()`` (10 wards × 5 streams × 3 seasons ×
4 levels × 4 windows = 600 rows) so a retrain always has data even when
telemetry history is empty. Real rows are capped by ``--max-points``.

(The grid is 10 wards × 5 streams × 3 seasons × 4 levels × 4 windows =
2 400 rows; older comments in ``app/ml_model.py`` under-count it as 600.)

Miss classifier: no table logs realised "missed collection" outcomes, so
the labelled rows encode the operations heuristic the code's own
heuristic fallback uses (elevated risk when recent complaints >= 3 OR
monsoon conditions), sampled across the full feature grid. The forest
therefore reproduces a smooth version of that rule and can be swapped
for a genuinely supervised model the moment miss outcomes are recorded —
extend ``build_miss_training_rows()`` to join real outcomes then.

Usage
-----
    python train_model.py                    # train, evaluate, save in place
    python train_model.py --out DIR          # write artifacts elsewhere
    python train_model.py --check            # evaluate current artifacts only
    python train_model.py --skip-real        # synthetic priors only (no DB)

Requires scikit-learn + pandas (already runtime deps). Run from the repo
root; DATABASE_URL is only needed when real telemetry rows are used.
"""
import argparse
import pickle
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FEATURES_MISS = ['day_of_week', 'season_idx', 'complaints_last7', 'ward_id']
FEATURES_FILL = ['level', 'hours_since_reset', 'season_idx', 'ward_id', 'stream_id']
RISK_RULE = 'recent >= 3 or monsoon'  # documented labelling rule for the classifier


def build_miss_training_rows():
    """Deterministic labelled grid for the miss-risk classifier.

    Mirrors the heuristic fallback in ``predict_miss``: risk = 1 when
    ``complaints_last7 >= 3 or season_idx == 2``. 10 wards × 7 weekdays ×
    3 seasons × 11 complaint counts = 2 310 rows.
    """
    rows = []
    for ward_id in range(1, 11):
        for day_of_week in range(7):
            for season_idx in (0, 1, 2):
                for complaints in range(11):
                    rows.append({
                        'day_of_week': day_of_week,
                        'season_idx': season_idx,
                        'complaints_last7': complaints,
                        'ward_id': ward_id,
                        'risk': 1 if (complaints >= 3 or season_idx == 2) else 0,
                    })
    return rows


def _split(rows, frac=0.8, seed=42):
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    cut = int(len(rows) * frac)
    return [rows[i] for i in idx[:cut]], [rows[i] for i in idx[cut:]]


def train_miss_model():
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score

    rows = build_miss_training_rows()
    train, test = _split(rows)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(pd.DataFrame(train)[FEATURES_MISS], [r['risk'] for r in train])
    preds = model.predict(pd.DataFrame(test)[FEATURES_MISS])
    metrics = {'rows': len(rows),
               'accuracy': round(float(accuracy_score([r['risk'] for r in test], preds)), 4)}
    return model, metrics


def train_fill_model(skip_real=False):
    """Train the fill-rate regressor on synthetic priors (+ real telemetry)."""
    import pandas as pd
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error

    from app.ml_model import build_synthetic_fill_rows

    rows = build_synthetic_fill_rows()          # 600 physics-prior rows
    n_real = 0
    if not skip_real:
        try:
            from app import create_app
            from app.ml_model import build_fill_training_rows
            app = create_app()
            with app.app_context():
                real = build_fill_training_rows()
            rows = rows + real
            n_real = len(real)
        except Exception as exc:  # no DB reachable — synthetic priors still suffice
            print(f'[train] telemetry history unavailable ({exc}); using synthetic priors only')

    train, test = _split(rows)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(pd.DataFrame(train)[FEATURES_FILL], [r['fill_rate_hour_pct'] for r in train])
    preds = model.predict(pd.DataFrame(test)[FEATURES_FILL])
    metrics = {'rows': len(rows), 'real_rows': n_real,
               'mae_pct_per_hour': round(float(mean_absolute_error(
                   [r['fill_rate_hour_pct'] for r in test], preds)), 4)}
    return model, metrics


def _probe_sanity(model_miss, model_fill):
    """Assert both models answer the probe questions the routes rely on."""
    import pandas as pd
    ok_low = int(model_miss.predict(pd.DataFrame(
        [[1, 0, 0, 3]], columns=FEATURES_MISS))[0])          # winter, no complaints
    ok_high = int(model_miss.predict(pd.DataFrame(
        [[1, 2, 0, 3]], columns=FEATURES_MISS))[0])          # monsoon, no complaints
    rate = float(model_fill.predict(pd.DataFrame(
        [[60, 12, 1, 3, 1]], columns=FEATURES_FILL))[0])
    return {'low_risk_probe': ok_low, 'monsoon_risk_probe': ok_high,
            'fill_rate_probe_pct_hr': round(rate, 3)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default=str(HERE / 'app'),
                    help='directory to write the .pkl artifacts into (default: app/)')
    ap.add_argument('--check', action='store_true',
                    help='load existing artifacts and probe them; save nothing')
    ap.add_argument('--skip-real', action='store_true',
                    help='train the regressor on synthetic priors only (no DB)')
    args = ap.parse_args()

    if args.check:
        miss_path = Path(args.out) / 'ml_model.pkl'
        fill_path = Path(args.out) / 'ml_fill_model.pkl'
        if not miss_path.exists() or not fill_path.exists():
            raise SystemExit(f'--check: artifacts missing under {args.out}')
        with miss_path.open('rb') as f:
            model_miss = pickle.load(f)
        with fill_path.open('rb') as f:
            model_fill = pickle.load(f)
        print('[check]', _probe_sanity(model_miss, model_fill))
        return

    random.seed(42)  # build_synthetic_fill_rows draws from global random
    model_miss, m_miss = train_miss_model()
    model_fill, m_fill = train_fill_model(skip_real=args.skip_real)
    probes = _probe_sanity(model_miss, model_fill)
    if probes['low_risk_probe'] != 0 or probes['monsoon_risk_probe'] != 1:
        raise SystemExit(f'sanity probes failed: {probes}')
    if probes['fill_rate_probe_pct_hr'] <= 0:
        raise SystemExit(f'fill-rate probe failed: {probes}')

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'ml_model.pkl').open('wb') as f:
        pickle.dump(model_miss, f)
    with (out / 'ml_fill_model.pkl').open('wb') as f:
        pickle.dump(model_fill, f)

    print('[train] miss classifier:', m_miss)
    print('[train] fill regressor :', m_fill)
    print('[train] probes         :', probes)
    print(f'[train] wrote {out / "ml_model.pkl"} and {out / "ml_fill_model.pkl"}')


if __name__ == '__main__':
    main()
