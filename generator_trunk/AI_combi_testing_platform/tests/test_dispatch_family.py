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

"""The `dispatch` family: order sensitivity and injected step failures.

Everything else in this platform is single-turn — the target reads one prompt
and answers one static question. That cannot reach the failure mode agentic
systems actually have, which is state tracking across a *sequence* where the
order is not the one anybody intended.

The companion `combination_thinking_tutor` SUT found that 120 of its 144 legal
orderings violate the dispatch rules. This family carries that shape into an LLM
task: the steps are delivered in an arbitrary order, some are marked failed, and
the target must report what actually took effect. Simulation makes it exactly
scorable, so the oracle stays exact while the question stops being static.
"""
import itertools

import pytest

from generator_trunk.AI_combi_testing_platform.engine import (
    initialize_candidate,
    run_candidate,
)
from generator_trunk.AI_combi_testing_platform.oracles.exact import (
    _parse_ordering,
    format_reference_response,
    simulate_dispatch,
    verify_response,
)
from generator_trunk.AI_combi_testing_platform.task_ir import (
    DISPATCH_ACTIONS,
    DispatchTask,
    generate_task,
)

ORDER = ("reserve", "charge", "ship")


def _task(delivered, failed=()):
    return DispatchTask(seed=1, delivered=tuple(delivered), failed_steps=tuple(failed),
                        complexity=len(delivered))


# --- the simulation ------------------------------------------------------
def test_legal_order_with_no_failures_completes():
    assert simulate_dispatch(_task(ORDER)) == ORDER


def test_precedence_blocks_out_of_order_delivery():
    """charge before reserve: charge cannot take effect, and reserve arriving
    later does not retroactively rescue it."""
    assert simulate_dispatch(_task(("charge", "reserve"))) == ("reserve",)


def test_failed_step_never_takes_effect():
    assert simulate_dispatch(_task(ORDER, failed=(1,))) == ("reserve",)


def test_a_failed_prerequisite_stops_everything_after_it():
    assert simulate_dispatch(_task(ORDER, failed=(0,))) == ()


def test_repeated_action_is_not_applied_twice():
    """The double-charge case: a duplicate delivery must be ignored, not
    counted again."""
    assert simulate_dispatch(_task(("reserve", "charge", "charge"))) == ("reserve", "charge")


def test_order_sensitivity_is_the_point_of_the_family():
    """Exhaustive over delivery orders x single failure injections: if almost
    every arrangement succeeded, the family would be measuring nothing."""
    total = complete = 0
    for perm in itertools.permutations(ORDER):
        for failed in ((), (0,), (1,), (2,)):
            total += 1
            if simulate_dispatch(_task(perm, failed)) == ORDER:
                complete += 1
    assert total == 24
    assert complete == 1, "exactly one arrangement should dispatch cleanly"


# --- generation ----------------------------------------------------------
@pytest.mark.parametrize("complexity", [2, 3, 4, 5, 6])
def test_generated_tasks_are_deterministic_and_valid(complexity):
    a = generate_task("dispatch", seed=4242, complexity=complexity)
    b = generate_task("dispatch", seed=4242, complexity=complexity)
    assert a.canonical_dict() == b.canonical_dict()
    assert a.structural_hash == b.structural_hash
    assert set(a.delivered) <= set(DISPATCH_ACTIONS)
    assert all(0 <= i < len(a.delivered) for i in a.failed_steps)


def test_different_seeds_give_different_tasks():
    hashes = {generate_task("dispatch", seed=s, complexity=4).structural_hash
              for s in range(20)}
    assert len(hashes) > 1


def test_invalid_tasks_are_rejected():
    with pytest.raises(ValueError):
        _task(())                                     # nothing delivered
    with pytest.raises(ValueError):
        _task(ORDER, failed=(9,))                     # index outside the log
    with pytest.raises(ValueError):
        _task(ORDER, failed=(1, 1))                   # duplicate index
    with pytest.raises(ValueError):
        DispatchTask(seed=1, delivered=("teleport",), failed_steps=(), complexity=1)


# --- parsing and scoring -------------------------------------------------
@pytest.mark.parametrize("schema", ["json", "plain", "csv"])
def test_empty_answer_round_trips_in_every_schema(schema):
    """`answer=` used to parse back as ('',) rather than (), so an empty result
    disagreed with itself across schemas -- a parser artifact that the schema
    invariance relation would have reported as a model defect."""
    text = format_reference_response((), schema)
    assert _parse_ordering(text, schema) == ()


@pytest.mark.parametrize("schema", ["json", "plain", "csv"])
def test_exact_answer_scores_clean_in_every_schema(schema):
    task = _task(ORDER)
    response = format_reference_response(simulate_dispatch(task), schema)
    result = verify_response(task, response, schema)
    assert result.format_ok and result.correct and result.all_constraints_pass
    assert result.code == 0


def test_reporting_a_failed_step_is_caught_as_a_constraint_breach():
    task = _task(ORDER, failed=(1,))
    wrong = format_reference_response(ORDER, "json")      # claims charge took effect
    result = verify_response(task, wrong, "json")
    assert not result.correct
    assert result.constraints_met < result.constraints_total


def test_malformed_output_is_a_format_failure_not_a_wrong_answer():
    result = verify_response(_task(ORDER), "I think reserve happened first.", "json")
    assert result.code == 4 and not result.format_ok


# --- through the engine --------------------------------------------------
def test_exact_control_solves_the_family_end_to_end():
    plan = initialize_candidate(family="dispatch", seed=99, complexity=4)
    plan.adapter_id = "oracle-control"
    result = run_candidate(plan)
    assert result.code == 0 and result.reason == "ok"


def test_prompt_states_the_rules_and_never_leaks_the_answer():
    plan = initialize_candidate(family="dispatch", seed=99, complexity=4)
    result = run_candidate(plan)
    prompt = result.render.prompt
    assert "canonical action order" in prompt
    assert "FAILED" in prompt
    # the renderer takes no `expected` argument; assert the answer is absent
    answer = simulate_dispatch(result.task)
    if answer:
        assert format_reference_response(answer, "json") not in prompt
