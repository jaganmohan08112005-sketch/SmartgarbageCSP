import os
import pickle
import hashlib
import sys
import random
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

# Ensure UTF-8 stdout encoding to support printing emojis on Windows systems
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def get_stable_ward_id(ward_name: str) -> int:
    """Generates a deterministic integer ID between 1 and 10 across processes."""
    encoded = str(ward_name).encode('utf-8')
    return (int(hashlib.md5(encoded).hexdigest(), 16) % 10) + 1

# 1. Base synthetic baseline data rows (Fallback)
synthetic_data = {
    'day_of_week': [0, 1, 2, 3, 4, 5, 6, 0, 1, 2, 3, 4, 5, 6, 0, 1, 2],
    'season_idx': [0, 0, 0, 2, 2, 2, 0, 2, 0, 2, 0, 2, 0, 0, 2, 2, 0], 
    'complaints_last7': [0, 0, 2, 5, 3, 1, 0, 4, 0, 6, 1, 2, 0, 0, 3, 5, 1],
    'ward_id': [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3],
    'missed': [0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0]
}
df = pd.DataFrame(synthetic_data)

GOOGLE_SHEET_ID = "15nwLEyIBtQPZc0eUDhxBMgxFHYh_cBBl5ZmH636HGcI"

print("🌐 Connecting directly to live Google Sheets server...")
try:
    cloud_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv"
    survey_df = pd.read_csv(cloud_url)
    total_responses = len(survey_df)
    
    if total_responses > 0:
        print(f"✅ Successfully downloaded {total_responses} live responses from Google Sheets!")
        
        # Initialize DataFrame with a fixed index range to guarantee index alignment
        survey_processed = pd.DataFrame(index=range(total_responses))
        
        # Feature 1: Distributed days
        survey_processed['day_of_week'] = ([1, 3, 5] * (total_responses // 3 + 1))[:total_responses]
        
        # Feature 2: Seasonal indexes
        survey_processed['season_idx'] = ([0, 1, 2] * (total_responses // 3 + 1))[:total_responses]
        
        # Feature 3: Map delay responses
        delay_col = "How long does garbage typically pile up when collection is missed ?"
        if delay_col in survey_df.columns:
            survey_processed['complaints_last7'] = survey_df[delay_col].apply(
                lambda x: 5 if "1-2 days" in str(x) else (1 if "Less than 1 day" in str(x) else 0)
            )
        else:
            survey_processed['complaints_last7'] = ([1, 2, 4] * (total_responses // 3 + 1))[:total_responses]
            
        # Feature 4: Deterministic tracking mapping
        area_col = "What is your residential area / ward ?"
        if area_col in survey_df.columns:
            survey_processed['ward_id'] = survey_df[area_col].apply(get_stable_ward_id)
        else:
            survey_processed['ward_id'] = ([1, 2, 3] * (total_responses // 3 + 1))[:total_responses]
            
        # Target Label
        target_col = "Have you experienced garbage piling up on your street for 2+ days ?"
        if target_col in survey_df.columns:
            survey_processed['missed'] = survey_df[target_col].apply(
                lambda x: 1 if "Yes" in str(x) else 0
            )
        else:
            survey_processed['missed'] = ([1, 0, 1] * (total_responses // 3 + 1))[:total_responses]
            
        # Merge synthetic records with cloud sheet data frames cleanly
        df = pd.concat([df, survey_processed], ignore_index=True)
        print("🎉 Real survey answers mapped directly into training columns!")

except Exception as e:
    print(f"⚠️ Cloud sync issue encountered ({e}). Falling back onto safety baselines.")

# 3. Model Training Pipeline
def train_and_save_models(extra_fill_rows=None):
    """Train BOTH models (miss-prediction classifier + fill-rate regressor)
    and atomically save them to versioned pickle files.

    Refactored from the original import-time script so the weekly RQ
    retraining job (jobs.py: model_retraining_job) can call it on a cadence
    instead of only at process start. `extra_fill_rows` lets the caller inject
    fresh telemetry-history samples; when None, build_real_fill_rows() is used
    (which itself pulls from the live DB). Returns True on success."""
    global df
    X = df[['day_of_week', 'season_idx', 'complaints_last7', 'ward_id']]
    y = df['missed']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    acc = accuracy_score(y_test, model.predict(X_test))
    print(f"🚀 Combined Model Classification Accuracy: {acc:.2%}")

    # Ensure destination directory structure exists safely
    os.makedirs('app', exist_ok=True)

    # 4. Save Compiled Model (atomic: write temp, then rename)
    _tmp = 'app/ml_model.pkl.tmp'
    with open(_tmp, 'wb') as f:
        pickle.dump(model, f)
    os.replace(_tmp, 'app/ml_model.pkl')
    print("Model compiled and saved successfully to app/ml_model.pkl")

    # ── Fill-rate regressor (same pipeline as the original script) ──
    fill_rows = extra_fill_rows if extra_fill_rows is not None else build_real_fill_rows()
    from app.ml_model import build_synthetic_fill_rows
    random.seed(42)
    synthetic_fill_rows = build_synthetic_fill_rows()
    real_fill_count = len(fill_rows)
    fill_rows = list(fill_rows) + list(synthetic_fill_rows)

    fill_df = pd.DataFrame(fill_rows)
    fill_X = fill_df[['level', 'hours_since_reset', 'season_idx', 'ward_id', 'stream_id']]
    fill_y = fill_df['fill_rate_hour_pct']

    fill_model = RandomForestRegressor(n_estimators=120, random_state=42)
    fill_model.fit(fill_X, fill_y)

    _tmp_fill = 'app/ml_fill_model.pkl.tmp'
    with open(_tmp_fill, 'wb') as f:
        pickle.dump(fill_model, f)
    os.replace(_tmp_fill, 'app/ml_fill_model.pkl')
    print(f"📦 Fill-rate regressor trained on {len(fill_rows)} rows "
          f"({real_fill_count} real + {len(synthetic_fill_rows)} synthetic) "
          f"and saved to app/ml_fill_model.pkl")
    return True


# ──────────────────────────────────────────────
# 5. Fill-rate regressor — hours-to-overflow forecast
# Predicts %-fill per hour for a smart bin from its telemetry history:
# level, hours since last reset (decomp timer/compaction), season, ward, stream.
# Wired into predict_overflow_eta_hours() -> SmartBin.overflow_eta_hours,
# which feeds the route optimizer and proactive dispatch.
#
# Training data = REAL per-ping telemetry history (BinTelemetryLog, the live
# snapshot table) merged with synthetic physics-inspired priors. The real
# samples teach the model each bin's actual fill velocity over time; the
# synthetic curves keep it well-behaved on wards/streams with thin history.
# Run `python train_model.py` after the DB has accumulated telemetry to
# retrain app/ml_fill_model.pkl on live data.
# ──────────────────────────────────────────────
def build_real_fill_rows():
    """Real supervised samples from the live telemetry history table.
    Returns [] when the DB has no usable history (e.g. fresh checkout),
    so the synthetic priors below always guarantee a trainable dataset."""
    try:
        from app import create_app
        from app.ml_model import build_fill_training_rows
        app = create_app()
        with app.app_context():
            rows = build_fill_training_rows()
        if rows:
            print(f"📡 Merged {len(rows)} REAL telemetry-history samples into training.")
        return rows
    except Exception as e:
        print(f"⚠️ No usable telemetry history for retrain ({e}) — synthetic priors only.")
        return []


# Run the full training pipeline at import time (original behaviour) so the
# models are always present on a fresh checkout. The RQ retraining job calls
# train_and_save_models() directly on its weekly cadence.
if __name__ == '__main__' or not os.path.exists('app/ml_model.pkl'):
    train_and_save_models()
