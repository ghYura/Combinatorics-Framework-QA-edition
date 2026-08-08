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

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Sequence

from .stages import fg

CardinalityEstimate = fg.CardinalityEstimate
CardinalityMode = fg.CardinalityMode

# Conservative placeholder per-unit ranges (STEP 11 action 5: "Не обещать
# точность без samples"). These are NOT measurements — they exist so a plan
# can give an operator a ballpark *with explicit assumptions attached*, and
# get replaced/calibrated once `bundle doctor`/the benchmark harness (STEP 15/
# 40) produce real samples. Every estimate built from them says so via
# `assumptions`.
DEFAULT_CORE_ROW_BYTES = (200, 2_000)
DEFAULT_RESULT_ROW_BYTES = (150, 1_500)
DEFAULT_CANDIDATE_SOURCE_BYTES = (500, 5_000)
DEFAULT_PER_CANDIDATE_SECONDS = (0.05, 2.0)


class RunClass(str, Enum):
    """Operational size tier for a planned run (STEP 11 action 1)."""
    SMOKE = "S"
    BOUNDED = "B"
    LARGE = "L"
    EXTREME = "X"


@dataclass(frozen=True)
class ResourceThresholds:
    """Configurable final-candidate-count boundaries that classify a run
    (STEP 11 action 2: "Configurable thresholds, defaults из high-level
    plan."). The high-level plan names the four classes (S/B/L/X) but leaves
    numeric boundaries to the implementation/operator — these defaults are
    placeholders an operator overrides via CLI/config once real scale data
    (benchmark harness, STEP 40) is available.

    A run whose final count cannot be statically sized (UNKNOWN) is classified
    `X` — fail-conservative, never silently treated as small.
    """
    smoke_max: int = 500
    bounded_max: int = 50_000
    large_max: int = 5_000_000

    def classify(self, final_count: "int | None") -> RunClass:
        if final_count is None:
            return RunClass.EXTREME
        if final_count <= self.smoke_max:
            return RunClass.SMOKE
        if final_count <= self.bounded_max:
            return RunClass.BOUNDED
        if final_count <= self.large_max:
            return RunClass.LARGE
        return RunClass.EXTREME


def _scaled_estimate(count: CardinalityEstimate, *, per_unit_low: float, per_unit_high: float,
                      unit: str, label: str,
                      extra_assumptions: "Sequence[str]" = (),
                      as_int: bool = True) -> CardinalityEstimate:
    """Scale a cardinality estimate by an assumed per-unit cost range.

    Mirrors `fg._combine_product`'s confidence discipline: an UNKNOWN count
    propagates as UNKNOWN — STEP 11 acceptance criterion "Unknown execution
    cost не становится нулём" applies to every dimension here, not only
    duration. The result is always `ESTIMATED` (never EXACT/BOUNDED): the
    per-unit cost is an assumption, not a provable bound, no matter how
    precisely the *count* is known.
    """
    if count.mode == CardinalityMode.UNKNOWN or count.value is None:
        cost_desc = f"{per_unit_low:g}" if per_unit_low == per_unit_high else f"{per_unit_low:g}-{per_unit_high:g}"
        # STEP 11 action 4 ("Любая estimate должна иметь assumptions") applies
        # to UNKNOWN estimates too — an UNKNOWN count is exactly where the
        # would-be per-unit assumption matters most to spell out, not less.
        return CardinalityEstimate.unknown(
            formula=f"{label} = ({unit} count) × (assumed per-unit cost) — count is UNKNOWN",
            reasons=(f"{label} cannot be sized without a known {unit} count; "
                     f"see the cardinality plan's reasons for why that count is UNKNOWN",),
            assumptions=tuple(extra_assumptions) +
            (f"even if the {unit} count were known, {label} would still depend on an assumed "
             f"per-unit cost in [{cost_desc}] — no real sample exists to calibrate it",))
    lower_n = count.lower if count.lower is not None else count.value
    upper_n = count.upper if count.upper is not None else count.value
    # `as_int` truncation is correct for whole-unit dimensions (bytes, inodes,
    # requests, seconds) but DESTROYS sub-unit dimensions like monetary cost —
    # 2 candidates × $0.01 truncating to int(0.02) == 0 would silently let a
    # $0.01 hard limit through. Monetary cost (and any other fractional-unit
    # dimension) must keep its floating-point precision end to end.
    cast = (lambda x: int(x)) if as_int else (lambda x: x)
    lower = cast(lower_n * per_unit_low)
    upper = cast(upper_n * per_unit_high)
    point = cast(count.value * ((per_unit_low + per_unit_high) / 2.0))
    cost_desc = f"{per_unit_low:g}" if per_unit_low == per_unit_high else f"{per_unit_low:g}-{per_unit_high:g}"
    return CardinalityEstimate(
        mode=CardinalityMode.ESTIMATED, value=point, lower=lower, upper=upper,
        formula=f"{label} ≈ {unit} count [{lower_n}, {upper_n}] × {cost_desc} per unit",
        reasons=(f"derived from a {count.mode.value} {unit} count — the per-unit cost itself "
                 f"is an assumption, not a measurement, so this stays ESTIMATED however exact "
                 f"the count is",),
        assumptions=tuple(extra_assumptions) +
        (f"per-unit cost assumed in [{cost_desc}] without a real sample — replace with a "
         f"measured value (e.g. via `bundle doctor`/the stage benchmark harness) for a tighter range",))


