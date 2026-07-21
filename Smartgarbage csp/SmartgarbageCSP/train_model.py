import os
import pickle
import hashlib
import sys
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
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
X = df[['day_of_week', 'season_idx', 'complaints_last7', 'ward_id']]
y = df['missed']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

acc = accuracy_score(y_test, model.predict(X_test))
print(f"🚀 Combined Model Classification Accuracy: {acc:.2%}")

# Ensure destination directory structure exists safely
os.makedirs('app', exist_ok=True)

# 4. Save Compiled Model
with open('app/ml_model.pkl', 'wb') as f:
    pickle.dump(model, f)
print("Model compiled and saved successfully to app/ml_model.pkl")
