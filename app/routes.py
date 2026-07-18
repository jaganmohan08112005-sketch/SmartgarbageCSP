import os
import re
import sys
import json
import random
import math
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import (Blueprint, render_template, request, jsonify,
                   redirect, url_for, session, flash, current_app, send_from_directory)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import requests

# ──────────────────────────────────────────────
# PHONE VALIDATION HELPER
# ──────────────────────────────────────────────
def validate_indian_phone(phone):
    """Validate an Indian mobile number.
    Accepts: +91XXXXXXXXXX or 91XXXXXXXXXX or XXXXXXXXXX (10 digits starting 6-9).
    Returns normalised +91XXXXXXXXXX on success, None on failure.
    Rejects obviously fake sequences (all-same digit, sequential runs).
    """
    if not phone:
        return None
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r'[\s\-().]+', '', phone)
    # Accept optional +91 or 91 prefix
    match = re.fullmatch(r'(?:\+91|91)?([6-9]\d{9})', cleaned)
    if not match:
        return None
    digits = match.group(1)
    # Reject all-same digit: 9999999999, 6666666666 …
    if len(set(digits)) == 1:
        return None
    # Reject simple ascending/descending sequences: 1234567890, 9876543210
    asc  = ''.join(str((int(digits[0]) + i) % 10) for i in range(10))
    desc = ''.join(str((int(digits[0]) - i) % 10) for i in range(10))
    if digits == asc or digits == desc:
        return None
    return f'+91{digits}'

# Ensure UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from . import db, limiter
from .models import (Schedule, Complaint, User, SmartBin, WorkerProfile, IncidentLog,
                     AuditLog, SensorHealth, OffloadLog, IllegalDumpReport,
                     WasteDeclaration, BWGDeclaration, PAYTInvoice, FirmwareRelease)
from .ml_model import predict_miss

main = Blueprint('main', __name__)

# ──────────────────────────────────────────────
# CONSTANTS & CONFIG
# ──────────────────────────────────────────────
WARD_COORDINATES = {
    "Ward 1 - MVGR College Area":          {"lat": 18.0552, "lon": 83.4051},
    "Ward 2 - Chintalavalasa Junction":    {"lat": 18.0675, "lon": 83.4094},
    "Ward 3 - RTC Colony":                 {"lat": 18.0702, "lon": 83.4153},
    "Ward 4 - Ramalayam Street":           {"lat": 18.0650, "lon": 83.4005},
    "Ward 5 - Sai Nagar":                  {"lat": 18.0751, "lon": 83.4201},
}
DEFAULT_LAT = 18.0675
DEFAULT_LON = 83.4094

# Geo-fence sector polygons per vehicle (bounding box format: [[lat,lon], ...])
SECTOR_POLYGONS = {
    "CV-01": [[18.0530,83.4020],[18.0530,83.4080],[18.0590,83.4080],[18.0590,83.4020]],
    "CV-02": [[18.0650,83.4060],[18.0650,83.4120],[18.0710,83.4120],[18.0710,83.4060]],
    "CV-03": [[18.0680,83.4120],[18.0680,83.4190],[18.0740,83.4190],[18.0740,83.4120]],
    "CV-04": [[18.0620,83.3970],[18.0620,83.4030],[18.0680,83.4030],[18.0680,83.3970]],
    "CV-05": [[18.0720,83.4160],[18.0720,83.4240],[18.0790,83.4240],[18.0790,83.4160]],
}
DUMP_YARDS = ["YARD-A (Vizianagaram Central)", "YARD-B (East Processing Plant)", "YARD-C (North Recycling Hub)"]

active_webhooks = []

# ──────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────
def get_wmo_phrase(code):
    if code == 0: return "Clear Skies"
    if code in [1, 2, 3]: return "Mainly Clear / Partly Cloudy"
    if code in [45, 48]: return "Foggy Conditions"
    if code in [51, 53, 55]: return "Drizzle / Light Rain"
    if code in [61, 63, 65]: return "Rainy Weather"
    if code in [80, 81, 82]: return "Heavy Rain Showers"
    if code in [95, 96, 99]: return "Thunderstorm Alert"
    return "Normal Seasonal Conditions"

