"""Regression checks for the Core-derived draggable verb palette."""

from face1_new.grid_model import TEMPLATES


def test_template_ids_are_unique_for_drag_and_drop():
    ids = [template.id for template in TEMPLATES]
    assert len(ids) == len(set(ids))


def test_palette_contains_core_row_flags_and_parameter_variants():
    directives = {template.directive for template in TEMPLATES}

    assert {
        "FW_Exclude",
        "FW_Optional",
        "FW_Reuse",
        "FW_ReuseTableOnly",
        "FW_Heading",
        "FW_LastInQueue",
        "FW_Concatenator=",
    } <= directives
    assert {
        "FW_Combi",
        "FW_Combi()",
        "FW_Combi(0)",
        "FW_Combi(1)",
        "FW_Combi(2)",
        "FW_Combi(size)",
        "FW_Combi(all)",
        "FW_Combi(full)",
        "FW_CombiR(2)",
        "FW_CombiR(size)",
        "FW_CombiR(all)",
        "FW_CombiR(full)",
    } <= directives
    assert {
        "FW_Permut",
        "FW_Permut()",
        "FW_Permut(2)",
        "FW_Permut(PermutationGenerator.TreatDuplicatesAs.IDENTICAL)",
        "FW_PermutR(2)",
        "FW_PermutR(size)",
        "FW_PermutR(all)",
        "FW_PermutR(full)",
    } <= directives


def test_palette_contains_every_core_subset_mode_and_brace_multiplicity():
    directives = {template.directive for template in TEMPLATES}

    assert {
        "FW_Subsets",
        "FW_Subsets_EXACT(2)",
        "FW_Subsets_BEFORE(2)",
        "FW_Subsets_AFTER(2)",
        "FW_Subsets_RANGE(2,3)",
        "FW_Subsets_GIVEN(1,3)",
    } <= directives
    assert {
        "FW_(,,LEFT,,RIGHT,,,,1:1)",
        "FW_(,,LEFT,,RIGHT,,,,1:N)",
        "FW_(,,LEFT,,RIGHT,,,,M:1)",
        "FW_(,,LEFT,,RIGHT,,,,M:M)",
        "FW_(,,LEFT,,RIGHT,,,,M:N)",
    } <= directives
