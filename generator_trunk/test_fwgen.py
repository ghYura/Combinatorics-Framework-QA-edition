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

"""Self-contained tests for fwgen (run: `python3 test_fwgen.py`; pytest also works).
Uses an in-memory spec — no external files — to exercise the engine, plus a
round-trip through build/validate/json on a temp workbook."""
import tempfile
from pathlib import Path

import fwgen as fg
import code_decompose as cd

HERE = Path(__file__).resolve().parent

SPEC_DICT = {
    "title": "unit-test scenario",
    "goals": ["cost_usd", "throughput_rps"],
    "slots": [
        {"sheet": "A", "key": "a", "values": ["a1", "a2", "a3"]},
        {"sheet": "B", "key": "b", "values": ["b1", "b2"]},
        {"sheet": "C", "key": "c", "values": ["c1", "c2", "c3"]},
    ],
}


def _all_pairs(combos):
    s = set()
    for c in combos:
        for (i, vi), (j, vj) in fg.itertools.combinations(enumerate(c), 2):
            s.add((i, vi, j, vj))
    return s


def test_spec_and_inference():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    assert spec.combos == 3 * 2 * 3 == 18
    assert spec.baseline == ("a1", "b1", "c1")
    assert [g.direction for g in spec.goals] == ["min", "max"]   # cost->min, throughput->max
    assert fg.infer_direction("latency_ms") == "min"
    assert fg.infer_direction("p99") == "min"
    assert fg.infer_direction("recall") == "max"


def test_cardinality_exact_formulas_for_combi_permut_subsets():
    M = fg.CardinalityMode
    # FW_Combi(k): C(n,k) — exact, bounds collapse to the value
    c = fg.verb_cardinality("FW_Combi(2)", 5)
    assert c.mode == M.EXACT and c.value == c.lower == c.upper == 10
    # FW_CombiR(k): multicombination C(n+k-1,k) — exact
    cr = fg.verb_cardinality("FW_CombiR(2)", 4)
    assert cr.mode == M.EXACT and cr.value == fg.math.comb(5, 2) == 10
    # FW_Permut: n! — exact
    p = fg.verb_cardinality("FW_Permut", 4)
    assert p.mode == M.EXACT and p.value == 24
    # FW_PermutR(k): n^k — exact
    pr = fg.verb_cardinality("FW_PermutR(2)", 3)
    assert pr.mode == M.EXACT and pr.value == 9
    # FW_Subsets / FW_Subsets_EXACT(k) — exact
    s = fg.verb_cardinality("FW_Subsets", 4)
    assert s.mode == M.EXACT and s.value == 16
    se = fg.verb_cardinality("FW_Subsets_EXACT(2)", 4)
    assert se.mode == M.EXACT and se.value == 6
    for est in (c, cr, p, pr, s, se):
        assert est.formula and est.lower == est.upper == est.value   # exact => degenerate bounds


def test_cardinality_optional_multiplier_is_exact():
    M = fg.CardinalityMode
    no_opt = fg.parse_spec(SPEC_DICT, "unit")
    est0 = fg.optional_multiplier_cardinality(no_opt)
    assert est0.mode == M.EXACT and est0.value == 1

    with_opt = fg.parse_spec({
        "slots": [
            {"sheet": "A", "key": "a", "values": ["a1", "a2", "a3"]},
            {"sheet": "B", "key": "b", "values": ["b1", "b2"], "flags": ["FW_Optional"]},
            {"sheet": "C", "key": "c", "values": ["c1"], "flags": ["FW_Optional"]},
        ],
    }, "unit-optional")
    est = fg.optional_multiplier_cardinality(with_opt)
    # B: 2 values + absent = 3; C: 1 value + absent = 2 -> 3*2 = 6, EXACT (closed form)
    assert est.mode == M.EXACT
    assert est.value == est.lower == est.upper == 6
    assert "B" in est.formula and "C" in est.formula


def test_cardinality_brace_and_group_are_non_exact():
    M = fg.CardinalityMode
    # FW_Group: row-preserving UPPER bound only — group_replace rewrites can
    # collide rows, so it must NOT be reported as exact (plan STEP 9 action 4)
    g = fg.verb_cardinality("FW_Group", 5)
    assert g.mode == M.BOUNDED
    assert g.lower == 1 and g.upper == 5
    assert g.value is not None and "group_replace" in g.reasons[0]

    # FW_Cartes: bounded by declared operand-sheet size, not its actual join size
    cartes = fg.verb_cardinality("FW_Cartes(OTHER)", 3, other_n=4)
    assert cartes.mode == M.BOUNDED
    assert cartes.lower <= cartes.value <= cartes.upper == 12
    assert "operand" in cartes.reasons[0]

    # Brace joiner: combines two operand RESULT TABLES — statically unknowable
    brace = fg.brace_cardinality("FW_(A,_,B,FW_Combi(2),C,_,D,sep,2)")
    assert brace.mode == M.UNKNOWN
    assert brace.value is None and brace.lower is None and brace.upper is None
    assert "RESULT TABLES" in brace.reasons[0]

    # An unrecognized verb is UNKNOWN, not silently presented as exact/bounded
    mystery = fg.verb_cardinality("FW_NoSuchVerb", 7)
    assert mystery.mode == M.UNKNOWN and mystery.value is None


