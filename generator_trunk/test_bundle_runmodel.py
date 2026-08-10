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

"""Targeted tests for bundle.models / bundle.jsonio: round-trip, atomic JSON
writer, and secret redaction (run: `python3 test_bundle_runmodel.py`)."""
import json
import tempfile
from pathlib import Path

from bundle.jsonio import read_json, redact, write_json_atomic, REDACTED
from bundle.models import (
    ArtifactRef,
    CountObservation,
    RUN_SCHEMA,
    RunManifest,
    RunStatus,
    SchemaError,
    STAGE_RESULT_SCHEMA,
    StageResult,
    StageStatus,
    run_manifest_from_dict,
    stage_result_from_dict,
    to_dict,
)


def _sample_stage_result() -> StageResult:
    return StageResult(
        schema=STAGE_RESULT_SCHEMA,
        stage="core",
        status=StageStatus.SUCCEEDED,
        start="2026-06-07T00:00:00Z",
        end="2026-06-07T00:01:00Z",
        duration_seconds=60.0,
        exit_code=0,
        log_path="/tmp/core.log",
        counts=(CountObservation(name="fw_final", expected=96, actual=96),),
        warnings=("note",),
        errors=(),
        artifacts=(ArtifactRef(kind="log", path="/tmp/core.log", bytes=123, sha256="abc"),),
    )


def _sample_run_manifest() -> RunManifest:
    return RunManifest(
        schema=RUN_SCHEMA,
        run_id="secure_pipeline-20260607-abcd",
        status=RunStatus.RUNNING,
        db_name="secure_pipeline",
        spec_path="/specs/secure_pipeline.toml",
        spec_sha256="deadbeef",
        mode="verdict",
        goals="security_failures:max",
        start="2026-06-07T00:00:00Z",
        scratch_root="/tmp/fw_work/secure_pipeline",
        settings={"db.password": "pass", "main_port": 5433},
    )


def test_stage_result_round_trips_through_json():
    original = _sample_stage_result()
    blob = json.dumps(to_dict(original))
    restored = stage_result_from_dict(json.loads(blob))
    assert restored == original


def test_run_manifest_round_trips_through_json():
    original = _sample_run_manifest()
    blob = json.dumps(to_dict(original))
    restored = run_manifest_from_dict(json.loads(blob))
    assert restored == original


def test_unknown_major_schema_version_rejected():
    bad = to_dict(_sample_stage_result())
    bad["schema"] = "bundle.stage-result/v99"
    try:
        stage_result_from_dict(bad)
    except SchemaError:
        pass
    else:
        raise AssertionError("expected SchemaError for unknown major schema version")
    bad2 = to_dict(_sample_run_manifest())
    bad2["schema"] = "bundle.other-thing/v1"
    try:
        run_manifest_from_dict(bad2)
    except SchemaError:
        pass
    else:
        raise AssertionError("expected SchemaError for mismatched schema name")


def test_atomic_writer_leaves_no_partial_target():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "run.json"
        write_json_atomic(target, _sample_run_manifest())
        assert target.exists()
        first = read_json(target)
        assert first["run_id"] == "secure_pipeline-20260607-abcd"
        assert first["settings"]["db.password"] == REDACTED  # writer redacts dataclass fields on disk too
        assert first["settings"]["main_port"] == 5433
        leftovers = [p.name for p in Path(d).iterdir() if p.name != target.name]
        assert leftovers == [], f"temp file(s) left behind: {leftovers}"

        # overwrite must replace atomically too — no partial/garbled content, no temp residue
        write_json_atomic(target, _sample_stage_result())
        second = read_json(target)
        assert second["stage"] == "core"
        leftovers = [p.name for p in Path(d).iterdir() if p.name != target.name]
        assert leftovers == [], f"temp file(s) left behind after overwrite: {leftovers}"

        text = target.read_text(encoding="utf-8")
        assert text.endswith("\n") and not text.endswith("\n\n")
        assert json.loads(text)["stage"] == "core"           # deterministic, parseable, UTF-8


def test_redaction_hides_secret_like_keys():
    raw = {"db": {"host": "localhost", "password": "pass", "settings": {"api_key": "xyz"}},
           "name": "secure_pipeline", "labels": ["t1", "t2"], "credential_refs": ["env:DB_PW"]}
    red = redact(raw)
    assert red["db"]["password"] == REDACTED
    assert red["db"]["settings"]["api_key"] == REDACTED
    assert red["db"]["host"] == "localhost"
    assert red["name"] == "secure_pipeline"
    assert red["labels"] == ["t1", "t2"]                      # non-secret-keyed values pass through untouched
    assert red["credential_refs"] == REDACTED                 # secret-like key redacts the whole value, even a list


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
