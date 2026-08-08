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

"""Deterministic coaching model for learning to think in combinations.

The module is deliberately stdlib-only.  It proposes an editable starting
model; it never silently commits a scenario, claims constraints were applied,
or turns a bounded count into an exact one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from math import factorial, prod
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class FactorDraft:
    key: str
    name: str
    values: tuple[str, ...]
    why: str
    risk: str = ""
    shape: str = "choose_one"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvitationDraft:
    domain: str
    title: str
    goal: str
    factors: tuple[FactorDraft, ...]
    interactions: tuple[str, ...]
    missing_constraints: tuple[str, ...]
    stress_actions: tuple[FactorDraft, ...]
    use_cases: tuple[str, ...]
    lesson: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["assessment"] = assessment(self.factors, self.stress_actions).as_dict()
        return value


@dataclass(frozen=True)
class GrowthAssessment:
    mandatory: int
    optional_multiplier: int
    total: int
    interaction_pairs: int
    confidence: str
    run_band: str
    warnings: tuple[str, ...]
    missing_constraints: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("mandatory", "optional_multiplier", "total", "interaction_pairs"):
            value[key] = str(value[key])
        return value


_PROFILES: dict[str, dict[str, Any]] = {
    "learn": {
        "title": "Learn with parcel dispatch",
        "factors": (
            ("channel", "Channel", ("web", "mobile"), "Where the request begins."),
            ("account", "Account type", ("guest", "member"), "Eligibility changes with identity."),
            ("payment", "Payment type", ("card", "wallet"), "Payment interacts with account rules."),
            ("steps", "Workflow order", ("reserve", "charge", "dispatch"), "Unsafe orders must remain observable.", "permute"),
        ),
        "interactions": (
            "Account × payment asks whether every payment is actually supported.",
            "Channel × payment × duplicate submission probes idempotency.",
            "Workflow order × timeout probes recovery timing.",
        ),
        "constraints": (
            "Wallet payment requires a member account.",
            "Which other states are truly impossible?",
            "Which unsafe action orders must remain behavior under test?",
        ),
        "stress": (
            ("duplicate_submit", "Duplicate submission", ("duplicate_submit",), "Checks idempotency instead of ordinary success.", "integrity"),
            ("carrier_timeout", "Carrier timeout", ("carrier_timeout",), "Checks recovery without changing ordinary inputs.", "timing"),
        ),
        "use_cases": ("$BUNDLE_SUT_ROOT/combination_thinking_tutor", "usecases/event_order"),
        "lesson": "The teaching SUT separates impossible states, unsafe behavior, and optional disturbances.",
    },
    "service": {
        "title": "Service or API behavior",
        "factors": (
            ("request", "Request kind", ("read", "create", "update"), "The route or operation selects different behavior."),
            ("payload", "Payload class", ("small valid", "boundary valid", "invalid"), "Boundaries and invalid data need explicit representation."),
            ("dependency", "Dependency state", ("healthy", "slow", "unavailable"), "Services often fail at dependency interactions."),
        ),
        "interactions": (
            "Request kind × payload class exposes validation asymmetry.",
            "Request kind × dependency state exposes unsafe fallback and retry behavior.",
            "Payload class × dependency state exposes timeout and resource amplification.",
        ),
        "constraints": (
            "Which payload classes are valid for each request kind?",
            "Which operations are safe to retry?",
            "Which identities or preconditions are required?",
        ),
        "stress": (
            ("retry", "Retry", ("one retry", "retry burst"), "Turns idempotency assumptions into executable cases.", "integrity"),
            ("latency", "Dependency latency", ("delayed",), "Reveals timeout and cancellation behavior.", "timing"),
            ("disconnect", "Client disconnect", ("disconnect",), "Exercises cleanup after abandoned work.", "resource"),
        ),
        "use_cases": ("usecases/telemetry_catalog_e2e", "combinatorial_tests/sieve3d_external_api"),
        "lesson": "Model business inputs separately from infrastructure state; their crossings are where service defects cluster.",
    },
    "workflow": {
        "title": "Ordered or stateful workflow",
        "factors": (
            ("actor", "Actor", ("initiator", "reviewer", "system"), "Different actors own different transitions."),
            ("operation", "Operation", ("create", "approve", "cancel"), "Actions define the state-machine edges."),
            ("starting_state", "Starting state", ("new", "pending", "completed"), "The same action is not valid in every state."),
        ),
        "interactions": (
            "Actor × operation exposes permission and ownership defects.",
            "Operation × starting state exposes invalid transitions.",
            "Actor × starting state exposes stale-view and takeover behavior.",
        ),
        "constraints": (
            "Which transitions are forbidden from each starting state?",
            "Which actor must differ from the initiator?",
            "Which operations must happen before or after another?",
        ),
        "stress": (
            ("repeat", "Repeated operation", ("repeat",), "Tests whether transitions are idempotent.", "integrity"),
            ("reorder", "Out-of-order event", ("reorder",), "Tests sequence assumptions.", "timing"),
            ("pause", "Pause and resume", ("resume",), "Tests durable state and recovery.", "resource"),
        ),
        "use_cases": ("usecases/event_order", "usecases/qa_pub_vs_bar"),
        "lesson": "When order matters, represent state and actor explicitly instead of hiding both inside scenario names.",
    },
    "data": {
        "title": "Data transformation or pipeline",
        "factors": (
            ("format", "Input format", ("structured", "delimited", "semi-structured"), "Parsers fail differently across representations."),
            ("quality", "Data quality", ("clean", "missing field", "duplicate"), "Quality is independent from format."),
            ("volume", "Volume class", ("small", "boundary", "large"), "Scale can change correctness as well as speed."),
        ),
        "interactions": (
            "Format × data quality exposes parser-specific validation gaps.",
            "Data quality × volume exposes amplification and deduplication defects.",
            "Format × volume exposes buffering and memory assumptions.",
        ),
        "constraints": (
            "Which fields are mandatory for each format?",
            "Are duplicates rejected, merged, or preserved?",
            "What volume is a supported boundary rather than an arbitrary stress value?",
        ),
        "stress": (
            ("replay", "Input replay", ("replay",), "Tests deduplication and exactly-once claims.", "integrity"),
            ("partial", "Partial input", ("truncate",), "Tests atomicity and recovery.", "resource"),
            ("late", "Late arrival", ("late",), "Tests time-window assumptions.", "timing"),
        ),
        "use_cases": ("usecases/etl_pipeline", "usecases/telemetry_catalog_full"),
        "lesson": "Do not combine format, quality, and volume into one giant factor; separating them reveals cross-effects.",
    },
    "performance": {
        "title": "Performance or configuration search",
        "factors": (
            ("algorithm", "Algorithm", ("baseline", "alternative A", "alternative B"), "A stable baseline makes improvement measurable."),
            ("workload", "Workload shape", ("small", "mixed", "large"), "Optimizations rarely dominate every workload."),
            ("resource", "Resource budget", ("constrained", "typical", "generous"), "Resource assumptions affect both speed and feasibility."),
        ),
        "interactions": (
            "Algorithm × workload identifies conditional winners.",
            "Algorithm × resource budget exposes memory or parallelism trade-offs.",
            "Workload × resource budget exposes saturation boundaries.",
        ),
        "constraints": (
            "Which results must remain semantically equivalent?",
            "What hard resource ceilings invalidate a candidate?",
            "How many repetitions are needed before comparing noisy measurements?",
        ),
        "stress": (
            ("pressure", "Resource pressure", ("memory pressure", "CPU contention"), "Tests whether a winner is robust.", "resource"),
            ("cold", "Cold start", ("cold start",), "Separates initialization from steady state.", "timing"),
        ),
        "use_cases": ("usecases/perf_opt", "usecases/perf_opt_java"),
        "lesson": "Optimization needs a correctness oracle first; otherwise the fastest wrong candidate wins.",
    },
    "model": {
        "title": "Model or decision-system evaluation",
        "factors": (
            ("variant", "Model variant", ("baseline", "candidate A", "candidate B"), "The variant is only one axis of evaluation."),
            ("data_slice", "Data slice", ("typical", "rare", "adversarial"), "Aggregate scores can hide slice failures."),
            ("budget", "Inference budget", ("small", "typical", "large"), "Quality and cost must be evaluated together."),
        ),
        "interactions": (
            "Model variant × data slice exposes uneven quality.",
            "Model variant × budget exposes cost-quality trade-offs.",
            "Data slice × budget exposes fragile behavior under constraints.",
        ),
        "constraints": (
            "Which metric is the hard correctness gate?",
            "Which data slices must never regress?",
            "What budget makes a candidate infeasible?",
        ),
        "stress": (
            ("noise", "Input perturbation", ("light noise", "heavy noise"), "Measures robustness rather than average quality.", "integrity"),
            ("pressure", "Memory pressure", ("constrained memory",), "Tests deployment feasibility.", "resource"),
        ),
        "use_cases": ("usecases/ml_eval", "usecases/ml_eval_surrogate"),
        "lesson": "Separate quality slices from implementation variants so failures cannot disappear inside one average.",
    },
    "interface": {
        "title": "User interface or interaction flow",
        "factors": (
            ("journey", "User journey", ("create", "edit", "recover"), "Journeys describe intent rather than individual clicks."),
            ("input", "Input class", ("typical", "boundary", "invalid"), "Validation and recovery need explicit cases."),
            ("viewport", "Viewport", ("desktop", "narrow"), "Layout can alter reachability and sequence."),
        ),
        "interactions": (
            "Journey × input class exposes inconsistent validation.",
            "Journey × viewport exposes unreachable actions.",
            "Input class × viewport exposes error-display defects.",
        ),
        "constraints": (
            "Which steps are prerequisites for each journey?",
            "Which controls must remain keyboard reachable?",
            "Which invalid inputs should preserve prior state?",
        ),
        "stress": (
            ("double", "Repeated activation", ("double activation",), "Tests duplicate submission guards.", "integrity"),
            ("refresh", "Refresh during edit", ("refresh",), "Tests persistence and recovery.", "resource"),
        ),
        "use_cases": ("usecases/gui_constraints_e2e", "usecases/gui_reactor_e2e"),
        "lesson": "Model user intent and state; enumerating raw clicks alone produces noise rather than useful coverage.",
    },
}


def domains() -> tuple[dict[str, str], ...]:
    return tuple({"id": key, "title": value["title"]} for key, value in _PROFILES.items())


def _factor(raw: tuple[Any, ...], risk: str = "") -> FactorDraft:
    key, name, values, why, *rest = raw
    shape = str(rest[0]) if rest else "choose_one"
    return FactorDraft(key, name, tuple(values), why, risk, shape)


def propose(domain: str, goal: str = "", risks: Iterable[str] = ()) -> InvitationDraft:
    key = domain if domain in _PROFILES else "learn"
    profile = _PROFILES[key]
    risk_order = {str(value).strip().lower() for value in risks if str(value).strip()}
    stress = [_factor(item[:4], item[4]) for item in profile["stress"]]
    if risk_order:
        stress.sort(key=lambda item: (item.risk not in risk_order, item.name))
    return InvitationDraft(
        domain=key,
        title=profile["title"],
        goal=str(goal or "").strip(),
        factors=tuple(_factor(item) for item in profile["factors"]),
        interactions=tuple(profile["interactions"]),
        missing_constraints=tuple(profile["constraints"]),
        stress_actions=tuple(stress),
        use_cases=tuple(profile["use_cases"]),
        lesson=profile["lesson"],
    )


def _coerce_factor(value: FactorDraft | Mapping[str, Any]) -> FactorDraft:
    if isinstance(value, FactorDraft):
        return value
    raw_values = value.get("values", ())
    return FactorDraft(
        str(value.get("key") or value.get("name") or "factor"),
        str(value.get("name") or value.get("key") or "Factor"),
        tuple(str(item).strip() for item in raw_values if str(item).strip()),
        str(value.get("why") or ""),
        str(value.get("risk") or ""),
        str(value.get("shape") or "choose_one"),
    )


def assessment(
    factors: Iterable[FactorDraft | Mapping[str, Any]],
    stress_actions: Iterable[FactorDraft | Mapping[str, Any]] = (),
    constraints: Iterable[str] = (),
) -> GrowthAssessment:
    normal = tuple(_coerce_factor(item) for item in factors)
    optional = tuple(_coerce_factor(item) for item in stress_actions)
    constraint_list = tuple(str(item).strip() for item in constraints if str(item).strip())
    warnings: list[str] = []

    level_counts: list[int] = []
    output_counts: list[int] = []
    for factor in normal:
        unique = tuple(dict.fromkeys(factor.values))
        if len(unique) != len(factor.values):
            warnings.append(f"{factor.name} repeats a value; duplicates add noise, not coverage.")
        if len(unique) < 2:
            warnings.append(f"{factor.name} has fewer than two values; fix it as context or add a real alternative.")
        if len(unique) > 12:
            warnings.append(f"{factor.name} has {len(unique)} values; split only if those values represent different risks.")
        levels = max(1, len(unique))
        level_counts.append(levels)
        output_counts.append(factorial(levels) if factor.shape == "permute" else levels)

    mandatory = prod(output_counts) if output_counts else 0
    optional_multiplier = prod(max(1, len(tuple(dict.fromkeys(item.values)))) + 1 for item in optional) if optional else 1
    total = mandatory * optional_multiplier
    interaction_pairs = sum(a * b for a, b in combinations(level_counts, 2))

    if len(normal) > 8:
        warnings.append("More than eight factors is difficult to reason about; merge correlated factors or stage the investigation.")
    if len(optional) > 4:
        warnings.append("Too many optional disturbances hide causality; introduce them in small risk-focused batches.")
    if len(normal) >= 2 and not constraint_list:
        warnings.append("No relationships are recorded yet; the raw count assumes every crossing is valid.")
    if total > 1_000_000:
        warnings.append("The raw space exceeds one million cases; constrain invalid relations or split the question before execution.")
    elif total > 100_000:
        warnings.append("The raw space is large; plan first and consider staged or interaction-focused coverage.")
    elif total > 10_000:
        warnings.append("The raw space needs an explicit execution budget and early planning.")

    missing = () if constraint_list or len(normal) < 2 else (
        "forbidden combinations",
        "required dependencies",
        "ordering or state-transition rules",
    )
    band = "S" if total <= 1_000 else "B" if total <= 10_000 else "L" if total <= 100_000 else "X"
    return GrowthAssessment(
        mandatory=mandatory,
        optional_multiplier=optional_multiplier,
        total=total,
        interaction_pairs=interaction_pairs,
        confidence="EXACT_RAW" if normal else "INCOMPLETE",
        run_band=band,
        warnings=tuple(warnings),
        missing_constraints=missing,
    )
