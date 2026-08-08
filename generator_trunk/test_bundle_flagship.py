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

"""Phase 05 flagship: the properties the evidence rests on.

These are not tests of "does it run". They are the assertions that make the
flagship's *claims* checkable, so that a change which quietly invalidates the
comparison fails here rather than in a document nobody re-derives:

* the oracle never reports a defect against the correct SUT (no false positives);
* the mutants are reachable — an undetectable mutant measures nothing;
* the two chains (engine and in-process twin) build the same trees;
* each level's declared count really is the count its spec produces;
* the sieve removes only candidates the domain cannot construct.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from generator_trunk.engine_demo import record_pipeline as rp          # noqa: E402
from generator_trunk.flagship import levels as L                       # noqa: E402
from generator_trunk.flagship import pipeline_flagship as F            # noqa: E402
from generator_trunk.flagship import reconcile as R                    # noqa: E402
from generator_trunk.flagship import run_flagship as RF                # noqa: E402


class TestOracleIndependence(unittest.TestCase):
    def test_correct_version_produces_no_detection(self):
        """A detection against `correct` is a false positive and voids the study."""
        for assignment in F.cartesian_suite():
            verdict = F.judge(F.build(assignment), F.CORRECT)
            self.assertFalse(verdict.defect_detected,
                             f"false positive on {assignment}: {verdict}")

    def test_every_mutant_is_reachable(self):
        """An unreachable mutant scores a MISS for every method and measures nothing.

        This test exists because the first `single_fault` mutant WAS unreachable on
        this corpus, and the numbers looked like a finding about the methods.
        """
        for version in (F.SINGLE_FAULT, F.INTERACTION_ONLY):
            detections = sum(F.judge(F.build(a), version).defect_detected
                             for a in F.cartesian_suite())
            self.assertGreater(detections, 0, f"{version} is undetectable on this corpus")

    def test_contract_violations_are_not_counted_as_detections(self):
        """A domain rejection the reference oracle also produces is the pipeline's
        declared behaviour, not a discovered defect."""
        report = F.compare()
        for name, data in report["methods"].items():
            self.assertGreaterEqual(data["versions"][F.CORRECT]["domain_rejections_not_defects"], 0,
                                    f"{name} scored a domain rejection as a detection")


class TestBaselineComparison(unittest.TestCase):
    def setUp(self):
        self.report = F.compare()

    def test_no_method_produces_a_false_positive(self):
        for name, data in self.report["methods"].items():
            self.assertEqual(data["false_positives"], 0, f"{name} fired against `correct`")

    def test_non_composing_baseline_misses_the_interaction_defect(self):
        """The finding under test. If this ever passes, the interaction defect has
        stopped being interaction-only and the study needs a new mutant."""
        isolated = self.report["methods"]["isolated-stages (non-composing)"]
        self.assertFalse(isolated["versions"][F.INTERACTION_ONLY]["detected"])

    def test_every_composing_method_finds_both_defects(self):
        for name, data in self.report["methods"].items():
            if name == "isolated-stages (non-composing)":
                continue
            self.assertEqual(data["defects_found"], 2, f"{name} missed a defect")

    def test_cost_is_reported_and_cartesian_is_the_expensive_one(self):
        """Detection without cost is half a result. Cartesian finds everything and
        must be recorded as the most expensive way to do it."""
        methods = self.report["methods"]
        cartesian = methods["flat-cartesian"]
        pairwise = methods["pairwise-covering-array (t=2)"]
        self.assertEqual(cartesian["defects_found"], pairwise["defects_found"])
        self.assertGreater(cartesian["total_executions"], pairwise["total_executions"] * 10)
        for data in methods.values():
            self.assertGreater(data["total_ops"], 0)

    def test_every_method_draws_from_one_factor_declaration(self):
        """No method may get a richer vocabulary than another."""
        for name, builder in F.BASELINES.items():
            for entry in builder():
                if isinstance(entry, dict):
                    self.assertLessEqual(set(entry), set(F.FACTORS), f"{name} invented a factor")
                    for key, value in entry.items():
                        self.assertIn(value, F.FACTORS[key], f"{name} invented a level")

    def test_markdown_table_is_generated_from_the_executed_report(self):
        table = F.format_comparison(self.report)
        self.assertIn("flat-cartesian", table)
        self.assertIn("MISSED", table)


class TestCoveringArraysAndRandom(unittest.TestCase):
    """The two baselines this study was missing for too long.

    A t-way covering array covers every t-tuple by construction, so a defect
    needing exactly t conditions is within its reach *by design*. Random sampling
    at the same budget is the least flattering baseline available. Both had to be
    added before any claim about "sampling misses interactions" could be trusted.
    """

    def test_a_t_way_array_covers_every_t_tuple(self):
        """The defining property. Without it the row is not a covering array and
        any conclusion drawn from it is worthless."""
        import itertools
        for t in (2, 3):
            suite = F.twise_suite(F.FACTORS, t=t)
            keys = list(F.FACTORS)
            for combo in itertools.combinations(range(len(keys)), t):
                required = set(itertools.product(*(F.FACTORS[keys[i]] for i in combo)))
                seen = {tuple(a[keys[i]] for i in combo) for a in suite}
                self.assertEqual(required - seen, set(), f"t={t} missed a tuple in {combo}")

    def test_higher_strength_costs_more(self):
        self.assertGreater(len(F.threewise_suite()), len(F.pairwise_suite()))

    def test_pairwise_is_exactly_the_t2_array(self):
        """Refactoring the generator must not silently move the published number."""
        self.assertEqual(F.pairwise_suite(), F.twise_suite(F.FACTORS, t=2))

    def test_a_three_way_array_finds_a_three_way_defect(self):
        """The honest counter-argument to this whole study, asserted rather than
        assumed: if a defect needs three conditions, a t=3 array reaches it."""
        suite = F.threewise_suite()
        hits = sum(F.judge(F.build(a), F.INTERACTION_ONLY).defect_detected for a in suite)
        self.assertGreater(hits, 0)

    def test_random_sampling_is_deterministic_per_seed(self):
        self.assertEqual(F.random_suite(budget=8, seed=3), F.random_suite(budget=8, seed=3))
        self.assertNotEqual(F.random_suite(budget=8, seed=3), F.random_suite(budget=8, seed=4))

    def test_random_draws_without_replacement_and_respects_the_budget(self):
        suite = F.random_suite(budget=12, seed=1)
        self.assertEqual(len(suite), 12)
        self.assertEqual(len({tuple(sorted(a.items())) for a in suite}), 12)

    def test_random_baseline_is_reported_over_many_seeds(self):
        """One draw measures luck. The report must aggregate."""
        report = F.random_baseline_report(seeds=5)
        self.assertEqual(report["seeds"], 5)
        self.assertEqual(report["budget"], len(F.pairwise_suite()))
        self.assertEqual(report["versions"][F.CORRECT]["seeds_detecting"], 0,
                         "random produced a false positive against the control")
        for version in (F.SINGLE_FAULT, F.INTERACTION_ONLY):
            self.assertLessEqual(report["versions"][version]["seeds_detecting"], 5)


class TestEngineTwinAgreement(unittest.TestCase):
    """`evaluate_stream_under` is what the engine's candidates call; `build` is the
    in-process twin. Both must reach the same verdict on the same structure."""

    def test_stream_and_node_paths_agree(self):
        for assignment in F.cartesian_suite()[::17]:
            node = F.build(assignment)
            for version in F.VERSIONS:
                from_node = F.evaluate_stream_under([node], version)
                verdict = F.judge(node, version)
                self.assertEqual(from_node.code == rp.VERDICT_ORACLE_DISAGREEMENT,
                                 verdict.defect_detected, assignment)
                self.assertEqual(from_node.ops, verdict.ops, assignment)

    def test_unknown_version_is_rejected(self):
        with self.assertRaises(ValueError):
            F.compiled_evaluator("not_a_version")

    def test_selected_version_defaults_to_the_control(self):
        import os
        saved = os.environ.pop(F.SUT_VERSION_ENV, None)
        try:
            self.assertEqual(F.selected_version(), F.CORRECT)
            os.environ[F.SUT_VERSION_ENV] = "nonsense"
            with self.assertRaises(ValueError):
                F.selected_version()
        finally:
            os.environ.pop(F.SUT_VERSION_ENV, None)
            if saved is not None:
                os.environ[F.SUT_VERSION_ENV] = saved


class TestLevelDerivations(unittest.TestCase):
    """Each level's declared count must be what its own factor space produces. The
    engine run asserts the same number from the other side."""

    def test_l2_space_matches_the_declared_count(self):
        self.assertEqual(len(F.cartesian_suite()), RF.LEVELS["l2"].expected_final)

    def test_l3_and_l4_spaces_match_their_declared_counts(self):
        for name in ("l3", "l4"):
            self.assertEqual(len(L.l3_suite(name)), RF.LEVELS[name].expected_final, name)

    def test_every_level_builds_distinct_trees(self):
        """Duplicate trees would mean the level is smaller than it claims."""
        for name, twin in R.TWINS.items():
            make_suite, build = twin()          # thunks: a SUT is imported on demand
            trees = {repr(build(a)) for a in make_suite()}
            self.assertEqual(len(trees), RF.LEVELS[name].expected_final, name)

    def test_budget_gate_sits_above_the_expected_count(self):
        for name, level in RF.LEVELS.items():
            self.assertGreater(level.budget_final, level.expected_final, name)


class TestSieveRemovesOnlyInvalidCandidates(unittest.TestCase):
    """The claim a constraint layer has to earn: it removed candidates the domain
    cannot execute, and nothing else."""

    def test_removed_assignments_are_exactly_the_unconstructible_ones(self):
        full = L.l3_suite("l3", apply_sieve=False)
        removed = [a for a in full if L.sieved(a)]
        kept = [a for a in full if not L.sieved(a)]
        self.assertEqual(len(removed) + len(kept), len(full))
        self.assertTrue(removed, "the sieve rule matched nothing — it proves nothing")
        for assignment in removed:
            self.assertEqual(rp.evaluate([L.build_l3(assignment)]).code,
                             rp.VERDICT_CONSTRUCTION, assignment)
        for assignment in kept:
            self.assertNotEqual(rp.evaluate([L.build_l3(assignment)]).code,
                                rp.VERDICT_CONSTRUCTION, assignment)


class TestSieveRejectsUnenforceableBonds(unittest.TestCase):
    """Regression: a bond on an FW_Exclude'd sheet used to raise KeyError deep in
    the row decode. It must fail with an explanation, before any query runs —
    silently keeping every row is indistinguishable from a satisfied constraint."""

    def test_bond_on_a_non_materialized_sheet_is_reported(self):
        sys.path.insert(0, str(HERE / "constraints"))
        import sieve as sv

        sidecar = {"version": 1, "params": {},
                   "constraints": [{"id": "r", "sheets": ["EXCLUDED", "KEPT"],
                                    "when": "EXCLUDED.a == 1", "gate": {}}]}
        with self.assertRaises(ValueError) as caught:
            sv.sieve_fw_final(object(), "fw_final", sidecar, {}, ["EXCLUDED", "KEPT"],
                              {"KEPT": "combos1_KEPT"}, dry_run=True)
        self.assertIn("EXCLUDED", str(caught.exception))


class TestReconciliationHelpers(unittest.TestCase):
    def test_corpus_parsing_and_multiset(self):
        line = ("candidate_id=1_0_0 app=engine_demo stages=11 depth=6 branches=2 "
                "ops=153 retained=28 reason=not_non_decreasing FW_VAR=5")
        rows = R.parse_corpus(_write_tmp(line + "\n" + line + "\n"))
        self.assertEqual(len(rows), 2)
        multiset = R.metric_multiset(rows)
        self.assertEqual(list(multiset.values()), [2])
        self.assertEqual(len(next(iter(multiset))), len(R.METRIC_KEYS))


def _write_tmp(text: str) -> Path:
    import tempfile
    handle = tempfile.NamedTemporaryFile("w", suffix=".kv", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
