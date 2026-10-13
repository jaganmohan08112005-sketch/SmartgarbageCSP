#!/usr/bin/env python3
"""Documentation_DEMO_VIDEO v4 - LIVE WEBSITE WALKTHROUGH (explains every feature).

Playwright drives a real browser over the local reproduction stack set in BASE
and INTERACTS with it (ward selection, form fills, logins, mobile PWA). Every
scene carries an on-screen caption band that names the feature being explained.
Narration via SAPI TTS per scene. Output: 1280x720 H.264 + AAC.

v6 changes:
- coverage is closed: every page the route table serves as a *page* is filmed -
  the anonymous illegal-dumping channel, the grievance redressal officer, the
  privacy / terms / accessibility statements, and a real filing that walks
  report -> success panel -> signed tracking page -> dashboard entry
- the recording context is given a live device position (geolocations are
  granted and pinned to Ward 2), because /report refuses a filing without a
  GPS fix and would otherwise block the submit on camera
- a "click" tour step, so a scene can follow a link the page renders (the
  success panel's tracking link opens in a new tab; the take follows it in place)
- the account-recovery forms close the last two pages the route table serves
  (/reset-password-request and /resend-verification), leaving only the two
  token-in-email links unfilmed
- segments encode at CRF 25 / 96k mono rather than 21/128k: the 31-scene cut is
  ~82 MB, under GitHub's 100 MB per-file push limit. At the old settings the
  same cut is ~117 MB and a push is rejected outright (measured per scene in
  _probe_encode_size.py)

v5 changes:
- the cut is nothing but the website: the branded title/outro cards are gone, so
  it opens on the homepage and closes on the last real page
- citizen, worker and admin are entered by typing the seeded demo credentials
  into the real login form on camera, MFA code included
- drawtext caption band per scene (feature name + one-line explanation)
- real interactions: schedule ward picker, report form typing, mobile PWA
- all segments re-encoded uniformly (concat-safe), mono AAC everywhere
"""
import glob
import os
import re
import subprocess
import time
import wave

from playwright.sync_api import sync_playwright
import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()
HERE = os.path.dirname(os.path.abspath(__file__))
# Record the LOCAL stack (scripts/run_local_stack.py, 127.0.0.1:5057): it has
# the new brand illustrations and seeded demo data. Switch to the live URL
# only after the site is redeployed with the same assets.
BASE = "http://127.0.0.1:5057"
VD = os.path.join(HERE, "_video_live")
os.makedirs(VD, exist_ok=True)
# R24 deliverable: render straight into the submission package so the
# finished video exists in exactly one place.
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "submission", "video", "SmartGarbage_Demo_Video.mp4")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
FONT = "C\\:/Windows/Fonts/arialbd.ttf"

WHITE_YAVG = 252.0   # >= this luma == blank white frame
PAGES = ["/", "/schedule", "/report", "/transparency", "/impact", "/contact",
         "/about", "/faq", "/track", "/login", "/admin", "/worker", "/dashboard"]

