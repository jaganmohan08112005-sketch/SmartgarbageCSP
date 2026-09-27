#!/usr/bin/env python3
"""Documentation_DEMO_VIDEO v4 - LIVE WEBSITE WALKTHROUGH (explains every feature).

Playwright drives a real browser over https://smartgarbage.onrender.com and
INTERACTS with it (ward selection, form fills, login fields, mobile PWA).
Every scene carries an on-screen caption band that names the feature being
explained; a branded title card opens the video and an outro card closes it.
Narration via SAPI TTS per scene. Output: 1280x720 H.264 + AAC.

v4 changes:
- drawtext caption band per scene (feature name + one-line explanation)
- title/outro cards from report/video/card_*.png
- real interactions: schedule ward picker, report form typing, login fields
- all segments re-encoded uniformly (concat-safe), mono AAC everywhere
"""
import glob
import os
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
OUT = os.path.join(HERE, "Documentation_DEMO_VIDEO.mp4")
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
START_PAGES = {"track_auth": "/mfa-verify"}

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
        pg.get_by_text("Hide", exact=True).first.click(timeout=2500)
        time.sleep(0.3)
    except Exception:
        pass


def wait_content(pg):
    """Wait until real page content is visible, then settle briefly."""
    for sel in ("header", "h1", "nav a"):
        try:
            pg.wait_for_selector(sel, state="visible", timeout=15000)
            break
        except Exception:
            continue
    time.sleep(0.6)


def clear_webms(d):
    for f in glob.glob(os.path.join(d, "*.webm")) + \
             glob.glob(os.path.join(d, "*.det.txt")):
        try:
            os.remove(f)
        except OSError:
            pass


def auth_cookies(pw, username, password, complete_mfa=True):
    """Authenticate in a THROWAWAY (unrecorded) browser and return the session
    cookies. For staff roles the throwaway session stops with mfa_pending=True,
    so the recording context can open straight on the MFA screen and finish
    the login on camera - no dead login-typing time inside the recorded window."""
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(service_workers="block")
    pg = ctx.new_page()
    pg.set_default_timeout(30000)
    goto_retry(pg, BASE + "/login")
    pg.locator("#lg_username").fill(username)
    pg.locator("#lg_password").fill(password)
    pg.locator("#password-login button[type=submit]").first.click()
    pg.wait_for_load_state("domcontentloaded")
    import re as _re
    # Poll for the flashed Dev OTP: under load the redirect + flash can take
    # longer than any fixed sleep, and an empty capture silently breaks the
    # on-camera MFA scene.
    m = None
    for _ in range(20):
        m = _re.search(r"Dev OTP \(localhost\):\s*(\d{6})", pg.inner_text("body"))
        if m:
            break
        time.sleep(0.5)
    # Complete MFA HERE (fresh OTP, no TTL race): the recording context then
    # starts already authenticated on the role's portal.
    role_url = "/dashboard"
    if m and complete_mfa:
        if "/worker" in pg.url or True:
            role_url = "/worker" if "WORKER" in username.upper() else (
                "/admin" if "ADMIN" in username.upper() else role_url)
        pg.locator("input[name=otp]").fill(m.group(1))
        pg.locator("input[name=otp]").press("Enter")
        try:
            pg.wait_for_url("**" + role_url, timeout=15000)
        except Exception:
            pass
        time.sleep(0.8)
    cookies = ctx.cookies(BASE)
    ctx.close()
    browser.close()
    # dev_otp: the code flashed at login - for complete_mfa=False sessions the
    # recording scene types it on camera (fresh at harvest, 5-min TTL >> delay).
    print("      harvest: otp_found=%s role_url=%s" % (bool(m), role_url))
    return cookies, role_url, (m.group(1) if m else "")


