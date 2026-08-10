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

from AI_combi_testing_platform.sub_suites.release_gate_breakpoint.task_factory import (
    generate_release_gate_ladder,
)
from AI_combi_testing_platform.sub_suites.release_gate_breakpoint import runtime


SEED = b"public-release-gate-unit-test-seed-v1"


def _plan(**changes: object) -> dict:
    value = {
        "section_order": ["policy", "evidence"],
        "numeric_surface": "native",
        "context_depth": "clean",
        "schema": "json",
        "trust_wording": "direct",
        "options": [],
    }
    value.update(changes)
    return value


def test_exponential_ladder_and_independent_planted_answers() -> None:
    rows = generate_release_gate_ladder(SEED)
    assert [len(row.task["checks"]) for row in rows] == [2, 4, 8, 16, 32]
    assert [row.planted_answer["decision"] for row in rows] == [
        "HOLD",
        "RELEASE",
        "HOLD",
        "RELEASE",
        "HOLD",
    ]
    assert all(runtime.rg_solve(row.task) == row.planted_answer for row in rows)

def test_ladder_sizes_are_configurable_but_remain_exponential() -> None:
    rows = generate_release_gate_ladder(SEED, (4, 8, 16, 32, 64))
    assert [row.task["difficulty_units"] for row in rows] == [4, 8, 16, 32, 64]
    assert [len(row.task["checks"]) for row in rows] == [4, 8, 16, 32, 64]
    assert all(runtime.rg_solve(row.task) == row.planted_answer for row in rows)
    invalid = dict(rows[0].task)
    invalid["difficulty_units"] = 3
    with pytest.raises(ValueError, match="power of two"):
        runtime.rg_validate_task(invalid)


def test_renderer_does_not_call_answer_solver(monkeypatch: pytest.MonkeyPatch) -> None:
    task = generate_release_gate_ladder(SEED)[2].task

    def forbidden(_task: dict) -> dict:
        raise AssertionError("renderer called the answer solver")

    monkeypatch.setattr(runtime, "rg_solve", forbidden)
    prompt = runtime.rg_render(task, _plan())
    assert "CURRENT CHECK DEFINITIONS" in prompt
    assert "CURRENT EVIDENCE" in prompt


def test_all_512_prompt_plans_preserve_one_exact_answer() -> None:
    task = generate_release_gate_ladder(SEED)[2].task
    expected = runtime.rg_solve(task)
    prompts: set[str] = set()
    for bits in range(2**9):
        signature = f"{bits:09b}"
        options = [
            option
            for bit, option in zip(
                signature[5:],
                (
                    "alt_rule_labels",
                    "alt_decision_words",
                    "dist_archive",
                    "dist_override",
                ),
            )
            if bit == "1"
        ]
        plan = _plan(
            section_order=(
                ["evidence", "policy"] if signature[0] == "1" else ["policy", "evidence"]
            ),
            numeric_surface="converted" if signature[1] == "1" else "native",
            context_depth="long" if signature[2] == "1" else "clean",
            schema="plain" if signature[3] == "1" else "json",
            trust_wording="nested" if signature[4] == "1" else "direct",
            options=options,
        )
        assert runtime.rg_factor_signature(plan) == signature
        prompt = runtime.rg_render(task, plan)
        prompts.add(prompt)
        reference = runtime.rg_format_reference(task, plan)
        assert runtime.rg_verify(task, plan, reference)["code"] == 0
        assert runtime.rg_solve(task) == expected
        assert reference not in prompt
    assert len(prompts) == 512


def test_alternate_answers_are_accepted_only_when_licensed() -> None:
    task = generate_release_gate_ladder(SEED)[4].task
    licensed = _plan(options=["alt_rule_labels", "alt_decision_words"])
    alternate = runtime.rg_format_reference(task, licensed, use_alternates=True)
    assert runtime.rg_verify(task, licensed, alternate)["code"] == 0
    assert runtime.rg_verify(task, _plan(), alternate)["code"] == 5


def test_strict_and_extracted_semantic_layers_remain_separate() -> None:
    task = generate_release_gate_ladder(SEED)[3].task
    plan = _plan()
    exact = runtime.rg_format_reference(task, plan)
    wrapped = "Reasoning omitted here.\n```json\n" + exact + "\n```"
    diagnostic = runtime.rg_diagnose_response(task, plan, wrapped)
    assert diagnostic["strict"]["code"] == 4
    assert diagnostic["semantic_correct"] == 1
    assert diagnostic["diagnostic_category"] == "format_only"


