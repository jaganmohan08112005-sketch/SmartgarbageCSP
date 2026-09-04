from . import db
from datetime import datetime, timezone
from flask_login import UserMixin


def utcnow():
    """Naive-UTC wall clock for DB columns (Postgres parity).

    Every DateTime column is `timestamp without time zone`, so a tz-aware
    value would either be rejected or silently shifted by the DB session's
    timezone on Postgres (SQLite ignores tz entirely). The app therefore
    stores UTC wall-clock time and only normalizes to aware UTC for
    arithmetic (see the read-side guards in ml_model / routes).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ──────────────────────────────────────────────
# CORE USER MODEL
# ──────────────────────────────────────────────
class User(db.Model, UserMixin):
    # `user` is a reserved word in PostgreSQL — SQLAlchemy/Alembic auto-quote
    # it in DDL and ORM SQL, so this is safe as long as nobody writes raw SQL
    # against it (quoted: SELECT * FROM "user"). Declared explicitly so the
    # table name is visible and greppable.
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default='citizen', nullable=False)  # 'citizen', 'worker', 'admin'
    phone = db.Column(db.String(20), nullable=True)
    green_points = db.Column(db.Integer, default=0, nullable=False)
    otp = db.Column(db.String(128), nullable=True)  # sha256 hex digest (64 chars)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)  # admin must approve new accounts
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    # v2: Gamification — segregation streak (consecutive declarations with >0 segregated kg)
    segregation_streak = db.Column(db.Integer, default=0, nullable=False)
    # v3: Household size for waste-declaration plausibility checks
    household_size = db.Column(db.Integer, default=1, nullable=False)

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


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
    __table_args__ = (
        # Hot path: admin ward sweeps (resolve_bin) + transparency view filter
        # on (ward, status). Composite index avoids a full scan per ward.
        db.Index('ix_complaint_ward_status', 'ward', 'status'),
        # Lifecycle state machine: SLA escalation + per-status admin sweeps.
        db.Index('ix_complaint_status_created', 'status', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    ward = db.Column(db.String(100))
    address = db.Column(db.Text)
    description = db.Column(db.Text)
    photo = db.Column(db.String(200))
    status = db.Column(db.String(20), default='Submitted')
    latitude = db.Column(db.String(50), nullable=True)
    longitude = db.Column(db.String(50), nullable=True)
    report_time = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    # v3: Complaint lifecycle state machine (Submitted → Under Review →
    # Assigned → In Progress → Resolved → Closed) with SLA + escalation.
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), nullable=True, index=True)
    assigned_worker_id = db.Column(db.Integer, db.ForeignKey('worker_profile.id'), nullable=True)
    sla_deadline = db.Column(db.DateTime, nullable=True)
    escalated = db.Column(db.Boolean, default=False, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)


# ──────────────────────────────────────────────
# v4: COMPLAINT STATUS TIMELINE (citizen tracking)
# One row per status transition — powers the public /track/<token> timeline
# (Submitted → Under Review → Assigned → In Progress → Escalated → Resolved
# → Closed). Written by record_complaint_event() at every transition so the
# citizen sees a real history, not just the current status.
# ──────────────────────────────────────────────
class ComplaintStatusLog(db.Model):
    __table_args__ = (
        # Hot path: timeline reads for one complaint ordered by time.
        db.Index('ix_complaint_status_log_complaint_created', 'complaint_id', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)   # Submitted / Under Review / Assigned / In Progress / Escalated / Resolved / Closed
    note = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    complaint = db.relationship('Complaint', backref=db.backref('status_logs', lazy=True))


# ──────────────────────────────────────────────
# SMART BIN (IoT Telemetry)
# ──────────────────────────────────────────────
class SmartBin(db.Model):
    __table_args__ = (
        # Hot path: dispatch queue sorting by forecast urgency + fill level.
        db.Index('ix_smart_bin_eta_level', 'overflow_eta_hours', 'level'),
    )
    id = db.Column(db.Integer, primary_key=True)
    hardware_id = db.Column(db.String(50), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    level = db.Column(db.Integer, default=0, nullable=False)         # 0–100%
    battery_level = db.Column(db.Integer, default=100, nullable=False)
    temperature = db.Column(db.Float, default=25.0, nullable=False)   # °C
    methane = db.Column(db.Float, default=50.0, nullable=False)       # ppm
    status = db.Column(db.String(20), default='Safe', nullable=False)  # Safe / Warning / Critical
    ward = db.Column(db.String(100), nullable=False, index=True)
    last_updated = db.Column(db.DateTime, default=utcnow, index=True)
    # v2 additions
    overflow_eta_hours = db.Column(db.Float, nullable=True)           # AI estimator: hours until overflow
    waste_stream = db.Column(db.String(20), default='mixed')          # wet/dry/sanitary/hazardous/mixed
    sensor_fault = db.Column(db.Boolean, default=False, nullable=False)
    # Decomposition timer & solar pre-compaction
    decomposition_started_at = db.Column(db.DateTime, nullable=True)  # timestamp when level first exceeded 10%
    precompaction_enabled = db.Column(db.Boolean, default=False, nullable=False)
    last_compacted_at = db.Column(db.DateTime, nullable=True)
    # v3: ETA recompute throttling (only recompute when level changes >5% or 15 min elapsed)
    last_eta_computed_at = db.Column(db.DateTime, nullable=True)
    # v4: Close-the-loop accountability — a bin may ONLY be cleared after the
    # worker uploads a real-time geotagged After-photo. The photo path is kept
    # here so the audit trail can point at the evidence for every clearance.
    after_photo = db.Column(db.String(200), nullable=True)
    # v5: Lid-state telemetry — 'open' vs 'closed' (False when the sensor
    # never reports). An open lid and structural overflow are DIFFERENT
    # events: an open lid needs a service vehicle, not an emergency dispatch.
    lid_open = db.Column(db.Boolean, default=False, nullable=False)


# ──────────────────────────────────────────────
# IOT DEVICE (per-bin authentication)
# ──────────────────────────────────────────────
class Device(db.Model):
    __tablename__ = 'device'
    id = db.Column(db.Integer, primary_key=True)
    hardware_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    api_key_hash = db.Column(db.String(128), nullable=False)  # sha256 hex digest (64 chars)
    name = db.Column(db.String(100), nullable=True)            # human label, e.g. "BIN-301 Sensor"
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_seen = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    bin = db.relationship('SmartBin', backref=db.backref('device', uselist=False),
                          primaryjoin='Device.hardware_id == SmartBin.hardware_id',
                          foreign_keys='Device.hardware_id')


# ──────────────────────────────────────────────
# WORKER / DRIVER PROFILE
# ──────────────────────────────────────────────
class WorkerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    vehicle_id = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Float, default=18.0675)
    longitude = db.Column(db.Float, default=83.4094)
    status = db.Column(db.String(20), default='Idle', nullable=False)  # Active / Idle / Off-Duty
    performance_rating = db.Column(db.Float, default=5.0, nullable=False)
    # v2: Geo-fencing
    sector_polygon = db.Column(db.Text, nullable=True)                # JSON polygon string
    current_lat = db.Column(db.Float, nullable=True)
    current_lon = db.Column(db.Float, nullable=True)
    geofence_violation = db.Column(db.Boolean, default=False, nullable=False)
    # v2: Worker Safety & Compliance (SBM Grameen II)
    ppe_compliance = db.Column(db.Boolean, default=False, nullable=False)     # PPE kit issued & used
    training_completed = db.Column(db.Boolean, default=False, nullable=False)  # Safety training completed
    insurance_enrolled = db.Column(db.Boolean, default=False, nullable=False)  # PMJAY/insurance enrolled
    insurance_policy_no = db.Column(db.String(50), nullable=True)              # Policy number
    last_training_date = db.Column(db.DateTime, nullable=True)                 # Last training date
    last_medical_checkup = db.Column(db.DateTime, nullable=True)               # Last medical checkup
    # v2: Informal waste-picker recognition (SBM Grameen Phase II)
    is_informal_picker = db.Column(db.Boolean, default=False, nullable=False)
    picker_area = db.Column(db.String(100), nullable=True)           # ward/area they operate in
    picker_id_card = db.Column(db.String(50), nullable=True)        # recognition ID

    user = db.relationship('User', backref=db.backref('worker_profile', uselist=False))


# ──────────────────────────────────────────────
# LIVE TELEMETRY HISTORY (per-ping level snapshots)
# Every bin-telemetry ping appends a row here, giving _estimate_fill_rate_hour_pct
# the actual fill-velocity signal (real level-vs-time points) instead of inferring
# it from a single anchor timestamp. Feeds the fill-rate regressor's retraining.
# Retention-pruned in bin_telemetry (bounded per-bin window) so it stays lean.
# ──────────────────────────────────────────────
class BinTelemetryLog(db.Model):
    __table_args__ = (
        # Hot path: per-bin history reads (fill-velocity) ordered by time.
        db.Index('ix_bin_telemetry_log_bin_timestamp', 'bin_id', 'timestamp'),
    )
    id = db.Column(db.Integer, primary_key=True)
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), nullable=False)
    level = db.Column(db.Integer, nullable=False)          # 0-100% snapshot
    temperature = db.Column(db.Float, nullable=True)
    methane = db.Column(db.Float, nullable=True)
    battery_level = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)

    bin = db.relationship('SmartBin', backref=db.backref('telemetry_logs', lazy=True))


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
    timestamp = db.Column(db.DateTime, default=utcnow)

    bin = db.relationship('SmartBin', backref=db.backref('incidents', lazy=True))


# ──────────────────────────────────────────────
# v2: AUDIT TRAIL LOG (Security Ledger)
# ──────────────────────────────────────────────
class AuditLog(db.Model):
    __table_args__ = (
        # Hot path: Razorpay webhook dedupe (action + target) + admin audit view.
        db.Index('ix_audit_action_target', 'action', 'target'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(100), nullable=True)       # denormalized for immutability
    role = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(100), nullable=False)        # e.g. "RESOLVE_BIN", "LOGIN", "OFFLOAD_LOG"
    target = db.Column(db.String(100), nullable=True)         # e.g. "BIN-302", "Route #3"
    detail = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))


# ──────────────────────────────────────────────
# v2: SENSOR HEALTH (Predictive Maintenance)
# ──────────────────────────────────────────────
class SensorHealth(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), unique=True, nullable=False)
    battery_voltage = db.Column(db.Float, default=3.7, nullable=False)   # Volts
    calibration_drift = db.Column(db.Float, default=0.0, nullable=False)  # % drift from baseline
    last_ping = db.Column(db.DateTime, default=utcnow)
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
    timestamp = db.Column(db.DateTime, default=utcnow)

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
    ward = db.Column(db.String(100), nullable=True, index=True)
    status = db.Column(db.String(20), default='Pending', nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)


# ──────────────────────────────────────────────
# v2: 4-STREAM WASTE DECLARATION
# ──────────────────────────────────────────────
class WasteDeclaration(db.Model):
    __table_args__ = (
        # Hot path: ward-scoped analytics + transparency filters on
        # (ward, timestamp) — the trend-over-time and per-ward segregation
        # queries GROUP BY month across a ward's rows. Composite index avoids
        # a full-table scan once declarations grow past tens of thousands.
        db.Index('ix_waste_declaration_ward_timestamp', 'ward', 'timestamp'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    wet_kg = db.Column(db.Float, default=0.0, nullable=False)           # Organic / Kitchen
    dry_kg = db.Column(db.Float, default=0.0, nullable=False)           # Plastics / Paper / Metals
    sanitary_kg = db.Column(db.Float, default=0.0, nullable=False)      # Securely wrapped items
    hazardous_kg = db.Column(db.Float, default=0.0, nullable=False)     # Batteries / E-waste / Bulbs
    ward = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow)
    # v3: Plausibility flag — set when declared kg exceeds ward/household norms.
    flagged_outlier = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship('User', backref=db.backref('waste_declarations', lazy=True))


# ──────────────────────────────────────────────
# v2: BULK WASTE GENERATOR (BWG) LEDGER
# ──────────────────────────────────────────────
class BWGDeclaration(db.Model):
    __table_args__ = (
        # Every citizen ledger view filters by user_id.
        db.Index('ix_bwg_declaration_user_id', 'user_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    entity_name = db.Column(db.String(200), nullable=False)             # Apartment / Mall name
    entity_type = db.Column(db.String(50), nullable=False)              # residential / commercial / institution
    composting_kg = db.Column(db.Float, default=0.0, nullable=False)   # On-site compost declared
    recyclable_kg = db.Column(db.Float, default=0.0, nullable=False)   # Recyclables for pickup
    landfill_kg = db.Column(db.Float, default=0.0, nullable=False)     # Residual landfill waste
    request_bulk_pickup = db.Column(db.Boolean, default=False, nullable=False)
    pickup_status = db.Column(db.String(20), default='Pending', nullable=False)
    timestamp = db.Column(db.DateTime, default=utcnow)

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
    compliance_score = db.Column(db.Float, default=100.0, nullable=False)  # 0-100% segregated
    penalty_multiplier = db.Column(db.Float, default=1.0, nullable=False)  # 1.0 = full compliance
    base_amount_rs = db.Column(db.Float, default=0.0, nullable=False)
    amount_rs = db.Column(db.Float, default=0.0, nullable=False)        # ₹ amount (after penalty)
    status = db.Column(db.String(20), default='Unpaid', nullable=False)  # Unpaid / Paid / Waived
    issued_at = db.Column(db.DateTime, default=utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    transaction_ref = db.Column(db.String(120), nullable=True)  # UPI ref / RRN / Razorpay payment id
    payment_method = db.Column(db.String(20), default='UPI', nullable=True)  # UPI / Razorpay
    # Server-side Razorpay order id (created before checkout so the capture
    # webhook can map an order back to its invoice without trusting the client).
    razorpay_order_id = db.Column(db.String(64), nullable=True, index=True)
    # Razorpay payment.failed tracking. Strictly informational: invoice.status
    # is CAPTURE-DRIVEN (only payment.captured / signature-verified verify
    # flips it to Paid). These columns let the pay page show a friendly retry
    # state and admins audit failed attempts without ever trusting a failure
    # event to change billing state.
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    last_failed_at = db.Column(db.DateTime, nullable=True)
    last_failed_reason = db.Column(db.String(200), nullable=True)
    # Admin waive / Razorpay-refund tracking. Status gains 'Refunded' (money
    # reversed via the Razorpay Refunds API) and 'Waived' (debt forgiven, no
    # money moves). refund_id is the Razorpay refund id — its presence is the
    # idempotency guard: a second admin refund attempt is a no-op.
    refund_id = db.Column(db.String(64), nullable=True, index=True)
    refunded_at = db.Column(db.DateTime, nullable=True)
    refund_reason = db.Column(db.String(200), nullable=True)
    # v3: Billing integrity — only worker-verified weights drive invoice amounts.
    billing_status = db.Column(db.String(20), default='Self-Reported', nullable=False)  # Self-Reported / Verified / Disputed
    verified_weight_kg = db.Column(db.Float, nullable=True)
    discrepancy_pct = db.Column(db.Float, nullable=True)

    user = db.relationship('User', backref=db.backref('payt_invoices', lazy=True))


# ──────────────────────────────────────────────
# v2: OTA FIRMWARE RELEASE
# ──────────────────────────────────────────────
class FirmwareRelease(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(20), nullable=False)                  # e.g. "2.1.4"
    filename = db.Column(db.String(200), nullable=False)
    sha256 = db.Column(db.String(64), nullable=True)                    # integrity hash of the artifact
    description = db.Column(db.Text, nullable=True)
    target_bins = db.Column(db.Text, nullable=True)                     # comma-separated hw_ids or "ALL"
    pushed_at = db.Column(db.DateTime, nullable=True)
    push_status = db.Column(db.String(20), default='Pending', nullable=False)  # Pending / Pushed / Failed
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)


# ──────────────────────────────────────────────
# v2: WEBHOOK REGISTRATION (persisted — survives restarts, shared across workers)
# ──────────────────────────────────────────────
class Webhook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f'<Webhook {self.url}>'


# ──────────────────────────────────────────────
# v2: CITIZEN NOTIFICATION (real-time status push)
# ──────────────────────────────────────────────
class Notification(db.Model):
    __table_args__ = (
        # Hot path: per-citizen notification lists (dashboard) filtered by
        # read-state and sorted by recency, plus the dunning dedupe lookup
        # (user_id + link). The citizen stream grows with every status change.
        db.Index('ix_notification_user_read_created', 'user_id', 'read', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(200), nullable=True)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))


# ──────────────────────────────────────────────
# PUSH NOTIFICATION SUBSCRIPTIONS (Web Push API)
# Stores browser push subscriptions so the server can send notifications
# when complaint status changes. One user may have multiple devices.
# ──────────────────────────────────────────────
class PushSubscription(db.Model):
    __table_args__ = (
        db.Index('ix_push_sub_user', 'user_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('push_subscriptions', lazy=True))


# ──────────────────────────────────────────────
# PUSH NOTIFICATION DELIVERY LOGS
# Records every push send attempt for admin analytics: sent, delivered,
# failed, dead subscription. Enables admins to monitor push health.
# ──────────────────────────────────────────────
class PushNotificationLog(db.Model):
    __table_args__ = (
        db.Index('ix_push_log_user_created', 'user_id', 'created_at'),
        db.Index('ix_push_log_status_created', 'status', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, index=True)  # sent, delivered, failed, dead
    error = db.Column(db.Text, nullable=True)
    endpoint = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    user = db.relationship('User', backref=db.backref('push_logs', lazy=True))


# ──────────────────────────────────────────────
# NOTIFICATION PREFERENCES
# Per-user toggle for which events trigger push notifications.
# One row per user; all defaults True (opt-out model).
# ──────────────────────────────────────────────
class NotificationPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    # Complaint lifecycle
    complaint_submitted = db.Column(db.Boolean, default=True, nullable=False)
    complaint_assigned = db.Column(db.Boolean, default=True, nullable=False)
    complaint_in_progress = db.Column(db.Boolean, default=True, nullable=False)
    complaint_resolved = db.Column(db.Boolean, default=True, nullable=False)
    complaint_escalated = db.Column(db.Boolean, default=True, nullable=False)
    # System
    schedule_reminder = db.Column(db.Boolean, default=True, nullable=False)
    green_points_earned = db.Column(db.Boolean, default=True, nullable=False)
    weekly_summary = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    user = db.relationship('User', backref=db.backref('notification_prefs', uselist=False, lazy=True))

    @classmethod
    def get_or_create(cls, user_id):
        prefs = cls.query.filter_by(user_id=user_id).first()
        if not prefs:
            prefs = cls(user_id=user_id)
            db.session.add(prefs)
            db.session.commit()
        return prefs

    def is_enabled(self, event_type):
        """Check if a specific event type is enabled for push notifications."""
        return getattr(self, event_type, True)


# ──────────────────────────────────────────────
# v2: PROACTIVE DISPATCH ASSIGNMENT
# Auto-queued by the telemetry ingest when a bin's ML overflow forecast
# crosses FORECAST_ALERT_HOURS (6h); workers see the ranked queue, accept a
# bin, and mark it completed once cleared. Admin control room watches the
# same rows live over socket.io.
# ──────────────────────────────────────────────
class DispatchAssignment(db.Model):
    __table_args__ = (
        # Hot paths: per-bin status lookups (queue render) + per-worker
        # active assignments (worker dashboard).
        db.Index('ix_dispatch_bin_status', 'bin_id', 'status'),
        db.Index('ix_dispatch_worker_status', 'worker_id', 'status'),
        # Race guard: at most ONE active (Assigned) assignment per bin, so two
        # trucks can never both claim the same bin. Partial unique index works
        # on both SQLite and Postgres (status is a constant here, not a param).
        db.Index('uq_dispatch_bin_assigned', 'bin_id', unique=True,
                 sqlite_where=db.text("status = 'Assigned'"),
                 postgresql_where=db.text("status = 'Assigned'")),
    )
    id = db.Column(db.Integer, primary_key=True)
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker_profile.id'), nullable=True)  # None while Pending
    eta_hours = db.Column(db.Float, nullable=True)      # forecast snapshot when queued
    status = db.Column(db.String(20), default='Pending', nullable=False)  # Pending / Assigned / Completed
    assigned_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    bin = db.relationship('SmartBin', backref=db.backref('dispatch_assignments', lazy=True))
    worker = db.relationship('WorkerProfile', backref=db.backref('dispatch_assignments', lazy=True))


# ──────────────────────────────────────────────
# v5: MAINTENANCE WORK ORDER (sensor-health follow-up)
# Created optionally when an admin clears a sensor fault: the bin leaves the
# faulted state but stays flagged maintenance_scheduled until a worker starts
# (Scheduled -> In Progress) and completes the order. Overdue highlighting is
# computed read-side from due_date; the row itself is immutable-by-audit.
# ──────────────────────────────────────────────
class MaintenanceWorkOrder(db.Model):
    __table_args__ = (
        # Hot paths: control-room sweep (status + due) and per-worker task list.
        db.Index('ix_maintenance_status_due', 'status', 'due_date'),
        db.Index('ix_maintenance_worker_status', 'worker_id', 'status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    bin_id = db.Column(db.Integer, db.ForeignKey('smart_bin.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker_profile.id'), nullable=True)  # None = unassigned pool
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)          # acting admin
    status = db.Column(db.String(20), default='Scheduled', nullable=False)  # Scheduled / In Progress / Completed
    due_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # v6: Overdue-escalation dedupe — set by the scheduled escalation job the
    # first time the order's due_date passes without completion. The job only
    # escalates orders where this is still NULL, so a long-overdue order
    # notifies exactly once instead of nagging on every sweep.
    escalated_at = db.Column(db.DateTime, nullable=True)

    bin = db.relationship('SmartBin', backref=db.backref('maintenance_orders', lazy=True))
    worker = db.relationship('WorkerProfile', backref=db.backref('maintenance_orders', lazy=True))
    creator = db.relationship('User', foreign_keys=[created_by],
                              backref=db.backref('created_maintenance_orders', lazy=True))
    completer = db.relationship('User', foreign_keys=[completed_by],
                                backref=db.backref('completed_maintenance_orders', lazy=True))


# ──────────────────────────────────────────────
# v2: OFFLINE DELIVERY (PWA queue replay health)
# Written when a submission tagged X-Offline-Replay lands, so the
# municipality can see offline-first usage: which complaints/photos
# arrived via the IndexedDB queue instead of a live form post.
# ──────────────────────────────────────────────
class OfflineDelivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(100), nullable=False)          # '/report' or '/report-illegal'
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaint.id'), nullable=True)
    illegal_report_id = db.Column(db.Integer, db.ForeignKey('illegal_dump_report.id'), nullable=True)
    ward = db.Column(db.String(100), nullable=True, index=True)
    has_photo = db.Column(db.Boolean, default=False, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)    # replay attempts before success
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    delivered_at = db.Column(db.DateTime, default=utcnow, index=True)


# ──────────────────────────────────────────────
# v7: ANONYMIZED CONSENT REGISTER (GDPR/DPDP evidence)
# One row per analytics-banner decision (Accept / Decline), written when the
# citizen clicks a banner button. Stored ANONYMIZED — no name, phone, address,
# IP or user-agent; only a salted SHA-256 fingerprint of (IP + UA) so the Gram
# Panchayat can demonstrate that consent was captured and count distinct
# choosers without being able to identify any individual. `version` records
# which consent-policy text was shown (a policy change is therefore auditable)
# and `source` records which page the banner was on.
# ──────────────────────────────────────────────
class ConsentRecord(db.Model):
    __table_args__ = (
        # Hot paths: per-choice counts + recent-choices listing on the
        # superadmin consent register.
        db.Index('ix_consent_choice_created', 'choice', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    choice = db.Column(db.String(10), nullable=False)       # 'accept' | 'decline'
    version = db.Column(db.String(20), nullable=False, default='v1')  # consent policy version shown
    source = db.Column(db.String(200), nullable=True)       # page path where the banner was shown
    fingerprint = db.Column(db.String(64), nullable=False)  # salted sha256(ip + user_agent) — never reversible to PII
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
