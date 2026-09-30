# SPDX-License-Identifier: LicenseRef-BUSL-1.1
"""Face 1 validates operand lifetimes rather than their row positions."""

import pytest

from face1_new.grid_model import EMPTY, GridProject
from face1_new.runtime_model import build_worker_command, default_run_config, plan_project, project_spec


def joined_project(left_mode="FW_Reuse", right_mode="FW_Reuse", second_join=True):
    project = GridProject(name="reused_operands", rows=[], directive_columns=5)
    left = project.add_row("LEFT", ["a", "b"])
    right = project.add_row("RIGHT", ["c", "d"])
    for row, mode in ((left, left_mode), (right, right_mode)):
        row.directives[:3] = ["FW_Exclude", "FW_Combi(1)", mode]
    first = project.add_row("JOIN1", [EMPTY])
    first.directives[0] = "FW_(,,LEFT,,RIGHT,,,,M:N)"
    if second_join:
        second = project.add_row("JOIN2", [EMPTY])
        second.directives[0] = "FW_(,,LEFT,,RIGHT,,,,M:N)"
    return project


def test_retained_operands_feed_two_nonadjacent_joins(tmp_path):
    import fwgen

    project = joined_project()
    assert project.validate() == []
    exported = tmp_path / "reused_operands.xlsx"
    exported.write_bytes(project.to_xlsx_bytes())
    spec = fwgen.load_workbook_spec(exported)
    # Both physical joins survive export, and their four-row results are
    # independently sized from the two two-row retained operands.
    assert spec.program["JOIN1"]["directives"] == ["FW_(,,LEFT,,RIGHT,,,,M:N)"]
    assert spec.program["JOIN2"]["directives"] == ["FW_(,,LEFT,,RIGHT,,,,M:N)"]
    sizes = fwgen.program_sizings(spec)
    assert sizes["JOIN1"].est.value == sizes["JOIN2"].est.value == 4


@pytest.mark.parametrize("mode", ["", "FW_ReuseTableOnly"])
def test_cleaned_operand_cannot_feed_a_second_join(mode):
    project = joined_project(left_mode=mode)
    messages = [issue.message for issue in project.validate() if issue.severity == "error"]
    assert any("LEFT" in message and "later joins would read an empty operand" in message
               for message in messages)
    with pytest.raises(ValueError, match="Cannot export invalid grid"):
        project.to_xlsx_bytes()


def test_single_join_operands_have_independent_cleanup_modes():
    project = joined_project(right_mode="FW_ReuseTableOnly", second_join=False)
    assert project.validate() == []


def test_reuse_keeps_rows_when_both_flags_are_present():
    project = joined_project()
    project.rows[0].directives[3] = "FW_ReuseTableOnly"
    assert project.validate() == []


def test_default_compact_reuse_flag_is_valid_on_an_ordinary_row():
    project = GridProject(name="ordinary", rows=[], directive_columns=2)
    row = project.add_row("A", ["a", "b"])
    row.directives[:] = ["FW_Reuse", "FW_Combi(1)"]
    assert project.validate() == []


def test_missing_named_operand_is_rejected():
    project = joined_project(second_join=False)
    project.rows[-1].directives[0] = "FW_(,,MISSING,,RIGHT,,,,M:N)"
    assert any("MISSING" in issue.message and "not a declared node" in issue.message
               for issue in project.validate())


def test_nested_operand_needs_a_prior_brace_target():
    project = joined_project(second_join=False)
    project.rows[-1].directives[0] = "FW_(,,FW_(),,RIGHT,,,,M:N)"
    assert any("missing_nested_prior" in issue.message for issue in project.validate())


def test_nested_operand_resolves_prior_join_without_adjacent_excluded_pair():
    project = joined_project()
    project.rows[-1].directives[0] = "FW_(,,FW_(),,RIGHT,,,,M:N)"
    assert project.validate() == []


def test_full_join_helper_references_must_exist():
    project = joined_project(second_join=False)
    project.rows[-1].directives[0] = "FW_(START,,LEFT,RELATION,RIGHT,,END,SEP,M:N)"
    missing = [issue.message for issue in project.validate()]
    assert all(any(repr(name) in message for message in missing)
               for name in ("START", "RELATION", "END", "SEP"))
    project.auxiliary_sheets = {name: [name.lower()] for name in ("START", "RELATION", "END", "SEP")}
    assert project.validate() == []


def test_raw_self_cartes_is_not_a_result_dependency_cycle():
    project = GridProject(name="self_cartes", rows=[], directive_columns=2)
    row = project.add_row("A", ["a", "b"])
    row.directives[0] = "FW_Cartes(A)"
    assert project.validate() == []


def test_planning_metadata_preserves_every_directive_and_passive_sheet():
    project = joined_project(second_join=False)
    project.rows[0].directives[3] = "FW_Separator(SEP)"
    project.auxiliary_sheets["SEP"] = ["+"]
    spec = project_spec(project)
    assert spec.source_format == "xlsx"
    assert spec.program["LEFT"]["directives"] == ["FW_Combi(1)", "FW_Separator(SEP)", "FW_Combi(1)"]
    assert spec.passive_sheets == {"SEP": ["+"]}


def test_worker_preflight_uses_the_same_program_as_its_exact_workbook(tmp_path):
    import fwgen

    project = joined_project(second_join=False)
    project.rows[0].directives[3] = "FW_Separator(SEP)"
    project.auxiliary_sheets["SEP"] = ["+"]
    workbook = tmp_path / "actual.xlsx"
    workbook.write_bytes(project.to_xlsx_bytes())
    command = build_worker_command(default_run_config(), workbook, tmp_path / "unused", tmp_path / "runs")
    bundle_args = command[command.index("--") + 1:]
    assert str(workbook) in bundle_args
    assert str(tmp_path / "unused") not in bundle_args
    actual = fwgen.load_spec(workbook)
    planned = project_spec(project)
    assert actual.program == planned.program
    assert actual.passive_sheets == planned.passive_sheets
    assert fwgen.spec_cardinality_plan(actual).final == fwgen.spec_cardinality_plan(planned).final


def test_face1_plan_uses_supported_ordered_program_sizing():
    project = GridProject(name="ordered", rows=[], directive_columns=2)
    row = project.add_row("S", ["a", "b"])
    row.directives[:] = ["FW_Combi(1)", "FW_Permut()"]
    plan = plan_project(project)
    assert plan.final["mode"] == "EXACT"
    assert plan.final["value"] == 2


def test_face1_nested_plan_matches_its_exported_workbook(tmp_path):
    import fwgen

    project = joined_project()
    project.rows[-1].directives[0] = "FW_(,,FW_(),,RIGHT,,,,M:N)"
    workbook = tmp_path / "nested.xlsx"
    workbook.write_bytes(project.to_xlsx_bytes())
    actual = fwgen.cardinality_plan_to_dict(fwgen.spec_cardinality_plan(fwgen.load_spec(workbook)))
    assert plan_project(project).final == actual["final"]
