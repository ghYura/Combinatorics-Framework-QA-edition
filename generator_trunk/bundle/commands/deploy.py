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

"""`bundle deploy` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from ..errors import BundleError, PreflightError, ok, report_and_exit


def cmd_deploy(a) -> None:
    """STEP 41: drive the local dev DB stack. validate (no runtime needed) / up /
    down (data-preserving) / status. DeployError -> PreflightError -> concise exit."""
    from .. import deploy
    try:
        if a.command == "validate":
            print(deploy.format_validation(deploy.validate_profile()))
            ok("deploy profile valid (local-only, pinned, health-checked)")
        elif a.command == "up":
            rep = deploy.up(monitoring=a.monitoring)
            for svc, st in rep["health"].items():
                print(f"  {svc}: {st}")
            unhealthy = [s for s, st in rep["health"].items() if st != "healthy"]
            if unhealthy:
                raise deploy.DeployError(f"started but not healthy in time: {', '.join(unhealthy)}")
            ok(f"deploy up: {len(rep['started'])} container(s) authenticated and healthy "
               f"(env {rep['env_file']})")
        elif a.command == "down":
            rep = deploy.down(volumes=a.volumes)
            ok(f"deploy down: removed {len(rep['removed'])} container(s); "
               + ("data DELETED (--volumes)" if a.volumes else "data PRESERVED (volumes kept)"))
        elif a.command == "status":
            st = deploy.status()
            if st["runtime"] != "available":
                raise deploy.DeployError("BLOCKED: Docker runtime is not available")
            for name, info in st["services"].items():
                extra = f" health={info.get('health')}" if "health" in info else ""
                print(f"  {name}: running={info['running']}{extra}")
            ok("deploy status reported")
    except deploy.DeployError as exc:
        raise PreflightError(str(exc))


def _main_deploy(argv):
    ap = argparse.ArgumentParser(prog="bundle_run deploy",
                                 description="STEP 41: reproducible LOCAL dev DB stack (containers). "
                                             "LOCAL-ONLY (127.0.0.1); `down` preserves data by default; "
                                             "never auto-installs the runtime.")
    ap.add_argument("command", choices=["validate", "up", "down", "status"])
    ap.add_argument("--monitoring", action="store_true", help="[up] also start the optional monitoring container")
    ap.add_argument("--volumes", action="store_true",
                    help="[down] ALSO delete the data volumes (destructive; default keeps data)")
    ap.add_argument("--debug", action="store_true",
                    help="show full traceback on failure instead of a concise '✗ <message>' line")
    a = ap.parse_args(argv)
    try:
        cmd_deploy(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
