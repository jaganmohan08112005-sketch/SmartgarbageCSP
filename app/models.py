from . import db
from datetime import datetime, timezone

# ──────────────────────────────────────────────
# CORE USER MODEL
# ──────────────────────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default='citizen', nullable=False)  # 'citizen', 'worker', 'admin'
    phone = db.Column(db.String(20), nullable=True)
    green_points = db.Column(db.Integer, default=0, nullable=False)
    otp = db.Column(db.String(10), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)  # admin must approve new accounts
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    # v2: Gamification — segregation streak (consecutive declarations with >0 segregated kg)
    segregation_streak = db.Column(db.Integer, default=0, nullable=False)

# ──────────────────────────────────────────────
# COLLECTION SCHEDULE
# ──────────────────────────────────────────────
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    district = db.Column(db.String(100), nullable=True)
    ward = db.Column(db.String(100), nullable=False)
    day = db.Column(db.String(20))
    time_slot = db.Column(db.String(50))
    vehicle_id = db.Column(db.String(20))

# ──────────────────────────────────────────────
# CITIZEN COMPLAINT / OVERFLOW REPORT
# ──────────────────────────────────────────────
class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    ward = db.Column(db.String(100))
    address = db.Column(db.Text)
    description = db.Column(db.Text)
    photo = db.Column(db.String(200))
    status = db.Column(db.String(20), default='Pending')
    latitude = db.Column(db.String(50), nullable=True)
    longitude = db.Column(db.String(50), nullable=True)
    report_time = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ──────────────────────────────────────────────
# SMART BIN (IoT Telemetry)
# ──────────────────────────────────────────────
class SmartBin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hardware_id = db.Column(db.String(50), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    level = db.Column(db.Integer, default=0, nullable=False)         # 0–100%
    battery_level = db.Column(db.Integer, default=100, nullable=False)
    temperature = db.Column(db.Float, default=25.0, nullable=False)   # °C
    methane = db.Column(db.Float, default=50.0, nullable=False)       # ppm
    status = db.Column(db.String(20), default='Safe', nullable=False) # Safe / Warning / Critical
    ward = db.Column(db.String(100), nullable=False)
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # v2 additions
    overflow_eta_hours = db.Column(db.Float, nullable=True)           # AI estimator: hours until overflow
    waste_stream = db.Column(db.String(20), default='mixed')          # wet/dry/sanitary/hazardous/mixed
    sensor_fault = db.Column(db.Boolean, default=False, nullable=False)
    # Decomposition timer & solar pre-compaction
    decomposition_started_at = db.Column(db.DateTime, nullable=True)  # timestamp when level first exceeded 10%
    precompaction_enabled = db.Column(db.Boolean, default=False, nullable=False)
    last_compacted_at = db.Column(db.DateTime, nullable=True)

# ──────────────────────────────────────────────
# WORKER / DRIVER PROFILE
# ──────────────────────────────────────────────
class WorkerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    vehicle_id = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Float, default=18.0675)
    longitude = db.Column(db.Float, default=83.4094)
    status = db.Column(db.String(20), default='Idle', nullable=False) # Active / Idle / Off-Duty
    performance_rating = db.Column(db.Float, default=5.0, nullable=False)
    # v2: Geo-fencing
    sector_polygon = db.Column(db.Text, nullable=True)                # JSON polygon string
    current_lat = db.Column(db.Float, nullable=True)
    current_lon = db.Column(db.Float, nullable=True)
    geofence_violation = db.Column(db.Boolean, default=False, nullable=False)
    # v2: Worker Safety & Compliance (SBM Grameen II)
    ppe_compliance = db.Column(db.Boolean, default=False, nullable=False)     # PPE kit issued & used
    training_completed = db.Column(db.Boolean, default=False, nullable=False) # Safety training completed
    insurance_enrolled = db.Column(db.Boolean, default=False, nullable=False) # PMJAY/insurance enrolled
    insurance_policy_no = db.Column(db.String(50), nullable=True)              # Policy number
    last_training_date = db.Column(db.DateTime, nullable=True)                 # Last training date
    last_medical_checkup = db.Column(db.DateTime, nullable=True)               # Last medical checkup
    # v2: Informal waste-picker recognition (SBM Grameen Phase II)
    is_informal_picker = db.Column(db.Boolean, default=False, nullable=False)
    picker_area = db.Column(db.String(100), nullable=True)           # ward/area they operate in
    picker_id_card = db.Column(db.String(50), nullable=True)        # recognition ID

    user = db.relationship('User', backref=db.backref('worker_profile', uselist=False))

# ──────────────────────────────────────────────
# INCIDENT / EMERGENCY LOG
# ──────────────────────────────────────────────
class IncidentLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), nullable=True)
    incident_type = db.Column(db.String(50), nullable=False)  # Fire Hazard / Vandalism / Methane Leak / Overflow / Sensor Fault / Impurity
    severity = db.Column(db.String(20), nullable=False)       # Critical / Warning
    status = db.Column(db.String(20), default='Active', nullable=False)
    description = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    bin = db.relationship('SmartBin', backref=db.backref('incidents', lazy=True))

# ──────────────────────────────────────────────
# v2: AUDIT TRAIL LOG (Security Ledger)
# ──────────────────────────────────────────────
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(100), nullable=True)       # denormalized for immutability
    role = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(100), nullable=False)        # e.g. "RESOLVE_BIN", "LOGIN", "OFFLOAD_LOG"
    target = db.Column(db.String(100), nullable=True)         # e.g. "BIN-302", "Route #3"
    detail = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))

