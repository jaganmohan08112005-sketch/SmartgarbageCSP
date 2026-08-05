import sys
import random
import pickle
import hashlib
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

# Ensure UTF-8 stdout encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

try:
    from . import db
    from .models import BinTelemetryLog, Complaint, utcnow
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from app import db
    from app.models import BinTelemetryLog, Complaint, utcnow

MODEL_PATH = Path(__file__).with_name("ml_model.pkl")
FILL_MODEL_PATH = Path(__file__).with_name("ml_fill_model.pkl")


def _load_model():
    """Load the pickled RandomForest. Returns None if absent/corrupt."""
    if not MODEL_PATH.exists():
        return None
    try:
        with MODEL_PATH.open("rb") as f:
            return pickle.load(f)
    except Exception as e:  # corrupt pickle / missing sklearn
        warnings.warn(f"[ML] Could not load model: {e}")
        return None


def _load_fill_model():
    """Load the pickled fill-rate regressor (RandomForestRegressor).
    Returns None if absent/corrupt — predict_overflow_eta_hours then falls
    back to a transparent heuristic so the route never errors."""
    if not FILL_MODEL_PATH.exists():
        return None
    try:
        with FILL_MODEL_PATH.open("rb") as f:
            return pickle.load(f)
    except Exception as e:  # corrupt pickle / missing sklearn
        warnings.warn(f"[ML] Could not load fill model: {e}")
        return None


# Module-level models are optional — never crash app import on a missing artifact.
model = _load_model()
fill_model = _load_fill_model()


def get_stable_ward_id(ward_name: str) -> int:
    """Deterministic 1–10 integer id for a ward across processes (MD5 hash)."""
    encoded = str(ward_name).encode('utf-8')
    return (int(hashlib.md5(encoded).hexdigest(), 16) % 10) + 1


def _waste_stream_id(stream: str) -> int:
    """Map the SmartBin.waste_stream string to a stable numeric feature."""
    mapping = {'mixed': 0, 'wet': 1, 'dry': 2, 'sanitary': 3, 'hazardous': 4}
    return mapping.get((stream or 'mixed').lower(), 0)


def _history_fill_rate_hour_pct(bin_id, now, lookback_hours=48.0,
                                min_points=3, min_span_hours=2.0):
    """Learn a bin's ACTUAL fill velocity from its telemetry history.

    Fits a least-squares line through the recent per-ping (time, level)
    snapshots and returns the slope in %/hr — the real rate this bin is
    filling at right now, rather than an inference from a single anchor
    timestamp. Guards keep a noisy snapshot pair from producing garbage:
      - at least `min_points` snapshots in the window,
      - spanning at least `min_span_hours` of wall-clock time (a pair of
        pings 30s apart would otherwise imply an absurd rate),
      - a positive slope (a bin that was just emptied mid-window shows a
        negative trend — treat that as 'no signal' and fall back).
    Returns the slope in %/hr, or None when the history is too sparse.
    """
    if bin_id is None or now is None:
        return None
    # Normalize a naive-UTC `now` (callers like predict pass aware UTC, but the
    # exported helper must be robust standalone — matching the read-side guard
    # pattern used for every stored timestamp in this file).
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    # Stored timestamps are naive UTC (utcnow defaults). The SQL filter must
    # compare naive-vs-naive — an aware literal against naive columns is a
    # Postgres-parity landmine (sqlite ignores tz, Postgres can reject it).
    if cutoff.tzinfo is not None:
        cutoff = cutoff.replace(tzinfo=None)
    rows = (BinTelemetryLog.query
            .filter(BinTelemetryLog.bin_id == bin_id,
                    BinTelemetryLog.timestamp >= cutoff)
            .order_by(BinTelemetryLog.timestamp.asc())
            .all())
    if len(rows) < min_points:
        return None
    # Build (hours, level) pairs; timestamps may be naive (SQLite) or aware.
    points = []
    t0 = None
    for r in rows:
        ts = r.timestamp
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hours = (ts - now).total_seconds() / 3600.0
        if t0 is None:
            t0 = hours
        points.append((hours - t0, float(r.level)))
    if len(points) < min_points:
        return None
    span = points[-1][0] - points[0][0]
    if span < min_span_hours:
        return None
    # Least-squares slope: sum((x-mean_x)(y-mean_y)) / sum((x-mean_x)^2)
    mean_x = sum(p[0] for p in points) / len(points)
    mean_y = sum(p[1] for p in points) / len(points)
    denom = sum((x - mean_x) ** 2 for x, _ in points)
    if denom <= 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denom
    # A bin that was emptied mid-window trends negative — no velocity signal.
    return slope if slope > 0 else None


