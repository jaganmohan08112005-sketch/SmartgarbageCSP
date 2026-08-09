"""Lighthouse-style mobile fold check.

The audits repeatedly flagged the homepage hero: on a phone, the primary
resident action ("Check Today's Pickup Schedule") can land below the fold,
so residents arrive and have to scroll to find the one thing they came for.
This test measures the REAL rendered layout — headless Chromium at a
375×667 viewport (the classic small-phone size) — and asserts the primary
CTA is fully visible in the first screen. A DOM-order or byte-offset
heuristic cannot catch a padding/typography regression that pushes the
button down; only a layout engine can.

The measurement waits for document.fonts.ready first: the H1 above the CTA
wraps according to font metrics, so the button's vertical position must be
read at the final web-font layout, not the fallback-font pass.
"""
import pytest
from playwright.sync_api import expect

# Classic small-phone viewport (CSS pixels). 667px height is the iPhone SE/
# 8 class — the strictest common case for "above the fold".
MOBILE_VIEWPORT = {"width": 375, "height": 667}

# The primary CTA is the one element the hero compaction exists to protect.
PRIMARY_CTA = "a.sg-hero-primary"


@pytest.fixture
def mobile_page(browser, live_server_url):
    """A fresh context at the mobile viewport (the shared `page` fixture is
    desktop 1280×900 — this test needs the phone size)."""
    context = browser.new_context(base_url=live_server_url,
                                  viewport=MOBILE_VIEWPORT)
    page = context.new_page()
    yield page
    context.close()


def _cta_box(page):
    cta = page.locator(PRIMARY_CTA)
    expect(cta).to_be_visible()
    # Final layout: wait for web fonts so text wrapping above the CTA is
    # settled before measuring (page.evaluate awaits the promise).
    page.evaluate("document.fonts.ready")
    box = cta.bounding_box()
    assert box is not None, "primary CTA has no rendered bounding box"
    return box, page.evaluate("window.innerHeight")


def test_primary_cta_fully_above_the_fold_at_375px(mobile_page):
    mobile_page.goto("/")

    box, vh = _cta_box(mobile_page)
    bottom = box["y"] + box["height"]

    assert box["y"] >= 0, (
        f"primary CTA starts above the viewport top (y={box['y']:.1f}px) — "
        f"something overlaps or offsets the hero"
    )
    assert bottom <= vh + 0.5, (
        f"primary CTA is NOT above the fold at 375×667: its bottom is at "
        f"{bottom:.1f}px but the viewport is {vh}px tall. The hero needs "
        f"compaction (padding / H1 size / paragraph size) so the main "
        f"resident action sits in the first phone screen."
    )


def test_primary_cta_bottom_margin_from_fold(mobile_page):
    """Regression guard with a little headroom: the CTA should sit at least
    ~24px above the fold, not be right at the edge (a few px of font-metric
    drift between environments must not flip the fold test)."""
    mobile_page.goto("/")

    box, vh = _cta_box(mobile_page)
    gap = vh - (box["y"] + box["height"])
    assert gap >= 24, (
        f"primary CTA only {gap:.1f}px above the fold — too tight for "
        f"cross-environment font-metric drift; compact the hero further"
    )