def test_cardinality_plan_aggregates_stages_with_confidence():
    import json
    M = fg.CardinalityMode

    # No optional slots, no constraints -> every stage stays EXACT and collapses
    spec = fg.parse_spec(SPEC_DICT, "unit")           # A:3 x B:2 x C:3 (default verb) = 18
    plan = fg.spec_cardinality_plan(spec)
    assert plan.raw_values == {"A": 3, "B": 2, "C": 3}
    assert set(plan.per_slot) == {"A", "B", "C"}
    assert all(e.mode == M.EXACT for e in plan.per_slot.values())
    assert plan.mandatory.mode == M.EXACT and plan.mandatory.value == 18 == fg.estimate_core_combos(spec)
    assert plan.post_sieve.mode == M.EXACT and plan.post_sieve.value == 18   # no constraints -> sieve no-op
    assert plan.optional_multiplier.mode == M.EXACT and plan.optional_multiplier.value == 1
    assert plan.final.mode == M.EXACT and plan.final.value == 18

    # JSON and human projections exist, round-trip, and mirror the same stages
    d = fg.cardinality_plan_to_dict(plan)
    assert json.loads(json.dumps(d)) == d
    for stage in ("raw_values", "per_slot", "mandatory", "post_sieve", "optional_multiplier", "final"):
        assert stage in d
    rendered = fg.format_cardinality_plan(plan)
    for needle in ("raw values", "per-slot Core rows", "mandatory Core product",
                   "estimated post-sieve", "optional multiplier", "final candidate count"):
        assert needle in rendered


def test_cardinality_plan_propagates_brace_confidence_into_aggregates():
    M = fg.CardinalityMode

    # Both A and B are FW_Exclude'd (brace operands) -> the per-slot mandatory
    # filter sees nothing mandatory of its own; the brace joiner is the ONLY
    # source of fw_final rows. Before the fix this collapsed to a bogus
    # "EXACT 1" empty-product instead of reflecting the brace's UNKNOWN join.
    spec = fg.parse_spec({
        "slots": [{"sheet": "A", "values": ["a1", "a2"], "flags": ["FW_Exclude"]},
                  {"sheet": "B", "values": ["b1", "b2"], "flags": ["FW_Exclude"]},
                  {"sheet": "JOINED", "values": [" placeholder"]}],
        "seq_extra": [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]],
    }, "brace-plan")
    plan = fg.spec_cardinality_plan(spec)

    assert plan.mandatory.mode == M.UNKNOWN, plan.mandatory
    assert plan.mandatory.value is None
    assert any("brace" in r for r in plan.mandatory.reasons)
    assert "brace" in plan.mandatory.formula

    # UNKNOWN propagates all the way through post-sieve/optional/final — never
    # silently reported as an exact number.
    assert plan.post_sieve.mode == M.UNKNOWN
    assert plan.final.mode == M.UNKNOWN
    assert plan.final.value is None


def test_cardinality_plan_optional_and_sieve_are_bounded_not_overclaimed():
    M = fg.CardinalityMode
    spec = fg.parse_spec({
        "slots": [
            {"sheet": "A", "key": "a", "values": ["a1", "a2", "a3"]},
            {"sheet": "B", "key": "b", "values": ["b1", "b2"], "flags": ["FW_Optional"]},
        ],
        "params": [{"sheet": "A", "value": "a1", "weight": 1}],
        "constraints": [{"id": "deny-a1-b1", "pairs": [{"A": "a1", "B": "b1"}], "polarity": "deny"}],
    }, "unit-plan")
    plan = fg.spec_cardinality_plan(spec)

    # mandatory: only A counts (B is FW_Optional) -> EXACT 3
    assert plan.mandatory.mode == M.EXACT and plan.mandatory.value == 3

    # constraints declared -> post-sieve is a provable range, NOT a fabricated point
    assert plan.post_sieve.mode == M.BOUNDED
    assert plan.post_sieve.lower == 0 and plan.post_sieve.upper == 3
    assert plan.post_sieve.reasons and "constraint" in plan.post_sieve.reasons[0]

    # optional multiplier: B contributes (2 values + absent) = 3, EXACT
    assert plan.optional_multiplier.mode == M.EXACT and plan.optional_multiplier.value == 3

    # final = post_sieve(BOUNDED) x optional_multiplier(EXACT) -> stays BOUNDED, never overclaimed EXACT
    assert plan.final.mode == M.BOUNDED
    assert plan.final.lower == 0 and plan.final.upper == 9
    assert plan.final.value == 9


def test_spec_version_legacy_default_and_strict_mode():
    # No spec_version key -> legacy interpretation, normalizes to the same model
    spec = fg.parse_spec(SPEC_DICT, "unit")
    assert spec.spec_version == "legacy"
    assert spec.combos == 18                                # unchanged by the version field

    # Explicit "1" is accepted and recorded as-is
    v1 = dict(SPEC_DICT, spec_version="1")
    spec1 = fg.parse_spec(v1, "unit-v1")
    assert spec1.spec_version == "1"
    assert spec1.combos == spec.combos == 18                # same internal model, same count

    # Unsupported spec_version fails closed regardless of mode (hard contract mismatch)
    bad_version = dict(SPEC_DICT, spec_version="999")
    for kw in ({}, {"strict": True}):
        try:
            fg.parse_spec(bad_version, "unit-badver", **kw)
        except ValueError as e:
            assert "999" in str(e) and "unsupported" in str(e)
        else:
            raise AssertionError(f"spec_version=999 should be rejected (strict={kw})")

    # Unknown top-level field: tolerated (with a warning) in compatibility mode...
    typo = dict(SPEC_DICT, goalz=["oops"])
    spec_compat = fg.parse_spec(typo, "unit-typo")
    assert spec_compat.combos == 18

    # ...but rejected outright in strict mode (typo detection)
    try:
        fg.parse_spec(typo, "unit-typo", strict=True)
    except ValueError as e:
        assert "goalz" in str(e) and "strict" in str(e)
    else:
        raise AssertionError("strict mode should reject unknown top-level field 'goalz'")