@dataclass(frozen=True)
class ResourcePlan:
    """Operational resource estimates derived from a `SpecCardinalityPlan`
    (STEP 11 action 3) — every dimension keeps its own confidence/assumptions
    instead of collapsing to a bare number, exactly like `SpecCardinalityPlan`
    does for row counts."""
    run_class: RunClass
    final_count: "int | None"
    core_db_bytes: CardinalityEstimate
    results_db_bytes: CardinalityEstimate
    candidate_source_bytes: CardinalityEstimate
    inode_count: CardinalityEstimate
    request_count: CardinalityEstimate
    duration_seconds: CardinalityEstimate
    monetary_cost: "Optional[CardinalityEstimate]"
    dominant: str
    dominant_reason: str
    # Plan-1 Phase 2 (docs/24 §3.3): present only when a repeat count plan is active (K>1).
    # `metric_artifact_bytes` is the repeat-aware metrics corpus — a FILE artifact, NOT
    # Results-DB rows (those stay V-only). `execution_count` is I (measurement opportunities),
    # preserved alongside `final_count` (distinct C). Both `None` ⇒ legacy / K=1.
    metric_artifact_bytes: "Optional[CardinalityEstimate]" = None
    execution_count: "int | None" = None
    # The full I estimate (mode/bounds/formula) so an UNKNOWN candidate count stays visible as
    # "execution count I = UNKNOWN" rather than collapsing to None — which would be
    # indistinguishable from inactive K=1. `None` ⇒ legacy/K=1; present ⇒ active repeat plan (its
    # `.value` may itself be None for an UNKNOWN C). `execution_count` above is an additive scalar.
    execution_count_estimate: "Optional[CardinalityEstimate]" = None


_DIMENSION_LABELS = {
    "core_db_bytes": "Core DB bytes",
    "results_db_bytes": "Results DB bytes",
    "candidate_source_bytes": "candidate source bytes",
    "inode_count": "loose-file inode count",
    "request_count": "external request count",
    "duration_seconds": "execution duration (seconds)",
    "monetary_cost": "monetary cost",
    "metric_artifact_bytes": "metric artifact bytes",
}


