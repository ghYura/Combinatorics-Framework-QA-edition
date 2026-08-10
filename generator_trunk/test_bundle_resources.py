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

"""Targeted tests for bundle.resources (STEP 11): run-class thresholds and
resource estimates derived from a SpecCardinalityPlan, without materializing
or running anything (run: `python3 test_bundle_resources.py`)."""
import json
from pathlib import Path

import fwgen as fg
from bundle.resources import (
    CardinalityMode,
    ResourceThresholds,
    RunClass,
    estimate_resources,
    format_resource_plan,
    resource_plan_to_dict,
)

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


def test_thresholds_classify_by_final_count_and_are_configurable():
    t = ResourceThresholds(smoke_max=100, bounded_max=1_000, large_max=100_000)
    assert t.classify(50) == RunClass.SMOKE
    assert t.classify(100) == RunClass.SMOKE
    assert t.classify(101) == RunClass.BOUNDED
    assert t.classify(1_000) == RunClass.BOUNDED
    assert t.classify(1_001) == RunClass.LARGE
    assert t.classify(100_001) == RunClass.EXTREME
    # an un-sizable (UNKNOWN) final count must classify as the worst case, not "small"
    assert t.classify(None) == RunClass.EXTREME


def test_288_case_classified_per_configured_thresholds():
    # 18 = 3*2*3 stands in for the bounded reference shape; tight thresholds
    # push it to B, loose thresholds keep it S — "S/B according to configured
    # thresholds" (acceptance criteria), exercised both ways on the same spec.
    spec = fg.parse_spec(SMALL_SPEC, "small")
    plan = fg.spec_cardinality_plan(spec)
    assert plan.final.value == 18

    loose = estimate_resources(plan, thresholds=ResourceThresholds(smoke_max=100))
    assert loose.run_class == RunClass.SMOKE

    tight = estimate_resources(plan, thresholds=ResourceThresholds(smoke_max=10, bounded_max=100))
    assert tight.run_class == RunClass.BOUNDED


def test_synthetic_large_spec_classified_without_materialization():
    # 9! and 13! are sized purely from the closed-form EXACT cardinality
    # formula — never by generating/counting actual rows.
    large = estimate_resources(fg.spec_cardinality_plan(_permut_spec("big-l", 9)))
    assert large.final_count == 362_880
    assert large.run_class == RunClass.LARGE

    extreme = estimate_resources(fg.spec_cardinality_plan(_permut_spec("big-x", 13)))
    assert extreme.final_count == 6_227_020_800
    assert extreme.run_class == RunClass.EXTREME


def test_unknown_final_count_never_collapses_to_zero_cost():
    M = CardinalityMode
    # both brace operands excluded -> mandatory/final collapse to UNKNOWN
    # (see fwgen STEP-9 fix); every resource dimension must say UNKNOWN too,
    # never silently report 0.
    spec = fg.parse_spec({
        "slots": [{"sheet": "A", "values": ["a1", "a2"], "flags": ["FW_Exclude"]},
                  {"sheet": "B", "values": ["b1", "b2"], "flags": ["FW_Exclude"]},
                  {"sheet": "JOINED", "values": [" x"]}],
        "seq_extra": [["JOINED", "FW_Reuse", "FW_(,,A,,B,,,,M:N)"]],
    }, "brace-resources")
    plan = fg.spec_cardinality_plan(spec)
    assert plan.final.mode == M.UNKNOWN

    rp = estimate_resources(plan)
    assert rp.run_class == RunClass.EXTREME      # unsizable -> worst case, never "small"
    for est in (rp.core_db_bytes, rp.results_db_bytes, rp.candidate_source_bytes,
                rp.inode_count, rp.request_count, rp.duration_seconds):
        assert est.mode == M.UNKNOWN
        assert est.value is None                 # UNKNOWN, not a fabricated 0
        assert est.reasons
        assert est.assumptions, est               # STEP 11 action 4 — UNKNOWN is not exempt either
    assert rp.dominant == "unknown"


REFERENCE_SPEC_TOML = Path(__file__).resolve().parent / "tryout_own/spec/secure_pipeline.toml"


