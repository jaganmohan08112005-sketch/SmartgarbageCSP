# Privacy Compliance Audit — SmartGarbage Chintalavalasa

Audit date: 2026-08-07
Framework: Digital Personal Data Protection (DPDP) Act, 2023 (India) + good-practice
benchmarks for public-service portals. The portal is operated by the Chintalavalasa
Gram Panchayat / Directorate of Waste Management & Sanitation (the Data Fiduciary).

Legend: ✅ done · 🟡 partial · ❌ missing

## 1. Notice at collection (DPDP s.5)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1.1 | Plain-language notice before/at collection | ✅ | Full `/privacy` notice + homepage "privacy at a glance" card + consent banner link |
| 1.2 | States items collected + specific purpose | ✅ | Section 1 (What We Collect) + Section 2 (Why) |
| 1.3 | Explains how to exercise access/correction/erasure | ✅ | Section 5 (Your Rights) |
| 1.4 | Explains how to file a complaint with the DPB India | ✅ | Added to Section 5 (this audit) |
| 1.5 | Available in a scheduled language (Telugu) | ✅ | Full TE translations on the privacy page |

## 2. Consent (DPDP s.6)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 2.1 | Consent free / specific / informed / unconditional / unambiguous | ✅ | Only for analytics; banner + plain-language text |
| 2.2 | No pre-checked boxes | ✅ | Explicit Accept/Decline buttons |
| 2.3 | Withdrawal as easy as grant | 🟡 | Clearing site data + contact; a one-click "withdraw" control on the portal is a future enhancement |
| 2.4 | Consent evidence captured (auditable) | ✅ | `consent_record` table + superadmin register (anonymized fingerprints) |

## 3. Children (DPDP s.9)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 3.1 | Correct age definition (under 18) | ✅ | Fixed from "under 13" (this audit) |
| 3.2 | Verifiable parental consent before processing a child's data | 🟡 | Policy commitment added; age-gate/verification flow not implemented (portal registration is phone-based) |
| 3.3 | No tracking / behavioral monitoring / targeted advertising of children | ✅ | Policy commitment added; no advertising anywhere |

## 4. Security safeguards (DPDP s.8(5) — non-derogable, even for government exemptions)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4.1 | Reasonable security safeguards documented | ✅ | New Section 12 lists actual controls |
| 4.2 | Passwords hashed | ✅ | Werkzeug PBKDF2/argon hashes |
| 4.3 | Transport encryption | ✅ | TLS on Render; HSTS + CSP headers (Talisman) |
| 4.4 | Photo metadata (EXIF/GPS) stripped | ✅ | `scrubbed_photo` pipeline |
| 4.5 | Rate limiting + login monitoring | ✅ | flask-limiter (Redis-backed in prod), lockout |
| 4.6 | Audit trail of admin actions | ✅ | `audit_log` + superadmin ledger |
| 4.7 | Retention sweeps | ✅ | Telemetry 90 d, tracking links 90 d, audit logs 2 y |

## 5. Breach notification (DPDP s.8(6))

| # | Item | Status | Notes |
|---|------|--------|-------|
| 5.1 | Process documented | ✅ | New Section 13 (contain → assess → notify DPB + affected principals → record → review) |
| 5.2 | Duty to notify DPB India | 🟡 | Committed in policy; execution runbook + templates to be prepared by the Panchayat |
| 5.3 | Duty to notify affected data principals | 🟡 | Committed in policy; contact list source = registered users' phone/email |
| 5.4 | Breach register / record-keeping | 🟡 | Audit-log record committed; dedicated breach log recommended |

## 6. Rights of data principals (DPDP s.11–14)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 6.1 | Access | ✅ | Section 5 + dashboard self-service |
| 6.2 | Correction | ✅ | Section 5 |
| 6.3 | Erasure | ✅ | Section 5 (anonymized illegal-dump reports excluded by design) |
| 6.4 | Grievance redressal | ✅ | Hotline + new Grievance/DPO contact (15-day commitment) |
| 6.5 | Nominate a representative | ✅ | Added to Section 5 (this audit) |
| 6.6 | Right to know processors data is shared with | ✅ | New Section 11 register |

## 7. Data processors

| # | Item | Status | Notes |
|---|------|--------|-------|
| 7.1 | Processor register published | ✅ | Section 11 covers the actual stack: Supabase (DB + photo storage), Upstash Redis, Razorpay, Render + Cloudflare, Cloudinary, Brevo (email), Twilio, Telegram, Open-Meteo, OpenStreetMap, asset CDNs, consent-gated Google Analytics, Sentry |
| 7.2 | Processor contracts in place (s.8(2)) | 🟡 | Commitment stated; signed DPAs to be executed by the Panchayat |

## 8. Data quality & retention (s.8(3), s.8(7))

| # | Item | Status | Notes |
|---|------|--------|-------|
| 8.1 | Data accuracy maintained for decisions | 🟡 | Phone/OTP validation; billing verification (PAYT) |
| 8.2 | Erasure on consent withdrawal / purpose end | 🟡 | Policy stated; automated erasure jobs not yet implemented |
| 8.3 | Retention periods published | ✅ | Section 4 table (all figures verified against code) |

## 9. Grievance & DPO contact (s.8(9), s.8(10))

| # | Item | Status | Notes |
|---|------|--------|-------|
| 9.1 | Designated contact person published | ✅ | New "Grievance & Data Protection Officer" block in Section 10 |
| 9.2 | Response-timeframe commitment | ✅ | 15 days (draft DPDP rules benchmark) |
| 9.3 | Real DPO email/name configured | ❌ | Placeholder `dpo@smartgarbage.example` — the Panchayat must assign a real officer |

## Action required by the Gram Panchayat (non-code)

1. Appoint a named Grievance & Data Protection Officer; replace the placeholder email.
2. Execute data-processor agreements with Razorpay, Render, Cloudflare, Twilio, and the email host.
3. Prepare the breach-notification runbook + DPB/affected-principal notice templates.
4. Decide the retained "legal basis" position for the §17 exemption analysis (this audit does not give legal advice).
5. Re-run this checklist after the DPDP Rules are finalised (2025 draft rules refine timelines/forms).