def record(pw, name, action, cookies=None, start="/", extra=None):
    extra = extra or {}
    """Record one scene -> _video_live/raw_<name>/*.webm"""
    webm_dir = os.path.abspath(os.path.join(VD, "raw_" + name))
    os.makedirs(webm_dir, exist_ok=True)
    clear_webms(webm_dir)
    browser = pw.chromium.launch(headless=True)
    # service_workers="block" is CRITICAL: sw.js is offline-first cache-first,
    # so it would serve the cached homepage for EVERY navigation and the video
    # would show the wrong page under each caption.
    ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                              device_scale_factor=1,
                              service_workers="block",
                              record_video_dir=webm_dir,
                              record_video_size={"width": 1280, "height": 720})
    page = ctx.new_page()
    page.set_default_timeout(45000)
    if cookies:
        # Pre-authenticated session (throwaway browser harvest) so the scene
        # opens directly on the role's page instead of the login round-trip.
        ctx.add_cookies(cookies)
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
        goto_retry(page, BASE + "/schedule")
        wait_content(page)
        time.sleep(1.0)
        # pick a real ward (by visible label) and submit the timetable search
        try:
            page.eval_on_selector(
                "#schedWard",
                r"""el => {
                  const opt = [...el.options].find(o => /ward\s*2/i.test(o.textContent));
                  if (opt) { el.value = opt.value; }
                  else { el.selectedIndex = Math.min(2, el.options.length - 1); }
                  el.dispatchEvent(new Event('input', {bubbles: true}));
                  el.dispatchEvent(new Event('change', {bubbles: true}));
                }""")
            time.sleep(0.6)
            page.get_by_role("button", name="View Ward Schedule").click(timeout=8000)
        except Exception as e:
            print("      ward select skipped:", str(e)[:60])
        time.sleep(2.2)
        scroll_slow(900)
        time.sleep(0.8)
    elif action == "report":
        goto_retry(page, BASE + "/report")
        wait_content(page)
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
        goto_retry(page, BASE + "/transparency")
        wait_content(page)
        scroll_slow(1400)
        time.sleep(0.8)
    elif action == "impact":
        goto_retry(page, BASE + "/impact")
        wait_content(page)
        scroll_slow(1000)
        goto_retry(page, BASE + "/contact")
        wait_content(page)
        scroll_slow(600)
        time.sleep(0.8)
    elif action == "track_auth":
        # Starts ON /login (START_PAGES). Worker credentials -> submit ->
        # MFA screen with the 'Email me the code' option lands inside the
        # narration window. (An in-scene goto from /track proved flaky: the
        # first navigation attempt occasionally stalled the full 30s.)
        # Pending-session cookie -> the take opens ON the MFA screen. Type the
        # fresh OTP IMMEDIATELY (record() already waited for content; the
        # consent banner only overlays the bottom strip, below the submit
        # button, so it cannot block the click) - the portal lands well inside
        # the narration cut.
        time.sleep(1.2)
        otp = (extra.get("dev_otp") or "").strip()
        # Tight timeline: fill -> CLICK the submit (Enter proved flaky under
        # load) -> poll briefly -> hard-navigate, so the worker portal fills
        # the scene well inside the narration cut (~24s).
        if otp:
            try:
                page.locator("input[name=otp]").fill(otp)
                print("      mfa typed, input_value_len=%s"
                      % len(page.locator("input[name=otp]").input_value()))
                time.sleep(0.4)
                page.locator("button:has-text('Verify and Proceed')").first.click(
                    timeout=5000)
            except Exception as e:
                print("      mfa fill skipped:", str(e)[:60])
            for _ in range(10):  # up to ~5s for the verify redirect
                if "/worker" in page.url:
                    break
                time.sleep(0.5)
            if "/worker" not in page.url:
                # Second attempt: Enter key (proved reliable in isolation)
                try:
                    page.locator("input[name=otp]").fill(otp)
                    page.locator("input[name=otp]").press("Enter")
                except Exception:
                    pass
                for _ in range(10):
                    if "/worker" in page.url:
                        break
                    time.sleep(0.5)
            print("      mfa verify url:", page.url)
        if "/worker" not in page.url:
            goto_retry(page, BASE + "/worker")  # portal fills the remainder
        wait_content(page)
        time.sleep(2.0)
        scroll_slow(600)
        time.sleep(0.6)
    elif action == "citizen":
        # Session cookie injected - the recording starts ON the dashboard.
        time.sleep(1.8)  # dashboard widgets settle
        scroll_slow(900)
        time.sleep(0.8)
    elif action == "worker":
        # Session injected mid-MFA (mfa_pending=True). Finish the REAL
        # 'Email me the code' flow EARLY so the portal fills the narration
        # window (the final cut keeps only the first ~19s of the take).
        # Fully-authenticated session cookie -> the take starts ON the portal
        # (MFA itself is showcased live in scene 09). No OTP-timing hazards.
        time.sleep(2.2)  # dispatch queue + tiles settle
        scroll_slow(700)
        time.sleep(0.8)
    elif action == "admin":
        # Same early MFA completion, then the control room fills the window.
        # Fully-authenticated session cookie -> straight onto the control room.
        time.sleep(2.4)  # live tiles settle
        scroll_slow(800)
        time.sleep(0.8)
    elif action == "about_faq":
        goto_retry(page, BASE + "/about")
        wait_content(page)
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

    ctx.close()
    browser.close()
    files = glob.glob(os.path.join(webm_dir, "*.webm"))
    webm = files[0] if files else None
    return webm


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
    cmd = ([FF, "-y"] + ins + ["-i", webm, "-i", wav,
           "-t", "%.2f" % total, "-vf", vf,
           "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
           "-pix_fmt", "yuv420p", out])
    subprocess.run(cmd, check=True, capture_output=True)
    tag = " trim=%.1f+%.1fs" % (leading, cut) if cut else ""
    print("      (video %s%s)" % (os.path.basename(webm), tag))
    return dur


