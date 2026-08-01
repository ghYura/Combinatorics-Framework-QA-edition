#!/usr/bin/env python3
"""List, plan, smoke, or run Bundle-native AI evaluation scenarios unattended."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable

if __package__:
    from .reporting import write_common_report
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from AI_combi_testing_platform.reporting import write_common_report



HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[1]
BUNDLE = FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"
SCENARIO_ROOT = HERE / "scenarios"
SCENARIOS = {
    "00_smoke": "bounded first-order exact-control chain",
    "01_operator_smoke": "FW_Group + FW_PermutR + three nested braces",
    "10_constraint_stack": "constraint breakpoint ladder",
    "20_logic_and_cancellation": "logic plus repeated cancellation identities",
    "30_semantic_interference": "semantic costumes and irrelevant noise",
    "40_long_range_dependency": "delayed definition and repeated context",
    "50_format_and_instruction_order": "schema and section-order resilience",
    "60_higher_order_prompt_programs": "fourth-order recursive prompt programs",
    "70_router_regression_dataset": "shared product-mode evidence matrix",
}
SMOKE_SCENARIOS = ("00_smoke", "01_operator_smoke")
EXTREME_SCENARIOS = ("01_operator_smoke", "60_higher_order_prompt_programs")
GOALS = (
    "correct:max,all_constraints_pass:max,semantic_invariance_ok:max,"
    "complexity:max,latency_us:min,cost_microusd:min"
)


def _environment(config: Path | None, allow_external: bool) -> dict[str, str]:
    env = os.environ.copy()
    framework = str(FRAMEWORK_ROOT)
    python_path = [item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]
    if framework not in python_path:
        env["PYTHONPATH"] = os.pathsep.join((framework, *python_path))
    env.setdefault("AI_COMBI_ENVIRONMENT_ID", "local")
    if config is not None:
        env["AI_COMBI_CONFIG"] = str(config.resolve())
    if allow_external:
        env["AI_COMBI_ALLOW_EXTERNAL"] = "1"
    else:
        env.pop("AI_COMBI_ALLOW_EXTERNAL", None)
    return env


def _require_external_authorization(args: argparse.Namespace) -> None:
    if not args.allow_external:
        return
    if args.config is None:
        raise SystemExit("--allow-external requires --config")
    if args.budget_requests is None or args.budget_requests < 1:
        raise SystemExit("--allow-external requires a positive --budget-requests")
    if args.budget_monetary_cost is None or args.budget_monetary_cost < 0:
        raise SystemExit(
            "--allow-external requires --budget-monetary-cost (zero is valid)"
        )
    if args.acknowledge_trusted_network_code != "reviewed-controlled-candidates":
        raise SystemExit(
            "--allow-external also requires "
            "--acknowledge-trusted-network-code reviewed-controlled-candidates"
        )


def _budget_args(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    if args.budget_requests is not None:
        values.extend(["--budget-requests", str(args.budget_requests)])
    if args.budget_monetary_cost is not None:
        values.extend(["--budget-monetary-cost", str(args.budget_monetary_cost)])
    if args.cost_per_candidate is not None:
        values.extend(["--cost-per-candidate", str(args.cost_per_candidate)])
    return values


def _plan_command(
    name: str,
    destination: Path,
    args: argparse.Namespace,
) -> list[str]:
    return [
        sys.executable,
        str(BUNDLE),
        "plan",
        str(SCENARIO_ROOT / name),
        "--out",
        str(destination),
        "--repeat",
        str(args.repeat),
        "--repeat-policy",
        "local",
        "--repeat-scope",
        "metrics" if args.repeat > 1 else "all",
        *_budget_args(args),
    ]


def _run_command(
    name: str,
    run_id: str,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        sys.executable,
        str(BUNDLE),
        str(SCENARIO_ROOT / name),
        "--db",
        args.db or f"ai_combi_{name}",
        "--run-id",
        run_id,
        "--runs-root",
        str(args.runs_root.resolve()),
        "--main-port",
        str(args.main_port),
        "--results-port",
        str(args.results_port),
        "--lang",
        "py",
        "--candidate-sink",
        "sharded",
        "--execution-policy-profile",
        "trusted-local",
        "--candidate-origin",
        "reviewed-checked-in",
        "--acknowledge-trusted-local",
        "reviewed checked-in scenario fragments in this repository",
        "--analyzer",
        GOALS,
        "--analysis-mode",
        "formal",
        "--repeat",
        str(args.repeat),
        "--repeat-policy",
        "local",
        "--repeat-scope",
        "metrics" if args.repeat > 1 else "all",
    ]
    if name in EXTREME_SCENARIOS:
        command.extend(
            [
                "--allow-extreme",
                "--override-budget",
                "reviewed Bundle-native AI higher-order composition",
            ]
        )
    command.extend(_budget_args(args))
    return command


def _run_checked(
    command: list[str],
    *,
    env: dict[str, str],
) -> None:
    completed = subprocess.run(
        command,
        cwd=FRAMEWORK_ROOT,
        env=env,
        check=False,
    )
    if completed.returncode:
        raise SystemExit(completed.returncode)


def _select(args: argparse.Namespace) -> tuple[str, ...]:
    if args.scenario:
        return tuple(args.scenario)
    if args.command == "smoke":
        return SMOKE_SCENARIOS
    return tuple(SCENARIOS)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "plan", "smoke", "run"))
    parser.add_argument("--scenario", action="append", choices=tuple(SCENARIOS))
    parser.add_argument(
        "--db",
        default="",
        help=("override the database name for a single selected scenario; intended for "
              "isolated harnesses/benchmarks that must create and clean a unique database"),
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="override the run id for a single selected scenario",
    )
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--output-dir", type=Path, default=HERE / "campaign_results")
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--budget-requests", type=int)
    parser.add_argument("--budget-monetary-cost", type=float)
    parser.add_argument("--cost-per-candidate", type=float)
    parser.add_argument("--acknowledge-trusted-network-code", default="")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    if args.command == "list":
        for name, description in SCENARIOS.items():
            print(f"{name}\t{description}")
        return 0

    _require_external_authorization(args)
    selected = _select(args)
    if (args.db or args.run_id) and len(selected) != 1:
        parser.error("--db/--run-id overrides require exactly one selected --scenario")
    env = _environment(args.config, args.allow_external)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Every executable campaign is planned immediately before DB/runtime work.
    for name in selected:
        plan_dir = Path("/tmp") / f"ai-combi-plan-{name}-{stamp}"
        print(f"\n==> plan {name}", flush=True)
        _run_checked(_plan_command(name, plan_dir, args), env=env)
    if args.command == "plan":
        return 0

    missing = [
        key
        for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD")
        if not env.get(key)
    ]
    if missing:
        parser.error("set " + " and ".join(missing))

    completed: list[tuple[str, Path]] = []
    for name in selected:
        run_id = args.run_id or f"ai-combi-{name}-{stamp}"
        print(f"\n==> run {name}", flush=True)
        _run_checked(_run_command(name, run_id, args), env=env)
        completed.append((name, args.runs_root.resolve() / run_id))
    report = write_common_report(completed, args.output_dir.resolve())
    print(
        f"\nCOMPLETE: {report['validated_candidates']} candidates; "
        f"report={args.output_dir.resolve() / 'common-results.md'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
