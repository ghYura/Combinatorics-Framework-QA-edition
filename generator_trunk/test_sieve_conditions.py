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

r"""Headless tests for the CONTEXTUAL constraint tier: a `condition` guard (value/x-column/cardinality
boolean over OTHER columns) and a `mapping` target (dependent allowed-set, the `key={v1:v2,v1:v3}`
shape). These re-express, on the flat fw_final, the staged/conditional interconnection the Core builds
via `FW_(...)` brace-joins of prior result tables. Domain: the telemetry catalog query.

Run: ``python3 -m pytest test_sieve_conditions.py -q``.
"""
from __future__ import annotations

import itertools
import sys

import pytest
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))
import fwgen as fg  # noqa: E402
import sieve as sv  # noqa: E402


def _rows(sheets: "OrderedDict[str, list]"):
    """Single-select cartesian over the sheets, as ordered placement-rows (pos = column index)."""
    names = list(sheets)
    out = []
    for combo in itertools.product(*sheets.values()):
        out.append([{"sheet": n, "value": v, "pos": i} for i, (n, v) in enumerate(zip(names, combo))])
    return out


def _sc(*cons, params=None):
    return {"version": 1, "params": params or {}, "constraints": list(cons)}


def _removed_combos(rows, sidecar):
    return {tuple(p["value"] for p in r) for r in rows if sv.row_violations(r, sidecar)}


_TELEMETRY = OrderedDict([("DatasetFamily", ["Mobility", "Climate"]),
                    ("SignalClass", ["Trajectory", "Radar", "WeatherStation"])])


# --------------------------------------------------------------------------- #
def test_condition_gates_a_forbid_to_one_context():
    rows = _rows(_TELEMETRY)                                   # 6
    c = {"id": "mobility_no_climate_signal", "polarity": "forbid", "sheets": ["SignalClass"],
         "sets": {"SignalClass": ["Radar", "WeatherStation"]},
         "condition": {"sheet": "DatasetFamily", "eq": "Mobility"}}
    rep = sv.sieve(rows, _sc(c))
    assert rep["unique_removals"] == 2                   # only Mobility+Radar, Mobility+WeatherStation
    assert _removed_combos(rows, _sc(c)) == {("Mobility", "Radar"), ("Mobility", "WeatherStation")}
    # flipping ONLY the context moves the effect to the Climate rows -> the condition really scopes it
    c_climate = {**c, "condition": {"sheet": "DatasetFamily", "eq": "Climate"}}
    assert _removed_combos(rows, _sc(c_climate)) == {("Climate", "Radar"), ("Climate", "WeatherStation")}


def test_condition_gates_a_require():
    rows = _rows(_TELEMETRY)
    # require SignalClass == Trajectory WHEN DatasetFamily == Mobility (else free)
    c = {"id": "mobility_needs_trajectory", "polarity": "require", "sheets": ["SignalClass"],
         "sets": {"SignalClass": ["Trajectory"]},
         "condition": {"sheet": "DatasetFamily", "eq": "Mobility"}}
    kept = {tuple(p["value"] for p in r) for r in sv.sieve(rows, _sc(c))["kept_rows"]}
    assert ("Mobility", "Trajectory") in kept
    assert ("Mobility", "Radar") not in kept and ("Mobility", "WeatherStation") not in kept
    assert ("Climate", "Radar") in kept and ("Climate", "WeatherStation") in kept   # Climate unaffected


def test_mapping_is_a_dependent_allowed_set():
    rows = _rows(_TELEMETRY)
    c = {"id": "signal_by_family",
         "mapping": {"source": "DatasetFamily", "target": "SignalClass",
                     "allow": {"Mobility": ["Trajectory"], "Climate": ["Radar", "WeatherStation"]}}}
    kept = {tuple(p["value"] for p in r) for r in sv.sieve(rows, _sc(c))["kept_rows"]}
    assert kept == {("Mobility", "Trajectory"), ("Climate", "Radar"), ("Climate", "WeatherStation")}
    # a mapping is equivalent to one conditional-require per source key
    eq = [
        {"id": "s", "polarity": "require", "sheets": ["SignalClass"], "sets": {"SignalClass": ["Trajectory"]},
         "condition": {"sheet": "DatasetFamily", "eq": "Mobility"}},
        {"id": "m", "polarity": "require", "sheets": ["SignalClass"], "sets": {"SignalClass": ["Radar", "WeatherStation"]},
         "condition": {"sheet": "DatasetFamily", "eq": "Climate"}},
    ]
    kept2 = {tuple(p["value"] for p in r) for r in sv.sieve(rows, _sc(*eq))["kept_rows"]}
    assert kept2 == kept


