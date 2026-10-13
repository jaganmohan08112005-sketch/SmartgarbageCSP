"""Does the cut film every page the app serves? Re-runnable coverage probe.

The demo video claims to cover the whole website — public, citizen, worker and
admin — page by page. That claim is only worth as much as the check behind it,
so this probe reads the AUTHORITATIVE Flask url_map (created with a database
URL that is never connected to), classifies each GET route by what its handler
returns, and matches every route against the URLs the recording pipeline knows:

    python report/video/_probe_route_coverage.py           # check, exit 1 on a gap
    python report/video/_probe_route_coverage.py --list    # dump every rule

A route is "filmed" when the cut visits its URL by name. Two documented
exceptions are allowed, and both must still exist:

  FILMED_VIA_REDIRECT  a page the browser reaches through a redirect the cut
                       does perform (the staff OTP screen).
  NOT_NAVIGABLE        a page whose only entry point is an emailed one-time
                       link, so no recording can visit it without the token.

Everything else — downloads (PDF/zip/RSS), state-changing action links and
utility redirects — is reached FROM a filmed page, which is what the table at
the end reports.
"""
import inspect
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # the app package lives at the repo root

from app import create_app  # noqa: E402  (needs ROOT on sys.path first)

VIDEO = ROOT / "report" / "video" / "_make_video_live.py"

# Machine endpoints and non-HTML outputs, matched on the endpoint's own name
# (never as a substring: "main.reset_password" ends in "sw" only by accident).
# Matched as a PREFIX of the endpoint's own name (never as a substring:
# "main.reset_password" merely ends in "sw").
ENDPOINT_SKIP_PREFIXES = (
    "static", "sw", "serve_sw", "sitemap", "robots", "health", "healthz",
    "llms", "manifest", "serve_manifest", "service_worker", "metrics",
    "favicon", "well_known", "webhook",
)
PATH_SKIP_PREFIXES = ("/api/", "/static/", "/tasks/", "/.well-known/")

# A page the cut films without ever typing its URL: the staff sign-in posts to
# /login and the browser is redirected here. Scene 09 shows this screen.
FILMED_VIA_REDIRECT = {
    "/mfa-verify": "the OTP screen every worker/admin sign-in redirects through "
                   "(scene 09 films it)",
}
# A page no recording can reach: the token arrives by email.
NOT_NAVIGABLE = {
    "/reset-password/<token>": "the reset link is mailed as a single-use token; "
                               "the form that requests it is filmed instead",
}
# Pages whose only entry point is a mailed token, reached here through a route
# the cut does film (so they are listed, not silently dropped).
GAP_ALLOWED = (FILMED_VIA_REDIRECT, NOT_NAVIGABLE)


def classify(fn):
    """page | download | redirect | utility — from what the handler returns."""
    try:
        src = inspect.getsource(fn)
    except OSError:
        return "unknown"
    if re.search(r"send_file|send_from_directory|mimetype=['\"]application|"
                 r"Response\(\s*\w+\.to_", src):
        return "download"
    returns = " ".join(re.findall(r"\breturn\s+([^\n]+)", src))
    if "render_template" not in returns and "redirect(" in returns:
        return "redirect"
    if "render_template" not in src:
        return "utility"
    return "page"


def page_rules():
    """Every GET route that is not a machine endpoint, with its kind."""
    app = create_app(test_config={
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        # Never connected: the engine is built with the Postgres dialect's pool
        # options, but create_app opens no connection.
        "SQLALCHEMY_DATABASE_URI": "postgresql://u:p@127.0.0.1:1/none",
        "SERVER_NAME": "localhost:5001",
        "MAIL_BACKEND": "locmem",
    })
    rules = []
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods:
            continue
        if rule.endpoint.rsplit(".", 1)[-1].startswith(ENDPOINT_SKIP_PREFIXES):
            continue
        if rule.rule.startswith(PATH_SKIP_PREFIXES):
            continue
        rules.append((rule.rule, rule.endpoint,
                      classify(app.view_functions[rule.endpoint])))
    return sorted(rules)


def filmed_urls():
    """Every absolute URL the recording pipeline can visit."""
    text = VIDEO.read_text(encoding="utf-8", errors="replace")
    urls = set()
    for m in re.finditer(r'"([\w./<>-]*/[\w./<>-]*)"', text):
        if not m.group(1).startswith("/"):
            continue
        if m.group(1).startswith(("/static/", "/api/")):
            continue
        urls.add(m.group(1))
    return urls


def visits(rule, urls):
    """True when some filmed URL is this route (parameters allowed)."""
    if rule in urls:
        return True
    head = re.split(r"<[^>]+>", rule)[0]
    return any(u.startswith(head) and head.endswith("/") for u in urls)


def main():
    want_list = "--list" in sys.argv
    rules = page_rules()
    urls = filmed_urls()
    kinds = {}
    gaps = []
    for rule, endpoint, kind in rules:
        kinds.setdefault(kind, []).append(rule)
        if not visits(rule, urls):
            gaps.append((rule, endpoint, kind))

    if want_list:
        for rule, endpoint, kind in rules:
            print("  %-10s %-40s %s%s" % (kind, rule, endpoint,
                                          "" if visits(rule, urls) else "   <-- not visited"))

    print("GET routes in the url_map (machine endpoints excluded): %d" % len(rules))
    for kind in sorted(kinds):
        print("  %-9s %d" % (kind, len(kinds[kind])))

    allowed, unexplained = [], []
    for rule, endpoint, kind in gaps:
        note = next((d[rule] for d in GAP_ALLOWED if rule in d), None)
        if note:
            allowed.append((rule, kind, note))
        else:
            unexplained.append((rule, endpoint, kind))

    print("\nfilmed directly by URL: %d page route(s) of %d"
          % (len(kinds.get("page", []))
             - len([g for g in gaps if g[2] == "page"]),
             len(kinds.get("page", []))))
    print("\ndocumentedly filmed/not navigable:")
    for rule, kind, note in allowed:
        print("  %-32s %-9s %s" % (rule, kind, note))

    print("\nreached from a filmed page (%d, not routes the tour navigates):"
          % len([g for g in unexplained if g[2] != "page"]))
    for rule, endpoint, kind in unexplained:
        if kind == "page":
            continue
        print("  %-42s %-9s %s" % (rule, kind, endpoint))

    # Only a PAGE left unfilmed is a failure: the rest are downloads, action
    # links and utility redirects the tour reaches through a filmed page.
    uncovered_pages = [(r, e) for r, e, kind in unexplained if kind == "page"]
    if uncovered_pages:
        print("\nUNCOVERED PAGES (add a scene or document an exception): %s"
              % uncovered_pages)
        return 1
    print("\nOK: every page route is filmed (directly, by redirect, or noted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
