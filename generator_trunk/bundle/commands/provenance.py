"""`bundle provenance` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_provenance(a) -> None:
    """Provenance and third-party license inventory. NON-OPERATIVE: it gathers
    evidence for a publication decision, activates nothing, and is not legal
    advice. Side-effect-free."""
    from .. import provenance as prov
    data = prov.report()
    print(prov.format_report(data))
    if a.json:
        write_json_atomic(Path(a.json), data)
        ok(f"provenance inventory -> {a.json}")
    if a.fail_on_blockers and data["blockers"]:
        raise PreflightError(
            f"{len(data['blockers'])} publication blocker(s) outstanding: "
            + ", ".join(b["id"] for b in data["blockers"]))


def _main_provenance(argv):
    ap = argparse.ArgumentParser(
        prog="bundle_run provenance",
        description="Evidence for a publication decision: what the Git history can and cannot "
                    "show, how each tracked file is classified, and what every dependency "
                    "DECLARES about its own license. Records the owner's authorship claim as an "
                    "attestation and never as a finding. Activates nothing.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the inventory JSON to PATH")
    ap.add_argument("--fail-on-blockers", action="store_true",
                    help="exit non-zero while any publication blocker is outstanding")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_provenance(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
