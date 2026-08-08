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
