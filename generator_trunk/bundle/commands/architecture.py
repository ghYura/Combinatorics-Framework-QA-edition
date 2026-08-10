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

"""`bundle architecture` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_architecture(a) -> None:
    """Engine-first architecture gate: print the declared layer model and fail
    when a module imports across a forbidden boundary. Side-effect-free."""
    from .. import architecture as arch
    report = arch.architecture_report()
    print(arch.format_architecture_report(report))
    if a.json:
        write_json_atomic(Path(a.json), report)
        ok(f"architecture report -> {a.json}")
    if report["unclassified_paths"]:
        raise PreflightError(
            f"{len(report['unclassified_paths'])} repository tree(s) declare no architectural "
            f"layer: {', '.join(report['unclassified_paths'])}")
    if report["violations"]:
        raise PreflightError(
            f"{len(report['violations'])} dependency-direction violation(s) across the audited "
            f"non-test product layers; see the report above")


def _main_architecture(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run architecture",
        description="Print and enforce the engine-first architecture boundary: which layer each "
                    "tree belongs to, which imports are allowed, and which reference applications "
                    "are registered. Exits non-zero on a violation or an unclassified tree.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the report JSON to PATH")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_architecture(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
