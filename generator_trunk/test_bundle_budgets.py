#!/usr/bin/env python3
"""Targeted tests for bundle.budgets + bundle.cli's STEP-12 budget gate:
warning/hard thresholds, blocked synthetic explosions, override accountability,
and the X-class confirmation — all evaluated statically, no Core/DB/process
side effects (run: `python3 test_bundle_budgets.py`)."""
from types import SimpleNamespace

import fwgen as fg
from bundle.budgets import (
    BudgetLimits,
    BudgetSeverity,
    blocking_checks,
    evaluate_budgets,
    warning_checks,
)
from bundle.cli import _check_budgets
from bundle.config import BundleConfig
from bundle.errors import BudgetError
from bundle.resources import RunClass, estimate_resources

SMALL_SPEC = {
    "slots": [
        {"sheet": "A", "values": ["a1", "a2", "a3"]},
        {"sheet": "B", "values": ["b1", "b2"]},
        {"sheet": "C", "values": ["c1", "c2", "c3"]},
    ],
}


def _permut_spec(name: str, n: int):
    return fg.parse_spec(
        {"slots": [{"sheet": "P", "verb": "FW_Permut", "values": [f"v{i}" for i in range(n)]}]}, name)


# STEP 13 folded the budget ceilings into `BundleConfig` (action 3: "budgets"
# is one of the things layered config must cover) — `_check_budgets` now reads
# them from `cfg`, not from argparse `a.budget_*`. `_args` therefore only
# carries the operational/accountability flags that stay outside config
# (override reason + extreme confirmation are per-invocation, never "settings"
# — see STEP 12); `_cfg` builds the layered-config side, keyed by the same
# `--budget-*` names the CLI exposes (mapped onto `BundleConfig` field names).
_BUDGET_ARG_TO_CONFIG_KEY = {
    "budget_mandatory_rows": "budget_mandatory_rows",
    "budget_final_candidates": "budget_final_candidates",
    "budget_disk_bytes": "budget_disk_bytes",
    "budget_inodes": "budget_inodes",
    "budget_wall_time_seconds": "budget_wall_time_seconds",
    "budget_requests": "budget_external_requests",
    "budget_monetary_cost": "budget_monetary_cost",
    "budget_warn_fraction": "budget_warn_fraction",
}


def _args(**over):
    base = dict(override_budget=None, allow_extreme=False, cost_per_candidate=None)
    base.update({k: v for k, v in over.items() if k not in _BUDGET_ARG_TO_CONFIG_KEY})
    return SimpleNamespace(**base)


def _cfg(**over):
    return BundleConfig(**{_BUDGET_ARG_TO_CONFIG_KEY[k]: v
                           for k, v in over.items() if k in _BUDGET_ARG_TO_CONFIG_KEY})


def _check(over_dict, spec):
    """`_check_budgets` needs both the operational namespace and the layered
    config — split *over_dict* across `_args`/`_cfg` (by key) and call it the
    way `cli._run` does (`_check_budgets(a, spec, cfg)`)."""
    return _check_budgets(_args(**over_dict), spec, _cfg(**over_dict))


def test_evaluate_budgets_classifies_ok_warning_blocking_with_reasons():
    spec = fg.parse_spec(SMALL_SPEC, "small")
    plan = fg.spec_cardinality_plan(spec)        # final = 18
    rp = estimate_resources(plan)

    ok_checks = evaluate_budgets(plan, rp, BudgetLimits(final_candidates=1_000))
    fc = next(c for c in ok_checks if c.dimension == "final_candidates")
    assert fc.severity == BudgetSeverity.OK and "within budget" in fc.message

    warn_checks_ = evaluate_budgets(plan, rp, BudgetLimits(final_candidates=20, warn_fraction=0.5))
    fc = next(c for c in warn_checks_ if c.dimension == "final_candidates")
    assert fc.severity == BudgetSeverity.WARNING and "warning threshold" in fc.message

    block_checks = evaluate_budgets(plan, rp, BudgetLimits(final_candidates=10))
    fc = next(c for c in block_checks if c.dimension == "final_candidates")
    assert fc.severity == BudgetSeverity.BLOCKING and "exceeds hard limit" in fc.message

    # an unconfigured dimension (None) is OK, not an implicit zero ceiling
    none_checks = evaluate_budgets(plan, rp, BudgetLimits(monetary_cost=None))
    mc = next(c for c in none_checks if c.dimension == "monetary_cost")
    assert mc.severity == BudgetSeverity.OK and "no limit configured" in mc.message


