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

from __future__ import annotations

import json

from AI_combi_testing_platform.dataset import VerifiedDataset
from AI_combi_testing_platform.engine import initialize_candidate, run_candidate
from AI_combi_testing_platform.reporting import _expected_count, parse_metrics_line


def test_dataset_exports_only_exact_passes_and_deduplicates(tmp_path) -> None:
    passing_plan = initialize_candidate(
        family="cancellation",
        seed=808,
        complexity=3,
    )
    passing = run_candidate(passing_plan)
    failing_plan = initialize_candidate(
        family="cancellation",
        seed=909,
        complexity=5,
    )
    failing_plan.semantic_mode = "loaded"
    failing_plan.adapter_id = "fragile-control"
    failing = run_candidate(failing_plan)

    dataset = VerifiedDataset(
        license_id="CC-BY-4.0",
        privacy_classification="synthetic-no-personal-data",
    )
    assert dataset.add(passing)
    assert not dataset.add(passing)
    assert not dataset.add(failing)
    output = tmp_path / "verified.jsonl"
    assert dataset.write_jsonl(output) == 1
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["oracle"]["exact"] is True
    assert record["provenance"]["source_kind"] == "control"
    assert record["privacy"] == "synthetic-no-personal-data"


def test_metrics_parser_preserves_provenance_and_numeric_contract() -> None:
    result = run_candidate(
        initialize_candidate(family="ordering", seed=1001, complexity=2)
    )
    fields = parse_metrics_line(result.metrics_line())
    assert fields["task_hash"] == result.task.structural_hash
    assert fields["renderer_id"] == result.render.renderer_id
    assert fields["FW_VAR"] == "0"
    assert fields["provider_error"] == "0"


def test_metrics_parser_accepts_sub_suite_records() -> None:
    for app in ("ai_combi_robustness", "ai_combi_release_gate"):
        fields = parse_metrics_line(
            f"app={app} FW_VAR=0 correct=1 task_id=rt-test"
        )
        assert fields["app"] == app
        assert fields["task_id"] == "rt-test"


def test_reader_expected_count_supports_optional_runtime_expansion() -> None:
    stage = {
        "stage": "reader",
        "counts": [{"name": "candidates", "actual": 256, "expected": 256}],
    }
    assert _expected_count(stage, "candidates") == 256
