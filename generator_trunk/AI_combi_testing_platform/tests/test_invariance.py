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

"""Metamorphic (orbit-scoped) verdicts.

The property under test is that a *group* of candidates can convict a target
without anyone knowing the right answer. The platform's own declared controls
make that checkable: `oracle-control` is exactly right everywhere, and
`fragile-control` degrades when declared-neutral filler appears -- which is a
violation of an invariance the filler text itself asserts ("descriptive only and
adds no rule").

A detector that only ever passes is worthless, so the fragile control is used to
prove the detector fires, and the per-axis relations are asserted to *exonerate*
the axes that are not responsible.
"""
import itertools

import pytest

from generator_trunk.AI_combi_testing_platform.engine import (
    initialize_candidate,
    run_candidate,
)
from generator_trunk.AI_combi_testing_platform.invariance import (
    JOINT_RELATION,
    RELATIONS,
    RELATIONS_BY_NAME,
    answer_digest,
    applicable_relations,
    evaluate_orbits,
    orbit_key,
    summarize,
)

VALID_LONG_RANGE = (0, 3, 6, 12)


def _orbit(adapter: str, complexity: int) -> list[dict]:
    """One task, every declared-invariant presentation of it."""
    records = []
    for long_range, schema, constraint_order in itertools.product(
        VALID_LONG_RANGE, ("json", "plain", "csv"), ("forward", "reverse")
    ):
        plan = initialize_candidate(family="ordering", seed=4242, complexity=complexity)
        plan.adapter_id = adapter
        plan.long_range = long_range
        plan.schema = schema
        plan.constraint_order = constraint_order
        records.append(dict(run_candidate(plan).metrics.dimensions))
    return records


# --- digests -------------------------------------------------------------
def test_digest_is_serialization_independent():
    """The whole schema relation depends on this: json/plain/csv must digest
    the same, because comparison happens on the parsed answer, not the text."""
    assert answer_digest(("a", "b")) == answer_digest(["a", "b"])
    assert answer_digest(("a", "b")) != answer_digest(("b", "a"))
    assert answer_digest(None) == "unparsed"


def test_unparsed_is_never_treated_as_agreement():
    """Two candidates that both failed to answer have not agreed on anything."""
    records = [{"orbit_x": "k", "answer_digest": "unparsed"} for _ in range(3)]
    verdict = evaluate_orbits(records)[0]
    assert verdict.status == "UNPARSED"
    assert verdict.distinct_answers == 0


def test_singletons_are_excluded_from_the_denominator():
    """One member proves nothing; counting it would make sparse runs look clean."""
    verdicts = evaluate_orbits([{"orbit_x": "solo", "answer_digest": "d1"}])
    assert verdicts[0].status == "SINGLETON"
    assert summarize(verdicts)["comparable_orbits"] == 0


# --- orbit identity ------------------------------------------------------
def test_orbit_key_separates_different_tasks():
    plan = initialize_candidate(family="ordering", seed=1, complexity=2)
    assert orbit_key(plan, "hash-a") != orbit_key(plan, "hash-b")


def test_orbit_key_ignores_the_axis_the_relation_varies():
    a = initialize_candidate(family="ordering", seed=1, complexity=2)
    b = initialize_candidate(family="ordering", seed=1, complexity=2)
    a.long_range, b.long_range = 0, 3
    assert orbit_key(a, "h", "neutral_context") == orbit_key(b, "h", "neutral_context")
    # ... but they are NOT comparable under a relation that holds it fixed
    assert orbit_key(a, "h", "output_schema") != orbit_key(b, "h", "output_schema")


def test_non_invariant_values_are_excluded_from_their_relation():
    """A contradictory distractor is designed to interfere, so asserting
    invariance across it would manufacture violations that are correct."""
    plan = initialize_candidate(family="ordering", seed=1, complexity=2)
    plan.distractor = "contradictory"
    relations = applicable_relations(plan)
    assert "neutral_distractor" not in relations
    assert JOINT_RELATION not in relations, "a non-invariant axis must leave the joint orbit"


def test_every_relation_documents_why_it_holds():
    for relation in RELATIONS:
        assert relation.rationale.strip(), f"{relation.name} has no rationale"
        assert len(relation.rationale) > 40, f"{relation.name}'s rationale is not an argument"


# --- the detector, against the platform's own controls -------------------
def test_exact_control_is_invariant_everywhere():
    summary = summarize(evaluate_orbits(_orbit("oracle-control", complexity=5)))
    assert summary["comparable_orbits"] > 0, "test would be vacuous"
    assert summary["invariance_violation_rate"] == 0.0


def test_fragile_control_is_convicted_without_any_ground_truth():
    """The headline claim: a group verdict, no expected answer consulted."""
    summary = summarize(evaluate_orbits(_orbit("fragile-control", complexity=5)))
    assert summary["invariance_violation_rate"] > 0.0
    assert summary["relations"]["neutral_context"]["violation_rate"] == 1.0


@pytest.mark.parametrize("innocent", ["output_schema", "constraint_order"])
def test_violation_is_attributed_to_the_axis_that_causes_it(innocent):
    """Detection is cheap; attribution is the useful part. The fragile control
    degrades on filler alone, so schema and constraint order must come back
    clean even though the same run convicts neutral_context."""
    summary = summarize(evaluate_orbits(_orbit("fragile-control", complexity=5)))
    bucket = summary["relations"][innocent]
    assert bucket["comparable"] > 0
    assert bucket["violation_rate"] == 0.0, f"{innocent} was wrongly blamed"


def test_fragile_control_is_consistent_below_its_declared_threshold():
    """Its contract is to degrade at complexity >= 4; below that it must look
    exactly like the exact control, or the relation set is over-firing."""
    summary = summarize(evaluate_orbits(_orbit("fragile-control", complexity=2)))
    assert summary["invariance_violation_rate"] == 0.0


def test_relation_names_are_stable_dimension_keys():
    """Emitted as `orbit_<name>` dimensions, so they must survive metrics
    sanitisation and stay unique."""
    names = [r.name for r in RELATIONS]
    assert len(set(names)) == len(names)
    for name in names:
        assert name.replace("_", "").isalnum()
        assert RELATIONS_BY_NAME[name].name == name
