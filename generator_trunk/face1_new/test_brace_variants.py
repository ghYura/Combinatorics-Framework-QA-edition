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

"""Coverage for full-field and nested FW_(...) forms accepted by Core."""

import pytest

from face1_new.grid_model import EMPTY, GridProject, TEMPLATES


def test_palette_contains_full_field_and_nested_brace_shapes():
    directives = {template.directive for template in TEMPLATES}

    assert {
        "FW_(START,,LEFT,RELATION,RIGHT,,END,SEPARATOR,1:1)",
        "FW_(START,,LEFT,RELATION,RIGHT,,END,SEPARATOR,1:N)",
        "FW_(START,,LEFT,RELATION,RIGHT,,END,SEPARATOR,M:1)",
        "FW_(START,,LEFT,RELATION,RIGHT,,END,SEPARATOR,M:M)",
        "FW_(START,,LEFT,RELATION,RIGHT,,END,SEPARATOR,M:N)",
        "FW_(,,FW_(),,RIGHT,,,,M:N)",
        "FW_(,,LEFT,,FW_(),,,,M:N)",
        "FW_(,,FW_(),,FW_(),,,,M:N)",
        "FW_(,,FW_()G,,RIGHT,,,,M:N)",
        "FW_(,,LEFT,,FW_()G,,,,M:N)",
        "FW_(,,FW_()G,,FW_()G,,,,M:N)",
    } <= directives


@pytest.mark.parametrize("nested_marker", ["FW_()", "FW_()G"])
def test_nested_operand_markers_pass_the_positional_brace_validator(nested_marker):
    project = GridProject(name="nested", rows=[], directive_columns=4)
    left = project.add_row("LEFT", ["a"])
    right = project.add_row("RIGHT", ["b"])
    joined = project.add_row("JOIN", [EMPTY])
    left.directives[0] = "FW_Exclude"
    right.directives[0] = "FW_Exclude"
    joined.directives[0] = f"FW_(,,{nested_marker},,RIGHT,,,,M:N)"

    messages = [issue.message for issue in project.validate()]
    assert not any("brace operands must be" in message for message in messages)
