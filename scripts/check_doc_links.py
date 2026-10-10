#!/usr/bin/env python3
"""Fail on broken relative links and references to deleted docs.

Documentation drift is silent: when a guide is renamed, split, or retired
(most recently the Cloudflare/Fly.io consolidation — a duplicate under `wiki/`,
three guides under `docs/guides/cloudflare/`, and the root `fly.toml`), every
markdown link and prose reference to the old path keeps pointing at a file that
no longer exists, and nothing in CI notices. This guard notices.

It scans the repository's text files and reports two classes of drift:

1. **Broken relative links** — a markdown link/image (or reference-style
   definition) whose target resolves to no file on disk. External URLs
   (`http(s)://`, `mailto:`, `tel:`), pure anchors (`#…`) and site-absolute app
   routes (`/schedule`) are ignored, as are links written inside fenced or
   inline code.

2. **References to deleted docs** — a prose/backtick/code reference to a
   retired path (`RETIRED_PATHS`), or to any `docs/`, `wiki/` or `.github/`
   markdown path that is not on disk. A few documents whose purpose is to
   *record* the retirement (see `RETIREMENT_NOTES`) are exempt from this class
   only — their links are still checked.

Usage:
    python scripts/check_doc_links.py [root]
    (defaults to the repository root)

Exit codes:
    0  every relative link and doc reference resolves
    1  one or more broken links / deleted-doc references found
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

# Generated, archived, vendored or third-party subtrees: their links are not
# this project's maintained docs, so checking them only adds noise.
SKIP_DIR_NAMES = {
    '.git', 'node_modules', 'venv', '.venv', '__pycache__',
    '_archive', '_qa', '_imgqa', 'test-results', 'playwright-report',
    '.freebuff', 'report', '.kilo',
}
# Vendored agent-skill definitions (they reference reference-files shipped by
# the tooling, not by this repo).
SKIP_SUBTREES = {'.github/skills'}

# File types worth scanning. Markdown carries links; prose references to
# deleted paths can live in any text file, so scan a broad set.
SCAN_SUFFIXES = {
    '.md', '.markdown', '.txt', '.py', '.yml', '.yaml', '.toml',
    '.cfg', '.ini', '.sh', '.js', '.mjs', '.html', '.json',
}

# This guard's own sources quote the retired paths as examples — never scan them.
SELF_FILES = {
    Path(__file__).resolve(),
    (ROOT / 'tests' / 'test_doc_links.py').resolve(),
}

# Paths this repo has retired. Referencing one points readers at a document
# that is gone. Keep the list explicit — it is the record of what was removed.
RETIRED_PATHS = (
    'wiki/CLOUDFLARE_CDN_SETUP.md',   # superseded by docs/CLOUDFLARE_CDN_SETUP.md
    'docs/guides/cloudflare',         # consolidated into docs/CLOUDFLARE_CDN_SETUP.md
    'e2e/example.spec.js',            # Playwright scaffold, replaced by smoke.spec.js
    'fly.toml',                       # Fly.io retired; config archived under _archive/
)

# Documents that intentionally narrate a retirement ("replaces the guides that
# used to live at …") or record an audit finding. They are exempt from the
# deleted-doc reference check ONLY; their markdown links are still validated.
RETIREMENT_NOTES = {
    'docs/CLOUDFLARE_CDN_SETUP.md',
    'docs/SITE_AUDIT_2026-10-03.md',
}

# A markdown inline link or image: [text](target "optional title").
LINK_RE = re.compile(r'!?\[[^\]]*\]\(\s*(?P<target>[^)\s]+)(?:\s+"[^"]*")?\s*\)')
# A reference-style link definition: [label]: target
REF_RE = re.compile(r'^\s{0,3}\[[^\]]+\]:\s*(?P<target>\S+)', re.MULTILINE)
# Fenced code blocks and inline code spans — links inside them are illustrations.
FENCE_RE = re.compile(r'(?ms)^\s*(?:```|~~~).*?^\s*(?:```|~~~)')
INLINE_CODE_RE = re.compile(r'`[^`\n]*`')
# A doc-path token in prose/code: docs/foo.md, wiki/foo.md, .github/foo.md.
DOC_PATH_RE = re.compile(r'(?<![\w/.-])((?:docs|wiki|\.github)/[\w./-]+\.md)')

# Targets that are not repo-relative files.
EXTERNAL_PREFIXES = ('http://', 'https://', 'mailto:', 'tel:', 'data:', 'ftp://', '//', '#')


def _iter_files(root: Path, suffixes):
    """Yield every scannable file under root, skipping generated/vendored dirs."""
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        posix = rel.as_posix()
        if any(posix == sub or posix.startswith(sub + '/') for sub in SKIP_SUBTREES):
            continue
        if path.resolve() in SELF_FILES:
            continue
        yield path


def _strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans, preserving line numbers."""
    text = FENCE_RE.sub(lambda m: '\n' * m.group(0).count('\n'), text)
    return INLINE_CODE_RE.sub(lambda m: ' ' * len(m.group(0)), text)


def _lineno(text: str, pos: int) -> int:
    return text.count('\n', 0, pos) + 1


def _resolve_candidates(target: str, source: Path, root: Path):
    """Return the plausible on-disk locations for a relative link target."""
    path = unquote(target.split('#', 1)[0].split('?', 1)[0])
    if not path:
        return []
    # A markdown link is relative to its own file; many docs here also write
    # repo-root-relative paths, so accept either convention. Drift (the path
    # exists under neither root) is still caught either way.
    return [source.parent / path, root / path]


def find_broken_links(root: Path):
    """Return [(file, lineno, target)] for markdown links that resolve nowhere."""
    hits = []
    for source in _iter_files(root, {'.md', '.markdown'}):
        raw = source.read_text(encoding='utf-8', errors='replace')
        stripped = _strip_code(raw)
        for regex in (LINK_RE, REF_RE):
            for match in regex.finditer(stripped):
                target = match.group('target').strip('<>')
                if not target or target.lower().startswith(EXTERNAL_PREFIXES):
                    continue
                if target.startswith('/'):  # site-absolute app route, not a repo file
                    continue
                candidates = _resolve_candidates(target, source, root)
                if candidates and not any(c.exists() for c in candidates):
                    hits.append((source, _lineno(stripped, match.start()), target))
    return hits


def find_deleted_refs(root: Path):
    """Return [(file, lineno, token)] for references to retired/missing docs."""
    hits = []
    for source in _iter_files(root, SCAN_SUFFIXES):
        rel = source.relative_to(root).as_posix()
        if rel in RETIREMENT_NOTES:
            continue
        text = source.read_text(encoding='utf-8', errors='replace')
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in RETIRED_PATHS:
                if token in line and not _archived_mention(token, line):
                    hits.append((source, lineno, token))
            for token in DOC_PATH_RE.findall(line):
                if not (root / token).exists():
                    hits.append((source, lineno, token))
    return hits


def _archived_mention(token: str, line: str) -> bool:
    """A pointer at the archived copy (``_archive/…``) is legitimate, not drift."""
    return '_archive/' in line


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0]).resolve() if argv else ROOT
    broken = find_broken_links(root)
    deleted = find_deleted_refs(root)
    if not broken and not deleted:
        print(f'OK: no broken relative links or deleted-doc references under {root}')
        return 0
    for path, lineno, target in broken:
        print(f'{path}:{lineno}: broken relative link -> {target}')
    for path, lineno, token in deleted:
        print(f'{path}:{lineno}: reference to deleted/missing doc -> {token}')
    print(f'\n{len(broken)} broken link(s), {len(deleted)} deleted-doc reference(s).')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
