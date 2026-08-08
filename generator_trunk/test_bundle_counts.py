#!/usr/bin/env python3
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

"""Plan-1 Phase 2 acceptance tests for bundle.counts + BundleConfig.validate_repeat
(design contract docs/24 §3; Automation required tests #1-#4). Pure — materializes nothing.
Run: `python3 -m pytest test_bundle_counts.py -q` or `python3 test_bundle_counts.py`."""
from pathlib import Path

import fwgen as fg
from bundle.budgets import BudgetLimits, blocking_checks, evaluate_budgets
from bundle.config import BundleConfig, ConfigError
from bundle.counts import (
    CountPlan,
    RepeatPolicy,
    RepeatScope,
    count_plan,
    scale_cardinality_exact,
)
from bundle.resources import estimate_resources, format_resource_plan, resource_plan_to_dict

HERE = Path(__file__).resolve().parent

EXACT = fg.CardinalityMode.EXACT
BOUNDED = fg.CardinalityMode.BOUNDED
ESTIMATED = fg.CardinalityMode.ESTIMATED
UNKNOWN = fg.CardinalityMode.UNKNOWN


def _exact(n):
    return fg.CardinalityEstimate.exact(n, formula="C")


def _bounded(lo, hi):
    return fg.CardinalityEstimate.bounded(lower=lo, upper=hi, value=hi, formula="C")


def _estimated(v, lo, hi):
    return fg.CardinalityEstimate(mode=ESTIMATED, value=v, lower=lo, upper=hi, formula="C")


def _unknown():
    return fg.CardinalityEstimate.unknown(formula="C", reasons=("brace join is UNKNOWN until Core runs",))


# Expected (A, V, I, metric_only) per (policy, scope) for the documented C=2, K=3, E=2 case
# (docs/24 §3.2 worked example). V == canonical_rows == processed; I == V + metric_only.
_CELLS_C2_K3_E2 = {
    ("local", "all"): (2, 6, 6, 0),
    ("local", "metrics"): (2, 2, 6, 4),
    ("disperse", "all"): (6, 6, 6, 0),
    ("disperse", "metrics"): (6, 2, 6, 4),
    ("nested", "all"): (4, 12, 12, 0),
    ("nested", "metrics"): (4, 4, 12, 8),
}


# ----------------------------- Automation test #1 -------------------------------- #
def test_six_cells_closure_exact_c2_k3_e2():
    C = _exact(2)
    for (policy, scope), (a, v, i, mo) in _CELLS_C2_K3_E2.items():
        cp = count_plan(policy, scope, C, k=3, e=2)
        assert (cp.A.value, cp.V.value, cp.I.value, cp.metric_only_invocations.value) == (a, v, i, mo), \
            f"{policy}/{scope}: got {(cp.A.value, cp.V.value, cp.I.value, cp.metric_only_invocations.value)}"
        # closure: canonical_rows == processed == V (V is the only verdict count);
        # measurement_opportunities == I == V + metric_only.
        assert cp.I.value == cp.V.value + cp.metric_only_invocations.value
        # exact C ⇒ every field EXACT.
        for f in (cp.A, cp.V, cp.I, cp.metric_only_invocations):
            assert f.mode == EXACT
        assert cp.topology_inactive is False


def test_general_exact_factors():
    C = _exact(5)
    cp = count_plan("local", "metrics", C, k=4)          # A=C, V=C, I=C·4, mo=C·3
    assert (cp.A.value, cp.V.value, cp.I.value, cp.metric_only_invocations.value) == (5, 5, 20, 15)
    cp = count_plan("nested", "all", C, k=4, e=3)        # A=C·E, V=I=C·E·K, mo=0
    assert (cp.A.value, cp.V.value, cp.I.value, cp.metric_only_invocations.value) == (15, 60, 60, 0)


# ----------------------------- Automation test #2 -------------------------------- #
def test_k1_normalization_all_cells_with_stray_e():
    # K=1 ⇒ topology inactive ⇒ A=V=I=C and metric_only=0 for EVERY policy/scope,
    # even with a stray E>1 (which must NOT make nested plan C·E). docs/24 §3.0.
    C = _exact(7)
    for policy in ("local", "disperse", "nested"):
        for scope in ("all", "metrics"):
            cp = count_plan(policy, scope, C, k=1, e=3)
            assert cp.topology_inactive is True
            assert cp.e_effective == 1
            assert cp.A.value == 7 and cp.V.value == 7 and cp.I.value == 7
            assert cp.A.mode == EXACT and cp.V.mode == EXACT and cp.I.mode == EXACT
            # the DERIVED metric_only field is 0, not C (Automation Limitation 1).
            assert cp.metric_only_invocations.value == 0
            assert cp.metric_only_invocations.mode == EXACT


