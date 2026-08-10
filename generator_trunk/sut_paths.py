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

"""Portable locations for external Systems Under Test (SUTs).

By default, SUT projects live in ``suts/`` at the Bundle repository root.  Set
``BUNDLE_SUT_ROOT`` to use a shared checkout elsewhere.  A relative override is
interpreted from the repository root, so callers behave the same regardless of
their current working directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType
from typing import Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_SUT_ROOT: Final[Path] = REPO_ROOT / "suts"

PROJECT_DIRS = MappingProxyType({
    "advanced_surrogate": "advanced_surrogate",
    "automation_scheme_studio": "automation-scheme-studio",
    "telemetry_catalog": "telemetry_catalog_service",
    "fintech": "fin_tech_to_test",
    "gpt4lite": "GPT-4-Lite_sandbox",
    "legacy_surrogate_apps": "legacy_surrogate_apps",
    "llm_transformer": "llm_transformer_testme",
    "sieve3d": "3Dprofile-VS-2Dsieve",
})


#: Sibling checkout names to look for when ``suts/`` is not populated in-tree.
#: Several test modules already discovered these by hand; doing it once here is
#: what stops the answer depending on which module ran first.
SIBLING_SUT_DIRS: Final[tuple] = ("SUT", "SUT-main")


def discovered_sut_root() -> Path:
    """The SUT root to use when nothing is configured.

    Prefers a populated in-repository ``suts/``; failing that, a sibling checkout
    next to the repository that actually contains at least one known project.
    Falls back to :data:`DEFAULT_SUT_ROOT` so the answer is always a path, whether
    or not anything is installed there.
    """
    if any((DEFAULT_SUT_ROOT / d).is_dir() for d in PROJECT_DIRS.values()):
        return DEFAULT_SUT_ROOT
    for sibling in SIBLING_SUT_DIRS:
        candidate = REPO_ROOT.parent / sibling
        if any((candidate / d).is_dir() for d in PROJECT_DIRS.values()):
            return candidate
    return DEFAULT_SUT_ROOT


def sut_root() -> Path:
    """Return the configured SUT root without requiring it to exist.

    Resolution is a pure function of the environment and the filesystem, so two
    callers in one process always agree. It used to depend on import order:
    `bundle.stages` pinned ``BUNDLE_SUT_ROOT`` to the in-repository ``suts/`` at
    import time, which then suppressed the sibling-checkout discovery that
    several test modules performed for themselves. Whether a SUT was found
    therefore depended on whether something had imported `bundle.stages` first.
    """
    configured = os.environ.get("BUNDLE_SUT_ROOT")
    root = Path(configured).expanduser() if configured else discovered_sut_root()
    if not root.is_absolute():
        root = REPO_ROOT / root
    return root.resolve()


def project_path(project: str, *parts: str | os.PathLike[str]) -> Path:
    """Return a named SUT project path, optionally joined with child parts."""

    try:
        project_dir = PROJECT_DIRS[project]
    except KeyError as exc:
        names = ", ".join(sorted(PROJECT_DIRS))
        raise ValueError(f"unknown SUT project {project!r}; choose one of: {names}") from exc
    return sut_root().joinpath(project_dir, *parts)


def project_paths() -> dict[str, Path]:
    """Return all canonical named project paths for the active SUT root."""

    return {name: project_path(name) for name in PROJECT_DIRS}