def test_unsizable_dimension_with_hard_limit_blocks_rather_than_passing_silently():
    M = fg.CardinalityMode
    spec = fg.parse_spec({
        "slots": [{"sheet": "A", "values": ["a1", "a2"], "flags": ["FW_Exclude"]},
                  {"sheet": "B", "values": ["b1", "b2"], "flags": ["FW_Exclude"]},
                  {"sheet": "JOINED", "values": [" x"]}],
        "seq_extra": [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]],
    }, "brace-budget")
    plan = fg.spec_cardinality_plan(spec)
    assert plan.final.mode == M.UNKNOWN
    rp = estimate_resources(plan)

    checks = evaluate_budgets(plan, rp, BudgetLimits(final_candidates=1_000))
    fc = next(c for c in checks if c.dimension == "final_candidates")
    assert fc.unsizable and fc.severity == BudgetSeverity.BLOCKING
    assert "UNKNOWN" in fc.message and "blocked until overridden" in fc.message

    # ... but with no hard limit configured, an unsizable dimension is OK (nothing to gate)
    open_checks = evaluate_budgets(plan, rp, BudgetLimits(final_candidates=None))
    fc_open = next(c for c in open_checks if c.dimension == "final_candidates")
    assert fc_open.unsizable and fc_open.severity == BudgetSeverity.OK


def test_synthetic_explosion_blocked_before_any_stage_starts():
    # 10! = 3,628,800 — over the default 2,000,000 hard ceilings (mandatory
    # rows / final candidates) yet still classified L (large_max=5,000,000),
    # so this isolates the BUDGET gate from the X-class gate. Sized purely
    # from the closed-form formula, never by materializing rows.
    big = _permut_spec("explosion", 10)
    cardinality = fg.spec_cardinality_plan(big)
    assert cardinality.final.value == 3_628_800
    assert estimate_resources(cardinality).run_class == RunClass.LARGE

    try:
        _check({}, big)
        assert False, "synthetic explosion must be blocked"
    except BudgetError as exc:
        msg = str(exc)
        assert "hard budget threshold(s) exceeded" in msg
        assert "blocking before Generator/Core starts" in msg
        assert "override with: --override-budget" in msg


def test_override_without_reason_is_rejected():
    big = _permut_spec("explosion2", 10)
    for bad_reason in (None, "", "   "):
        try:
            _check({"override_budget": bad_reason}, big)
            assert False, f"empty override reason {bad_reason!r} must be rejected"
        except BudgetError as exc:
            assert "override" in str(exc).lower()


def test_accepted_override_is_reflected_in_the_returned_manifest_intent():
    big = _permut_spec("explosion3", 10)
    intent = _check({"override_budget": "approved for the synthetic-explosion smoke test"}, big)
    assert intent["override"] is True
    assert intent["reason"] == "approved for the synthetic-explosion smoke test"
    assert intent["exceeded"]                       # which dimensions triggered it is recorded too
    assert intent["run_class"] == RunClass.LARGE.value
    assert intent["allow_extreme"] is False


def test_extreme_class_requires_its_own_flag_independent_of_override():
    huge = _permut_spec("huge4", 13)
    # a budget override alone does not satisfy the X-class gate
    try:
        _check({"override_budget": "plenty of reason, but no --allow-extreme"}, huge)
        assert False, "X class must require --allow-extreme regardless of --override-budget"
    except BudgetError as exc:
        assert "extreme" in str(exc).lower() and "--allow-extreme" in str(exc)

    # nor does --allow-extreme alone satisfy a separate hard-budget block
    try:
        _check({"allow_extreme": True}, huge)
        assert False, "hard budget exceed must still require --override-budget"
    except BudgetError as exc:
        assert "override" in str(exc).lower()


def test_existing_small_run_passes_with_no_override_needed():
    # the reference-shaped small spec must clear default budgets untouched —
    # "Existing small runs должны проходить без override" (action 6).
    spec = fg.parse_spec(SMALL_SPEC, "small-pass")
    intent = _check({}, spec)
    assert intent["override"] is False
    assert intent["reason"] is None
    assert intent["exceeded"] == []
    assert intent["run_class"] in (RunClass.SMOKE.value, RunClass.BOUNDED.value)


