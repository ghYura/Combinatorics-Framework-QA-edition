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
"""t-wise coverage is executed, not only reported.

`plan` used to state a covering array's size while the run executed the full
product. These pin the repaired contract: the plan's final count IS the suite the
sieve stage keeps (one allowlist feeds both), specs a covering array cannot be
applied to faithfully are refused with the reason, and the stage keeps exactly
the planned rows or refuses to run.
"""
from __future__ import annotations

import itertools

import pytest

import fwgen as fg
from bundle import stages, twise
from bundle.errors import StageError

_SPEC = """
spec_version = "1"
title = "t-wise probe"
{extra}

[[slots]]
sheet = "A"
key = "a"
verb = "{verb_a}"
values = ["a1", "a2", "a3"]

[[slots]]
sheet = "B"
key = "b"
verb = "FW_Combi(1)"
values = ["b1", "b2", "b3"]

[[slots]]
sheet = "C"
key = "c"
verb = "FW_Combi(1)"
values = ["c1", "c2"]

[[slots]]
sheet = "D"
key = "d"
verb = "FW_Combi(1)"
values = ["d1", "d2", "d3"]

[[slots]]
sheet = "OPT"
key = "opt"
verb = "FW_Combi(1)"
flags = ["FW_Optional"]
values = ["o1"]
"""


def _spec(tmp_path, extra="coverage_strength = 2\ncoverage_optimal = true", verb_a="FW_Combi(1)"):
    path = tmp_path / "probe.toml"
    path.write_text(_SPEC.format(extra=extra, verb_a=verb_a), encoding="utf-8")
    return fg.load_spec(path)


def test_plan_final_is_the_covering_array_times_the_optional_multiplier(tmp_path) -> None:
    spec = _spec(tmp_path)
    strength, rows = fg.coverage_allowlist(spec)
    plan = fg.spec_cardinality_plan(spec)
    assert strength == 2 and plan.coverage.value == len(rows) < 3 * 3 * 2 * 3
    assert plan.post_sieve.value == len(rows)
    assert plan.final.value == len(rows) * plan.optional_multiplier.value


def test_the_allowlist_covers_every_pair_of_mandatory_values(tmp_path) -> None:
    spec = _spec(tmp_path)
    _t, rows = fg.coverage_allowlist(spec)
    levels = [["a1", "a2", "a3"], ["b1", "b2", "b3"], ["c1", "c2"], ["d1", "d2", "d3"]]
    for i, j in itertools.combinations(range(4), 2):
        for pair in itertools.product(levels[i], levels[j]):
            assert any((row[i], row[j]) == pair for row in rows), (i, j, pair)
    assert fg.coverage_allowlist(spec) == (2, rows), "plan and run must derive the same list"


def test_no_request_leaves_the_plan_untouched(tmp_path) -> None:
    plan = fg.spec_cardinality_plan(_spec(tmp_path, extra=""))
    assert plan.coverage is None
    assert plan.final.value == 3 * 3 * 2 * 3 * plan.optional_multiplier.value


@pytest.mark.parametrize("verb", ["FW_Permut", "FW_Subsets", "FW_Combi(2)"])
def test_order_and_subset_verbs_are_refused_with_the_reason(tmp_path, verb) -> None:
    spec = _spec(tmp_path, verb_a=verb)
    reason = fg.coverage_ineligibility(spec)
    assert reason and "'A'" in reason and verb.split("(")[0] in reason
    plan = fg.spec_cardinality_plan(spec)
    assert plan.coverage.mode is fg.CardinalityMode.UNKNOWN
    assert plan.post_sieve.value == plan.mandatory.value, "an unapplied reduction must not shrink the plan"


def test_a_constraint_sidecar_is_refused(tmp_path) -> None:
    spec = _spec(tmp_path)
    spec.constraints.append({"id": "r1", "sheets": ["A", "B"], "pairs": [["a1", "b1"]]})
    assert "constraint sidecar" in fg.coverage_ineligibility(spec)


