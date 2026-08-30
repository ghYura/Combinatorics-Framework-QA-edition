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

"""`bundle triage` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
import glob
import os
from pathlib import Path

from ..errors import PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def _resolve_run(target: str) -> Path:
    """Accept a run directory, a scratch root, or a `<scratch>/<db>` path.

    Picks the most recent run when handed a container, which is what someone
    typing `bundle triage /tmp/fw_work/mydb` means.
    """
    p = Path(target)
    if (p / "metrics.kv").is_file() or (p / "executor-summary.json").is_file():
        return p
    for pattern in ("runs/*", "*/runs/*"):
        runs = sorted(glob.glob(str(p / pattern)))
        if runs:
            return Path(runs[-1])
    raise PreflightError(
        f"no run directory under {target!r}: expected it to hold metrics.kv / "
        f"executor-summary.json, or to contain runs/<run-id>/")


def cmd_triage(a) -> None:
    """Group a finished run's failures into findings, each with a minimal
    witness, and rank the axes that explain them. Reads only what the run
    persisted; never re-executes a candidate. Side-effect-free apart from an
    optional --json report."""
    from .. import triage as tri

    run = _resolve_run(a.run)
    data = tri.triage_run(run)
    print(tri.format_report(data, top_axes=a.top))

    if a.json:
        write_json_atomic(Path(a.json), data)
        ok(f"triage report -> {a.json}")
    elif a.write:
        out = run / "triage.json"
        write_json_atomic(out, data)
        ok(f"triage report -> {out}")

    if a.fail_on_findings and data["findings"]:
        raise PreflightError(
            f"{len(data['findings'])} distinct finding(s) in this run; "
            f"{data['corpus']['failing']} of {data['corpus']['records']} candidates failed")


def _main_triage(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run triage",
        description="Turn a finished campaign's verdicts into a report: failures grouped into "
                    "distinct findings, a minimal witness for each, and the axes whose values "
                    "explain them. Reads the run's own K=V corpus and outcome summary; it never "
                    "re-executes a candidate, because re-running generated code outside the "
                    "recorded execution policy would bypass the sandbox and a stateful candidate "
                    "would give a different verdict anyway.")
    ap.add_argument("run", metavar="RUN",
                    help="a run directory, or a scratch/db path containing runs/<run-id>/")
    ap.add_argument("--json", default="", metavar="PATH", help="write the report JSON to PATH")
    ap.add_argument("--write", action="store_true",
                    help="write triage.json into the run directory")
    ap.add_argument("--top", type=int, default=12, metavar="N",
                    help="how many enrichment rows to show (default 12)")
    ap.add_argument("--fail-on-findings", action="store_true",
                    help="exit non-zero when the run produced any finding")
    ap.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        cmd_triage(a)
    except Exception as exc:                                  # noqa: BLE001
        report_and_exit(exc, debug=a.debug)