def test_monetary_budget_is_gated_only_when_a_price_is_configured():
    # Without --cost-per-candidate there is no monetary projection at all —
    # a configured monetary ceiling has nothing to compare against, so it
    # cannot block (must not be silently treated as "0 cost, always passes"
    # OR as "unsizable, always blocks"; it is simply not gated).
    spec = fg.parse_spec(SMALL_SPEC, "money-unpriced")  # final = 18
    intent = _check({"budget_monetary_cost": 0.01}, spec)
    assert intent["exceeded"] == []
    assert intent["override"] is False

    plan = fg.spec_cardinality_plan(spec)
    rp_unpriced = estimate_resources(plan, cost_per_candidate=None)
    assert rp_unpriced.monetary_cost is None
    checks = evaluate_budgets(plan, rp_unpriced, BudgetLimits(monetary_cost=0.01))
    mc = next(c for c in checks if c.dimension == "monetary_cost")
    assert mc.severity == BudgetSeverity.OK and "no limit configured" not in mc.message
    assert "not estimated" in mc.message

    # With --cost-per-candidate configured, the monetary dimension gets a real
    # ESTIMATED projection (18 candidates × $1/candidate = ~$18) that a hard
    # ceiling of $1 must classify as exceeded and BLOCKING.
    rp_priced = estimate_resources(plan, cost_per_candidate=1.0)
    assert rp_priced.monetary_cost is not None
    assert rp_priced.monetary_cost.value == 18
    priced_checks = evaluate_budgets(plan, rp_priced, BudgetLimits(monetary_cost=1.0))
    mc_priced = next(c for c in priced_checks if c.dimension == "monetary_cost")
    assert mc_priced.severity == BudgetSeverity.BLOCKING and "exceeds hard limit" in mc_priced.message

    # End-to-end through the CLI gate: --cost-per-candidate=1.0 plus
    # --budget-monetary-cost=1.0 must actually BLOCK the run (the exact gap
    # called out in review — "even --budget-monetary-cost 0.01 never blocks").
    try:
        _check({"cost_per_candidate": 1.0, "budget_monetary_cost": 1.0}, spec)
        assert False, "a configured monetary ceiling must block once a price makes the cost sizable"
    except BudgetError as exc:
        msg = str(exc)
        assert "monetary cost" in msg and "exceeds hard limit" in msg
        assert "override with: --override-budget" in msg

    # ... and an accepted override records the priced run's exceeded dimension.
    intent2 = _check({"cost_per_candidate": 1.0, "budget_monetary_cost": 1.0,
            "override_budget": "approved for the monetary-budget smoke test"}, spec)
    assert intent2["override"] is True
    assert "monetary_cost" in intent2["exceeded"]


def test_fractional_monetary_cost_is_not_truncated_to_zero():
    # 2 candidates x $0.01 = $0.02 — int-truncation (int(0.02) == 0) would
    # silently slip under a $0.01 hard limit. Monetary cost must keep its
    # floating-point precision so a sub-dollar limit still blocks.
    two_spec = fg.parse_spec(
        {"slots": [{"sheet": "A", "values": ["a1", "a2"]}]}, "money-fractional")
    plan = fg.spec_cardinality_plan(two_spec)
    assert plan.final.value == 2

    rp = estimate_resources(plan, cost_per_candidate=0.01)
    assert rp.monetary_cost.value == 0.02
    assert rp.monetary_cost.lower == rp.monetary_cost.upper == 0.02
    assert rp.monetary_cost.value != 0                 # not truncated to zero

    checks = evaluate_budgets(plan, rp, BudgetLimits(monetary_cost=0.01))
    mc = next(c for c in checks if c.dimension == "monetary_cost")
    assert mc.severity == BudgetSeverity.BLOCKING and "exceeds hard limit" in mc.message

    try:
        _check({"cost_per_candidate": 0.01, "budget_monetary_cost": 0.01}, two_spec)
        assert False, "a $0.01 hard limit must block a $0.02 projected cost, not be bypassed by truncation"
    except BudgetError as exc:
        assert "monetary cost" in str(exc) and "exceeds hard limit" in str(exc)


def test_optional_number_cli_type_disables_a_dimension():
    from bundle.cli import _optional_number
    parse = _optional_number(int)
    assert parse("1000") == 1000
    for disabled in ("none", "None", "unlimited", "", "  "):
        assert parse(disabled) is None


