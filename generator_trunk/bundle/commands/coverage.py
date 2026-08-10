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

"""`bundle coverage` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, ok, report_and_exit
from ..jsonio import read_json, write_json_atomic


def cmd_coverage(a) -> None:
    """Reference-coverage audit: which engine capabilities each registered
    target exercises, its architectural role/composition depth, and what its
    launcher pins. Side-effect-free; deterministic for a source revision."""
    from .. import coverage as cov
    measurements = read_json(Path(a.measurements)) if a.measurements else None
    report = cov.reference_coverage_report(measurements)
    print(cov.format_coverage_report(report))
    if a.json:
        write_json_atomic(Path(a.json), report)
        ok(f"reference-coverage report -> {a.json}")


def _main_coverage(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run coverage",
        description="Audit engine capability exposure: engine composition vocabulary vs. the "
                    "subset each registered coverage target exercises, its role/order, "
                    "and the policy restrictions its launcher imposes. Reports individual facts "
                    "— never a single aggregate 'power' score.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the report JSON to PATH")
    ap.add_argument("--measurements", default="", metavar="PATH",
                    help="merge a bundle bench --stages reference_overhead report so each "
                         "application's per-phase measurement is carried into the audit")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_coverage(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
