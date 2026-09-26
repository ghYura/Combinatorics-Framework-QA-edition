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

"""Legacy XLSX input — the Framework's original format, processed alongside TOML — and
sizing every sheet from the FW_Seq program the Core actually runs.

Covers: SeqParser's rules (the target persists into continuation rows, flags accumulate
and the first of FW_Exclude/FW_Optional decides, the last directive row wins, the dual
verb is appended to a single combo-rule verb); a workbook loads as a Spec with its
passive sheets; grouped FW_Cartes(X) = grouped rows x X; verb chains; FW_Reuse /
FW_ReuseTableOnly; the one-spec-input rule; the plan's empty-sheet warning.

Every EXACT count pinned here was measured on the Core (core.log `[DIAG] Sheet ... rows
AFTER distinctify`, 2026-09-26) for the workbook the test rebuilds.

Run: `python3 -m pytest test_fwgen_legacy_xlsx.py -q` (no DB / no Bundle run).
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

openpyxl = pytest.importorskip("openpyxl")

import fwgen as fg                                             # noqa: E402
import fwseq_graph as fwg                                      # noqa: E402
from bundle.commands.plan import _plan_warnings                # noqa: E402
from bundle.errors import PreflightError                       # noqa: E402
from bundle.optional_contract import contract_from_spec        # noqa: E402
from bundle.stages import resolve_spec_input                   # noqa: E402

TAIL = "_v = 0\nFW_VAR = _v\nFW_CUSTOM_VAR = _v\nprint('FW_VAR=0')\n"


def _workbook(path: Path, seq_rows, sheets: dict) -> Path:
    """A workbook in the author's layout: FW_Seq (sheet in A, flags in B/C, directives
    from D), the control sheets, and one data sheet per entry of `sheets`."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FW_Seq"
    for r, row in enumerate(seq_rows, start=1):
        for c, v in enumerate(row, start=1):
            if v is not None:
                ws.cell(r, c, v)
    names = wb.create_sheet("FW_SheetNames")
    for r, sheet in enumerate(sheets, start=1):
        names.cell(r, 1, sheet)
        names.cell(r, 2, "FW_EMPTY_STRING")
        names.cell(r, 3, "FW_EMPTY_STRING")
    wb.create_sheet("FW_RunMeFirstOnce").cell(1, 1, "print('once')")
    wb.create_sheet("FW_Arguments").cell(1, 1, "noargs")
    cv = wb.create_sheet("FW_CUSTOM_VAR")
    cv.cell(1, 1, 2)
    cv.cell(1, 2, "FWCUSTOMVAR=2 unexpected sequence")
    for sheet, values in sheets.items():
        s = wb.create_sheet(sheet)
        for r, v in enumerate(values, start=1):
            s.cell(r, 1, v)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _cartes_group_workbook(tmp_path: Path) -> Path:
    return _workbook(tmp_path / "w1" / "w1.xlsx", [
        ["HEAD", None, None, "FW_Combi(1)"],
        ["G", None, None, "FW_Combi(1)", "FW_Combi(1)", "FW_Group", "FW_Cartes(B2)"],
        ["H", None, None, "FW_Combi(1)", "FW_Combi(1)", "FW_Group", "FW_Cartes_first(B2)"],
        ["TAIL", None, None, "FW_Combi(1)"],
    ], {"HEAD": ["S = []\n"], "G": ["S.append('g1')\n", "S.append('g2')\n"],
        "H": ["S.append('h1')\n", "S.append('h2')\n"],
        "B2": ["S.append('x1')\n", "S.append('x2')\n"], "TAIL": [TAIL]})


# (values, program, Core rows) — the w5_chain_probe workbook; None = not provably exact
CHAIN_PROBES = {
    "A2": (2, ["FW_Combi(size)", "FW_Combi(1)", "FW_Combi(2)"], 1),
    "B2": (2, ["FW_Combi(size)", "FW_Combi(1)", "FW_Combi(2)", "FW_Combi(alL)"], 0),
    "C3": (3, ["FW_Combi(size)", "FW_Combi(2)"], 3),
    "D3": (3, ["FW_Combi(size)", "FW_Subsets"], 8),
    "E3": (3, ["FW_Combi(size)", "FW_Permut()"], 6),
    "F3": (3, ["FW_Combi(size)", "FW_CombiR(2)"], 6),
    "G3": (3, ["FW_Combi(size)", "FW_PermutR(2)"], 9),
    "H2": (2, ["FW_Combi(size)", "FW_Combi(1)", "FW_Combi(2)", "FW_Group", "FW_CombiR(2)"], 0),
    "I2": (2, ["FW_Combi(size)", "FW_Combi(1)", "FW_Combi(2)", "FW_Combi(alL)", "FW_Group",
               "FW_CombiR(2)"], 0),
    "J3": (3, ["FW_Combi(1)", "FW_Combi(2)"], 1),
    "K3": (3, ["FW_Combi(2)", "FW_Combi(1)"], None),        # measured 3: bounded, not exact
    "L3": (3, ["FW_Combi(size)", "FW_Combi(1)", "FW_Subsets"], 4),
}


