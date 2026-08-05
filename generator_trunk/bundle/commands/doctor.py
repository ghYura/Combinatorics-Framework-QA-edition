"""`bundle doctor` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from ..cliutil import _resolve_bundle_config
from ..doctor import doctor_exit_code, doctor_report_to_dict, format_doctor_report, run_doctor
from ..errors import BundleError, PreflightError, ok, report_and_exit
from ..jsonio import write_json_atomic


def cmd_doctor(a) -> None:
    """`bundle doctor` (STEP 15): diagnose the environment — Python/Java/jars/
    DB connectivity+privileges/scratch/analyzer/sandbox — independent of and
    without performing an actual run. Read-only: creates nothing in any
    production DB, installs nothing (action 4/5)."""
    cfg, _sources = _resolve_bundle_config(a)
    # STEP 41: `--deploy` makes doctor automatically target the LOCAL deploy stack
    # (ports + password read from deploy/.env) instead of the host PostgreSQL, so
    # the deployment profile is validated through the REAL `bundle doctor` CLI.
    if getattr(a, "deploy", False):
        from .. import deploy
        try:
            cfg = deploy.apply_to_config(cfg)
        except deploy.DeployError as exc:
            raise PreflightError(str(exc))
        print(f"(using LOCAL deploy stack: 127.0.0.1:{cfg.main_db_port}/{cfg.results_db_port} from deploy/.env)")
    checks = run_doctor(cfg)
    print("BUNDLE DOCTOR")
    print(format_doctor_report(checks))
    report = doctor_report_to_dict(checks)
    print(f"\noverall: {report['overall']}")
    if a.json:
        out_path = Path(a.json)
        write_json_atomic(out_path, report)
        ok(f"report -> {out_path}")
    code = doctor_exit_code(checks)
    if code:
        sys.exit(code)


def _main_doctor(argv):
    ap = argparse.ArgumentParser(prog="bundle_run doctor",
                                 description="Diagnose the environment (Python/Java/jars/DB/scratch/...) "
                                             "without starting a run or touching any production DB.")
    ap.add_argument("--json", default="", metavar="PATH",
                    help="also write the report as JSON to PATH")
    ap.add_argument("--config-file", default="", metavar="PATH",
                    help="JSON file of BundleConfig overrides (lowest-precedence layer above defaults)")
    ap.add_argument("--deploy", action="store_true",
                    help="diagnose the LOCAL deploy stack instead of the host DBs — auto-reads "
                         "ports/password from deploy/.env (run `bundle deploy up` first)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_doctor(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
