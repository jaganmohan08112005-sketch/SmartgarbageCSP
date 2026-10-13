"""Preflight the new scenes' interactive steps before spending a render pass.

Scene 33 files a real complaint on camera; if anything blocks the submit (the
GPS gate, a required field, CSRF) the take would show a form that never leaves
the page - and the narration would describe a tracking page the video never
reaches. So the exact step list is replayed here, unrecorded, and the landing
URL + the dashboard row are asserted.
"""
import importlib.util
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mvl", os.path.join(HERE, "_make_video_live.py"))
mvl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvl)

STEPS = (
    ("go", "/dashboard"),
    ("wait", 0.8),
    ("scroll", 500),
    ("go", "/report"),
    ("pick", "#repWard", 1),
    ("fill", "#repAddress", "Door No 7-14, Gandhi Road, opposite the ward office"),
    ("fill", "#repDescription",
     "Garbage collection skipped twice this week - dustbin overflowing near the school gate."),
    ("wait", 0.6),
    ("submit", "text=Submit Report to Panchayat Sanitation Team"),
    ("wait", 2.0),
    ("scroll", 400),
    ("click", 'a[href*="/track/"]'),
    ("wait", 1.6),
    ("scroll", 800),
    ("go", "/dashboard"),
    ("wait", 1.2),
    ("scroll", 700),
)

problems = []
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                              service_workers="block")
    mvl.grant_location(ctx)
    page = ctx.new_page()
    page.set_default_timeout(45000)
    mvl.role_login(page, "citizen")

    track_url = None
    for step in STEPS:
        try:
            kind = step[0]
            if kind == "go":
                page.goto(mvl.BASE + step[1], wait_until="domcontentloaded")
                page.wait_for_timeout(900)
                print("  go %-16s -> %s" % (step[1], page.url))
            elif kind == "scroll":
                page.mouse.wheel(0, step[1])
                page.wait_for_timeout(500)
            elif kind == "pick":
                v = page.eval_on_selector(
                    step[1],
                    "(el, n) => {const o = el.options[Math.min(n, el.options.length - 1)];"
                    "el.value = o.value; el.dispatchEvent(new Event('change', {bubbles:true}));"
                    "return o.textContent.trim();}", step[2])
                print("  pick %s = %s" % (step[1], v))
            elif kind == "fill":
                page.locator(step[1]).fill(step[2])
            elif kind == "submit":
                print("  gps fields before submit: lat=%r lon=%r"
                      % (page.input_value("#latitude"), page.input_value("#longitude")))
                page.locator(step[1]).first.click(timeout=8000)
                page.wait_for_timeout(1600)
                page.wait_for_load_state("domcontentloaded")
                track_url = page.url
                print("  submit -> %s" % track_url)
            elif kind == "click":
                page.eval_on_selector(step[1], "el => el.removeAttribute('target')")
                page.locator(step[1]).first.click(timeout=8000)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(1000)
                print("  click %s -> %s" % (step[1], page.url))
                if "/track/" in page.url:
                    track_url = page.url
            elif kind == "wait":
                page.wait_for_timeout(int(step[1] * 1000))
        except Exception as e:
            problems.append("%s %s: %s" % (step[0], step[1] if len(step) > 1 else "", str(e)[:90]))
            print("  STEP FAILED", step, str(e)[:90])

    # 1. did we land on a real tracking page?
    if not track_url or "/track/" not in track_url:
        problems.append("the filing never reached /track/<token> (ended at %s)" % track_url)
    else:
        resp = page.request.get(track_url)
        if resp.status != 200:
            problems.append("tracking page returned %s" % resp.status)
        page.goto(track_url, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        heads = page.eval_on_selector_all(
            "main h1, main h2, main .card-header",
            "els => els.map(e => e.innerText.trim().replace(/\\s+/g,' ')).slice(0,4)")
        print("  track page headings:", heads)
        body = page.eval_on_selector("main", "el => el.innerText.replace(/\\s+/g,' ').slice(0,200)")
        print("  track page body:", body)

    # 2. does the dashboard list it with a tracking link?
    links = page.eval_on_selector_all(
        "a[href*='/track/']", "els => els.map(e => e.getAttribute('href'))")
    print("  dashboard track links:", links[:4])
    if not links:
        problems.append("dashboard shows no tracking link after filing")

    ctx.close()
    browser.close()

print("\nPREFLIGHT: %s" % ("all new-scene steps work" if not problems
                           else "PROBLEMS:\n  " + "\n  ".join(problems)))
sys.exit(1 if problems else 0)