def build_synthetic_fill_rows():
    """Synthetic physics-inspired priors for the fill-rate regressor.

    Bins fill fastest in monsoon, slower in winter; denser wards and wet waste
    fill faster. Kept as a pure function so train_model.py AND tests share the
    exact same grid (10 wards × 5 streams × 3 seasons × 4 levels × 4 windows
    = 600 rows) and a retrain always has data even with empty history.
    """
    rows = []
    for ward_id in range(1, 11):
        for stream_id in [0, 1, 2, 3, 4]:  # mixed, wet, dry, sanitary, hazardous
            for season in (0, 1, 2):
                base = 0.3 + 0.1 * ward_id + {0: 0.35, 1: 0.5, 2: 0.15, 3: 0.1, 4: 0.3}[stream_id]
                season_mult = {0: 0.85, 1: 1.0, 2: 1.6}[season]
                for level in (20, 40, 60, 80):
                    for hours in (6, 12, 24, 48):
                        # Rate slows as the bin approaches capacity (compaction,
                        # reduced effective volume) — a gentle decay.
                        decay = 1.0 - 0.15 * (level / 100.0)
                        rate = base * season_mult * decay * random.uniform(0.8, 1.2)
                        rows.append({
                            'level': level,
                            'hours_since_reset': hours,
                            'season_idx': season,
                            'ward_id': ward_id,
                            'stream_id': stream_id,
                            'fill_rate_hour_pct': max(0.05, rate),
                        })
    return rows


def build_fill_training_rows(max_points=200):
    """Real supervised rows for the fill-rate regressor from telemetry history.

    For every bin with history, derive per-ping fill-velocity samples: for
    each consecutive snapshot pair, the observed rate is (level_delta /
    hours_delta), clipped to a plausible range so a compaction-triggered level
    drop or a 30-second re-ping doesn't poison the training set. Returns a
    list of dicts ready for a DataFrame; empty when the history table has no
    useful data yet (callers merge with synthetic priors).
    """
    rows = (db.session.query(BinTelemetryLog)
            .order_by(BinTelemetryLog.bin_id, BinTelemetryLog.timestamp.asc())
            .limit(max_points * 50)
            .all())
    samples = []
    prev = None
    for r in rows:
        if prev is not None and r.bin_id == prev.bin_id:
            ts_cur = r.timestamp.replace(tzinfo=timezone.utc) if r.timestamp and r.timestamp.tzinfo is None else r.timestamp
            ts_prev = prev.timestamp.replace(tzinfo=timezone.utc) if prev.timestamp and prev.timestamp.tzinfo is None else prev.timestamp
            if ts_cur and ts_prev:
                hours = (ts_cur - ts_prev).total_seconds() / 3600.0
                if 0.25 <= hours <= 24.0:   # skip sub-15min re-pings and long gaps
                    dlevel = float(r.level) - float(prev.level)
                    if 0.0 < dlevel <= 70.0:  # ignore compaction drops / resets
                        rate = dlevel / hours
                        if 0.05 <= rate <= 15.0:
                            samples.append({
                                'level': float(r.level),
                                'hours_since_reset': hours,
                                'season_idx': get_season_for_month(r.timestamp.month if r.timestamp else datetime.now().month),
                                'ward_id': get_stable_ward_id((r.bin.ward if r.bin else '') or ''),
                                'stream_id': _waste_stream_id(r.bin.waste_stream if r.bin else None),
                                'fill_rate_hour_pct': rate,
                            })
        prev = r
    return samples[:max_points]