def test_cross_column_equality_leaf():
    rows = _rows(OrderedDict([("SourceTimestamp", ["d1", "d2"]), ("CaptureTimeStart", ["d1", "d2"])]))
    # forbid the row when the two date columns are equal (VX = VY)
    c = {"id": "no_same_date", "polarity": "forbid", "sheets": ["SourceTimestamp"],
         "sets": {"SourceTimestamp": ["d1", "d2"]},
         "condition": {"sheet": "SourceTimestamp", "eqSheet": "CaptureTimeStart"}}
    assert _removed_combos(rows, _sc(c)) == {("d1", "d1"), ("d2", "d2")}


def test_cardinality_leaf_over_a_multi_select_subset():
    # SignalClassList is a SUBSET (>1 placement per row); SignalJoin only matters when |list|>=2.
    base = [{"sheet": "DatasetFamily", "value": "Climate", "pos": 0}]
    one = base + [{"sheet": "SignalClass", "value": "Radar", "pos": 1}]
    two = base + [{"sheet": "SignalClass", "value": "Radar", "pos": 1},
                  {"sheet": "SignalClass", "value": "WeatherStation", "pos": 1}]
    c = {"id": "join_needs_two", "polarity": "forbid", "sheets": ["DatasetFamily"],
         "sets": {"DatasetFamily": ["Climate"]},
         "condition": {"sheet": "SignalClass", "countGe": 2}}
    assert bool(sv.row_violations(two, _sc(c))) is True       # 2 selected -> fires
    assert bool(sv.row_violations(one, _sc(c))) is False      # 1 selected -> inert
    # and the membership/`in` leaf is set-subset over the whole multi-select selection
    c_in = {"id": "all_climate_signals", "polarity": "forbid", "sheets": ["DatasetFamily"],
            "sets": {"DatasetFamily": ["Climate"]},
            "condition": {"sheet": "SignalClass", "in": ["Radar", "WeatherStation", "OceanBuoy"]}}
    assert bool(sv.row_violations(two, _sc(c_in))) is True     # {Radar,WeatherStation} ⊆ allowed


def test_boolean_any_all_not_nesting():
    rows = _rows(_TELEMETRY)
    # forbid Radar when (DatasetFamily==Mobility OR DatasetFamily==Climate) AND NOT(DatasetFamily==Climate)  -> only Mobility+Radar
    c = {"id": "b", "polarity": "forbid", "sheets": ["SignalClass"], "sets": {"SignalClass": ["Radar"]},
         "condition": {"all": [{"any": [{"sheet": "DatasetFamily", "eq": "Mobility"},
                                        {"sheet": "DatasetFamily", "eq": "Climate"}]},
                               {"not": {"sheet": "DatasetFamily", "eq": "Climate"}}]}}
    assert _removed_combos(rows, _sc(c)) == {("Mobility", "Radar")}


def test_conditional_forbid_on_a_specific_combination_context():
    # the user's "VY=X prohibited with one combination if val11:val21 only":
    # forbid Encoding=zarr  WHEN (DatasetFamily=Climate AND SignalClass=Radar)
    sheets = OrderedDict([("DatasetFamily", ["Mobility", "Climate"]),
                          ("SignalClass", ["Radar", "WeatherStation"]),
                          ("Encoding", ["csv", "zarr"])])
    rows = _rows(sheets)                                  # 2*2*2 = 8
    c = {"id": "no_zarr_for_climate_radar", "polarity": "forbid", "sheets": ["Encoding"],
         "sets": {"Encoding": ["zarr"]},
         "condition": {"all": [{"sheet": "DatasetFamily", "eq": "Climate"},
                               {"sheet": "SignalClass", "eq": "Radar"}]}}
    assert _removed_combos(rows, _sc(c)) == {("Climate", "Radar", "zarr")}


def test_arity_counts_condition_sheets_and_strict_still_guards_true_unary():
    # a 1-TARGET bond gated by a condition over ANOTHER sheet IS a supported bond (arity 2)
    c = {"id": "ok", "polarity": "forbid", "sheets": ["SignalClass"], "sets": {"SignalClass": ["Radar"]},
         "condition": {"sheet": "DatasetFamily", "eq": "Mobility"}}
    assert sv.validate_sidecar(_sc(c))["unsupported_constraint_count"] == 0
    # a genuinely unary bond (one sheet, no condition) is still unsupported / strict-fails
    u = {"id": "u", "polarity": "forbid", "sheets": ["SignalClass"], "sets": {"SignalClass": ["Radar"]}}
    assert sv.validate_sidecar(_sc(u))["unsupported_constraint_count"] == 1
    try:
        sv.validate_sidecar(_sc(u), strict=True)
        assert False, "strict should reject the unary bond"
    except ValueError:
        pass


