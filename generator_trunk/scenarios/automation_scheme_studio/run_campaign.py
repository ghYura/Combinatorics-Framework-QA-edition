#!/usr/bin/env python3
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

"""Plan or run the Automation Scheme Studio Bundle campaign."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[2]
SPECS = (
    "00_smoke",
    "01_ordered_serial",
    "02_deep_nested",
    "03_redundant_multiset",
    "04_brace_join",
    "05_cartesian_refinement",
    "06_feedback_path_covering",
)
GOALS = (
    "control_score:max,robustness_score:max,stability_score:max,"
    "settling_time_s:min,worst_error:min,overshoot_pct:min,control_effort:min"
)


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("BUNDLE_FRAMEWORK_ROOT"):
        env["BUNDLE_FRAMEWORK_ROOT"] = str(FRAMEWORK_ROOT)
    if not env.get("BUNDLE_SUT_ROOT"):
        for sibling_name in ("SUT", "SUT-main"):
            sibling_sut_root = FRAMEWORK_ROOT.parent / sibling_name
            if (sibling_sut_root / "automation-scheme-studio" / "src").is_dir():
                env["BUNDLE_SUT_ROOT"] = str(sibling_sut_root)
                break
    return env


def _bundle() -> Path:
    return FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"


def _selected(command: str, requested: list[str] | None) -> tuple[str, ...]:
    if requested:
        return tuple(requested)
    return (SPECS[0],) if command == "smoke" else SPECS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "bootstrap", "plan", "smoke", "run"))
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--spec", action="append", choices=SPECS)
    parser.add_argument(
        "--executor-workers", type=int, default=min(8, os.cpu_count() or 1)
    )
    args = parser.parse_args()
    env = _environment()
    if args.executor_workers < 1:
        parser.error("--executor-workers must be at least 1")
    env["AUTOMATION_BUNDLE_EXECUTOR_WORKERS"] = str(args.executor_workers)

    if args.command == "list":
        print("\n".join(SPECS))
        return 0
    if args.command == "bootstrap":
        return subprocess.call(
            [sys.executable, str(HERE / "RunMeFirstOnce.py")],
            cwd=FRAMEWORK_ROOT,
            env=env,
        )
    if args.command in {"smoke", "run"}:
        missing = [
            key for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD")
            if not env.get(key)
        ]
        if missing:
            parser.error("database password environment variables are required: " + ", ".join(missing))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for spec_name in _selected(args.command, args.spec):
        spec = HERE / spec_name
        stem = spec.name
        if args.command == "plan":
            output = Path("/tmp") / f"automation-studio-plan-{stem}-{stamp}"
            command = [sys.executable, str(_bundle()), "plan", str(spec), "--out", str(output)]
        else:
            db = "automation_studio_" + stem
            command = [
                sys.executable,
                str(_bundle()),
                str(spec),
                "--db", db,
                "--run-id", f"automation-{stem}-{stamp}",
                "--main-port", str(args.main_port),
                "--results-port", str(args.results_port),
                "--runs-root", str(args.runs_root),
                "--candidate-sink", "sharded",
                "--py-executor", str(HERE / "parallel_py_executor.py"),
                "--analyzer", GOALS,
                "--analysis-mode", "formal",
                "--execution-policy-profile", "trusted-local",
                "--candidate-origin", "reviewed-checked-in",
                "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
                "--unleash-initial-productivity-power",
            ]
        print(f"==> {spec_name}", flush=True)
        completed = subprocess.run(command, cwd=FRAMEWORK_ROOT, env=env, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
