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

"""Characterization and oracle tests for the direct engine demonstration.

Self-contained: no database, no network, no external SUT. These tests pin the
adapter's structural semantics and — importantly — prove the exact oracle is
*not vacuous*: a seeded defect in one evaluator must be caught by the other.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from generator_trunk.engine_demo import record_pipeline as rp
from generator_trunk.engine_demo.record_pipeline import (
    Atom, CORPUS, Parallel, PipelineError, Repeat, Sequence_,
    contract_violation, emit_atom, emit_close, emit_node, emit_open, evaluate,
    max_output_length, parse_topology, reference_eval, run_compiled, template,
)

HERE = Path(__file__).resolve().parent
SPEC = HERE / "direct_engine_smoke" / "scenario.toml"

#: The exact structure the Bundle's three-link brace chain assembles, rebuilt
#: here in Python so the scenario's expected outcome can be characterized
#: without a database. Kept in sync with the TOML by
#: `test_scenario_declares_the_operators_the_demonstration_claims`.
_MOTIF = (("sort", {}), ("scale", {"k": -1}))
_GROUPS = ("normalize", "spread")


def _assembled_stream(group: str, first: tuple, second: tuple) -> list:
    stream: list = []
    emit_open(stream, 3, "sequence")                  # ROOT_OPEN
    emit_open(stream, 2, "parallel", reducer="merge")  # PAR_OPEN
    emit_open(stream, 1, "sequence")                  # SEQ_OPEN
    emit_node(stream, template(group))                # GROUPED_STAGE (FW_Group)
    emit_atom(stream, first[0], **first[1])           # REPEATED_MOTIF (FW_PermutR)
    emit_atom(stream, second[0], **second[1])
    emit_close(stream, 1)                             # SEQ_CLOSE
    emit_node(stream, template("guard"))              # SIDE_BRANCH
    emit_close(stream, 2)                             # PAR_CLOSE
    emit_node(stream, template("compact"))            # FINALIZER
    emit_close(stream, 3)                             # ROOT_CLOSE
    return stream


def _all_candidates():
    for group, (first, second) in itertools.product(
            _GROUPS, itertools.product(_MOTIF, repeat=2)):
        yield group, first, second, _assembled_stream(group, first, second)


# ------------------------------------------------------------ structure ------
def test_parse_selects_the_deepest_complete_root() -> None:
    stream = _assembled_stream("normalize", _MOTIF[0], _MOTIF[1])
    node = parse_topology(stream)
    assert isinstance(node, Sequence_)
    assert isinstance(node.children[0], Parallel)
    assert rp.depth(node) == 5


def test_helper_debris_is_dropped_not_fatal() -> None:
    """Core re-emits helper sheets as ordinary one-value columns, producing
    empty scopes, and may retain an operand whose scope never closes. Both are
    debris — the real root must still be selected."""
    stream = _assembled_stream("spread", _MOTIF[1], _MOTIF[0])
    stream = [rp.Marker(tag=1, opening=True, kind="sequence"),
              rp.Marker(tag=1, opening=False)] + stream
    emit_open(stream, 9, "parallel", reducer="merge")   # opened, never closed
    node = parse_topology(stream)
    assert rp.depth(node) == 5


def test_a_stream_with_no_complete_structure_is_a_construction_failure() -> None:
    stream: list = []
    emit_open(stream, 1, "sequence")
    emit_atom(stream, "sort")
    result = evaluate(stream)
    assert result.code == rp.VERDICT_CONSTRUCTION


def test_unknown_atom_and_reducer_are_rejected() -> None:
    with pytest.raises(PipelineError):
        run_compiled(Atom("teleport"), CORPUS)
    with pytest.raises(PipelineError):
        reference_eval(Parallel((Atom("sort"),), "quantum"), CORPUS)


# --------------------------------------------------------------- oracle ------
@pytest.mark.parametrize("node", [
    Atom("sort"),
    Atom("dedupe"),
    Atom("drop_below", (("threshold", 0),)),
    Sequence_((Atom("scale", (("k", -1),)), Atom("sort"))),
    Parallel((Atom("sort"), Atom("dedupe")), "merge"),
    Parallel((Atom("sort"), Atom("dedupe")), "concat"),
    Repeat(Atom("offset", (("k", 2),)), 3),
    Sequence_((Parallel((template("normalize"), template("guard")), "merge"),
               template("compact"))),
])
def test_compiled_and_reference_evaluators_agree(node) -> None:
    compiled, _ops = run_compiled(node, CORPUS)
    assert compiled == reference_eval(node, CORPUS)


def test_the_differential_oracle_is_not_vacuous(monkeypatch) -> None:
    """Seed a defect in the compiled path only. If the two evaluators were
    really one implementation this test could not fail the candidate — which is
    exactly what it exists to prove."""
    original = rp._compile_atom

    def broken(atom):
        if atom.kind == "sort":                       # wrong direction, on purpose
            return lambda data, ops: sorted(data, reverse=True)
        return original(atom)

    monkeypatch.setattr(rp, "_compile_atom", broken)
    result = evaluate(_assembled_stream("normalize", _MOTIF[0], _MOTIF[0]))
    assert result.code == rp.VERDICT_ORACLE_DISAGREEMENT
    assert result.reason == "differential_mismatch"


def test_structural_bound_is_a_real_upper_bound() -> None:
    for _group, _f, _s, stream in _all_candidates():
        node = parse_topology(stream)
        compiled, _ops = run_compiled(node, CORPUS)
        assert len(compiled) <= max_output_length(node, len(CORPUS))


def test_evaluation_is_deterministic() -> None:
    stream = _assembled_stream("spread", _MOTIF[0], _MOTIF[1])
    first, second = evaluate(stream), evaluate(stream)
    assert first == second


# ------------------------------------------------------------- contract ------
def test_contract_reasons_are_exact_and_distinct() -> None:
    assert contract_violation(()) == "empty_output"
    assert contract_violation((1, 0)) == "not_non_decreasing"
    assert contract_violation((0, rp.CONTRACT_HIGH + 1)) == "value_out_of_band"
    assert contract_violation((rp.CONTRACT_LOW, 0, rp.CONTRACT_HIGH)) == ""


def test_out_of_band_output_is_a_domain_failure_not_a_defect() -> None:
    stream: list = []
    emit_open(stream, 1, "sequence")
    emit_atom(stream, "scale", k=1000)
    emit_close(stream, 1)
    result = evaluate(stream)
    assert result.code == rp.VERDICT_CONTRACT
    assert result.reason == "value_out_of_band"


# ------------------------------------------- characterized smoke behaviour ----
def test_the_smoke_space_is_eight_candidates_with_a_known_pass_and_fail() -> None:
    """Pins the bounded outcome the release gate expects: 8 generated, 6 PASS,
    2 DOMAIN_FAIL — and the failures are attributable to stage ORDER, not to a
    template, since both grouped modules are monotone on their own."""
    outcomes = {}
    for group, first, second, stream in _all_candidates():
        result = evaluate(stream)
        outcomes[(group, first[0], second[0])] = (result.code, result.reason)

    assert len(outcomes) == 8
    passed = [k for k, (code, _) in outcomes.items() if code == rp.VERDICT_PASS]
    failed = {k: reason for k, (code, reason) in outcomes.items() if code != rp.VERDICT_PASS}
    assert len(passed) == 6
    assert set(failed.values()) == {"not_non_decreasing"}
    # The interaction: sorting and THEN negating is the only order that breaks
    # the contract, for both grouped modules.
    assert set(failed) == {("normalize", "sort", "scale"), ("spread", "sort", "scale")}


def test_metrics_line_is_one_parseable_finite_record() -> None:
    for _group, _f, _s, stream in _all_candidates():
        line = evaluate(stream).metrics_line()
        assert "\n" not in line
        pairs = dict(token.split("=", 1) for token in line.split())
        assert pairs["app"] == "engine_demo"
        for key in ("stages", "depth", "branches", "ops", "retained", "FW_VAR"):
            int(pairs[key])                            # finite integers only


# ------------------------------------------------- the scenario declaration ---
def test_scenario_declares_the_operators_the_demonstration_claims() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert "group_replace" in text                     # FW_Group
    assert 'verb = "FW_PermutR(2)"' in text            # ordered repetition
    assert text.count("FW_()") == 2                    # two nested brace links
    assert text.count('"FW_Reuse", "FW_(') == 3        # three brace rows
    assert "--" not in text.split("seq_extra", 1)[0]   # seq_extra stays top-level


def test_intermediate_brace_targets_are_excluded_from_the_final_product() -> None:
    text = SPEC.read_text(encoding="utf-8")
    for sheet in ("GROUPED_STAGE", "REPEATED_MOTIF", "SIDE_BRANCH", "FINALIZER",
                  "SEQ_RESULT", "PAR_RESULT"):
        block = text.split(f'sheet = "{sheet}"', 1)[1].split("[[slots]]", 1)[0]
        assert 'flags = ["FW_Exclude"]' in block, sheet
    root = text.split('sheet = "ROOT_RESULT"', 1)[1].split("[[slots]]", 1)[0]
    assert "FW_Exclude" not in root                     # the highest-order root DOES enter fw_final
