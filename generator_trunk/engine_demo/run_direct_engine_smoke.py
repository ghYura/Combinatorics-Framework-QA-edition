#!/usr/bin/env python3
"""Launcher for the direct engine demonstration.

`list` / `plan` are side-effect-free and need no database. `run` executes the
bounded full chain: Generator -> Core -> Reader -> Executor -> persistence ->
formal Analyzer.

This launcher is deliberately thin. It does not re-implement lifecycle, budget,
policy or evidence logic — it invokes the canonical `bundle_run.py` entry point
as a subprocess, which is the documented boundary a reference application (or a
demonstration) is supposed to use. A second orchestrator would be a second
source of truth.

Planning always precedes execution: the brace chain's cardinality is genuinely
runtime-known, so the plan reports UNKNOWN and the run carries an explicit,
recorded bounded materialization gate instead of pretending to a count nobody
can compute in advance.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parent.parent
BUNDLE = FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"

SCENARIO = "direct_engine_smoke"
SPEC_DIR = HERE / SCENARIO
GOALS = "stages:max,retained:max,ops:min"

# The brace chain materializes 8 roots. The gate is set just above that so a
# structural regression that multiplies the space (typically a missing
# FW_Exclude on an intermediate brace target) fails the run instead of quietly
# executing hundreds of redundant candidates.
BUDGET_FINAL_CANDIDATES = 64
BUDGET_MANDATORY_ROWS = 64
OVERRIDE_REASON = ("bounded direct engine smoke: higher-order brace cardinality is "
                   "runtime-known and capped by explicit budgets")


def _plan_command(out_dir: Path) -> "list[str]":
    return [sys.executable, str(BUNDLE), "plan", str(SPEC_DIR), "--out", str(out_dir)]


def _run_command(args: argparse.Namespace) -> "list[str]":
    return [
        sys.executable, str(BUNDLE), str(SPEC_DIR),
        "--db", args.db,
        "--run-id", args.run_id,
        "--runs-root", str(args.runs_root.resolve()),
        "--main-port", str(args.main_port),
        "--results-port", str(args.results_port),
        "--lang", "py",
        # Checked-in, reviewed candidate source in this repository: the reviewed
        # trusted-local origin class. Generated or imported candidates must not
        # reuse this profile.
        "--execution-policy-profile", "trusted-local",
        "--candidate-origin", "reviewed-checked-in",
        "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
        "--analyzer", GOALS,
        "--analysis-mode", "formal",
        "--allow-extreme",
        "--override-budget", OVERRIDE_REASON,
        "--budget-final-candidates", str(BUDGET_FINAL_CANDIDATES),
        "--budget-mandatory-rows", str(BUDGET_MANDATORY_ROWS),
    ]


def _checked(command: "list[str]") -> None:
    completed = subprocess.run(command, cwd=FRAMEWORK_ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("list", "plan", "run"))
    parser.add_argument("--db", default="engine_demo_smoke")
    parser.add_argument("--run-id", default="direct-engine-smoke")
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--plan-out", type=Path, default=Path("/tmp/engine-demo-plan"))
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    args = parser.parse_args(argv)

    if args.command == "list":
        print(f"{SCENARIO}\t{SPEC_DIR}")
        print(f"  goals: {GOALS} (formal)")
        print(f"  bounded gate: final<={BUDGET_FINAL_CANDIDATES}, mandatory<={BUDGET_MANDATORY_ROWS}")
        return 0

    _checked(_plan_command(args.plan_out))
    if args.command == "plan":
        return 0

    for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD"):
        if not os.environ.get(key):
            raise SystemExit(f"{key} is not set; the run stage needs both database passwords")
    _checked(_run_command(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
