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

"""`bundle capabilities` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_capabilities(a) -> None:
    """Print/emit the generated capability matrix. Side-effect-free.

    The matrix is the single source for preflight, the documentation table, the
    CI case list and the GUIs' option availability, so this command is how each
    of those is refreshed — none of them is hand-maintained."""
    from .. import capabilities as caps
    matrix = caps.capability_matrix()
    if a.markdown:
        text = caps.format_matrix_markdown(matrix)
        if a.markdown == "-":
            print(text)
        else:
            Path(a.markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(a.markdown).write_text(text, encoding="utf-8")
            ok(f"capability matrix (markdown) -> {a.markdown}")
    else:
        print(caps.format_matrix_text(matrix))
    if a.json:
        write_json_atomic(Path(a.json), matrix)
        ok(f"capability matrix (json) -> {a.json}")
    if a.ci_cases:
        write_json_atomic(Path(a.ci_cases), {"schema": caps.SCHEMA, "cases": caps.ci_cases()})
        ok(f"CI cases -> {a.ci_cases}")
    if a.check:
        # Freshness gate: the checked-in documentation table must match what the
        # registry generates right now, or the two have drifted.
        target = Path(a.check)
        if not target.is_file():
            raise PreflightError(f"capability matrix document missing: {target}")
        current = caps.format_matrix_markdown(matrix)
        if target.read_text(encoding="utf-8") != current:
            raise PreflightError(
                f"{target} is stale: regenerate with "
                f"`bundle_run.py capabilities --markdown {target}`")
        ok(f"{target} is up to date with the capability registry")


def _main_capabilities(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run capabilities",
        description="The one generated capability matrix: which operator-visible combinations are "
                    "SUPPORTED, EXPERIMENTAL or UNSUPPORTED, with a stable reason code, the "
                    "required backend/artifact, the security boundary and the evidence for each. "
                    "Preflight, the documentation table, the CI case list and both GUIs are all "
                    "generated from this registry.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the matrix JSON to PATH")
    ap.add_argument("--markdown", default="", metavar="PATH",
                    help="write the human support table to PATH ('-' for stdout)")
    ap.add_argument("--ci-cases", default="", metavar="PATH",
                    help="write one CI case per runnable combination to PATH")
    ap.add_argument("--check", default="", metavar="PATH",
                    help="fail if the generated Markdown at PATH is stale (CI freshness gate)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_capabilities(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
