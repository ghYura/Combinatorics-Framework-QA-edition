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

"""Targeted tests for `bundle cleanup` (STEP 25): the dry-run inventory must
never mutate state, real cleanup must stay inside the run root (no path-
traversal/symlink escape) and refuse a DB-name mismatch, and its action log
must survive the very deletion it records (run:
`python3 -m pytest test_bundle_cleanup.py -q`)."""
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from bundle import cleanup
from bundle.cleanup import (
    CleanupError,
    delete_run,
    format_cleanup_report,
    scan_run,
)
from bundle.config import BundleConfig
from bundle.jsonio import read_json, write_json_atomic
from bundle.models import RUN_SCHEMA, RunManifest, RunStatus
from bundle.runs import RunLayout

CFG = BundleConfig(results_db_host="db.invalid", results_db_port=5432,
                   results_db_user="postgres", results_db_password="")


def _build_run(d, *, run_id="demo-run", db_name="demo", start=None):
    root = Path(d) / "scratch" / "demo" / "runs" / run_id
    (root / "stages").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "handshake" / "resultsDbURL").mkdir(parents=True)
    layout = RunLayout(run_id=run_id, root=root, manifest_path=root / "run.json", state_path=root / "state.json")

    start = start or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    manifest = RunManifest(
        schema=RUN_SCHEMA, run_id=run_id, status=RunStatus.SUCCEEDED, db_name=db_name,
        spec_path=str(Path(d) / "spec.toml"), spec_sha256="x" * 64, spec_version="v1",
        mode="verdict", goals="", start=start,
        scratch_root=str(Path(d) / "scratch" / "demo"), settings={})
    write_json_atomic(layout.manifest_path, manifest)
    write_json_atomic(layout.state_path, {"schema": RUN_SCHEMA, "run_id": run_id,
                                           "status": RunStatus.SUCCEEDED.value, "stages": {}})
    (root / "logs" / "reader.log").write_text("hello\nworld\n", encoding="utf-8")
    (root / "candidates_note.txt").write_bytes(b"x" * 100)
    # A run-private "temporary credentials" file (STEP 14 action 7): the
    # templated `fw.properties`/`resultsDbURL.properties` shape -- a
    # secret-shaped key with a non-empty value.
    (root / "handshake" / "resultsDbURL" / "resultsDbURL.properties").write_text(
        "db.host=127.0.0.1\nresults.db.password=hunter2\nhibernate.connection.url=jdbc:postgresql://x/y\n",
        encoding="utf-8")
    return layout, manifest


def _fake_psql(count):
    return MagicMock(side_effect=lambda _port, _db, _sql, **_kw: (str(count), 0))


# --------------------------------- dry-run scan ------------------------------- #
def test_scan_run_reports_inventory_without_changing_state():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d)
        before = {p: (p.stat().st_mtime_ns, p.read_bytes())
                  for p in layout.root.rglob("*") if p.is_file()}

        with patch.object(cleanup, "psql", _fake_psql(7)):
            report = scan_run(layout, manifest, CFG, retention_seconds=1800.0)

        assert report.run_id == "demo-run"
        assert report.file_count == len(before)
        assert report.total_bytes == sum(len(b) for _, b in before.values())
        assert report.db_name == "demo"
        assert report.db_name_matches_manifest is True
        assert report.results_v2_rows == 7
        assert report.age_seconds is not None and report.age_seconds >= 3000  # ~1h old
        assert report.retention_seconds == 1800.0
        assert report.retention_eligible is True  # older than the 30-minute threshold
        assert len(report.credential_files) == 1
        assert report.credential_files[0].key == "results.db.password"
        assert "resultsDbURL.properties" in report.credential_files[0].path

        # Dry-run must be a pure read: every file is byte-for-byte and
        # mtime-for-mtime identical (acceptance: "Dry-run не меняет state").
        after = {p: (p.stat().st_mtime_ns, p.read_bytes())
                 for p in layout.root.rglob("*") if p.is_file()}
        assert after == before

        text = format_cleanup_report(report)
        assert "demo-run" in text and "results.db.password" in text and "eligible for cleanup" in text


def test_scan_run_skips_db_row_count_on_name_mismatch():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d, db_name="demo")
        with patch.object(cleanup, "psql", _fake_psql(99)) as fake:
            report = scan_run(layout, manifest, CFG, db="some_other_db")
            fake.assert_not_called()

        assert report.db_name == "some_other_db"
        assert report.db_name_matches_manifest is False
        assert report.results_v2_rows is None


