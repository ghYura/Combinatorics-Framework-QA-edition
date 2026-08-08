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

"""Make a failure name its own cause.

`FW_VAR != 0` currently answers "did this candidate fail". It cannot answer the
question an operator actually has, because three different things wear that same
verdict:

* **capability** — the target cannot do the task at this size. Change model.
* **fragility** — it can, but this phrasing broke it. Fix the prompt.
* **instability** — it sometimes can. Add self-consistency or retries.

Published accuracy numbers mash all three together, which is why they transfer
so badly to production: a model that is 2% more accurate and far more fragile is
the worse deployment, and no single figure can say so.

A combinatorial grid can separate them, because the grid already contains the
controlled comparisons. Hold presentation and sweep size to see capability; hold
size and sweep presentation to see fragility; hold both and repeat to see
stability. Each is a marginal of the same tensor, so all three come from one run.

The second half of this module is about *interaction*. Failures that only appear
when two pressures meet are the ones sampling misses and the ones exhaustive
composition is for, so `interaction_map` reports them separately: a cell that
fails while both of its marginals pass is evidence no sampled suite can produce.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: A candidate is a pass when the engine returned verdict code 0.
PASS_CODE = 0


def flatten(record: Any) -> dict[str, Any]:
    """Merge a MetricRecord's dimensions and measurements into one mapping.

    Reporting works on flat rows because the results DB hands them back that
    way; accepting either shape keeps callers from having to care.
    """
    if isinstance(record, Mapping):
        if "dimensions" in record or "measurements" in record:
            merged = {**record.get("dimensions", {}), **record.get("measurements", {})}
            if "verdict_code" in record:
                merged["verdict_code"] = record["verdict_code"]
            return merged
        return dict(record)
    merged = {**dict(record.dimensions), **dict(record.measurements)}
    merged["verdict_code"] = record.verdict_code
    return merged


def _passed(row: Mapping[str, Any]) -> bool:
    if "verdict_code" in row:
        return int(row["verdict_code"]) == PASS_CODE
    return bool(int(row.get("correct", 0)))


def _rate(passed: int, total: int) -> float | None:
    return round(passed / total, 4) if total else None


# --- capability ----------------------------------------------------------
@dataclass(frozen=True)
class CapabilityProfile:
    by_complexity: dict[int, dict[str, Any]]
    ceiling: int | None
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "ceiling": self.ceiling,
            "by_complexity": {str(k): v for k, v in sorted(self.by_complexity.items())},
        }


def capability_profile(records: Iterable[Any], *, threshold: float = 0.95) -> CapabilityProfile:
    """Pass rate per task size, and the largest size still above *threshold*.

    The ceiling is deliberately the largest complexity that holds the threshold
    *with no smaller complexity failing it* — a lucky pass at size 8 after a
    failure at size 6 is not a capability ceiling, it is noise, and reporting it
    as a ceiling would overstate the target.
    """
    buckets: dict[int, list[bool]] = defaultdict(list)
    for record in records:
        row = flatten(record)
        if "complexity" not in row:
            continue
        buckets[int(row["complexity"])].append(_passed(row))

    by_complexity = {
        level: {
            "candidates": len(results),
            "passed": sum(results),
            "pass_rate": _rate(sum(results), len(results)),
        }
        for level, results in buckets.items()
    }
    ceiling: int | None = None
    for level in sorted(by_complexity):
        rate = by_complexity[level]["pass_rate"]
        if rate is not None and rate >= threshold:
            ceiling = level
        else:
            break
    return CapabilityProfile(by_complexity, ceiling, threshold)


# --- fragility -----------------------------------------------------------
def fragility_profile(
    records: Iterable[Any],
    *,
    task_key: str = "task_hash",
    presentation_keys: Sequence[str] = ("renderer_id",),
) -> dict[str, Any]:
    """Share of the *legal presentation space* that fails, per task.

    This is the number only an exhaustive design can report honestly, because
    the denominator is the whole space rather than whatever a sampler happened
    to draw. A target with a high pass rate and a high fragility coefficient is
    correct on average and unreliable in particular, which is the distinction
    that matters when someone has to ship it.
    """
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        row = flatten(record)
        task = str(row.get(task_key, "unknown"))
        bucket = buckets.setdefault(task, {"presentations": set(), "failed": set()})
        presentation = tuple(str(row.get(key, "")) for key in presentation_keys)
        bucket["presentations"].add(presentation)
        if not _passed(row):
            bucket["failed"].add(presentation)

    per_task = {}
    for task, bucket in sorted(buckets.items()):
        total = len(bucket["presentations"])
        failed = len(bucket["failed"])
        per_task[task] = {
            "presentation_space": total,
            "failing_presentations": failed,
            "fragility_coefficient": _rate(failed, total),
        }
    total_space = sum(v["presentation_space"] for v in per_task.values())
    total_failed = sum(v["failing_presentations"] for v in per_task.values())
    return {
        "tasks": per_task,
        "presentation_space": total_space,
        "failing_presentations": total_failed,
        "fragility_coefficient": _rate(total_failed, total_space),
    }


# --- stability -----------------------------------------------------------
def stability_profile(
    records: Iterable[Any],
    *,
    identity_keys: Sequence[str] = ("task_hash", "renderer_id", "adapter", "model"),
) -> dict[str, Any]:
    """Disagreement among repeats of an identical candidate.

    Identical inputs that produce different verdicts are the target's own
    non-determinism, not a property of the prompt. Groups of one are excluded:
    a single sample can never demonstrate stability, and counting it as stable
    would make a K=1 run look perfectly reliable.
    """
    buckets: dict[tuple[str, ...], list[bool]] = defaultdict(list)
    for record in records:
        row = flatten(record)
        buckets[tuple(str(row.get(k, "")) for k in identity_keys)].append(_passed(row))

    comparable = {k: v for k, v in buckets.items() if len(v) > 1}
    flaky = {k: v for k, v in comparable.items() if len(set(v)) > 1}
    return {
        "groups": len(buckets),
        "comparable_groups": len(comparable),
        "singleton_groups": len(buckets) - len(comparable),
        "flaky_groups": len(flaky),
        "instability_rate": _rate(len(flaky), len(comparable)),
    }


# --- interaction ---------------------------------------------------------
@dataclass(frozen=True)
class InteractionCell:
    factor_a: str
    factor_b: str
    failed: bool
    marginal_a_passed: bool
    marginal_b_passed: bool

    @property
    def interaction_only(self) -> bool:
        """Fails together, passes apart — invisible to any one-factor sweep."""
        return self.failed and self.marginal_a_passed and self.marginal_b_passed


def interaction_map(
    records: Iterable[Any],
    *,
    factor_a: str,
    factor_b: str,
    baseline_a: str,
    baseline_b: str,
) -> dict[str, Any]:
    """Cross two factors and separate interaction-only failures.

    A cell's *marginals* are that factor's level paired with the other factor's
    baseline — i.e. the result a one-factor-at-a-time suite would have seen. A
    failure whose marginals both pass cannot be attributed to either factor, and
    could not have been found without composing them.

    The reported `interaction_only` count is the concrete argument for
    combinatorial coverage over sampling: it is exactly the set of defects that
    require the cross product to exist.
    """
    outcomes: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for record in records:
        row = flatten(record)
        if factor_a not in row or factor_b not in row:
            continue
        outcomes[(str(row[factor_a]), str(row[factor_b]))].append(_passed(row))

    def cell_failed(a: str, b: str) -> bool | None:
        results = outcomes.get((a, b))
        if not results:
            return None
        return not all(results)          # any failure in the cell fails the cell

    cells: list[InteractionCell] = []
    for (a, b) in sorted(outcomes):
        failed = cell_failed(a, b)
        marginal_a = cell_failed(a, baseline_b)
        marginal_b = cell_failed(baseline_a, b)
        if failed is None or marginal_a is None or marginal_b is None:
            continue                     # incomplete grid: no honest verdict
        cells.append(InteractionCell(a, b, failed, not marginal_a, not marginal_b))

    interaction_only = [c for c in cells if c.interaction_only]
    failing = [c for c in cells if c.failed]
    return {
        "factor_a": factor_a,
        "factor_b": factor_b,
        "cells": len(cells),
        "failing_cells": len(failing),
        "interaction_only_failures": len(interaction_only),
        "interaction_only_share": _rate(len(interaction_only), len(failing)),
        "interaction_only_cells": [
            {factor_a: c.factor_a, factor_b: c.factor_b} for c in interaction_only
        ],
    }


def decompose(records: Iterable[Any], **kwargs: Any) -> dict[str, Any]:
    """All three marginals from one pass over the same rows."""
    rows = [flatten(record) for record in records]
    return {
        "capability": capability_profile(rows).as_dict(),
        "fragility": fragility_profile(rows),
        "stability": stability_profile(rows),
    }
