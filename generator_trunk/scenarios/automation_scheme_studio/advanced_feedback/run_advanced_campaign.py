#!/usr/bin/env python3
"""Plan, smoke-test, or run the advanced recursive feedback campaign."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[3]
BUNDLE = FRAMEWORK_ROOT / "generator_trunk" / "bundle_run.py"
EXECUTOR = HERE.parent / "parallel_py_executor.py"
SPECS = (
    "00_smoke",
    "01_operator_smoke",
    "10_third_order_brace",
    "20_grouped_repetition",
)
SMOKE_SPECS = SPECS[:2]
HEAVY_SPECS = SPECS[2:]
EXTREME_SPECS = SPECS[1:]
GOALS = (
    ("control_score", "max"),
    ("robustness_score", "max"),
    ("stability_score", "max"),
    ("settling_time_s", "min"),
    ("worst_error", "min"),
    ("overshoot_pct", "min"),
    ("control_effort", "min"),
)
ANALYZER = ",".join(f"{key}:{direction}" for key, direction in GOALS)


def _environment(workers: int) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("BUNDLE_FRAMEWORK_ROOT", str(FRAMEWORK_ROOT))
    env["AUTOMATION_BUNDLE_EXECUTOR_WORKERS"] = str(workers)
    if not env.get("BUNDLE_SUT_ROOT"):
        for sibling in ("SUT-main", "SUT"):
            root = FRAMEWORK_ROOT.parent / sibling
            if (root / "automation-scheme-studio" / "src").is_dir():
                env["BUNDLE_SUT_ROOT"] = str(root)
                break
    return env


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a JSON object")
    return value


def _outcome(summary: dict[str, Any], name: str) -> int:
    outcomes = summary.get("outcomes")
    return int(outcomes.get(name, 0) or 0) if isinstance(outcomes, dict) else 0


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    lo = left["objectives"]
    ro = right["objectives"]
    weak = True
    strict = False
    for key, direction in GOALS:
        if key not in lo or key not in ro:
            return False
        left_value = float(lo[key])
        right_value = float(ro[key])
        better = (
            left_value >= right_value
            if direction == "max"
            else left_value <= right_value
        )
        strict_here = (
            left_value > right_value
            if direction == "max"
            else left_value < right_value
        )
        weak = weak and better
        strict = strict or strict_here
    return weak and strict


def _pareto(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    front: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates,
        key=lambda value: (
            str(value.get("suite_spec", "")),
            str(value.get("run_id", "")),
            str(value.get("candidate_id", "")),
        ),
    ):
        if any(_dominates(existing, candidate) for existing in front):
            continue
        front = [
            existing for existing in front
            if not _dominates(candidate, existing)
        ]
        front.append(candidate)
    return front


def _aggregate(
    completed: list[tuple[str, Path]],
    output_dir: Path,
) -> None:
    runs: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    total = 0
    aggregate_outcomes: dict[str, int] = {}
    for spec, run_dir in completed:
        state = _read_json(run_dir / "state.json")
        summary = _read_json(run_dir / "executor-summary.json")
        provenance = _read_json(run_dir / "provenance.json")
        processed = int(summary.get("processed", -1))
        inserted = int(summary.get("inserted", -1))
        if (
            state.get("status") != "SUCCEEDED"
            or processed < 1
            or inserted != processed
            or provenance.get("provenance_ok") is not True
            or any(
                _outcome(summary, key)
                for key in ("BROKEN", "TIMEOUT", "INFRA_FAIL", "CANCELLED")
            )
        ):
            raise RuntimeError(f"run did not validate cleanly: {run_dir}")
        total += processed
        outcomes = summary.get("outcomes", {})
        if isinstance(outcomes, dict):
            for key, value in outcomes.items():
                aggregate_outcomes[key] = aggregate_outcomes.get(key, 0) + int(value or 0)
        raw_candidates = provenance.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise RuntimeError(f"missing Analyzer candidates: {run_dir}")
        for raw in raw_candidates:
            if isinstance(raw, dict):
                candidate = dict(raw)
                candidate["suite_spec"] = spec
                candidates.append(candidate)
        runs[spec] = {
            "run_id": state.get("run_id"),
            "run_dir": str(run_dir),
            "processed": processed,
            "inserted": inserted,
            "outcomes": outcomes,
            "formal_front_count": len(raw_candidates),
            "provenance_ok": True,
        }
    front = _pareto(candidates)
    result = {
        "schema": "automation-scheme-studio.advanced-feedback-results/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "validated_processed": total,
        "outcomes": aggregate_outcomes,
        "goals": [{"key": key, "direction": direction} for key, direction in GOALS],
        "runs": runs,
        "global_front_count": len(front),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "common-results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "common-pareto.json").write_text(
        json.dumps(
            {
                "schema": "automation-scheme-studio.advanced-feedback-pareto/v1",
                "count": len(front),
                "candidates": front,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        "# Advanced feedback campaign results",
        "",
        "- Status: **COMPLETE**",
        f"- Validated candidates: **{total:,}**",
        f"- Exact global formal Pareto front: **{len(front):,}**",
        "",
        "| Scenario | Processed | PASS | Domain fail | Formal front |",
        "|---|---:|---:|---:|---:|",
    ]
    for spec, record in runs.items():
        outcomes = record["outcomes"]
        rows.append(
            f"| `{spec}` | {record['processed']:,} | "
            f"{int(outcomes.get('PASS', 0) or 0):,} | "
            f"{int(outcomes.get('DOMAIN_FAIL', 0) or 0):,} | "
            f"{record['formal_front_count']:,} |"
        )
    rows.extend(
        [
            "",
            "Candidate topology IDs, signatures, objective values, and source "
            "references are retained in `common-pareto.json`.",
            "",
        ]
    )
    (output_dir / "common-results.md").write_text(
        "\n".join(rows),
        encoding="utf-8",
    )
    print(f"\nStatus: COMPLETE")
    print(f"Validated: {total:,}; global Pareto front: {len(front):,}")
    print(f"Common report: {output_dir / 'common-results.md'}")
    print(f"Machine-readable: {output_dir / 'common-results.json'}")
    print(f"Full front: {output_dir / 'common-pareto.json'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "plan", "smoke", "run"))
    parser.add_argument("--spec", action="append", choices=SPECS)
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "campaign_results",
    )
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least one")
    if args.command == "list":
        print("\n".join(SPECS))
        return 0

    selected = tuple(args.spec or (
        SPECS if args.command == "plan"
        else SMOKE_SPECS if args.command == "smoke"
        else HEAVY_SPECS
    ))
    env = _environment(args.workers)
    if args.command in {"smoke", "run"}:
        missing = [
            key
            for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD")
            if not env.get(key)
        ]
        if missing:
            parser.error("set " + " and ".join(missing))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    completed: list[tuple[str, Path]] = []
    for spec_name in selected:
        spec = HERE / spec_name
        if args.command == "plan":
            plan_dir = Path("/tmp") / f"advanced-feedback-plan-{spec_name}-{stamp}"
            command = [
                sys.executable, str(BUNDLE), "plan", str(spec),
                "--out", str(plan_dir),
            ]
        else:
            run_id = f"automation-advanced-{spec_name}-{stamp}"
            run_dir = args.runs_root.resolve() / run_id
            command = [
                sys.executable,
                str(BUNDLE),
                str(spec),
                "--db", f"automation_advanced_{spec_name}",
                "--run-id", run_id,
                "--main-port", str(args.main_port),
                "--results-port", str(args.results_port),
                "--runs-root", str(args.runs_root.resolve()),
                "--candidate-sink", "sharded",
                "--py-executor", str(EXECUTOR),
                "--analyzer", ANALYZER,
                "--analysis-mode", "formal",
                "--execution-policy-profile", "trusted-local",
                "--candidate-origin", "reviewed-checked-in",
                "--acknowledge-trusted-local", "reviewed checked-in scenario fragments in this repository",
                "--unleash-initial-productivity-power",
            ]
            if spec_name in EXTREME_SPECS:
                command.extend(
                    [
                        "--allow-extreme",
                        "--override-budget",
                        "explicit advanced recursive control-topology search",
                    ]
                )
        print(f"\n==> {spec_name}", flush=True)
        result = subprocess.run(
            command,
            cwd=FRAMEWORK_ROOT,
            env=env,
            check=False,
        )
        if result.returncode:
            return result.returncode
        if args.command != "plan":
            completed.append((spec_name, run_dir))
    if completed:
        _aggregate(completed, args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