def test_scan_run_reports_symlinks_without_following_or_counting_them():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d)
        outside = Path(d) / "outside.txt"
        outside.write_text("do not touch", encoding="utf-8")
        link = layout.root / "escape_link.txt"
        link.symlink_to(outside)

        with patch.object(cleanup, "psql", _fake_psql(0)):
            report = scan_run(layout, manifest, CFG)

        assert str(link) in report.skipped_symlinks
        assert all(str(link) != c.path for c in report.credential_files)
        # The symlink doesn't get walked-through and counted as a (huge or
        # tiny) regular file -- only real files under the run root are.
        real_files = [p for p in layout.root.rglob("*") if p.is_file() and not p.is_symlink()]
        assert report.file_count == len(real_files)


# -------------------------------- real cleanup -------------------------------- #
def test_delete_run_refuses_db_name_mismatch_and_deletes_nothing():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d, db_name="demo")
        with patch.object(cleanup, "psql", _fake_psql(0)) as fake:
            try:
                delete_run(layout, manifest, CFG, db="not_demo")
                assert False, "expected CleanupError"
            except CleanupError as exc:
                assert "does not match run manifest" in str(exc)
            fake.assert_not_called()
        assert layout.root.is_dir()
        assert layout.manifest_path.is_file()


def test_delete_run_refuses_a_run_root_that_fails_the_safety_check():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d, run_id="demo-run")
        # Construct a layout whose root no longer ends in its own run ID --
        # exactly the shape a layout-resolution bug could produce; this must
        # be refused before anything is ever touched (acceptance: "Path
        # traversal/symlink escape blocked" / "Никогда не удалять path вне
        # run root").
        wrong = RunLayout(run_id="demo-run", root=layout.root.parent,
                          manifest_path=layout.root.parent / "run.json",
                          state_path=layout.root.parent / "state.json")
        with patch.object(cleanup, "psql", _fake_psql(0)) as fake:
            try:
                delete_run(wrong, manifest, CFG)
                assert False, "expected CleanupError"
            except CleanupError as exc:
                assert "refusing to delete" in str(exc)
            fake.assert_not_called()
        assert layout.root.is_dir()



def test_delete_run_rejects_symlinked_root_before_db_action():
    with tempfile.TemporaryDirectory() as d:
        real_layout, manifest = _build_run(d)
        link = Path(d) / "links" / real_layout.run_id
        link.parent.mkdir()
        link.symlink_to(real_layout.root, target_is_directory=True)
        linked_layout = RunLayout(run_id=real_layout.run_id, root=link,
                                  manifest_path=link / "run.json", state_path=link / "state.json")

        with patch.object(cleanup, "psql", _fake_psql(0)) as fake:
            try:
                delete_run(linked_layout, manifest, CFG)
                assert False, "expected CleanupError"
            except CleanupError as exc:
                assert "symlink" in str(exc)
            fake.assert_not_called()
        assert real_layout.root.is_dir()

def test_delete_run_removes_tree_db_rows_and_writes_surviving_log():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d)
        outside = Path(d) / "outside.txt"
        outside.write_text("do not touch", encoding="utf-8")
        (layout.root / "escape_link.txt").symlink_to(outside)
        expected_files = sum(1 for p in layout.root.rglob("*") if p.is_file() and not p.is_symlink())
        expected_bytes = sum(p.stat().st_size for p in layout.root.rglob("*")
                             if p.is_file() and not p.is_symlink())

        with patch.object(cleanup, "psql", _fake_psql(3)):
            log, log_path = delete_run(layout, manifest, CFG)

        assert not layout.root.exists(), "the run directory must be gone"
        assert outside.is_file() and outside.read_text() == "do not touch", \
            "a symlink inside the run root must never delete its outside target"

        assert log.run_id == "demo-run"
        assert log.removed_files == expected_files
        assert log.removed_bytes == expected_bytes
        assert log.deleted_results_v2_rows == 3
        assert log.db_name == "demo"
        assert log.skipped_symlinks == (str(layout.root / "escape_link.txt"),)

        # The action log itself must survive the deletion it documents
        # (acceptance/action 6: "Cleanup action log записывается").
        assert log_path.parent == layout.root.parent
        assert log_path.is_file()
        on_disk = read_json(log_path)
        assert on_disk["run_id"] == "demo-run"
        assert on_disk["removed_files"] == expected_files
        assert on_disk["deleted_results_v2_rows"] == 3


def test_delete_run_skips_db_cleanup_when_disabled():
    with tempfile.TemporaryDirectory() as d:
        layout, manifest = _build_run(d)
        with patch.object(cleanup, "psql", _fake_psql(123)) as fake:
            log, _ = delete_run(layout, manifest, CFG, delete_db_rows=False)
            fake.assert_not_called()
        assert log.deleted_results_v2_rows is None
