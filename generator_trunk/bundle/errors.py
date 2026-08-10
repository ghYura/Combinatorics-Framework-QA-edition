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

from __future__ import annotations

import sys


def ok(msg):
    print(f"  ✓ {msg}")


# ------------------------------ exception hierarchy ------------------------- #
class BundleError(Exception):
    """Base for all Bundle control-plane errors.

    Carries a concise, user-facing message (str(exc)). Stage code raises these
    instead of calling sys.exit deep inside the package; the CLI boundary is the
    single place that turns a BundleError into a non-zero process exit.
    """


class PreflightError(BundleError):
    """Environment/spec is not ready to start a run (missing jar, DB down, ...)."""


class StageError(BundleError):
    """A pipeline stage (gen/core/sieve/reader/executor/analyzer/stress) failed."""


class InvariantError(BundleError):
    """A cross-stage count invariant did not hold (introduced fully in STEP 6)."""


class BudgetError(BundleError):
    """Placeholder for resource-budget gate violations, wired up in STEP 12."""


# -------------------------------- CLI boundary ------------------------------ #
def report_and_exit(exc: BundleError, *, debug: bool = False) -> "None":
    """The one path through which a BundleError becomes a process exit.

    Default: concise ``✗ <message>`` line, no traceback, exit code 1 — preserving
    the launcher's existing fail-fast exit semantics. ``debug=True`` re-raises so
    the full traceback reaches the user.
    """
    if debug:
        raise exc
    print(f"\n  ✗ {exc}")
    sys.exit(1)