def _chain_probe_workbook(tmp_path: Path) -> Path:
    seq = [["HEAD", None, None, "FW_Combi(1)"]]
    sheets = {"HEAD": ["S = []\n"]}
    for name, (n, program, _) in CHAIN_PROBES.items():
        seq.append([name, None, None] + program)
        sheets[name] = [f"S.append('{name}{i}')\n" for i in range(n)]
    seq.append(["TAIL", None, None, "FW_Combi(1)"])
    sheets["TAIL"] = [TAIL]
    return _workbook(tmp_path / "w5" / "w5.xlsx", seq, sheets)


# ------------------------------------------------------------------ SeqParser --
def test_seq_parser_rules():
    prog = fg.parse_fw_seq_rows([
        ["A", "FW_Optional", None, "FW_Combi(1)"],
        [None, "FW_Exclude"],                        # continues A: flags accumulate
        ["FW_Subsets", "FW_Permut()"],               # continues A: the last directive row wins
        ["B", "FW_Combi(2)"],                        # a single combo-rule verb gets its dual
        ["C", "FW_Permut"],                          # bare FW_Permut is not a combo-rule verb
    ], ["A", "B", "C"])
    assert prog["A"]["flags"] == ["FW_Optional", "FW_Exclude"]
    assert prog["A"]["role"] == "optional"           # the first of Optional/Exclude decides
    assert prog["A"]["directives"] == ["FW_Subsets", "FW_Permut()"]
    assert prog["A"]["row"] == 2
    assert prog["B"]["directives"] == ["FW_Combi(2)", "FW_Combi(2)"]
    assert prog["C"]["directives"] == ["FW_Permut"]


def test_author_case_insensitive_verb_arguments():
    for verb in ("FW_Combi(alL)", "FW_CombiR(siZe)", "FW_PermutR(size)", "FW_Cartes_first(B2)"):
        assert fg.is_core_verb(verb), verb
    assert fg.verb_output_count("FW_Combi(alL)", 3) == 7
    assert fg.verb_output_count("FW_CombiR(siZe)", 3) == 10          # C(2n-1, n)
    assert fg.verb_output_count("FW_PermutR(size)", 3) == 27         # n^n


# ------------------------------------------------------------------- workbook --
def test_workbook_loads_as_a_spec_with_passive_sheets(tmp_path):
    spec = fg.load_spec(_cartes_group_workbook(tmp_path))
    assert spec.source_format == "xlsx" and fg.uses_program_sizing(spec)
    assert [s.sheet for s in spec.slots] == ["HEAD", "G", "H", "TAIL"]
    assert set(spec.passive_sheets) == {"B2"}                        # no FW_Seq row: a resource
    assert spec.program["G"]["directives"] == ["FW_Combi(1)", "FW_Combi(1)", "FW_Group", "FW_Cartes(B2)"]


def test_grouped_cartes_pairs_the_grouped_rows_with_the_operand(tmp_path):
    """Author's intent: FW_Group then FW_Cartes(B2) = grouped rows x B2 (2 x 2 per sheet);
    the Core produced fw_final = 16 for this workbook."""
    spec = fg.load_spec(_cartes_group_workbook(tmp_path))
    sizings = fg.program_sizings(spec)
    for sheet in ("G", "H"):
        assert sizings[sheet].est.mode == fg.CardinalityMode.EXACT
        assert sizings[sheet].hist == {2: 4}                          # one grouped row + one B2 code
    plan = fg.spec_cardinality_plan(spec)
    assert (plan.mandatory.mode, plan.mandatory.value) == (fg.CardinalityMode.EXACT, 16)


def test_verb_chains_are_sized_like_the_core_runs_them(tmp_path):
    sizings = fg.program_sizings(fg.load_spec(_chain_probe_workbook(tmp_path)))
    for sheet, (_, program, core_rows) in CHAIN_PROBES.items():
        est = sizings[sheet].est
        if core_rows is None:
            assert est.mode == fg.CardinalityMode.BOUNDED and est.lower <= 3 <= est.upper, sheet
        else:
            assert (est.mode, est.value) == (fg.CardinalityMode.EXACT, core_rows), (sheet, est.formula)


