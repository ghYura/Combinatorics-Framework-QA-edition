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

"""Translate confirmed teaching suggestions into the existing workbook model."""

from __future__ import annotations

import re
from typing import Iterable

from invitation_wizard.model import FactorDraft, InvitationDraft

from .grid_model import GridProject


def _sheet_name(label: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", label.strip()).strip("_").upper() or "FACTOR"
    base = base[:31]
    candidate = base
    number = 2
    while candidate in used:
        suffix = f"_{number}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        number += 1
    used.add(candidate)
    return candidate


def project_from_invitation(
    draft: InvitationDraft,
    selected_stress: Iterable[str] = (),
    visible_rows: int = 12,
) -> GridProject:
    selected = set(selected_stress)
    project = GridProject(name="guided_" + draft.domain, rows=[], directive_columns=7)
    used: set[str] = set()

    def add_factor(factor: FactorDraft, optional: bool = False) -> None:
        row = project.add_row(_sheet_name(factor.name, used), factor.values)
        verb = "FW_Permut" if factor.shape == "permute" else "FW_Combi(1)"
        if optional:
            row.directives[0] = "FW_Optional"
            row.directives[1] = verb
        else:
            row.directives[0] = verb

    for factor in draft.factors:
        add_factor(factor)
    for factor in draft.stress_actions:
        if factor.key in selected:
            add_factor(factor, optional=True)
    project.add_blank_rows(max(0, visible_rows - len(project.rows)))
    return project
