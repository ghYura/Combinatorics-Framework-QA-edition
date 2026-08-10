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

"""Exact, deterministic solvers and parsers that do not call a model."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import itertools
import json
from typing import TypeAlias

from ..task_ir import (
    DISPATCH_ACTIONS,
    CancellationTask,
    DispatchTask,
    OrderingTask,
    Task,
)


ExactAnswer: TypeAlias = tuple[str, ...] | Fraction
OUTPUT_SCHEMAS = ("json", "plain", "csv")


@dataclass(frozen=True)
class OracleResult:
    format_ok: bool
    correct: bool
    constraints_met: int
    constraints_total: int
    parsed: ExactAnswer | None
    reason: str

    @property
    def all_constraints_pass(self) -> bool:
        return (
            self.constraints_total > 0
            and self.constraints_met == self.constraints_total
        )

    @property
    def code(self) -> int:
        if not self.format_ok:
            return 4
        return 0 if self.correct and self.all_constraints_pass else 5


def _ordering_valid(task: OrderingTask, order: tuple[str, ...]) -> bool:
    if len(order) != len(task.entities) or set(order) != set(task.entities):
        return False
    positions = {name: index for index, name in enumerate(order)}
    return all(
        positions[constraint.before] < positions[constraint.after]
        for constraint in task.constraints
    )


def simulate_dispatch(task: "DispatchTask") -> tuple[str, ...]:
    """The actions that actually take effect, in effect order.

    The rules are the companion tutor SUT's, stated once here so the oracle and
    the rendered instructions cannot drift apart:

    * an action takes effect only if every action before it in the canonical
      order has already taken effect (precedence);
    * a delivered step that is marked failed never takes effect;
    * an action already in effect is never applied twice (no double charge).

    Deterministic and total: every delivered sequence has exactly one outcome,
    which is what keeps this family exactly scorable while still being a
    question about state over time.
    """
    canonical = list(DISPATCH_ACTIONS)
    in_effect: list[str] = []
    for index, action in enumerate(task.delivered):
        if index in task.failed_steps:
            continue
        if action in in_effect:
            continue
        position = canonical.index(action)
        prerequisites = [a for a in canonical[:position] if a in task.delivered]
        if any(p not in in_effect for p in prerequisites):
            continue
        in_effect.append(action)
    return tuple(in_effect)


def solve_exact(task: Task) -> ExactAnswer:
    if isinstance(task, DispatchTask):
        return simulate_dispatch(task)
    if isinstance(task, OrderingTask):
        for order in itertools.permutations(sorted(task.entities)):
            if _ordering_valid(task, order):
                return order
        raise ValueError("canonical ordering task has no valid solution")
    if isinstance(task, CancellationTask):
        value = Fraction(task.numerator, task.denominator)
        symbol = Fraction(task.symbol_value, 1)
        for _ in range(task.inverse_depth):
            value *= symbol
            value /= symbol
        return value
    raise TypeError(f"unsupported task type: {type(task)!r}")


def _fraction_text(value: Fraction) -> str:
    return (
        str(value.numerator)
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}"
    )


def format_reference_response(answer: ExactAnswer, schema: str) -> str:
    """Format a control response.  This function is never used by renderers."""
    if schema not in OUTPUT_SCHEMAS:
        raise ValueError(f"unsupported output schema: {schema!r}")
    if isinstance(answer, Fraction):
        value: str | list[str] = _fraction_text(answer)
    else:
        value = list(answer)
    if schema == "json":
        return json.dumps({"answer": value}, separators=(",", ":"), sort_keys=True)
    if schema == "plain":
        joined = ">".join(value) if isinstance(value, list) else value
        return f"answer={joined}"
    joined = ",".join(value) if isinstance(value, list) else value
    return f"answer,{joined}"


def _parse_ordering(response: str, schema: str) -> tuple[str, ...] | None:
    try:
        if schema == "json":
            document = json.loads(response)
            answer = document["answer"]
            if set(document) != {"answer"} or not isinstance(answer, list):
                return None
            return tuple(str(item) for item in answer)
        if schema == "plain":
            if not response.startswith("answer="):
                return None
            payload = response.removeprefix("answer=")
            # An empty payload is the empty sequence, not a sequence containing
            # one empty name. Without this, `answer=` parsed to `('',)` while
            # the json form parsed to `()`, so any empty answer disagreed with
            # itself across schemas -- a parser artifact that would register as
            # a metamorphic violation and convict a target of nothing.
            return () if payload == "" else tuple(payload.split(">"))
        if schema == "csv":
            parts = response.split(",")
            if not parts or parts[0] != "answer":
                return None
            rest = parts[1:]
            return () if rest == [""] else tuple(rest)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _parse_fraction(response: str, schema: str) -> Fraction | None:
    try:
        if schema == "json":
            document = json.loads(response)
            if set(document) != {"answer"}:
                return None
            raw = document["answer"]
        elif schema == "plain" and response.startswith("answer="):
            raw = response.removeprefix("answer=")
        elif schema == "csv" and response.startswith("answer,"):
            raw = response.removeprefix("answer,")
        else:
            return None
        if isinstance(raw, bool) or not isinstance(raw, (str, int)):
            return None
        return Fraction(str(raw))
    except (KeyError, TypeError, ValueError, ZeroDivisionError, json.JSONDecodeError):
        return None


def verify_response(
    task: Task,
    response: str,
    schema: str,
    *,
    expected: ExactAnswer | None = None,
) -> OracleResult:
    """Parse once, check every declared constraint, then compare exact answers."""
    if schema not in OUTPUT_SCHEMAS:
        raise ValueError(f"unsupported output schema: {schema!r}")
    exact = solve_exact(task) if expected is None else expected
    if isinstance(task, DispatchTask):
        parsed = _parse_ordering(response.strip(), schema)
        if parsed is None:
            return OracleResult(False, False, 0, 3, None, "format")
        # Three independently checkable properties, so a near-miss is
        # distinguishable from nonsense: only delivered actions may appear, no
        # failed step may appear, and precedence must hold in what is reported.
        delivered_ok = set(parsed) <= set(task.delivered)
        failed_actions = {task.delivered[i] for i in task.failed_steps}
        no_failed = not (set(parsed) & failed_actions)
        canonical = list(DISPATCH_ACTIONS)
        precedence_ok = parsed == tuple(
            sorted(parsed, key=canonical.index)
        ) and len(set(parsed)) == len(parsed)
        met = int(delivered_ok) + int(no_failed) + int(precedence_ok)
        correct = parsed == exact
        return OracleResult(
            True, correct, met, 3, parsed,
            "ok" if correct and met == 3 else "dispatch",
        )
    if isinstance(task, OrderingTask):
        parsed = _parse_ordering(response.strip(), schema)
        if parsed is None:
            return OracleResult(
                False, False, 0, len(task.constraints) + 1, None, "format"
            )
        positions = {name: index for index, name in enumerate(parsed)}
        membership_ok = len(parsed) == len(task.entities) and set(parsed) == set(
            task.entities
        )
        met = int(membership_ok)
        met += sum(
            int(
                membership_ok
                and positions[constraint.before] < positions[constraint.after]
            )
            for constraint in task.constraints
        )
        total = len(task.constraints) + 1
        correct = parsed == exact
        return OracleResult(
            True,
            correct,
            met,
            total,
            parsed,
            "ok" if correct and met == total else "ordering",
        )

    parsed_fraction = _parse_fraction(response.strip(), schema)
    if parsed_fraction is None:
        return OracleResult(False, False, 0, 2, None, "format")
    nonzero_assignment = task.symbol_value != 0
    exact_match = parsed_fraction == exact
    return OracleResult(
        True,
        exact_match,
        int(nonzero_assignment) + int(exact_match),
        2,
        parsed_fraction,
        "ok" if exact_match else "arithmetic",
    )