# ----------------------------- Automation test #3 -------------------------------- #
def _cfg(**kw):
    return BundleConfig(**kw)


def test_validation_defaults_and_enums():
    assert _cfg().validate_repeat() == ("local", "metrics", 1, 1)        # legacy default
    assert _cfg(repeat_each_candidate=4, repeat_policy="disperse",
               repeat_scope="all").validate_repeat() == ("disperse", "all", 4, 1)


def test_validation_k_must_be_ge_1():
    for bad in (0, -1):
        try:
            _cfg(repeat_each_candidate=bad).validate_repeat()
            assert False, f"K={bad} should be rejected"
        except ConfigError as e:
            assert "repeat_each_candidate" in str(e)


def test_validation_rejects_bad_enums():
    try:
        _cfg(repeat_policy="bogus").validate_repeat()
        assert False
    except ConfigError as e:
        assert "repeat_policy" in str(e)
    try:
        _cfg(repeat_scope="bogus").validate_repeat()
        assert False
    except ConfigError as e:
        assert "repeat_scope" in str(e)


def test_validation_nested_k_gt_1_requires_e():
    # nested + K>1 + E unset(0) → named error.
    try:
        _cfg(repeat_policy="nested", repeat_each_candidate=3).validate_repeat()
        assert False, "nested K>1 without E must be rejected"
    except ConfigError as e:
        assert "repeat_environments" in str(e) and "nested" in str(e)
    # nested + K>1 + E≥1 → e_effective=E.
    assert _cfg(repeat_policy="nested", repeat_each_candidate=3,
                repeat_environments=4).validate_repeat() == ("nested", "metrics", 3, 4)
    # E must be ≥0.
    try:
        _cfg(repeat_environments=-2).validate_repeat()
        assert False
    except ConfigError as e:
        assert "repeat_environments" in str(e)


def test_validation_local_disperse_ignore_e():
    # local/disperse never multiply by E: e_effective is 1 regardless of repeat_environments.
    assert _cfg(repeat_policy="local", repeat_each_candidate=5,
                repeat_environments=9).validate_repeat() == ("local", "metrics", 5, 1)
    assert _cfg(repeat_policy="disperse", repeat_each_candidate=5,
                repeat_environments=9).validate_repeat() == ("disperse", "metrics", 5, 1)
    # and count_plan ignores E for them too (e=99 gives the same counts as e=1).
    C = _exact(5)
    for policy in ("local", "disperse"):
        for scope in ("all", "metrics"):
            a = count_plan(policy, scope, C, k=4, e=1)
            b = count_plan(policy, scope, C, k=4, e=99)
            assert (a.A.value, a.V.value, a.I.value) == (b.A.value, b.V.value, b.I.value)


def test_validation_nested_k1_e_unset_ok():
    # nested at K=1 with E unset is fine — topology is inactive, e_effective=1.
    assert _cfg(repeat_policy="nested", repeat_each_candidate=1).validate_repeat() == ("nested", "metrics", 1, 1)


# ----------------------------- Automation test #4 -------------------------------- #
def test_exact_factor_scaler_preserves_mode():
    # factor 0 collapses any mode to a proven EXACT 0 (the metric_only=0 cells).
    z = scale_cardinality_exact(_unknown(), 0, formula="0")
    assert z.mode == EXACT and z.value == 0
    # factor ≥1 preserves the mode and multiplies present numeric fields.
    e = scale_cardinality_exact(_exact(6), 3, formula="x")
    assert e.mode == EXACT and (e.value, e.lower, e.upper) == (18, 18, 18)
    b = scale_cardinality_exact(_bounded(4, 10), 3, formula="x")
    assert b.mode == BOUNDED and (b.lower, b.upper, b.value) == (12, 30, 30)
    s = scale_cardinality_exact(_estimated(8, 4, 12), 3, formula="x")
    assert s.mode == ESTIMATED and (s.value, s.lower, s.upper) == (24, 12, 36)
    u = scale_cardinality_exact(_unknown(), 3, formula="x")
    assert u.mode == UNKNOWN and u.value is None