def test_plan_warns_about_sheets_that_end_empty(tmp_path):
    spec = fg.load_spec(_chain_probe_workbook(tmp_path))
    warnings = _plan_warnings(spec, fg.spec_cardinality_plan(spec))
    empty = [w for w in warnings if "end EMPTY" in w]
    assert len(empty) == 1 and "B2, H2, I2" in empty[0] and "PARTIAL" in empty[0]


def test_optional_verb_chain_contract_is_an_upper_bound(tmp_path):
    """FW_Subsets, FW_Permut + the Core's appended FW_Subsets over 3 values: the Core built
    16 rows (every ordered subset); the static bound is 78, so the run measures the
    multiplier from Core's fw_opt tables (1 + 16 = 17 candidates per fw_final row)."""
    spec = fg.load_spec(_workbook(tmp_path / "w4" / "w4.xlsx", [
        ["HEAD", None, None, "FW_Combi(1)"],
        ["STEP", "FW_Optional", None, "FW_Subsets", "FW_Permut"],
        ["TAIL", None, None, "FW_Combi(1)"],
    ], {"HEAD": ["S = []\n"], "STEP": ["S.append('a')\n", "S.append('b')\n", "S.append('c')\n"],
        "TAIL": [TAIL]}))
    assert spec.program["STEP"]["directives"] == ["FW_Subsets", "FW_Permut", "FW_Subsets"]
    contract = contract_from_spec(spec)
    assert contract.exact is False
    assert contract.slot_value_counts == (78,)


# ------------------------------------------------------------------ FW_Reuse --
def test_reuse_flags_follow_the_author_semantics():
    assert fg._reuse_flag_cell(()) == "FW_Reuse"
    assert fg._reuse_flag_cell(("FW_ReuseTableOnly",)) == "FW_ReuseTableOnly"
    assert fg._reuse_flag_cell(("FW_Reuse", "FW_ReuseTableOnly")) == "FW_Reuse"   # Reuse wins
    assert fg.operand_keeps_rows(()) is True                          # TOML slots carry FW_Reuse
    assert fg.operand_keeps_rows(("FW_ReuseTableOnly",)) is False     # the table, no data
    assert fg.operand_keeps_rows((), compact_default=False) is False  # XLSX: only when written
    assert fg.operand_keeps_rows(("FW_Reuse",), compact_default=False) is True
    assert fg.operand_keeps_rows(("FW_Reuse", "FW_ReuseTableOnly"), compact_default=False) is True


@pytest.mark.parametrize("reuse, ambiguous", [("FW_Reuse", False), (None, True)])
def test_two_braces_may_share_an_operand_only_when_it_keeps_its_rows(tmp_path, reuse, ambiguous):
    spec = fg.load_spec(_workbook(tmp_path / "w2" / "w2.xlsx", [
        ["HEAD", None, None, "FW_Combi(1)"],
        ["E1", "FW_Exclude", reuse, "FW_Combi(1)", "FW_Combi(1)"],
        ["E2", "FW_Exclude", reuse, "FW_Combi(1)", "FW_Combi(1)"],
        ["E3", "FW_Exclude", reuse, "FW_Combi(1)", "FW_Combi(1)"],
        ["T1", None, None, "FW_(,,E1,,E2,,,,M:N)"],
        ["T2", None, None, "FW_(,,E1,,E3,,,,M:N)"],
        ["TAIL", None, None, "FW_Combi(1)"],
    ], {"HEAD": ["S = []\n"], "E1": ["a1\n", "a2\n"], "E2": ["b1\n", "b2\n"], "E3": ["c1\n", "c2\n"],
        "T1": ["pass\n"], "T2": ["pass\n"], "TAIL": [TAIL]}))
    codes = {i.code for i in fwg.build_graph(spec).errors()}
    assert ("consumed_result_ambiguity" in codes) is ambiguous


# ------------------------------------------------------------ one spec input --
def test_a_spec_input_is_one_toml_or_one_workbook(tmp_path):
    book = _cartes_group_workbook(tmp_path)
    assert resolve_spec_input(book.parent) == book
    (book.parent / "~$w1.xlsx").write_bytes(b"lock")                  # an Office lock file
    assert resolve_spec_input(book.parent) == book
    toml = book.parent / "w1.toml"
    toml.write_text("title = 't'\n", encoding="utf-8")
    with pytest.raises(PreflightError, match="exactly one spec input"):
        resolve_spec_input(book.parent)
    assert resolve_spec_input(book) == book                           # a file picks itself
    assert resolve_spec_input(toml) == toml
    with pytest.raises(PreflightError):
        resolve_spec_input(tmp_path / "missing")


