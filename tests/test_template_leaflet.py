"""Regression test: a Leaflet CDN failure must never kill a page's script.

History: several portal pages called ``L.map(...)`` as a top-level statement of
their inline script. When the Leaflet CDN is blocked (offline kiosk, corporate
proxy, flaky network) the browser throws ``L is not defined`` at that statement
and every statement AFTER it in the same inline script silently never runs —
form wiring, SSE streams, everything. worker.html was hardened to guard its
map init:

    if (typeof window.L !== 'undefined') {
        try {
            map = L.map('workerNavMap').setView([...], 14);
            ...
        } catch (e) { /* map optional, page must not die */ }
    }

This test locks that invariant in for every template: any free function
``L.map(`` call in an inline <script> must sit inside a ``try {`` that is
itself inside an ``if (typeof window.L ...) {`` guard (function scopes may
still sit between the call and the try for lazy init patterns). A doctored
script without the guard must make this test fail loudly.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"

SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S)
JINJA_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)


def _mask(text: str) -> str:
    """Blank out comments and string bodies, keep every other char in place
    (so character offsets map 1:1 to the original)."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            j = i
            while j < n and text[j] != "\n":
                out[j] = " "
                j += 1
            i = j
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out[i:end] = " " * (end - i)
            i = end
        elif ch in "'\"":
            quote = ch
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    out[j] = " "
                    out[j + 1] = " " if j + 1 < n else out[j + 1]
                    j += 2
                    continue
                if text[j] == quote:
                    break
                if text[j] != "\n":
                    out[j] = " "
                j += 1
            i = j + 1
        elif ch == "`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    out[j] = " "
                    if j + 1 < n:
                        out[j + 1] = " "
                    j += 2
                    continue
                if text[j] == "`":
                    break
                if text[j] != "\n":
                    out[j] = " "
                j += 1
            i = j + 1
        else:
            i += 1
    return "".join(out)


def _prev_word(masked: str, pos: int) -> str:
    """Identifier/keyword (last token) immediately before pos."""
    m = re.search(r"([A-Za-z_$][\w$]*)\s*$", masked[:pos])
    return m.group(1) if m else ""


def _paren_match(masked: str) -> dict[int, int]:
    """Map each ``)`` offset to its matching ``(`` offset in masked text."""
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for idx, ch in enumerate(masked):
        if ch == "(":
            stack.append(idx)
        elif ch == ")" and stack:
            pairs[idx] = stack.pop()
    return pairs


def inline_scripts(path: Path) -> list[str]:
    """The inline (non-src, non-JSON) script bodies of one template, with
    Jinja expressions and statements blanked out for JS scanning."""
    text = path.read_text(encoding="utf-8")
    scripts = []
    for attrs, body in SCRIPT_RE.findall(text):
        if re.search(r'\bsrc\s*=', attrs) or 'application/json' in attrs:
            continue
        scripts.append(JINJA_RE.sub("'x'", body))
    return scripts