# ──────────────────────────────────────────────
# v2: SENSOR HEALTH (Predictive Maintenance)
# ──────────────────────────────────────────────
class SensorHealth(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), unique=True, nullable=False)
    battery_voltage = db.Column(db.Float, default=3.7, nullable=False)   # Volts
    calibration_drift = db.Column(db.Float, default=0.0, nullable=False) # % drift from baseline
    last_ping = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    fault_flag = db.Column(db.Boolean, default=False, nullable=False)
    fault_reason = db.Column(db.String(200), nullable=True)
    maintenance_scheduled = db.Column(db.Boolean, default=False, nullable=False)

    bin = db.relationship('SmartBin', backref=db.backref('sensor_health', uselist=False))

# ──────────────────────────────────────────────
# v2: OFFLOAD LOG (Irreversible Dump Manifest)
# ──────────────────────────────────────────────
class OffloadLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker_profile.id'), nullable=False)
    dump_yard_id = db.Column(db.String(50), nullable=False)              # e.g. "YARD-A", "YARD-B"
    weight_kg = db.Column(db.Float, nullable=False)
    vehicle_id = db.Column(db.String(20), nullable=True)
    impurity_flagged = db.Column(db.Boolean, default=False, nullable=False)
    impurity_detail = db.Column(db.String(200), nullable=True)
    verified = db.Column(db.Boolean, default=True, nullable=False)       # immutable once created
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    worker = db.relationship('WorkerProfile', backref=db.backref('offload_logs', lazy=True))

# ──────────────────────────────────────────────
# v2: ANONYMOUS ILLEGAL DUMP REPORT
# ──────────────────────────────────────────────
class IllegalDumpReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(100), nullable=False)  # e-waste / chemical / medical / construction
    description = db.Column(db.Text, nullable=True)
    scrubbed_photo = db.Column(db.String(200), nullable=True)   # EXIF-stripped
    ward = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='Pending', nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ──────────────────────────────────────────────
# v2: 4-STREAM WASTE DECLARATION
# ──────────────────────────────────────────────
class WasteDeclaration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wet_kg = db.Column(db.Float, default=0.0, nullable=False)           # Organic / Kitchen
    dry_kg = db.Column(db.Float, default=0.0, nullable=False)           # Plastics / Paper / Metals
    sanitary_kg = db.Column(db.Float, default=0.0, nullable=False)      # Securely wrapped items
    hazardous_kg = db.Column(db.Float, default=0.0, nullable=False)     # Batteries / E-waste / Bulbs
    ward = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('waste_declarations', lazy=True))

# ──────────────────────────────────────────────
# v2: BULK WASTE GENERATOR (BWG) LEDGER
# ──────────────────────────────────────────────
class BWGDeclaration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    entity_name = db.Column(db.String(200), nullable=False)             # Apartment / Mall name
    entity_type = db.Column(db.String(50), nullable=False)              # residential / commercial / institution
    composting_kg = db.Column(db.Float, default=0.0, nullable=False)   # On-site compost declared
    recyclable_kg = db.Column(db.Float, default=0.0, nullable=False)   # Recyclables for pickup
    landfill_kg = db.Column(db.Float, default=0.0, nullable=False)     # Residual landfill waste
    request_bulk_pickup = db.Column(db.Boolean, default=False, nullable=False)
    pickup_status = db.Column(db.String(20), default='Pending', nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('bwg_declarations', lazy=True))

# ──────────────────────────────────────────────
# v2: PAY-AS-YOU-THROW (PAYT) INVOICE
# ──────────────────────────────────────────────
class PAYTInvoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    period = db.Column(db.String(50), nullable=False)                   # e.g. "July 2025"
    weight_kg = db.Column(db.Float, default=0.0, nullable=False)
    bin_pickups = db.Column(db.Integer, default=0, nullable=False)
    segregation_kg = db.Column(db.Float, default=0.0, nullable=False)  # compostable+recyclable (exempt)
    landfill_kg = db.Column(db.Float, default=0.0, nullable=False)    # residual (taxed)
    compliance_score = db.Column(db.Float, default=100.0, nullable=False) # 0-100% segregated
    penalty_multiplier = db.Column(db.Float, default=1.0, nullable=False) # 1.0 = full compliance
    base_amount_rs = db.Column(db.Float, default=0.0, nullable=False)
    amount_rs = db.Column(db.Float, default=0.0, nullable=False)        # ₹ amount (after penalty)
    status = db.Column(db.String(20), default='Unpaid', nullable=False) # Unpaid / Paid / Waived
    issued_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('payt_invoices', lazy=True))

# ──────────────────────────────────────────────
# v2: OTA FIRMWARE RELEASE
# ──────────────────────────────────────────────
class FirmwareRelease(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), nullable=False)                  # e.g. "2.1.4"
    filename = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    target_bins = db.Column(db.Text, nullable=True)                     # comma-separated hw_ids or "ALL"
    pushed_at = db.Column(db.DateTime, nullable=True)
    push_status = db.Column(db.String(20), default='Pending', nullable=False) # Pending / Pushed / Failed
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────
# v2: CITIZEN NOTIFICATION (real-time status push)
# ──────────────────────────────────────────────
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(200), nullable=True)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))
