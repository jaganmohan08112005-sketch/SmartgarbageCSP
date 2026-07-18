# SmartGarbage — System Architecture

## 📐 System Diagram

```mermaid
graph TD
    A[Citizen Portal] -->|HTTP| B[Flask App]
    C[Admin Console] -->|HTTP| B
    D[Worker Dashboard] -->|HTTP| B
    E[WhatsApp Bot] -->|Webhook| B
    F[Telegram Bot] -->|Webhook| B
    G[IoT Sensors] -->|Telemetry| B
    
    B --> H[(Database)]
    B --> I[ML Model]
    B --> J[External APIs]
    
    J --> K[Open-Meteo Weather]
    J --> L[Twilio WhatsApp]
    J --> M[Telegram API]
```

## 🗄️ Data Model (ER Diagram)

```mermaid
erDiagram
    User ||--o{ Complaint : submits
    User ||--o{ WasteDeclaration : declares
    User ||--o{ BWGDeclaration : generates
    User ||--o{ PAYTInvoice : receives
    User ||--o| WorkerProfile : has
    User ||--o{ AuditLog : generates
    
    SmartBin ||--o{ SensorHealth : monitors
    SmartBin ||--o{ IncidentLog : triggers
    SmartBin ||--o{ OffloadLog : logs
    
    Complaint ||--o{ IllegalDumpReport : relates
    FirmwareRelease ||--o{ SmartBin : applies
    
    User {
        int id
        string username
        string password_hash
        string role
        string phone
        bool is_superadmin
        int green_points
    }
    
    Complaint {
        int id
        int user_id
        string name
        string phone
        string ward
        string description
        string photo
        float latitude
        float longitude
        string status
    }
    
    SmartBin {
        int id
        string hardware_id
        float latitude
        float longitude
        int level
        string status
        float temperature
        float methane
        bool sensor_fault
    }
```

## 🔄 Request Flow Walkthroughs

### Complaint Submission Flow

1. Citizen opens dashboard (`/dashboard`)
2. Fills Emergency Cleanup form with GPS, photo, description
3. POST to `/report` with CSRF token
4. Server validates, stores complaint, awards Green Points
5. Redirects to success page

### WhatsApp Illegal-Dump Reporting

1. Citizen sends photo via WhatsApp to Twilio number
2. Twilio webhook POSTs to `/webhook/whatsapp`
3. Server downloads media, extracts GPS, creates `IllegalDumpReport`
4. Replies with TwiML acknowledgment

### IoT Telemetry Processing

1. Smart bin sends telemetry to IoT endpoint
2. Server evaluates emergency metrics (temp > 65°C or methane > 500ppm)
3. Creates `IncidentLog` if threshold exceeded
4. Triggers webhook notifications to registered endpoints

### Admin MFA Login

1. Admin submits credentials at `/login`
2. Server verifies password, generates OTP, stores with 5-min expiry
3. Redirects to `/mfa-verify` with OTP display (simulated SMS)
4. Admin enters OTP, server validates, grants access

## 🔒 Security Architecture

| Measure | Implementation | Why |
|---------|---------------|-----|
| **Admin registration blocked** | Role validation in `register()` | Prevents privilege escalation |
| **MFA for privileged roles** | OTP required for admin/worker | Multi-factor authentication |
| **SECRET_KEY env var** | Read from environment with fallback | Avoids hardcoded secrets |
| **File upload uniqueness** | Random prefix on filenames | Prevents collision attacks |
| **Phone validation** | `validate_indian_phone()` helper | Rejects fake/sequential numbers |
| **Rate limiting** | Flask-Limiter on auth routes | Prevents brute-force attacks |
| **Debug mode gated** | FLASK_ENV check in run.py | Prevents info disclosure |

## 📊 API Reference

### Citizen Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/dashboard` | Login | Citizen dashboard |
| POST | `/report` | Login | Submit complaint |
| POST | `/dashboard/declare-waste` | Login | Declare segregation |
| GET | `/api/payt-invoice` | Login | Get PAYT invoices |

### Admin Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/admin` | Admin | Admin console |
| GET | `/admin/audit` | Admin | Audit trail |
| POST | `/admin/firmware/upload` | Admin | Upload firmware |
| GET | `/api/route-optimize` | Admin | Optimize routes |

### Public/Webhook Endpoints

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/webhook/whatsapp` | None | WhatsApp reporting |
| POST | `/webhook/telegram` | None | Telegram reporting |
| GET | `/report-illegal` | None | Anonymous reporting |

## 🎯 Known Gaps

1. **Single-worker rate limiting** — global limits, not per-user (Flask-Limiter uses in-memory store; move to Redis when running >1 worker)
2. **State portal compliance export** — extend the existing CSRD export to a state-portal format
3. **Citizen segregation streak/score** — data exists in `WasteDeclaration`, no citizen-facing view yet
4. **Trend analytics** — segregation rate over time per ward, not just point-in-time
5. **True route optimization** — beyond miss-risk prediction (traveling-salesman ordering)

## ✅ Recently Closed

- ✅ **Segregation penalty wired into billing** — `bwg_ledger` computes compliance % + penalty multiplier (1.0×→2.0×) into `PAYTInvoice`.
- ✅ **Worker safety tracking** — `WorkerProfile` now has `ppe_compliance`, `training_completed`, `insurance_enrolled`, `insurance_policy_no`, `last_training_date`, `last_medical_checkup`.
- ✅ **Superadmin panel** — `/admin/super` (create admin, toggle super flag) gated by `superadmin_required`; `/admin/audit` now genuinely restricted to superadmins only.
- ✅ **Ward Committee / Gram Sabha transparency view** — public read-only `/transparency` + `/ward/<name>` dashboard (fill %, open/resolved complaints, 30-day segregation rate).
- ✅ **Informal waste-picker registration** — `/register/picker` creates a `worker` with `is_informal_picker=True`, separate from fleet drivers.
- ✅ **Automated tests + CI** — `tests/` (14 pytest cases) + `.github/workflows/ci.yml` (pytest + flake8 on every push/PR).

## 🚀 Future Roadmap

- [ ] Redis-backed per-user rate limiting
- [ ] State portal compliance export
- [ ] Citizen segregation streak/score + ward leaderboard
- [ ] Trend analytics dashboard
- [ ] Mobile app (PWA enhancement)
- [ ] Real-time push notifications for complaint status changes