def test_unleash_initial_productivity_power_makes_the_gate_advisory():
    """unleash_initial_productivity_power lifts the limiter: a synthetic explosion
    that normally BLOCKS instead runs (hard ceilings advisory), the manifest intent
    records it, and an X/extreme run no longer needs --allow-extreme."""
    big = _permut_spec("big", 10)            # 10! = 3,628,800 -> exceeds default ceilings
    # blocked WITHOUT the flag
    try:
        _check_budgets(_args(), big, BundleConfig())
        assert False, "expected a hard-budget block without unleash"
    except BudgetError:
        pass
    # advisory WITH the flag -> no raise, intent records it
    intent = _check_budgets(_args(), big, BundleConfig(unleash_initial_productivity_power=True))
    assert intent["unleash_initial_productivity_power"] is True
    assert "mandatory_rows" in intent["exceeded"] and intent["override"] is False

    # X/extreme: normally needs --allow-extreme; unleashed proceeds without it
    extreme = _permut_spec("xtreme", 11)     # 11! = 39,916,800 -> X class
    try:
        _check_budgets(_args(allow_extreme=False), extreme, BundleConfig())
        assert False, "expected an X-class block without --allow-extreme"
    except BudgetError:
        pass
    intent_x = _check_budgets(_args(allow_extreme=False), extreme,
                              BundleConfig(unleash_initial_productivity_power=True))
    assert intent_x["unleash_initial_productivity_power"] is True
    assert intent_x["run_class"] == RunClass.EXTREME.value


def test_repeat_k_gt_1_capability_gate(monkeypatch):
    # Plan-1 (docs/24 §4): the K>1 gate PERMITS the verified local/metrics AND local/all paths on BOTH
    # executors when their probes advertise the required repeat capability, and fails closed on
    # disperse / nested / legacy-handoff, all before any run dir/stage. Probe parsing and real-artifact
    # execution have dedicated tests; this unit test must not require generated Executor artifacts.
    from bundle.config import ConfigError
    repeat = {"local_metrics": True, "local_all": True, "raw_sample_identity": True,
              "runtime_accounting": True, "max_k": 100}
    monkeypatch.setattr(
        "bundle.orchestrator.probe_python_executor_repeat_capability",
        lambda cfg: {"schema": "py_executor.capabilities/v1", "repeat": dict(repeat)},
    )
    monkeypatch.setattr(
        "bundle.orchestrator.probe_java_executor_repeat_capability",
        lambda cfg: {"schema": "java_executor.capabilities/v1", "repeat": dict(repeat)},
    )
    spec = fg.parse_spec(SMALL_SPEC, "repeat-gate")            # final = 18 (SMOKE)
    # Python local/metrics K>1 is executable: no raise, returns the budget intent.
    intent = _check_budgets(_args(), spec, BundleConfig(repeat_each_candidate=2))  # defaults: py/local/metrics
    assert intent["run_class"] == "S"
    # Python local/all (every sample a full verdict, V=C·K) is now executable too.
    assert _check_budgets(_args(), spec,
                          BundleConfig(repeat_each_candidate=2, repeat_scope="all"))["run_class"] == "S"
    # disperse is NOT capable (needs multi-instance dispatch) -> fail closed.
    try:
        _check_budgets(_args(), spec, BundleConfig(repeat_each_candidate=2, repeat_policy="disperse"))
        assert False, "disperse K>1 must be refused"
    except BudgetError as e:
        assert "REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY" in str(e)
    # The Java Executor is repeat-capable on BOTH local/metrics and local/all (advertises local_metrics
    # + local_all in -capabilities; MainWatch runs the K>1 fan-out / K verdict rows). Gate PERMITS both.
    a_java = _args()
    a_java.lang = "java"
    assert _check_budgets(a_java, spec, BundleConfig(repeat_each_candidate=2))["run_class"] == "S"
    assert _check_budgets(a_java, spec,
                          BundleConfig(repeat_each_candidate=2, repeat_scope="all"))["run_class"] == "S"
    # ...but Java disperse stays fail-closed (needs multi-instance dispatch).
    try:
        _check_budgets(a_java, spec, BundleConfig(repeat_each_candidate=2, repeat_policy="disperse"))
        assert False, "java disperse K>1 must be refused"
    except BudgetError as e:
        assert "REPEAT_K_REQUIRES_EXECUTOR_CAPABILITY" in str(e)
    # K=1 stays the unchanged legacy path (any policy/scope inactive).
    assert _check_budgets(_args(), spec, BundleConfig(repeat_each_candidate=1))["run_class"] == "S"
    assert _check_budgets(_args(), spec,
                          BundleConfig(repeat_each_candidate=1, repeat_policy="nested"))["run_class"] == "S"
    # nested K>1 without E is rejected by validate_repeat (named ConfigError) before the gate.
    try:
        _check_budgets(_args(), spec, BundleConfig(repeat_policy="nested", repeat_each_candidate=2))
        assert False, "nested K>1 without E must be rejected"
    except ConfigError as e:
        assert "repeat_environments" in str(e)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