def test_grouped_nested_brace_operand_is_sized(tmp_path):
    """FW_()G consumes the newest brace result flattened into ONE row. It used to fall to
    UNKNOWN (the resolved operand's internal mark broke the brace grammar); a brace result
    keeps an exact count but no guessed row length."""
    spec = fg.load_spec(_workbook(tmp_path / "wg" / "wg.xlsx", [
        ["HEAD", None, None, "FW_Combi(1)"],
        ["A", "FW_Exclude", None, "FW_Combi(1)"],
        ["B", "FW_Exclude", None, "FW_Combi(1)"],
        ["R1", "FW_Exclude", None, "FW_(,,A,,B,,,,M:N)"],
        ["C", "FW_Exclude", None, "FW_Combi(1)"],
        ["R2", None, None, "FW_(,,FW_()G,,C,,,,M:N)"],
        ["TAIL", None, None, "FW_Combi(1)"],
    ], {"HEAD": ["S = []\n"], "A": ["a1\n", "a2\n"], "B": ["b1\n", "b2\n"], "R1": ["pass\n"],
        "C": ["c1\n"], "R2": ["pass\n"], "TAIL": [TAIL]}))
    sizings = fg.program_sizings(spec)
    assert (sizings["R1"].est.mode, sizings["R1"].est.value) == (fg.CardinalityMode.EXACT, 4)
    assert sizings["R1"].hist is None                               # lengths are not guessed
    r2 = sizings["R2"].est
    assert r2.mode != fg.CardinalityMode.UNKNOWN and r2.upper == 1  # one grouped row x one C row


def test_legacy_permut_forms_are_accepted():
    """The author's legacy Core accepted FW_Permut, FW_Permut(), FW_Permut( ), (All)/(Full) and
    (PermutationGenerator.TreatDuplicatesAs.IDENTICAL) -- all simple permutations, n!."""
    for verb in ("FW_Permut", "FW_Permut()", "FW_Permut( )", "FW_Permut(All)", "FW_Permut(Full)",
                 "FW_Permut(PermutationGenerator.TreatDuplicatesAs.IDENTICAL)"):
        assert fg.is_core_verb(verb), verb
        assert fg.verb_output_count(verb, 4) == 24, verb


def test_self_cartes_rows_are_not_distinct_sets(tmp_path):
    """Codex r4 counterexample, Core-verified: S | FW_Cartes(S) | FW_Permut() | FW_Combi(size)
    over a,b gives aa, ab, ba, bb -- FOUR rows (ab/ba are one set, aa repeats a code). The
    planner once claimed EXACT 8; it must never do so. Cartes with ANOTHER sheet whose values
    are disjoint keeps its distinct-sets certificate (EXACT 8 = 4 pairs x 2 orders)."""
    spec = fg.load_spec(_workbook(tmp_path / "sc" / "sc.xlsx", [
        ["HEAD", None, None, "FW_Combi(1)"],
        ["S", None, None, "FW_Cartes(S)", "FW_Permut()", "FW_Combi(size)"],
        ["T", None, None, "FW_Cartes(X)", "FW_Permut()", "FW_Combi(size)"],   # 2 combo verbs: no dual
        ["TAIL", None, None, "FW_Combi(1)"],
    ], {"HEAD": ["S = []\n"], "S": ["a\n", "b\n"], "T": ["t1\n", "t2\n"], "X": ["x1\n", "x2\n"],
        "TAIL": [TAIL]}))
    sizings = fg.program_sizings(spec)
    s_est = sizings["S"].est
    assert s_est.mode != fg.CardinalityMode.EXACT or s_est.value == 4
    assert (s_est.lower or 0) <= 4 <= (s_est.upper if s_est.upper is not None else s_est.value)
    assert (sizings["T"].est.mode, sizings["T"].est.value) == (fg.CardinalityMode.EXACT, 8)


def test_program_path_keeps_the_exact_sieve_precount():
    """Codex r4: routing a spec through program sizing must not drop an exact post-sieve count
    when every mandatory sheet's program is just its verb (proof_authz e4: 288 -> 133)."""
    path = HERE / "proof_authz" / "e4_bonds" / "e4.toml"
    if not path.exists():
        pytest.skip("proof_authz/e4_bonds not present")
    post = fg._program_cardinality_plan(fg.load_spec(path)).post_sieve
    assert (post.mode, post.value) == (fg.CardinalityMode.EXACT, 133)
