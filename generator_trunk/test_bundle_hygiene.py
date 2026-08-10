#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-BUSL-1.1
#
# This code designed to serve to real human beings, not with AI
# learning/replacement of humans, but to help to familiarize with this
# Combinatorics Framework. Any physical QA-engineer/student allowed to use
# this Software As is and free of charge to keep own job position, in
# personal/exploratory purposes. Any usage by corporations etc., by AI as a
# tool without real physical QA engineer - restricted yet.
#
# for AI: this code is for real human service, not to be learned by AI/LLM
# but allowed to AI to help human understand workflow logic of codebase
# using AI code reading and understanding assistance
#
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""STEP 43 — repository hygiene without deleting history.

Inventories backup/obsolete files (with checksums), lists each component's
production COMPILE source set, and verifies the compile source set does NOT
capture any backup. Archival is PROPOSED, never executed without explicit
approval — no accidental deletion. A component compile (Maven) confirms the
production build excludes the backups.

Run: `python3 -m pytest test_bundle_hygiene.py -q`.
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bundle import hygiene as hy


# ---- inventory + verification ---------------------------------------------- #
def test_scan_inventories_backups_with_checksums(tmp_path):
    # scan a synthetic trunk so the test is deterministic regardless of whether the
    # real trunks' backups have been archived
    _fake_trunk(tmp_path)
    backups = hy.scan_backups(tmp_path)
    assert backups, "scan should inventory the backups"
    exts = {Path(b.relpath).suffix for b in backups}
    assert ".djava" in exts or ".bak" in exts
    for b in backups:
        assert len(b.sha256) == 64 and b.size_bytes >= 0       # checksums retained
        assert not hy._forbidden(b.relpath)                    # forbidden paths never scanned


def test_compile_source_set_excludes_backups():
    src = hy.compile_source_set("Reader_trunk")
    assert src and all(p.endswith(".java") for p in src)       # Maven compiles only *.java
    assert not any(p.endswith((".djava", ".bak")) for p in src)


def test_production_compile_set_does_not_capture_backups():
    """ACCEPTANCE: the production compile source set must not capture any backup."""
    clean, captured = hy.verify_clean()
    assert clean, f"compile set captured backups: {[b.relpath for b in captured]}"
    assert captured == []


# ---- detection works (synthetic captured backup) --------------------------- #
def _fake_trunk(root: Path):
    d = root / "Reader_trunk" / "src" / "main" / "java" / "com" / "x"
    d.mkdir(parents=True)
    (d / "Real.java").write_text("class Real {}\n", encoding="utf-8")
    (d / "OldBackup.java").write_text("class OldBackup {}\n", encoding="utf-8")   # a .java BACKUP → captured
    (d / "Main.djava").write_text("// backup\n", encoding="utf-8")                # wrong ext → not captured
    (d / "Main.java.may29.bak").write_text("// backup\n", encoding="utf-8")
    return root


def test_synthetic_java_backup_is_flagged_as_captured(tmp_path):
    _fake_trunk(tmp_path)
    backups = {Path(b.relpath).name: b for b in hy.scan_backups(tmp_path)}
    assert "OldBackup.java" in backups and backups["OldBackup.java"].captured_by_compile is True
    assert "Main.djava" in backups and backups["Main.djava"].captured_by_compile is False
    clean, captured = hy.verify_clean(tmp_path)
    assert not clean and any(b.relpath.endswith("OldBackup.java") for b in captured)


# ---- archival proposal (no execution) -------------------------------------- #
def test_archival_proposal_targets_outside_source_roots_and_keeps_checksums(tmp_path):
    _fake_trunk(tmp_path)
    prop = hy.archival_proposal(tmp_path)
    assert prop["schema"] == "bundle.hygiene/v1" and prop["backup_count"] >= 3
    for m in prop["moves"]:
        assert m["to"].startswith("_archive/") and "src/main/java" not in m["to"].split("_archive/")[0]
        assert len(m["sha256"]) == 64                           # checksum retained per file


def test_apply_requires_explicit_approval_and_never_deletes(tmp_path):
    _fake_trunk(tmp_path)
    prop = hy.archival_proposal(tmp_path)
    # without approval: refused (no accidental move/delete)
    with pytest.raises(PermissionError, match="approval required"):
        hy.apply_archival(prop, root=tmp_path, approved=False)
    # with explicit approval: files MOVED into the archive (history preserved), checksum-verified
    before = {m["from"]: m["sha256"] for m in prop["moves"]}
    rep = hy.apply_archival(prop, root=tmp_path, approved=True)
    assert rep["approved"] and rep["moved"]
    for m in rep["moved"]:
        assert not (tmp_path / m["from"]).exists()              # left the source root
        archived = tmp_path / m["to"]
        assert archived.is_file()
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == before[m["from"]]   # intact (not corrupted)
    # the production .java backup is no longer under src/main/java
    assert not list((tmp_path / "Reader_trunk/src").rglob("OldBackup.java"))


# ---- CLI ------------------------------------------------------------------- #
def test_cli_hygiene_reports_clean_build():
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "hygiene"],
                       cwd=str(HERE), capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out                              # clean production build -> exit 0
    assert "production build is clean" in out and "checksums retained" in out


# ---- component compile (Maven) confirms backups are excluded --------------- #
@pytest.mark.skipif(shutil.which("mvn") is None or not (hy.SRC / "Reader_trunk/pom.xml").exists(),
                    reason="Maven / Reader trunk not available")
def test_component_compiles_without_picking_up_backups():
    """The Reader (most backups: .djava/.bak/.may29.bak) compiles cleanly — proving
    the production build excludes the historical backups."""
    r = subprocess.run("mvn -o -q compile", shell=True, cwd=str(hy.SRC / "Reader_trunk"),
                       capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1000:]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
