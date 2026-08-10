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

"""Shared candidate bootstrap for the Automation Scheme Studio campaign."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from generator_trunk.sut_paths import project_path


def _sut_project() -> Path:
    explicit = os.environ.get("AUTOMATION_STUDIO_ROOT")
    project = Path(explicit).expanduser().resolve() if explicit else project_path(
        "automation_scheme_studio"
    )
    if not (project / "src" / "automation_constructor").is_dir():
        raise RuntimeError(
            "automation-scheme-studio was not found; set BUNDLE_SUT_ROOT to the "
            "directory containing automation-scheme-studio or set "
            "AUTOMATION_STUDIO_ROOT to that project directly"
        )
    return project


def ensure_sut_on_path() -> bool:
    """Put the SUT's ``src/`` on ``sys.path`` if the checkout can be located.

    Returns True when ``automation_constructor`` is importable afterwards. Unlike
    :func:`_sut_project` this never raises, so a caller that must decide between
    "run the gate" and "skip the gate" — a pytest module at collection time — can
    ask without handling an exception first.
    """
    try:
        source = _sut_project() / "src"
    except RuntimeError:
        return False
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return True


def _api() -> dict[str, Any]:
    source = _sut_project() / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from automation_constructor.experiments.bundle_search import (
        SearchPlan,
        bootstrap_check,
        catalog_parameter_defaults,
        catalog_terminal_contract,
        evaluate_plan,
    )
    return {
        "SearchPlan": SearchPlan,
        "bootstrap_check": bootstrap_check,
        "catalog_parameter_defaults": catalog_parameter_defaults,
        "catalog_terminal_contract": catalog_terminal_contract,
        "evaluate_plan": evaluate_plan,
    }


def initialize_candidate(
    *, family: str, battery: str, duration: float, dt: float
):
    api = _api()
    plan = api["SearchPlan"](
        family=family,
        battery=battery,
        duration=duration,
        dt=dt,
    )
    initial = api["catalog_parameter_defaults"]()
    terminals = api["catalog_terminal_contract"]()
    return plan, initial, terminals


def finish_candidate(plan, terminal_contract):
    api = _api()
    result = api["evaluate_plan"](plan)
    result.metrics["declared_terminal_count"] = sum(
        len(terminals) for terminals in terminal_contract.values()
    )
    result.metrics["declared_component_types"] = len(terminal_contract)
    return result


def preflight() -> dict[str, Any]:
    return _api()["bootstrap_check"]()
