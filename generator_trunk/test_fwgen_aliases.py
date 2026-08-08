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

"""STEP 36 — domain-level authoring aliases.

An author may write a slot with a plain-English `alias` (choose_one / choose_k /
permute / feature_subset / optional_action) instead of a raw FW verb. The
compiler lowers it to the SAME advanced verb (+flags) an expert would write, so:

  * an alias spec and its equivalent expert spec produce the IDENTICAL workbook
    and combo count (acceptance #1),
  * a conflicting alias+verb on the same slot is rejected (acceptance #2),
  * the normalized advanced representation is inspectable and round-trips
    (acceptance #3 + action #4).

Run: `python3 -m pytest test_fwgen_aliases.py -q` (no DB / no Bundle run).
"""
import json
import tempfile
from pathlib import Path

import pytest

import fwgen as fg
from bundle.handoff import validate_against_json_schema, HandoffError

_SCHEMA = json.loads((Path(__file__).resolve().parent / "bundle-spec-v1.schema.json")
                     .read_text(encoding="utf-8"))


def _schema_doc(slots):
    return {"spec_version": "1", "title": "schema-check", "slots": slots}


def _base(slots):
    # a constant runme so the spec NAME never leaks into the workbook (the default
    # runme embeds the name) — lets us compare alias-vs-expert workbooks by value.
    return {"title": "alias-equiv", "runme": "class R{}", "goals": ["cost_usd"], "slots": slots}


