"""CSP gate: templates must not ship inline handlers or un-nonced inline blocks.

Talisman authorises inline <script>/<style> with a per-request nonce
(content_security_policy_nonce_in=['script-src', 'style-src']), and inline event
handlers cannot carry a nonce at all — they are declared as data-sg-* attributes
wired up by static/js/csp-events.js.

Both conventions are invisible to every other test: a template edit that adds
onclick="..." or an un-nonced <script> renders perfectly in a test client and
only breaks in a browser, and it breaks silently (the handler never fires, the
block never executes, the console shows a CSP violation nobody reads). That is
exactly the kind of regression this file exists to catch.

The scans are pure text analysis of app/templates/, so they need no database and
fail fast. The last test renders a real page and proves the nonce in the CSP
header is the nonce in the markup.
"""
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "templates"

SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>", re.I | re.S)
STYLE_TAG_RE = re.compile(r"<style\b[^>]*>", re.I | re.S)
SCRIPT_BODY_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.I | re.S)
STYLE_BODY_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->|\{#.*?#\}", re.S)
TAG_RE = re.compile(r"<[a-zA-Z][a-zA-Z0-9:._-]*\b[^>]*>", re.S)
HANDLER_ATTR_RE = re.compile(r"[\s\"']on([a-z]{3,})\s*=", re.I)
SRC_ATTR_RE = re.compile(r"\bsrc\s*=", re.I)
NONCE_ATTR_RE = re.compile(r"\bnonce\s*=\s*([\"'])(.*?)\1", re.I | re.S)
JS_URL_RE = re.compile(r"\b(?:href|src|action|formaction)\s*=\s*([\"'])\s*javascript:", re.I)

# The only accepted nonce value: the per-request helper. A hardcoded literal
# would not be in the response's policy and the block would be refused.
NONCE_HELPER = "{{ csp_nonce() }}"


def _templates():
    files = sorted(p for p in TEMPLATES.rglob("*.html") if p.is_file())
    assert files, "no templates found under %s" % TEMPLATES
    return files


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _blank(match):
    """Replace a region with spaces, preserving newlines so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))


def _markup_only(text):
    """Template markup with comments and <script>/<style> bodies blanked out.

    Handlers and tags are only meaningful outside those regions: JS/CSS bodies
    legitimately contain the strings "onload=" or "<div>" inside comments and
    string literals.
    """
    text = COMMENT_RE.sub(_blank, text)
    text = SCRIPT_BODY_RE.sub(_blank, text)
    return STYLE_BODY_RE.sub(_blank, text)


def _line(text, offset):
    return text.count("\n", 0, offset) + 1


def _snippet(text, offset, width=70):
    start = text.rfind("\n", 0, offset) + 1
    return text[start:offset + width].strip().replace("\n", " ")[:width]


def test_no_inline_event_handlers():
    """onclick="..." / onload="..." etc. cannot be nonced — they must not exist.

    The CSP-safe form is a data-sg-* attribute handled by csp-events.js.
    """
    offenders = []
    for path in _templates():
        text = _read(path)
        scannable = _markup_only(text)
        for tag in TAG_RE.finditer(scannable):
            for m in HANDLER_ATTR_RE.finditer(tag.group(0)):
                offenders.append("%s:%d  inline %s= attribute: %s"
                                 % (path.relative_to(TEMPLATES.parent.parent),
                                    _line(text, tag.start()), m.group(1).lower(),
                                    _snippet(text, tag.start())))
    assert not offenders, (
        "inline event handlers are blocked by the CSP header and can never fire. "
        "Use a data-sg-* attribute wired in static/js/csp-events.js instead:\n  "
        + "\n  ".join(offenders))


def test_inline_scripts_and_styles_carry_the_nonce():
    """Every inline <script>/<style> must carry the nonce attribute.

    A tag with src= is loaded by host-source and needs no nonce; everything else
    (including JSON-LD data blocks, for consistency) does.
    """
    offenders = []
    for path in _templates():
        text = _read(path)
        rel = path.relative_to(TEMPLATES.parent.parent)
        for tag_re, kind in ((SCRIPT_TAG_RE, "script"), (STYLE_TAG_RE, "style")):
            for tag in tag_re.finditer(text):
                opening = tag.group(0)
                if kind == "script" and SRC_ATTR_RE.search(opening):
                    continue
                if not NONCE_ATTR_RE.search(opening):
                    offenders.append("%s:%d  inline <%s> without nonce: %s"
                                     % (rel, _line(text, tag.start()), kind,
                                        opening.strip()[:80]))
    assert not offenders, (
        "inline script/style blocks are refused without a matching nonce. "
        'Add nonce="%s":\n  ' % NONCE_HELPER + "\n  ".join(offenders))


def test_nonce_always_comes_from_the_per_request_helper():
    """A literal nonce would never appear in the response policy."""
    offenders = []
    for path in _templates():
        text = _read(path)
        rel = path.relative_to(TEMPLATES.parent.parent)
        for m in NONCE_ATTR_RE.finditer(text):
            if m.group(2).strip() != NONCE_HELPER:
                offenders.append("%s:%d  nonce=%s (expected %s)"
                                 % (rel, _line(text, m.start()),
                                    m.group(2).strip()[:60], NONCE_HELPER))
    assert not offenders, ("nonces must be rendered per request:\n  "
                           + "\n  ".join(offenders))


def test_no_javascript_urls():
    """javascript: URLs are a script-injection surface CSP only partly covers."""
    offenders = []
    for path in _templates():
        text = _read(path)
        rel = path.relative_to(TEMPLATES.parent.parent)
        for m in JS_URL_RE.finditer(_markup_only(text)):
            offenders.append("%s:%d  %s" % (rel, _line(text, m.start()),
                                            _snippet(text, m.start())))
    assert not offenders, ("javascript: URLs found:\n  " + "\n  ".join(offenders))


def test_rendered_page_nonce_matches_its_csp_header(client):
    """The end-to-end proof: the policy's nonce is the one in the markup."""
    r = client.get("/")
    assert r.status_code == 200, "homepage returned %s" % r.status_code
    csp = r.headers.get("Content-Security-Policy", "")
    m = re.search(r"'nonce-([A-Za-z0-9+/=_-]+)'", csp)
    assert m, "no per-request nonce in the CSP header: %r" % csp[:300]
    nonce = m.group(1)
    body = r.data.decode("utf-8", "replace")
    assert 'nonce="%s"' % nonce in body, (
        "the rendered page does not carry the header's nonce %r — an inline "
        "block would be refused by the browser" % nonce)
    script_src = re.search(r"script-src([^;]*)", csp)
    assert script_src, "script-src missing from the policy: %r" % csp[:300]
    assert "'unsafe-inline'" not in script_src.group(1), (
        "script-src allows 'unsafe-inline', which voids the nonce: %r"
        % script_src.group(1).strip())
