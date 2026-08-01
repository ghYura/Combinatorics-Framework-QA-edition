from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from face1_new.workbook_model import analyze_workbook


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "example150726.xlsx"


def test_example_workbook_structure_is_understood():
    analysis = analyze_workbook(EXAMPLE)

    assert analysis.sheet_count == 208
    assert analysis.data_sheet_count == 202
    assert len(analysis.sequence_steps) == 177
    assert analysis.metrics["composed_steps"] == 11
    assert analysis.metrics["optional_steps"] == 6
    assert analysis.metrics["intermediate_steps"] == 22
    assert analysis.metrics["grouped_steps"] == 158
    assert analysis.detected_pattern == "Legacy Core compatibility / operator-composition corpus"
    assert [step.sheet_name for step in analysis.sequence_steps[:3]] == ["E1", "E2", "E1E2"]
    assert [step.sheet_name for step in analysis.sequence_steps[-3:]] == ["142", "143", "144"]


def test_example_runtime_and_cell_contract():
    analysis = analyze_workbook(EXAMPLE)

    assert len(analysis.runtime.arguments) == 7
    assert len(analysis.runtime.custom_verdicts) == 17
    assert "class RunMeFirstOnce" in analysis.runtime.run_once_source
    assert analysis.sheet_by_name["E1"].baseline == "e11"
    assert [item.value for item in analysis.sheet_by_name["E2"].values] == ["e21", "e22", "e23"]
    assert analysis.sheet_by_name["E1E2"].role == "composed"
    assert analysis.sheet_by_name["St1"].role == "helper"
    assert analysis.sheet_by_name["1234567890123456789012345678901"].role == "empty"
    assert analysis.operation_counts["FW_Group"] == 226
    assert analysis.operation_counts["FW_ReplaceRE"] == 1582


def test_generic_workbook_falls_back_without_legacy_control_sheets():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "REGION"
    sheet.append(["eu"])
    sheet.append(["us"])
    payload = BytesIO()
    workbook.save(payload)

    analysis = analyze_workbook(payload.getvalue(), source_name="regions.xlsx")

    assert analysis.detected_pattern == "Generic workbook (no FW_Seq contract detected)"
    assert len(analysis.sequence_steps) == 0
    assert analysis.sheet_by_name["REGION"].baseline == "eu"
    assert analysis.sheet_by_name["REGION"].role == "dormant"
    assert '"source_name": "regions.xlsx"' in analysis.to_json()
