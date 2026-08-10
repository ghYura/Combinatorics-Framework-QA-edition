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

from fractions import Fraction

from AI_combi_testing_platform.oracles import (
    format_reference_response,
    solve_exact,
    verify_response,
)
from AI_combi_testing_platform.task_ir import (
    CancellationTask,
    OrderingTask,
    generate_task,
)


def test_generation_is_deterministic_and_semantic_mode_changes_identity() -> None:
    first = generate_task("ordering", seed=101, complexity=5)
    again = generate_task("ordering", seed=101, complexity=5)
    loaded = generate_task(
        "ordering",
        seed=101,
        complexity=5,
        semantic_mode="loaded",
    )
    assert isinstance(first, OrderingTask)
    assert first == again
    assert first.structural_hash == again.structural_hash
    assert first.structural_hash != loaded.structural_hash
    assert any(name in {"Zero", "False", "Infinity"} for name in loaded.entities)


def test_exact_ordering_oracle_checks_membership_each_rule_and_tie_break() -> None:
    task = generate_task("ordering", seed=202, complexity=3)
    expected = solve_exact(task)
    assert isinstance(expected, tuple)
    for schema in ("json", "plain", "csv"):
        response = format_reference_response(expected, schema)
        result = verify_response(task, response, schema)
        assert result.code == 0
        assert result.correct
        assert result.constraints_met == result.constraints_total

    malformed = verify_response(task, '{"answer":[]}', "json")
    assert malformed.format_ok
    assert not malformed.correct
    assert malformed.code == 5


def test_cancellation_uses_exact_rational_arithmetic() -> None:
    task = generate_task("cancellation", seed=303, complexity=7)
    assert isinstance(task, CancellationTask)
    expected = solve_exact(task)
    assert expected == Fraction(task.numerator, task.denominator)
    good = verify_response(
        task,
        format_reference_response(expected, "plain"),
        "plain",
    )
    bad = verify_response(task, "answer=999/7", "plain")
    assert good.code == 0
    assert bad.code == 5
