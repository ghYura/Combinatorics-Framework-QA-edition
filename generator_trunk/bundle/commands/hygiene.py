"""`bundle hygiene` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_hygiene(a) -> None:
    """STEP 43: report the backup inventory + the production compile-source-set
    verification + the archival proposal. REPORT-ONLY — moves/deletes never happen
    here (apply_archival needs explicit code-level approval). Exits non-zero if the
    production compile source set captures a backup (an acceptance violation)."""
    from .. import hygiene
    print(hygiene.format_report())
    if a.json:
        write_json_atomic(Path(a.json), hygiene.archival_proposal())
        ok(f"hygiene proposal -> {a.json}")
    clean, captured = hygiene.verify_clean()
    if not clean:
        raise PreflightError(f"production compile source set captures {len(captured)} backup file(s): "
                             + ", ".join(b.relpath for b in captured))


def _main_hygiene(argv):
    ap = argparse.ArgumentParser(prog="bundle_run hygiene",
                                 description="STEP 43: separate production sources from historical backups. "
                                             "Inventories backups (with checksums), verifies the compile source "
                                             "set excludes them, proposes archival. NEVER deletes/moves.")
    ap.add_argument("--json", default="", metavar="PATH", help="write the archival PROPOSAL (no execution) to PATH")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_hygiene(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
