"""The doc-link reference scan must stay bounded so the suite cannot hang.

`scripts/check_doc_links.py` reads every text file under the repo root to look
for references to deleted docs, and it skips generated directories by name
(`SKIP_DIR_NAMES`). It has no size cap, so any large text file left in the tree
by a tool is read line by line with no way out.

On 2026-10-11 `tests/test_doc_links.py::test_no_broken_links_or_deleted_refs_in_repo`
hit the 180s per-test timeout inside `find_deleted_refs()` -> `read_text()`,
failing the run. The generated Lighthouse/axe reports under `audit/out/` are the
largest scannable text files on a developer's machine (~9 MB total), they are
git-ignored, and they can never carry a doc reference worth validating, so
`audit/out` is now skipped by name. This test pins that skip and also asserts
the scan stays bounded if the tree later grows another large text file.
"""
import os
from pathlib import Path

import scripts.check_doc_links as cdl

ROOT = Path(cdl.ROOT)
AUDIT_OUT = ROOT / "audit" / "out"
MAX_SCAN_BYTES = 1_000_000


def test_audit_output_is_not_scanned():
    """Generated Lighthouse/axe reports are git-ignored and never scanned."""
    if "audit" not in cdl.SKIP_DIR_NAMES:
        raise AssertionError(
            "'audit' must be in SKIP_DIR_NAMES: the generated reports under "
            "audit/out/ are git-ignored, so a reference inside them is not a "
            "reference in the repo, and they are the largest text files a "
            "developer machine has.")
    # Prove the guard reaches the real subtree, not just the constant.
    if not AUDIT_OUT.is_dir():
        return  # nothing generated on this machine; the constant still guards
    scanned = list(cdl._iter_files(ROOT, cdl.SCAN_SUFFIXES))
    inside = [p for p in scanned if AUDIT_OUT in p.parents or p.parent == AUDIT_OUT]
    assert not inside, "audit/out files were yielded by the scan: %s" % inside[:5]


def test_scan_skips_every_declared_subtree():
    """Every name in SKIP_DIR_NAMES really suppresses its subtree.

    Both sides come from ONE walk of the tree: the directories that carry a
    skipped name, and the files the scan yields. Re-walking per name was O(tree)
    per entry and blew the per-test timeout on a checkout with a `.git` and a
    `.kilo` worktree in it.
    """
    present = {}
    for dirpath, dirnames, _ in os.walk(ROOT):
        for name in dirnames:
            if name in cdl.SKIP_DIR_NAMES:
                present.setdefault(name, Path(dirpath) / name)
    assert present, ("none of the declared skipped directories exist in this "
                     "checkout, so this guard proves nothing")

    offenders = []
    for path in cdl._iter_files(ROOT, cdl.SCAN_SUFFIXES):
        for name, skipped in present.items():
            if path == skipped or skipped in path.parents:
                offenders.append((name, str(path)))
    assert not offenders, "directories still scanned: %s" % offenders


def test_iter_files_ignores_oversized_inputs(tmp_path):
    """A single huge text file must not be handed to a line-by-line reader.

    The checker walks the real repo tree, so the only defence against a future
    multi-megabyte text file is size-aware iteration. If the helper grows a cap,
    this passes; until then it documents the contract by asserting the cap
    constant is at least declared and the scan is not unbounded by default.
    """
    big = tmp_path / "huge.json"
    big.write_bytes(b"0" * (MAX_SCAN_BYTES + 1))
    small = tmp_path / "small.md"
    small.write_text("# ok\n")

    capped = getattr(cdl, "MAX_SCAN_BYTES", None)
    if capped is None:
        # No cap implemented yet: the size check below is the regression we
        # want, so fail with an actionable message rather than skip.
        raise AssertionError(
            "check_doc_links._iter_files has no size cap; a large text file "
            "left by a tool makes the doc-link test hang until its timeout. "
            "Add MAX_SCAN_BYTES and skip larger files.")
    assert capped < 10_000_000, "cap %d bytes is too generous to bound the scan" % capped
    yielded = list(cdl._iter_files(tmp_path, {".md", ".json"}))
    assert small in yielded, "the small file must still be scanned"
    assert big not in yielded, "the oversized file must be skipped"
