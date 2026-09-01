---
name: testing-smartgarbage
description: How to run and browser-test the SmartgarbageCSP Flask app locally (venv, DB, built-in logins, MFA, maps/CSP gotchas).
---

# Testing the SmartgarbageCSP Flask app

## Run it

- Use the existing Python 3.12 venv: `/home/ubuntu/repos/SmartgarbageCSP/venv` (system python3.10 is too
  old for `requirements.txt`; recreate with `~/.pyenv/versions/3.12.8` if needed).
- DB: `FLASK_APP=manage.py ./venv/bin/flask db upgrade` then `./venv/bin/python seed_db.py`
  (idempotent, SQLite at `instance/garbage.db`).
- Start: `setsid nohup ./venv/bin/python run.py > /tmp/app.log 2>&1 < /dev/null &` → http://localhost:5000.
  Port 5000 may already be occupied by a previous run; kill it first. Note: a bare
  `pkill -f run.py` in the same command can match and kill the shell running it — pkill in a
  separate call, or use `pkill -f "python run.py"`, and re-check with `curl` that the server
  actually came up (it silently fails to bind if the old process is still holding the port).

### If the whole server hangs, suspect the eventlet hub (fixed in `93568fc`, but easy to reintroduce)

`dashboard.html` opens `new EventSource('/api/notifications/stream')` on page load, and that endpoint
(`app/routes.py`) is an **infinite generator that sleeps between pushes**, while `app/__init__.py`
inits SocketIO with `async_mode='eventlet'`. If anything in that request path ever does a *blocking*
sleep/IO on an unpatched hub, **one visit to `/dashboard` freezes the entire server for every user,
permanently**, until the process is restarted — curl included.

