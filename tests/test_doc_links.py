"""Guard against broken relative links and references to deleted docs.

Docs drift silently: a renamed/split/retired guide leaves every link and prose
reference to the old path dangling (the Cloudflare/Fly.io consolidation is the
most recent example). This test (run in the CI job) fails if the repository
contains such a reference, backed by the same stdlib-only scanner CI uses:
scripts/check_doc_links.py.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = ROOT / 'scripts' / 'check_doc_links.py'


def _load_checker():
    spec = importlib.util.spec_from_file_location('check_doc_links', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def test_no_broken_links_or_deleted_refs_in_repo():
    """Every relative link and doc reference in the repository must resolve."""
    broken = checker.find_broken_links(checker.ROOT)
    deleted = checker.find_deleted_refs(checker.ROOT)
    messages = []
    if broken:
        messages.append(
            'Broken relative links:\n'
            + '\n'.join(f'  {p.relative_to(checker.ROOT)}:{n}: {t}' for p, n, t in broken)
        )
    if deleted:
        messages.append(
            'References to deleted docs:\n'
            + '\n'.join(f'  {p.relative_to(checker.ROOT)}:{n}: {t}' for p, n, t in deleted)
        )
    assert not messages, '\n'.join(messages) + '\n(see scripts/check_doc_links.py)'


def test_detects_broken_relative_link(tmp_path):
    """A markdown link to a missing file must be reported."""
    (tmp_path / 'present.md').write_text('# present\n', encoding='utf-8')
    (tmp_path / 'doc.md').write_text(
        '[ok](present.md) and [gone](missing.md)\n', encoding='utf-8')
    hits = checker.find_broken_links(tmp_path)
    assert [t for _, _, t in hits] == ['missing.md']


def test_ignores_external_anchor_and_site_absolute_links(tmp_path):
    """External URLs, pure anchors and app routes are not repo files."""
    (tmp_path / 'doc.md').write_text(
        '[a](https://example.com/x.md)\n'
        '[b](#local-heading)\n'
        '[c](/schedule)\n'
        '[d](mailto:ci@example.com)\n',
        encoding='utf-8',
    )
    assert checker.find_broken_links(tmp_path) == []


def test_ignores_links_inside_code(tmp_path):
    """A link written inside fenced or inline code is an illustration."""
    (tmp_path / 'doc.md').write_text(
        'Inline `[x](nope.md)` is an example.\n\n'
        '```markdown\n[y](also-missing.md)\n```\n',
        encoding='utf-8',
    )
    assert checker.find_broken_links(tmp_path) == []


def test_detects_reference_to_missing_doc(tmp_path):
    """A prose/backtick reference to a non-existent docs/*.md path is drift."""
    (tmp_path / 'notes.md').write_text(
        'See `docs/GONE.md` for the old setup.\n', encoding='utf-8')
    hits = checker.find_deleted_refs(tmp_path)
    assert [t for _, _, t in hits] == ['docs/GONE.md']


def test_detects_retired_path_reference(tmp_path):
    """A reference to an explicitly retired path is drift."""
    (tmp_path / 'notes.md').write_text(
        'Setup lives in fly.toml at the repo root.\n', encoding='utf-8')
    hits = checker.find_deleted_refs(tmp_path)
    assert any(t == 'fly.toml' for _, _, t in hits)


def test_retirement_notes_file_is_exempt_from_deleted_ref_check(tmp_path):
    """A doc that narrates the retirement may name the retired path."""
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'CLOUDFLARE_CDN_SETUP.md').write_text(
        'Replaces the guide that used to live at `wiki/CLOUDFLARE_CDN_SETUP.md`.\n',
        encoding='utf-8',
    )
    assert checker.find_deleted_refs(tmp_path) == []
