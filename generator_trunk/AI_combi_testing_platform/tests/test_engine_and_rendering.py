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

import inspect

import pytest

from AI_combi_testing_platform.adapters import AdapterInfrastructureError
from AI_combi_testing_platform.engine import initialize_candidate, run_candidate
from AI_combi_testing_platform.renderers import (
    emit_atom,
    emit_close,
    emit_open,
    parse_program,
    program_stats,
    render_task,
)


@pytest.mark.parametrize("family", ("ordering", "cancellation"))
@pytest.mark.parametrize("schema", ("json", "plain", "csv"))
def test_exact_local_control_produces_one_eligible_record(
    family: str,
    schema: str,
) -> None:
    plan = initialize_candidate(family=family, seed=404, complexity=5)
    plan.schema = schema
    plan.semantic_mode = "loaded"
    plan.costume = "loaded"
    result = run_candidate(plan)
    line = result.metrics_line()
    assert result.code == 0
    assert line.startswith("app=ai_combi_testing ")
    assert line.count("FW_VAR=") == 1
    assert "\n" not in line
    assert "is_control=1" in line
    assert "correct=1" in line


def test_renderer_has_no_oracle_answer_or_certificate_parameter() -> None:
    parameters = inspect.signature(render_task).parameters
    assert tuple(parameters) == ("task", "plan")
    assert "expected" not in parameters
    assert "answer" not in parameters
    assert "certificate" not in parameters


def test_fragile_control_is_a_declared_negative_control() -> None:
    plan = initialize_candidate(family="cancellation", seed=505, complexity=5)
    plan.semantic_mode = "loaded"
    plan.costume = "loaded"
    plan.adapter_id = "fragile-control"
    result = run_candidate(plan)
    assert result.code == 5
    assert result.completion is not None and result.completion.is_control
    assert "correct=0" in result.metrics_line()


def test_recursive_prompt_program_selects_complete_highest_order_root() -> None:
    plan = initialize_candidate(family="ordering", seed=606, complexity=4)
    emit_open(plan.program_stream, 1, "clauses")
    emit_atom(plan.program_stream, "constraint_order:reverse")
    emit_close(plan.program_stream, 1)
    emit_open(plan.program_stream, 3, "prompt")
    emit_atom(plan.program_stream, "schema:plain")
    emit_atom(plan.program_stream, "long_range:3")
    emit_close(plan.program_stream, 3)
    emit_open(plan.program_stream, 3, "empty_bookkeeping")
    emit_close(plan.program_stream, 3)
    emit_open(plan.program_stream, 4, "incomplete")
    root = parse_program(plan.program_stream)
    stats = program_stats(root)
    assert root.kind == "prompt"
    assert stats["program_order"] == 3
    assert stats["program_depth"] >= 2
    result = run_candidate(plan)
    assert result.code == 0
    assert result.render is not None and result.render.schema == "plain"


def test_external_adapter_selection_fails_closed_without_config() -> None:
    plan = initialize_candidate(family="ordering", seed=707, complexity=2)
    plan.adapter_id = "external-not-configured"
    with pytest.raises(AdapterInfrastructureError):
        run_candidate(plan)