def test_spec_version_strict_mode_rejects_nested_dict_typos():
    # Unknown keys inside dict-shaped goals[]/custom_vars[]/constraints[] entries:
    # tolerated (with a warning, silently falling through to inferred defaults) in
    # compatibility mode, rejected in strict mode — closing the gap where e.g. a
    # goal's "direktion" typo would otherwise silently fall back to infer_direction.
    cases = [
        ("goals", [{"key": "latency_ms", "direktion": "max"}], "direktion", "goal"),
        ("custom_vars", [{"code": 3, "msg": "x", "mesage": "oops"}], "mesage", "custom_var"),
        ("constraints", [{"id": "c1", "pairs": [{"A": "a1", "B": "b1"}], "polarty": "deny"}], "polarty", "constraint"),
    ]
    for key, value, typo, where_word in cases:
        spec_dict = dict(SPEC_DICT, **{key: value})
        spec_compat = fg.parse_spec(spec_dict, f"unit-{key}-typo")
        assert spec_compat.combos == 18                      # loaded; typo silently ignored
        try:
            fg.parse_spec(spec_dict, f"unit-{key}-typo", strict=True)
        except ValueError as e:
            assert typo in str(e) and "strict" in str(e) and where_word in str(e), (key, str(e))
        else:
            raise AssertionError(f"strict mode should reject unknown {key}[] field {typo!r}")

    # The un-typo'd direction key still wins over inference when present
    spec_ok = fg.parse_spec(dict(SPEC_DICT, goals=[{"key": "latency_ms", "direction": "max"}]), "unit-goal-ok")
    assert spec_ok.goals[0].direction == "max"               # explicit override honored, not inferred "min"


def test_spec_version_strict_mode_rejects_nested_slot_typos():
    # Unknown per-slot field (e.g. "flgas" instead of "flags"): tolerated with a
    # warning in compatibility mode, rejected in strict mode — same typo-detection
    # contract as top-level fields, one level down.
    nested_typo = {
        "title": "nested typo",
        "slots": [
            {"sheet": "A", "key": "a", "values": ["a1", "a2"], "flgas": ["FW_Optional"]},
            {"sheet": "B", "key": "b", "values": ["b1"]},
        ],
    }
    spec_compat = fg.parse_spec(nested_typo, "unit-nested-typo")
    assert spec_compat.combos == 2                           # loaded; typo'd flag silently ignored

    try:
        fg.parse_spec(nested_typo, "unit-nested-typo", strict=True)
    except ValueError as e:
        assert "flgas" in str(e) and "strict" in str(e) and "'A'" in str(e)
    else:
        raise AssertionError("strict mode should reject unknown slot field 'flgas'")


def test_expand_options():
    assert fg.expand_options("x=${1|2|3}") == ["x=1", "x=2", "x=3"]
    assert fg.expand_options("plain") == ["plain"]


def test_assemble_and_cartesian():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    full = list(fg.cartesian(spec))
    assert len(full) == 18
    line = fg.assemble(spec, ("a2", "b1", "c3"), prefix="ablation=A:a2")
    assert line == " ablation=A:a2 a=a2 b=b1 c=c3"
    assert not line.lstrip().startswith("FW_")          # Core-safe


def test_nwise_covers_all_pairs_and_shrinks():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    full = list(fg.cartesian(spec))
    target = _all_pairs(full)
    for reducer in (lambda c: fg.nwise_greedy(c, 2), lambda c: fg.nwise_optimal(c, 2)):
        red = reducer(full)
        assert len(red) < len(full)                     # actually reduced
        assert _all_pairs(red) == target                # but still pairwise-complete


def test_pick_for_budget():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    n, combos = fg.pick_n_for_budget(spec, budget=100)   # 18 <= 100 -> full
    assert n == 0 and len(combos) == 18
    n2, combos2 = fg.pick_n_for_budget(spec, budget=10)   # must reduce
    assert n2 >= 1 and len(combos2) <= 10


def test_build_validate_json_roundtrip():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # compact
        cp = d / "compact.xlsx"
        fg.build_compact(spec).save(cp)
        assert fg.validate_workbook(cp) == []
        # materialized
        rows = [fg.assemble(spec, c) for c in fg.cartesian(spec)]
        mp = d / "mat.xlsx"
        fg.build_materialized(spec, rows).save(mp)
        assert fg.validate_workbook(mp) == []
        # json round-trip preserves sheet count
        js = fg.write_json_sibling(mp)
        import json
        data = json.loads(js.read_text())
        assert len(data["sheets"]) == len(fg.openpyxl.load_workbook(mp).sheetnames)


def test_data_cells_never_start_fw():
    # even directive-valued slots stay Core-safe because of the ' key=' prefix
    spec = fg.parse_spec({"slots": [{"sheet": "V", "values": ["FW_Combi(2)", "FW_Permut"]}]}, "dsl")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "dsl.xlsx"
        fg.build_compact(spec).save(p)
        assert fg.validate_workbook(p) == []


def _candidate_rows(path):
    wb = fg.openpyxl.load_workbook(path)
    return [c[0] for c in wb["CANDIDATE"].iter_rows(values_only=True) if c[0] is not None]


def test_chunking_preserves_all_rows():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    rows = [fg.assemble(spec, c) for c in fg.cartesian(spec)]      # 18 rows
    with tempfile.TemporaryDirectory() as d:
        paths = fg.write_chunked(spec, rows, d, "unit", chunk_rows=5)  # 18 -> 4 chunks (5,5,5,3)
        assert len(paths) == 4
        assert [len(_candidate_rows(p)) for p in paths] == [5, 5, 5, 3]
        for p in paths:
            assert fg.validate_workbook(p) == []
        union = [r for p in paths for r in _candidate_rows(p)]
        assert union == rows                                      # nothing lost / reordered


def test_chunking_parallel_matches_sequential():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    rows = [fg.assemble(spec, c) for c in fg.cartesian(spec)]
    with tempfile.TemporaryDirectory() as d:
        seq = fg.write_chunked(spec, rows, Path(d) / "s", "u", chunk_rows=4, workers=1)
        par = fg.write_chunked(spec, rows, Path(d) / "p", "u", chunk_rows=4, workers=4)
        assert len(seq) == len(par)
        assert [_candidate_rows(s) for s in seq] == [_candidate_rows(p) for p in par]