# ── scene plan: (name, narration, action) ────────────────────────
SCENES = [
    ("01_home",
     "Welcome to SmartGarbage Chintalavalasa - the community waste management "
     "portal for the five wards of Chintalavalasa Gram Panchayat. Let me walk "
     "you through the live website, feature by feature.",
     "home"),
    ("02_home_scroll",
     "This is the public homepage. Notice the helpline number 1800 119 9111 "
     "and the collection schedule quick search right at the top. As we scroll, "
     "you can see ward-wise collection days, the transparency statistics, and "
     "the community impact numbers - all live from the database.",
     "scroll_home"),
    ("03_schedule",
     "Every citizen can check their ward's collection schedule here. Pick a "
     "ward - watch as I select Ward 2, Junction - and the portal shows the "
     "pickup days, plus a machine learning overflow-risk prediction for the "
     "coming days. No phone calls, no guesswork.",
     "schedule"),
    ("04_report",
     "Reporting a missed pickup takes under a minute. The form captures your "
     "ward, the location with automatic GPS, and a photo as proof. Every "
     "submission gets a tracking token, and duplicates within 100 metres or "
     "30 minutes are rejected automatically.",
     "report"),
    ("05_whatsapp",
     "Below every page sits the rescue strip: the WhatsApp fallback card that "
     "opens a saved chat, and the free toll-free grievance helpline "
     "1800 119 9111. Citizens without internet are covered by the "
     "offline-first PWA.",
     "footer_cta"),
    ("06_transparency",
     "The ward transparency dashboard is the accountability view: complaint "
     "counts by status, resolution times, and the waste-collection statistics "
     "for every ward - published openly for residents.",
     "transparency"),
    ("07_impact",
     "The impact page summarises the community's environmental and social "
     "gains so far, and the contact page lists every way to reach the "
     "panchayat team - WhatsApp, the toll-free helpline, email, and a "
     "dedicated grievance form for formal complaints.",
     "impact"),
    ("08_about_faq",
     "The About page explains the initiative and the five wards it serves. "
     "The FAQ page answers the common questions - what can be recycled, how "
     "Green Points work, and how PAYT billing is calculated.",
     "about_faq"),
    ("09_track_auth",
     "Every complaint also gets a signed tracking link, so its status can "
     "never vanish. Staff sign-in is where security shows: a password plus a "
     "second factor - a six-digit one-time code that can arrive by email with "
     "one click, no SMS gateway required. Watch the worker sign in now; the "
     "one-time code screen is the gate to the worker and admin portals.",
     "track_auth"),
    ("12_citizen",
     "Logged in as a citizen, the dashboard shows Green Points earned for "
     "segregation, the eco-champions leaderboard, daily four-stream waste "
     "declarations, PAYT invoices with UPI payment and receipts, and real-time "
     "notifications when a complaint moves.",
     "citizen"),
    ("13_worker",
     "The worker portal opens after MFA. It shows today's dispatch queue "
     "ranked by predicted fill, maintenance tasks, and the geofenced bin "
     "checklist - a bin can only be cleared on site, with a live after-photo "
     "as proof. Offload logs close the loop at the dump yard.",
     "worker"),
    ("14_admin",
     "The admin control room is the operational brain: live bin telemetry "
     "with fire, methane and tilt alerts, SLA-escalating complaints, worker "
     "monitoring, OTA firmware pushes, audit trail, failed-job alerts, and "
     "one-click state compliance exports.",
     "admin"),
    # ── The rest of each portal, feature by feature. These scenes open already
    # signed in (the login is shown once per role above) and are driven by the
    # generic "tour" action: an ordered list of (step, args) tuples. Scenes that
    # write - a waste declaration, a preference change, an offload log - submit
    # the real form, so the admin views later in the cut show data this session
    # created.
    ("20_citizen_declare",
     "Back in the citizen portal - still signed in. The dashboard carries a bin "
     "status search, one-tap issue reporting, the cleanliness leaderboard, and "
     "the daily segregation declaration: wet, dry, sanitary and hazardous waste "
     "in kilograms. Watch me declare today's waste and submit it - the weights "
     "feed the household's Green Points and the ward's pay-as-you-throw billing.",
     ("tour", "citizen", (
         ("go", "/dashboard"),
         ("scroll", 500),
         ("pick", "#segWard", 2),
         ("fill", "#wet_kg", "4.5"),
         ("fill", "#dry_kg", "2.0"),
         ("fill", "#sanitary_kg", "0.3"),
         ("fill", "#hazardous_kg", "0.2"),
         ("wait", 0.6),
         ("submit", "text=Declare Segregated Waste"),
         ("wait", 1.6),
         ("scroll", 400),
     ))),
    ("21_citizen_prefs",
     "Notification preferences: the citizen chooses which events trigger a "
     "push notification - complaint submitted, assigned, in progress, resolved "
     "or escalated, schedule reminders, Green Points earned, and a weekly "
     "summary. I'll switch the weekly summary on and save.",
     ("tour", "citizen", (
         ("go", "/notifications/preferences"),
         ("wait", 0.8),
         ("check", "#weekly_summary"),
         ("wait", 0.5),
         ("submit", "text=Save Preferences"),
         ("wait", 1.4),
         ("scroll", 400),
     ))),
    ("22_citizen_payt",
     "Pay-as-you-throw billing. This is the outstanding August invoice - 363 "
     "rupees, billed on 62.9 percent segregation compliance with the penalty "
     "multiplier shown openly. The citizen pays by UPI or card through Razorpay "
     "right here, and every settled invoice has a downloadable PDF receipt.",
     ("tour", "citizen", (
         ("go", "/payt/pay/3"),
         ("wait", 1.2),
         ("scroll", 700),
     ))),
    ("23_citizen_track_delete",
     "Every complaint gets a signed tracking link - the tracking page explains "
     "how to use it, how to reopen a resolved complaint, and how to rate the "
     "resolution. Under the Digital Personal Data Protection Act a citizen can "
     "also file a right-to-erasure request here, which lands in the admin queue.",
     ("tour", "citizen", (
         ("go", "/track"),
         ("scroll", 700),
         ("go", "/data-deletion"),
         ("scroll", 700),
     ))),
    ("24_worker_actions",
     "The worker's side of the loop. A driver can raise a bin issue - damage or "
     "blockage - straight from the portal instead of by phone, and at the end of "
     "the round logs the offload at the dump yard, which closes the collection "
     "record for that truck.",
     ("tour", "worker", (
         ("go", "/worker"),
         ("scroll", 900),
         ("pick", "#issueBinId", 1),
         ("pick", "#issueType", 1),
         ("fill", "#issueDetails",
          "Lid hinge broken - bin cannot be closed after emptying."),
         ("wait", 0.6),
         ("submit", "text=Dispatch Issue Report"),
         ("wait", 1.4),
         ("scroll", 700),
         # The dump yard is a required field: without it the browser blocks the
         # submit and no request ever reaches the app.
         ("pick", "#dumpYardId", 1),
         ("fill", "#offloadWeight", "420.5"),
         ("wait", 0.6),
         ("submit", "text=Log & Verify Digital Manifest"),
         ("wait", 1.8),
         ("scroll", 500),
     ))),
    ("25_admin_firmware_ops",
     "Admin operations, continued. OTA firmware management pushes ESP32 and "
     "Arduino updates to the bins over Wi-Fi, with a release history and a "
     "per-bin connectivity report - no physical access needed. The offline "
     "deliveries view audits complaints and photos that arrived through the PWA "
     "queue, and the dead-letter queue exposes background jobs that exhausted "
     "their retry budget.",
     ("tour", "admin", (
         ("go", "/admin/firmware"),
         ("scroll", 700),
         ("go", "/admin/offline-deliveries"),
         ("scroll", 600),
         ("go", "/admin/failed-jobs"),
         ("scroll", 500),
     ))),
    ("26_admin_photogate_audit",
     "This is the photo gate's feedback loop: uploads the anti-fake-report model "
     "refused land here so an admin can relabel a false positive, and the "
     "relabelled set downloads as the next retraining batch. Behind everything "
     "sits the immutable audit trail - tamper-proof, with every action from all "
     "three roles recorded.",
     ("tour", "admin", (
         ("go", "/admin/photo-rejections"),
         ("scroll", 600),
         ("go", "/admin/audit"),
         ("scroll", 800),
     ))),
    ("27_admin_analytics",
     "The analytics and compliance hub: predictive collection heatmaps, an ESG "
     "compliance audit, the carbon-footprint tracker and circular-economy "
     "reports - plus one-click exports, the state portal compliance file, the "
     "CSRD export and a performance PDF.",
     ("tour", "admin", (
         ("go", "/analytics"),
         ("wait", 1.2),
         ("scroll", 1000),
     ))),
    ("28_admin_privacy_super",
     "Governance. The deletion queue lists right-to-erasure requests with their "
     "acknowledge and completion deadlines, and the super-admin console is the "
     "only place a new administrator account can be created - public "
     "registration never grants a staff role.",
     ("tour", "admin", (
         ("go", "/admin/data-deletion"),
         ("scroll", 600),
         ("go", "/admin/super"),
         ("scroll", 700),
     ))),
    ("29_public_picker_register",
     "Registration is open to citizens, and the informal waste picker register "
     "is a flow of its own: recognition under Swachh Bharat Mission Phase Two "
     "for the people who already keep the ward clean.",
     ("tour", "public", (
         ("go", "/register/picker"),
         ("scroll", 800),
         ("go", "/register"),
         ("scroll", 600),
     ))),
    ("30_public_bwg_search",
     "Bulk waste generators - hotels, shops, institutions - declare their waste "
     "in the BWG ledger, which drives the panchayat's bulk collection approvals. "
     "And site-wide search jumps straight to any of these services.",
     ("tour", "citizen", (
         ("go", "/bwg-ledger"),
         ("wait", 1.0),
         ("scroll", 800),
         ("go", "/search"),
         ("scroll", 600),
     ))),
    ("31_public_offline_satisfaction",
     "Rural connectivity is the default, so the offline page states exactly what "
     "still works - draft a report now, it syncs when the signal returns. Cookie "
     "settings give granular consent, and the ward satisfaction report ranks all "
     "five wards by the ratings citizens give after a resolution.",
     ("tour", "public", (
         ("go", "/offline"),
         ("scroll", 500),
         ("go", "/cookie-settings"),
         ("scroll", 600),
         ("go", "/reports/ward-satisfaction"),
         ("scroll", 700),
     ))),
    # ── The remaining surfaces of the site. Everything the route table serves
    # as a page is filmed: these three close the gaps left by the grouped scenes
    # above (the anonymous dump channel, the grievance officer, the legal /
    # accessibility statements) and, in 33, walk the report -> signed tracking
    # page -> dashboard loop end to end with a real submission.
    ("32_public_illegal_grievance",
     "Illegal dumping has its own anonymous channel: an eyewitness files a dump "
     "report with a photo and the location, and the system strips EXIF and never "
     "stores who reported it. If a complaint is mishandled, the grievance page "
     "names the redressal officer and the order in which a grievance escalates.",
     ("tour", "public", (
         ("go", "/report-illegal"),
         ("scroll", 900),
         ("go", "/grievance"),
         ("scroll", 900),
     ))),
    ("33_citizen_file_track",
     "Filing and tracking, end to end. The report form takes the ward, the "
     "address and the description, and tags the exact device coordinates - GPS "
     "is mandatory, so a report cannot be filed from nowhere. On submit the "
     "citizen lands on the signed tracking page: the live status timeline, the "
     "ward's SLA window, the one-tap reopen if a resolution does not hold, and "
     "the satisfaction rating once it closes. Back on the dashboard the "
     "complaint is listed with its tracking link.",
     ("tour", "citizen", (
         ("go", "/dashboard"),
         ("wait", 0.8),
         ("scroll", 500),
         ("go", "/report"),
         ("pick", "#repWard", 1),
         ("fill", "#repAddress",
          "Door No 7-14, Gandhi Road, opposite the ward office"),
         ("fill", "#repDescription",
          "Garbage collection skipped twice this week - dustbin overflowing "
          "near the school gate."),
         ("wait", 0.6),
         ("submit", "text=Submit Report to Panchayat Sanitation Team"),
         ("wait", 2.0),
         ("scroll", 400),
         # The filing confirms in place and hands the reporter the signed
         # tracking link (absolute, target=_blank); follow it to the live
         # status page in this tab.
         ("click", 'a[href*="/track/"]'),
         ("wait", 1.6),
         ("scroll", 800),
         ("go", "/dashboard"),
         ("wait", 1.2),
         ("scroll", 700),
     ))),
    ("34_public_legal_a11y",
     "The legal and inclusion layer. The privacy policy sets out what the "
     "portal collects and why under the data-protection framework, the terms of "
     "service state the rules of use, and the accessibility statement publishes "
     "the WCAG commitments - keyboard support, heading structure and contrast.",
     ("tour", "public", (
         ("go", "/privacy"),
         ("scroll", 900),
         ("go", "/terms"),
         ("scroll", 800),
         ("go", "/accessibility"),
         ("scroll", 900),
     ))),
    ("35_password_recovery",
     "Account recovery, for the moment a password or the verification mail goes "
     "missing: a citizen enters the username and the portal mails a single-use "
     "reset link, or, if the verification email never arrived, asks for a fresh "
     "verification link against the address on the account. Both links are for "
     "one use only.",
     ("tour", "public", (
         ("go", "/reset-password-request"),
         ("scroll", 600),
         ("go", "/resend-verification"),
         ("scroll", 600),
     ))),
    ("15_pwa",
     "SmartGarbage is an installable Progressive Web App. On a phone, the "
     "browser offers an install button; after that the app opens full-screen "
     "and keeps working without internet - pages are cached and complaints "
     "filed offline sync automatically when connectivity returns.",
     "mobile"),
    ("16_deploy",
     "Under the hood: GitHub pushes auto-deploy to Render, PostgreSQL runs on "
     "Supabase, Cloudflare serves the edge, and GitHub Actions pings the "
     "health endpoint every fifteen minutes. The entire stack is free-tier.",
     "back_home"),
    ("17_close",
     "That is SmartGarbage - schedules, complaints, transparency, machine "
     "learning dispatch, gamification and billing, all bilingual in English "
     "and Telugu, running at zero cost for the panchayat. Thank you.",
     "final"),
]