def test_actual_288_reference_spec_resource_plan():
    # The flagship secure-pipeline reference (STEP 7's bounded compatibility
    # run): Core 96 -> sieve 72 -> ×4 optional = 288 candidates end-to-end.
    # The static plan can only PROVE the pre-sieve shape (mandatory=96 EXACT,
    # optional×4 EXACT) and bound the rest — exactly the STEP-9 confidence
    # discipline `bundle plan` is built to surface, never silently sharpened
    # into a fabricated "288".
    assert REFERENCE_SPEC_TOML.exists(), REFERENCE_SPEC_TOML
    spec = fg.load_spec(REFERENCE_SPEC_TOML)
    plan = fg.spec_cardinality_plan(spec)
    assert plan.mandatory.value == 96 and plan.mandatory.mode == CardinalityMode.EXACT
    assert plan.optional_multiplier.value == 4 and plan.optional_multiplier.mode == CardinalityMode.EXACT
    assert plan.post_sieve.mode == CardinalityMode.BOUNDED and plan.post_sieve.lower == 0 and plan.post_sieve.upper == 96
    # mandatory(96 exact) × optional(×4 exact) post-sieve narrows to 72*4=288 at
    # runtime — but statically only the upper bound 96*4=384 is provable.
    assert plan.final.mode == CardinalityMode.BOUNDED
    assert plan.final.lower == 0 and plan.final.upper == 384
    # the actual reference figure (288) sits inside the provable [0, 384] range —
    # the static estimate is honest about not being able to sharpen it further
    # without running the sieve.
    assert plan.final.lower <= 288 <= plan.final.upper

    # configured run-class thresholds classify this reference shape as S or B
    # (acceptance criteria: "288-case classified S/B according to configured
    # thresholds") — exercised both ways on the SAME spec.
    loose = estimate_resources(plan, thresholds=ResourceThresholds(smoke_max=500))
    assert loose.run_class == RunClass.SMOKE
    tight = estimate_resources(plan, thresholds=ResourceThresholds(smoke_max=200, bounded_max=1_000))
    assert tight.run_class == RunClass.BOUNDED

    # configurable per-candidate duration (the gap this revision closes): the
    # SAME spec/plan, scaled by two different operator-supplied cost ranges,
    # produces correspondingly different (and clearly assumption-tagged)
    # execution-duration estimates — driven by `final.upper` = 384.
    cheap = estimate_resources(plan, per_candidate_seconds=(0.01, 0.02))
    pricey = estimate_resources(plan, per_candidate_seconds=(5.0, 10.0))
    assert cheap.duration_seconds.mode == pricey.duration_seconds.mode == CardinalityMode.ESTIMATED
    assert cheap.duration_seconds.upper == int(384 * 0.02)
    assert pricey.duration_seconds.upper == int(384 * 10.0)
    assert cheap.duration_seconds.upper < pricey.duration_seconds.upper
    assert any("0.01" in a and "0.02" in a for a in cheap.duration_seconds.assumptions)
    assert any("5" in a and "10" in a for a in pricey.duration_seconds.assumptions)


def test_resource_plan_estimates_are_estimated_with_assumptions_and_never_zero_for_nonzero_count():
    spec = fg.parse_spec(SMALL_SPEC, "small-est")
    plan = fg.spec_cardinality_plan(spec)
    rp = estimate_resources(plan, template_sample_bytes=1234, cost_per_candidate=2.5)

    for est in (rp.core_db_bytes, rp.results_db_bytes, rp.candidate_source_bytes,
                rp.inode_count, rp.request_count, rp.duration_seconds, rp.monetary_cost):
        assert est.mode == CardinalityMode.ESTIMATED   # never EXACT — the per-unit cost is an assumption
        assert est.value is not None and est.value > 0
        assert est.assumptions, est                    # STEP 11 action 4: every estimate has assumptions

    # a real template sample tightens candidate-source bytes to a point estimate
    assert rp.candidate_source_bytes.lower == rp.candidate_source_bytes.upper == 18 * 1234
    assert any("template sample" in a for a in rp.candidate_source_bytes.assumptions)
    # monetary cost only appears when a price is configured
    assert rp.monetary_cost.value == int(18 * 2.5)
    assert rp.dominant != "unknown"


def test_resource_plan_json_and_human_projections_round_trip():
    spec = fg.parse_spec(SMALL_SPEC, "small-fmt")
    plan = fg.spec_cardinality_plan(spec)
    rp = estimate_resources(plan)

    d = resource_plan_to_dict(rp)
    assert json.loads(json.dumps(d)) == d
    assert d["run_class"] == "S"
    for key in ("core_db_bytes", "results_db_bytes", "candidate_source_bytes",
                "inode_count", "request_count", "duration_seconds", "dominant", "dominant_reason"):
        assert key in d
    assert d["monetary_cost"] is None             # no price configured

    rendered = format_resource_plan(rp)
    for needle in ("run class:", "Core DB bytes", "Results DB bytes", "candidate source bytes",
                   "loose-file inode count", "external request count", "execution duration",
                   "dominant resource:"):
        assert needle in rendered


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nALL {len(fns)} TESTS PASSED")
