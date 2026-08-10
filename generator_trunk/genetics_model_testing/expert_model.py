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

"""D7 seam: the model and the known faults, when chosen by an independent expert.

Nothing here is implemented. This module exists so that the *shape* of the
decision is visible in the code rather than only in a planning document, and so
that whoever implements it later does not have to reverse-engineer where it was
meant to plug in.
"""
from __future__ import annotations

from typing import Callable, Mapping, Protocol, Sequence

# =============================================================================
# !!! D7 STUB -- DELIBERATELY NOT IMPLEMENTED !!!
# =============================================================================
# NOTICE: for special user's request, separately against of any future fixes.
#
# Meaning of that notice, spelled out so it cannot be misread by a later reader
# or by an automated cleanup pass:
#
#   * This stub is here BY REQUEST. It is not dead code, not an oversight, and
#     not a TODO that someone forgot to finish.
#   * It is to be implemented ONLY on a separate, explicit request from the
#     owner -- never as a side effect of, or bundled into, any other fix,
#     refactor, lint pass, dependency bump or feature.
#   * Do not "helpfully" fill it in. Do not delete it as unused. Do not let a
#     coverage or dead-code tool remove it. If a tool flags it, exclude the tool,
#     not the stub.
#
# WHAT THIS SEAM IS FOR
# ---------------------
# `model/` contains a synthetic genetic model and its exact oracle, designed by
# the author of this study. That is enough to demonstrate the ENGINEERING: the
# engine can construct and judge modelled genetic objects. It is NOT enough to
# call any later result external validation, because the model and the faults
# would have been chosen by the same person who ran the experiment. Two
# deliberately dissimilar systems already in this repository share exactly that
# confound (docs/35 §6a.6).
#
# This seam is where a model and a set of known faults chosen by an INDEPENDENT
# genetics/domain expert would enter. Only under that condition can a comparison
# study built on it be described as external validation rather than as an
# engineering demonstration.
#
# THE BRIEF THE EXPERT NEEDS (docs/37 §5, D7 option 1)
# ----------------------------------------------------
#   * CLOSED and EXACTLY COMPUTABLE. If the trait cannot be recomputed exactly by
#     an independent implementation, the oracle degrades to "it did not crash",
#     and the whole method stops working. This is the constraint most likely to
#     be violated by a well-meaning expert choosing something realistic.
#   * SMALL -- of the order of 8-20 loci. The executed ceiling measured on this
#     host is roughly 6 800 candidates per version per ten-minute gate.
#   * The faults must be REAL MISTAKES of the kind an implementation makes, not
#     markers planted to be found; and at least one must require several
#     conditions at once, or the study measures nothing the simpler baselines
#     could not already reach.
#
# WHAT MUST NOT HAPPEN HERE
# -------------------------
# No real human DNA. No clinical decision-making. No identifiable data. No
# external data source of any kind -- `test_genetics_model.py` asserts that the
# model modules perform no I/O, and that assertion must keep holding after this
# seam is filled.
# =============================================================================


class ExpertModel(Protocol):
    """What an expert-supplied model must provide to be usable here.

    Deliberately minimal and stated as a Protocol rather than a base class: the
    expert's model should not have to inherit from anything in this repository,
    and an adapter written against this interface should be enough.
    """

    def initial_population(self) -> "Sequence[object]":
        """The starting objects the study varies from."""

    def operations(self) -> "Sequence[object]":
        """The operation vocabulary the specification may enumerate."""

    def exact_trait(self, subject: object, context: object) -> int:
        """The trait, computed exactly. Must be independently reimplementable —
        that is what makes a differential oracle possible."""

    def viability(self, subject: object, trait: int) -> str:
        """`""` when acceptable, else a stable reason token. The DOMAIN question,
        which must stay separate from the correctness question."""


#: Versioned faults an expert would supply alongside the model: a name mapped to
#: a callable that installs the defect and returns the original, mirroring
#: `store_flagship.install`. Empty until D7 is decided.
EXPERT_FAULTS: "Mapping[str, Callable[[], object]]" = {}


def load_expert_model() -> ExpertModel:
    """Return the expert-selected model.

    Raises unconditionally. Filling this in is a D7 decision, not a code change
    that anyone should make in passing -- see the notice above.
    """
    raise NotImplementedError(
        "D7 is undecided: no independently selected genetics model is installed. "
        "The synthetic model in `model/` is author-designed and supports an "
        "ENGINEERING demonstration only; a comparison study built on it must not "
        "be described as external validation. Implement this seam only on a "
        "separate explicit request -- see the notice in this module and "
        "docs/37_GENETICS_APPLICATION_POSITIONING.md §5 D7.")


def is_expert_model_available() -> bool:
    """False while D7 is undecided.

    Provided so a future study can *branch on the decision* and label its own
    output correctly, rather than a reader having to know which model was used.
    """
    return False