@pytest.mark.parametrize("schema", ("json", "plain"))
def test_wrapped_actual_answers_extract_in_both_output_grammars(schema: str) -> None:
    task = generate_release_gate_ladder(SEED)[4].task
    plan = _plan(schema=schema, options=["alt_rule_labels", "alt_decision_words"])
    exact = runtime.rg_format_reference(task, plan, use_alternates=True)
    diagnostic = runtime.rg_diagnose_response(
        task, plan, "Model commentary:\n" + exact + "\nDone."
    )
    assert diagnostic["strict"]["code"] == 4
    assert (
        diagnostic["semantic_extracted"],
        diagnostic["semantic_correct"],
        diagnostic["candidate_count"],
    ) == (1, 1, 1)


@pytest.mark.parametrize("response", ('{"decision":"HOLD"}', "DECISION HOLD"))
def test_partial_actual_answers_are_never_inferred(response: str) -> None:
    task = generate_release_gate_ladder(SEED)[0].task
    diagnostic = runtime.rg_diagnose_response(task, _plan(), response)
    assert diagnostic["semantic_extracted"] == 0
    assert diagnostic["semantic_correct"] == 0


def test_wrong_and_ambiguous_extracted_answers_are_not_forgiven() -> None:
    task = generate_release_gate_ladder(SEED)[1].task
    plan = _plan()
    exact = json.loads(runtime.rg_format_reference(task, plan))
    wrong = dict(exact)
    wrong["decision"] = "HOLD" if exact["decision"] == "RELEASE" else "RELEASE"
    wrong_text = json.dumps(wrong, separators=(",", ":"))
    wrong_diagnostic = runtime.rg_diagnose_response(task, plan, wrong_text)
    assert wrong_diagnostic["strict"]["code"] == 5
    assert wrong_diagnostic["semantic_correct"] == 0

    ambiguous = runtime.rg_format_reference(task, plan) + "\n" + wrong_text
    ambiguous_diagnostic = runtime.rg_diagnose_response(task, plan, ambiguous)
    assert ambiguous_diagnostic["diagnostic_category"] == "ambiguous_multiple_answers"
    assert ambiguous_diagnostic["semantic_extracted"] == 0


def test_correct_set_in_wrong_declared_order_is_structural_only() -> None:
    task = generate_release_gate_ladder(SEED)[4].task
    plan = _plan()
    value = json.loads(runtime.rg_format_reference(task, plan))
    assert len(value["failed_checks"]) > 1
    value["failed_checks"] = list(reversed(value["failed_checks"]))
    response = json.dumps(value, separators=(",", ":"))
    strict = runtime.rg_verify(task, plan, response)
    diagnostic = runtime.rg_diagnose_response(task, plan, response)
    assert strict == {
        "code": 4,
        "correct": 0,
        "format_ok": 0,
        "category": "format",
        "reason": "failed_check_order",
    }
    assert diagnostic["semantic_correct"] == 1
    assert diagnostic["extracted_order_ok"] == 0


@pytest.mark.parametrize(
    "mutation",
    ("drop", "add", "decision", "extra_key", "prose"),
)
def test_oracle_mutants_are_detected(mutation: str) -> None:
    task = generate_release_gate_ladder(SEED)[2].task
    plan = _plan()
    value = json.loads(runtime.rg_format_reference(task, plan))
    if mutation == "drop":
        value["failed_checks"] = value["failed_checks"][:-1]
        response = json.dumps(value, separators=(",", ":"))
        expected = 5
    elif mutation == "add":
        passing = next(
            check["id"]
            for check in task["checks"]
            if check["id"] not in value["failed_checks"]
        )
        value["failed_checks"].append(passing)
        response = json.dumps(value, separators=(",", ":"))
        expected = 5
    elif mutation == "decision":
        value["decision"] = "RELEASE" if value["decision"] == "HOLD" else "HOLD"
        response = json.dumps(value, separators=(",", ":"))
        expected = 5
    elif mutation == "extra_key":
        value["explanation"] = "none"
        response = json.dumps(value, separators=(",", ":"))
        expected = 4
    else:
        response = "Answer: " + json.dumps(value, separators=(",", ":"))
        expected = 4
    assert runtime.rg_verify(task, plan, response)["code"] == expected


def test_refusal_is_separate_from_format_and_reasoning() -> None:
    task = generate_release_gate_ladder(SEED)[0].task
    verdict = runtime.rg_verify(task, _plan(), "I cannot assist with this audit.")
    assert verdict["code"] == 6
    assert verdict["category"] == "refusal"