def test_mode_propagation_through_count_plan():
    # EXACT stays EXACT.
    cp = count_plan("local", "metrics", _exact(6), k=3)
    assert all(f.mode == EXACT for f in (cp.A, cp.V, cp.I, cp.metric_only_invocations))
    assert (cp.V.value, cp.I.value, cp.metric_only_invocations.value) == (6, 18, 12)

    # BOUNDED stays BOUNDED (bounds multiply componentwise).
    cp = count_plan("disperse", "all", _bounded(4, 10), k=3)
    assert cp.V.mode == BOUNDED and (cp.V.lower, cp.V.upper) == (12, 30)

    # ESTIMATED stays ESTIMATED — never mislabeled BOUNDED (the key Limitation-2 assertion).
    cp = count_plan("nested", "all", _estimated(8, 4, 12), k=2, e=2)
    assert cp.V.mode == ESTIMATED and (cp.V.value, cp.V.lower, cp.V.upper) == (32, 16, 48)
    assert cp.I.mode == ESTIMATED

    # UNKNOWN stays UNKNOWN and never becomes 0; metric_only via a DIRECT formula stays
    # UNKNOWN too (not 0, and not an ill-defined UNKNOWN−UNKNOWN subtraction).
    cp = count_plan("local", "metrics", _unknown(), k=3)
    assert cp.V.mode == UNKNOWN and cp.V.value is None
    assert cp.I.mode == UNKNOWN and cp.I.value is None
    assert cp.metric_only_invocations.mode == UNKNOWN and cp.metric_only_invocations.value is None
    # but a structurally-zero metric_only (all-scope) is a proven EXACT 0 even for UNKNOWN C.
    cp = count_plan("local", "all", _unknown(), k=3)
    assert cp.metric_only_invocations.mode == EXACT and cp.metric_only_invocations.value == 0


def test_to_dict_roundtrip_is_jsonable():
    import json
    cp = count_plan("nested", "metrics", _exact(2), k=3, e=2)
    d = cp.to_dict()
    json.dumps(d)  # must not raise
    assert d["policy"] == "nested" and d["k"] == 3 and d["e_effective"] == 2
    assert d["full_verdict_invocations"]["value"] == 4
    assert d["measurement_opportunities"]["value"] == 12


# ------------------- Automation tests #5, #6 (resources / disk budget) ----------- #
_RES_SPEC = {
    "slots": [
        {"sheet": "A", "values": ["a1", "a2", "a3"]},
        {"sheet": "B", "values": ["b1", "b2"]},
        {"sheet": "C", "values": ["c1", "c2", "c3"]},
    ],
}  # Cartesian default ⇒ final candidate count C = 18 (EXACT)


def _plan18():
    return fg.spec_cardinality_plan(fg.parse_spec(_RES_SPEC, "res-spec"))


def test_resources_scale_off_V_and_I_and_keep_C_distinct():
    plan = _plan18()
    cp = count_plan("nested", "metrics", plan.final, k=2, e=2)   # V = C·E = 36, I = C·E·K = 72
    assert (cp.V.value, cp.I.value) == (36, 72)
    rp = estimate_resources(plan, count_plan=cp)
    d = resource_plan_to_dict(rp)
    # distinct C and I are BOTH preserved (Automation #5).
    assert d["final_count"] == 18 and d["execution_count"] == 72
    # Results-DB bytes scale off V (verdict rows), the metric artifact off I (opportunities);
    # I>V with equal per-row bytes ⇒ the metric artifact estimate is strictly larger, proving
    # Results-DB bytes are V-only (not I).
    assert d["metric_artifact_bytes"] is not None
    assert rp.metric_artifact_bytes.value > rp.results_db_bytes.value
    rendered = format_resource_plan(rp)
    assert "execution count I = 72" in rendered and "metric artifact bytes" in rendered


def test_resources_k1_is_legacy_identical():
    plan = _plan18()
    cp = count_plan("nested", "all", plan.final, k=1, e=3)       # K=1 ⇒ topology inactive
    rp_k1 = estimate_resources(plan, count_plan=cp)
    rp_legacy = estimate_resources(plan)                         # no count plan
    assert resource_plan_to_dict(rp_k1) == resource_plan_to_dict(rp_legacy)
    assert rp_k1.metric_artifact_bytes is None and rp_k1.execution_count is None