# Scenes that should START on a specific page (record() otherwise opens "/",
# whose load time would push the action past the narration cut).
START_PAGES = {"track_auth": "/login", "citizen": "/login", "worker": "/login",
               "admin": "/login", "schedule": "/schedule",
               "report": "/report", "transparency": "/transparency",
               "impact": "/impact", "about_faq": "/about",
               # Tour scenes: the starts below are the page the scene's first
               # step would navigate to anyway, so no homepage pre-roll.
               "20_citizen_declare": "/dashboard",
               "21_citizen_prefs": "/notifications/preferences",
               "22_citizen_payt": "/payt/pay/3",
               "23_citizen_track_delete": "/track",
               "24_worker_actions": "/worker",
               "25_admin_firmware_ops": "/admin/firmware",
               "26_admin_photogate_audit": "/admin/photo-rejections",
               "27_admin_analytics": "/analytics",
               "28_admin_privacy_super": "/admin/data-deletion",
               "29_public_picker_register": "/register/picker",
               "30_public_bwg_search": "/bwg-ledger",
               "31_public_offline_satisfaction": "/offline",
               "32_public_illegal_grievance": "/report-illegal",
               "33_citizen_file_track": "/dashboard",
               "34_public_legal_a11y": "/privacy",
               "35_password_recovery": "/reset-password-request"}