def estimate_resources(plan: "fg.SpecCardinalityPlan", *,
                        thresholds: "Optional[ResourceThresholds]" = None,
                        core_row_bytes: "tuple[float, float]" = DEFAULT_CORE_ROW_BYTES,
                        results_row_bytes: "tuple[float, float]" = DEFAULT_RESULT_ROW_BYTES,
                        template_sample_bytes: "Optional[int]" = None,
                        per_candidate_seconds: "tuple[float, float]" = DEFAULT_PER_CANDIDATE_SECONDS,
                        cost_per_candidate: "Optional[float]" = None,
                        count_plan: "Optional[object]" = None,
                        metric_row_bytes: "tuple[float, float]" = DEFAULT_RESULT_ROW_BYTES) -> ResourcePlan:
    """Build the full resource/run-class plan for `plan` (STEP 11).

    `template_sample_bytes` lets a caller plug in a real candidate-source
    sample (per action 3's "candidate source bytes на основе template
    sample") — without one, a generic placeholder range is used and the
    estimate says so via `assumptions`. `cost_per_candidate` is the optional
    monetary dimension (action 3's last bullet); omitted unless a price is
    configured, per the high-level plan's "monetary estimate, если задана цена".
    """
    thresholds = thresholds or ResourceThresholds()

    # Plan-1 §3.3: with an active repeat count plan (K>1) the execution-derived dimensions
    # scale off the count plan's verdict count V (Results-DB rows) and measurement-opportunity
    # count I (requests, duration, monetary, metric artifact, run class), NOT the distinct
    # candidate count C. No count plan / K=1 ⇒ V=I=C ⇒ byte-identical to the legacy estimate.
    _active = count_plan is not None and not count_plan.topology_inactive
    verdict_count = count_plan.full_verdict_invocations if _active else plan.final
    exec_count = count_plan.measurement_opportunities if _active else plan.final

    core_db_bytes = _scaled_estimate(
        plan.mandatory, per_unit_low=core_row_bytes[0], per_unit_high=core_row_bytes[1],
        unit="Core rows", label="Core DB bytes")
    results_db_bytes = _scaled_estimate(
        verdict_count, per_unit_low=results_row_bytes[0], per_unit_high=results_row_bytes[1],
        unit="verdict rows (V)", label="Results DB bytes")

    if template_sample_bytes is not None:
        src_lo = src_hi = float(template_sample_bytes)
        src_assumptions = (f"candidate source size taken from the provided template sample "
                           f"({template_sample_bytes} bytes) — still a single sample, not a "
                           f"distribution, so treat the range as a point estimate",)
    else:
        src_lo, src_hi = DEFAULT_CANDIDATE_SOURCE_BYTES
        src_assumptions = (f"no template sample provided — candidate source size assumed in the "
                           f"generic range {DEFAULT_CANDIDATE_SOURCE_BYTES} bytes; pass a real "
                           f"sample (`template_sample_bytes`) for a sound estimate",)
    candidate_source_bytes = _scaled_estimate(
        plan.final, per_unit_low=src_lo, per_unit_high=src_hi,
        unit="final candidates", label="candidate source bytes", extra_assumptions=src_assumptions)

    inode_count = _scaled_estimate(
        plan.final, per_unit_low=1, per_unit_high=1,
        unit="final candidates", label="loose-file inode count",
        extra_assumptions=("one inode per loose candidate file — the compressed shard sink "
                           "(STEP 32) would change this ratio; not yet active by default",))
    request_count = _scaled_estimate(
        exec_count, per_unit_low=1, per_unit_high=1,
        unit="measurement opportunities (I)", label="external request count",
        extra_assumptions=("one execution request per candidate invocation; I = V + metric-only "
                           "repeats (docs/24 §3.3)",))
    duration_seconds = _scaled_estimate(
        exec_count, per_unit_low=per_candidate_seconds[0], per_unit_high=per_candidate_seconds[1],
        unit="measurement opportunities (I)", label="execution duration (seconds)",
        extra_assumptions=(f"per-candidate cost assumed in [{per_candidate_seconds[0]:g}, "
                           f"{per_candidate_seconds[1]:g}] seconds, single worker — no "
                           f"parallelism/backpressure modelled (see STEP 33/34)",
                           "with repeats active, duration ≈ I × per-candidate cost — the CONSERVATIVE "
                           "assumption t_m == t_v (a metric-only re-measure costs as much as a full "
                           "verdict); the split V·t_v + metric_only·t_m awaits Phase 4's measured t_m",))

    monetary_cost = None
    if cost_per_candidate is not None:
        monetary_cost = _scaled_estimate(
            exec_count, per_unit_low=cost_per_candidate, per_unit_high=cost_per_candidate,
            unit="measurement opportunities (I)", label="monetary cost", as_int=False,
            extra_assumptions=(f"flat ${cost_per_candidate:g} per candidate, as configured — "
                               f"no infrastructure/idle cost included",))

    # Plan-1 §3.3: the repeat-aware metrics corpus (metrics.kv) is a FILE artifact sized by the
    # measurement opportunities I — added to the disk budget alongside Core/Results/sources, NEVER
    # folded into Results-DB bytes. Present only when a repeat count plan is active (K>1).
    metric_artifact_bytes = None
    if _active:
        metric_artifact_bytes = _scaled_estimate(
            exec_count, per_unit_low=metric_row_bytes[0], per_unit_high=metric_row_bytes[1],
            unit="measurement opportunities (I)", label="metric artifact bytes",
            extra_assumptions=("repeat-aware metrics corpus on the filesystem (metrics.kv) — a file "
                               "artifact, not a Results-DB row (those stay V-only); docs/24 §3.3. "
                               "CONSERVATIVE UPPER BOUND: one row per measurement opportunity; missing "
                               "measurements (empty captures) may yield fewer rows. Placeholder per-row "
                               "bytes until the artifact schema lands.",))

    dims: "dict[str, CardinalityEstimate]" = {
        "core_db_bytes": core_db_bytes,
        "results_db_bytes": results_db_bytes,
        "candidate_source_bytes": candidate_source_bytes,
        "inode_count": inode_count,
        "request_count": request_count,
        "duration_seconds": duration_seconds,
    }
    if monetary_cost is not None:
        dims["monetary_cost"] = monetary_cost
    if metric_artifact_bytes is not None:
        dims["metric_artifact_bytes"] = metric_artifact_bytes

    # "Dominant resource" (action 6) is necessarily a rough cross-unit signal —
    # bytes vs. seconds vs. counts aren't commensurable without budget weights
    # (STEP 12). Until those exist, the largest assumed point value is reported
    # as a planning hint, with the comparison's nature spelled out so it is
    # never mistaken for a normalized ranking.
    sized = {k: e for k, e in dims.items() if e.value is not None}
    if sized:
        dominant_key = max(sized, key=lambda k: sized[k].value)
        dominant = _DIMENSION_LABELS[dominant_key]
        dominant_reason = (f"largest assumed point estimate ({sized[dominant_key].value}) among "
                           f"sizable dimensions — a rough cross-unit signal only; budget gates "
                           f"(STEP 12) will provide a normalized ranking")
    else:
        dominant = "unknown"
        dominant_reason = "every dimension is UNKNOWN — final candidate count could not be sized statically"

    return ResourcePlan(
        run_class=thresholds.classify(exec_count.value),
        final_count=plan.final.value,
        core_db_bytes=core_db_bytes,
        results_db_bytes=results_db_bytes,
        candidate_source_bytes=candidate_source_bytes,
        inode_count=inode_count,
        request_count=request_count,
        duration_seconds=duration_seconds,
        monetary_cost=monetary_cost,
        dominant=dominant,
        dominant_reason=dominant_reason,
        metric_artifact_bytes=metric_artifact_bytes,
        execution_count=(exec_count.value if _active else None),
        execution_count_estimate=(exec_count if _active else None),
    )