def lmap_guard_problems(scripts: list[str]) -> list[str]:
    """Return human-readable violations for one script list."""
    problems = []
    for i, js in enumerate(scripts, 1):
        masked = _mask(JINJA_RE.sub("'x'", js))
        pairs = _paren_match(masked)
        stack: list[str] = []          # scope kinds, outer→inner
        guard_stack: list[bool] = []   # parallel: is this scope a guard block
        scopes: list[tuple[int, int]] = []  # (open offset, ) to pop
        idx = 0
        snapshot_events: list[tuple[int, tuple]] = []
        match_ranges = [m.start() for m in re.finditer(r"\bL\.map\(", masked)]
        while idx < len(masked):
            ch = masked[idx]
            if ch == "{":
                tail = masked[max(0, idx - 12):idx]
                m = re.search(r"(try|catch|else|function)\s*$|=>\s*$|\)\s*$|([A-Za-z_$][\w$]*)\s*$", tail)
                kind, is_guard = "object", False
                if m and m.group(1):
                    kind = {"try": "try", "catch": "catch", "else": "else",
                            "function": "function"}[m.group(1)]
                elif m and m.group(0).endswith("=>"):
                    kind = "function"
                elif m and re.search(r"\)\s*$", tail):
                    # a block opened by ``(cond) {``: find the ')' just before
                    cond_open = -1
                    c = idx - 1
                    while c >= 0 and masked[c].isspace():
                        c -= 1
                    if c >= 0 and masked[c] == ")":
                        cond_open = pairs.get(c, -1)
                    if cond_open != -1:
                        cond = masked[cond_open:idx]
                        name = _prev_word(masked, cond_open)
                        back = _prev_word(masked, cond_open - len(name)) if name else ""
                        if name == "if" and re.search(r"typeof\s+(?:window\.)?L\b", cond):
                            kind, is_guard = "guard", True
                        elif back == "function":
                            kind = "function"     # `function name() {`
                    if kind == "object":
                        kind = "block"
                elif m:                        # word directly before '{'
                    words = re.findall(r"[A-Za-z_$][\w$]*", masked[max(0, idx - 40):idx])
                    if len(words) >= 2 and words[-2] == "function":
                        kind = "function"       # named function declaration
                stack.append(kind)
                guard_stack.append(is_guard)
                scopes.append((idx, None))
            elif ch == "}":
                if stack: stack.pop(); guard_stack.pop(); scopes.pop()
                else: break  # unbalanced; bail out of this script
            if match_ranges:
                for p in match_ranges:
                    if p == idx:
                        snapshot_events.append((p, tuple(enumerate(reversed(stack)))))
                match_ranges = [p for p in match_ranges if p != idx]
            idx += 1
        for p, snap in snapshot_events:
            nl = masked[:p].rfind("\n")
            line = masked[:p].count("\n") + 1
            # find first relevant scope walking innermost→outermost
            seen_try = ok = False
            for _depth, kind in snap:
                if kind == "catch":
                    break
                if kind == "try":
                    seen_try = True
                elif kind == "guard":
                    ok = seen_try
                    break
                elif kind == "function":
                    pass          # lazy-in-function patterns stay acceptable
                elif kind in ("block", "object", "else"):
                    break         # an unguarded boundary swallowed the try
            if not ok:
                problems.append(
                    f"script {i}, line {line}: L.map( call is not inside a "
                    f"guarded try ({' > '.join(reversed([kind for _, kind in snap]))})"
                )
    return problems


def _template_files() -> list[Path]:
    import os

    out = []
    for base, _dirs, files in os.walk(TEMPLATES):
        for f in files:
            if f.endswith(".html"):
                out.append(Path(base) / f)
    return sorted(out)


def test_no_unguarded_lmap_calls():
    """Every L.map( in every template's inline script must be CDN-guarded."""
    problems = []
    for path in _template_files():
        scripts = inline_scripts(path)
        for prob in lmap_guard_problems(scripts):
            problems.append(f"{path.name}: {prob}")
    if problems:
        # Print the accepted guard pattern so the fix is one copy away.
        pattern = (
            "    if (typeof window.L !== 'undefined') {\n"
            "        try {\n"
            "            map = L.map('<container>').setView([...], zoom);\n"
            "            /* tile layers / markers at load time go here too */\n"
            "        } catch (e) { console.warn('map init failed (no Leaflet?):', e); }\n"
            "    }\n"
        )
        raise AssertionError(
            "Unguarded L.map( call(s) found - a Leaflet CDN failure would "
            "silently kill the page's inline script.\nAccepted pattern:\n"
            f"{pattern}\n" + "\n".join(problems))


def test_test_catches_doctored_unguarded_call():
    """The scan itself is load-bearing: a removed guard must be detected."""
    doctored = ("let map = L.map('x').setView([1, 2], 3);"
                "document.getElementById('x').textContent = 'ok';")
    problems = lmap_guard_problems([doctored])
    assert problems and "not inside a guarded try" in problems[0]
    # ...and the accepted worker.html-style pattern must PASS the scan.
    guarded = ("if (typeof window.L !== 'undefined') {"
               "  try {"
               "    map = L.map('x').setView([1, 2], 3);"
               "  } catch (e) { }"
               "}")
    assert not lmap_guard_problems([guarded])


def test_real_files_scan_without_crash():
    for path in _template_files():
        assert isinstance(lmap_guard_problems(inline_scripts(path)), list)