# Seeded demo logins (password == username; see the defaults in app/__init__.py
# and scripts/run_local_stack.py). They exist only locally or with
# SEED_DEMO=true - a production deployment never creates them.
DEMO_LOGINS = {
    "citizen": ("24331A4441CITIZEN", "/dashboard"),
    "worker": ("24331A4441WORKER", "/worker"),
    "admin": ("24331A4441ADMIN", "/admin"),
}

# on-screen caption per scene (same order as SCENES)
CAPTIONS = [
    "Homepage - SmartGarbage Chintalavalasa Portal",
    "Live ward data, collection days & helpline 1800 119 9111",
    "Collection Schedule - pick your ward: pickup days + AI overflow risk",
    "Report a Missed Pickup - GPS location, photo proof, tracking token",
    "WhatsApp fallback & toll-free helpline - always reachable",
    "Transparency Dashboard - open complaint & collection data",
    "Impact & Contact - community results and every contact channel",
    "About & FAQ - segregation, Green Points and PAYT explained",
    "Track Complaints & Secure Login - token tracking, staff MFA",
    "Citizen Dashboard - Green Points, declarations, PAYT billing",
    "Worker Portal - MFA entry, ML-ranked dispatch, geofenced proof",
    "Admin Control Room - live telemetry, SLA, exports, audit",
    "Citizen - four-stream waste declaration feeding Green Points",
    "Notification Preferences - per-event push switches",
    "PAYT billing - invoice, UPI / Razorpay payment, PDF receipt",
    "Signed tracking links & DPDP right-to-erasure request",
    "Worker - raise a bin issue, log the dump-yard offload",
    "Admin - OTA firmware, offline deliveries, dead-letter queue",
    "Admin - photo-gate relabelling & the immutable audit trail",
    "Analytics & Compliance - ESG, carbon, state portal exports",
    "Admin - DPDP deletion queue & super-admin console",
    "Public - account registration & the informal waste picker register",
    "BWG ledger - bulk generators declare, panchayat approves",
    "Offline PWA, cookie consent & ward satisfaction rankings",
    "Anonymous illegal-dumping report & grievance redressal officer",
    "File a complaint & track it - signed link, live timeline, SLA, reopen",
    "Privacy policy, terms of service & accessibility statement",
    "Account recovery - password reset & a fresh verification link",
    "Installable PWA - works offline, syncs when back online",
    "Powered by Render + Supabase + Cloudflare - 100% free tier",
    "Schedules, complaints, ML dispatch, gamification - bilingual, zero cost",
]


def goto_retry(pg, url, attempts=4):
    """goto with retries. The app runs Socket.IO, whose persistent websocket
    means 'networkidle' NEVER fires - use domcontentloaded + a settle wait."""
    last = None
    for k in range(attempts):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            return
        except Exception as e:
            last = e
            print("      goto retry %d for %s (%s)" % (k + 1, url, str(e)[:60]))
            time.sleep(6 * (k + 1))
    raise last


def dismiss_banner(pg):
    """Close the cookie-consent banner if present - it overlays the bottom of
    the page and can intercept clicks on the MFA 'Email me the code' button."""
    try:
        btn = pg.get_by_text("Hide", exact=True)
        if btn.count():          # absent: skip instantly instead of timing out
            btn.first.click(timeout=2500)
            time.sleep(0.3)
    except Exception:
        pass


def wait_content(pg):
    """Wait until real page content is visible, then settle briefly.

    base.html has no <header> (it uses <nav> + <main id="main-content">), so the
    old header-first chain burned its whole 15s timeout at the head of every
    scene - longer than a narration window. Match on what actually exists.
    """
    try:
        pg.wait_for_selector("main, h1, nav", state="visible", timeout=15000)
    except Exception:
        pass
    time.sleep(0.6)


def ensure_page(page, path):
    """Navigate to `path` unless the scene already opened there.

    Scenes start on the page they explain (see START_PAGES), so the recorded
    window opens on the feature itself instead of a homepage pre-roll.
    """
    if page.url.split("?")[0].rstrip("/") != (BASE + path).rstrip("/"):
        goto_retry(page, BASE + path)
        wait_content(page)


