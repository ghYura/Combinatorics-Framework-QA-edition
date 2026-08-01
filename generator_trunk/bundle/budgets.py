from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from .resources import CardinalityMode, ResourcePlan
from .stages import fg

CardinalityEstimate = fg.CardinalityEstimate


class BudgetSeverity(str, Enum):
    """How urgently a dimension's projected size needs operator attention
    (STEP 12 action 2: "Поддержать: warning threshold; hard threshold")."""
    OK = "OK"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


@dataclass(frozen=True)
class BudgetLimits:
    """Hard ceilings (and, via `warn_fraction`, derived warning thresholds)
    for the seven STEP-12 budget dimensions (action 1). `None` means "no limit
    configured for this dimension" — evaluated as OK, never as an implicit
    zero ceiling. Defaults are conservative placeholders an operator overrides
    per-spec/per-environment (CLI flags in `bundle.cli`); they exist so a
    plain small run passes untouched while a synthetic explosion is stopped
    before it reaches Core/DB.
    """
    mandatory_rows: "Optional[int]" = 2_000_000
    final_candidates: "Optional[int]" = 2_000_000
    disk_bytes: "Optional[int]" = 20 * 1024 ** 3
    inodes: "Optional[int]" = 2_000_000
    wall_time_seconds: "Optional[float]" = 24 * 3600
    external_requests: "Optional[int]" = 2_000_000
    monetary_cost: "Optional[float]" = None
    warn_fraction: float = 0.5

    def warning_for(self, hard: "Optional[float]") -> "Optional[float]":
        return hard * self.warn_fraction if hard is not None else None


@dataclass(frozen=True)
class BudgetCheck:
    """One dimension's projected value against its configured ceilings — the
    machine-readable unit `bundle.cli`'s gate (and the run manifest) reasons
    over (STEP 12 action 4: "reason записывается")."""
    dimension: str
    label: str
    value: "int | float | None"
    unsizable: bool
    warning: "int | float | None"
    hard: "int | float | None"
    severity: BudgetSeverity
    message: str


def _dimension_value(est: "Optional[CardinalityEstimate]"):
    """`(value, unsizable)`. `value` is the conservative (upper-bound) point
    the gate compares against ceilings; `unsizable=True` marks a dimension
    whose true size is statically UNKNOWN (e.g. an unresolved brace join) —
    distinct from "not applicable" (`est is None`, e.g. monetary cost when no
    price is configured)."""
    if est is None:
        return None, False
    if est.mode == CardinalityMode.UNKNOWN or est.value is None:
        return None, True
    return (est.upper if est.upper is not None else est.value), False


def _classify(dimension: str, label: str, value, unsizable: bool,
              warning, hard) -> BudgetCheck:
    if hard is None:
        if unsizable:
            return BudgetCheck(dimension, label, value, unsizable, warning, hard, BudgetSeverity.OK,
                               f"{label} is statically UNKNOWN and no hard limit is configured — "
                               f"not gated, but its true size will only be known once Core runs")
        return BudgetCheck(dimension, label, value, unsizable, warning, hard, BudgetSeverity.OK,
                           f"{label}: no limit configured")
    if unsizable:
        return BudgetCheck(
            dimension, label, value, unsizable, warning, hard, BudgetSeverity.BLOCKING,
            f"{label} is statically UNKNOWN but a hard limit ({hard:g}) is configured — "
            f"cannot prove the run stays within budget without running it; blocked until "
            f"overridden")
    if value is None:
        return BudgetCheck(dimension, label, value, unsizable, warning, hard, BudgetSeverity.OK,
                           f"{label}: not estimated (no projection available)")
    if value > hard:
        return BudgetCheck(dimension, label, value, unsizable, warning, hard, BudgetSeverity.BLOCKING,
                           f"{label} ~{value:g} exceeds hard limit {hard:g}")
    if warning is not None and value > warning:
        return BudgetCheck(dimension, label, value, unsizable, warning, hard, BudgetSeverity.WARNING,
                           f"{label} ~{value:g} exceeds warning threshold {warning:g} (hard limit {hard:g})")
    return BudgetCheck(dimension, label, value, unsizable, warning, hard, BudgetSeverity.OK,
                       f"{label} ~{value:g} within budget (limit {hard:g})")


def evaluate_budgets(cardinality_plan: "fg.SpecCardinalityPlan", resource_plan: ResourcePlan,
                      limits: "Optional[BudgetLimits]" = None) -> "list[BudgetCheck]":
    """Evaluate every STEP-12 budget dimension against `limits` (defaults if
    omitted), using each dimension's conservative upper bound — never its
    optimistic point value — so a BOUNDED/ESTIMATED projection can't slip
    under a ceiling it might actually exceed (STEP 12 action 1+3)."""
    limits = limits or BudgetLimits()

    disk_parts = [resource_plan.core_db_bytes, resource_plan.results_db_bytes,
                  resource_plan.candidate_source_bytes]
    # Plan-1 §3.3: the repeat-aware metrics corpus is a real on-disk artifact (metrics.kv,
    # NOT Results-DB rows) — fold it into the disk ceiling so a hard limit blocks on
    # metric-artifact growth. Present only when a repeat count plan is active (K>1); absent
    # ⇒ the disk sum is the legacy Core+Results+sources, unchanged.
    _has_metric_artifact = getattr(resource_plan, "metric_artifact_bytes", None) is not None
    if _has_metric_artifact:
        disk_parts.append(resource_plan.metric_artifact_bytes)
    disk_label = ("estimated disk bytes (Core+Results+sources"
                  + ("+metric-artifact)" if _has_metric_artifact else ")"))
    if any(p.mode == CardinalityMode.UNKNOWN or p.value is None for p in disk_parts):
        disk_value, disk_unsizable = None, True
    else:
        disk_value, disk_unsizable = sum(p.upper if p.upper is not None else p.value for p in disk_parts), False

    rows = (
        ("mandatory_rows", "mandatory Core rows",
         *_dimension_value(cardinality_plan.mandatory), limits.mandatory_rows),
        ("final_candidates", "final candidates",
         *_dimension_value(cardinality_plan.final), limits.final_candidates),
        ("disk_bytes", disk_label,
         disk_value, disk_unsizable, limits.disk_bytes),
        ("inodes", "estimated loose-file inodes",
         *_dimension_value(resource_plan.inode_count), limits.inodes),
        ("wall_time_seconds", "estimated wall time (s)",
         *_dimension_value(resource_plan.duration_seconds), limits.wall_time_seconds),
        ("external_requests", "estimated external requests",
         *_dimension_value(resource_plan.request_count), limits.external_requests),
        ("monetary_cost", "estimated monetary cost",
         *_dimension_value(resource_plan.monetary_cost), limits.monetary_cost),
    )
    checks = []
    for dim, label, value, unsizable, hard in rows:
        checks.append(_classify(dim, label, value, unsizable, limits.warning_for(hard), hard))
    return checks


def budget_check_to_dict(c: BudgetCheck) -> dict:
    return {"dimension": c.dimension, "label": c.label, "value": c.value, "unsizable": c.unsizable,
            "warning": c.warning, "hard": c.hard, "severity": c.severity.value, "message": c.message}


def blocking_checks(checks: "Sequence[BudgetCheck]") -> "list[BudgetCheck]":
    return [c for c in checks if c.severity == BudgetSeverity.BLOCKING]


def warning_checks(checks: "Sequence[BudgetCheck]") -> "list[BudgetCheck]":
    return [c for c in checks if c.severity == BudgetSeverity.WARNING]