def card_mp4(png, seconds, out, fade_in=False, fade_out=False):
    """Title/outro card: still PNG + silence, encoded to match scene segments."""
    vf = "scale=1280:720,setsar=1,fps=30"
    if fade_in:
        vf += ",fade=t=in:st=0:d=0.6"
    if fade_out:
        vf += ",fade=t=out:st=%.1f:d=0.8" % (seconds - 0.8)
    subprocess.run([FF, "-y", "-loop", "1", "-i", png, "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=mono", "-t", "%.2f" % seconds,
                    "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
                    "-pix_fmt", "yuv420p", out], check=True, capture_output=True)
    print("      (card %s)" % os.path.basename(out))


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

    print("1. warming up live site (avoid cold-start blanks)...")
    warmup()
    print("2. recording browser scenes...")
    # Role scenes open with a pre-harvested session cookie (throwaway browser),
    # so no login typing burns recorded time. Staff roles land mid-MFA.
    role_sessions = {}
    try:
        with sync_playwright() as pw:
            print("   harvesting citizen session...")
            c, u, _ = auth_cookies(pw, "24331A4441CITIZEN", "24331A4441CITIZEN")
            role_sessions["citizen"] = (c, "/dashboard", "")
            print("   harvesting worker session (full MFA)...")
            c, u, _ = auth_cookies(pw, "24331A4441WORKER", "24331A4441WORKER")
            role_sessions["worker"] = (c, "/worker", "")
            print("   harvesting admin session (full MFA)...")
            c, u, _ = auth_cookies(pw, "24331A4441ADMIN", "24331A4441ADMIN")
            role_sessions["admin"] = (c, "/admin", "")
    except Exception as e:
        print("   WARN cookie harvest failed, role scenes fall back to public pages:", str(e)[:80])
        role_sessions = {}
    webms = []
    with sync_playwright() as pw:
        for i, (name, _, action) in enumerate(SCENES):
            seg = os.path.abspath(os.path.join(VD, "seg%02d.mp4" % i))
            raw = existing_raw(name)
            if os.path.exists(seg) and raw:
                webms.append((name, raw))
                print("   resume", name)
                continue
            cookies, start, dev_otp = role_sessions.get(
                action, (None, START_PAGES.get(action, "/"), ""))
            if action == "track_auth":
                # Pending session + OTP harvested NOW: earlier scenes burn
                # minutes and the OTP TTL is 5 min, so it must be seconds old
                # when typed on camera.
                c9, _, otp9 = auth_cookies(pw, "24331A4441WORKER",
                                           "24331A4441WORKER", complete_mfa=False)
                cookies, start, dev_otp = c9, START_PAGES["track_auth"], otp9
            w = record(pw, name, action, cookies=cookies, start=start,
                       extra={"dev_otp": dev_otp})
            webms.append((name, w))
            print("   recorded", name)
    print("3. synthesizing narration...")
    sapi_wavs()
    print("4. converting scenes (trim + frame-hold + captions)...")
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
    print("5. title & outro cards...")
    tcard = os.path.abspath(os.path.join(VD, "seg_title.mp4"))
    ocard = os.path.abspath(os.path.join(VD, "seg_outro.mp4"))
    card_mp4(os.path.join(HERE, "card_title.png"), 4.5, tcard, fade_in=True)
    card_mp4(os.path.join(HERE, "card_outro.png"), 6.0, ocard, fade_out=True)
    print("6. concatenating...")
    lst = os.path.join(VD, "list.txt")
    with open(lst, "w") as f:
        f.write("file '%s'\n" % tcard.replace("\\", "/"))
        for s in segs:
            f.write("file '%s'\n" % s.replace("\\", "/"))
        f.write("file '%s'\n" % ocard.replace("\\", "/"))
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", OUT], check=True, capture_output=True)
    print("WROTE %s (%.1f MB)" % (OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
