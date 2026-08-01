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