def test_autofit_sets_dimensions():
    # a value with literal \n -> real in-cell newline -> taller row after autofit
    spec = fg.parse_spec({"slots": [{"sheet": "M", "values": ["one", "li\\nne\\ntwo"]}]}, "m")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "af.xlsx"
        fg.build_compact(spec, autofit=130).save(p)
        ws = fg.openpyxl.load_workbook(p)["M"]
        assert ws.column_dimensions["A"].width >= 10                      # width set
        assert ws.row_dimensions[2].height > ws.row_dimensions[1].height  # 3-line cell taller


def test_batch_json_dir():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    with tempfile.TemporaryDirectory() as d:
        xdir = Path(d) / "x"
        xdir.mkdir()
        for nm in ("a", "b"):
            fg.build_compact(spec).save(xdir / f"{nm}.xlsx")
        jdir = fg.xlsx_dir_to_json_dir(xdir, workers=1)                   # -> sibling x_json
        assert sorted(p.name for p in jdir.glob("*.json")) == ["a.json", "b.json"]
        import json
        data = json.loads((jdir / "a.json").read_text())
        assert data["workbook"] == "a.xlsx" and len(data["sheets"]) >= 6


def test_gui_core_run_generation():
    # GUI's generation core is Qt-free and testable directly (importing PyQt6 is
    # fine without a display; only QApplication needs a platform plugin).
    try:
        import fwgen_gui
    except ImportError:
        print("  (skip GUI core: PyQt6 not installed)")
        return
    with tempfile.TemporaryDirectory() as d:
        params = dict(specs_dir=HERE / "specs", out=d, selected={"k8s_rightsizing"},
                      strategy="ablation", n=0, optimal=False, budget=64,
                      fw_info="dup", clone_path="", json=False, materialize=False,
                      chunk_rows=0, workers=1, autofit=0.0)
        results, bad = fwgen_gui.run_generation(params)
        assert len(results) == 1 and bad == 0
        assert (Path(d) / "k8s_rightsizing_k1_ablation.xlsx").exists()


def test_preview_is_domain_facing():
    spec = fg.parse_spec(SPEC_DICT, "unit")
    pv = fg.render_preview(spec, k=4)
    assert "FW_" not in pv                      # no Core machinery shown
    assert "a=a1" in pv and "baseline" in pv     # candidate lines + baseline tag
    assert fg.sample_combos(spec, 1)[0] == spec.baseline


def test_authoring_toml_roundtrip():
    import tomllib
    data = fg.build_spec_dict("auth",
        [("MODEL", "model", ["gpt-4o", "assistant"]), ("STYLE", None, ["terse", "verbose"])],
        title="Authoring", goals=["accuracy", "cost"])
    sp = fg.parse_spec(tomllib.loads(fg.dump_spec_toml(data)), "auth")
    assert [s.sheet for s in sp.slots] == ["MODEL", "STYLE"]
    assert sp.slots[1].key == "style"                       # auto key
    assert [g.direction for g in sp.goals] == ["max", "min"]  # accuracy/cost inference
    # tricky values (quotes) survive
    waf = fg.build_spec_dict("w", [("SQLI", "sqli", ["' OR 1=1--", 'a"b'])])
    sp2 = fg.parse_spec(tomllib.loads(fg.dump_spec_toml(waf)), "w")
    assert sp2.slots[0].values == ["' OR 1=1--", 'a"b']
    # scaffold template (from example) parses
    fg.parse_spec(tomllib.loads(fg.scaffold_template("demo", sp)), "demo")


# --- Core verb coverage: the generator can emit EVERY combination rule ---------

ALL_VERBS = ["FW_Combi(1)", "FW_Combi(2)", "FW_Combi(all)", "FW_CombiR(2)",
             "FW_Permut", "FW_Permut(2)",
             "FW_Permut(PermutationGenerator.TreatDuplicatesAs.IDENTICAL)",
             "FW_PermutR(2)", "FW_Subsets", "FW_Subsets_EXACT(2)",
             "FW_Subsets_RANGE(1,2)", "FW_Subsets_BEFORE(2)",
             "FW_Subsets_AFTER(1)", "FW_Subsets_GIVEN(1,3)",
             "FW_Cartes(OTHER)", "FW_Cartes_first(OTHER)", "FW_Separator(OTHER)"]


def test_grammar_recognizes_every_core_verb():
    for v in ALL_VERBS:
        assert fg.is_core_verb(v), f"grammar rejected valid Core verb {v!r}"
    assert fg.is_core_verb("FW_Group\nFW_ReplaceRE(\"a\",\"b\")")          # multi-line Group
    assert fg.is_core_verb("FW_(,,A,,B,,,,M:N)")                          # brace joiner
    assert not fg.is_core_verb("FW_Nonsense(9)")
    assert not fg.is_core_verb("FW_Combi(")                                 # malformed
    assert fg.is_core_flag("FW_Optional") and fg.is_core_flag("FW_Concatenator=,")
    assert not fg.is_core_flag("FW_Combi(1)")


def test_per_slot_verb_emit_and_validate():
    # each unary/binary verb, chosen per-slot, builds + validates + is emitted in FW_Seq
    with tempfile.TemporaryDirectory() as d:
        for v in ALL_VERBS:
            slots = [{"sheet": "S", "values": ["x", "y", "z"], "verb": v}]
            if "OTHER" in v:                       # binary verbs need the operand sheet present
                slots.append({"sheet": "OTHER", "values": ["o1", "o2"]})
            spec = fg.parse_spec({"slots": slots}, "v")
            assert spec.slots[0].verb == v
            p = Path(d) / "v.xlsx"
            fg.build_compact(spec).save(p)
            assert fg.validate_workbook(p) == [], (v, fg.validate_workbook(p))
            seq = list(fg.openpyxl.load_workbook(p)["FW_Seq"].iter_rows(values_only=True))
            assert any(v in [str(c) for c in row] for row in seq), f"{v} not emitted"


