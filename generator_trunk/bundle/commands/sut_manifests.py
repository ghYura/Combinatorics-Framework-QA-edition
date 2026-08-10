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

"""`bundle sut-manifests` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_sut_manifests(a) -> None:
    """Validate and report the canonical SUT adapter manifests. Side-effect-free."""
    from .. import sut_manifests as sm
    try:
        data = sm.report()
    except sm.SutManifestError as exc:
        raise PreflightError(str(exc))
    print(sm.format_report(data))
    if a.json:
        write_json_atomic(Path(a.json), data)
        ok(f"SUT manifest inventory -> {a.json}")
    # Review item B.1: fail on EVERY drift list. Failing only on missing paths
    # let a canonical manifest claim a CI gate that no workflow step runs, which
    # is the more dangerous of the two — a missing path is visible, an unwired
    # gate looks like coverage.
    for name, entries in sorted((data.get("drift") or {}).items()):
        if entries:
            raise PreflightError(
                f"canonical SUT drift in {name!r} ({len(entries)}): {', '.join(entries)}")


def _main_sut_manifests(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run sut-manifests",
        description="Validate the canonical SUT adapter manifests: schema, capability row against "
                    "the registry, controls, oracle independence, and that every referenced test "
                    "and scenario path exists. Exits non-zero on drift.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the inventory JSON to PATH")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_sut_manifests(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
