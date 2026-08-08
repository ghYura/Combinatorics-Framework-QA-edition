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

"""Evidence reconciliation and cross-product reporting for all three modes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a JSON object")
    return value


def _count(stage: dict[str, Any], name: str) -> int:
    for item in stage.get("counts", []):
        if isinstance(item, dict) and item.get("name") == name:
            return int(item.get("actual"))
    raise RuntimeError(f"stage {stage.get('stage')!r} lacks count {name!r}")


def _expected_count(stage: dict[str, Any], name: str) -> int:
    """Return the stage-declared count that its own invariant enforced."""
    for item in stage.get("counts", []):
        if isinstance(item, dict) and item.get("name") == name:
            if item.get("expected") is None:
                raise RuntimeError(
                    f"stage {stage.get('stage')!r} count {name!r} lacks expected"
                )
            return int(item["expected"])
    raise RuntimeError(f"stage {stage.get('stage')!r} lacks count {name!r}")


def parse_metrics_line(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in line.strip().split():
        key, separator, value = token.partition("=")
        if separator and key:
            fields[key] = value
    if fields.get("app") not in {
        "ai_combi_testing",
        "ai_combi_robustness",
        "ai_combi_release_gate",
    } or "FW_VAR" not in fields:
        raise ValueError("not an AI combinatorial platform metrics line")
    return fields


def load_metrics(path: Path) -> list[dict[str, str]]:
    return [
        parse_metrics_line(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def reconcile_run(run_dir: Path) -> dict[str, Any]:
    """Fail closed unless generation, execution, persistence and analysis agree."""
    state = _read_json(run_dir / "state.json")
    if state.get("status") != "SUCCEEDED":
        raise RuntimeError(f"run is not SUCCEEDED: {run_dir}")
    stages = {
        name: _read_json(run_dir / "stages" / f"{name}.json")
        for name in ("core", "reader", "executor", "analyzer")
    }
    if any(stage.get("status") != "SUCCEEDED" for stage in stages.values()):
        raise RuntimeError(f"one or more stages did not succeed: {run_dir}")
    summary = _read_json(run_dir / "executor-summary.json")
    provenance = _read_json(run_dir / "provenance.json")
    metrics = load_metrics(run_dir / "metrics.kv")

    core = _count(stages["core"], "fw_final")
    reader = _count(stages["reader"], "candidates")
    reader_expected = _expected_count(stages["reader"], "candidates")
    processed = int(summary.get("processed", -1))
    passed = int(summary.get("pass", -1))
    failed = int(summary.get("fail", -1))
    inserted = int(summary.get("inserted", -1))
    outcomes = summary.get("outcomes")
    if not isinstance(outcomes, dict):
        raise RuntimeError("executor summary has no outcomes map")
    unexpected = {
        name: int(outcomes.get(name, 0) or 0)
        for name in ("BROKEN", "TIMEOUT", "INFRA_FAIL", "CANCELLED", "SKIPPED")
    }
    terminal = sum(int(value or 0) for value in outcomes.values())
    repeat_measurements = summary.get("repeat_measurements")
    repeat_measurements = (
        repeat_measurements if isinstance(repeat_measurements, dict) else {}
    )
    expected_metric_rows = int(
        repeat_measurements.get("metric_rows") or processed
    )
    eligible_metric_rows = sum(
        int(_as_int(row, "FW_VAR") == 0) for row in metrics
    )
    eligible_candidate_keys = {
        (row.get("run_id", ""), row.get("candidate_id", ""))
        for row in metrics
        if _as_int(row, "FW_VAR") == 0 and row.get("candidate_id")
    }
    eligible_candidates = (
        len(eligible_candidate_keys) if eligible_candidate_keys else passed
    )
    checks = {
        # Core records mandatory fw_final rows. Reader expands each through the
        # selected fw_optK tables, so direct equality is invalid with FW_Optional.
        "reader_equals_declared_runtime_expansion": reader == reader_expected,
        "reader_equals_processed": reader == processed,
        "terminal_equals_processed": terminal == processed,
        "inserted_equals_verdicts": inserted == passed + failed,
        "metrics_equals_expected_samples": len(metrics) == expected_metric_rows,
        "formal_seen_equals_eligible_candidates": int(
            provenance.get("candidates_seen", -1)
        ) == eligible_candidates,
        "provenance_ok": provenance.get("provenance_ok") is True,
        "no_unexpected_outcomes": not any(unexpected.values()),
        "run_ids_match": all(
            not item.get("run_id") or item.get("run_id") == state.get("run_id")
            for item in provenance.get("candidates", [])
            if isinstance(item, dict)
        ),
    }
    failed_checks = [name for name, passed_check in checks.items() if not passed_check]
    if failed_checks:
        raise RuntimeError(
            f"evidence reconciliation failed for {run_dir}: {', '.join(failed_checks)}"
        )
    return {
        "run_id": state.get("run_id"),
        "run_dir": str(run_dir),
        "core": core,
        "reader": reader,
        "reader_expected": reader_expected,
        "processed": processed,
        "pass": passed,
        "domain_fail": failed,
        "inserted": inserted,
        "metrics_lines": len(metrics),
        "expected_metric_rows": expected_metric_rows,
        "eligible_metric_rows": eligible_metric_rows,
        "eligible_candidates": eligible_candidates,
        "formal_candidates_seen": int(provenance["candidates_seen"]),
        "outcomes": outcomes,
        "checks": checks,
        "metrics": metrics,
        "front": provenance.get("candidates", []),
    }


def _as_int(row: dict[str, str], key: str) -> int:
    return int(float(row.get(key, "0")))


def _derived_metrics(rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    materialized = list(rows)
    by_adapter: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_equivalence: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(
        list
    )
    by_repeat: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in materialized:
        by_adapter[row.get("adapter", "unknown")].append(row)
        if row.get("candidate_id"):
            by_repeat[(row.get("run_id", ""), row["candidate_id"])].append(row)
        by_equivalence[
            (
                row.get("task_hash", ""),
                row.get("adapter", ""),
                row.get("prompt_version", ""),
            )
        ].append(row)

    adapters: dict[str, Any] = {}
    for adapter, values in sorted(by_adapter.items()):
        passes = sum(_as_int(value, "correct") for value in values)
        failures = sorted(
            {
                _as_int(value, "complexity")
                for value in values
                if not _as_int(value, "correct")
            }
        )
        adapters[adapter] = {
            "samples": len(values),
            "pass_rate": passes / len(values) if values else 0.0,
            "first_failure_complexity": failures[0] if failures else None,
            "mean_cost_microusd": (
                sum(_as_int(value, "cost_microusd") for value in values)
                / len(values)
                if values
                else 0.0
            ),
            "mean_latency_us": (
                sum(_as_int(value, "latency_us") for value in values) / len(values)
                if values
                else 0.0
            ),
            "is_control": all(_as_int(value, "is_control") for value in values),
        }

    equivalent_groups = [
        values for values in by_equivalence.values() if len(values) > 1
    ]
    invariant_groups = sum(
        int(all(_as_int(value, "correct") for value in values))
        for values in equivalent_groups
    )
    repeat_groups = [values for values in by_repeat.values() if len(values) > 1]
    consistent_repeat_groups = sum(
        int(len({_as_int(value, "correct") for value in values}) == 1)
        for values in repeat_groups
    )
    prompt_versions: dict[str, dict[str, int]] = defaultdict(
        lambda: {"samples": 0, "pass": 0}
    )
    for row in materialized:
        version = row.get("prompt_version", "unknown")
        prompt_versions[version]["samples"] += 1
        prompt_versions[version]["pass"] += _as_int(row, "correct")
    return {
        "adapters": adapters,
        "semantic_invariance": {
            "equivalent_groups": len(equivalent_groups),
            "all_renderings_pass_groups": invariant_groups,
            "rate": (
                invariant_groups / len(equivalent_groups)
                if equivalent_groups
                else None
            ),
        },
        "repeat_consistency": {
            "groups": len(repeat_groups),
            "consistent_verdict_groups": consistent_repeat_groups,
            "rate": (
                consistent_repeat_groups / len(repeat_groups)
                if repeat_groups
                else None
            ),
        },
        "prompt_ci": dict(sorted(prompt_versions.items())),
        "router_policy": {
            "status": "WITHHELD"
            if not any(not value["is_control"] for value in adapters.values())
            else "EVIDENCE_AVAILABLE",
            "reason": (
                "controls are pipeline checks, not measured AI models"
                if not any(not value["is_control"] for value in adapters.values())
                else "apply a documented quality floor before cost/latency tie-breaks"
            ),
        },
    }


def write_common_report(
    completed: Iterable[tuple[str, Path]],
    output_dir: Path,
) -> dict[str, Any]:
    records: dict[str, Any] = {}
    rows: list[dict[str, str]] = []
    front: list[dict[str, Any]] = []
    for scenario, run_dir in completed:
        record = reconcile_run(run_dir)
        rows.extend(record.pop("metrics"))
        front.extend(record.pop("front"))
        records[scenario] = record
    derived = _derived_metrics(rows)
    result = {
        "schema": "ai-combi.campaign-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "runs": records,
        "validated_candidates": sum(
            int(record["processed"]) for record in records.values()
        ),
        "formal_eligible_candidates": sum(
            int(record["formal_candidates_seen"]) for record in records.values()
        ),
        "derived": derived,
        "formal_front": front,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "common-results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# AI combinatorial campaign results",
        "",
        "- Status: **COMPLETE**",
        f"- Reconciled candidates: **{result['validated_candidates']:,}**",
        (
            "- Formal eligible candidates: "
            f"**{result['formal_eligible_candidates']:,}**"
        ),
        (
            "- Router claim: **"
            f"{derived['router_policy']['status']}** — "
            f"{derived['router_policy']['reason']}."
        ),
        "",
        "| Scenario | Core | Reader | Processed | PASS | Domain fail |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario, record in records.items():
        lines.append(
            f"| `{scenario}` | {record['core']:,} | {record['reader']:,} | "
            f"{record['processed']:,} | {record['pass']:,} | "
            f"{record['domain_fail']:,} |"
        )
    lines.extend(
        [
            "",
            "Controls validate assembly and oracle plumbing; they are not AI rankings.",
            "Machine-readable evidence is in `common-results.json`.",
            "",
        ]
    )
    (output_dir / "common-results.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return result