def test_default_verb_preserved_byte_for_byte():
    # no `verb` given -> still FW_Combi(1); row layout identical to the historical output
    spec = fg.parse_spec({"slots": [{"sheet": "S", "values": ["a", "b"]}]}, "d")
    assert spec.slots[0].verb == "FW_Combi(1)" and spec.slots[0].flags == ()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "d.xlsx"
        fg.build_compact(spec).save(p)
        row0 = next(iter(fg.openpyxl.load_workbook(p)["FW_Seq"].iter_rows(values_only=True)))
        assert [c for c in row0 if c is not None] == ["S", "FW_Reuse", "FW_Combi(1)"]


def test_slot_flags_emitted():
    spec = fg.parse_spec({"slots": [{"sheet": "S", "values": ["a"], "verb": "FW_Combi(1)",
                                     "flags": ["FW_Optional"]}]}, "f")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.xlsx"
        fg.build_compact(spec).save(p)
        cells = [str(c) for r in fg.openpyxl.load_workbook(p)["FW_Seq"].iter_rows(values_only=True) for c in r if c]
        assert "FW_Optional" in cells and "FW_Reuse" in cells and "FW_Combi(1)" in cells


def test_bad_verb_and_flag_rejected():
    for bad in ({"slots": [{"sheet": "S", "values": ["a"], "verb": "FW_Nonsense(9)"}]},
                {"slots": [{"sheet": "S", "values": ["a"], "flags": ["FW_Bogus"]}]}):
        try:
            fg.parse_spec(bad, "x")
            assert False, f"should have raised for {bad}"
        except ValueError:
            pass


def test_cartes_operand_validation():
    ok = fg.parse_spec({"slots": [{"sheet": "A", "values": ["a1", "a2"], "verb": "FW_Cartes(B)"},
                                  {"sheet": "B", "values": ["b1"]}]}, "ok")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.xlsx"
        fg.build_compact(ok).save(p)
        assert fg.validate_workbook(p) == []


def test_brace_joiner_seq_extra():
    # brace M:N joiner over two excluded operand sheets builds + validates
    spec = fg.parse_spec({
        "slots": [{"sheet": "A", "values": ["a1", "a2"], "flags": ["FW_Exclude"]},
                  {"sheet": "B", "values": ["b1", "b2"], "flags": ["FW_Exclude"]},
                  {"sheet": "JOINED", "values": [" placeholder"]}],
        "seq_extra": [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]],
    }, "brace")
    assert spec.seq_extra and "FW_(" in spec.seq_extra[0][-1]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "brace.xlsx"
        fg.build_compact(spec).save(p)
        assert fg.validate_workbook(p) == []
    # brace referencing an UNDECLARED operand sheet is rejected at parse time
    try:
        fg.parse_spec({"slots": [{"sheet": "A", "values": ["a1"]}],
                       "seq_extra": [["A", "FW_(,,A,,ZZZ,,,,M:N)"]]}, "b2")
        assert False, "should reject undeclared brace operand"
    except ValueError:
        pass


def test_nested_braces_are_first_class_fwgen_verbs():
    forms = (
        "FW_(,,FW_(),,RIGHT,,,,M:N)",
        "FW_(,,LEFT,,FW_(),,,,M:N)",
        "FW_(,,FW_(),,FW_(),,,,M:N)",
        "FW_(,,FW_()G,,RIGHT,,,,M:N)",
        "FW_(,,LEFT,,FW_()G,,,,M:N)",
        "FW_(,,FW_()G,,FW_()G,,,,M:N)",
    )
    assert all(fg.is_core_verb(form) for form in forms)
    assert fg.verb_sheet_operands(
        "FW_(START,,FW_(),REL,RIGHT,,END,SEP,M:N)"
    ) == ["START", "REL", "RIGHT", "END", "SEP"]


def test_brace_all_fields_operands_checked():
    # the brace has start/rel/sep/end too — verb_sheet_operands must surface ALL sheet fields
    ops = fg.verb_sheet_operands("FW_(START,,A,REL,B,,END,SEP,1:N)")
    assert set(ops) == {"START", "A", "REL", "B", "END", "SEP"}, ops
    # a full-field brace validates when every referenced sheet is declared (E1/E2 excluded)
    spec = fg.parse_spec({"slots": [
        {"sheet": "START", "values": ["<<"]}, {"sheet": "REL", "values": ["->"]},
        {"sheet": "END", "values": [">>"]}, {"sheet": "SEP", "values": ["|"]},
        {"sheet": "A", "values": ["a1", "a2"], "flags": ["FW_Exclude"]},
        {"sheet": "B", "values": ["b1", "b2"], "flags": ["FW_Exclude"]},
        {"sheet": "J", "values": [" x"]}],
        "seq_extra": [["J", "FW_(START,,A,REL,B,,END,SEP,1:N)"]]}, "fullbrace")
    assert spec.seq_extra
    # a missing start/rel/sep/end sheet is now caught (was silently ignored before)
    try:
        fg.parse_spec({"slots": [{"sheet": "A", "values": ["a1"], "flags": ["FW_Exclude"]},
                                 {"sheet": "B", "values": ["b1"], "flags": ["FW_Exclude"]},
                                 {"sheet": "J", "values": [" x"]}],
                       "seq_extra": [["J", "FW_(NOPE,,A,,B,,,,M:N)"]]}, "missingstart")
        assert False, "should reject undeclared brace start sheet"
    except ValueError:
        pass


