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

from pathlib import Path

import fwgen


HERE = Path(__file__).resolve().parents[1]
SCENARIOS = HERE / "scenarios"
EXPECTED = (
    "00_smoke",
    "01_operator_smoke",
    "10_constraint_stack",
    "20_logic_and_cancellation",
    "30_semantic_interference",
    "40_long_range_dependency",
    "50_format_and_instruction_order",
    "60_higher_order_prompt_programs",
    "70_router_regression_dataset",
)


def test_every_scenario_is_present_and_strictly_parseable() -> None:
    for name in EXPECTED:
        path = SCENARIOS / name / "scenario.toml"
        assert path.is_file(), name
        spec = fwgen.load_spec(path, strict=True)
        assert spec.spec_version == "1"
        assert spec.goals


def test_smoke_cardinality_is_bounded_and_exact() -> None:
    spec = fwgen.load_spec(SCENARIOS / "00_smoke" / "scenario.toml", strict=True)
    plan = fwgen.spec_cardinality_plan(spec)
    assert plan.final.mode.value == "EXACT"
    assert plan.final.value == 32


def test_operator_smoke_and_fourth_order_scenario_use_real_result_tables() -> None:
    operator = (SCENARIOS / "01_operator_smoke" / "scenario.toml").read_text()
    fourth = (
        SCENARIOS / "60_higher_order_prompt_programs" / "scenario.toml"
    ).read_text()
    assert "group_replace" in operator
    assert "FW_PermutR(2)" in operator
    assert operator.count("FW_()") == 2
    assert fourth.count("FW_()") >= 2
    assert "FW_()G" in fourth
    assert 'sheet = "ROOT_RESULT"' in fourth


def test_intermediate_brace_targets_are_excluded() -> None:
    expectations = {
        "01_operator_smoke": (
            "TASK_RENDER_RESULT",
            "SCHEMA_RESULT",
        ),
        "60_higher_order_prompt_programs": (
            "CLAUSE_RESULT",
            "FORMAT_RESULT",
            "CONTEXT_RESULT",
        ),
    }
    for scenario, sheets in expectations.items():
        text = (SCENARIOS / scenario / "scenario.toml").read_text()
        for sheet in sheets:
            block = text.split(f'sheet = "{sheet}"', 1)[1].split(
                "[[slots]]",
                1,
            )[0]
            assert 'flags = ["FW_Exclude"]' in block
