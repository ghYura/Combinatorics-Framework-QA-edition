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
# Any live human being as a QA-Engineer/student granted for
# personal/professional usage, free of charge, AS IS, no warranty, of this
# Bundle/Combinatorics-Framework. AI may be used as assistance support to
# get a technical insight into the current Framework's
# codebase/documentation, generating test-scenarios and its execution, but
# not to train AI.
#
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Plan-1 repeat (Python local/metrics K>1) runtime-wiring tests (Automation #37 steps 1-4): the count
invariants (processed==V, results_v2 attempted==V, metric_rows+missing==I) and the executor-stage
repeat flags. Pure — no DB, no subprocess. Run: python3 -m pytest test_bundle_repeat_runtime.py -q"""
from bundle import invariants
from bundle.config import BundleConfig
from bundle.stages import _repeat_executor_flags


def test_repeat_processed_eq_verdicts():
    assert invariants.repeat_processed_eq_verdicts(18, 18).passed
    bad = invariants.repeat_processed_eq_verdicts(36, 18)
    assert not bad.passed and bad.severity == invariants.CRITICAL and bad.expected == 18


def test_repeat_results_v2_attempted_eq_verdicts():
    assert invariants.repeat_results_v2_attempted_eq_verdicts(18, 18).passed
    assert not invariants.repeat_results_v2_attempted_eq_verdicts(54, 18).passed


def test_repeat_metric_rows_plus_missing_eq_opportunities():
    # I = C*K = 18*3 = 54; every opportunity is an emitted row or an explicit missing measurement.
    assert invariants.repeat_metric_rows_plus_missing_eq_opportunities(54, 0, 54).passed
    assert invariants.repeat_metric_rows_plus_missing_eq_opportunities(50, 4, 54).passed
    bad = invariants.repeat_metric_rows_plus_missing_eq_opportunities(50, 0, 54)
    assert not bad.passed and bad.actual == 50 and bad.expected == 54


def test_repeat_executor_flags_only_for_local_metrics_or_all_k_gt_1():
    # the verified capability paths -> flags present (scope threaded through).
    flags = _repeat_executor_flags(BundleConfig(repeat_each_candidate=3), run_id="r1")
    assert flags == ["--repeat", "3", "--repeatPolicy", "local", "--repeatScope", "metrics",
                     "--envId", "local:r1"]
    # local/all (every sample a full verdict) is also capable now -> flags present with scope=all.
    assert _repeat_executor_flags(BundleConfig(repeat_each_candidate=3, repeat_scope="all"), run_id="r1") == \
        ["--repeat", "3", "--repeatPolicy", "local", "--repeatScope", "all", "--envId", "local:r1"]
    # K=1 -> no flags (the unchanged legacy single-measurement path).
    assert _repeat_executor_flags(BundleConfig(repeat_each_candidate=1)) == []
    # non-capable modes -> no flags (defensive; the launcher gate already blocks these pre-launch).
    assert _repeat_executor_flags(BundleConfig(repeat_each_candidate=3, repeat_policy="disperse")) == []
    # run_id omitted -> a stable default env id.
    assert "--envId" in _repeat_executor_flags(BundleConfig(repeat_each_candidate=2))


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} PASSED")
    sys.exit(0)
