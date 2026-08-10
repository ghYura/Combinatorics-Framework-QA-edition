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

from __future__ import annotations

import json

import pytest

from AI_combi_testing_platform.reporting import reconcile_run


def _write_optional_run(
    run_dir,
    *,
    core_rows: int = 2,
    reader_rows: int = 32,
    reader_expected: int = 32,
) -> None:
    run_id = "optional-expansion-run"
    (run_dir / "stages").mkdir(parents=True)
    documents = {
        "state.json": {"status": "SUCCEEDED", "run_id": run_id},
        "stages/core.json": {
            "stage": "core",
            "status": "SUCCEEDED",
            "counts": [
                {"name": "fw_final", "actual": core_rows, "expected": core_rows}
            ],
        },
        "stages/reader.json": {
            "stage": "reader",
            "status": "SUCCEEDED",
            "counts": [
                {
                    "name": "candidates",
                    "actual": reader_rows,
                    "expected": reader_expected,
                }
            ],
        },
        "stages/executor.json": {"stage": "executor", "status": "SUCCEEDED"},
        "stages/analyzer.json": {"stage": "analyzer", "status": "SUCCEEDED"},
        "executor-summary.json": {
            "processed": reader_rows,
            "pass": reader_rows,
            "fail": 0,
            "inserted": reader_rows,
            "outcomes": {"PASS": reader_rows},
        },
        "provenance.json": {
            "candidates_seen": reader_rows,
            "provenance_ok": True,
            "candidates": [{"run_id": run_id}],
        },
    }
    for relative, document in documents.items():
        (run_dir / relative).write_text(json.dumps(document), encoding="utf-8")
    (run_dir / "metrics.kv").write_text(
        "".join(
            f"app=ai_combi_testing FW_VAR=0 run_id={run_id} candidate_id=c{index}\n"
            for index in range(reader_rows)
        ),
        encoding="utf-8",
    )


def test_reconcile_accepts_factored_core_and_optional_reader_expansion(tmp_path) -> None:
    _write_optional_run(tmp_path)
    evidence = reconcile_run(tmp_path)
    assert evidence["core"] == 2
    assert evidence["reader"] == evidence["reader_expected"] == 32
    assert evidence["checks"]["reader_equals_declared_runtime_expansion"]
    assert "core_equals_reader" not in evidence["checks"]


def test_reconcile_rejects_reader_that_misses_declared_expansion(tmp_path) -> None:
    _write_optional_run(tmp_path, reader_expected=31)
    with pytest.raises(
        RuntimeError,
        match="reader_equals_declared_runtime_expansion",
    ):
        reconcile_run(tmp_path)