def grant_location(ctx):
    """Give the recording context a live device position (see /report's GPS gate)."""
    try:
        ctx.grant_permissions(["geolocation"], origin=BASE)
        ctx.set_geolocation({"latitude": 18.0675, "longitude": 83.4094,
                             "accuracy": 12})
    except Exception as e:
        print("      geolocation grant skipped:", str(e)[:70])


def clear_webms(d):
    for f in glob.glob(os.path.join(d, "*.webm")) + \
             glob.glob(os.path.join(d, "*.det.txt")):
        try:
            os.remove(f)
        except OSError:
            pass


def role_login(page, role):
    """Sign in ON CAMERA with the role's seeded demo credentials.

    The old pipeline authenticated inside a throwaway browser and injected the
    resulting session cookie, so no scene ever showed a password being typed
    even though the narration describes exactly that ("watch the worker sign in
    now"). The credentials go into the real form here, with typewriter pacing.

    Staff logins land on the MFA screen, which flashes its dev code under the
    form on localhost; the code is read from the page itself, so there is no
    pre-harvested OTP that can expire before it is typed.
    """
    username, role_url = DEMO_LOGINS[role]
    goto_retry(page, BASE + "/login")
    wait_content(page)
    dismiss_banner(page)
    u_field = page.locator("#lg_username")
    u_field.click()
    page.keyboard.type(username, delay=35)
    page.locator("#lg_password").click()
    page.keyboard.type(username, delay=35)  # demo password == username
    time.sleep(0.3)
    page.locator("#password-login button[type=submit]").first.click()
    page.wait_for_load_state("domcontentloaded")
    otp = None
    for _ in range(24):          # MFA screen can lag under load; citizens skip it
        m = re.search(r"Dev OTP \(localhost\):\s*(\d{6})", page.inner_text("body"))
        if m:
            otp = m.group(1)
            break
        if role_url in page.url:
            break
        time.sleep(0.25)
    if otp:
        try:
            page.locator("input[name=otp]").fill(otp)
            time.sleep(0.3)
            page.locator("button:has-text('Verify and Proceed')").first.click(timeout=6000)
        except Exception as e:
            print("      mfa fill skipped:", str(e)[:60])
        for _ in range(16):
            if role_url in page.url:
                break
            time.sleep(0.25)
    if role_url not in page.url:
        # The session is authenticated either way, so land on the portal rather
        # than leaving the scene on a login form the narration does not cover.
        print("      login fallback -> %s (was %s)" % (role_url, page.url))
        goto_retry(page, BASE + role_url)
    wait_content(page)
    print("      logged in as %s -> %s" % (role, page.url))


def harvest_session(pw, role):
    """Sign in as `role` in a THROWAWAY (unrecorded) browser; return its cookies.

    The sign-in is filmed once per role (12_citizen / 13_worker / 14_admin), so
    the feature-by-feature tour scenes that follow open already signed in rather
    than repeating the password and MFA beats - the same demo credentials and
    the same MFA path, just not recorded.
    """
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(service_workers="block")
    page = ctx.new_page()
    page.set_default_timeout(30000)
    cookies = []
    try:
        role_login(page, role)
        cookies = ctx.cookies(BASE)
    except Exception as e:
        print("      harvest failed for %s: %s" % (role, str(e)[:70]))
    ctx.close()
    browser.close()
    return cookies


