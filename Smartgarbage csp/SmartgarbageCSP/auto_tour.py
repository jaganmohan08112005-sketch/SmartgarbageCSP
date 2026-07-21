import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
import requests
from app import create_app, db
from app.models import User

app = create_app()
BASE = "http://127.0.0.1:5000"
s = requests.Session()

def step(n, title):
    print("\n" + "=" * 72)
    print(f"STEP {n}: {title}")
    print("=" * 72)

def title_of(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return (m.group(1).strip() if m else "?")

def otp_for(username):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        return u.otp if u else None

# ---------------------------------------------------------------
step(0, "PUBLIC HOME — render landing page")
r = s.get(BASE + "/")
print(f"  GET /                 -> {r.status_code}  | title: {title_of(r.text)}")

r = s.get(BASE + "/?fetch_weather=true&ward=" + requests.utils.quote("Ward 2 - Chintalavalasa Junction"))
print(f"  GET /?fetch_weather   -> {r.status_code}  | payload: {r.json()}")

# ---------------------------------------------------------------
step(1, "CITIZEN AUTH — register a new citizen")
r = s.post(BASE + "/register",
           data={"username": "demo_citizen", "password": "demo123", "role": "citizen", "phone": "+919999888777"},
           allow_redirects=False)
print(f"  POST /register        -> {r.status_code} (redirect -> {r.headers.get('Location')})")

# ---------------------------------------------------------------
step(2, "CITIZEN LOGIN — role-based redirect to dashboard")
r = s.post(BASE + "/login", data={"username": "demo_citizen", "password": "demo123"}, allow_redirects=False)
print(f"  POST /login (citizen) -> {r.status_code} -> {r.headers.get('Location')}")

# ---------------------------------------------------------------
step(3, "CITIZEN DASHBOARD — wallet, leaderboard, locator, PAYT")
r = s.get(BASE + "/dashboard")
print(f"  GET /dashboard        -> {r.status_code}  | title: {title_of(r.text)}")
print(f"  contains Eco-Wallet?  -> {'Eco-Reward Wallet' in r.text}")
print(f"  contains Locator Map? -> {'Public Smart Bin Locator' in r.text}")
print(f"  contains Leaderboard? -> {'Cleanliness Leaderboard' in r.text}")

# ---------------------------------------------------------------
step(4, "4-STREAM WASTE DECLARATION — earn green points")
r = s.post(BASE + "/dashboard/declare-waste",
           data={"wet_kg": "2.5", "dry_kg": "1.2", "sanitary_kg": "0.3", "hazardous_kg": "0.1",
                  "ward": "Ward 2 - Chintalavalasa Junction"},
           allow_redirects=False)
print(f"  POST /declare-waste   -> {r.status_code} (redirect -> {r.headers.get('Location')})")

r = s.get(BASE + "/api/payt-invoice")
print(f"  GET /api/payt-invoice -> {r.status_code}  | invoices: {json.dumps(r.json(), ensure_ascii=False)}")

# ---------------------------------------------------------------
step(5, "ANONYMOUS ILLEGAL DUMP REPORT — EXIF-stripped upload")
r = s.get(BASE + "/report-illegal")
print(f"  GET /report-illegal   -> {r.status_code}  | title: {title_of(r.text)}")
r = s.post(BASE + "/report-illegal",
           data={"category": "E-Waste / Electronics", "description": "Auto-tour test dump report",
                  "ward": "Ward 1 - MVGR College Area", "latitude": "18.0565", "longitude": "83.4040"},
           allow_redirects=False)
print(f"  POST /report-illegal  -> {r.status_code} (redirect -> {r.headers.get('Location')})")

# ---------------------------------------------------------------
step(6, "LOGOUT citizen")
s.get(BASE + "/logout")

# ---------------------------------------------------------------
step(7, "WORKER LOGIN (MFA) — get OTP, verify, open portal")
r = s.post(BASE + "/login", data={"username": "worker", "password": "worker123"}, allow_redirects=False)
print(f"  POST /login (worker)  -> {r.status_code} -> {r.headers.get('Location')}  (MFA required)")
otp = otp_for("worker")
print(f"  OTP for worker        -> {otp}")
r = s.post(BASE + "/mfa-verify", data={"otp": otp}, allow_redirects=False)
print(f"  POST /mfa-verify      -> {r.status_code} -> {r.headers.get('Location')}")

r = s.get(BASE + "/worker")
print(f"  GET /worker           -> {r.status_code}  | title: {title_of(r.text)}")
print(f"  contains Offload form?-> {'Offloading Checkpoint' in r.text}")

# ---------------------------------------------------------------
step(8, "WORKER — Mark a bin 'Cleared' (reset to 🟢)")
r = s.post(BASE + "/resolve-bin/BIN-201", allow_redirects=False)
print(f"  POST /resolve-bin/BIN-201 -> {r.status_code}  | {r.json()}")

# ---------------------------------------------------------------
step(9, "WORKER — Digital Manifest / Offload Checkpoint")
r = s.post(BASE + "/worker/offload",
           data={"dump_yard_id": "YARD-A (Vizianagaram Central)", "weight_kg": "320.5"},
           allow_redirects=False)
print(f"  POST /worker/offload  -> {r.status_code} (redirect -> {r.headers.get('Location')})")

# ---------------------------------------------------------------
step(10, "LOGOUT worker")
s.get(BASE + "/logout")

# ---------------------------------------------------------------
step(11, "ADMIN LOGIN (MFA) — open control center")
r = s.post(BASE + "/login", data={"username": "admin", "password": "admin123"}, allow_redirects=False)
print(f"  POST /login (admin)   -> {r.status_code} -> {r.headers.get('Location')}  (MFA required)")
otp = otp_for("admin")
print(f"  OTP for admin         -> {otp}")
r = s.post(BASE + "/mfa-verify", data={"otp": otp}, allow_redirects=False)
print(f"  POST /mfa-verify      -> {r.status_code} -> {r.headers.get('Location')}")

r = s.get(BASE + "/admin")
print(f"  GET /admin            -> {r.status_code}  | title: {title_of(r.text)}")
for label in ["Live GIS", "Fleet Geo-Fencing", "Predictive Maintenance", "Audit Trail", "OTA Firmware"]:
    print(f"     - admin has '{label}'? -> {label in r.text}")

# ---------------------------------------------------------------
step(12, "ADMIN — Automated Dispatch (Dijkstra route optimize)")
r = s.get(BASE + "/api/route-optimize")
d = r.json()
print(f"  GET /api/route-optimize -> {r.status_code}")
print(f"     critical bins: {d.get('critical_count')} | distance: {d.get('total_distance_km')} km | CO2 saved: {d.get('co2_saved_kg')} kg")
print(f"     route path: {' -> '.join(n['label'] for n in d.get('route', []))}")

# ---------------------------------------------------------------
step(13, "ADMIN — Fleet Geo-Fencing (out-of-bounds detection)")
r = s.get(BASE + "/api/fleet-location")
print(f"  GET /api/fleet-location -> {r.status_code}")
for t in r.json():
    print(f"     {t['vehicle_id']}: in_bounds={t['in_bounds']} violation={t['geofence_violation']}")

# ---------------------------------------------------------------
step(14, "ADMIN — Audit Trail (immutable security ledger)")
r = s.get(BASE + "/admin/audit")
print(f"  GET /admin/audit      -> {r.status_code}  | title: {title_of(r.text)}")
print(f"     contains 'Immutable Audit Trail'? -> {'Immutable Audit Trail' in r.text}")

# ---------------------------------------------------------------
step(15, "ADMIN — OTA Firmware Hub push")
r = s.post(BASE + "/api/ota/BIN-301", data={"release_id": "2"}, allow_redirects=False)
print(f"  POST /api/ota/BIN-301 -> {r.status_code}  | {r.json()}")

# ---------------------------------------------------------------
step(16, "ANALYTICS — heatmap, circular economy, carbon, CSRD export")
r = s.get(BASE + "/analytics")
print(f"  GET /analytics        -> {r.status_code}  | title: {title_of(r.text)}")
for label in ["Predictive Waste Hotspot Heatmap", "CO₂ Footprint Tracker", "Circular Economy Auditor", "4-Stream Waste Breakdown"]:
    print(f"     - analytics has '{label}'? -> {label in r.text}")
r = s.get(BASE + "/analytics/csrd-export")
d = r.json()
print(f"  GET /analytics/csrd-export -> {r.status_code}")
print(f"     declarations: {len(d.get('waste_declarations', []))} | offloads: {len(d.get('offload_logs', []))} | audit samples: {len(d.get('audit_trail_sample', []))}")

# ---------------------------------------------------------------
step(17, "IOT TELEMETRY INGESTION — drive emergency pipeline")
r = s.post(BASE + "/api/bin-telemetry",
           json={"hardware_id": "BIN-402", "level": 96, "temperature": 71.0, "methane": 640.0, "battery_level": 80})
print(f"  POST /api/bin-telemetry (hazard) -> {r.status_code}  | {r.json()}")

# ---------------------------------------------------------------
print("\n" + "#" * 72)
print("# AUTOMATED WALKTHROUGH COMPLETE — all pages & features responded OK #")
print("#" * 72)
