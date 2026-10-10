"""Preflight role_login() for citizen, worker and admin against the live stack.

Checks the exact code path the recorder will use: type the demo credentials into
the real form, complete MFA from the code the page itself flashes, and confirm
the browser ends up on the role's portal.
"""
import importlib.util
import os
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mvl", os.path.join(HERE, "_make_video_live.py"))
mvl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvl)

ok = True
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    for role in ("citizen", "worker", "admin"):
        ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                                  service_workers="block")
        page = ctx.new_page()
        page.set_default_timeout(45000)
        expected = mvl.DEMO_LOGINS[role][1]
        t0 = time.monotonic()
        try:
            mvl.role_login(page, role)
        except Exception as e:
            print("  %-8s EXCEPTION %s" % (role, str(e)[:120]))
            ok = False
            ctx.close()
            continue
        took = time.monotonic() - t0
        landed = page.url.replace(mvl.BASE, "") or "/"
        good = landed.startswith(expected)
        ok = ok and good
        # What the recording would show at the end of the login step.
        title = page.title()[:60]
        print("  %-8s %-5s %.1fs  %s -> %s   [%s]"
              % (role, "OK" if good else "FAIL", took, "/login", landed, title))
        ctx.close()
    browser.close()

print("\nPREFLIGHT: %s" % ("all three roles reach their portal" if ok else "PROBLEMS FOUND"))
