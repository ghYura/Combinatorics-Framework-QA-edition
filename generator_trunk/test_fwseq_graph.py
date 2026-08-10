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

"""STEP 37 — FW_Seq dependency graph artifact.

Covers: a valid brace graph shows the prior-result join; invalid synthetic graphs
(missing operand / cycle) are detected; a cyclic spec is rejected BEFORE the
workbook; consumed-result ambiguity and unused advanced nodes are flagged; the
graph hash lands in plan.json; JSON + DOT outputs are produced.

Run: `python3 -m pytest test_fwseq_graph.py -q` (no DB / no Bundle run).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fwgen as fg
import fwseq_graph as fwg


_BRACE_SPEC = {
    "title": "brace demo",
    "runme": "class R{}",
    "slots": [
        {"sheet": "A", "values": ["a1", "a2"], "flags": ["FW_Exclude"]},
        {"sheet": "B", "values": ["b1", "b2"], "flags": ["FW_Exclude"]},
        {"sheet": "JOINED", "values": [" placeholder"]},
    ],
    "seq_extra": [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]],
}


def _brace_spec():
    return fg.parse_spec(_BRACE_SPEC, "brace")


# Same brace spec as TOML. NB: top-level keys (seq_extra) MUST precede the
# [[slots]] array-of-tables, else TOML attaches seq_extra to the last slot.
_BRACE_TOML = (
    'title = "brace demo"\n'
    'runme = "class R{}"\n'
    'seq_extra = [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]]\n'
    '\n'
    '[[slots]]\nsheet = "A"\nvalues = ["a1", "a2"]\nflags = ["FW_Exclude"]\n'
    '\n'
    '[[slots]]\nsheet = "B"\nvalues = ["b1", "b2"]\nflags = ["FW_Exclude"]\n'
    '\n'
    '[[slots]]\nsheet = "JOINED"\nvalues = [" placeholder"]\n'
)


# --------------------------------------------------------------------------- #
def test_valid_brace_graph_shows_prior_result_join():
    g = fwg.build_graph(_brace_spec())

    # the brace node consumes the prior RESULT tables of A and B (the join) ...
    brace_ids = [nid for nid, n in g.nodes.items() if n.kind == "brace"]
    assert len(brace_ids) == 1
    bid = brace_ids[0]
    operands = {e.dst for e in g.edges if e.kind == "brace_operand" and e.src == bid}
    assert operands == {"A", "B"}

    # ... and produces the JOINED result; A/B are excluded, JOINED is a join-result
    assert any(e.src == "JOINED" and e.dst == bid and e.kind == "produces" for e in g.edges)
    assert g.nodes["A"].attrs["excluded"] and g.nodes["B"].attrs["excluded"]
    assert g.nodes["JOINED"].attrs.get("is_join_result") is True

    # a valid brace spec has NO structural errors
    assert g.errors() == []


def test_nested_brace_chain_resolves_prior_targets():
    spec = fg.parse_spec({
        "runme": "class R{}",
        "slots": [
            {"sheet": "A", "values": ["a"], "flags": ["FW_Exclude"]},
            {"sheet": "B", "values": ["b"], "flags": ["FW_Exclude"]},
            {"sheet": "C", "values": ["c"], "flags": ["FW_Exclude"]},
            {"sheet": "D", "values": ["d"], "flags": ["FW_Exclude"]},
            {"sheet": "R1", "values": ["r1"]},
            {"sheet": "R2", "values": ["r2"]},
            {"sheet": "R3", "values": ["r3"]},
        ],
        "seq_extra": [
            ["R1", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"],
            ["R2", "FW_Reuse", "FW_(,,FW_(),,C,,,,M:N)"],
            ["R3", "FW_Reuse", "FW_(,,FW_()G,,D,,,,M:N)"],
        ],
    }, "nested")
    graph = fwg.validate_spec_graph(spec)
    nested = {
        (edge.src, edge.dst)
        for edge in graph.edges
        if edge.kind == "brace_nested_operand"
    }
    assert nested == {("brace#1.2", "R1"), ("brace#2.2", "R2")}


def test_graph_hash_is_stable_and_content_addressed():
    g1 = fwg.build_graph(_brace_spec())
    g2 = fwg.build_graph(_brace_spec())
    assert g1.graph_hash() == g2.graph_hash()
    assert g1.graph_hash().startswith("sha256:")
    # a different spec -> different hash
    other = fg.parse_spec({"slots": [{"sheet": "X", "values": ["x"]}], "runme": "class R{}"}, "x")
    assert fwg.build_graph(other).graph_hash() != g1.graph_hash()


def test_json_and_dot_outputs():
    g = fwg.build_graph(_brace_spec())
    doc = g.to_json()
    assert {n["id"] for n in doc["nodes"]} >= {"A", "B", "JOINED"}
    assert any(e["kind"] == "brace_operand" for e in doc["edges"])
    dot = g.to_dot()
    assert dot.startswith("digraph fwseq {")
    assert "brace_operand" in dot and "produces" in dot
    assert '[shape=box' in dot                 # the brace node


# --- invalid SYNTHETIC graphs (constructed directly, bypassing parse_spec) --- #
def test_invalid_synthetic_graph_missing_operand():
    g = fwg.FwSeqGraph(
        nodes={"A": fwg.GraphNode("A", "slot", {})},
        edges=[fwg.GraphEdge("A", "ZZZ", "cartes")],
    )
    codes = {i.code for i in g.validate()}
    assert "missing_operand" in codes
    assert g.errors()                          # an error -> would reject


def test_invalid_synthetic_graph_cycle():
    g = fwg.FwSeqGraph(
        nodes={"A": fwg.GraphNode("A", "slot", {}), "B": fwg.GraphNode("B", "slot", {})},
        edges=[fwg.GraphEdge("A", "B", "cartes"), fwg.GraphEdge("B", "A", "cartes")],
    )
    cyc = [i for i in g.validate() if i.code == "cycle"]
    assert cyc and cyc[0].level == fwg.ERROR


def test_consumed_result_ambiguity_two_braces_one_operand():
    g = fwg.FwSeqGraph(
        nodes={"A": fwg.GraphNode("A", "slot", {"excluded": True}),
               "br1": fwg.GraphNode("br1", "brace", {}),
               "br2": fwg.GraphNode("br2", "brace", {})},
        edges=[fwg.GraphEdge("br1", "A", "brace_operand"),
               fwg.GraphEdge("br2", "A", "brace_operand")],
    )
    assert any(i.code == "consumed_result_ambiguity" for i in g.errors())


def test_consumed_result_ambiguity_operand_not_excluded():
    g = fwg.FwSeqGraph(
        nodes={"A": fwg.GraphNode("A", "slot", {"excluded": False}),
               "br": fwg.GraphNode("br", "brace", {})},
        edges=[fwg.GraphEdge("br", "A", "brace_operand")],
    )
    assert any(i.code == "consumed_result_ambiguity" for i in g.errors())


def test_unused_advanced_node_is_a_warning_not_an_error():
    spec = fg.parse_spec({"runme": "class R{}", "slots": [
        {"sheet": "A", "values": ["a1"], "flags": ["FW_Exclude"]},
        {"sheet": "B", "values": ["b1"]}]}, "unused")
    g = fwg.build_graph(spec)
    warns = [i for i in g.validate() if i.level == fwg.WARNING]
    assert any(i.code == "unused_advanced_node" for i in warns)
    assert g.errors() == []                     # warning does not gate
    fg.build_compact(spec)                       # so the workbook still builds


# --- the gate: invalid cycle rejected BEFORE the workbook --------------------- #
def _cyclic_spec():
    return fg.parse_spec({"runme": "class R{}", "slots": [
        {"sheet": "A", "values": ["a1"], "verb": "FW_Cartes(B)"},
        {"sheet": "B", "values": ["b1"], "verb": "FW_Cartes(A)"}]}, "cyc")


def test_cyclic_spec_rejected_before_workbook():
    spec = _cyclic_spec()
    # the graph reports the cycle ...
    assert any(i.code == "cycle" for i in fwg.build_graph(spec).errors())
    # ... and BOTH workbook builders refuse to emit it
    with pytest.raises(ValueError, match="graph rejected before workbook"):
        fg.build_compact(spec)
    with pytest.raises(ValueError, match="graph rejected before workbook"):
        fg.build_compact_core_json(spec)


def test_validate_spec_graph_returns_graph_when_clean():
    g = fwg.validate_spec_graph(_brace_spec())   # no raise
    assert g.graph_hash().startswith("sha256:")


# --- graph hash recorded in plan.json ---------------------------------------- #
def test_graph_hash_recorded_in_plan_json():
    from bundle import cli
    with tempfile.TemporaryDirectory() as d:
        spec_dir = Path(d) / "spec"
        spec_dir.mkdir()
        (spec_dir / "brace.toml").write_text(_BRACE_TOML, encoding="utf-8")
        out = Path(d) / "out"
        cli._main_plan([str(spec_dir), "--out", str(out)])
        plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))

        assert "dependency_graph" in plan
        dg = plan["dependency_graph"]
        assert dg["graph_hash"].startswith("sha256:")
        spec = fg.load_spec(spec_dir / "brace.toml")
        assert dg["graph_hash"] == fwg.build_graph(spec).graph_hash()
        assert any(e["kind"] == "brace_operand" for e in dg["graph"]["edges"])


# --- plan MUST reject error-level graph issues BEFORE writing the artifact ---- #
_CYCLIC_TOML = (
    'runme = "class R{}"\n'
    '[[slots]]\nsheet = "A"\nvalues = ["a1"]\nverb = "FW_Cartes(B)"\n'
    '[[slots]]\nsheet = "B"\nvalues = ["b1"]\nverb = "FW_Cartes(A)"\n'
)
_MISSING_OPERAND_TOML = (
    'runme = "class R{}"\n'
    '[[slots]]\nsheet = "A"\nvalues = ["a1"]\nverb = "FW_Cartes(ZZZ)"\n'
)


@pytest.mark.parametrize("toml,marker", [
    (_CYCLIC_TOML, "cycle"),
    (_MISSING_OPERAND_TOML, "missing_operand"),
])
def test_plan_rejects_error_graph_before_writing_artifact(toml, marker):
    from bundle import cli
    with tempfile.TemporaryDirectory() as d:
        spec_dir = Path(d) / "spec"
        spec_dir.mkdir()
        (spec_dir / "s.toml").write_text(toml, encoding="utf-8")
        out = Path(d) / "out"
        # _main_plan reports the BundleError and exits non-zero ...
        with pytest.raises(SystemExit) as ei:
            cli._main_plan([str(spec_dir), "--out", str(out)])
        assert ei.value.code not in (0, None)
        # ... and writes NO plan.json for the rejected (unbuildable) graph
        assert not (out / "plan.json").exists()
        # the gate itself classifies the issue as an error of the expected kind
        spec = fg.load_spec(spec_dir / "s.toml")
        errs = fwg.build_graph(spec).errors()
        assert any(e.code == marker for e in errs)


# --- the CLI emits JSON + DOT ------------------------------------------------- #
def _write_brace_spec_dir(d: Path) -> Path:
    sd = d / "spec"
    sd.mkdir()
    (sd / "brace.toml").write_text(_BRACE_TOML, encoding="utf-8")
    return sd


def test_cli_graph_emits_json_and_dot():
    with tempfile.TemporaryDirectory() as d:
        sd = _write_brace_spec_dir(Path(d))
        r = subprocess.run([sys.executable, "fwgen_cli.py", "graph", "--specs", str(sd)],
                           cwd=str(HERE), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "sha256:" in r.stdout and '"nodes"' in r.stdout and '"edges"' in r.stdout

        r2 = subprocess.run([sys.executable, "fwgen_cli.py", "graph", "--specs", str(sd), "--dot"],
                            cwd=str(HERE), capture_output=True, text=True)
        assert r2.returncode == 0, r2.stderr
        assert "digraph fwseq {" in r2.stdout and "brace_operand" in r2.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
