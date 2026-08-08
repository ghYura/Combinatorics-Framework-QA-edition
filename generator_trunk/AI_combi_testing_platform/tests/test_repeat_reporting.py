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

from AI_combi_testing_platform.reporting import _derived_metrics


def _row(run_id: str, candidate_id: str, repeat_idx: int, correct: int) -> dict[str, str]:
    return {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "repeat_idx": str(repeat_idx),
        "adapter": "measured-model",
        "model": "model-a",
        "task_hash": "task",
        "renderer_id": "renderer",
        "prompt_version": "v1",
        "correct": str(correct),
        "complexity": "3",
        "latency_us": "10",
        "cost_microusd": "2",
        "is_control": "0",
        "FW_VAR": "0" if correct else "5",
    }


def test_repeat_consistency_groups_by_run_and_candidate() -> None:
    rows = [
        _row("run-a", "1_0_0", 0, 1),
        _row("run-a", "1_0_0", 1, 1),
        # The same Bundle candidate number in another run is not a repeat.
        _row("run-b", "1_0_0", 0, 0),
    ]
    derived = _derived_metrics(rows)
    assert derived["repeat_consistency"] == {
        "groups": 1,
        "consistent_verdict_groups": 1,
        "rate": 1.0,
    }
    assert derived["router_policy"]["status"] == "EVIDENCE_AVAILABLE"
