"""Plan-1 Phase 2: the structured execution-count plan.

Design contract: ``docs/24_PLAN1_PHASE0_CONTRACT_DELTA.md`` (v4), accepted by Automation QA
(`Automation_GPT-5_2026-06-19T12_59Z.md`, ACCEPT WITH EXPLICIT LIMITATIONS).

A per-candidate *repeat* run measures the same candidate ``K`` times to turn a single
noisy metric sample into a per-candidate distribution. How many times the candidate is
*dispatched*, *run as a full verdict*, and *measured* differs by ``repeatPolicy`` and
``repeatScope`` — and a single scalar cannot represent all of those (they diverge under
``repeatScope=metrics``). This module returns a **structured count plan** whose fields are
each consumed by a named planner/budget/invariant, and whose confidence is preserved end
to end (an UNKNOWN candidate count stays UNKNOWN, never becomes 0).

Minimal independent planned quantities (everything else derives):
  * ``A`` = ``assignment_units``        — control-plane dispatch units (policy-specific).
  * ``V`` = ``full_verdict_invocations``— runs that produce an honest verdict ⇒ exactly
                                          ``V`` ``results_v2`` canonical rows ⇒
                                          ``processed == attempted == canonical_rows == V``.
  * ``I`` = ``measurement_opportunities``— total sandbox runs = ``V + metric_only``. Each
                                          invocation is one *chance* to observe a metric;
                                          whether it produces a row is a runtime fact
                                          (``metric_rows + missing == measurement_opportunities``),
                                          so this planned field is an opportunity count, not
                                          an assumed-observed sample count.
  * ``metric_only_invocations = I - V``  — computed by a direct per-cell formula, never by
                                          subtracting UNKNOWN estimates.

Closure (Automation-accepted): ``canonical_rows == processed == V`` and
``measurement_opportunities == I == V + metric_only`` for every ``(policy, scope)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .stages import fg

CardinalityEstimate = fg.CardinalityEstimate
CardinalityMode = fg.CardinalityMode


class RepeatPolicy(str, Enum):
    """How a candidate's ``K`` repeats are distributed (REPEAT_POLICY_REFACTOR_PLAN §1).

    * ``disperse`` — scatter ``candidate×repeat`` across Executor instances ⇒ between-
      environment variance; ``K`` independently assignable units.
    * ``local``    — one Executor runs all ``K`` repeats of a candidate ⇒ within-
      environment variance; one assignable unit per candidate.
    * ``nested``   — ``K`` on each of ``E`` Executors ⇒ full decomposition; one unit per
      ``(candidate, env)``.
    """
    DISPERSE = "disperse"
    LOCAL = "local"
    NESTED = "nested"


class RepeatScope(str, Enum):
    """Which work repeats.

    * ``all``     — every sample is a full verdict + metric execution.
    * ``metrics`` — the deterministic FW_VAR verdict runs once (= metric sample 0); only
      the metric measurement repeats (``REPEAT_POLICY_REFACTOR_PLAN.md:22-25``).
    """
    ALL = "all"
    METRICS = "metrics"


def scale_cardinality_exact(est: "CardinalityEstimate", factor: int, *,
                            formula: str) -> "CardinalityEstimate":
    """Multiply a :class:`CardinalityEstimate` by an **exact, non-negative integer**
    factor, preserving the confidence mode (Automation Limitation 2).

    Neither existing helper is correct for an exact ``K``/``E`` multiplication:
      * ``resources._scaled_estimate`` always returns ``ESTIMATED`` (it scales by an
        *assumed* per-unit cost) — it would downgrade an EXACT/BOUNDED count to a guess.
      * ``fwgen._combine_product`` handles EXACT/BOUNDED/UNKNOWN but **drops** an input
        ``ESTIMATED`` to ``BOUNDED`` (a non-exact, non-unknown factor falls through).

    The factor here is provably exact (a count of repeats/environments), so it never
    weakens the mode:
      * ``UNKNOWN``   → ``UNKNOWN`` (reasons/assumptions propagated; never becomes 0).
      * ``EXACT``     → ``EXACT``  (value/lower/upper × factor).
      * ``BOUNDED``   → ``BOUNDED``(value/lower/upper × factor).
      * ``ESTIMATED`` → ``ESTIMATED`` (every present numeric field × factor; bounds are
        *not* promoted to proof).
    An exact factor of ``0`` collapses any mode to a proven ``EXACT 0`` (``0 × anything ==
    0``) — used for ``metric_only`` in the all-scope/non-metrics cells, where there are
    provably no metric-only invocations regardless of the candidate count.
    """
    if factor < 0:
        raise ValueError(f"scale_cardinality_exact: factor must be >= 0, got {factor}")
    if factor == 0:
        return CardinalityEstimate.exact(0, formula=formula, assumptions=est.assumptions)

    def _mul(x):
        return None if x is None else x * factor

    mode = est.mode
    if mode == CardinalityMode.UNKNOWN:
        return CardinalityEstimate.unknown(formula=formula, reasons=est.reasons,
                                           assumptions=est.assumptions)
    if mode == CardinalityMode.EXACT:
        return CardinalityEstimate.exact(_mul(est.value), formula=formula,
                                         assumptions=est.assumptions)
    if mode == CardinalityMode.BOUNDED:
        return CardinalityEstimate.bounded(lower=_mul(est.lower), upper=_mul(est.upper),
                                           value=_mul(est.value), formula=formula,
                                           reasons=est.reasons, assumptions=est.assumptions)
    # ESTIMATED — stays ESTIMATED; multiply every present field, never promote to BOUNDED.
    return CardinalityEstimate(mode=CardinalityMode.ESTIMATED, value=_mul(est.value),
                               lower=_mul(est.lower), upper=_mul(est.upper), formula=formula,
                               reasons=est.reasons, assumptions=est.assumptions)


@dataclass(frozen=True)
class CountPlan:
    """The structured execution-count plan for one ``(policy, scope, C, K, E)`` (doc 24 §3).

    All four count fields are :class:`CardinalityEstimate`s so the candidate count's
    confidence (EXACT/BOUNDED/ESTIMATED/UNKNOWN) is preserved through the ×K/×E scaling.
    """
    policy: str
    scope: str
    k: int
    e_effective: int
    topology_inactive: bool                       # True ⇔ K==1 (repeat topology inactive)
    assignment_units: "CardinalityEstimate"            # A  → reader.emitted_eq_expected, manifest
    full_verdict_invocations: "CardinalityEstimate"    # V  == canonical_rows == processed
    measurement_opportunities: "CardinalityEstimate"   # I  → metric artifact, request_count, RunClass
    metric_only_invocations: "CardinalityEstimate"     # I - V (direct formula)

    # Short aliases matching the design doc's A/V/I notation.
    @property
    def A(self) -> "CardinalityEstimate":
        return self.assignment_units

    @property
    def V(self) -> "CardinalityEstimate":
        return self.full_verdict_invocations

    @property
    def I(self) -> "CardinalityEstimate":
        return self.measurement_opportunities

    def to_dict(self) -> dict:
        """JSON-able projection (mirrors ``fg.cardinality_estimate_to_dict`` per field)."""
        return {
            "policy": self.policy,
            "scope": self.scope,
            "k": self.k,
            "e_effective": self.e_effective,
            "topology_inactive": self.topology_inactive,
            "assignment_units": fg.cardinality_estimate_to_dict(self.assignment_units),
            "full_verdict_invocations": fg.cardinality_estimate_to_dict(self.full_verdict_invocations),
            "measurement_opportunities": fg.cardinality_estimate_to_dict(self.measurement_opportunities),
            "metric_only_invocations": fg.cardinality_estimate_to_dict(self.metric_only_invocations),
        }


# Per-(policy, scope) integer factors multiplying the distinct candidate count C, for K>1.
# Returns (a_factor, v_factor, i_factor, metric_only_factor). `metric_only` uses a DIRECT
# non-negative formula (Automation Limitation 2) — never `i - v` subtraction of estimates.
#   verdicts:  one full verdict per candidate for local/disperse metrics; one per
#              (candidate, env) for nested metrics; every sample is a verdict under `all`.
def _factors(policy: "RepeatPolicy", scope: "RepeatScope", k: int, e: int):
    if policy == RepeatPolicy.LOCAL:
        if scope == RepeatScope.ALL:
            return (1, k, k, 0)
        return (1, 1, k, k - 1)                 # local/metrics: verdict once, K-1 metric-only
    if policy == RepeatPolicy.DISPERSE:
        if scope == RepeatScope.ALL:
            return (k, k, k, 0)
        return (k, 1, k, k - 1)                 # disperse/metrics: verdict once, K-1 metric-only scattered
    if policy == RepeatPolicy.NESTED:
        if scope == RepeatScope.ALL:
            return (e, e * k, e * k, 0)
        return (e, e, e * k, e * (k - 1))       # nested/metrics: verdict once per (cand,env)
    raise ValueError(f"unknown repeat policy {policy!r}")


def count_plan(policy: str, scope: str, final_count: "CardinalityEstimate",
               k: int, e: "Optional[int]" = None) -> CountPlan:
    """Build the structured count plan (doc 24 §3).

    ``final_count`` is the distinct candidate count ``C`` (``fg.SpecCardinalityPlan.final``,
    a :class:`CardinalityEstimate`). ``k`` ≥ 1 repeats; ``e`` is the environment count, **required
    (≥1) for ``nested`` with K>1** and ``None`` (unused) otherwise. Operator inputs are validated by
    ``config.BundleConfig.validate_repeat``; this public function **defensively re-validates** so a
    direct caller cannot produce a fractional/mis-typed "count" or silently default a nested ``E``.

    **K=1 normalization (Automation Limitation 1 + blocker #2):** when ``k == 1`` the repeat topology is
    operationally inactive — ``E_effective = 1`` and ``A == V == I == C`` for *every* policy/scope,
    with ``metric_only == 0`` (the *derived* field is 0, not C). Applied **before** the policy table,
    so e.g. ``--repeat-policy nested`` at K=1 plans ``C`` (not ``C·E``) and matches the legacy path.
    """
    rp = RepeatPolicy(policy)
    rs = RepeatScope(scope)
    # Defensive type/range validation — this is a public planning function, not only reached via
    # BundleConfig.validate_repeat. `bool` is an `int` subclass, so reject it explicitly; reject any
    # non-int K so a stray float (e.g. 1.5) can never produce a fractional count.
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError(f"count_plan: K (repeatEachCandidate) must be a non-bool int >= 1, got {k!r}")
    if e is not None and (isinstance(e, bool) or not isinstance(e, int) or e < 1):
        raise ValueError(f"count_plan: E (repeatEnvironments) must be a non-bool int >= 1 when given, got {e!r}")

    if k == 1:
        # Topology inactive: A=V=I=C (identity, confidence preserved), metric_only=0.
        zero = CardinalityEstimate.exact(0, formula="0 (K=1: no metric-only invocations)")
        return CountPlan(policy=rp.value, scope=rs.value, k=1, e_effective=1,
                         topology_inactive=True,
                         assignment_units=final_count,
                         full_verdict_invocations=final_count,
                         measurement_opportunities=final_count,
                         metric_only_invocations=zero)

    if rp == RepeatPolicy.NESTED:
        if e is None:
            raise ValueError("count_plan: nested policy with K>1 requires an explicit E "
                             "(repeatEnvironments) >= 1 — refusing to default it, E must be authoritative")
        e_eff = e
    else:
        e_eff = 1

    a_f, v_f, i_f, mo_f = _factors(rp, rs, k, e_eff)
    tag = f"{rp.value}/{rs.value}, K={k}" + (f", E={e_eff}" if rp == RepeatPolicy.NESTED else "")
    return CountPlan(
        policy=rp.value, scope=rs.value, k=k, e_effective=e_eff, topology_inactive=False,
        assignment_units=scale_cardinality_exact(final_count, a_f, formula=f"A = C × {a_f}  ({tag})"),
        full_verdict_invocations=scale_cardinality_exact(final_count, v_f, formula=f"V = C × {v_f}  ({tag})"),
        measurement_opportunities=scale_cardinality_exact(final_count, i_f, formula=f"I = C × {i_f}  ({tag})"),
        metric_only_invocations=scale_cardinality_exact(final_count, mo_f, formula=f"metric_only = C × {mo_f}  ({tag})"),
    )
