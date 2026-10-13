"""List what each planned scene page actually renders, for narration that is true.

For every page the expanded tour intends to visit, print the HTTP status, the
first h1/h2, and the opening lines of <main> - logged in as the role that can see
it. A 404/405/500 must never become a filmed blank, and the narration must name
features that exist rather than features that were intended.
"""
import importlib.util
import os
import re

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mvl", os.path.join(HERE, "_make_video_live.py"))
mvl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvl)

PLAN = {
    "public": ["/register/picker", "/register", "/bwg-ledger", "/search",
               "/cookie-settings", "/offline", "/reports/ward-satisfaction",
               "/report-illegal", "/grievance", "/privacy", "/terms",
               "/accessibility"],
    "citizen": ["/dashboard", "/notifications/preferences", "/data-deletion",
                "/payt/pay/3", "/payt/receipt/1", "/report", "/track"],
    "worker": ["/worker"],
    "admin": ["/admin", "/analytics", "/admin/audit", "/admin/failed-jobs",
              "/admin/offline-deliveries", "/admin/photo-rejections",
              "/admin/firmware", "/admin/data-deletion", "/admin/super"],
}


def summarise(page):
    try:
        heads = page.eval_on_selector_all(
            "main h1, main h2, main .card-header",
            "els => els.map(e => e.innerText.trim().replace(/\\s+/g,' '))"
            ".filter(t => t && t.length < 70)")
    except Exception:
        heads = []
    try:
        body = page.eval_on_selector(
            "main", "el => el.innerText.replace(/\\s+/g,' ').trim()")
    except Exception:
        body = ""
    uniq = []
    for h in heads:
        if h not in uniq:
            uniq.append(h)
    return " · ".join(uniq[:4]), re.sub(r"\s+", " ", body)[:150]


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    for role, paths in PLAN.items():
        ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                                  service_workers="block")
        page = ctx.new_page()
        page.set_default_timeout(30000)
        if role != "public":
            mvl.role_login(page, role)
        print("\n===== %s =====" % role.upper())
        for path in paths:
            try:
                resp = page.goto(mvl.BASE + path, wait_until="domcontentloaded",
                                 timeout=25000)
                page.wait_for_timeout(1000)
                code = resp.status if resp else 0
                heads, body = summarise(page)
                print("  %s  [%s] %s\n        %s" % (path, code, heads or "(no headings)",
                                                     body))
            except Exception as e:
                print("  %s  EXCEPTION %s" % (path, str(e)[:80]))
        ctx.close()
    browser.close()
