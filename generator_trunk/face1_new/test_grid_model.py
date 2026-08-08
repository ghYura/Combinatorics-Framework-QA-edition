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

from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from face1_new.grid_model import EMPTY, GridProject, project_from_analysis
from face1_new.workbook_model import analyze_workbook


ROOT = Path(__file__).resolve().parents[1]


def _brace_project_with_gaps() -> GridProject:
    project = GridProject(name="gap_contract", rows=[], directive_columns=7)
    left = project.add_row("LEFT", ["l0", "l1"])
    right = project.add_row("RIGHT", ["r0", "r1"])
    joined = project.add_row("JOINED", [EMPTY])
    for row in (left, right):
        row.directives[0] = "FW_Exclude"       # B
        row.directives[3] = "FW_Reuse"         # E; C and D intentionally empty
        row.directives[5] = "FW_Combi(1)"       # G; F intentionally empty
    joined.directives[4] = "FW_(,,LEFT,,RIGHT,,,,M:N)"  # F
    return project


def test_blank_columns_between_nonempty_cells_are_preserved_and_valid():
    project = _brace_project_with_gaps()

    assert project.validate() == []
    workbook = load_workbook(BytesIO(project.to_xlsx_bytes()), data_only=False)
    sequence = workbook["FW_Seq"]
    assert sequence["B1"].value == "FW_Exclude"
    assert sequence["C1"].value is None
    assert sequence["D1"].value is None
    assert sequence["E1"].value == "FW_Reuse"
    assert sequence["F1"].value is None
    assert sequence["G1"].value == "FW_Combi(1)"
    assert sequence["F3"].value == "FW_(,,LEFT,,RIGHT,,,,M:N)"


def test_reuse_must_be_next_nonempty_cell_but_not_physically_adjacent():
    project = _brace_project_with_gaps()
    project.rows[0].directives[2] = "FW_Subsets"  # D now intervenes before Reuse in E

    messages = [issue.message for issue in project.validate()]
    assert any("next non-empty cell after FW_Exclude" in message for message in messages)


def test_group_cells_are_valid_in_middle_and_multiple_positions():
    project = GridProject.blank(visible_rows=1)
    row = project.rows[0]
    row.directives = ["FW_Combi(1)", "", "FW_Group", "", "FW_Group\nFW_ReplaceRE(\"x\", \"y\")", "", "FW_Combi(size)"]

    assert project.validate() == []


def test_brace_requires_exactly_the_previous_two_excluded_rows():
    project = _brace_project_with_gaps()
    extra = project._new_row("INTERVENING", ["x"])
    extra.directives[0] = "FW_Combi(1)"
    project.rows.insert(2, extra)

    messages = [issue.message for issue in project.validate()]
    assert any("only directly after two FW_Exclude rows" in message for message in messages)


def test_example_import_is_explicit_and_round_trips_the_full_contract():
    analysis = analyze_workbook(ROOT / "example150726.xlsx")
    project = project_from_analysis(analysis, trailing_rows=0)

    assert project.validate() == []
    rebuilt = analyze_workbook(project.to_xlsx_bytes(), source_name="grid-rebuilt.xlsx")
    assert len(rebuilt.sequence_steps) == 177
    assert rebuilt.sheet_count == 208
    assert rebuilt.metrics["optional_steps"] == 6
    assert rebuilt.metrics["grouped_steps"] == 158