def resource_plan_to_dict(plan: ResourcePlan) -> dict:
    """JSON-able projection of a :class:`ResourcePlan` (mirrors
    `fg.cardinality_plan_to_dict` so the two views stay structurally twinned)."""
    d = {
        "run_class": plan.run_class.value,
        "final_count": plan.final_count,
        "core_db_bytes": fg.cardinality_estimate_to_dict(plan.core_db_bytes),
        "results_db_bytes": fg.cardinality_estimate_to_dict(plan.results_db_bytes),
        "candidate_source_bytes": fg.cardinality_estimate_to_dict(plan.candidate_source_bytes),
        "inode_count": fg.cardinality_estimate_to_dict(plan.inode_count),
        "request_count": fg.cardinality_estimate_to_dict(plan.request_count),
        "duration_seconds": fg.cardinality_estimate_to_dict(plan.duration_seconds),
        "monetary_cost": fg.cardinality_estimate_to_dict(plan.monetary_cost) if plan.monetary_cost else None,
        "metric_artifact_bytes": (fg.cardinality_estimate_to_dict(plan.metric_artifact_bytes)
                                  if plan.metric_artifact_bytes else None),
        "execution_count": plan.execution_count,
        "execution_count_estimate": (fg.cardinality_estimate_to_dict(plan.execution_count_estimate)
                                     if plan.execution_count_estimate is not None else None),
        "dominant": plan.dominant,
        "dominant_reason": plan.dominant_reason,
    }
    return d


def _format_resource_estimate(label: str, est: CardinalityEstimate) -> str:
    if est.mode == CardinalityMode.UNKNOWN:
        body = f"UNKNOWN  ({est.formula})"
    else:
        body = f"~{est.value}  [{est.lower}, {est.upper}]  ({est.mode.value} — {est.formula})"
    lines = [f"{label}: {body}"]
    for a in est.assumptions:
        lines.append(f"    assumption: {a}")
    return "\n".join(lines)


def format_resource_plan(plan: ResourcePlan) -> str:
    """Human-readable rendering of a :class:`ResourcePlan` — mirrors
    `fg.format_cardinality_plan`'s one-line-per-dimension + reasons/assumptions
    layout (STEP 11 action 6: plan output shows the dominant resource)."""
    head = f"run class: {plan.run_class.value}  (final candidate count = {plan.final_count}"
    if plan.execution_count_estimate is not None:
        i_val = plan.execution_count_estimate.value
        head += f"; execution count I = {'UNKNOWN' if i_val is None else i_val}"
    lines = [head + ")"]
    lines.append(_format_resource_estimate("Core DB bytes", plan.core_db_bytes))
    lines.append(_format_resource_estimate("Results DB bytes", plan.results_db_bytes))
    lines.append(_format_resource_estimate("candidate source bytes", plan.candidate_source_bytes))
    lines.append(_format_resource_estimate("loose-file inode count", plan.inode_count))
    lines.append(_format_resource_estimate("external request count", plan.request_count))
    lines.append(_format_resource_estimate("execution duration (s)", plan.duration_seconds))
    if plan.monetary_cost is not None:
        lines.append(_format_resource_estimate("monetary cost", plan.monetary_cost))
    if plan.metric_artifact_bytes is not None:
        lines.append(_format_resource_estimate("metric artifact bytes", plan.metric_artifact_bytes))
    lines.append(f"dominant resource: {plan.dominant}  ({plan.dominant_reason})")
    return "\n".join(lines)