def test_separator_and_group_authoring():
    # FW_Separator + FW_Group are first-class slot fields → correct FW_Seq emission
    spec = fg.parse_spec({"slots": [
        {"sheet": "GLUE", "values": [" + "]},
        {"sheet": "OPS", "values": ["a", "b", "c"], "verb": "FW_Combi(2)",
         "separator": "GLUE", "group_replace": [["FOO", "BAR"], ["BAZ", ""]]}]}, "joincase")
    ops = next(s for s in spec.slots if s.sheet == "OPS")
    assert ops.separator == "GLUE"
    assert ops.group_replace == (("FOO", "BAR"), ("BAZ", ""))
    wb = fg.build_compact(spec)
    cells = [c.value for r in wb["FW_Seq"].iter_rows() if r[0].value == "OPS" for c in r if c.value]
    assert "FW_Separator(GLUE)" in cells
    assert any(str(c).startswith("FW_Group") and "FW_ReplaceRE" in str(c) for c in cells)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sg.xlsx"; wb.save(p)
        assert fg.validate_workbook(p) == []
    # JSON emitter parity
    js = fg.build_compact_core_json(spec)
    opsrow = next(r for r in js["sheets"]["FW_Seq"] if r and r[0] == "OPS")
    assert "FW_Separator(GLUE)" in opsrow and any("FW_Group" in str(c) for c in opsrow)
    # undeclared separator sheet rejected
    try:
        fg.parse_spec({"slots": [{"sheet": "X", "values": ["x"], "separator": "NOPE"}]}, "badsep")
        assert False, "should reject undeclared separator sheet"
    except ValueError:
        pass


def test_verb_coverage_suite_bounded_and_valid():
    specs = fg.verb_coverage_specs()
    assert len(specs) >= 12
    for s in specs:                         # every chunk tiny — NO cartesian explosion
        assert len(s.slots) <= fg.COVERAGE_MAX_SLOTS
        assert max(len(sl.values) for sl in s.slots) <= fg.COVERAGE_MAX_VALUES
    with tempfile.TemporaryDirectory() as d:
        man = fg.build_verb_coverage(d)
        assert len(man) == len(specs) + 1          # + the 10+-row interop workbook
        assert all(m["valid"] == "OK" for m in man), [m for m in man if m["valid"] != "OK"]


def test_verb_output_count_known():
    assert fg.verb_output_count("FW_Combi(1)", 3) == 3
    assert fg.verb_output_count("FW_Combi(2)", 3) == 3            # C(3,2)
    assert fg.verb_output_count("FW_Combi(all)", 3) == 7         # 2^3-1
    assert fg.verb_output_count("FW_CombiR(2)", 2) == 3          # C(2+2-1,2)
    assert fg.verb_output_count("FW_Permut", 3) == 6            # 3!
    assert fg.verb_output_count("FW_Permut(2)", 3) == 6        # P(3,2)
    assert fg.verb_output_count("FW_PermutR(2)", 2) == 4        # 2^2
    assert fg.verb_output_count("FW_Subsets", 3) == 8          # 2^3
    assert fg.verb_output_count("FW_Subsets_EXACT(2)", 3) == 3
    assert fg.verb_output_count("FW_Subsets_RANGE(1,2)", 3) == 6  # C(3,1)+C(3,2)
    assert fg.verb_output_count("FW_Cartes(X)", 2, other_n=3) == 6


def test_interop_10plus_rows_bounded():
    # 10+ FW_Seq rows of DIFFERENT verbs interoperating, with the inner combined
    # product kept SMALL (no explosion).
    spec = fg.verb_interop_spec()
    rows = len(spec.slots) + len(spec.seq_extra)
    assert rows >= 10, f"interop has only {rows} FW_Seq rows"
    assert len({s.verb for s in spec.slots}) >= 5            # a real verb mix
    est = fg.estimate_core_combos(spec)
    assert est <= fg.INTEROP_MAX_CORE_ROWS, f"interop inner product {est} too large"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "interop.xlsx"
        fg.build_compact(spec).save(p)
        assert fg.validate_workbook(p) == []
        seq = [r for r in fg.openpyxl.load_workbook(p)["FW_Seq"].iter_rows(values_only=True) if any(r)]
        assert len(seq) >= 10


def test_reduce_many_slots_is_optimal():
    # the 'optimal combinations for many parameters' path: 10 cartesian-leaf slots,
    # full = 2^10 = 1024; pairwise covering array is a tiny, still-complete subset.
    slots = [{"sheet": f"S{i}", "values": ["a", "b"]} for i in range(10)]
    spec = fg.parse_spec({"slots": slots}, "many")
    full = list(fg.cartesian(spec))
    assert len(full) == 1024
    red = fg.nwise_optimal(full, 2)
    assert len(red) < 30                                     # optimal pairwise is tiny
    assert _all_pairs(red) == _all_pairs(full)               # still pairwise-complete


# --- code decomposition → TOML → Bundle (the cold-start "quick start") ---------

def test_raw_mode_preserves_code_verbatim():
    # build_compact(raw) must NOT apply the \n/\t -> char substitution (would corrupt code)
    code = 'x = "a\\nb"  # literal backslash-n stays 2 chars'   # contains \n as 2 chars
    spec = fg.parse_spec({"slots": [{"sheet": "C", "values": [code], "raw": True}]}, "raw")
    assert spec.slots[0].raw is True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.xlsx"
        fg.build_compact(spec).save(p)
        got = fg.openpyxl.load_workbook(p)["C"].cell(1, 1).value
        assert got == code, (got, code)                      # verbatim
        assert fg.validate_workbook(p) == []


def test_decompose_byte_preserving():
    for fname in ("code_decompose.py", "fwgen_cli.py", "xlsx_autofit.py"):
        src = (HERE / fname).read_text(encoding="utf-8")
        pieces = cd.decompose(src)
        assert len(pieces) >= 2, fname
        assert "".join(p.code for p in pieces) == src, f"{fname} not byte-preserving"


def test_decompose_detects_indirect_interaction():
    src = "def f(x):\n    return x + 1\n\n\ndef g(y):\n    return f(y) * 2\n"
    pieces = cd.decompose(src, "py")
    assert "".join(p.code for p in pieces) == src
    g = next(p for p in pieces if p.name == "g")
    assert "f" in g.uses and "interacts" in g.note and "f" in g.note   # g uses f → flagged


