import sys
import os
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
    from .models import Complaint
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from app.models import Complaint

MODEL_PATH = Path(__file__).with_name("ml_model.pkl")


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


# Module-level model is optional — never crash app import on a missing artifact.
model = _load_model()

def get_live_season_index() -> int:
    """
    Evaluates current month calendar status to determine active AP season index.
    Returns: 1 for Summer, 2 for Monsoon, 0 for Winter.
    """
    month = datetime.now().month
    if month in [3, 4, 5]:
        return 1  # Summer
    elif month in [6, 7, 8, 9]:
        return 2  # Monsoon
    else:
        return 0  # Winter

def get_live_weather_status() -> int:
    """Checks live API values for severe condition overrides using correct JSON formats."""
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
                return 2  # Set weights to match Monsoon conditions
    except Exception as e:
        print(f"📡 [ML TELEMETRY] Skipping API override check: {e}")

    return get_live_season_index()

def predict_miss(ward: str) -> int:
    """
    Predicts the missed garbage collection risk for a given ward.
    Uses the RandomForest model trained on: day_of_week, season_idx, recent_complaints, ward_id
    Falls back to a transparent heuristic if no model artifact is present,
    so the route NEVER errors.
    """
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    day_of_week = datetime.now().weekday()  # 0=Monday ... 6=Sunday
    season_idx = get_live_weather_status()

    # Calculate recent complaints in this ward
    recent = Complaint.query.filter(Complaint.ward == ward, Complaint.created_at >= week_ago).count()

    # Generate stable ward_id using MD5 hash
    encoded_ward = str(ward).encode('utf-8')
    ward_id = (int(hashlib.md5(encoded_ward).hexdigest(), 16) % 10) + 1

    if model is None:
        # Honest heuristic fallback (no trained artifact):
        # elevated risk if many recent complaints OR monsoon season.
        return 1 if (recent >= 3 or season_idx == 2) else 0

    features = [[day_of_week, season_idx, recent, ward_id]]
    prediction = model.predict(features)

    return int(prediction[0])
