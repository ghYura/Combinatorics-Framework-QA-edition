from __future__ import annotations

from pathlib import Path

import pytest

# Tier classification (Prompt 03 Part C): this suite needs the sibling SUT
# checkout on the import path. A missing optional SUT must be a classified skip,
# not a collection error that reads as a broken suite.
pytest.importorskip(
    "automation_constructor",
    reason="MISSING_AUTHORIZED_BACKEND: needs the sibling SUT checkout on PYTHONPATH "
           "(BUNDLE_SUT_ROOT/automation-scheme-studio/src)")

from automation_constructor.experiments.bundle_search import (
    ALL_STAGE_TOKENS,
    SearchPlan,
    build_circuit,
)

from generator_trunk.scenarios.automation_scheme_studio.advanced_topology import (
    Marker,
    Node,
    attach_topology,
    emit_atom,
    emit_close,
    emit_node,
    emit_open,
    parse_topology,
    template,
    topology_stats,
)

HERE = Path(__file__).resolve().parent


def test_parser_selects_complete_highest_order_root() -> None:
    stream: list[Node | Marker] = []
    emit_open(stream, 1, "sequence")
    emit_atom(stream, "gain")
    emit_atom(stream, "low_pass")
    emit_close(stream, 1)
    emit_open(stream, 3, "feedback", controller="pid", boundary="unit_delay")
    emit_node(stream, template("parallel_conditioners"))
    emit_close(stream, 3)
    # Incomplete helper debris is legal because Core may retain helper sheets.
    emit_open(stream, 4, "parallel", reducer="signed")
    selected = parse_topology(stream)
    assert selected.kind == "feedback"
    assert topology_stats(selected)["topology_depth"] >= 4


def test_every_smoke_topology_builds_real_nested_sut_circuit() -> None:
    for name in (
        "inverter_modulator_loop",
        "parallel_conditioners",
        "parallel_pid_loops",
        "deep_mixed",
    ):
        plan = SearchPlan(family=f"advanced-test-{name}", duration=0.3, dt=0.06)
        node = attach_topology(plan, [template(name)])
        built = build_circuit(plan)
        stats = topology_stats(node)
        assert built.circuit.nodes
        assert built.circuit.connections
        assert stats["topology_feedbacks"] >= 1
        assert stats["topology_depth"] >= 3


def test_third_order_axis_exposes_every_sut_stage() -> None:
    text = (HERE / "10_third_order_brace" / "scenario.toml").read_text()
    assert all(f'"{token}"' in text for token in ALL_STAGE_TOKENS)
    assert text.count("FW_()") == 2
    assert "FW_Permut(2)" in text
    assert "FW_CombiR(2)" in text
    assert "FW_Subsets_RANGE(1,2)" in text


def test_fourth_order_uses_group_repetition_and_nested_brace() -> None:
    text = (HERE / "20_grouped_repetition" / "scenario.toml").read_text()
    assert "group_replace" in text
    assert "FW_PermutR(2)" in text
    assert "FW_()" in text


def test_intermediate_brace_targets_are_excluded_from_final_cartesian_product() -> None:
    expectations = {
        "01_operator_smoke": ("SERIES_RESULT", "PARALLEL_RESULT"),
        "10_third_order_brace": ("SERIES_RESULT", "PARALLEL_RESULT"),
        "20_grouped_repetition": ("PARALLEL_RESULT",),
    }
    for scenario, sheets in expectations.items():
        text = (HERE / scenario / "scenario.toml").read_text()
        for sheet in sheets:
            remainder = text.split(f'sheet = "{sheet}"', 1)[1]
            block = remainder.split("[[slots]]", 1)[0]
            assert 'flags = ["FW_Exclude"]' in block, (scenario, sheet)