def test_decompose_toml_roundtrips_builds_and_reassembles():
    src = (HERE / "xlsx_autofit.py").read_text(encoding="utf-8")
    pieces = cd.decompose(src)
    # the emitted TOML parses back through fwgen, all slots raw, default cartesian verb
    spec = fg.parse_spec(cd.to_spec_dict(pieces, "xlsx_autofit"), "dec")
    assert all(s.raw for s in spec.slots)
    assert fg.estimate_core_combos(spec) == 1                # baseline-only = the original program
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "dec.xlsx"
        fg.build_compact(spec).save(p)
        assert fg.validate_workbook(p) == []
        wb = fg.openpyxl.load_workbook(p)
        reassembled = "".join(wb[s.sheet].cell(1, 1).value for s in spec.slots)
        assert reassembled == src                            # pieces concatenate back to source


def test_decompose_java_method_level():
    src = (HERE / "scenarios" / "api_orders" / "harness.java").read_text(encoding="utf-8")
    pieces = cd.decompose(src)                              # auto → java
    assert "".join(p.code for p in pieces) == src           # byte-preserving
    assert pieces[0].kind == "header" and pieces[-1].kind == "footer"
    methods = [p.name for p in pieces if p.kind == "method"]
    assert "main" in methods and len(methods) >= 4          # real method-level granularity
    assert any(p.kind == "field" and p.name == "FW_VAR" for p in pieces)
    spec = fg.parse_spec(cd.to_spec_dict(pieces, "harness"), "j")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "j.xlsx"
        fg.build_compact(spec).save(p)
        assert fg.validate_workbook(p) == []
        wb = fg.openpyxl.load_workbook(p)
        assert "".join(wb[s.sheet].cell(1, 1).value for s in spec.slots) == src   # reassembles


def test_landing_specs_build_and_validate():
    specs = fg.load_specs_dir(HERE / "landing")                     # the quick-start examples
    assert len(specs) >= 2
    with tempfile.TemporaryDirectory() as d:
        for spec in specs:
            p = Path(d) / f"{spec.name}.xlsx"
            fg.build_compact(spec).save(p)
            assert fg.validate_workbook(p) == [], (spec.name, fg.validate_workbook(p))


def test_handshake_prediction_and_emit():
    spec = fg.parse_spec({
        "title": "hs", "args": ["mode=hs"],
        "custom_vars": [{"code": 2, "msg": "violated"}],
        "slots": [
            {"sheet": "FRAME", "verb": "FW_Combi(1)", "raw": True, "values": ["a\n"]},
            {"sheet": "OPS", "verb": "FW_Permut", "raw": True, "values": ["x\n", "y\n"]},
            {"sheet": "DROP", "verb": "FW_Combi(1)", "flags": ["FW_Exclude"], "values": ["z"]},
        ]}, "hs")
    # the FW_Exclude slot is dropped from fw_final → not a combos column; 2 mandatory → 2 combos
    assert fg.results_combos_columns(spec) == ["combos1_FRAME", "combos2_OPS"]
    cols = fg.predict_results_columns(spec)
    assert cols[:6] == fg.RESULTS_BASE_COLUMNS and len(cols) == 8
    sql = fg.predict_insert_sql(spec, "hs")
    assert sql.count("?") == 8 and 'public."hs"' in sql and '"combos2_OPS"' in sql
    rep = fg.handshake_report(spec)
    assert rep["mode"] == "FW_VAR" and rep["n_combos"] == 2 and rep["fwvar_shift"] == 1
    assert rep["warnings"] == []                              # code 2 ≤ 2 combos → fits
    # a verdict code larger than #combos columns must warn (positional FW_VAR overflow)
    spec2 = fg.parse_spec({"custom_vars": [{"code": 5, "msg": "x"}],
                           "slots": [{"sheet": "A", "raw": True, "values": ["a"]},
                                     {"sheet": "B", "raw": True, "values": ["b"]}]}, "hs2")
    assert any("overflow" in w for w in fg.handshake_report(spec2)["warnings"])
    with tempfile.TemporaryDirectory() as d:
        fg.emit_handshake(spec, d, table_name="hs",
                          db_url="jdbc:postgresql://localhost:5432/hs?user=postgres&password=TEST_FIXTURE_NOT_A_CREDENTIAL")
        assert (Path(d) / "arguments" / "fwVar.shift").read_text() == "1"     # NON-empty (Reader emits empty)
        assert "jdbc:postgresql" in (Path(d) / "resultsDbURL" / "resultsDbURL.properties").read_text()
        assert (Path(d) / "sqlTemplate" / "insert.sql").read_text().count("?") == 8
        assert "class RunMeFirstOnce" in (Path(d) / "runFirstOnce" / "runmefirstonce.first").read_text()


def test_load_specs_dir_skips_bundle_artifact_json():
    """Regression for BUG-5: `bundle plan <dir>` writes plan.json INTO the spec
    dir by default, and the dir loader accepts .json -- so a later run/plan would
    parse the plan output as a spec and crash (KeyError 'values'). load_specs_dir
    must skip the Bundle's own artifact JSONs (schema starts 'bundle.'/'analyzer.')
    while still loading a genuine .json spec."""
    import json
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # an authored spec
        (d / "spec.toml").write_text(
            "[[slots]]\nsheet='A'\nkey='a'\nvalues=['a1','a2']\n", encoding="utf-8")
        # the Bundle's own plan output dropped alongside it (must be skipped)
        (d / "plan.json").write_text(json.dumps({
            "schema": "bundle.plan/v1", "spec_name": "spec", "cardinality": {}}), encoding="utf-8")
        # a run.json artifact too (must be skipped)
        (d / "run.json").write_text(json.dumps({"schema": "bundle.run/v1"}), encoding="utf-8")
        specs = fg.load_specs_dir(d)
        assert [s.name for s in specs] == ["spec"], [s.name for s in specs]
        # a genuine .json spec is still loaded (no bundle/analyzer schema key)
        (d / "more.json").write_text(json.dumps({
            "slots": [{"sheet": "B", "key": "b", "values": ["b1"]}]}), encoding="utf-8")
        names = sorted(s.name for s in fg.load_specs_dir(d))
        assert names == ["more", "spec"], names


