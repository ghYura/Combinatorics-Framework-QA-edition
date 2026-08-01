"""Second flagship SUT: the properties its half of the evidence rests on.

The first flagship's tests check that one study is sound. These check the thing
that makes a *second* study worth running at all — that it is genuinely a
different experiment, and that the claims drawn from it are falsifiable:

* the interaction defect really does need all three conditions at once (if this
  ever passes with two, the "interaction-only" label is wrong and the comparison
  means something else);
* the single-factor defect really is single-factor;
* the two defects are caught by *different* oracle layers, so neither result is
  an artefact of one check;
* both mutants are reachable — the trap that has now bitten this work twice;
* the naive replay oracle shares no code with the implementation it judges.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from generator_trunk.engine_demo import txn_store as ts                 # noqa: E402
from generator_trunk.flagship import pipeline_flagship as F             # noqa: E402
from generator_trunk.flagship import run_flagship as RF                 # noqa: E402
from generator_trunk.flagship import store_flagship as S                # noqa: E402

#: The three conditions the interaction defect is claimed to require. Stated here
#: as data so the test can check each one is INDIVIDUALLY necessary, not merely
#: that the detecting candidates happen to have them.
REQUIRED = {"nesting": "repeated", "outcome": "rollback", "side": "put_b"}


def _suite():
    return F.cartesian_suite(S.FACTORS)


def _detecting(version):
    return [a for a in _suite() if S.judge(S.build(a), version).defect_detected]


class TestOracleIndependence(unittest.TestCase):
    def test_correct_version_produces_no_detection(self):
        """A detection against `correct` is a false positive and voids the study."""
        for assignment in _suite():
            verdict = S.judge(S.build(assignment), S.CORRECT)
            self.assertFalse(verdict.defect_detected, f"false positive on {assignment}")

    def test_every_mutant_is_reachable(self):
        """An unreachable mutant scores a MISS for every method and measures nothing.

        This has now caught two different unreachable mutants in this work — the
        record pipeline's `x > high + 1`, and an earlier version of this factor
        space in which no level ever called `delete`, so the single-factor defect
        could not execute. It runs first for that reason.
        """
        for version in (S.SINGLE_FAULT, S.INTERACTION_ONLY):
            self.assertTrue(_detecting(version), f"{version} is undetectable in this space")

    def test_mutants_are_caught_by_different_oracle_layers(self):
        """One oracle layer catching everything would make the other layers
        decoration, and would make both results rest on a single check."""
        reasons = {v: {S.judge(S.build(a), v).reason for a in _detecting(v)}
                   for v in (S.SINGLE_FAULT, S.INTERACTION_ONLY)}
        self.assertEqual(reasons[S.SINGLE_FAULT], {"index_incoherent"})       # layer 1
        self.assertEqual(reasons[S.INTERACTION_ONLY], {"rollback_leaked"})    # layer 2

    def test_naive_replay_shares_no_state_with_the_store(self):
        """Layer 3 must be able to disagree with the implementation. It cannot if
        it reaches into it."""
        node = S.build(dict.fromkeys(S.FACTORS) | {k: v[0] for k, v in S.FACTORS.items()})
        replayed = ts.naive_apply(ts.effective_ops(node))
        self.assertIsInstance(replayed, dict)
        store, _, _ = ts.execute(node)
        self.assertIsNot(replayed, store.data)


class TestDefectClassification(unittest.TestCase):
    """The labels `single_fault` and `interaction_only` are load-bearing: the whole
    comparison is about which methods reach which class. They are checked, not
    asserted in a docstring."""

    def test_interaction_defect_requires_all_three_conditions(self):
        detecting = _detecting(S.INTERACTION_ONLY)
        self.assertTrue(detecting)
        for assignment in detecting:
            for factor, level in REQUIRED.items():
                self.assertEqual(assignment[factor], level,
                                 f"detected without {factor}={level}: {assignment}")

    def test_each_of_the_three_conditions_is_individually_necessary(self):
        """Flipping any one of them must destroy the detection. Without this, the
        defect could be a two-way interaction that merely correlates with a third
        factor — a materially weaker claim."""
        for assignment in _detecting(S.INTERACTION_ONLY):
            for factor, level in REQUIRED.items():
                other = next(v for v in S.FACTORS[factor] if v != level)
                flipped = dict(assignment, **{factor: other})
                self.assertFalse(
                    S.judge(S.build(flipped), S.INTERACTION_ONLY).defect_detected,
                    f"still detected after flipping {factor} to {other}: {flipped}")

    def test_single_fault_is_reached_by_one_factor(self):
        """Every detecting candidate shares one level, and every candidate with
        that level detects — that is what makes it the control."""
        detecting = _detecting(S.SINGLE_FAULT)
        self.assertTrue(all(a["final"] == "delete_c" for a in detecting))
        self.assertEqual(len(detecting),
                         sum(1 for a in _suite() if a["final"] == "delete_c"))

    def test_the_two_suts_pose_different_problems(self):
        """If the second SUT's interaction defect were as easy as the first's, it
        would not test whether the finding generalizes."""
        store_rate = len(_detecting(S.INTERACTION_ONLY)) / len(_suite())
        pipeline_rate = sum(F.judge(F.build(a), F.INTERACTION_ONLY).defect_detected
                            for a in F.cartesian_suite()) / len(F.cartesian_suite())
        self.assertLess(store_rate, pipeline_rate)


class TestBaselineComparison(unittest.TestCase):
    def setUp(self):
        self.report = S.compare()

    def test_no_method_produces_a_false_positive(self):
        for name, data in self.report["methods"].items():
            self.assertEqual(data["false_positives"], 0, f"{name} fired against `correct`")

    def test_non_composing_baseline_misses_the_interaction_defect(self):
        isolated = self.report["methods"]["isolated-operations (non-composing)"]
        self.assertFalse(isolated["versions"][S.INTERACTION_ONLY]["detected"])

    def test_the_finding_reproduces_on_this_sut(self):
        """The reason this SUT exists: at least one *composing* sampling method
        must also miss the interaction defect, or the first study's result was
        about the record pipeline rather than about construction method."""
        missed_by = [name for name, data in self.report["methods"].items()
                     if not data["versions"][S.INTERACTION_ONLY]["detected"]]
        self.assertIn("one-factor-at-a-time (composing)", missed_by)

    def test_exhaustive_construction_finds_both_defects(self):
        cartesian = self.report["methods"]["flat-cartesian"]
        self.assertEqual(cartesian["defects_found"], 2)

    def test_every_method_draws_from_one_factor_declaration(self):
        for name, builder in S.BASELINES.items():
            for entry in builder(S.FACTORS):
                if isinstance(entry, dict):
                    self.assertLessEqual(set(entry), set(S.FACTORS), f"{name} invented a factor")
                    for key, value in entry.items():
                        self.assertIn(value, S.FACTORS[key], f"{name} invented a level")

    def test_wide_space_is_a_superset_of_the_narrow_one(self):
        """The wide space must widen the SAME axes, or the two widths are not
        comparable and the degradation between them means nothing."""
        self.assertEqual(set(S.WIDE_FACTORS), set(S.FACTORS))
        for key, levels in S.FACTORS.items():
            self.assertLessEqual(set(levels), set(S.WIDE_FACTORS[key]), key)


class TestEngineTwinAgreement(unittest.TestCase):
    def test_stream_and_node_paths_agree(self):
        for assignment in _suite()[::17]:
            node = S.build(assignment)
            for version in S.VERSIONS:
                result = S.evaluate_stream_under([node], version)
                verdict = S.judge(node, version)
                self.assertEqual(result.code == ts.VERDICT_ORACLE_DISAGREEMENT,
                                 verdict.defect_detected, assignment)
                self.assertEqual(result.ops, verdict.ops, assignment)

    def test_mutants_are_uninstalled_after_use(self):
        """A leaked patch would silently contaminate every later candidate — and
        the in-process study runs thousands of them in one process."""
        before = (ts._OPS["delete"], ts._savepoint_enter)
        S.evaluate_stream_under([S.build(_suite()[0])], S.SINGLE_FAULT)
        S.evaluate_stream_under([S.build(_suite()[0])], S.INTERACTION_ONLY)
        self.assertEqual((ts._OPS["delete"], ts._savepoint_enter), before)

    def test_unknown_version_is_rejected(self):
        with self.assertRaises(ValueError):
            S.install("not_a_version")

    def test_selected_version_defaults_to_the_control(self):
        import os
        saved = os.environ.pop(S.SUT_VERSION_ENV, None)
        try:
            self.assertEqual(S.selected_version(), S.CORRECT)
        finally:
            if saved is not None:
                os.environ[S.SUT_VERSION_ENV] = saved


class TestLevelDerivation(unittest.TestCase):
    def test_s2_space_matches_the_declared_count(self):
        self.assertEqual(len(_suite()), RF.LEVELS["s2"].expected_final)

    def test_s2_builds_distinct_trees(self):
        """Duplicate trees would mean the level is smaller than it claims."""
        self.assertEqual(len({repr(S.build(a)) for a in _suite()}),
                         RF.LEVELS["s2"].expected_final)

    def test_scope_tags_in_the_tree_match_the_scenario(self):
        """`build` and the scenario must produce the same shape: one transaction
        scope, and a repeated nest exactly when `nesting=repeated`."""
        flat = S.build({**{k: v[0] for k, v in S.FACTORS.items()}, "nesting": "flat"})
        repeated = S.build({**{k: v[0] for k, v in S.FACTORS.items()}, "nesting": "repeated"})
        self.assertEqual(ts.topology_stats(flat)["branches"], 1)
        self.assertEqual(ts.topology_stats(repeated)["branches"], 1)
        self.assertGreater(ts.op_count(repeated), ts.op_count(flat))


class TestStoreSemantics(unittest.TestCase):
    """The SUT has to be correct before it can host a defect study."""

    def test_rollback_restores_exactly(self):
        store = ts.Store()
        before = store.snapshot()
        node = ts.Txn((ts.Op("put", ts._params(key=9, value=1)),), commit=False)
        result, _, findings = ts.execute(node, store)
        self.assertEqual(result.snapshot(), before)
        self.assertEqual(findings, [])

    def test_commit_survives(self):
        node = ts.Txn((ts.Op("put", ts._params(key=9, value=1)),), commit=True)
        store, _, findings = ts.execute(node)
        self.assertEqual(store.data[9], 1)
        self.assertEqual(findings, [])

    def test_index_is_the_inverse_of_the_map(self):
        node = ts.Block((ts.Op("put", ts._params(key=1, value=7)),
                         ts.Op("delete", ts._params(key=2)),
                         ts.Op("bump", ts._params(key=3, delta=4))))
        store, _, _ = ts.execute(node)
        self.assertEqual(ts.index_incoherence(store), "")

    def test_reads_do_not_arm_the_copy_on_write_savepoint(self):
        """The third condition of the interaction defect depends on this. If a
        read armed the savepoint, `side` would stop being a real factor."""
        node = ts.Txn((ts.Op("read", ts._params(key=1)),), commit=False)
        store, _, findings = ts.execute(node)
        self.assertEqual(findings, [])
        self.assertEqual(store.data, dict(ts.INITIAL))

    def test_unbalanced_scope_is_a_construction_failure_not_a_domain_answer(self):
        stream = [ts.Marker(tag=1, opening=True, kind="block"),
                  ts.Op("put", ts._params(key=1, value=1))]
        self.assertEqual(ts.evaluate(stream).code, ts.VERDICT_CONSTRUCTION)


if __name__ == "__main__":
    unittest.main()
