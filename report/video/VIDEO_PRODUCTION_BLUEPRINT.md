# SmartGarbage — Video Production Blueprint
**Deliverable:** ~3-minute demo video · synchronized voiceover + storyboard matrix
**Audience:** Gram Panchayat officials, faculty evaluators, community members
**Golden rule (civic-technical balance):** every technical scene must answer
*"how does this keep Chintalavalasa's streets clean?"*

---

## Scene Matrix (voiceover ⟷ visuals)

| # | Time | Scene objective | Visual — what the editor shows | Asset | Voiceover (read verbatim, `[PAUSE]` = beat of silence) |
|---|------|-----------------|-------------------------------|-------|--------------------------------------------------------|
| 1 | 0:00–0:25 | **The Community Problem** — make the audience feel the civic pain before any tech | Handheld shots of an overflowing ward bin, a paper collection register, a resident stepping around waste; hard-cut to the clean "after" concept frame | `[Hardware B-Roll]` | "In Chintalavalasa, five wards, twelve thousand people — one paper register decides when your street gets cleaned. [PAUSE] Bins overflow before anyone reports them. Complaints vanish into a notebook. [PAUSE] SmartGarbage replaces that notebook with a system the whole panchayat can see." |
| 2 | 0:25–0:55 | **IoT System Overview** — one diagram: bin → HMAC-signed device → telemetry API → PostgreSQL → dashboard | Animated build-up of the report's Figure 4.3, box by box, arrow by arrow; end on the live admin bin map | `[UI Software Demo]` + diagram overlay | "Each smart bin reports its fill level over the network. Every message is **signed with HMAC-SHA256** — the server only accepts telemetry from genuine devices. [PAUSE] Data lands in PostgreSQL and streams straight to the ward dashboard — so the panchayat sees which bins are nearly full **before** residents smell a problem." |
| 3 | 0:55–1:45 | **Dashboard Features & Demo** — live fill levels, threshold alerts, ML-ranked dispatch queue | Screen capture: admin control room → bin tiles crossing 80% turning red → alert badge → ranked dispatch queue; then the citizen complaint flow with GPS + photo, token issued | `[UI Software Demo]` | "Here is the live control room. When a bin crosses the **80 percent threshold**, its tile turns red and an alert is raised — no phone calls needed. [PAUSE] The dispatch queue is ranked by a machine-learning model, so the truck clears the fullest bins first — fewer overflow complaints, less fuel wasted. [PAUSE] Citizens help too: they report overflow with **GPS and photo evidence**, and get a tracking token instantly." |
| 4 | 1:45–2:45 | **Step-by-Step Deployment** — from `git push` to live site with data handshakes | Split screen: terminal left, Render dashboard right. Show `git push` → Render auto-deploy build log → migrations applied → `curl https://<app>.onrender.com/health` returning JSON with `queue.workers` → GitHub Actions uptime probe green | `[Terminal Log Capture]` + `[UI Software Demo]` | "Deployment is one command. Push to GitHub — and Render rebuilds the Docker image **automatically**. [PAUSE] Alembic migrations apply the database schema. [PAUSE] The health endpoint proves the handshake end to end: it reports not just that the site is up, but that background workers are actually running. [PAUSE] A GitHub Action pings it every fifteen minutes, and Cloudflare serves the world over HTTPS. Zero-cost, free-tier infrastructure — a system any panchayat can replicate." |
| 5 | 2:45–3:05 | **Civic Call to Action** — impact, honesty, and the open invitation | Report's Figure 7.1 (before/after bars) → team photo/slide → repo URL card | `[UI Software Demo]` (figure) | "Projected result: complaint resolution from seventy-two hours to eighteen. [PAUSE] This is a prototype — IoT is simulated and impact values are estimates — and we say so openly. [PAUSE] The code is open source. Any panchayat can adopt it: update the ward coordinates, deploy, and cleaner streets are one push away." |

---

## Critical code snippets (show these on screen — nothing denser)

**1. Telemetry handshake (the "genuine device" proof) — `app/routes/iot.py`**
```python
@app.route('/api/bin-telemetry', methods=['POST'])
@csrf.exempt                     # HMAC-signed device POSTs instead
def bin_telemetry():
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, expected):
        return jsonify({"message": "Invalid signature"}), 401
```

**2. Device onboarding — `POST /api/devices/register`** — registers a bin's
hardware ID against the server secret (`IOT_TELEMETRY_SECRET`); unset secret
returns **503**, so unsigned deployments fail loudly.

**3. Deployment trigger — `render.yaml` (verbatim, it *is* the config)**
```yaml
services:
  - type: web
    name: smartgarbage
    runtime: docker
    branch: main              # every push auto-deploys
    healthCheckPath: /health
```

**4. The data handshake proof (terminal)**
```bash
curl -s https://<your-app>.onrender.com/health
# → {"status": "ok", "queue": {"workers": 1, ...}, ...}
```

---

## Asset guidelines (strict — label every clip)

| Tag | Meaning | Rules for this video |
|-----|---------|----------------------|
| `[Hardware B-Roll]` | Real-world civic footage | Phone shots of actual ward bins/registers; 3–5 s each; no faces without consent |
| `[UI Software Demo]` | Live screen capture | 100% browser zoom, clean profile, cursor deliberate; bin-tile threshold moment is the hero shot — light it well |
| `[Terminal Log Capture]` | Command-line truth | Monospace ≥ 16 pt, dark theme; keep the deploy build log and `curl /health` on screen ≥ 4 s each so viewers can read the JSON |

**Honesty rule (project-specific):** the prototype has **no physical ESP32/ultrasonic
hardware** — bin telemetry is simulated via `scripts/seed_demo_data.py`. Narrate it
exactly as Scene 2 does ("reports its fill level"), never claim sensors are deployed;
Scene 5 states the simulation openly. Figures 4.3 / 7.1 come from the report's
`_diagrams/report/` PNGs — reuse them so video and report match.

## Pacing notes
- 5 scenes, ~19 s average; cut on action, never mid-sentence.
- `[PAUSE]` ≈ 0.5 s of silence — honor them; they separate civic problem from technical answer.
- Background music: none under voiceover sections; soft track allowed only under Scene 5.
- Captions in English burned in; optional Telugu subtitle track for community screening.
