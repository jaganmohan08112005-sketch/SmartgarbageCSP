# SmartGarbage — Full-Site Audit (3 Oct 2026)

Scope: structure/files, content & duplicates, security, accessibility, code quality.
Branch: `feat/uptime-monitoring`.

## Fixed in this pass

### 1. CI-gating lint failure (would fail the `lint` job on push)
- `app/jobs.py:1687` — `E303 too many blank lines (3)` before
  `PHOTO_GATE_BREACH_EVENT`. CI's gating selector
  (`E9,F63,F7,F82,E301-E306`) failed on this. Now clean (exit 0).

### 2. Dead code / unused imports (17 → 0 real F-errors in `app/`)
- `app/push.py` — removed unused `WebPushException` import, unused
  `url_for` import, dead `track_url` variable and the pointless
  `try/except` around it (`F401`, `F841`, `F541`).
- `app/routes/citizen.py` — dropped unused `hashlib`/`base64`/`json as _json`,
  `time as _time`, and the unused `_publish_user_event` /
  `find_duplicate_complaint` re-imports.
- `app/routes/public.py` — dropped unused `send_from_directory`, an unused
  local `func` import, and unused `WorkerProfile`/`PAYTInvoice`/`SmartBin`
  model imports.
- `app/routes/admin.py` — dropped unused local `func` import in `push_analytics`.
- `app/routes/webhook.py` — dropped unused `json as _json`.
- `app/jobs.py` — dropped unused `current_app` / `utcnow` imports.
- `app/routes/__init__.py` — `F402`: loop variable `admin` shadowed the
  `admin` module import; renamed to `admin_user`.

### 3. Accessibility — form labels (WCAG 1.3.1 / 4.1.2 / 3.3.2)
Every form control is now programmatically labelled. 30 controls across
11 templates had a visible `<label>` that was a **sibling with no `for=`**
(so screen readers announced no name), or no label at all. Fixed with
`for`/`id` pairs (or `aria-label` where the layout had no visible label):

| Template | Controls fixed |
|---|---|
| `mfa_verify.html` | OTP |
| `resend_verification.html` | email |
| `reset_password.html` | new password |
| `reset_password_request.html` | username |
| `super_admin.html` | username, password, phone (aria-label) |
| `firmware.html` | version, release notes, target bins, binary, OTA bin select |
| `bwg_ledger.html` | entity name, type, composting/recyclable/landfill kg |
| `dashboard.html` | ward ×2, address, description, photo, 4 waste-stream kg |
| `illegal_dump.html` | ward, latitude, longitude, description, photo |
| `worker.html` | bin, issue type, description, dump yard, weight; converted a
  misused `<label>` on a non-form "Device Coordinates" block to `<div>` |
| `admin.html` | webhook URL + 10 WhatsApp/Telegram simulator fields |

Verification: a scan finds **0** unlabelled non-hidden controls; all 47
templates parse; all 11 previously affected pages render 200.

## Verified clean (no action needed)

- **Secrets**: `.env` untracked and git-ignored; no hardcoded credentials in
  tracked code (only `${{ secrets.* }}` references and CI's throwaway
  `POSTGRES_PASSWORD: postgres`).
- **Security headers** (live from the test client): CSP (scoped to real CDNs +
  `report-uri`), HSTS w/ preload, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, COOP/CORP, `Permissions-Policy`,
  `X-Permitted-Cross-Domain-Policies: none`.
- **Dangerous patterns**: no `eval`/`exec`/`shell=True`/string-built SQL;
  `subprocess.run` (alerting) uses an argv list; `pickle.load` only on the
  app's own committed model files.
- **`<img>` alt**: 0 images missing `alt`.
- **Landmarks**: `<html lang>`, skip-to-content link + CSS, `#main-content`.
- **Structure**: `.venv*`, `node_modules`, logs, datasets untracked; no
  accidental build artifacts committed. Section-banner guard passes.

## Findings left for the owner (not auto-changed)

1. **Cloudflare docs overlap** — 4 files cover the same topic:
   `docs/CLOUDFLARE_CDN_SETUP.md` (103 ln), `wiki/CLOUDFLARE_CDN_SETUP.md`
   (713 ln, near-superset), and `docs/guides/cloudflare/*` (3 files). Also
   `docs/CLOUDFLARE_CDN_SETUP.md` still references the retired
   `smartgarbage.onrender.com`/Fly.io path. Recommend consolidating to one
   canonical guide and deleting/redirecting the rest. **Not deleted** —
   content choice for the owner.
2. **`SECURITY.md` placeholder** — `[INSERT SECURITY EMAIL]` appears twice.
   Needs a real contact address.
3. **Legacy/tracked QA cruft** — `_qa/` (58 files, screenshots), `_imgqa/` (6),
   `_archive/` (22), `keepalive/`, `social-media/`, `wiki/`. Tracked and
   unreferenced by code; candidates for archival or removal. Left as-is to
   avoid deleting the owner's materials.
4. **Style-only lint debt** — ~1,775 non-gating flake8 findings, overwhelmingly
   `E501` long lines (CI runs the strict selector plus `--exit-zero` on the
   rest, so it's green). Optional cleanup.
5. **CSP `'unsafe-inline'`** in `script-src`/`style-src` is required by the
   inline GA4 snippet and Bootstrap; tightening needs nonce/hash work.

## How to re-verify

```bash
# gating lint (must be exit 0)
venv/Scripts/python.exe -m flake8 app/ --count \
  --select=E9,F63,F7,F82,E301,E302,E303,E304,E305,E306 --show-source
# real bugs
venv/Scripts/python.exe -m flake8 app/ --select=F401,F402,F541,F811,F821,F823
# front-end unit tests
npm run test:js
# full suite (needs Postgres)
TEST_DATABASE_URL=... venv/Scripts/python.exe -m pytest tests/ -n 0
```