def test_disk_budget_blocks_on_metric_artifact_growth():
    plan = _plan18()
    cp = count_plan("nested", "metrics", plan.final, k=2, e=2)
    rp = estimate_resources(plan, count_plan=cp)
    no_metric_sum = rp.core_db_bytes.upper + rp.results_db_bytes.upper + rp.candidate_source_bytes.upper
    metric = rp.metric_artifact_bytes.upper
    # a ceiling ABOVE the legacy Core+Results+sources sum but BELOW the with-metric sum must
    # BLOCK — proving the metric artifact is folded into the disk ceiling (Automation #6).
    checks = evaluate_budgets(plan, rp, BudgetLimits(disk_bytes=no_metric_sum + metric // 2))
    assert "disk_bytes" in {c.dimension for c in blocking_checks(checks)}
    # a ceiling above the full with-metric sum does NOT block on disk.
    checks_ok = evaluate_budgets(plan, rp, BudgetLimits(disk_bytes=no_metric_sum + metric + 1))
    assert "disk_bytes" not in {c.dimension for c in blocking_checks(checks_ok)}


# ------------------- Automation #29 finding 2 (defensive count_plan validation) -- #
def test_count_plan_rejects_non_int_or_bool_k():
    C = _exact(10)
    for bad in (1.5, True, "3", 0, -1):
        try:
            count_plan("local", "metrics", C, k=bad)
            assert False, f"K={bad!r} must be rejected"
        except ValueError:
            pass


def test_count_plan_validates_e_and_requires_nested_e():
    C = _exact(10)
    # bad E values are rejected when given (non-bool int >= 1).
    for bad in (0, -1, 1.5, True):
        try:
            count_plan("nested", "all", C, k=2, e=bad)
            assert False, f"E={bad!r} must be rejected"
        except ValueError:
            pass
    # nested K>1 with E omitted must NOT silently default to 1.
    try:
        count_plan("nested", "all", C, k=2)
        assert False, "nested K>1 without explicit E must be rejected"
    except ValueError as e:
        assert "nested" in str(e) and "E" in str(e)
    # local/disperse never require E and ignore it (None ok).
    assert count_plan("local", "metrics", C, k=2).I.value == 20
    assert count_plan("disperse", "all", C, k=2).V.value == 20


# ------------------- Automation #29 finding 3 (preserve I confidence) ------------ #
def test_resources_preserve_unknown_execution_count():
    plan = _plan18()
    cp = count_plan("local", "metrics", _unknown(), k=3)        # I is UNKNOWN
    assert cp.I.mode == UNKNOWN and cp.I.value is None
    rp = estimate_resources(plan, count_plan=cp)
    # the scalar collapses to None, but the estimate stays UNKNOWN — distinct from inactive K=1.
    assert rp.execution_count is None
    assert rp.execution_count_estimate is not None and rp.execution_count_estimate.mode == UNKNOWN
    d = resource_plan_to_dict(rp)
    assert d["execution_count_estimate"] is not None and d["execution_count_estimate"]["mode"] == "UNKNOWN"
    assert "execution count I = UNKNOWN" in format_resource_plan(rp)
    # inactive K=1 has NO execution_count_estimate (the disambiguation Automation asked for).
    rp_k1 = estimate_resources(plan, count_plan=count_plan("local", "metrics", plan.final, k=1))
    assert rp_k1.execution_count_estimate is None


# ------------------- Automation #29 finding 1 (plan-only budget evaluation) ------ #
def test_cmd_plan_evaluates_repeat_budget_and_blocks_on_metric_artifact():
    import contextlib
    import io
    import json
    import tempfile
    from types import SimpleNamespace

    from bundle.cli import _load_one_spec, cmd_plan
    from bundle.resources import DEFAULT_PER_CANDIDATE_SECONDS, ResourceThresholds

    spec_dir = HERE / "usecases" / "perf_opt"
    spec, _toml = _load_one_spec(spec_dir)
    plan = fg.spec_cardinality_plan(spec)
    rp = estimate_resources(plan, count_plan=count_plan("local", "metrics", plan.final, k=8))
    legacy = rp.core_db_bytes.upper + rp.results_db_bytes.upper + rp.candidate_source_bytes.upper
    metric = rp.metric_artifact_bytes.upper
    assert metric > 0
    ceiling = legacy + metric // 2          # ABOVE legacy Core+Results+sources, BELOW +metric-artifact

    th = ResourceThresholds()
    out = tempfile.mkdtemp()
    a = SimpleNamespace(
        spec_dir=spec_dir, out=out, config_file="",
        class_smoke_max=th.smoke_max, class_bounded_max=th.bounded_max, class_large_max=th.large_max,
        template_sample_bytes=0, per_candidate_seconds_min=DEFAULT_PER_CANDIDATE_SECONDS[0],
        per_candidate_seconds_max=DEFAULT_PER_CANDIDATE_SECONDS[1], cost_per_candidate=None,
        repeat=8, repeat_policy="local", repeat_scope="metrics", budget_disk_bytes=ceiling,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_plan(a)
    output = buf.getvalue()
    assert "BUDGET BLOCKING" in output and "disk_bytes" in output
    d = json.loads((Path(out) / "plan.json").read_text())
    assert d["budget_blocking"] == ["disk_bytes"]
    assert any(c["dimension"] == "disk_bytes" and c["severity"] == "BLOCKING" for c in d["budget_checks"])
    # the block is SPECIFICALLY metric-artifact growth: legacy Core+Results+sources is under the ceiling.
    assert legacy <= ceiling < legacy + metric


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    sys.exit(1 if failures else 0)