# Each case: (alias slot, the expert slot it MUST compile to). Same sheet/values
# so the only difference is alias-vs-verb; everything else must come out identical.
_VALUES = ["v1", "v2", "v3", "v4"]
_EQUIV_CASES = [
    ("choose_one",
     {"sheet": "S", "values": _VALUES, "alias": "choose_one"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Combi(1)"}),
    ("choose_k(2)",
     {"sheet": "S", "values": _VALUES, "alias": "choose_k(2)"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Combi(2)"}),
    ("permute",
     {"sheet": "S", "values": _VALUES, "alias": "permute"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Permut"}),
    ("permute(2)",
     {"sheet": "S", "values": _VALUES, "alias": "permute(2)"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Permut(2)"}),
    ("feature_subset",
     {"sheet": "S", "values": _VALUES, "alias": "feature_subset"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Subsets"}),
    ("feature_subset(2)",
     {"sheet": "S", "values": _VALUES, "alias": "feature_subset(2)"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Subsets(2)"}),
    ("optional_action",
     {"sheet": "S", "values": _VALUES, "alias": "optional_action"},
     {"sheet": "S", "values": _VALUES, "verb": "FW_Combi(1)", "flags": ["FW_Optional"]}),
]


@pytest.mark.parametrize("label,alias_slot,expert_slot", _EQUIV_CASES,
                         ids=[c[0] for c in _EQUIV_CASES])
def test_alias_equivalent_to_expert_spec(label, alias_slot, expert_slot):
    """Acceptance #1: identical workbook + count for alias vs equivalent expert."""
    a = fg.parse_spec(_base([alias_slot]), "alias")
    e = fg.parse_spec(_base([expert_slot]), "expert")

    # compiled slot is byte-for-byte the expert one (verb + flags + values)
    assert a.slots[0].verb == e.slots[0].verb
    assert a.slots[0].flags == e.slots[0].flags
    assert a.slots[0].values == e.slots[0].values
    assert a.slots[0].alias == label and e.slots[0].alias == ""

    # identical combo count …
    assert fg.estimate_core_combos(a) == fg.estimate_core_combos(e)
    plan_a, plan_e = fg.spec_cardinality_plan(a), fg.spec_cardinality_plan(e)
    assert plan_a.mandatory.value == plan_e.mandatory.value

    # … and the IDENTICAL workbook (deterministic core-json: FW_Seq + data sheets)
    assert fg.build_compact_core_json(a) == fg.build_compact_core_json(e)


def test_conflicting_alias_and_verb_is_rejected():
    """Acceptance #2: a slot cannot carry both an alias and a raw verb."""
    with pytest.raises(ValueError, match="BOTH alias"):
        fg.parse_spec(_base([
            {"sheet": "S", "values": _VALUES, "alias": "choose_k(2)", "verb": "FW_Permut"}
        ]), "conflict")


def test_alias_argument_validation():
    """choose_k needs (k); the no-arg aliases reject a stray (k); unknown alias fails."""
    with pytest.raises(ValueError, match="choose_k.*requires a .*k. argument"):
        fg.parse_spec(_base([{"sheet": "S", "values": _VALUES, "alias": "choose_k"}]), "bad1")
    with pytest.raises(ValueError, match="choose_one.*takes no .*k. argument"):
        fg.parse_spec(_base([{"sheet": "S", "values": _VALUES, "alias": "choose_one(2)"}]), "bad2")
    with pytest.raises(ValueError, match="unknown authoring alias"):
        fg.parse_spec(_base([{"sheet": "S", "values": _VALUES, "alias": "pick_some"}]), "bad3")


def test_compile_alias_unit_mapping():
    """The lowering table itself (direct unit check, independent of parse_spec)."""
    assert fg.compile_alias("choose_one") == ("FW_Combi(1)", ())
    assert fg.compile_alias("choose_k(3)") == ("FW_Combi(3)", ())
    assert fg.compile_alias("permute") == ("FW_Permut", ())
    assert fg.compile_alias("permute(2)") == ("FW_Permut(2)", ())
    assert fg.compile_alias("feature_subset") == ("FW_Subsets", ())
    assert fg.compile_alias("feature_subset(2)") == ("FW_Subsets(2)", ())
    assert fg.compile_alias("optional_action") == ("FW_Combi(1)", ("FW_Optional",))
    assert fg.is_alias("choose_k(2)") and not fg.is_alias("FW_Combi(2)")


def test_optional_action_merges_with_author_flags():
    """optional_action contributes FW_Optional; an author-listed flag is kept too, de-duped."""
    s = fg.parse_spec(_base([
        {"sheet": "S", "values": _VALUES, "alias": "optional_action", "flags": ["FW_Exclude"]}
    ]), "merge").slots[0]
    assert s.verb == "FW_Combi(1)"
    assert set(s.flags) == {"FW_Exclude", "FW_Optional"}
    # listing FW_Optional explicitly alongside the alias does not duplicate it
    s2 = fg.parse_spec(_base([
        {"sheet": "S", "values": _VALUES, "alias": "optional_action", "flags": ["FW_Optional"]}
    ]), "merge2").slots[0]
    assert s2.flags == ("FW_Optional",)


def test_normalized_spec_roundtrips_to_expert_spec():
    """Acceptance #3: the normalized advanced representation is raw-verb-only and
    re-parses to a spec equivalent to the hand-written expert one."""
    alias_slots = [
        {"sheet": "MODE", "values": ["x", "y", "z"], "alias": "choose_one"},
        {"sheet": "OPTS", "values": ["a", "b", "c", "d"], "alias": "feature_subset(2)"},
        {"sheet": "EXTRA", "values": ["p", "q"], "alias": "optional_action"},
    ]
    expert_slots = [
        {"sheet": "MODE", "values": ["x", "y", "z"], "verb": "FW_Combi(1)"},
        {"sheet": "OPTS", "values": ["a", "b", "c", "d"], "verb": "FW_Subsets(2)"},
        {"sheet": "EXTRA", "values": ["p", "q"], "verb": "FW_Combi(1)", "flags": ["FW_Optional"]},
    ]
    a = fg.parse_spec(_base(alias_slots), "mix")
    e = fg.parse_spec(_base(expert_slots), "mix-expert")

    norm = fg.normalized_spec_dict(a)
    # the normalized dict carries NO aliases — only compiled verbs
    assert all("alias" not in s for s in norm["slots"])
    assert [s["verb"] for s in norm["slots"]] == ["FW_Combi(1)", "FW_Subsets(2)", "FW_Combi(1)"]

    # and it round-trips to an equivalent spec (same workbook as the expert spec)
    reparsed = fg.parse_spec(norm, "mix-normalized")
    assert fg.build_compact_core_json(reparsed) == fg.build_compact_core_json(e)
    assert fg.estimate_core_combos(reparsed) == fg.estimate_core_combos(e)


def test_emit_normalized_spec_writes_inspectable_artifact():
    """action #4: emit_normalized_spec writes JSON with the round-trippable
    `normalized` block + an `alias_provenance` audit list."""
    a = fg.parse_spec(_base([
        {"sheet": "MODE", "values": ["x", "y"], "alias": "choose_one"},
        {"sheet": "OPTS", "values": ["a", "b", "c"], "alias": "feature_subset"},
    ]), "art")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "art.normalized.json"
        obj = fg.emit_normalized_spec(a, p)
        on_disk = json.loads(p.read_text(encoding="utf-8"))
        assert on_disk == obj
        assert obj["spec"] == "art"
        prov = {x["sheet"]: x for x in obj["alias_provenance"]}
        assert prov["MODE"]["alias"] == "choose_one" and prov["MODE"]["verb"] == "FW_Combi(1)"
        assert prov["OPTS"]["alias"] == "feature_subset" and prov["OPTS"]["verb"] == "FW_Subsets"
        # the embedded normalized block re-parses cleanly (strict: no stray keys)
        reparsed = fg.parse_spec(obj["normalized"], "art-norm", strict=True)
        assert [s.verb for s in reparsed.slots] == ["FW_Combi(1)", "FW_Subsets"]


def test_alias_spec_generates_a_valid_workbook():
    """Generator validate: a workbook built from an alias spec passes
    validate_workbook (the aliases compiled to real Core verbs)."""
    a = fg.parse_spec(_base([
        {"sheet": "MODE", "values": ["x", "y", "z"], "alias": "choose_one"},
        {"sheet": "OPTS", "values": ["a", "b", "c", "d"], "alias": "choose_k(2)"},
    ]), "wbk")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wbk.xlsx"
        fg.build_compact(a).save(p)
        assert fg.validate_workbook(p) == []


# --------------------------------------------------------------------------
# Public schema (bundle-spec-v1.schema.json) must declare `alias` and forbid
# alias+verb — otherwise schema validation would reject a valid alias spec.
# --------------------------------------------------------------------------

_VALID_ALIASES = ["choose_one", "choose_k(2)", "permute", "permute(3)",
                  "feature_subset", "feature_subset(2)", "optional_action"]


@pytest.mark.parametrize("alias", _VALID_ALIASES)
def test_schema_accepts_alias_specs(alias):
    """The public spec-v1 schema accepts a slot authored with each alias."""
    validate_against_json_schema(
        _schema_doc([{"sheet": "S", "values": ["a", "b"], "alias": alias}]), _SCHEMA)


def test_schema_still_accepts_expert_verb_specs():
    """Raw-verb (expert) slots remain valid — the alias addition is additive."""
    validate_against_json_schema(
        _schema_doc([{"sheet": "S", "values": ["a", "b"], "verb": "FW_Subsets(2)",
                      "flags": ["FW_Optional"]}]), _SCHEMA)


def test_schema_rejects_alias_plus_verb():
    """Schema-level mutual exclusion: a slot may not carry both alias and verb."""
    with pytest.raises(HandoffError, match="must NOT match"):
        validate_against_json_schema(
            _schema_doc([{"sheet": "S", "values": ["a"],
                          "alias": "choose_one", "verb": "FW_Combi(1)"}]), _SCHEMA)


@pytest.mark.parametrize("bad", ["pick_some", "choose_k", "choose_one(2)",
                                 "feature_subset(x)", "permute(2", "CHOOSE_ONE"])
def test_schema_rejects_invalid_alias_values(bad):
    """The alias pattern rejects unknown names and malformed/forbidden (k) args."""
    with pytest.raises(HandoffError, match="pattern"):
        validate_against_json_schema(
            _schema_doc([{"sheet": "S", "values": ["a"], "alias": bad}]), _SCHEMA)


def test_schema_accepts_normalized_artifact_block():
    """The compiled `normalized` block (raw verbs only) is itself schema-valid —
    so the saved run artifact validates against the public spec contract."""
    a = fg.parse_spec(_base([
        {"sheet": "MODE", "values": ["x", "y"], "alias": "choose_one"},
        {"sheet": "OPTS", "values": ["a", "b", "c"], "alias": "optional_action"},
    ]), "norm-art")
    validate_against_json_schema(fg.normalized_spec_dict(a), _SCHEMA)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
