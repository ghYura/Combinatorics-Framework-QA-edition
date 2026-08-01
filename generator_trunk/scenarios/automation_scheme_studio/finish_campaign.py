#!/usr/bin/env python3
"""Resume the Automation Scheme Studio campaign and emit common results.

The script reuses only runs whose Bundle state, Executor reconciliation, and
formal Analyzer provenance are all complete. Missing or interrupted scenarios
are rerun from the beginning; candidate-level resume is intentionally avoided
because it would weaken the run's count/provenance guarantees.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
FRAMEWORK_ROOT = HERE.parents[2]
RUNNER = HERE / "run_campaign.py"

SPECS = (
    "00_smoke",
    "01_ordered_serial",
    "02_deep_nested",
    "03_redundant_multiset",
    "04_brace_join",
    "05_cartesian_refinement",
)
EXPECTED_COUNTS = {
    "00_smoke": 48,
    "01_ordered_serial": 49_152,
    "02_deep_nested": 90_000,
    # Core's authoritative FW_CombiR runtime count is twice the static estimate.
    "03_redundant_multiset": 7_680,
    "04_brace_join": 1_152,
    "05_cartesian_refinement": 7_680,
}
GOALS = (
    ("control_score", "max"),
    ("robustness_score", "max"),
    ("stability_score", "max"),
    ("settling_time_s", "min"),
    ("worst_error", "min"),
    ("overshoot_pct", "min"),
    ("control_effort", "min"),
)
DIMENSION_KEYS = (
    "architecture",
    "controller",
    "inner_controller",
    "plant",
    "profile",
    "battery",
    "chain",
    "branches",
    "inner_loops",
    "options",
)
OUTCOMES = (
    "PASS",
    "DOMAIN_FAIL",
    "BROKEN",
    "TIMEOUT",
    "INFRA_FAIL",
    "CANCELLED",
    "SKIPPED",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _outcome_count(summary: dict[str, Any], key: str) -> int:
    outcomes = summary.get("outcomes")
    if isinstance(outcomes, dict):
        return int(outcomes.get(key, 0) or 0)
    legacy = {
        "PASS": "pass",
        "DOMAIN_FAIL": "fail",
        "BROKEN": "broken",
        "TIMEOUT": "timeout",
        "INFRA_FAIL": "infra_fail",
    }
    return int(summary.get(legacy.get(key, ""), 0) or 0)


def _validated_run(run_dir: Path, spec: str) -> dict[str, Any] | None:
    expected = EXPECTED_COUNTS[spec]
    state = _read_json(run_dir / "state.json")
    summary = _read_json(run_dir / "executor-summary.json")
    provenance = _read_json(run_dir / "provenance.json")
    if not state or not summary or not provenance:
        return None
    stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    if (
        state.get("status") != "SUCCEEDED"
        or stages.get("executor", {}).get("status") != "SUCCEEDED"
        or stages.get("analyzer", {}).get("status") != "SUCCEEDED"
        or int(summary.get("processed", -1)) != expected
        or int(summary.get("inserted", -1)) != expected
        # Formal Analyzer intentionally excludes Oracle failures. Its seen count
        # must therefore reconcile to Executor PASS, not to all processed rows.
        or int(provenance.get("candidates_seen", -1)) != _outcome_count(summary, "PASS")
        or provenance.get("provenance_ok") is not True
        or not (run_dir / "metrics.kv").is_file()
    ):
        return None
    if any(_outcome_count(summary, key) for key in ("BROKEN", "TIMEOUT", "INFRA_FAIL", "CANCELLED")):
        return None
    candidates = provenance.get("candidates")
    if not isinstance(candidates, list):
        return None
    return {
        "path": run_dir,
        "state": state,
        "summary": summary,
        "provenance": provenance,
    }


def _latest_validated_run(runs_root: Path, spec: str) -> dict[str, Any] | None:
    matches = sorted(
        runs_root.glob(f"automation-{spec}-*"),
        key=lambda path: path.name,
        reverse=True,
    )
    for run_dir in matches:
        result = _validated_run(run_dir, spec)
        if result:
            return result
    return None


def _candidate(raw: dict[str, Any], spec: str) -> dict[str, Any]:
    dimensions = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else {}
    objectives = raw.get("objectives") if isinstance(raw.get("objectives"), dict) else {}
    return {
        "spec": spec,
        "run_id": str(raw.get("run_id", "")),
        "candidate_id": str(raw.get("candidate_id", "")),
        "source_ref": str(raw.get("source_ref", "")),
        "dimensions": {
            key: dimensions[key]
            for key in DIMENSION_KEYS
            if key in dimensions
        },
        "objectives": {
            key: float(objectives[key])
            for key, _direction in GOALS
            if key in objectives
        },
    }


def _identity(candidate: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(candidate.get("spec", "")),
        str(candidate.get("run_id", "")),
        str(candidate.get("candidate_id", "")),
    )


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_values = left["objectives"]
    right_values = right["objectives"]
    weakly_better = True
    strictly_better = False
    for key, direction in GOALS:
        lv = float(left_values[key])
        rv = float(right_values[key])
        if direction == "max":
            weakly_better &= lv >= rv
            strictly_better |= lv > rv
        else:
            weakly_better &= lv <= rv
            strictly_better |= lv < rv
        if not weakly_better:
            return False
    return strictly_better


def _global_front(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    front: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=_identity):
        if any(_dominates(existing, candidate) for existing in front):
            continue
        front = [
            existing
            for existing in front
            if not _dominates(candidate, existing)
        ]
        front.append(candidate)
    return sorted(front, key=_identity)


def _champions(front: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    winners: dict[str, dict[str, Any]] = {}
    for key, direction in GOALS:
        ordered = sorted(front, key=_identity)
        pick = (max if direction == "max" else min)(
            ordered, key=lambda candidate: candidate["objectives"][key]
        )
        winners[key] = {
            "direction": direction,
            "value": pick["objectives"][key],
            "candidate": pick,
        }
    return winners


def _balanced(front: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not front:
        return None
    bounds: dict[str, tuple[float, float]] = {}
    for key, _direction in GOALS:
        values = [candidate["objectives"][key] for candidate in front]
        bounds[key] = (min(values), max(values))

    def utility(candidate: dict[str, Any]) -> float:
        terms: list[float] = []
        for key, direction in GOALS:
            low, high = bounds[key]
            if math.isclose(low, high):
                terms.append(1.0)
                continue
            value = candidate["objectives"][key]
            normalized = (value - low) / (high - low)
            terms.append(normalized if direction == "max" else 1.0 - normalized)
        return sum(terms) / len(terms)

    ordered = sorted(front, key=_identity)
    best = max(ordered, key=utility)
    return {
        "method": "equal-weight min-max utility over the exact global formal front",
        "utility": round(utility(best), 9),
        "candidate": best,
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _common_results(
    validated: dict[str, dict[str, Any]],
    *,
    reused: list[str],
    executed: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    missing = [spec for spec in SPECS if spec not in validated]
    aggregate_outcomes = {key: 0 for key in OUTCOMES}
    runs: dict[str, Any] = {}
    local_fronts: list[dict[str, Any]] = []

    for spec in SPECS:
        record = validated.get(spec)
        if not record:
            continue
        summary = record["summary"]
        provenance = record["provenance"]
        outcomes = {key: _outcome_count(summary, key) for key in OUTCOMES}
        for key, value in outcomes.items():
            aggregate_outcomes[key] += value
        candidates = [
            _candidate(raw, spec)
            for raw in provenance["candidates"]
            if isinstance(raw, dict)
        ]
        local_fronts.extend(candidates)
        provenance_issues = provenance.get("provenance_issues", [])
        issue_count = (
            len(provenance_issues)
            if isinstance(provenance_issues, list)
            else int(provenance_issues or 0)
        )
        runs[spec] = {
            "run_id": record["state"].get("run_id"),
            "run_dir": str(record["path"]),
            "expected": EXPECTED_COUNTS[spec],
            "processed": int(summary["processed"]),
            "inserted": int(summary["inserted"]),
            "outcomes": outcomes,
            "executor_duration_seconds": float(summary.get("duration_seconds", 0.0) or 0.0),
            "analyzer_front_count": len(candidates),
            "provenance_ok": True,
            "provenance_issues": issue_count,
        }

    front = _global_front(local_fronts)
    processed = sum(run["processed"] for run in runs.values())
    expected_total = sum(EXPECTED_COUNTS.values())
    result = {
        "schema": "automation-scheme-studio.common-results/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "expected_total": expected_total,
        "validated_processed": processed,
        "coverage_pct": round(100.0 * processed / expected_total, 6),
        "missing_specs": missing,
        "reused_specs": reused,
        "executed_specs": executed,
        "goals": [{"key": key, "direction": direction} for key, direction in GOALS],
        "outcomes": aggregate_outcomes,
        "runs": runs,
        "global_analysis": {
            "method": (
                "exact Pareto re-filter of each formal Analyzer front; a point "
                "dominated inside one scenario cannot enter the global front"
            ),
            "source_front_candidates": len(local_fronts),
            "global_front_count": len(front),
            "champions": _champions(front) if front else {},
            "balanced_candidate": _balanced(front),
            "timing_note": (
                "evaluation_ms is recorded in raw metrics but is not ranked; "
                "single-host execution time is not a controlled benchmark"
            ),
        },
    }
    return result, front


def _candidate_label(candidate: dict[str, Any]) -> str:
    dimensions = candidate["dimensions"]
    values = [
        dimensions.get("architecture"),
        dimensions.get("controller"),
        dimensions.get("plant"),
        dimensions.get("profile"),
        dimensions.get("chain"),
        dimensions.get("branches"),
        dimensions.get("inner_loops"),
        dimensions.get("options"),
    ]
    return " / ".join(str(value) for value in values if value and value != "none")


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Automation Scheme Studio — common campaign results",
        "",
        f"- Status: **{result['status']}**",
        f"- Validated candidates: **{result['validated_processed']:,} / {result['expected_total']:,}** "
        f"({result['coverage_pct']:.2f}%)",
        f"- Outcomes: **{result['outcomes']['PASS']:,} PASS**, "
        f"**{result['outcomes']['DOMAIN_FAIL']:,} DOMAIN_FAIL**, "
        f"**{result['outcomes']['BROKEN']:,} BROKEN**, "
        f"**{result['outcomes']['INFRA_FAIL']:,} INFRA_FAIL**, "
        f"**{result['outcomes']['TIMEOUT']:,} TIMEOUT**",
        "",
        "## Runs",
        "",
        "| Scenario | Processed | PASS | Domain fail | Analyzer front | Seconds |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for spec in SPECS:
        run = result["runs"].get(spec)
        if not run:
            lines.append(f"| `{spec}` | missing | — | — | — | — |")
            continue
        lines.append(
            f"| `{spec}` | {run['processed']:,} | {run['outcomes']['PASS']:,} | "
            f"{run['outcomes']['DOMAIN_FAIL']:,} | {run['analyzer_front_count']:,} | "
            f"{run['executor_duration_seconds']:.3f} |"
        )

    analysis = result["global_analysis"]
    lines.extend(
        [
            "",
            "## Common formal result",
            "",
            f"Exact global Pareto front: **{analysis['global_front_count']:,}** candidates "
            f"from {analysis['source_front_candidates']:,} per-scenario front candidates.",
            "",
        ]
    )
    balanced = analysis.get("balanced_candidate")
    if balanced:
        candidate = balanced["candidate"]
        lines.extend(
            [
                "Balanced recommendation:",
                "",
                f"- `{candidate['spec']} / {candidate['candidate_id']}` — "
                f"{_candidate_label(candidate)}",
                f"- Equal-weight normalized utility: `{balanced['utility']}`",
                "- Objectives: "
                + ", ".join(
                    f"`{key}={candidate['objectives'][key]:.9g}`"
                    for key, _direction in GOALS
                ),
                "",
            ]
        )

    lines.extend(
        [
            "### Champion by objective",
            "",
            "| Objective | Direction | Value | Candidate | Design |",
            "|---|:---:|---:|---|---|",
        ]
    )
    for key, _direction in GOALS:
        champion = analysis.get("champions", {}).get(key)
        if not champion:
            continue
        candidate = champion["candidate"]
        lines.append(
            f"| `{key}` | {champion['direction']} | {champion['value']:.9g} | "
            f"`{candidate['spec']} / {candidate['candidate_id']}` | "
            f"{_candidate_label(candidate)} |"
        )
    if result["missing_specs"]:
        lines.extend(
            [
                "",
                "## Missing",
                "",
                ", ".join(f"`{spec}`" for spec in result["missing_specs"]),
            ]
        )
    lines.extend(
        [
            "",
            "Raw run directories and exact candidate identities are recorded in "
            "`common-results.json`; the full common front is in `common-pareto.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_outputs(
    output_dir: Path,
    result: dict[str, Any],
    front: list[dict[str, Any]],
) -> None:
    _atomic_write(
        output_dir / "common-results.json",
        json.dumps(result, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(
        output_dir / "common-pareto.json",
        json.dumps(
            {
                "schema": "automation-scheme-studio.common-pareto/v1",
                "status": result["status"],
                "goals": result["goals"],
                "count": len(front),
                "candidates": front,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _atomic_write(output_dir / "common-results.md", _markdown(result))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reuse green scenario runs, execute only missing/incomplete runs, "
            "and produce one common formal result."
        )
    )
    parser.add_argument("--runs-root", type=Path, default=Path("/tmp/fw_work"))
    parser.add_argument("--output-dir", type=Path, default=HERE / "campaign_results")
    parser.add_argument("--main-port", type=int, default=5433)
    parser.add_argument("--results-port", type=int, default=5432)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--rerun", action="append", choices=SPECS, default=[])
    parser.add_argument("--all", action="store_true", help="rerun all six scenarios")
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="do not execute; fail if a validated scenario is missing",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="with --aggregate-only, write a clearly marked partial report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show which runs would be reused/executed and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    args.runs_root = args.runs_root.resolve()
    args.output_dir = args.output_dir.resolve()

    validated = {
        spec: record
        for spec in SPECS
        if (record := _latest_validated_run(args.runs_root, spec))
    }
    forced = set(SPECS if args.all else args.rerun)
    remaining = [spec for spec in SPECS if spec not in validated or spec in forced]
    reused = [spec for spec in SPECS if spec in validated and spec not in forced]

    print("Reusable:", ", ".join(reused) or "none")
    print("To execute:", ", ".join(remaining) or "none")
    if args.dry_run:
        return 0

    if args.aggregate_only:
        if remaining and not args.allow_incomplete:
            print(
                "Incomplete: " + ", ".join(remaining)
                + ". Run without --aggregate-only to finish them.",
                file=sys.stderr,
            )
            return 2
    elif remaining:
        missing_environment = [
            key
            for key in ("BUNDLE_MAIN_DB_PASSWORD", "BUNDLE_RESULTS_DB_PASSWORD")
            if not os.environ.get(key)
        ]
        if missing_environment:
            print(
                "Set the required environment variables: "
                + ", ".join(missing_environment),
                file=sys.stderr,
            )
            return 2

    executed: list[str] = []
    if not args.aggregate_only:
        for spec in remaining:
            print(f"\n=== EXECUTING {spec} ===", flush=True)
            command = [
                sys.executable,
                str(RUNNER),
                "run",
                "--spec",
                spec,
                "--runs-root",
                str(args.runs_root),
                "--main-port",
                str(args.main_port),
                "--results-port",
                str(args.results_port),
                "--executor-workers",
                str(args.workers),
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=FRAMEWORK_ROOT,
                    env=os.environ.copy(),
                    check=False,
                )
            except KeyboardInterrupt:
                print("\nInterrupted; completed run evidence remains reusable.", file=sys.stderr)
                return 130
            if completed.returncode:
                print(f"{spec} failed with exit code {completed.returncode}", file=sys.stderr)
                return completed.returncode
            record = _latest_validated_run(args.runs_root, spec)
            if not record:
                print(f"{spec} exited but did not produce validated evidence", file=sys.stderr)
                return 3
            validated[spec] = record
            executed.append(spec)

    result, front = _common_results(validated, reused=reused, executed=executed)
    _write_outputs(args.output_dir, result, front)
    print(f"\nStatus: {result['status']}")
    print(
        f"Validated: {result['validated_processed']:,}/{result['expected_total']:,}; "
        f"global Pareto front: {len(front):,}"
    )
    print(f"Common report: {args.output_dir / 'common-results.md'}")
    print(f"Machine-readable: {args.output_dir / 'common-results.json'}")
    print(f"Full front: {args.output_dir / 'common-pareto.json'}")
    return 0 if result["status"] == "COMPLETE" or args.allow_incomplete else 2


if __name__ == "__main__":
    raise SystemExit(main())