def point_in_polygon(lat, lon, polygon):
    """Ray-casting algorithm to test if point is inside polygon."""
    n = len(polygon)
    inside = False
    px, py = lat, lon
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def write_audit(action, target=None, detail=None):
    """Write an entry to the immutable AuditLog."""
    try:
        entry = AuditLog(
            user_id=session.get('user_id'),
            username=session.get('username', 'anonymous'),
            role=session.get('role', 'unknown'),
            action=action,
            target=target,
            detail=detail,
            ip_address=request.remote_addr,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        print(f"[AuditLog Write Error] {e}")

def evaluate_emergency_metrics(smart_bin):
    hazard = False
    details = ""
    itype = ""
    severity = "Warning"
    if smart_bin.temperature > 65.0:
        hazard = True; itype = "Fire Hazard"; severity = "Critical"
        details = f"Extreme temperature ({smart_bin.temperature}°C) at {smart_bin.hardware_id} in {smart_bin.ward}."
    elif smart_bin.methane > 500.0:
        hazard = True; itype = "Methane Leak"; severity = "Critical"
        details = f"Hazardous methane ({smart_bin.methane} ppm) at {smart_bin.hardware_id} in {smart_bin.ward}."
    if hazard:
        incident = IncidentLog(bin_id=smart_bin.id, incident_type=itype, severity=severity,
                               status="Active", description=details, timestamp=datetime.now(timezone.utc))
        db.session.add(incident)
        db.session.commit()
        for wh in active_webhooks:
            try:
                requests.post(wh, json={"event": "SMART_BIN_EMERGENCY", "bin_id": smart_bin.hardware_id,
                                        "incident_type": itype, "severity": severity,
                                        "description": details,
                                        "timestamp": datetime.now(timezone.utc).isoformat()}, timeout=3)
            except Exception as e:
                print(f"Webhook delivery failed: {e}")

def activate_compactor(smart_bin):
    """Trigger solar-powered mechanical compactor for bin."""
    smart_bin.last_compacted_at = datetime.now(timezone.utc)
    smart_bin.level = max(0, int(smart_bin.level * 0.7))
    db.session.commit()
    write_audit("PRE_COMPACTION", target=smart_bin.hardware_id,
                detail=f"Compactor activated at 70%+ fill, level reduced to {smart_bin.level}%")

def check_sensor_faults():
    """Auto-flag bins that haven't pinged in 24h as Sensor Fault."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    bins = SmartBin.query.all()
    for b in bins:
        last = b.last_updated
        if last is None:
            # Never reported telemetry — treat as perpetually stale (fault)
            last = datetime.min.replace(tzinfo=timezone.utc)
        elif last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < threshold and not b.sensor_fault:
            b.sensor_fault = True
            # Create / update SensorHealth record
            sh = SensorHealth.query.filter_by(bin_id=b.id).first()
            if sh:
                sh.fault_flag = True
                sh.fault_reason = f"No telemetry received for >24h. Last ping: {b.last_updated}"
                sh.maintenance_scheduled = True
            else:
                sh = SensorHealth(bin_id=b.id, fault_flag=True,
                                  fault_reason=f"No telemetry for >24h. Last ping: {b.last_updated}",
                                  maintenance_scheduled=True)
                db.session.add(sh)
            # Log incident
            existing = IncidentLog.query.filter_by(bin_id=b.id, incident_type="Sensor Fault", status="Active").first()
            if not existing:
                db.session.add(IncidentLog(bin_id=b.id, incident_type="Sensor Fault", severity="Warning",
                                           status="Active",
                                           description=f"Sensor Fault: {b.hardware_id} silent >24h. Maintenance scheduled."))
    db.session.commit()

def check_decomposition_timers():
    """Override ultrasonic status → 'Pending Clearance' (🟡 Yellow) for any bin
    that has stayed above 10% fill for more than 48h without being cleared."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=48)
    bins = SmartBin.query.filter(SmartBin.level > 10).all()
    for b in bins:
        if b.decomposition_started_at is None:
            # Timer hasn't started (level just crossed 10%) — seed it now
            b.decomposition_started_at = datetime.now(timezone.utc)
            continue
        started = b.decomposition_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started < threshold and b.status != "Pending Clearance":
            b.status = "Pending Clearance"
            existing = IncidentLog.query.filter_by(
                bin_id=b.id, incident_type="Decomposition Timeout", status="Active").first()
            if not existing:
                db.session.add(IncidentLog(
                    bin_id=b.id, incident_type="Decomposition Timeout", severity="Warning",
                    status="Active",
                    description=f"{b.hardware_id} stagnant >48h above 10% fill. Forced 🟡 Pending Clearance."))
    db.session.commit()

# ──────────────────────────────────────────────
# ACCESS DECORATORS
# ──────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('main.login'))
        if session.get('mfa_pending'):
            flash('Complete MFA verification first.', 'error')
            return redirect(url_for('main.mfa_verify'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('main.login'))
        if session.get('mfa_pending'):
            flash('Complete MFA verification first.', 'error')
            return redirect(url_for('main.mfa_verify'))
        if session.get('role') != 'admin':
            flash('Administrator privileges required.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated

def worker_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('main.login'))
        if session.get('mfa_pending'):
            flash('Complete MFA verification first.', 'error')
            return redirect(url_for('main.mfa_verify'))
        if session.get('role') != 'worker':
            flash('Worker privileges required.', 'error')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated

def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Super-administrator access required.', 'error')
            return redirect(url_for('main.login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_superadmin:
            flash('Super-administrator access required.', 'error')
            return redirect(url_for('main.admin'))
        return f(*args, **kwargs)
    return decorated

# ═══════════════════════════════════════════════════════════════════
# SECTION 1 — HOME / WEATHER
# ═══════════════════════════════════════════════════════════════════
@main.route('/')
def home():
    if request.args.get('fetch_weather') == 'true':
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        ward = request.args.get('ward')
        if lat and lon:
            target_lat, target_lon = lat, lon
            city_label = "My Location"
        elif ward in WARD_COORDINATES:
            target_lat = WARD_COORDINATES[ward]['lat']
            target_lon = WARD_COORDINATES[ward]['lon']
            city_label = ward
        else:
            target_lat = DEFAULT_LAT
            target_lon = DEFAULT_LON
            city_label = "Chintalavalasa"
        try:
            api_url = (f"https://api.open-meteo.com/v1/forecast?latitude={target_lat}"
                       f"&longitude={target_lon}&current=temperature_2m,relative_humidity_2m,"
                       f"weather_code,wind_speed_10m&wind_speed_unit=kmh")
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                wd = response.json().get('current', {})
                return jsonify({
                    "city": city_label,
                    "temp": f"{round(wd.get('temperature_2m'))}°C",
                    "humidity": f"{wd.get('relative_humidity_2m')}%",
                    "wind": f"{wd.get('wind_speed_10m')} km/h",
                    "condition": get_wmo_phrase(wd.get('weather_code', 0))
                })
        except Exception as e:
            print(f"Weather API error: {e}")
        return jsonify({"error": "Weather API unavailable"}), 500
    return render_template('index.html')

# ═══════════════════════════════════════════════════════════════════
# SECTION 2 — AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════
@main.route('/register', methods=['GET', 'POST'])
@limiter.limit("10/hour")
def register():
    if 'user_id' in session and not session.get('mfa_pending'):
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        role = request.form.get('role', 'citizen')
        if role not in ['citizen', 'worker']:  # Only allow citizen/worker via public registration
            role = 'citizen'
        raw_phone = request.form.get('phone', '').strip()
        # ── Phone Validation ──────────────────────────────────────────
        if not raw_phone:
            flash('Phone number is required.', 'error')
            return redirect(url_for('main.register'))
        phone = validate_indian_phone(raw_phone)
        if not phone:
            flash('Enter a valid Indian mobile number (10 digits starting with 6–9, e.g. +91 98765 43210). Fake or sequential numbers are not accepted.', 'error')
            return redirect(url_for('main.register'))
        # ─────────────────────────────────────────────────────────────
        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('main.register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('main.register'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('main.register'))
        if User.query.filter_by(phone=phone).first():
            flash('This phone number is already registered with another account.', 'error')
            return redirect(url_for('main.register'))
        new_user = User(username=username, password_hash=generate_password_hash(password),
                        role=role, phone=phone)
        db.session.add(new_user)
        db.session.commit()
        if role == 'worker':
            wp = WorkerProfile(user_id=new_user.id, vehicle_id=f"CV-{random.randint(10,99)}",
                               status="Idle", performance_rating=5.0)
            db.session.add(wp)
            db.session.commit()
        write_audit("REGISTER", target=username, detail=f"New {role} account created. Phone: {phone}")
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html')

@main.route('/login', methods=['GET', 'POST'])
@limiter.limit("10/minute")
def login():
    if 'user_id' in session and not session.get('mfa_pending'):
        if session.get('role') == 'admin': return redirect(url_for('main.admin'))
        elif session.get('role') == 'worker': return redirect(url_for('main.worker'))
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('main.login'))
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        if user.role in ['admin', 'worker']:
            otp_val = str(random.randint(100000, 999999))
            user.otp = otp_val
            user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
            db.session.commit()
            print(f"\n🔑 [MFA SIMULATOR] OTP for {user.username}: {otp_val}\n")
            flash(f"MFA OTP Code (Simulated SMS): {otp_val}", "success")
            session['mfa_pending'] = True
            return redirect(url_for('main.mfa_verify'))
        session['mfa_pending'] = False
        write_audit("LOGIN", target=username, detail="Citizen login successful.")
        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')

@main.route('/mfa-verify', methods=['GET', 'POST'])
@limiter.limit("10/minute")
def mfa_verify():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        if user.otp and user.otp_expiry:
            expiry = user.otp_expiry if user.otp_expiry.tzinfo else user.otp_expiry.replace(tzinfo=timezone.utc)
            if expiry > datetime.now(timezone.utc) and user.otp == entered_otp:
                user.otp = None; user.otp_expiry = None
                db.session.commit()
                session['mfa_pending'] = False
                write_audit("MFA_SUCCESS", target=user.username, detail="MFA verified successfully.")
                flash(f'MFA Verified. Welcome, {user.username}!', 'success')
                if user.role == 'admin': return redirect(url_for('main.admin'))
                elif user.role == 'worker': return redirect(url_for('main.worker'))
                return redirect(url_for('main.dashboard'))
            else:
                flash('Invalid or expired OTP.', 'error')
        else:
            flash('OTP not found. Please log in again.', 'error')
            return redirect(url_for('main.login'))
    return render_template('mfa_verify.html')

@main.route('/auth/google')
def auth_google():
    email = f"google_citizen_{random.randint(100,999)}@gmail.com"
    user = User.query.filter_by(username=email).first()
    if not user:
        user = User(username=email, password_hash=generate_password_hash("google_pass"),
                    role="citizen", phone="+919999999999")
        db.session.add(user); db.session.commit()
    session.update({'user_id': user.id, 'username': user.username,
                    'role': user.role, 'mfa_pending': False})
    write_audit("GOOGLE_LOGIN", target=email, detail="Google OAuth quick-signin.")
    flash(f"Authenticated via Google OAuth: {email}", "success")
    return redirect(url_for('main.dashboard'))

@main.route('/auth/phone-login', methods=['POST'])
def auth_phone_login():
    raw_phone = request.form.get('phone_number', '').strip()
    if not raw_phone:
        flash("Phone number is required.", "error")
        return redirect(url_for('main.login'))
    # ── Validate real Indian mobile format ────────────────────────────
    phone_number = validate_indian_phone(raw_phone)
    if not phone_number:
        flash("Enter a valid Indian mobile number (10 digits starting with 6–9). Fake or sequential numbers like 1234567890 are not accepted.", "error")
        return redirect(url_for('main.login'))
    # ─────────────────────────────────────────────────────────────────
    user = User.query.filter_by(phone=phone_number).first()
    if not user:
        # Auto-create a citizen account for the verified phone number
        last4 = phone_number[-4:]
        username = f"citizen_{last4}_{random.randint(10, 99)}"
        # Ensure unique username
        while User.query.filter_by(username=username).first():
            username = f"citizen_{last4}_{random.randint(10, 99)}"
        user = User(username=username, password_hash=generate_password_hash("phone_otp_user"),
                    role="citizen", phone=phone_number)
        db.session.add(user); db.session.commit()
    otp_val = str(random.randint(100000, 999999))
    user.otp = otp_val
    user.otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.session.commit()
    print(f"\n🔑 [MFA SIMULATOR] Phone OTP for {phone_number}: {otp_val}\n")
    flash(f"OTP sent to {phone_number} (Simulated): {otp_val}", "success")
    session.update({'user_id': user.id, 'mfa_pending': True,
                    'username': user.username, 'role': user.role})
    return redirect(url_for('main.mfa_verify'))

@main.route('/logout')
def logout():
    write_audit("LOGOUT", target=session.get('username'))
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.login'))

# ═══════════════════════════════════════════════════════════════════
# SECTION 3 — CITIZEN DASHBOARD
# ═══════════════════════════════════════════════════════════════════
@main.route('/dashboard')
@login_required
def dashboard():
    complaints = Complaint.query.filter_by(user_id=session['user_id']).order_by(Complaint.id.desc()).all()
    user = User.query.get(session['user_id'])
    wards_scores = []
    for ward_name in WARD_COORDINATES:
        bins = SmartBin.query.filter_by(ward=ward_name).all()
        avg_level = sum(b.level for b in bins) / len(bins) if bins else 0
        wards_scores.append({"ward": ward_name, "score": max(0, 100 - int(avg_level))})
    wards_scores.sort(key=lambda x: x['score'], reverse=True)
    bin_assets = SmartBin.query.all()
    invoices = PAYTInvoice.query.filter_by(user_id=session['user_id']).order_by(PAYTInvoice.issued_at.desc()).all()
    declarations = WasteDeclaration.query.filter_by(user_id=session['user_id']).order_by(WasteDeclaration.timestamp.desc()).limit(5).all()
    bins_data = [{'hardware_id': b.hardware_id, 'latitude': b.latitude, 'longitude': b.longitude,
                  'level': b.level, 'status': b.status} for b in bin_assets]
    # Pass the real registered phone so the report form pre-fills accurately
    current_user_phone = user.phone or ''
    return render_template('dashboard.html', complaints=complaints, green_points=user.green_points,
                           leaderboard=wards_scores, bins=bin_assets, bins_data=bins_data,
                           invoices=invoices, declarations=declarations, dump_yards=DUMP_YARDS,
                           current_user_phone=current_user_phone)

@main.route('/api/redeem', methods=['POST'])
@login_required
def redeem_rewards():
    user = User.query.get(session['user_id'])
    points_to_redeem = int(request.form.get('points', 0))
    reward_type = request.form.get('reward_type', '')
    if user.green_points >= points_to_redeem:
        user.green_points -= points_to_redeem
        db.session.commit()
        write_audit("REDEEM_POINTS", detail=f"Redeemed {points_to_redeem} pts for {reward_type}.")
        return jsonify({"success": True, "message": f"Coupon redeemed for {reward_type}!",
                        "new_points": user.green_points})
    return jsonify({"success": False, "message": "Insufficient green points."}), 400

# 4-Stream Waste Segregation Declaration
@main.route('/dashboard/declare-waste', methods=['POST'])
@login_required
def declare_waste():
    user = User.query.get(session['user_id'])
    wet = float(request.form.get('wet_kg', 0))
    dry = float(request.form.get('dry_kg', 0))
    sanitary = float(request.form.get('sanitary_kg', 0))
    hazardous = float(request.form.get('hazardous_kg', 0))
    ward = request.form.get('ward', '')
    declaration = WasteDeclaration(user_id=user.id, wet_kg=wet, dry_kg=dry,
                                   sanitary_kg=sanitary, hazardous_kg=hazardous, ward=ward)
    db.session.add(declaration)
    # Award green points for proper segregation
    total_kg = wet + dry + sanitary + hazardous
    points_earned = max(5, int(total_kg * 2))
    user.green_points += points_earned
    db.session.commit()
    write_audit("WASTE_DECLARATION", target=ward, detail=f"Declared {total_kg:.1f}kg total waste.")
    flash(f"Waste declaration submitted! Earned +{points_earned} Green Points 🌿", "success")
    return redirect(url_for('main.dashboard'))

# PAYT Invoice List API
@main.route('/api/payt-invoice')
@login_required
def payt_invoice_list():
    invoices = PAYTInvoice.query.filter_by(user_id=session['user_id']).all()
    return jsonify([{
        "id": inv.id, "period": inv.period, "weight_kg": inv.weight_kg,
        "amount_rs": inv.amount_rs, "status": inv.status,
        "issued_at": inv.issued_at.isoformat()
    } for inv in invoices])

# ═══════════════════════════════════════════════════════════════════
# SECTION 4 — ANONYMOUS ILLEGAL DUMP REPORT
# ═══════════════════════════════════════════════════════════════════
@main.route('/report-illegal', methods=['GET', 'POST'])
def report_illegal():
    if request.method == 'POST':
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        category = request.form.get('category', 'Unknown')
        description = request.form.get('description', '')
        ward = request.form.get('ward', '')
        photo_filename = None
        file = request.files.get('photo')
        if file and file.filename != '':
            filename = f"illegal_{random.randint(10000,99999)}_{secure_filename(file.filename)}"
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            # Strip EXIF metadata using Pillow if available
            try:
                from PIL import Image
                import io
                img = Image.open(file)
                # Create a new clean image (strips all metadata)
                clean_io = io.BytesIO()
                img.save(clean_io, format=img.format or 'JPEG')
                clean_io.seek(0)
                with open(upload_path, 'wb') as f_out:
                    f_out.write(clean_io.read())
            except ImportError:
                # Pillow not installed — save raw
                file.seek(0)
                file.save(upload_path)
            except Exception as e:
                print(f"EXIF strip error: {e}")
                file.seek(0)
                file.save(upload_path)
            photo_filename = f"uploads/{filename}"
        report = IllegalDumpReport(
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            category=category, description=description,
            scrubbed_photo=photo_filename, ward=ward, status="Pending"
        )
        db.session.add(report)
        db.session.commit()
        # No user_id stored — anonymous by design
        flash("Anonymous report submitted. Your identity is protected. Thank you! 🛡️", "success")
        return redirect(url_for('main.report_illegal'))
    return render_template('illegal_dump.html')

# ──────────────────────────────────────────────
# OMNICHANNEL HELPERS (WhatsApp / Telegram bot)
# ──────────────────────────────────────────────
def _extract_gps_from_exif(img):
    """Return (lat, lon) decimal degrees read from a PIL image's EXIF GPS tags."""
    try:
        from PIL.ExifTags import GPSTAGS, TAGS
        exif = img._getexif()
        if not exif:
            return None
        gps = {}
        for tag, val in exif.items():
            if TAGS.get(tag) == 'GPSInfo':
                for t, v in val.items():
                    gps[GPSTAGS.get(t, t)] = v
        if 'GPSLatitude' not in gps or 'GPSLongitude' not in gps:
            return None
        def _to_deg(value):
            d, m, s = value
            return float(d) + float(m) / 60.0 + float(s) / 3600.0
        lat = _to_deg(gps['GPSLatitude'])
        lon = _to_deg(gps['GPSLongitude'])
        if gps.get('GPSLatitudeRef') == 'S':
            lat = -lat
        if gps.get('GPSLongitudeRef') == 'W':
            lon = -lon
        return lat, lon
    except Exception as e:
        print(f"GPS EXIF parse error: {e}")
        return None

def _download_illegal_media(media_url, auth=None):
    """Download a remote image, extract native GPS from EXIF, strip EXIF, and
    save it. Returns (relative_upload_path_or_None, (lat,lon)_or_None)."""
    try:
        resp = requests.get(media_url, auth=auth, timeout=10)
        if resp.status_code != 200:
            return None, None
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(resp.content))
        gps = _extract_gps_from_exif(img)
        clean = io.BytesIO()
        img.save(clean, format=img.format or 'JPEG')
        clean.seek(0)
        filename = f"illegal_{random.randint(10000,99999)}.jpg"
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        with open(path, 'wb') as f:
            f.write(clean.read())
        return f"uploads/{filename}", gps
    except Exception as e:
        print(f"Media download error: {e}")
        return None, None

@main.route('/webhook/whatsapp', methods=['POST'])
def webhook_whatsapp():
    """Twilio WhatsApp inbound webhook. A citizen photos a trash pile; we extract
    GPS from the image (or supplied lat/lon), log an anonymous IllegalDumpReport,
    and reply with a TwiML acknowledgement."""
    from flask import Response
    form = request.form
    sender = form.get('From', '')
    body = form.get('Body', '')
    num_media = int(form.get('NumMedia', 0) or 0)
    lat = form.get('Latitude')
    lon = form.get('Longitude')
    photo, gps = None, None
    if num_media > 0:
        media_url = form.get('MediaUrl0')
        sid = os.environ.get('TWILIO_ACCOUNT_SID')
        token = os.environ.get('TWILIO_AUTH_TOKEN')
        auth = (sid, token) if sid and token else None
        photo, gps = _download_illegal_media(media_url, auth)
        if gps:
            lat, lon = gps
    report = IllegalDumpReport(
        latitude=float(lat) if lat else None,
        longitude=float(lon) if lon else None,
        category='WhatsApp Report',
        description=body or 'Illegal dump reported via WhatsApp bot.',
        scrubbed_photo=photo, ward='', status='Pending'
    )
    db.session.add(report)
    db.session.commit()
    write_audit("ILLEGAL_REPORT_WHATSAPP", detail=f"From {sender}, media={num_media}")
    twiml = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Response><Message>✅ Report received! Ticket #'
             f'{report.id} logged. Our team will inspect the location.</Message></Response>')
    return Response(twiml, mimetype='application/xml')

@main.route('/webhook/telegram', methods=['POST'])
def webhook_telegram():
    """Telegram Bot API webhook. Accepts a photo (+ optional location/caption),
    resolves the file via Telegram API, extracts GPS, logs an IllegalDumpReport."""
    data = request.get_json(silent=True) or {}
    message = data.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    caption = message.get('caption', '')
    location = message.get('location')
    lat = location.get('latitude') if location else None
    lon = location.get('longitude') if location else None
    photo, gps = None, None
    photos = message.get('photo')
    if photos:
        file_id = photos[-1]['file_id']  # largest resolution
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if token:
            try:
                fresp = requests.get(
                    f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}",
                    timeout=10).json()
                if fresp.get('ok'):
                    file_path = fresp['result']['file_path']
                    media_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                    photo, gps = _download_illegal_media(media_url)
            except Exception as e:
                print(f"Telegram file error: {e}")
    if gps:
        lat, lon = gps
    report = IllegalDumpReport(
        latitude=float(lat) if lat else None,
        longitude=float(lon) if lon else None,
        category='Telegram Report',
        description=caption or 'Illegal dump reported via Telegram bot.',
        scrubbed_photo=photo, ward='', status='Pending'
    )
    db.session.add(report)
    db.session.commit()
    write_audit("ILLEGAL_REPORT_TELEGRAM", detail=f"chat_id {chat_id}")
    # Telegram expects a 200 OK acknowledgement
    return jsonify({"ok": True, "ticket_id": report.id})


# ═══════════════════════════════════════════════════════════════════
# SECTION 4b — DEV SANDBOX: simulate WhatsApp / Telegram bots in-browser
# (no real Twilio/Telegram account needed — drives the public webhooks)
# ═══════════════════════════════════════════════════════════════════
@main.route('/api/illegal-reports')
@admin_required
def api_illegal_reports():
    """Recent illegal-dump reports (dev/demo helper for the sandbox UI)."""
    limit = min(int(request.args.get('limit', 10) or 10), 50)
    rows = IllegalDumpReport.query.order_by(IllegalDumpReport.timestamp.desc()).limit(limit).all()
    return jsonify([
        {
            'id': r.id,
            'category': r.category,
            'description': (r.description or '')[:120],
            'status': r.status,
            'latitude': r.latitude,
            'longitude': r.longitude,
            'scrubbed_photo': r.scrubbed_photo,
            'timestamp': r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ])


# ═══════════════════════════════════════════════════════════════════
# SECTION 5 — BWG COMMERCIAL LEDGER
# ═══════════════════════════════════════════════════════════════════
@main.route('/bwg-ledger', methods=['GET', 'POST'])
@login_required
def bwg_ledger():
    if request.method == 'POST':
        user = User.query.get(session['user_id'])
        entity_name = request.form.get('entity_name', '')
        entity_type = request.form.get('entity_type', 'commercial')
        composting_kg = float(request.form.get('composting_kg', 0))
        recyclable_kg = float(request.form.get('recyclable_kg', 0))
        landfill_kg = float(request.form.get('landfill_kg', 0))
        request_pickup = request.form.get('request_pickup') == 'on'
        decl = BWGDeclaration(
            user_id=user.id, entity_name=entity_name, entity_type=entity_type,
            composting_kg=composting_kg, recyclable_kg=recyclable_kg,
            landfill_kg=landfill_kg, request_bulk_pickup=request_pickup,
            pickup_status='Pending' if request_pickup else 'N/A'
        )
        db.session.add(decl)
        # Generate PAYT invoice with segregation-compliance penalty
        # (SWM Rules 2026: landfill fees penalise mixed/unsegregated waste)
        total_kg = composting_kg + recyclable_kg + landfill_kg
        segregated_kg = composting_kg + recyclable_kg  # exempt from landfill fee
        if total_kg > 0:
            compliance = round((segregated_kg / total_kg) * 100, 1)
        else:
            compliance = 100.0
        # Penalty multiplier: full compliance (100%) = 1.0; 0% = up to 2.0x
        penalty = round(1.0 + (100.0 - compliance) / 100.0, 2)
        if total_kg >= 100:
            base = round(total_kg * 1.5, 2)  # ₹1.5 per kg base rate
            amount = round(base * penalty, 2)
            invoice = PAYTInvoice(
                user_id=user.id,
                period=datetime.now(timezone.utc).strftime("%B %Y"),
                weight_kg=total_kg, bin_pickups=0,
                segregation_kg=segregated_kg, landfill_kg=landfill_kg,
                compliance_score=compliance, penalty_multiplier=penalty,
                base_amount_rs=base, amount_rs=amount, status='Unpaid'
            )
            db.session.add(invoice)
            if penalty > 1.0:
                flash(f"BWG Declaration recorded. PAYT Invoice of ₹{amount} generated "
                      f"(compliance {compliance:.0f}% → {penalty:.2f}x penalty applied).", "warning")
            else:
                flash(f"BWG Declaration recorded. PAYT Invoice of ₹{amount} generated for {total_kg:.0f}kg.", "success")
        else:
            flash("BWG Declaration submitted successfully.", "success")
        db.session.commit()
        write_audit("BWG_DECLARATION", target=entity_name, detail=f"{total_kg:.1f}kg declared.")
        return redirect(url_for('main.bwg_ledger'))
    declarations = BWGDeclaration.query.filter_by(user_id=session['user_id']).order_by(BWGDeclaration.timestamp.desc()).all()
    return render_template('bwg_ledger.html', declarations=declarations)

# ═══════════════════════════════════════════════════════════════════
# SECTION 6 — SCHEDULE
# ═══════════════════════════════════════════════════════════════════
@main.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    schedules = []
    prediction = None
    selected_ward = None
    if request.method == 'POST':
        selected_ward = request.form.get('ward')
        schedules = Schedule.query.filter_by(ward=selected_ward).all()
        try:
            prediction = predict_miss(selected_ward)
        except Exception as e:
            print(f"ML Prediction Error: {e}")
    return render_template('schedule.html', schedules=schedules, prediction=prediction, selected_ward=selected_ward)

# ═══════════════════════════════════════════════════════════════════
# SECTION 7 — COMPLAINT REPORTING
# ═══════════════════════════════════════════════════════════════════
@main.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        ward = request.form.get('ward')
        address = request.form.get('address')
        description = request.form.get('description')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        report_time = request.form.get('report_time')
        photo_filename = None
        file = request.files.get('photo')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            photo_filename = f"uploads/{filename}"
        new_complaint = Complaint(name=name, phone=phone, ward=ward,
                                  address=f"Chintalavalasa, {address}", description=description,
                                  photo=photo_filename, latitude=latitude, longitude=longitude,
                                  report_time=report_time, user_id=session['user_id'])
        db.session.add(new_complaint)
        user = User.query.get(session['user_id'])
        user.green_points += 15
        db.session.commit()
        write_audit("COMPLAINT_SUBMIT", target=ward, detail=f"Overflow report filed by {name}.")
        return render_template('success.html')
    return render_template('report.html')

# ═══════════════════════════════════════════════════════════════════
# SECTION 8 — ADMIN CONSOLE
# ═══════════════════════════════════════════════════════════════════
@main.route('/admin')
@admin_required
def admin():
    check_sensor_faults()  # Auto-flag stale sensors on every admin load
    check_decomposition_timers()  # Force 🟡 Pending Clearance on >48h stagnant bins
    complaints = Complaint.query.order_by(Complaint.id.desc()).all()
    bins = SmartBin.query.all()
    workers = WorkerProfile.query.all()
    incidents = IncidentLog.query.order_by(IncidentLog.id.desc()).all()
    sensor_healths = SensorHealth.query.all()
    firmware_releases = FirmwareRelease.query.order_by(FirmwareRelease.created_at.desc()).all()
    illegal_reports = IllegalDumpReport.query.order_by(IllegalDumpReport.timestamp.desc()).all()
    bwg_requests = BWGDeclaration.query.filter_by(request_bulk_pickup=True, pickup_status='Pending').all()
    kpis = {
        "total_bins": len(bins),
        "critical_bins": len([b for b in bins if b.status == "Critical"]),
        "active_trucks": len([w for w in workers if w.status == "Active"]),
        "pending_complaints": len([c for c in complaints if c.status == "Pending"]),
        "daily_waste_tons": round(sum(b.level for b in bins) * 0.045, 2),
        "sensor_faults": len([b for b in bins if b.sensor_fault]),
        "geofence_violations": len([w for w in workers if w.geofence_violation]),
        "pending_pickups": len(bwg_requests),
    }
    return render_template('admin.html', complaints=complaints, bins=bins, workers=workers,
                           incidents=incidents, kpis=kpis, webhooks=active_webhooks,
                           sensor_healths=sensor_healths, firmware_releases=firmware_releases,
                           illegal_reports=illegal_reports, bwg_requests=bwg_requests,
                           dump_yards=DUMP_YARDS)

# Dijkstra TSP Route Optimizer
@main.route('/api/route-optimize')
@login_required
def route_optimize():
    critical_bins = SmartBin.query.filter(SmartBin.level >= 80).all()
    depot = {"lat": DEFAULT_LAT, "lon": DEFAULT_LON, "label": "Municipal HQ (Depot)"}
    if not critical_bins:
        return jsonify({"route": [depot], "total_distance": 0, "message": "No critical bins today."})
    nodes = [{"lat": b.latitude, "lon": b.longitude, "label": b.hardware_id,
               "ward": b.ward, "level": b.level} for b in critical_bins]
    route = [depot]; current = depot; unvisited = list(nodes); total_dist = 0.0
    while unvisited:
        closest = min(unvisited, key=lambda n: (n['lat']-current['lat'])**2 + (n['lon']-current['lon'])**2)
        dist = math.sqrt((closest['lat']-current['lat'])**2 + (closest['lon']-current['lon'])**2)
        total_dist += dist
        route.append(closest); current = closest; unvisited.remove(closest)
    dist_back = math.sqrt((depot['lat']-current['lat'])**2 + (depot['lon']-current['lon'])**2)
    total_dist += dist_back; route.append(depot)
    km_distance = round(total_dist * 111.0, 2)
    # CO2 savings: traditional fixed-route = 45 km, optimized route saves the difference
    traditional_km = 45.0
    co2_saved_kg = round(max(0, traditional_km - km_distance) * 0.21, 2)
    write_audit("ROUTE_OPTIMIZE", detail=f"Optimized route: {km_distance}km, {len(critical_bins)} critical bins.")
    return jsonify({"route": route, "total_distance_km": km_distance,
                    "critical_count": len(critical_bins), "co2_saved_kg": co2_saved_kg})

# Fleet GPS API (simulated real-time positions)
@main.route('/api/fleet-location')
@admin_required
def fleet_location():
    workers = WorkerProfile.query.filter(WorkerProfile.status == 'Active').all()
    fleet = []
    for w in workers:
        # Simulate slight GPS drift from assigned position
        drift_lat = w.latitude + random.uniform(-0.001, 0.001)
        drift_lon = w.longitude + random.uniform(-0.001, 0.001)
        # Check geo-fence
        sector_poly = SECTOR_POLYGONS.get(w.vehicle_id, [])
        in_bounds = point_in_polygon(drift_lat, drift_lon, sector_poly) if sector_poly else True
        if not in_bounds and not w.geofence_violation:
            w.geofence_violation = True
            db.session.commit()
            write_audit("GEOFENCE_VIOLATION", target=w.vehicle_id,
                        detail=f"Vehicle {w.vehicle_id} exited assigned sector.")
        fleet.append({
            "vehicle_id": w.vehicle_id,
            "worker_username": w.user.username if w.user else "Unknown",
            "lat": drift_lat, "lon": drift_lon,
            "status": w.status,
            "in_bounds": in_bounds,
            "geofence_violation": w.geofence_violation
        })
    return jsonify(fleet)

# Webhook configuration
@main.route('/api/webhooks', methods=['POST'])
@admin_required
def configure_webhooks():
    url = request.form.get('webhook_url', '').strip()
    if url and url not in active_webhooks:
        active_webhooks.append(url)
        write_audit("WEBHOOK_ADD", target=url, detail="Webhook URL registered.")
        flash(f"Webhook registered: {url}", "success")
    return redirect(url_for('main.admin'))

# Complaint resolution
@main.route('/resolve/<int:id>')
@admin_required
def resolve_complaint(id):
    complaint = Complaint.query.get_or_404(id)
    complaint.status = 'Resolved'
    db.session.commit()
    write_audit("RESOLVE_COMPLAINT", target=f"Complaint #{id}", detail=f"Ward: {complaint.ward}")
    flash(f"Complaint #{id} resolved.", "success")
    return redirect(url_for('main.admin'))

# Admin approves BWG pickup request
@main.route('/admin/bwg-approve/<int:id>')
@admin_required
def bwg_approve(id):
    decl = BWGDeclaration.query.get_or_404(id)
    decl.pickup_status = 'Approved'
    db.session.commit()
    write_audit("BWG_APPROVE", target=decl.entity_name, detail=f"{decl.recyclable_kg}kg bulk pickup approved.")
    flash(f"Bulk pickup approved for {decl.entity_name}.", "success")
    return redirect(url_for('main.admin'))

# ═══════════════════════════════════════════════════════════════════
# SECTION 9 — AUDIT TRAIL (Super-Admin)
# ═══════════════════════════════════════════════════════════════════
@main.route('/admin/audit')
@admin_required
def audit_trail():
    user = User.query.get(session['user_id'])
    # All admins can see audit logs (super-admin sees everything, others see own)
    if user and user.is_superadmin:
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    else:
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render_template('audit_log.html', logs=logs, is_superadmin=(user.is_superadmin if user else False))

# ═══════════════════════════════════════════════════════════════════
# SECTION 10 — OTA FIRMWARE HUB
# ═══════════════════════════════════════════════════════════════════
@main.route('/admin/firmware')
@admin_required
def firmware_hub():
    releases = FirmwareRelease.query.order_by(FirmwareRelease.created_at.desc()).all()
    bins = SmartBin.query.all()
    return render_template('firmware.html', releases=releases, bins=bins)

@main.route('/admin/firmware/upload', methods=['POST'])
@admin_required
def firmware_upload():
    version = request.form.get('version', '').strip()
    description = request.form.get('description', '').strip()
    target_bins = request.form.get('target_bins', 'ALL').strip()
    file = request.files.get('firmware_file')
    if not version or not file or file.filename == '':
        flash("Version number and firmware file are required.", "error")
        return redirect(url_for('main.firmware_hub'))
    filename = secure_filename(f"firmware_v{version}_{file.filename}")
    upload_path = os.path.join(current_app.config.get('FIRMWARE_FOLDER',
                               current_app.config['UPLOAD_FOLDER']), filename)
    file.save(upload_path)
    release = FirmwareRelease(version=version, filename=filename, description=description,
                              target_bins=target_bins, push_status='Pending',
                              uploaded_by=session['user_id'])
    db.session.add(release); db.session.commit()
    write_audit("FIRMWARE_UPLOAD", target=f"v{version}", detail=f"File: {filename}, Targets: {target_bins}")
    flash(f"Firmware v{version} uploaded successfully. Ready to push.", "success")
    return redirect(url_for('main.firmware_hub'))

@main.route('/api/ota/<hw_id>', methods=['POST'])
@admin_required
def ota_push(hw_id):
    release_id = request.form.get('release_id')
    release = FirmwareRelease.query.get(release_id)
    if not release:
        return jsonify({"success": False, "message": "Firmware release not found."}), 404
    target_bin = SmartBin.query.filter_by(hardware_id=hw_id).first()
    if not target_bin:
        return jsonify({"success": False, "message": f"Bin {hw_id} not found."}), 404
    # Simulate OTA push (in production this would call MQTT or HTTP to the ESP32)
    success = random.random() > 0.1  # 90% success rate simulation
    if success:
        release.push_status = 'Pushed'
        release.pushed_at = datetime.now(timezone.utc)
        db.session.commit()
        write_audit("OTA_PUSH", target=hw_id, detail=f"Firmware v{release.version} pushed to {hw_id}.")
        return jsonify({"success": True, "message": f"OTA push to {hw_id} successful. Bin rebooting...",
                        "version": release.version})
    else:
        release.push_status = 'Failed'
        db.session.commit()
        return jsonify({"success": False, "message": f"OTA push to {hw_id} failed. Bin may be offline."}), 503

# ═══════════════════════════════════════════════════════════════════
# SECTION 11 — SANITATION WORKER PORTAL
# ═══════════════════════════════════════════════════════════════════
@main.route('/worker')
@worker_required
def worker():
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    work_bins = SmartBin.query.filter(SmartBin.level >= 50).all()
    offload_logs = OffloadLog.query.filter_by(worker_id=profile.id).order_by(
        OffloadLog.timestamp.desc()).limit(10).all() if profile else []
    task_bins_data = [{'hardware_id': b.hardware_id, 'latitude': b.latitude, 'longitude': b.longitude,
                       'level': b.level, 'status': b.status, 'ward': b.ward} for b in work_bins]
    return render_template('worker.html', profile=profile, work_bins=work_bins,
                           task_bins_data=task_bins_data,
                           offload_logs=offload_logs, dump_yards=DUMP_YARDS)

# Mark bin as cleared
@main.route('/resolve-bin/<string:hw_id>', methods=['POST'])
@login_required
def resolve_bin(hw_id):
    smart_bin = SmartBin.query.filter_by(hardware_id=hw_id).first_or_404()
    smart_bin.level = 0; smart_bin.status = "Safe"
    smart_bin.battery_level = min(100, smart_bin.battery_level + 10)
    smart_bin.temperature = 24.0; smart_bin.methane = 20.0
    smart_bin.sensor_fault = False
    smart_bin.last_updated = datetime.now(timezone.utc)
    unresolved = Complaint.query.filter_by(ward=smart_bin.ward, status="Pending").all()
    for comp in unresolved:
        comp.status = "Resolved"
        reporter = User.query.get(comp.user_id)
        if reporter: reporter.green_points += 10
    active_incidents = IncidentLog.query.filter_by(bin_id=smart_bin.id, status="Active").all()
    for inc in active_incidents: inc.status = "Resolved"
    # Also clear sensor fault if present
    sh = SensorHealth.query.filter_by(bin_id=smart_bin.id).first()
    if sh: sh.fault_flag = False; sh.maintenance_scheduled = False
    db.session.commit()
    write_audit("RESOLVE_BIN", target=hw_id, detail=f"Bin {hw_id} emptied and reset to Safe.")
    return jsonify({"success": True, "message": f"Bin {hw_id} cleared and reset!"})

# Toggle Solar-Powered Mechanical Pre-Compaction per bin
@main.route('/admin/toggle-compactor/<string:hw_id>', methods=['POST'])
@admin_required
def toggle_compactor(hw_id):
    smart_bin = SmartBin.query.filter_by(hardware_id=hw_id).first_or_404()
    smart_bin.precompaction_enabled = not smart_bin.precompaction_enabled
    db.session.commit()
    write_audit("TOGGLE_COMPACTOR", target=hw_id,
                detail=f"Solar pre-compaction {'ENABLED' if smart_bin.precompaction_enabled else 'DISABLED'}.")
    return jsonify({"success": True, "hardware_id": hw_id,
                    "precompaction_enabled": smart_bin.precompaction_enabled})

# Smart-bin telemetry for the admin GIS map (loaded client-side via fetch so the
# template stays free of server-injected Jinja inside the <script> block)
@main.route('/api/bins')
@login_required
def api_bins():
    bins = SmartBin.query.all()
    return jsonify([{
        "id": b.id,
        "hardware_id": b.hardware_id,
        "latitude": b.latitude,
        "longitude": b.longitude,
        "level": b.level,
        "battery": b.battery_level,
        "temperature": b.temperature,
        "methane": b.methane,
        "status": b.status,
        "ward": b.ward,
        "precompaction_enabled": b.precompaction_enabled,
    } for b in bins])

# Digital Manifest: Offload Checkpoint
@main.route('/worker/offload', methods=['POST'])
@worker_required
def worker_offload():
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        flash("Worker profile not found.", "error")
        return redirect(url_for('main.worker'))
    dump_yard_id = request.form.get('dump_yard_id', '')
    weight_kg = float(request.form.get('weight_kg', 0))
    # AI CV Impurity Check (simulated)
    impurity_detected = False
    impurity_detail = None
    # Simulate: if methane of any assigned critical bin > 300, flag impurity
    critical_bins = SmartBin.query.filter(SmartBin.level >= 80, SmartBin.methane > 300).all()
    if critical_bins and random.random() < 0.3:
        impurity_detected = True
        impurity_detail = f"CV Scanner flagged contaminated organic waste mixed with plastic in bin {critical_bins[0].hardware_id}. Sorting violation logged."
        incident = IncidentLog(bin_id=critical_bins[0].id, incident_type="Impurity Detected",
                               severity="Warning", status="Active", description=impurity_detail)
        db.session.add(incident)
    offload = OffloadLog(worker_id=profile.id, dump_yard_id=dump_yard_id, weight_kg=weight_kg,
                         vehicle_id=profile.vehicle_id, impurity_flagged=impurity_detected,
                         impurity_detail=impurity_detail, verified=True)
    db.session.add(offload)
    # Generate PAYT-style invoice context
    profile.status = 'Idle'
    db.session.commit()
    write_audit("OFFLOAD_LOG", target=dump_yard_id,
                detail=f"Worker {session.get('username')} dumped {weight_kg}kg at {dump_yard_id}.")
    if impurity_detected:
        flash(f"⚠️ Impurity flagged! {impurity_detail} Offload recorded with violation note.", "warning")
    else:
        flash(f"✅ Offload verified: {weight_kg}kg at {dump_yard_id}. Digital manifest logged!", "success")
    return redirect(url_for('main.worker'))

# Worker issue reporter
@main.route('/worker/report-issue', methods=['POST'])
@worker_required
def worker_report_issue():
    bin_hw_id = request.form.get('bin_id')
    issue_type = request.form.get('issue_type')
    details = request.form.get('details')
    target_bin = SmartBin.query.filter_by(hardware_id=bin_hw_id).first()
    incident = IncidentLog(bin_id=target_bin.id if target_bin else None,
                           incident_type=issue_type, severity="Warning", status="Active",
                           description=f"Worker reported [{issue_type}] — {details} (Bin: {bin_hw_id})")
    db.session.add(incident)
    db.session.commit()
    write_audit("WORKER_REPORT_ISSUE", target=bin_hw_id, detail=f"{issue_type}: {details}")
    flash("Issue flagged to administrative dashboard.", "success")
    return redirect(url_for('main.worker'))

# ═══════════════════════════════════════════════════════════════════
# SECTION 11.5 — IoT BIN TELEMETRY INGESTION
# ═══════════════════════════════════════════════════════════════════
def _recompute_bin_status(level):
    """Derive Safe / Warning / Critical status from fill level."""
    if level >= 80:
        return "Critical"
    if level >= 50:
        return "Warning"
    return "Safe"

@main.route('/api/bin-telemetry', methods=['POST'])
def bin_telemetry():
    """ESP32/Arduino smart-bin ingestion endpoint. Receives live sensor
    readings, updates the bin record in the database, clears stale sensor
    faults, and runs the emergency evaluation pipeline (fire / methane
    hazard detection + webhook dispatch) via evaluate_emergency_metrics()."""
    data = request.get_json(silent=True) or request.form
    hw_id = data.get('hardware_id') or data.get('id')
    if not hw_id:
        return jsonify({"success": False, "message": "hardware_id is required."}), 400

    smart_bin = SmartBin.query.filter_by(hardware_id=hw_id).first()
    if not smart_bin:
        return jsonify({"success": False, "message": f"Bin {hw_id} not found."}), 404

    try:
        if data.get('level') is not None:
            smart_bin.level = int(float(data.get('level')))
        if data.get('temperature') is not None:
            smart_bin.temperature = float(data.get('temperature'))
        if data.get('methane') is not None:
            smart_bin.methane = float(data.get('methane'))
        if data.get('battery_level') is not None:
            smart_bin.battery_level = int(float(data.get('battery_level')))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid numeric telemetry value."}), 400

    smart_bin.status = _recompute_bin_status(smart_bin.level)
    smart_bin.last_updated = datetime.now(timezone.utc)

    # ── Stagnant Rot & Decomposition Timer (Max 48h above 10% fill) ──
    now = datetime.now(timezone.utc)
    if smart_bin.level > 10:
        if smart_bin.decomposition_started_at is None:
            smart_bin.decomposition_started_at = now
    else:
        # Bin was cleared/emptied below threshold → reset the timer
        smart_bin.decomposition_started_at = None

    # ── Solar-Powered Mechanical Pre-Compaction (triggers at 70% fill) ──
    if smart_bin.precompaction_enabled and smart_bin.level >= 70:
        if (smart_bin.last_compacted_at is None or
                (now - smart_bin.last_compacted_at).total_seconds() > 3600):
            activate_compactor(smart_bin)

    # A live ping clears any previous "Sensor Fault" flag and its
    # predictive-maintenance record so the bin returns to healthy state.
    if smart_bin.sensor_fault:
        smart_bin.sensor_fault = False
        sh = SensorHealth.query.filter_by(bin_id=smart_bin.id).first()
        if sh:
            sh.fault_flag = False
            sh.maintenance_scheduled = False
        # Also resolve any open Sensor Fault incidents
        open_faults = IncidentLog.query.filter_by(
            bin_id=smart_bin.id, incident_type="Sensor Fault", status="Active").all()
        for inc in open_faults:
            inc.status = "Resolved"

    db.session.commit()

    # Run the hazard evaluation (creates incidents + fires webhooks on breach)
    evaluate_emergency_metrics(smart_bin)

    write_audit("BIN_TELEMETRY", target=hw_id,
                detail=f"Level {smart_bin.level}% | {smart_bin.temperature}°C | CH4 {smart_bin.methane}ppm")
    return jsonify({
        "success": True,
        "hardware_id": hw_id,
        "level": smart_bin.level,
        "status": smart_bin.status,
        "temperature": smart_bin.temperature,
        "methane": smart_bin.methane,
        "battery_level": smart_bin.battery_level
    })

# ═══════════════════════════════════════════════════════════════════
# SECTION 12 — ANALYTICS & COMPLIANCE
# ═══════════════════════════════════════════════════════════════════
def _compute_analytics():
    """Aggregate all analytics metrics. Shared by the page and the JSON API so
    no server data has to be embedded inside the template's <script>."""
    bins = SmartBin.query.all()
    all_declarations = WasteDeclaration.query.all()
    total_wet = sum(d.wet_kg for d in all_declarations)
    total_dry = sum(d.dry_kg for d in all_declarations)
    total_sanitary = sum(d.sanitary_kg for d in all_declarations)
    total_hazardous = sum(d.hazardous_kg for d in all_declarations)
    total_declared = total_wet + total_dry + total_sanitary + total_hazardous
    recycled = total_dry + total_hazardous
    landfill = total_wet + total_sanitary
    recycling_rate = round((recycled / total_declared * 100) if total_declared > 0 else 42.0, 1)

    traditional_km_monthly = 45.0 * 22  # 22 working days
    optimized_km_monthly = traditional_km_monthly * 0.78
    co2_saved_monthly_kg = round((traditional_km_monthly - optimized_km_monthly) * 0.21, 1)
    co2_saved_tonnes = round(co2_saved_monthly_kg / 1000, 3)

    generation_trends = {
        "labels": ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"],
        "organic": [12, 25, 18, 30, 45, 22],
        "plastic": [8, 14, 25, 20, 35, 15],
        "metal": [3, 7, 10, 5, 12, 8]
    }
    circular_economy = {
        "recycled_kg": round(recycled, 1),
        "landfill_kg": round(landfill, 1),
        "recycling_rate": recycling_rate,
        "wet_kg": round(total_wet, 1),
        "dry_kg": round(total_dry, 1),
        "sanitary_kg": round(total_sanitary, 1),
        "hazardous_kg": round(total_hazardous, 1),
    }
    carbon_data = {
        "traditional_km": traditional_km_monthly,
        "optimized_km": round(optimized_km_monthly, 1),
        "co2_saved_kg": co2_saved_monthly_kg,
        "co2_saved_tonnes": co2_saved_tonnes,
        "trees_equivalent": round(co2_saved_tonnes * 45, 1),
    }
    bins_json = [{"lat": b.latitude, "lon": b.longitude, "level": b.level} for b in bins]
    return {
        "circular": circular_economy,
        "carbon": carbon_data,
        "bins": bins_json,
        "trends": generation_trends,
    }

@main.route('/analytics')
@login_required
def analytics():
    d = _compute_analytics()
    # circular_economy / carbon_data are still passed for the static text displays
    return render_template('analytics.html',
                           circular_economy=d['circular'],
                           carbon_data=d['carbon'])

@main.route('/api/analytics-data')
@login_required
def analytics_data():
    return jsonify(_compute_analytics())

# ESG/CSRD Compliance Export data endpoint (data for client-side jsPDF)
@main.route('/analytics/csrd-export')
@admin_required
def csrd_export():
    all_declarations = WasteDeclaration.query.all()
    all_offloads = OffloadLog.query.all()
    all_audits = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return jsonify({
        "report_title": "SmartGarbage ESG/CSRD Compliance Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "municipality": "Chintalavalasa, Vizianagaram",
        "waste_declarations": [{
            "id": d.id, "wet_kg": d.wet_kg, "dry_kg": d.dry_kg,
            "sanitary_kg": d.sanitary_kg, "hazardous_kg": d.hazardous_kg,
            "ward": d.ward, "timestamp": d.timestamp.isoformat()
        } for d in all_declarations],
        "offload_logs": [{
            "id": o.id, "dump_yard": o.dump_yard_id, "weight_kg": o.weight_kg,
            "verified": o.verified, "impurity_flagged": o.impurity_flagged,
            "timestamp": o.timestamp.isoformat()
        } for o in all_offloads],
        "audit_trail_sample": [{
            "username": a.username, "action": a.action, "target": a.target,
            "timestamp": a.timestamp.isoformat()
        } for a in all_audits]
    })

# ═══════════════════════════════════════════════════════════════════
# SECTION 13 — PWA STATIC ROUTES
# ═══════════════════════════════════════════════════════════════════
@main.route('/sw.js')
def serve_sw():
    return send_from_directory(os.path.join(current_app.root_path, 'static'),
                                'sw.js', mimetype='application/javascript')

@main.route('/manifest.json')
def serve_manifest():
    return send_from_directory(os.path.join(current_app.root_path, 'static'),
                                'manifest.json', mimetype='application/json')
