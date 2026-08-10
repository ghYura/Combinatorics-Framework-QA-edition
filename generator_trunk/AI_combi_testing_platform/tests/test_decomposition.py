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

"""Capability / fragility / stability decomposition and the interaction map.

`FragileControlAdapter` is the fixture that makes these checkable, because its
contract is declared in code rather than inferred: it degrades when
``complexity >= 4 AND (semantic_mode == 'loaded' OR context notes >= 3)``.

That is a *conjunction*, which means the honest expectations are strong ones:
the capability ceiling must land exactly one step below the declared threshold,
and every failure in a complexity x filler grid must be attributable to the
interaction rather than to either factor alone. A decomposition that cannot
recover a boundary someone wrote down is not measuring anything.
"""
import itertools

import pytest

from generator_trunk.AI_combi_testing_platform.decomposition import (
    capability_profile,
    decompose,
    flatten,
    fragility_profile,
    interaction_map,
    stability_profile,
)
from generator_trunk.AI_combi_testing_platform.engine import (
    initialize_candidate,
    run_candidate,
)

FRAGILE_THRESHOLD = 4          # declared by FragileControlAdapter


def _grid(adapter="fragile-control", complexities=(2, 3, 4, 5, 6),
          fillers=(0, 3, 6, 12), repeats=1):
    records = []
    for complexity, filler, _rep in itertools.product(complexities, fillers, range(repeats)):
        plan = initialize_candidate(family="ordering", seed=777, complexity=complexity)
        plan.adapter_id = adapter
        plan.long_range = filler
        records.append(run_candidate(plan).metrics)
    return records


# --- plumbing ------------------------------------------------------------
def test_flatten_accepts_records_and_plain_rows():
    record = _grid(complexities=(2,), fillers=(0,))[0]
    flat = flatten(record)
    assert flat["complexity"] == 2 and "verdict_code" in flat
    assert flatten(flat) == flat                      # idempotent on flat rows
    assert flatten({"dimensions": {"a": "1"}, "measurements": {"b": 2}}) == {"a": "1", "b": 2}


def test_presentation_axes_are_emitted_individually():
    """Without these only the composite renderer_id hash is available, and no
    per-axis fragility or interaction map can be computed from the results DB."""
    flat = flatten(_grid(complexities=(2,), fillers=(3,))[0])
    for axis in ("px_schema", "px_distractor", "px_long_range", "px_instruction_order"):
        assert axis in flat, f"{axis} is not recoverable from emitted metrics"
    assert flat["px_long_range"] == "3"


# --- capability ----------------------------------------------------------
def test_capability_ceiling_recovers_the_declared_threshold():
    profile = capability_profile(_grid())
    assert profile.ceiling == FRAGILE_THRESHOLD - 1


def test_exact_control_has_no_ceiling_below_the_grid():
    profile = capability_profile(_grid(adapter="oracle-control"))
    assert profile.ceiling == 6, "the exact control must pass every size tested"


def test_ceiling_stops_at_the_first_failure_not_the_last_success():
    """A lucky pass above a failure is noise, not capability -- reporting it
    as a ceiling would overstate the target."""
    rows = [
        {"complexity": 2, "verdict_code": 0},
        {"complexity": 3, "verdict_code": 5},          # breaks here
        {"complexity": 4, "verdict_code": 0},          # ... and recovers
    ]
    assert capability_profile(rows).ceiling == 2


# --- fragility -----------------------------------------------------------
def test_fragility_counts_the_whole_presentation_space():
    report = fragility_profile(_grid(complexities=(5,)), presentation_keys=("px_long_range",))
    task = next(iter(report["tasks"].values()))
    assert task["presentation_space"] == 4          # fillers 0/3/6/12
    assert task["failing_presentations"] == 3       # everything but filler=0
    assert task["fragility_coefficient"] == 0.75


def test_exact_control_is_not_fragile():
    report = fragility_profile(_grid(adapter="oracle-control"))
    assert report["fragility_coefficient"] == 0.0


# --- stability -----------------------------------------------------------
def test_deterministic_control_is_perfectly_stable_across_repeats():
    report = stability_profile(_grid(complexities=(5,), fillers=(6,), repeats=4))
    assert report["comparable_groups"] >= 1
    assert report["instability_rate"] == 0.0


def test_single_samples_cannot_demonstrate_stability():
    """K=1 must not read as 'perfectly reliable'."""
    report = stability_profile(_grid(complexities=(5,), fillers=(6,), repeats=1))
    assert report["comparable_groups"] == 0
    assert report["instability_rate"] is None


def test_disagreeing_repeats_are_flagged_flaky():
    rows = [
        {"task_hash": "t", "renderer_id": "r", "adapter": "a", "model": "m", "verdict_code": 0},
        {"task_hash": "t", "renderer_id": "r", "adapter": "a", "model": "m", "verdict_code": 5},
    ]
    report = stability_profile(rows)
    assert report["flaky_groups"] == 1 and report["instability_rate"] == 1.0


# --- interaction ---------------------------------------------------------
def test_conjunction_failures_are_reported_as_interaction_only():
    """The headline: the fragile control fails only on complexity AND filler,
    so every failure must be invisible to a one-factor-at-a-time sweep."""
    report = interaction_map(_grid(), factor_a="complexity", factor_b="px_long_range",
                             baseline_a="2", baseline_b="0")
    assert report["failing_cells"] == 9
    assert report["interaction_only_failures"] == 9
    assert report["interaction_only_share"] == 1.0


def test_single_factor_failures_are_not_called_interactions():
    """At a fixed failing complexity the filler alone explains everything, so
    nothing may be attributed to an interaction."""
    report = interaction_map(_grid(complexities=(5,)), factor_a="complexity",
                             factor_b="px_long_range", baseline_a="5", baseline_b="0")
    assert report["failing_cells"] > 0
    assert report["interaction_only_failures"] == 0


def test_incomplete_grids_yield_no_verdict_rather_than_a_guess():
    """Without both marginals present a cell cannot be classified; the map must
    drop it instead of assuming the missing side passed."""
    rows = [{"a": "x", "b": "y", "verdict_code": 5}]     # no baseline row at all
    report = interaction_map(rows, factor_a="a", factor_b="b", baseline_a="base", baseline_b="base")
    assert report["cells"] == 0 and report["interaction_only_failures"] == 0


# --- combined ------------------------------------------------------------
def test_decompose_returns_all_three_marginals_from_one_pass():
    report = decompose(_grid(repeats=2))
    assert report["capability"]["ceiling"] == FRAGILE_THRESHOLD - 1
    assert report["fragility"]["fragility_coefficient"] > 0
    assert report["stability"]["instability_rate"] == 0.0