def test_load_specs_dir_skips_constraint_sidecar_json():
    import json
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "spec.toml").write_text(
            "[[slots]]\nsheet='A'\nkey='a'\nvalues=['a1']\n", encoding="utf-8")
        sidecar = {"version": 1, "params": {}, "constraints": []}
        (d / "sidecar.json").write_text(json.dumps(sidecar), encoding="utf-8")
        (d / "spec.sidecar.generated.json").write_text(json.dumps(sidecar), encoding="utf-8")
        specs = fg.load_specs_dir(d)
        assert [s.name for s in specs] == ["spec"], [s.name for s in specs]


def test_load_specs_dir_skips_selfposed_metadata_and_jsonl():
    import json
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "spec.toml").write_text(
            "[[slots]]\nsheet='A'\nkey='a'\nvalues=['a1']\n", encoding="utf-8")
        (d / "training.jsonl").write_text('{"prompt":"not a spec"}\n', encoding="utf-8")
        (d / "result_card.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        (d / "scenario.graph.json").write_text(json.dumps({"nodes": []}), encoding="utf-8")
        meta = d / "meta"
        meta.mkdir()
        (meta / "result_card.json").write_text(json.dumps({"schema": "bundle.selfposed-result-card/v1"}),
                                                encoding="utf-8")
        specs = fg.load_specs_dir(d)
        assert [s.name for s in specs] == ["spec"], [s.name for s in specs]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")


# --------------------------------------------------------------------------
# pick_n_for_budget: search order
#
# The original implementation walked strengths from k-1 downwards, so it
# computed the most expensive reduction first and discarded it. For a small
# budget -- the case that matters against a metered target -- the answer is a
# low strength, so every costly high-t reduction ran before reaching it. With
# `optimal=True` that did not merely run slowly, it did not finish: >20 min on a
# 10,368-row product where a single t=2 call takes 1.0 s.
#
# The fix walks upwards and stops at the first overrun, which is exact rather
# than heuristic: suite size is monotone non-decreasing in t, because a
# t-covering array is also a (t-1)-covering array and the greedy reducer keeps a
# combo iff it introduces a new t-tuple.
# --------------------------------------------------------------------------
_BUDGET_SPEC = {
    "title": "budget search",
    "slots": [{"sheet": f"S{i}", "verb": "FW_Combi(1)", "values": ["a", "b", "c"]}
              for i in range(6)],
}


def _reference_high_to_low(spec, allc, budget, optimal):
    """The original search order, kept as the correctness oracle."""
    for n in range(len(spec.slots) - 1, 0, -1):
        red = fg.reduce_combos(allc, n, optimal)
        if len(red) <= budget:
            return n, len(red)
    return 1, len(fg.reduce_combos(allc, 1, optimal))


def _covers_all_tuples(reduced, full, t):
    import itertools

    def tuples(combos):
        seen = set()
        for combo in combos:
            for idx in itertools.combinations(range(len(combo)), t):
                seen.add(tuple((i, combo[i]) for i in idx))
        return seen

    return tuples(reduced) == tuples(full)


def test_budget_search_matches_the_original_order_exactly():
    """Optimising the search must not change which strength is chosen."""
    spec = fg.parse_spec(_BUDGET_SPEC, "budget")
    allc = list(fg.cartesian(spec))
    for budget in (5, 12, 30, 80, 250, 700):
        n_new, reduced = fg.pick_n_for_budget(spec, budget)
        n_ref, size_ref = _reference_high_to_low(spec, allc, budget, False)
        assert (n_new, len(reduced)) == (n_ref, size_ref), (
            f"budget={budget}: walking up gave t={n_new}/{len(reduced)}, "
            f"walking down gave t={n_ref}/{size_ref}")


def test_budget_search_result_fits_the_budget_and_still_covers():
    spec = fg.parse_spec(_BUDGET_SPEC, "budget")
    allc = list(fg.cartesian(spec))
    for budget in (12, 80, 250):
        n, reduced = fg.pick_n_for_budget(spec, budget)
        assert len(reduced) <= budget or n == 1     # t=1 is the floor, may overrun
        assert _covers_all_tuples(reduced, allc, n)


def test_full_product_is_returned_untouched_when_it_already_fits():
    spec = fg.parse_spec(_BUDGET_SPEC, "budget")
    n, reduced = fg.pick_n_for_budget(spec, budget=10_000)
    assert n == 0 and len(reduced) == spec.combos


def test_budget_search_never_computes_a_strength_above_the_answer():
    """The actual regression guard, and the reason the fix matters.

    A timing bound would be vacuous here: on a spec small enough for a unit test
    the old order is merely slower, not pathological, so a 60-second assertion
    passes either way. What distinguishes the two orders is *which* reductions
    they compute — the old one starts at t=k-1 and works down, so on a small
    budget it builds every expensive high-strength covering array and throws it
    away. That is exactly what did not finish on a wide grid.

    So assert the shape of the search, not its duration: nothing above
    answer+1 may ever be computed.
    """
    spec = fg.parse_spec(_BUDGET_SPEC, "budget")
    requested: list[int] = []
    original = fg.reduce_combos

    def spy(combos, n, optimal=False):
        requested.append(n)
        return original(combos, n, optimal)

    fg.reduce_combos = spy
    try:
        n, reduced = fg.pick_n_for_budget(spec, budget=40, optimal=True)
    finally:
        fg.reduce_combos = original

    assert requested, "the search computed nothing"
    assert max(requested) <= n + 1, (
        f"chose t={n} but computed strengths up to t={max(requested)} "
        f"({sorted(set(requested))}) — the search is walking down from k-1 again")
    assert len(reduced) <= 40


def test_max_strength_caps_the_search():
    spec = fg.parse_spec(_BUDGET_SPEC, "budget")
    n, _reduced = fg.pick_n_for_budget(spec, budget=10_000 - 1, max_strength=2)
    assert n <= 2
