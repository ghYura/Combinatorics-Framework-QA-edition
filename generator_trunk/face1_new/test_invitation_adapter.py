from invitation_wizard import propose

from .invitation_adapter import project_from_invitation
from .runtime_model import plan_project


def test_confirmed_invitation_becomes_valid_editable_workbook_rows():
    draft = propose("learn")
    project = project_from_invitation(draft, selected_stress=("duplicate_submit",))
    rows = project.sequence_rows
    assert [row.target for row in rows[:3]] == ["CHANNEL", "ACCOUNT_TYPE", "PAYMENT_TYPE"]
    assert rows[4].directives[:2] == ["FW_Optional", "FW_Combi(1)"]
    assert not [issue for issue in project.validate() if issue.severity == "error"]


def test_generated_workbook_uses_existing_exact_planner():
    project = project_from_invitation(propose("learn"), selected_stress=("duplicate_submit",))
    plan = plan_project(project)
    assert plan.mandatory["mode"] == "EXACT"
    assert plan.mandatory["value"] == 48
    assert plan.optional_multiplier["value"] == 2
    assert plan.final["value"] == 96
