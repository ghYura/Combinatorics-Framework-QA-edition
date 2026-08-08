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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Targeted tests for bundle.runs: run ID minting/validation, run-directory
layout creation, collision handling, and redacted run.json inspection
(run: `python3 test_bundle_runs.py`)."""
import tempfile
from pathlib import Path

from bundle.errors import BundleError
from bundle.jsonio import read_json, REDACTED
from bundle.models import RunStatus, run_manifest_from_dict
from bundle.runs import create_run, file_sha256, generate_run_id, RunCollisionError, RunLayout


def test_generate_run_id_accepts_valid_and_rejects_invalid():
    assert generate_run_id("secure_pipeline-2026-06-07") == "secure_pipeline-2026-06-07"
    for bad in ("../escape", "has space", "", "/abs/path", "trailing/slash/"):
        try:
            generate_run_id(bad or None if bad == "" else bad)
        except BundleError:
            continue
        if bad == "":
            continue                                  # empty -> auto-mint, not an error
        raise AssertionError(f"expected rejection for run id {bad!r}")


def test_generate_run_id_auto_mint_is_unique_and_safe():
    a, b = generate_run_id(), generate_run_id()
    assert a != b
    for rid in (a, b):
        assert generate_run_id(rid) == rid             # round-trips through validation
        assert "/" not in rid and " " not in rid


def test_create_run_builds_layout_and_redacted_manifest():
    with tempfile.TemporaryDirectory() as d:
        runs_root = Path(d) / "runs"
        spec = Path(d) / "spec.toml"
        spec.write_text("title = 'x'\n", encoding="utf-8")
        layout = create_run(
            runs_root=runs_root, db_name="secure_pipeline", spec_path=spec,
            spec_sha256=file_sha256(spec), mode="verdict", goals="security_failures:max",
            scratch_root=Path(d) / "scratch", run_id="secure_pipeline-smoke",
            settings={"db.password": "hunter2-supersecret", "main_port": 5433},
        )
        assert isinstance(layout, RunLayout)
        assert layout.root.is_dir()
        for sub in ("stages", "logs", "workbooks", "candidates", "handoff", "metrics", "reports"):
            assert (layout.root / sub).is_dir(), f"missing layout dir: {sub}"

        on_disk = read_json(layout.manifest_path)
        raw_text = layout.manifest_path.read_text(encoding="utf-8")
        assert "hunter2-supersecret" not in raw_text     # secret VALUE never reaches disk (key name may legitimately contain "password")
        assert on_disk["settings"]["db.password"] == REDACTED
        assert on_disk["settings"]["main_port"] == 5433
        assert on_disk["run_id"] == "secure_pipeline-smoke"
        assert on_disk["db_name"] == "secure_pipeline"  # existing CLI DB-name choice still flows through
        assert on_disk["status"] == RunStatus.PENDING.value

        manifest = run_manifest_from_dict(on_disk)       # typed reader round-trips the redacted JSON
        assert manifest.run_id == "secure_pipeline-smoke"
        assert manifest.status is RunStatus.PENDING

        state = read_json(layout.state_path)
        assert state["run_id"] == "secure_pipeline-smoke" and state["stages"] == {}


def test_create_run_collision_fails_closed_without_overwrite():
    with tempfile.TemporaryDirectory() as d:
        runs_root = Path(d) / "runs"
        spec = Path(d) / "spec.toml"
        spec.write_text("title = 'x'\n", encoding="utf-8")
        kwargs = dict(runs_root=runs_root, db_name="secure_pipeline", spec_path=spec,
                      spec_sha256=file_sha256(spec), mode="verdict", goals="",
                      scratch_root=Path(d) / "scratch", run_id="dup-run")
        layout = create_run(settings={"db.password": "first"}, **kwargs)
        before = layout.manifest_path.read_text(encoding="utf-8")

        try:
            create_run(settings={"db.password": "second"}, **kwargs)
        except RunCollisionError:
            pass
        else:
            raise AssertionError("expected RunCollisionError on duplicate run ID")

        after = layout.manifest_path.read_text(encoding="utf-8")
        assert before == after                          # existing run.json untouched by the collision attempt


def test_file_sha256_is_stable_and_content_sensitive():
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.toml"; a.write_text("same\n", encoding="utf-8")
        b = Path(d) / "b.toml"; b.write_text("same\n", encoding="utf-8")
        c = Path(d) / "c.toml"; c.write_text("different\n", encoding="utf-8")
        assert file_sha256(a) == file_sha256(b)
        assert file_sha256(a) != file_sha256(c)
        assert len(file_sha256(a)) == 64


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