def test_invalid_condition_and_mapping_shapes_fail_closed():
    bad_cond = {"id": "bad", "polarity": "forbid", "sheets": ["SignalClass"],
                "sets": {"SignalClass": ["Radar"]},
                "condition": {"sheet": "DatasetFamily", "eqq": "Mobility"}}
    report = sv.validate_sidecar(_sc(bad_cond))
    assert report["invalid_constraint_count"] == 1
    assert "unknown key" in report["warnings"][0]
    with pytest.raises(ValueError, match="unknown key"):
        sv.validate_sidecar(_sc(bad_cond), strict=True)
    with pytest.raises(ValueError, match="invalid condition"):
        sv.row_violations(_rows(_TELEMETRY)[0], _sc(bad_cond))

    raw = {"slots": [{"sheet": "DatasetFamily", "values": ["Mobility"]},
                       {"sheet": "SignalClass", "values": ["Radar"]}],
           "constraints": [bad_cond]}
    with pytest.raises(ValueError, match="invalid condition"):
        fg.parse_spec(raw, "bad")

    bad_mapping = {"id": "bad_map", "mapping": {"source": "DatasetFamily", "target": "SignalClass",
                                                   "allow": {"Mobility": "Trajectory"}}}
    with pytest.raises(ValueError, match="invalid mapping"):
        fg.parse_spec({**raw, "constraints": [bad_mapping]}, "bad_map")


def test_optional_contextual_bonds_compile_when_domains_are_known():
    c = {"id": "optional_context", "polarity": "forbid", "sheets": ["DatasetFamily"],
         "sets": {"DatasetFamily": ["Mobility"]},
         "condition": {"sheet": "OPT", "eq": "present"}}
    report = sv.optional_bond_compile_report(
        [c], {}, {"DatasetFamily": {1: "Mobility", 2: "Climate", 3: "present"},
                 "OPT": {1: "Mobility", 2: "Climate", 3: "present"}},
        {"DatasetFamily": "combos2_DatasetFamily", "OPT": "combos2_OPT"},
        ["DatasetFamily", "OPT"], {"OPT"},
        {"DatasetFamily": ["Mobility", "Climate"], "OPT": ["present"]})
    assert report["blockers"] == []
    assert report["lines"] == ["F|1|DatasetFamily,OPT|1,3"]


def test_optional_absence_sensitive_conditions_still_block_reader_compile():
    c = {"id": "optional_absence", "polarity": "forbid", "sheets": ["DatasetFamily"],
         "sets": {"DatasetFamily": ["Mobility"]},
         "condition": {"sheet": "OPT", "hasnt": "present"}}
    report = sv.optional_bond_compile_report(
        [c], {}, {"DatasetFamily": {1: "Mobility"}, "OPT": {2: "present"}},
        {"DatasetFamily": "combos2_DatasetFamily", "OPT": "combos2_OPT"},
        ["DatasetFamily", "OPT"], {"OPT"},
        {"DatasetFamily": ["Mobility"], "OPT": ["present"]})
    assert report["lines"] == []
    assert report["blockers"][0]["id"] == "optional_absence"
    assert "absence-sensitive" in report["blockers"][0]["reason"]


def test_no_condition_is_byte_for_byte_unchanged():
    rows = _rows(_TELEMETRY)
    plain = {"id": "p", "polarity": "forbid", "sheets": ["DatasetFamily", "SignalClass"],
             "pairs": [{"DatasetFamily": "Mobility", "SignalClass": "Radar"}], "gate": {}}
    rep = sv.sieve(rows, _sc(plain))
    assert rep["unique_removals"] == 1 and _removed_combos(rows, _sc(plain)) == {("Mobility", "Radar")}


def test_describe_renders_condition_and_mapping():
    c = {"id": "x", "polarity": "forbid", "sheets": ["SignalClass"], "sets": {"SignalClass": ["Radar"]},
         "condition": {"sheet": "DatasetFamily", "eq": "Mobility"}}
    assert "only when" in sv.describe(c) and "DatasetFamily=Mobility" in sv.describe(c)
    m = {"id": "m", "mapping": {"source": "DatasetFamily", "target": "SignalClass",
                                "allow": {"Mobility": ["Trajectory"]}}}
    assert "Map" in sv.describe(m) and "Mobility" in sv.describe(m)
    assert sv.describe_condition({"any": [{"sheet": "A", "eq": "1"}, {"sheet": "B", "in": ["2", "3"]}]})
