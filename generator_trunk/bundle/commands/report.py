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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""`bundle report` — render a finished run as readable HTML (Face 3).

Side-effect-free with respect to the engine: it reads one run directory and
writes one HTML file. No database, no JAR, no stage, no re-execution -- which is
why it is safe to point at a failed or interrupted run.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..cliutil import _resolve_bundle_config
from ..errors import BundleError, ok, report_and_exit
from ..jsonio import write_json_atomic
from ..report import collect, format_text, render_html
from ..resume import resolve_run_layout


def cmd_report(a) -> None:
    """Render `<run-dir|run-id>` into a self-contained HTML results page.

    Face 3 is the results-reading surface: the consumption half of the tool,
    for a reader who did not author the spec and should not have to read CLI
    text output to find out what a run concluded.
    """
    cfg, _sources = _resolve_bundle_config(a)
    layout = resolve_run_layout(a.run, runs_root=(a.runs_root or None),
                                scratch_root=cfg.scratch_root or None)
    data = collect(layout.root)

    print(format_text(data))

    out = Path(a.out) if a.out else layout.root / "reports" / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data), encoding="utf-8")
    ok(f"report -> {out}")

    if a.json:
        json_path = Path(a.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(json_path, data)
        ok(f"report data -> {json_path}")


def _main_report(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run report",
        description="Render a finished run as a self-contained HTML results page. "
                    "Reads only what the run already recorded; re-executes nothing.")
    ap.add_argument("run", help="run directory or bare run ID")
    ap.add_argument("--out", default="", metavar="PATH",
                    help="write the HTML here (default: <run-dir>/reports/report.html)")
    ap.add_argument("--json", default="", metavar="PATH",
                    help="also write the collected report data as JSON")
    ap.add_argument("--runs-root", default="", metavar="PATH",
                    help="directory run directories live under, when resolving a bare run ID")
    ap.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON file of BundleConfig overrides (lowest-precedence layer above defaults)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_report(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