def _estimate_fill_rate_hour_pct(smart_bin, now):
    """Estimate the bin's fill rate in %-per-hour from its telemetry history.

    Three sources feed the estimate, best-first:
      1. Learned velocity: least-squares slope over the bin's real per-ping
         (time, level) history — the ACTUAL rate this bin is filling at now.
      2. Trained regressor (ml_fill_model.pkl), when present, keyed on level,
         hours-since-reset, season, ward and waste stream (learned from real
         history + synthetic physics priors).
      3. Empirical anchor: level / hours since the last reset (decomposition
         timer start, last solar compaction, or first ping) — the previous
         single-anchor heuristic.

    As a last resort a conservative seasonal baseline (~0.5%/hr scaled by
    ward/season) keeps the forecast finite. Never raises — a forecast is an
    advisory, not a hard dependency.
    """
    level = max(0.0, float(smart_bin.level or 0))

    # 1. Real fill velocity from per-ping history (best signal available).
    history_rate = _history_fill_rate_hour_pct(getattr(smart_bin, 'id', None), now)
    if history_rate is not None and history_rate > 0:
        return history_rate

    # Hours since the last "reset" anchor — the fill clock restarts whenever
    # the bin is emptied (decomposition timer resets) or mechanically
    # compacted, so use whichever event happened most recently.
    anchors = [a for a in (smart_bin.decomposition_started_at,
                           smart_bin.last_compacted_at) if a is not None]
    hours_since_reset = None
    if anchors:
        latest = max(anchors)
        if latest.tzinfo is None:  # SQLite returns naive datetimes
            latest = latest.replace(tzinfo=timezone.utc)
        hours_since_reset = max(0.0, (now - latest).total_seconds() / 3600.0)

    empirical = None
    if hours_since_reset and hours_since_reset > 0.25:
        empirical = level / hours_since_reset

    # 2. Trained regressor path (when the artifact exists).
    if fill_model is not None and hours_since_reset is not None:
        try:
            import pandas as pd
            features = pd.DataFrame([[
                level, hours_since_reset, get_live_season_index(),
                get_stable_ward_id(smart_bin.ward or ''),
                _waste_stream_id(smart_bin.waste_stream),
            ]], columns=['level', 'hours_since_reset', 'season_idx', 'ward_id', 'stream_id'])
            predicted = float(fill_model.predict(features)[0])
            if predicted > 0:
                return predicted
        except Exception:
            pass  # fall through to empirical / heuristic

    # 3. Empirical single-anchor rate.
    if empirical is not None and empirical > 0:
        return empirical

    # Conservative seasonal baseline (no fill history yet).
    season = get_live_season_index()
    ward_factor = 0.8 + 0.1 * (get_stable_ward_id(smart_bin.ward or '') % 5)
    season_factor = 1.6 if season == 2 else (1.0 if season == 1 else 0.85)
    return 0.5 * ward_factor * season_factor


def predict_overflow_eta_hours(smart_bin, now=None) -> float:
    """Predict hours until a smart bin reaches 100% fill (overflow).

    Wires the unused SmartBin.overflow_eta_hours column: this is the function
    that produces the value. Returns a positive float (hours) for bins with
    data, or None for empty/faulty bins where a forecast is meaningless.
    """
    if smart_bin is None or smart_bin.level is None or smart_bin.level <= 0:
        return None
    if getattr(smart_bin, 'sensor_fault', False):
        return None
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:  # naive-UTC callers (Postgres parity) → normalize for arithmetic
        now = now.replace(tzinfo=timezone.utc)
    level = float(smart_bin.level)
    if level >= 100:
        return 0.0  # already overflowing
    rate = _estimate_fill_rate_hour_pct(smart_bin, now)
    if rate <= 0:
        return None
    eta_hours = (100.0 - level) / rate
    # Cap at 14 days — beyond that the estimate is noise, and the caller
    # treats huge ETAs as "not urgent".
    return round(min(eta_hours, 14 * 24.0), 1)


