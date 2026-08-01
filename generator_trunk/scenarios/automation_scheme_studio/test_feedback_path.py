import pytest

# Tier classification (Prompt 03 Part C): a missing optional SUT checkout must be
# a classified skip, not a collection error.
pytest.importorskip(
    "automation_constructor",
    reason="MISSING_AUTHORIZED_BACKEND: needs the sibling SUT checkout on PYTHONPATH "
           "(BUNDLE_SUT_ROOT/automation-scheme-studio/src)")

from automation_constructor.experiments.bundle_search import (
    ALL_STAGE_TOKENS,
    SearchPlan,
    build_circuit,
)

from generator_trunk.scenarios.automation_scheme_studio.feedback_path import (
    append_covering_feedback_path,
    covering_feedback_recipe,
)


def test_covering_design_exercises_every_stage_position_and_pair() -> None:
    expected = set(ALL_STAGE_TOKENS)
    ordered_pairs = set()
    for front_index in range(370):
        recipes = [covering_feedback_recipe(front_index, row) for row in range(16)]
        for position in range(3):
            assert {recipe[2][position] for recipe in recipes} == expected
        assert len({(recipe[0], recipe[1]) for recipe in recipes}) >= 15
        assert {recipe[3] for recipe in recipes} == {
            "feedback_only",
            "forward_and_feedback",
        }
        ordered_pairs.update((recipe[2][0], recipe[2][1]) for recipe in recipes)
    assert ordered_pairs == {(left, right) for left in expected for right in expected}


def test_every_path_row_builds_a_real_dynamic_circuit() -> None:
    for row in range(16):
        plan = SearchPlan(family="feedback-path-build-test")
        append_covering_feedback_path(plan, 0, row)
        built = build_circuit(plan)
        assert built.circuit.nodes
        assert built.circuit.connections


def test_scenario_allocates_all_five_oracle_outcomes() -> None:
    from pathlib import Path

    text = (Path(__file__).parent / "06_feedback_path_covering" / "scenario.toml").read_text()
    assert text.count("[[custom_vars]]") == 5
    assert all(f"code = {code}" in text for code in range(1, 6))
