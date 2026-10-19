#!/usr/bin/env python3
"""Rebuild the R24 source-code zip from a curated manifest.

The manifest is the previous curated list, refreshed:
  * entries that no longer exist on disk are dropped;
  * the report binaries that duplicate separately-submitted deliverables
    (BOOK pdf, softcopy docx, deck pptx) are excluded - they are delivered in
    `submission/`, not inside the code archive;
  * new code/docs files (CI composite action, video pipeline sources) are added.

Usage:
    python submission/_scratch/build_code_zip.py [--write]
"""
from __future__ import annotations

import os
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MANIFEST = os.path.join(ROOT, "submission", "_scratch", "code_list.txt")
ZIP = os.path.join(ROOT, "submission", "code", "SmartGarbage_Source_Code.zip")

# Duplicated deliverables: shipped separately in submission/, never in the zip.
DROP = {
    "report/DOCUMENTATION_UPDATED.docx",
    "report/DOCUMENTATION_UPDATED.pdf",
    "report/DOCUMENT_FINAL.pptx",
}
# Sources created after the manifest was captured.
ADD = [
    ".github/actions/boot-local-stack/action.yml",
    "report/video/_make_video_live.py",
    "report/video/DEMO_VIDEO_SCRIPT.md",
    "report/video/VIDEO_PRODUCTION_BLUEPRINT.md",
    # Added with the web-push migration fix and the full-coverage tour recorder.
    "migrations/versions/p3q4r5s6t7u8_add_missing_notification_preference_.py",
    "tests/test_migration_coverage.py",
    "tests/test_template_csp.py",
    "report/video/_probe_pages.py",
    "report/video/_probe_new_scenes.py",
    # Added with the bounded doc-link scan and the tour verifier the recording
    # checklist tells a reviewer to run, plus the encode-size measurement that
    # justifies the cut's CRF/preset choice.
    "tests/test_doc_link_scan_bounded.py",
    "report/video/_verify_video.py",
    "report/video/_probe_encode_size.py",
    "report/video/_probe_route_coverage.py",
    # The narration generator: the committed SAPI/Zira TTS script (31 scene
    # voices) that regenerates the walkthrough audio on any Windows box,
    # without needing the Playwright recorder. It was tracked in 1bc9dba but
    # missing from the manifest, so the shipped audio pipeline was not fully
    # reproducible from the zip.
    "report/video/_video_live/tts.ps1",
    # Sidecar captions: the SRT/WebVTT generator that captions the shipped
    # demo video's narration in English and Telugu without burning any text
    # into the picture, plus its timing-model test suite.
    "report/video/_make_subtitles.py",
    "tests/test_make_subtitles.py",
    # The local-Postgres harness family (audit §2.1/§5.3): the archive ships
    # run_pg_suite.py and scripts/run_local_stack.py, and both import these —
    # without them the delivered suite runner and stack are unrunnable.
    "scripts/local_pg.py",
    "tests/test_local_pg_helper.py",
    # The stack-readiness contract the stack script and the CI composite
    # action both consume, and the sqlite3-binding guard the CI lint job runs.
    "scripts/stack_readiness.py",
    "scripts/check_sqlite_adapters.py",
    "tests/test_no_unadapted_sqlite_bindings.py",
    # The subtitle burner (audit §2.2) and the audit itself (audit docs ship
    # by precedent: SITE_AUDIT_2026-10-03.md is already in the manifest).
    "report/video/_burn_subtitles.py",
    "docs/PROJECT_AUDIT.md",
    # DECISION (audit §2.3): docs/INSPECTION_REPORT.md stays EXCLUDED — it is
    # untracked and superseded by docs/PROJECT_AUDIT.md.
]
FORBIDDEN = ("venv/", "node_modules/", "audit/out/", "submission/")


def forbidden(path: str) -> bool:
    if any(b in path for b in FORBIDDEN):
        return True
    base = os.path.basename(path)
    # real secrets are never allowed; the documented example file is fine
    return (base == ".env" or base.startswith(".env.")) and base != ".env.example"


def main():
    write = "--write" in sys.argv
    old = [l.strip().replace("\r", "") for l in open(MANIFEST, encoding="utf-8") if l.strip()]
    kept, dropped_missing, dropped_dup = [], [], []
    for f in old:
        if f in DROP:
            dropped_dup.append(f)
            continue
        if not os.path.exists(os.path.join(ROOT, f)):
            dropped_missing.append(f)
            continue
        kept.append(f)
    added = [f for f in ADD if os.path.exists(os.path.join(ROOT, f)) and f not in kept]
    manifest = kept + added

    bad = [f for f in manifest if forbidden(f)]
    if bad:
        raise SystemExit(f"manifest contains forbidden paths: {bad}")

    print(f"kept {len(kept)} · dropped missing {len(dropped_missing)} · dropped duplicates {len(dropped_dup)} · added {len(added)}")
    for f in dropped_missing:
        print("   -missing  ", f)
    for f in dropped_dup:
        print("   -duplicate", f)
    for f in added:
        print("   +added    ", f)

    if write:
        with open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(manifest))
        tmp = ZIP + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for f in manifest:
                zf.write(os.path.join(ROOT, f), f)
        os.replace(tmp, ZIP)
        size = os.path.getsize(ZIP)
        with zipfile.ZipFile(ZIP) as zf:
            names = zf.namelist()
        print(f"\nWROTE {ZIP}\n  {len(names)} files, {size/1048576:.1f} MB")
        assert len(names) == len(manifest), (len(names), len(manifest))
        assert "app/static/js/csp-events.js" in names
        assert not any(n in DROP for n in names)
        assert not any(n.startswith("submission/") for n in names)
        print("  verify: csp-events.js present, deliverables absent, count matches manifest")


if __name__ == "__main__":
    main()
