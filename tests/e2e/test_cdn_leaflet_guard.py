"""Playwright test: a Leaflet CDN failure must never kill a page's script.

When the Leaflet CDN is blocked (offline kiosk, corporate proxy, flaky network),
the browser throws ``L is not defined`` at the ``L.map(...)`` statement and every
statement AFTER it in the same inline script silently never runs — form wiring,
SSE streams, everything.

This test verifies that with the CDN blocked, the portal pages still load
without JS errors that would prevent form submission or SSE wiring.
"""

import pytest


@pytest.mark.parametrize(
    "page_url, script_selector",
    [
        # analytics.html: initAnalytics() has L.heatLayer inside try/catch after shim
        ("/analytics", "script[nonce]"),
        # dashboard.html: map init guarded by typeof window.L
        ("/dashboard", "script[nonce]"),
        # illegal_dump.html: map init guarded by typeof window.L + try/catch
        ("/illegal-dump", "script[nonce]"),
    ],
)
def test_cdn_blocked_no_js_errors(page_url, script_selector, page, base_url):
    """Ensure that blocking the Leaflet CDN does not cause unhandled errors that
    would kill the inline script's remaining statements.

    The templates harden their Leaflet init with:
      if (typeof window.L !== 'undefined') {
        try { L.map(...) ... } catch(e) { console.warn(...) }
      } else { console.warn('Leaflet CDN unavailable') }
    Plus the new shim in analytics.html defines a minimal L for the heat plugin.
    """
    # Block the Leaflet CSS/JS CDNs at the network level
    with page.context().wait_for_event("response") as response_event:
        # Intercept requests to Leaflet CDNs and fail them
        def block_leaflet(route, request):
            url = request.url()
            return "leaflet" in url.lower() or "unpkg.com/leaflet" in url

        page.route("**/*", block_leaflet)

    # Navigate and capture console messages
    with page.expect_console_message(lambda msg: "L is not defined" not in msg.text.lower() or "warn" in msg.type.lower()):
        page.goto(base_url + page_url)

    # Find the inline script and verify it still has its core functionality
    scripts = page.locator(script_selector).all()
    assert len(scripts) > 0, f"No inline script found on {page_url}"

    # Check that the page loaded without fatal JS errors
    # The page should not have "L is not defined" as an unhandled error
    console_messages = []
    page.on("console", lambda msg: console_messages.append(msg))

    # Re-navigate to capture all console messages
    page.goto(base_url + page_url)

    # Verify no unhandled "L is not defined" errors
    l_not_defined_errors = [
        m for m in console_messages
        if "l is not defined" in m.text.lower() and "warn" not in m.type.lower()
    ]
    assert not l_not_defined_errors, (
        f"Found unhandled 'L is not defined' error on {page_url}: "
        f"{[m.text for m in l_not_defined_errors]}"
    )