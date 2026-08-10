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

"""`bundle cleanup` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
import sys
from ..cleanup import CleanupError, delete_run, format_cleanup_report, scan_run
from ..cliargs import _add_bundle_config_args
from ..cliutil import _resolve_bundle_config
from ..errors import BundleError, ok, report_and_exit
from ..jsonio import read_json
from ..models import RunStatus, run_manifest_from_dict
from ..resume import resolve_run_layout


# --------------------------------- cleanup (STEP 25) ------------------------- #
def cmd_cleanup(a) -> None:
    """`bundle cleanup <run-dir|run-id> [--yes]` (STEP 25): report -- and,
    only with explicit `--yes`, actually remove -- everything a finished run
    left behind (run directory, its `results_v2` rows, any temporary
    credential files). Always prints the dry-run inventory first, even when
    `--yes` is given, so the operator sees exactly what is about to disappear
    (action 2/3: dry-run shows files/bytes/DBs/credentials/age, real cleanup
    needs the explicit flag)."""
    cfg, _sources = _resolve_bundle_config(a)
    layout = resolve_run_layout(a.run, runs_root=(a.runs_root or None), scratch_root=cfg.scratch_root or None)
    manifest = run_manifest_from_dict(read_json(layout.manifest_path))
    if manifest.status in (RunStatus.PENDING, RunStatus.RUNNING):
        raise CleanupError(f"run '{manifest.run_id}' is still {manifest.status.value} -- "
                           f"cancel it first ('bundle cancel {a.run}'), then clean up")
    report = scan_run(layout, manifest, cfg, db=(a.db or None), retention_seconds=a.retention_seconds)
    print(format_cleanup_report(report))
    if not a.yes:
        ok("dry-run only -- nothing changed; pass --yes to actually delete")
        return
    if not report.db_name_matches_manifest:
        raise CleanupError(f"DB name {report.db_name!r} does not match run manifest's db_name "
                           f"{manifest.db_name!r} -- refusing to clean up (action 5)")
    print()
    log, log_path = delete_run(layout, manifest, cfg, db=(a.db or None))
    rows = log.deleted_results_v2_rows if log.deleted_results_v2_rows is not None else "?"
    ok(f"removed {log.removed_files} file(s) / {log.removed_bytes} byte(s) under {log.root}, "
       f"{rows} results_v2 row(s) for run_id={layout.run_id!r} from {log.db_name!r}")
    ok(f"cleanup action log -> {log_path}")


def _main_cleanup(argv):
    ap = argparse.ArgumentParser(prog="bundle_run cleanup",
                                 description="Inspect (dry-run, default) or remove (--yes) everything a "
                                             "finished run left behind: its directory, results_v2 rows, "
                                             "and any temporary credential files.")
    ap.add_argument("run", metavar="<run-dir|run-id>",
                    help="path to an existing run directory (containing run.json), "
                         "or a bare run ID to look up under --runs-root / the scratch root's "
                         "'<db>/runs/<run-id>' layout")
    ap.add_argument("--runs-root", default="",
                    help="directory to search for a bare run ID under (in addition to "
                         "'<scratch-root>/*/runs/<run-id>', the default layout)")
    ap.add_argument("--dry-run", action="store_true",
                    help="(default) report only -- the same as omitting --yes; kept as an "
                         "explicit, self-documenting spelling for scripts/operators")
    ap.add_argument("--yes", action="store_true",
                    help="explicit confirmation required for real deletion (action 3) -- "
                         "without it, this command always behaves as a dry-run")
    ap.add_argument("--db", default="", metavar="NAME",
                    help="DB name to validate/operate against (default: the run manifest's "
                         "own db_name -- an explicit override that disagrees with it blocks "
                         "all DB-side action, see action 5)")
    ap.add_argument("--retention-seconds", type=float, default=None, metavar="SECONDS",
                    help="report whether this run's age clears a retention threshold "
                         "(informational only -- does not gate --yes)")
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_cleanup(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
    except KeyboardInterrupt:
        if a.debug:
            raise
        print("\n  ✗ interrupted")
        sys.exit(130)