def record(pw, name, action, start="/", extra=None):
    extra = extra or {}
    """Record one scene -> _video_live/raw_<name>/*.webm

    `action` is either a named action (see the dispatch below) or a tour tuple
    ("tour", auth_role_or_None, steps) - an ordered list of page steps. Tours
    exist so the feature-by-feature pass over each portal is data, not code.
    """
    tour = ()
    if isinstance(action, tuple) and action and action[0] == "tour":
        tour = tuple(action[2])
        action = "tour"
    webm_dir = os.path.abspath(os.path.join(VD, "raw_" + name))
    os.makedirs(webm_dir, exist_ok=True)
    clear_webms(webm_dir)
    t_video0 = time.monotonic()   # the take starts when the context is created
    browser = pw.chromium.launch(headless=True)
    # service_workers="block" is CRITICAL: sw.js is offline-first cache-first,
    # so it would serve the cached homepage for EVERY navigation and the video
    # would show the wrong page under each caption.
    ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                              device_scale_factor=1,
                              service_workers="block",
                              record_video_dir=webm_dir,
                              record_video_size={"width": 1280, "height": 720})
    # Recording cosmetics: #sgSplash (brand intro) and #sgPrivacyNotice (cookie
    # notice) are loading/permission overlays, not page content, and they sat on
    # top of the feature being narrated - the splash alone ate ~4s of every
    # narration window. Hidden for the take via an init script so every
    # navigation in this context is clean.
    ctx.add_init_script(
        "const _sgS=document.createElement('style');"
        "_sgS.textContent='#sgSplash,#sgPrivacyNotice{display:none!important}';"
        "(document.head||document.documentElement).appendChild(_sgS);")
    # Emulate a real device location: /report refuses to file without a live
    # GPS fix (and blocks the submit client-side), so a headless browser that
    # denies geolocation could never film the filing flow. The coordinates are
    # the panchayat office in Ward 2 - the same locality the demo data uses.
    grant_location(ctx)
    page = ctx.new_page()
    page.set_default_timeout(45000)
    # Portal tour scenes open signed in: the sign-in is filmed once per role
    # (12_citizen / 13_worker / 14_admin), so repeating it would cost the
    # feature time and show nothing new. The session is harvested in an
    # unrecorded browser; the role's login uses the same demo credentials the
    # filmed sign-ins type.
    auth = extra.get("auth")
    if auth and auth in DEMO_LOGINS:
        cookies = harvest_session(pw, auth)
        if cookies:
            ctx.add_cookies(cookies)
            print("      %s session injected for %s" % (auth, name))
    goto_retry(page, BASE + start)
    wait_content(page)
    dismiss_banner(page)  # consent strip otherwise peeks above the caption band

    def scroll_slow(px, step=140, pause=0.12):
        for _ in range(0, px, step):
            page.mouse.wheel(0, step)
            time.sleep(pause)

    if action == "home":
        time.sleep(1.5)
    elif action == "scroll_home":
        scroll_slow(2600)
        time.sleep(0.6)
        page.mouse.wheel(0, -4000)
        time.sleep(0.5)
    elif action == "schedule":
        ensure_page(page, "/schedule")
        time.sleep(1.0)
        # pick a real ward (by visible label) and submit the timetable search
        try:
            label = page.eval_on_selector(
                "#schedWard",
                r"""el => {
                  const opt = [...el.options].find(o => /ward\s*2/i.test(o.textContent));
                  const chosen = opt || el.options[Math.min(2, el.options.length - 1)];
                  el.value = chosen.value;
                  el.dispatchEvent(new Event('input', {bubbles: true}));
                  el.dispatchEvent(new Event('change', {bubbles: true}));
                  return chosen.textContent.trim();
                }""")
            time.sleep(0.6)
            submit_ward_search(page, label)
        except Exception as e:
            print("      ward select skipped:", str(e)[:70])
        time.sleep(2.2)
        scroll_slow(900)
        time.sleep(0.8)
    elif action == "report":
        ensure_page(page, "/report")
        time.sleep(0.8)
        scroll_slow(600)  # bring the form fields into view first
        # fill() waits only for visibility - more reliable than typing here
        try:
            page.locator("#repAddress").fill(
                "Door No 12-34, Temple Street, near ward office")
            time.sleep(0.5)
        except Exception as e:
            print("      address fill skipped:", str(e)[:60])
        try:
            page.locator("#repDescription").fill(
                "Doorstep waste collection missed this morning - bin not emptied.")
            time.sleep(0.5)
        except Exception as e:
            print("      description fill skipped:", str(e)[:60])
        scroll_slow(700)
        time.sleep(1.0)
    elif action == "footer_cta":
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.0)
        try:
            page.hover(".sg-whatsapp-fallback", timeout=4000)
        except Exception:
            pass
        time.sleep(1.2)
    elif action == "transparency":
        ensure_page(page, "/transparency")
        scroll_slow(1400)
        time.sleep(0.8)
    elif action == "impact":
        ensure_page(page, "/impact")
        scroll_slow(1000)
        goto_retry(page, BASE + "/contact")
        wait_content(page)
        scroll_slow(600)
        time.sleep(0.8)
    elif action == "track_auth":
        # The sign-in showcase: the worker's demo password is typed into the
        # real form, the MFA screen appears, and the code the page flashes is
        # typed in - then the worker portal fills the remainder of the scene.
        role_login(page, "worker")
        time.sleep(2.0)
        scroll_slow(600)
        time.sleep(0.6)
    elif action == "citizen":
        # The citizen's demo password goes in on camera, then the dashboard.
        role_login(page, "citizen")
        time.sleep(1.4)  # dashboard widgets settle
        scroll_slow(900)
        time.sleep(0.8)
    elif action == "worker":
        role_login(page, "worker")
        time.sleep(1.6)  # dispatch queue + tiles settle
        scroll_slow(700)
        time.sleep(0.8)
    elif action == "admin":
        role_login(page, "admin")
        time.sleep(1.8)  # live tiles settle
        # The control room is one long page (metrics, GIS telemetry map, fleet
        # geofencing, route optimisation, dispatch queue, sensor health, bot
        # feed, exports): walk most of it, not just the first screen.
        scroll_slow(2800)
        time.sleep(0.8)
    elif action == "tour":
        # A tour is an ordered list of steps. Every step is individually
        # guarded: a selector that moved costs that one beat, never the take.
        for step in tour:
            try:
                kind = step[0]
                if kind == "go":
                    ensure_page(page, step[1])
                    time.sleep(0.9)
                elif kind == "scroll":
                    scroll_slow(step[1])
                    time.sleep(0.5)
                elif kind == "end":
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.0)
                elif kind == "pick":
                    # choose a real <select> option the way the page's own JS does
                    picked = page.eval_on_selector(
                        step[1],
                        "(el, n) => {const o = el.options[Math.min(n, "
                        "el.options.length - 1)]; el.value = o.value;"
                        "el.dispatchEvent(new Event('input', {bubbles: true}));"
                        "el.dispatchEvent(new Event('change', {bubbles: true}));"
                        "return o.textContent.trim();}", step[2])
                    print("      picked %s = %s" % (step[1], picked))
                    time.sleep(0.5)
                elif kind == "fill":
                    page.locator(step[1]).fill(step[2])
                    time.sleep(0.4)
                elif kind == "check":
                    page.locator(step[1]).check()
                    time.sleep(0.5)
                elif kind == "submit":
                    page.locator(step[1]).first.click(timeout=8000)
                    print("      submitted via %s" % step[1])
                    time.sleep(1.2)
                elif kind == "click":
                    # The success panel's tracking link opens in a new tab; the
                    # take has one tab, so follow it in place.
                    page.eval_on_selector(
                        step[1], "el => el.removeAttribute('target')")
                    page.locator(step[1]).first.click(timeout=8000)
                    page.wait_for_load_state("domcontentloaded")
                    print("      clicked %s -> %s" % (step[1], page.url))
                    time.sleep(1.0)
                elif kind == "wait":
                    time.sleep(step[1])
            except Exception as e:
                print("      tour step %s skipped: %s" % (step[0], str(e)[:80]))
    elif action == "about_faq":
        ensure_page(page, "/about")
        scroll_slow(800)
        goto_retry(page, BASE + "/faq")
        wait_content(page)
        scroll_slow(700)
    elif action == "mobile":
        mob_dir = os.path.abspath(os.path.join(VD, "raw_" + name + "_m"))
        os.makedirs(mob_dir, exist_ok=True)
        clear_webms(mob_dir)
        mob = browser.new_context(viewport={"width": 390, "height": 780},
                                  device_scale_factor=1, is_mobile=True,
                                  service_workers="block",
                                  record_video_dir=mob_dir,
                                  record_video_size={"width": 390, "height": 780},
                                  user_agent=("Mozilla/5.0 (Linux; Android 13; "
                                  "Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0 Mobile Safari/537.36"))
        grant_location(mob)
        mob.add_init_script(
            "const _sgS=document.createElement('style');"
            "_sgS.textContent='#sgSplash,#sgPrivacyNotice{display:none!important}';"
            "(document.head||document.documentElement).appendChild(_sgS);")
        mp = mob.new_page()
        goto_retry(mp, BASE + "/")
        wait_content(mp)
        mp.evaluate("window.scrollTo(0, 700)")
        time.sleep(1.0)
        goto_retry(mp, BASE + "/report")
        wait_content(mp)
        mp.evaluate("window.scrollTo(0, 500)")
        time.sleep(1.0)
        mp.close()
        mob.close()
        files = glob.glob(os.path.join(mob_dir, "*.webm"))
        if files:
            open(os.path.join(VD, name + "_m.webm.done"), "w").write(files[0])
    elif action == "back_home":
        goto_retry(page, BASE + "/")
        wait_content(page)
        time.sleep(1.0)
    elif action == "final":
        time.sleep(1.6)

    # Fill the narration window. The cut is "narration + 1s" (to_mp4), so a take
    # shorter than its narration would freeze on its last frame; drift through
    # the page instead, reversing at the ends so the motion stays in view.
    target = float(extra.get("target") or 0.0)
    direction = 1
    while target and (time.monotonic() - t_video0) < target:
        try:
            edge = page.evaluate(
                "(d) => {window.scrollBy(0, d*45);"
                " const b = window.scrollY + window.innerHeight >= "
                "document.documentElement.scrollHeight - 12;"
                " const t = window.scrollY <= 2;"
                " return b ? 1 : (t ? -1 : 0);}", direction)
        except Exception:
            break
        if edge == 1:
            direction = -1
        elif edge == -1:
            direction = 1
        time.sleep(0.18)

    ctx.close()
    browser.close()
    files = glob.glob(os.path.join(webm_dir, "*.webm"))
    webm = files[0] if files else None
    return webm