def get_season_for_month(month: int) -> int:
    """Map a calendar month to the AP season index: 1 Summer, 2 Monsoon, 0 Winter."""
    if month in [3, 4, 5]:
        return 1  # Summer
    elif month in [6, 7, 8, 9]:
        return 2  # Monsoon
    else:
        return 0  # Winter


def get_live_season_index() -> int:
    """
    Evaluates current month calendar status to determine active AP season index.
    Returns: 1 for Summer, 2 for Monsoon, 0 for Winter.
    """
    return get_season_for_month(datetime.now().month)


# Live weather is a slow-moving, GLOBAL signal (monsoon override for the
# miss-classifier). Polling wttr.in synchronously on every /schedule POST
# blocks the request for up to 4s during API hiccups, so the parsed result is
# cached in-process for WEATHER_CACHE_TTL_S. A per-process cache is fine: the
# value only shifts seasonally, and ≤10-min drift across instances is
# irrelevant for a risk classifier.
_WEATHER_CACHE = {'ts': 0.0, 'val': None}
WEATHER_CACHE_TTL_S = 600  # 10 minutes


def get_live_weather_status() -> int:
    """Checks live API values for severe condition overrides using correct JSON formats.

    The wttr.in result is cached for WEATHER_CACHE_TTL_S so the request path
    never blocks on the external API more than once per cache window — the
    /schedule route calls this via predict_miss on every ward lookup."""
    import time as _time
    now = _time.time()
    if _WEATHER_CACHE['val'] is not None and (now - _WEATHER_CACHE['ts']) < WEATHER_CACHE_TTL_S:
        return _WEATHER_CACHE['val']
    try:
        # wttr.in JSON endpoint requires a location (here: Vizianagaram, AP).
        # Returns current_condition[0].weatherDesc[0].value in the JSON payload.
        response = requests.get('https://wttr.in/18.10,83.41?format=j1', timeout=4)
        if response.ok:
            data = response.json()
            current_condition = data.get('current_condition', [{}])[0]
            weather_desc_list = current_condition.get('weatherDesc', [{}])
            desc = weather_desc_list[0].get('value', '').lower()

            print(f"📡 [ML TELEMETRY] Live Condition parsed: '{desc}'")

            if any(w in desc for w in ['rain', 'storm', 'heavy', 'cyclone', 'shower']):
                result = 2  # Set weights to match Monsoon conditions
            else:
                result = get_live_season_index()
        else:
            result = get_live_season_index()
    except Exception as e:
        print(f"📡 [ML TELEMETRY] Skipping API override check: {e}")
        result = get_live_season_index()

    _WEATHER_CACHE['ts'] = now
    _WEATHER_CACHE['val'] = result
    return result


def predict_miss(ward: str) -> int:
    """
    Predicts the missed garbage collection risk for a given ward.
    Uses the RandomForest model trained on: day_of_week, season_idx, recent_complaints, ward_id
    Falls back to a transparent heuristic if no model artifact is present,
    so the route NEVER errors.
    """
    week_ago = utcnow() - timedelta(days=7)  # naive UTC: matches Complaint.created_at storage
    day_of_week = datetime.now().weekday()  # 0=Monday ... 6=Sunday
    season_idx = get_live_weather_status()

    # Calculate recent complaints in this ward
    recent = Complaint.query.filter(Complaint.ward == ward, Complaint.created_at >= week_ago).count()

    # Generate stable ward_id using MD5 hash
    ward_id = get_stable_ward_id(ward)

    if model is None:
        # Honest heuristic fallback (no trained artifact):
        # elevated risk if many recent complaints OR monsoon season.
        return 1 if (recent >= 3 or season_idx == 2) else 0

    import pandas as pd
    feature_names = ['day_of_week', 'season_idx', 'complaints_last7', 'ward_id']
    df_features = pd.DataFrame([[day_of_week, season_idx, recent, ward_id]], columns=feature_names)
    prediction = model.predict(df_features)

    return int(prediction[0])