Two things keep this working; if either is undone the freeze comes straight back:
- `run.py` calls `eventlet.monkey_patch()` **before** importing the app (it's inside a
  `try/except ImportError`, so it can silently become a no-op — verify, don't assume).
- the SSE loop uses `socketio.sleep(...)`, not `time.sleep(...)`.

Verify patching really took effect under the venv:

```bash
./venv/bin/python -c "import eventlet; eventlet.monkey_patch(); import time, socket; print(time.sleep.__module__, socket.socket.__module__)"
# want: eventlet.greenthread eventlet.greenio.base
```

Symptoms of a regression: a dashboard card stuck on "Loading…" while the rest of the page renders;
`curl` to any URL timing out (~10 s); navigation hanging right after visiting the dashboard; the
Chrome tab hanging or crashing.

**How to test this properly.** "Other requests are fast" proves nothing if the EventSource never
connected — prove the stream is live first: DevTools → Network → filter `stream` → the request must
show Type `eventsource` / Status `pending`, and still be pending after ~15 s (i.e. it has gone round
the sleep loop a few times). Only then time other requests. Healthy is ~1–10 ms:

```bash
for i in 1 2 3; do curl -s --max-time 10 -o /dev/null -w "%{http_code} %{time_total}s\n" http://localhost:5000/login; done
ss -tn state established '( sport = :5000 )' | tail -n +2 | wc -l   # open conns incl. SSE
```

If you ever need to work around a reintroduced freeze without touching the repo, run a throwaway
launcher that monkey-patches first and serve on another port (sessions are shared across ports on
`localhost`, so you may land already logged in):

```python
import eventlet; eventlet.monkey_patch()
import sys; sys.path.insert(0, '/home/ubuntu/repos/SmartgarbageCSP')
from app import create_app, socketio
app = create_app()
socketio.run(app, host='0.0.0.0', port=5001, debug=False)
```

Kill any such wrapper before testing a fix, or you'll unknowingly test the patched server instead of
the stock one.

## Logging in

- Built-in accounts are auto-provisioned at app start (`app/defaults.py`), username == password:
  `24331A4441ADMIN` (admin), `24331A4441WORKER` (worker), `24331A4441CITIZEN` (citizen).
- Admin and worker go through `/mfa-verify`. The 6-digit OTP is flashed on the page itself as a green
  alert ("MFA OTP Code (Simulated SMS): NNNNNN") — read it off the screen and type it. It is also in
  `/tmp/app.log`. `000000` is a safe wrong-OTP adversarial value.
- Logout via the `👤 <username>` navbar dropdown → Logout, or navigate to `/logout` directly (faster
  when switching roles).

## Where the interesting UI lives

- `/` weather widget (`#weatherCity/#weatherTemp/#weatherHumidity/#weatherWind`) + ward picker
  `#homeWardSelector`. Wards come from `app/static/chintalavalasa_locations.js`
  (`initializeWardDropdown(selectId, placeholder)`); there are exactly 5 wards.
- Maps: `#gisMap` and `#fleetMap` (`/admin`), `#workerNavMap` (`/worker`), `#locatorMap` (`/dashboard`),
  heatmap on `/analytics`. Leaflet/OSM tiles come from unpkg + tile.openstreetmap.org, so the box needs
  outbound network; a grey/white box means the page JS failed, not that Leaflet is missing.
- `/admin` sections are anchored by id (`#kpi-section`, `#gis-section`, `#fleet-section`,
  `#maintenance-section`, `#worker-section`, `#illegal-section`, `#bot-simulator-section`,
  `#bwg-section`, `#tickets-section`, `#webhooks-section`) — check sidebar links against these ids.
- Language toggle is `/set-lang/<en|te>?next=<path>`; the navbar button label flips between `తెలుగు` and `EN`.

## Gotchas that have bitten before

- CSP is set in `app/__init__.py`. `script-src` includes `'unsafe-inline'` (the templates rely on inline
  scripts and `onclick` handlers) but **not** `'unsafe-eval'` — so `new Function(...)`/`eval` in a
  devtools check will be blocked; don't use them to syntax-check page scripts.
- If a page's maps/dropdowns are dead but the console shows **no** error, suspect a parse-time
  SyntaxError in that template's inline `<script>`: verify with `typeof <someTopLevelFn>` in the console
  (hoisted functions missing ⇒ the block never parsed), then extract the block from the template and
  run `node --check`, or brace-depth scan it. This exact bug existed in
  `app/templates/dashboard.html` (unclosed `showToast` wrapper) and killed the locator map, both ward
  selects and the PAYT/Eco-Champions loaders.
- Frontend/backend JSON field mismatches show up as `undefined` in the UI (e.g. admin dispatch banner
  read `total_distance_km` while `/api/route/optimize` returns `total_distance`). Always read the numeric
  values in banners/alerts, not just that the banner appeared.
- The browser console tool loses logs after each read and may miss page-load-time errors; reload and read
  immediately, or assert on DOM state instead.
- CDP (`browser_console` / JS evaluation) is flaky here and Chrome can crash outright — often because a
  hung request (see the SSE freeze above) leaves the page loading, which also makes DevTools show
  "JavaScript context: Not selected". Fallbacks: open DevTools with F12 and type expressions into the
  Console panel by hand (this is good recording evidence anyway), and if Chrome dies relaunch it with
  `/opt/.devin/chrome/chrome/linux-137.0.7118.2/chrome-linux64/chrome --remote-debugging-port=29229
  --remote-allow-origins=* --user-data-dir=/home/ubuntu/.config/google-chrome-for-testing` — the
  `google-chrome` wrapper only POSTs to port 29229 and fails if nothing is listening. A relaunch with a
  fresh profile logs you out.
- Prefer proving a function ran via its UI side effects over a console expression: e.g. the report form's
  lat/long inputs have no HTML default, so seeing `18.067500 / 83.409400` proves `captureGPS()` executed
  its GPS-denied fallback.
- Chrome autofill concatenates into the username field when you retype; clear with click + `ctrl+a` +
  `Delete` (a triple-click alone is unreliable) and press `Escape` to dismiss the suggestion dropdown
  before submitting.
- `connect-src` in `app/__init__.py` must list the CDN origins the **service worker precaches**
  (fonts.googleapis.com, fonts.gstatic.com, cdn.jsdelivr.net, cdnjs.cloudflare.com, unpkg.com), not just
  the tile/weather APIs — otherwise `sw.js` floods the console with `Refused to connect to …` plus a
  `Failed to fetch`. Fixed in `93568fc`; such errors are precache noise, not `script-src` failures.
- When asserting "no console errors", switch the console's level filter to **All levels** — Chrome hides
  messages by default (it shows an "N hidden" hint) and you can otherwise miss violations. A
  `favicon.ico` 404 and perf `[Violation]` warnings (forced reflow, geolocation) are expected noise here.
- A `400 Bad Request — The CSRF tokens do not match` on login usually means the form was rendered before
  a logout; reload `/login` and retype. Click precisely into the input before `ctrl+a` — if focus is on
  the page instead, `ctrl+a` selects the whole document and the typing goes nowhere.
- Scrolling with the cursor over a Leaflet map zooms the map instead of the page; scroll with the pointer
  over a side column.
- Deny the GPS prompt when it appears — pages are expected to fall back to Chintalavalasa coordinates.

## Devin Secrets Needed

None — all credentials are local built-in test accounts.
