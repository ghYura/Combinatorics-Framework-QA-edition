#!/usr/bin/env python3
r"""Unit coverage for the NESTED value-dependency tier added to the sieve (2027-04-18, task
29062026): the ordinal `orders` model, the new condition leaves (presence, ordinal-vs-constant,
ordinal-cross-sheet, subset-cross-sheet) and the `assert` bond family (a condition-AST as a
require/forbid body). See docs/28_SECOND_ORDER_AXES_AND_NESTED_BONDS.md.

These are DB-free and fast. The telemetry-catalog end-to-end (pure classifier + live HTTP SUT + full Bundle
pipeline) lives in test_telemetry_catalog_full_e2e.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "constraints"))

import fwgen as fg     # noqa: E402
import sieve as sv     # noqa: E402

ORD = {"CaptureStart": "numeric", "CaptureEnd": "numeric",
       "quality": ["bronze", "silver", "gold", "platinum", "diamond"],
       "encoding": ["csv", "parquet", "zarr"],
       "sourceTimestamp": "date"}


def _row(*placements):
    """placements: (sheet, value) pairs OR (sheet, value, pos). Auto-assigns positions in order."""
    out, pos = [], 0
    for p in placements:
        if len(p) == 3:
            out.append({"sheet": p[0], "value": p[1], "pos": p[2]})
        else:
            out.append({"sheet": p[0], "value": p[1], "pos": pos})
        pos += 1
    return out


def _rv(row, constraints, orders=ORD):
    return sv.row_violations(row, {"version": 1, "params": {}, "orders": orders, "constraints": constraints})


# --------------------------------------------------------------------------- #
# orders / _rank
# --------------------------------------------------------------------------- #
def test_rank_list_numeric_date():
    assert sv._rank("quality", "gold", ORD) == 2
    assert sv._rank("CaptureStart", "7", ORD) == 7.0
    assert sv._rank("sourceTimestamp", "2027-04-18", ORD) == __import__("datetime").date(2027, 4, 18).toordinal()


def test_rank_fail_closed_on_unknown_value_or_missing_order():
    with pytest.raises(ValueError):
        sv._rank("quality", "no-such-tier", ORD)            # value not in the declared list
    with pytest.raises(ValueError):
        sv._rank("CaptureStart", "not-a-number", ORD)           # numeric order, non-numeric value
    with pytest.raises(ValueError):
        sv._rank("undeclared", "x", ORD)                 # no order declared for this sheet


# --------------------------------------------------------------------------- #
# presence
# --------------------------------------------------------------------------- #
def test_presence_leaf():
    c = [{"id": "indexed_xor_provisional", "polarity": "forbid",
          "assert": {"all": [{"sheet": "IndexedTimestamp", "present": True},
                             {"sheet": "provisional", "present": True}]}}]
    assert _rv(_row(("IndexedTimestamp", "t1"), ("provisional", "enabled")), c) == ["indexed_xor_provisional"]   # both present → forbidden
    assert _rv(_row(("IndexedTimestamp", "t1")), c) == []                            # only one present → ok
    assert _rv(_row(("provisional", "enabled")), c) == []
    assert _rv(_row(("DatasetFamily", "Climate")), c) == []                     # neither present → ok


def test_presence_implication_require():
    # CaptureEnd present requires CaptureStart present
    c = [{"id": "need_start", "polarity": "require",
          "assert": {"any": [{"sheet": "CaptureEnd", "present": False},
                             {"sheet": "CaptureStart", "present": True}]}}]
    assert _rv(_row(("CaptureEnd", "5")), c) == ["need_start"]                       # CaptureEnd w/o CaptureStart → violated
    assert _rv(_row(("CaptureEnd", "5"), ("CaptureStart", "3")), c) == []                   # both → ok
    assert _rv(_row(("DatasetFamily", "X")), c) == []                          # CaptureEnd absent → vacuous ok


# --------------------------------------------------------------------------- #
# ordinal vs a constant  (ge/gt/le/lt) — vacuous on absence
# --------------------------------------------------------------------------- #
def test_ordinal_vs_constant():
    c = [{"id": "zarr_quality", "polarity": "require", "assert": {"sheet": "quality", "ge": "gold"},
          "condition": {"sheet": "encoding", "eq": "zarr"}}]
    assert _rv(_row(("encoding", "zarr"), ("quality", "silver")), c) == ["zarr_quality"]             # below threshold
    assert _rv(_row(("encoding", "zarr"), ("quality", "gold")), c) == []                 # at threshold
    assert _rv(_row(("encoding", "zarr"), ("quality", "diamond")), c) == []               # above
    assert _rv(_row(("encoding", "csv"), ("quality", "bronze")), c) == []                 # condition false → inert
    assert _rv(_row(("encoding", "zarr"),), c) == []                                 # quality absent → vacuous

    lt = [{"id": "lo", "polarity": "forbid", "assert": {"sheet": "encoding", "lt": "parquet"}}]
    assert _rv(_row(("encoding", "csv"),), lt) == ["lo"]                          # csv < parquet → forbidden
    assert _rv(_row(("encoding", "zarr"),), lt) == []


# --------------------------------------------------------------------------- #
# ordinal cross-sheet  (geSheet/…/ltSheet) — single + multi-select + vacuous
# --------------------------------------------------------------------------- #
def test_ordinal_cross_sheet_single():
    c = [{"id": "range", "polarity": "require", "assert": {"sheet": "CaptureEnd", "geSheet": "CaptureStart"}}]
    assert _rv(_row(("CaptureEnd", "5"), ("CaptureStart", "3")), c) == []
    assert _rv(_row(("CaptureEnd", "3"), ("CaptureStart", "3")), c) == []                   # equal ok for ge
    assert _rv(_row(("CaptureEnd", "2"), ("CaptureStart", "3")), c) == ["range"]
    assert _rv(_row(("CaptureEnd", "2"),), c) == []                                  # CaptureStart absent → vacuous
    assert _rv(_row(("CaptureStart", "3"),), c) == []                                # CaptureEnd absent → vacuous

    strict = [{"id": "gt", "polarity": "require", "assert": {"sheet": "CaptureEnd", "gtSheet": "CaptureStart"}}]
    assert _rv(_row(("CaptureEnd", "3"), ("CaptureStart", "3")), strict) == ["gt"]          # equal fails strict gt


def test_ordinal_cross_sheet_multiselect_semantics():
    # geSheet ⟺ min(left) >= max(right): the whole left selection lies at/above the whole right.
    c = [{"id": "ge", "polarity": "require", "assert": {"sheet": "CaptureEnd", "geSheet": "CaptureStart"}}]
    ok = _row(("CaptureEnd", "4"), ("CaptureEnd", "5"), ("CaptureStart", "2"), ("CaptureStart", "4"))     # min(4,5)=4 >= max(2,4)=4
    bad = _row(("CaptureEnd", "3"), ("CaptureEnd", "5"), ("CaptureStart", "2"), ("CaptureStart", "4"))    # min(3,5)=3 <  max=4
    assert _rv(ok, c) == [] and _rv(bad, c) == ["ge"]


# --------------------------------------------------------------------------- #
# subset cross-sheet  (subOf/supOf)
# --------------------------------------------------------------------------- #
def test_subset_cross_sheet():
    c = [{"id": "sort_subset", "polarity": "require", "assert": {"sheet": "sortBy", "subOf": "SignalClass"}}]
    inside = _row(("sortBy", "A"), ("SignalClass", "A"), ("SignalClass", "B"))
    outside = _row(("sortBy", "A"), ("sortBy", "X"), ("SignalClass", "A"), ("SignalClass", "B"))
    assert _rv(inside, c, orders={}) == []
    assert _rv(outside, c, orders={}) == ["sort_subset"]
    sup = [{"id": "sup", "polarity": "require", "assert": {"sheet": "SignalClass", "supOf": "sortBy"}}]
    assert _rv(outside, sup, orders={}) == ["sup"]                            # SignalClass ⊉ sortBy


# --------------------------------------------------------------------------- #
# assert polarity + nesting + gate
# --------------------------------------------------------------------------- #
def test_assert_polarity_default_is_require():
    c = [{"id": "r", "assert": {"sheet": "CaptureEnd", "geSheet": "CaptureStart"}}]          # no polarity → require
    assert _rv(_row(("CaptureEnd", "2"), ("CaptureStart", "5")), c) == ["r"]
    assert _rv(_row(("CaptureEnd", "9"), ("CaptureStart", "5")), c) == []


def test_deeply_nested_assert():
    # forbid:  (encoding=zarr AND quality<gold)  OR  (CaptureEnd<CaptureStart)
    c = [{"id": "deep", "polarity": "forbid",
          "assert": {"any": [
              {"all": [{"sheet": "encoding", "eq": "zarr"}, {"sheet": "quality", "lt": "gold"}]},
              {"not": {"sheet": "CaptureEnd", "geSheet": "CaptureStart"}}]}}]
    assert _rv(_row(("encoding", "zarr"), ("quality", "bronze"), ("CaptureEnd", "5"), ("CaptureStart", "1")), c) == ["deep"]
    assert _rv(_row(("encoding", "zarr"), ("quality", "platinum"), ("CaptureEnd", "5"), ("CaptureStart", "1")), c) == []
    assert _rv(_row(("encoding", "csv"), ("quality", "bronze"), ("CaptureEnd", "1"), ("CaptureStart", "5")), c) == ["deep"]


# --------------------------------------------------------------------------- #
# validation: fail-closed + arity exemption + describe
# --------------------------------------------------------------------------- #
def test_validation_fail_closed():
    bad = lambda c: sv.validate_sidecar({"version": 1, "constraints": [c]})["invalid_constraint_count"]
    assert bad({"id": "x", "assert": {"sheet": "A", "eqq": 1}}) == 1           # unknown op
    assert bad({"id": "x", "assert": {"sheet": "A", "present": "yes"}}) == 1   # present not bool
    assert bad({"id": "x", "assert": {"sheet": "A", "ge": ["a", "b"]}}) == 1   # ordinal const must be scalar
    assert bad({"id": "x", "assert": {"sheet": "A", "hasAny": 1}}) == 1        # set ops need list values
    assert bad({"id": "x", "assert": {"sheet": "A", "geSheet": ""}}) == 1      # sheet-op needs a name
    assert bad({"id": "x", "assert": {"sheet": "A", "eq": 1, "ne": 2}}) == 1   # >1 op


def test_assert_exempt_from_arity_floor():
    # a unary threshold references ONE sheet; a pairs bond with one sheet would be "unsupported".
    rep = sv.validate_sidecar({"version": 1, "orders": ORD,
                               "constraints": [{"id": "u", "assert": {"sheet": "quality", "ge": "gold"}}]})
    assert rep["unsupported_constraint_count"] == 0 and rep["invalid_constraint_count"] == 0
    rep2 = sv.validate_sidecar({"version": 1, "constraints": [{"id": "p", "pairs": [{"A": "a1"}]}]})
    assert rep2["unsupported_constraint_count"] == 1                           # one-sheet pairs → not a bond


def test_describe_renders_new_leaves():
    d = sv.describe({"id": "x", "polarity": "require", "assert":
                     {"all": [{"sheet": "CaptureEnd", "geSheet": "CaptureStart"}, {"sheet": "IndexedTimestamp", "present": True}]}})
    assert "Require:" in d and "CaptureEnd≥CaptureStart" in d and "IndexedTimestamp present" in d


# --------------------------------------------------------------------------- #
# fail-closed for FW_Optional sheets (the Reader filter can't express relational ops)
# --------------------------------------------------------------------------- #
def test_optional_relational_bonds_fail_closed():
    opt = {"provisional", "IndexedTimestamp"}
    report = sv.optional_bond_compile_report(
        [{"id": "indexed_xor_provisional", "polarity": "forbid",
          "assert": {"all": [{"sheet": "IndexedTimestamp", "present": True}, {"sheet": "provisional", "present": True}]}}],
        params={}, code2val={"g": {1: "x"}}, combos_col={}, sheet_order=["IndexedTimestamp", "provisional"],
        optional_sheets=opt)
    assert report["lines"] == [] and len(report["blockers"]) == 1
    assert "assert" in report["blockers"][0]["features"]


# --------------------------------------------------------------------------- #
# input spec is first-class: orders + assert author/load/emit round-trip
# --------------------------------------------------------------------------- #
def test_input_spec_orders_and_assert_roundtrip(tmp_path):
    spec_toml = tmp_path / "s.toml"
    spec_toml.write_text('''
title = "rt"
[[slots]]
sheet = "CaptureStart"
values = ["s1","s2","s3"]
[[slots]]
sheet = "CaptureEnd"
values = ["s1","s2","s3"]
[orders]
CaptureStart = ["s1","s2","s3"]
CaptureEnd = ["s1","s2","s3"]
[[constraints]]
id = "range"
polarity = "require"
assert = {sheet="CaptureEnd", geSheet="CaptureStart"}
''', encoding="utf-8")
    spec = fg.load_spec(spec_toml)
    assert spec.orders == {"CaptureStart": ["s1", "s2", "s3"], "CaptureEnd": ["s1", "s2", "s3"]}
    sc = fg.emit_sidecar(spec, tmp_path / "sidecar.json")
    assert sc["orders"]["CaptureEnd"] == ["s1", "s2", "s3"]
    assert sv.validate_sidecar(sc)["invalid_constraint_count"] == 0
    # an undeclared order sheet is rejected at load (fail-closed authoring)
    bad = tmp_path / "bad.toml"
    bad.write_text('title="b"\n[[slots]]\nsheet="A"\nvalues=["a"]\n[orders]\nNope=["x"]\n', encoding="utf-8")
    with pytest.raises(ValueError):
        fg.load_spec(bad)
    bad_assert = tmp_path / "bad_assert.toml"
    bad_assert.write_text('title="b"\n[[slots]]\nsheet="A"\nvalues=["a"]\n[[constraints]]\nid="x"\nassert={sheet="A",hasAny=1}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="hasAny"):
        fg.load_spec(bad_assert)