def narration_seconds():
    """Narration length per scene, read back from the synthesized narr%02d.wav."""
    durs = []
    for i in range(len(SCENES)):
        try:
            with wave.open(os.path.join(VD, "narr%02d.wav" % i), "rb") as w:
                durs.append(w.getnframes() / float(w.getframerate()))
        except Exception:
            durs.append(0.0)
    return durs


def sapi_wavs():
    ps = os.path.join(VD, "tts.ps1")
    with open(ps, "w", encoding="utf-8") as f:
        f.write("Add-Type -AssemblyName System.Speech\n")
        f.write("$v = New-Object System.Speech.Synthesis.SpeechSynthesizer\n")
        f.write("$v.SelectVoice('Microsoft Zira Desktop')\n")
        f.write("$v.Rate = 0\n")
        for i, (_, text, _) in enumerate(SCENES):
            wav = os.path.abspath(os.path.join(VD, "narr%02d.wav" % i)).replace("\\", "/")
            safe = text.replace("'", "''")
            f.write("$v.SetOutputToWaveFile('%s')\n" % wav)
            f.write("$v.Speak('%s')\n" % safe)
            f.write("$v.SetOutputToWaveFile($null)\n")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", ps], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        print(r.stderr[-600:])
        raise SystemExit(1)


def content_times(webm):
    """Per-frame luma scan -> list of timestamps that show real content."""
    det = webm + ".det.txt"
    vf = ("crop=iw:ih-8:0:0,signalstats,"
          "metadata=print:key=lavfi.signalstats.YAVG:file='%s'"
          % det.replace("\\", "/").replace(":", "\\:"))
    subprocess.run([FF, "-y", "-i", webm, "-vf", vf, "-an", "-f", "null", "-"],
                   check=True, capture_output=True)
    ts = []
    t = None
    for line in open(det, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("frame:") and "pts_time:" in line:
            t = float(line.split("pts_time:")[1].split()[0])
        elif "YAVG=" in line and t is not None:
            v = float(line.split("YAVG=")[1].split()[0])
            if v < WHITE_YAVG:
                ts.append(t)
            t = None
    try:
        os.remove(det)
    except OSError:
        pass
    return ts


def trim_window(webm):
    """(leading_skip, input_cut) to drop blank white head/tail, or (0, None)."""
    ts = content_times(webm)
    if not ts:
        return 0.0, None
    leading = max(0.0, ts[0] - 0.3) if ts[0] > 0.5 else 0.0
    tail = ts[-1] + 0.3
    cut = tail - leading
    if cut < 1.0:
        return 0.0, None
    return leading, cut


def esc(text):
    """Escape a string for ffmpeg drawtext."""
    return (text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
                .replace("%", "\\%"))


def caption_filter(text, total):
    """drawtext caption band shown from 0.4s to the end of the segment."""
    return ("drawtext=fontfile='%s':text='%s':fontsize=32:fontcolor=white"
            ":x=(w-text_w)/2:y=h-74:box=1:boxcolor=0x124630D9:boxborderw=18"
            ":enable='gte(t,0.4)'" % (FONT, esc(text)))


def to_mp4(webm, wav, out, fade_out=False, caption=None):
    with wave.open(wav, "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    total = dur + 1.0
    leading, cut = trim_window(webm)
    ins = []
    if leading > 0.2:
        ins += ["-ss", "%.2f" % leading]
    if cut:
        ins += ["-t", "%.2f" % cut]
    vf = ("crop=iw:ih-8:0:0,"
          "scale=1280:720:force_original_aspect_ratio=decrease,"
          "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
    if cut:
        vf += ",tpad=stop_mode=clone:stop_duration=%.2f" % max(0.0, total - cut + 2.0)
    if caption:
        vf += "," + caption_filter(caption, total)
    if fade_out:
        vf += ",fade=t=out:st=%.1f:d=0.8" % (total - 0.8)
    # CRF 25 / 96k mono keeps the finished cut (~82 MB for ~10 min) under
    # GitHub's 100 MB per-file push limit, which the deliverable is committed
    # with. At 21/128k the same cut is ~117 MB and a push is rejected outright;
    # 720p screen footage is flat and compresses well, so the text stays sharp.
    # Measured per-scene ratios are in _probe_encode_size.py's output.
    cmd = ([FF, "-y"] + ins + ["-i", webm, "-i", wav,
           "-t", "%.2f" % total, "-vf", vf,
           "-c:v", "libx264", "-preset", "medium", "-crf", "25",
           "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "1",
           "-pix_fmt", "yuv420p", out])
    subprocess.run(cmd, check=True, capture_output=True)
    tag = " trim=%.1f+%.1fs" % (leading, cut) if cut else ""
    print("      (video %s%s)" % (os.path.basename(webm), tag))
    return dur


def submit_ward_search(page, label):
    """Click 'View Ward Schedule' and wait for the ward results card.

    The POST runs the ML missed-collection prediction, so one click can outlast
    its timeout (first-request model warm-up, or the results card animating
    under the cursor). Retry the click, then fall back to requestSubmit() so the
    recorded scene always lands on the timetable + risk card.
    """
    btn = page.get_by_role("button", name="View Ward Schedule")
    for attempt in range(3):
        try:
            btn.first.click(timeout=15000)
            break
        except Exception as e:
            print("      ward submit attempt %d: %s" % (attempt + 1, str(e)[:70]))
            time.sleep(1.5)
    else:
        # Direct DOM submit: same POST, no actionability dance.
        page.eval_on_selector("#schedWard", "el => el.form.requestSubmit()")
    try:
        page.wait_for_selector("text=Missed Collection Risk", timeout=20000)
    except Exception as e:
        print("      ward results wait:", str(e)[:70])



def warmup():
    """Hit every URL once so Render is awake and CDN/SW caches are warm."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        pg = ctx.new_page()
        pg.set_default_timeout(90000)
        for u in PAGES:
            try:
                goto_retry(pg, BASE + u)
                print("   warm", u, "ok")
            except Exception as e:
                print("   warm", u, "warn:", str(e)[:80])
        ctx.close()
        browser.close()


def main():
    # Resumable: scenes whose segNN.mp4 AND raw footage already exist are
    # skipped, so an interrupted batch continues where it died instead of
    # re-recording everything.
    def existing_raw(name):
        done = os.path.join(VD, name + "_m.webm.done")
        if os.path.exists(done):
            return open(done).read().strip()
        raw_dir = os.path.join(VD, "raw_" + name)
        files = glob.glob(os.path.join(raw_dir, "*.webm")) if os.path.isdir(raw_dir) else []
        return files[0] if files else None

    print("0. synthesizing narration (paces each take to its scene)...")
    sapi_wavs()
    narr = narration_seconds()
    print("   narration: %s" % ", ".join("%.1fs" % d for d in narr))
    print("1. warming up live site (avoid cold-start blanks)...")
    warmup()
    print("2. recording browser scenes...")
    # The three role scenes sign in on camera with their demo credentials; the
    # tour scenes that follow re-enter through a harvested session so they open
    # on the feature instead of on a second login.
    webms = []
    with sync_playwright() as pw:
        for i, (name, _, action) in enumerate(SCENES):
            seg = os.path.abspath(os.path.join(VD, "seg%02d.mp4" % i))
            raw = existing_raw(name)
            if os.path.exists(seg) and raw:
                webms.append((name, raw))
                print("   resume", name)
                continue
            start = START_PAGES.get(name, START_PAGES.get(action, "/"))
            w = record(pw, name, action, start=start,
                       extra={"target": (narr[i] + 0.6) if i < len(narr) else 0.0,
                              "auth": (action[1] if isinstance(action, tuple)
                                       and action[0] == "tour" else None)})
            webms.append((name, w))
            print("   recorded", name)
    print("3. converting scenes (trim + frame-hold + captions)...")
    segs = []
    for i, (name, webm) in enumerate(webms):
        seg = os.path.abspath(os.path.join(VD, "seg%02d.mp4" % i))
        if os.path.exists(seg):
            segs.append(seg)
            print("   keep", name)
            continue
        w = webm
        done = os.path.join(VD, name + "_m.webm.done")
        if os.path.exists(done):
            w = open(done).read().strip()
        wav = os.path.join(VD, "narr%02d.wav" % i)
        to_mp4(w, wav, seg, caption=CAPTIONS[i] if i < len(CAPTIONS) else None,
               fade_out=(i == len(webms) - 1))
        segs.append(seg)
        print("   seg", name)
    print("5. concatenating...")
    lst = os.path.join(VD, "list.txt")
    with open(lst, "w") as f:
        # Website footage only: no title/outro cards are spliced in, so the cut
        # opens on the homepage and closes on the last real page.
        for s in segs:
            f.write("file '%s'\n" % s.replace("\\", "/"))
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", OUT], check=True, capture_output=True)
    print("WROTE %s (%.1f MB)" % (OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