def test_the_sieve_stage_refuses_an_ineligible_spec_before_touching_the_database(tmp_path) -> None:
    with pytest.raises(StageError, match="t-wise coverage refused"):
        stages.stage_sieve(_spec(tmp_path, verb_a="FW_Permut"), tmp_path, "db", 5433, 99)


# ---- decoding fw_final's delta encoding -------------------------------------
_CODES = {"A": {1: "a2", 2: "a3"}, "B": {3: "b2"}}
_BASE = {"A": "a1", "B": "b1"}


def test_empty_cells_decode_to_the_baseline_and_codes_to_their_value() -> None:
    assert twise.decode_row({"A": None, "B": [3]}, ["A", "B"], _CODES, _BASE) == ("a1", "b2")
    assert twise.decode_row({"A": [2], "B": []}, ["A", "B"], _CODES, _BASE) == ("a3", "b1")


def test_a_multi_code_cell_is_not_guessed() -> None:
    with pytest.raises(ValueError, match="single-pick"):
        twise.decode_row({"A": [1, 2], "B": None}, ["A", "B"], _CODES, _BASE)


def test_partition_reports_kept_dropped_and_missing() -> None:
    records = [(10, {"A": None, "B": None}), (11, {"A": [1], "B": None}), (12, {"A": [2], "B": [3]})]
    allow = {("a1", "b1"), ("a3", "b2"), ("a2", "b2")}
    keep, drop, missing = twise.partition(records, ["A", "B"], _CODES, _BASE, allow)
    assert keep == [10, 12] and drop == [11] and missing == {("a2", "b2")}


class _Cursor:
    def __init__(self, rows):
        self.rows, self.deleted = rows, None

    def execute(self, sql, params=None):
        if sql.startswith("DELETE"):
            self.deleted = sorted(params[0])

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _Conn:
    def __init__(self, rows):
        self.cur = _Cursor(rows)
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def _fw_final(spec):
    """A faithful fw_final for `spec`: every mandatory tuple once, delta-encoded."""
    mandatory = [s for s in spec.slots if "FW_Optional" not in s.flags]
    code2val, codes, baseline, next_code = {}, {}, {}, 1
    for s in mandatory:
        baseline[s.sheet] = s.values[0]
        code2val[s.sheet] = {}
        for v in s.values[1:]:
            code2val[s.sheet][next_code] = v
            codes[(s.sheet, v)] = next_code
            next_code += 1
    rows = []
    for i, combo in enumerate(itertools.product(*[s.values for s in mandatory])):
        cells = [[] if v == s.values[0] else [codes[(s.sheet, v)]] for s, v in zip(mandatory, combo)]
        rows.append((i + 1, *cells))
    combos_col = {s.sheet: f"combos1_{s.sheet}" for s in mandatory}
    return rows, code2val, baseline, combos_col


def test_the_stage_keeps_exactly_the_planned_rows(tmp_path) -> None:
    spec = _spec(tmp_path)
    rows, code2val, baseline, combos_col = _fw_final(spec)
    conn = _Conn(rows)
    kept = stages._apply_coverage(conn, spec, code2val, baseline, combos_col)
    assert kept == fg.spec_cardinality_plan(spec).post_sieve.value
    assert len(conn.cur.deleted) == len(rows) - kept and conn.committed


def test_a_short_fw_final_refuses_rather_than_overclaim_coverage(tmp_path) -> None:
    spec = _spec(tmp_path)
    rows, code2val, baseline, combos_col = _fw_final(spec)
    _t, allowed = fg.coverage_allowlist(spec)
    first_allowed = rows[[tuple(v for v in combo) for combo in itertools.product(
        *[s.values for s in spec.slots if "FW_Optional" not in s.flags])].index(allowed[0])]
    with pytest.raises(StageError, match="planned tuple"):
        stages._apply_coverage(_Conn([r for r in rows if r is not first_allowed]),
                               spec, code2val, baseline, combos_col)
