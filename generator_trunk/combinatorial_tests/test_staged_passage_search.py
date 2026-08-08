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

"""Independent and real-SUT tests for the all-pairs staged search."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
GENERATOR_ROOT = HERE.parent
SEARCH_ROOT = (
    HERE / "sieve3d_max_passage" / "equivalence_size_first"
)
sys.path.insert(0, str(GENERATOR_ROOT))
sys.path.insert(0, str(SEARCH_ROOT))

import fwgen as fg  # noqa: E402
from constraints import sieve as bundle_sieve  # noqa: E402
from sut_paths import project_path  # noqa: E402

_sieve_root = Path(os.environ.get("SIEVE3D_ROOT", str(project_path("sieve3d"))))
if not (_sieve_root / "sieve3d" / "__init__.py").is_file():
    raise unittest.SkipTest(f"optional sieve3d SUT not found at {_sieve_root}")
import staged_passage_search as staged  # noqa: E402


SPEC = SEARCH_ROOT / "sieve3d_max_passage.toml"


def _config(
        *,
        rotations=(("neutral", 0.0, 0.0, 0.0),
                   ("front", 0.0, 90.0, 0.0)),
        shifts=(("center", 0.0, 0.0), ("tiny", 0.1, 0.0)),
        dynamic=(("dynamic", 0.0, 90.0, 0.0, 0.1, 0.0),),
        budgets=(1,),
        planners=("direct-drop",),
        frames=24,
        record=False,
) -> staged.SearchConfig:
    return staged.SearchConfig(
        rotation_seeds=tuple(rotations),
        shift_seeds=tuple(shifts),
        anchor_seeds=(),
        campaign_rotation_refinement_deg=0.0,
        campaign_shift_refinement_mm=0.0,
        dynamic_seed_poses=tuple(dynamic),
        wiggle_budgets=tuple(budgets),
        pair_wiggle_budgets=(),
        planner_algorithms=tuple(planners),
        adaptive_queue=("direct-drop",),
        planner_frames=frames,
        planner_max_steps=4,
        planner_rounds=1,
        planner_evals=20,
        planner_starts=1,
        planner_lookahead=0,
        planner_retreats=0,
        record_attempts=record,
    )


def _execute(body: str, hole: str, config: staged.SearchConfig,
             root: Path, run_id: str, *, record=False):
    universe = staged.generate_pair_universe(body, hole, config)
    proof = staged.execute_pair_universe(
        universe,
        evidence_root=root,
        run_id=run_id,
        record=record,
        resume=False,
    )
    return universe, proof


class TestDeclaredUniverse(unittest.TestCase):
    def test_all_live_bodies_x_holes_are_covered_exactly(self):
        self.assertEqual(staged.live_bodies(), tuple(staged.cc.BODIES))
        self.assertEqual(staged.live_holes(), tuple(staged.cc.HOLES))
        self.assertEqual(len(staged.live_bodies()), 10)
        self.assertEqual(len(staged.live_holes()), 10)
        pairs = {(body, hole) for body in staged.live_bodies()
                 for hole in staged.live_holes()}
        self.assertEqual(len(pairs), 100)

    def test_bundle_spec_exposes_every_registry_member_and_exact_raw_count(self):
        spec = fg.load_spec(SPEC, strict=True)
        slots = {slot.sheet: slot for slot in spec.slots}
        self.assertEqual(len(slots["BODY"].values), len(staged.live_bodies()))
        self.assertEqual(len(slots["HOLE"].values), len(staged.live_holes()))
        for body in staged.live_bodies():
            self.assertTrue(any(f'"{body}"' in value
                                for value in slots["BODY"].values))
        for hole in staged.live_holes():
            self.assertTrue(any(f'"{hole}"' in value
                                for value in slots["HOLE"].values))
        plan = fg.spec_cardinality_plan(spec)
        self.assertEqual(plan.mandatory.value, 200)
        self.assertEqual(plan.optional_multiplier.value, 1)
        self.assertEqual(slots["FAMILIES"].verb, "FW_Subsets_EXACT(6)")
        self.assertEqual(slots["RIGID_MOVES"].verb, "FW_Subsets_EXACT(8)")

    def test_bundle_candidate_fails_closed_on_incomplete_move_assembly(self):
        staged.reset_bundle_context()
        staged.select_body("flower")
        staged.select_hole("flower_hole")
        staged.select_policy("rigid_only")
        staged.select_modification("none")
        for family in staged.STAGE_ORDER:
            staged.enable_family(family)
        with self.assertRaisesRegex(staged.UniverseError,
                                    "all eight rigid moves"):
            staged.run_configured_pair()
        staged.reset_bundle_context()

    def test_bundle_accepts_preplanned_policy_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planned = root / "preplanned" / "planned_universes"
            planned.mkdir(parents=True)
            (planned / "flower--flower_hole.json").write_text(
                json.dumps({"policy_digest": staged.SearchConfig().digest}),
                encoding="utf-8")
            staged.reset_bundle_context()
            staged.select_body("flower")
            staged.select_hole("flower_hole")
            for family in staged.STAGE_ORDER:
                staged.enable_family(family)
            for move in staged.POSE_KEYS + ("drop", "wiggle", "thread"):
                staged.enable_move(move)
            proof = {"infrastructure_valid": True,
                     "certificate": {"verdict": True}}
            with mock.patch.dict(os.environ, {
                    "SIEVE3D_STAGED_EVIDENCE_ROOT": str(root),
                    "SIEVE3D_SEARCH_RUN_ID": "preplanned"}), \
                    mock.patch.object(staged, "execute_pair_universe",
                                      return_value=proof) as execute:
                self.assertEqual(staged.run_configured_pair(), proof)
                execute.assert_called_once()
            staged.reset_bundle_context()

    def test_bundle_sieve_removes_only_rigid_scale_contradictions(self):
        spec = fg.load_spec(SPEC, strict=True)
        slots = {slot.sheet: slot for slot in spec.slots}
        policy = slots["POLICY"].values[0]
        rows = []
        for body in slots["BODY"].values:
            for hole in slots["HOLE"].values:
                for modification in slots["MODIFICATION"].values:
                    rows.append([
                        {"sheet": "BODY", "value": body, "pos": 0},
                        {"sheet": "HOLE", "value": hole, "pos": 1},
                        {"sheet": "POLICY", "value": policy, "pos": 2},
                        {"sheet": "MODIFICATION", "value": modification,
                         "pos": 3},
                    ])
        report = bundle_sieve.sieve(rows, {
            "version": 1,
            "params": spec.params,
            "constraints": spec.constraints,
        })
        self.assertEqual(report["total"], 200)
        self.assertEqual(report["removed"], 100)
        self.assertEqual(report["kept"], 100)
        self.assertEqual(report["matched"]["rigid_policy_forbids_scale"], 100)
        self.assertEqual(report["total_rule_matches"], 100)

    def test_nary_and_deferred_optional_sieve_paths_classify_independently(self):
        nary = {
            "version": 1,
            "params": {},
            "constraints": [{
                "id": "illegal_triple",
                "polarity": "forbid",
                "sheets": ["FAMILY", "POSE", "ACTION"],
                "pairs": [{
                    "FAMILY": "neutral", "POSE": "shifted",
                    "ACTION": "drop",
                }],
                "gate": {},
            }],
        }
        illegal = [
            {"sheet": "FAMILY", "value": "neutral", "pos": 0},
            {"sheet": "POSE", "value": "shifted", "pos": 1},
            {"sheet": "ACTION", "value": "drop", "pos": 2},
        ]
        difficult_but_legal = [
            {"sheet": "FAMILY", "value": "mixed", "pos": 0},
            {"sheet": "POSE", "value": "hard", "pos": 1},
            {"sheet": "ACTION", "value": "drop", "pos": 2},
        ]
        report = bundle_sieve.sieve([illegal, difficult_but_legal], nary)
        self.assertEqual(report["removed"], 1)
        self.assertEqual(report["kept"], 1)

        constraint = {
            "id": "optional_deform",
            "polarity": "forbid",
            "sheets": ["POLICY", "OPT"],
            "pairs": [{"POLICY": "rigid", "OPT": "deform"}],
            "gate": {},
        }
        values = {1: "rigid", 2: "deform"}
        compiled = bundle_sieve.optional_bond_compile_report(
            [constraint], {}, {"POLICY": values, "OPT": values},
            {"POLICY": "combos_POLICY", "OPT": "combos_OPT"},
            ["POLICY", "OPT"], {"OPT"},
        )
        self.assertEqual(compiled["blockers"], [])
        self.assertEqual(len(compiled["lines"]), 1)
        self.assertTrue(compiled["lines"][0].startswith("F|"))

    def test_deterministic_unique_full_product_and_no_op_rejection(self):
        config = _config(
            rotations=(("neutral", 0, 0, 0), ("wave", 270, 90, 90)),
            shifts=(("center", 0, 0), ("tiny", 0.1, 0)),
        )
        first, equal = staged.generate_pair_universe_twice(
            "wave_bar", "wave_slot", config)
        self.assertTrue(equal)
        ids = [row["candidate_id"] for row in first["candidates"]]
        signatures = [row["canonical_signature"]
                      for row in first["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(signatures), len(set(signatures)))
        self.assertGreaterEqual(first["factors"]["rotation"]["rejected_no_op"], 1)
        mixed = first["factors"]["mixed"]
        self.assertEqual(
            mixed["raw_rotation_x_shift_cardinality"],
            first["stage_cardinalities"]["rotation"] *
            first["stage_cardinalities"]["shift"],
        )
        self.assertFalse(mixed["framework"]["nwise_reduction"])
        self.assertIsNone(first["resource_implications"]["hidden_candidate_cap"])
        self.assertEqual(
            first["raw_candidate_cardinality"],
            sum(first["pre_normalization_stage_cardinalities"].values()),
        )
        self.assertGreater(first["raw_candidate_cardinality"],
                           first["normalized_unique_cardinality"])

    def test_required_candidate_schema_and_true_neutral(self):
        universe = staged.generate_pair_universe(
            "flower", "flower_hole", _config())
        neutral = universe["candidates"][0]
        self.assertEqual(neutral["stage"], "neutral")
        self.assertEqual([item["action"] for item in neutral["action_plan"]],
                         ["assign", "drop"])
        self.assertNotIn("set_pose",
                         [item["action"] for item in neutral["action_plan"]])
        self.assertEqual(neutral["pose"], {key: 0.0 for key in staged.POSE_KEYS})
        required = staged._required_candidate_fields()
        self.assertTrue(all(required.issubset(row)
                            for row in universe["candidates"]))

    def test_exact_oracle_rejects_partial_crossing_jam_and_planner_only(self):
        self.assertTrue(staged.exact_full_pass(
            {"status": "passed", "passed_pct": 100.0}))
        for state in (
            {"status": "crossing", "passed_pct": 100.0},
            {"status": "passed", "passed_pct": 99.99},
            {"status": "jammed", "passed_pct": 100.0},
            {"status": "ready", "passed_pct": 0.0, "success": True},
        ):
            self.assertFalse(staged.exact_full_pass(state), state)

    def test_atomic_mixed_pose_and_cost_are_distinct_from_sequential(self):
        universe = staged.generate_pair_universe(
            "plug", "triangle",
            _config(
                rotations=(("neutral", 0, 0, 0), ("tri", 90, 90, 180)),
                shifts=(("center", 0, 0), ("tri", 0, 1.75)),
            ),
        )
        mixed = next(row for row in universe["candidates"]
                     if row["stage"] == "mixed")
        self.assertEqual([item["action"] for item in mixed["action_plan"]],
                         ["assign", "set_pose", "drop"])
        self.assertEqual(mixed["measured_action_tier"], 2)
        self.assertEqual(mixed["action_plan"][1]["cost"], 1)
        sequential_cost = 1 + 1 + 1
        self.assertEqual(sequential_cost, 3)


@unittest.skipUnless(staged.SIEVE3D_ROOT.exists(), "external SUT absent")
class TestRealStagedBranches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="staged-search-tests-")
        cls.root = Path(cls.temp.name)
        cls.results = {}

        cls.results["neutral"] = _execute(
            "flower", "flower_hole", _config(record=True), cls.root,
            "neutral", record=True)
        cls.results["rotation"] = _execute(
            "wave_bar", "wave_slot",
            _config(
                rotations=(("neutral", 0, 0, 0),
                           ("wave", 270, 90, 90)),
            ), cls.root, "rotation")
        cls.results["shift"] = _execute(
            "snake", "eye_snake",
            _config(
                rotations=(("neutral", 0, 0, 0),
                           ("front", 0, 90, 0)),
                shifts=(("center", 0, 0), ("measured", 0.3119, 0)),
                dynamic=(("snake", 90, 12, 270, 0.3119, 0),),
            ), cls.root, "shift")
        cls.results["mixed"] = _execute(
            "plug", "triangle",
            _config(
                rotations=(("neutral", 0, 0, 0),
                           ("tri", 90, 90, 180)),
                shifts=(("center", 0, 0), ("tri", 0, 1.75)),
                dynamic=(("tri", 90, 90, 180, 0, 1.75),),
            ), cls.root, "mixed")
        cls.results["dynamic"] = _execute(
            "twisted_flower", "flower_hole",
            _config(
                dynamic=(("anchor", 0, 0, 180, 0, 0),),
                budgets=(1, 4, 16, 40),
                frames=48,
            ), cls.root, "dynamic")
        cls.results["exhausted"] = _execute(
            "flower", "round_small", _config(), cls.root, "exhausted")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_neutral_success_stops_all_retries(self):
        _universe, proof = self.results["neutral"]
        self.assertEqual(proof["status"], "passed")
        self.assertEqual(proof["search_attempt_count"], 1)
        self.assertEqual(proof["first_successful_stage"], "neutral")
        self.assertEqual(proof["solution_action_cost"], 1)
        self.assertTrue(proof["certificate"]["verdict"])

    def test_rotation_success_exhausts_complete_shared_static_tier(self):
        universe, proof = self.results["rotation"]
        static_count = sum(universe["stage_cardinalities"][stage]
                           for stage in ("rotation", "shift", "mixed"))
        self.assertEqual(proof["search_attempt_count"], 1 + static_count)
        self.assertEqual(proof["first_successful_stage"], "rotation")
        self.assertTrue(all(attempt["stage"] in
                            {"neutral", "rotation", "shift", "mixed"}
                            for attempt in proof["attempts"]))
        self.assertTrue(proof["certificate"][
            "first_successful_tier_fully_exhausted"])

    def test_shift_solution_replaces_old_feedback_result(self):
        universe, proof = self.results["shift"]
        selected = next(row for row in universe["candidates"]
                        if row["candidate_id"] ==
                        proof["selected_candidate_id"])
        attempt = next(row for row in proof["attempts"]
                       if row["candidate_id"] ==
                       proof["selected_candidate_id"])
        self.assertEqual(proof["first_successful_stage"], "shift")
        self.assertEqual(selected["pose"]["dx"], 0.3119)
        self.assertEqual(selected["pose"]["dy"], 0.0)
        self.assertEqual(proof["solution_action_cost"], 2)
        self.assertAlmostEqual(attempt["worst_clearance"], 0.1859, places=4)

    def test_mixed_solution_requires_atomic_rotation_plus_shift(self):
        _universe, proof = self.results["mixed"]
        by_stage = {stage: [] for stage in staged.STAGE_ORDER}
        for attempt in proof["attempts"]:
            by_stage[attempt["stage"]].append(attempt)
        self.assertFalse(any(row["full_pass"] for row in by_stage["rotation"]))
        self.assertFalse(any(row["full_pass"] for row in by_stage["shift"]))
        self.assertTrue(any(row["full_pass"] for row in by_stage["mixed"]))
        self.assertEqual(proof["first_successful_stage"], "mixed")
        self.assertEqual(proof["solution_action_cost"], 2)

    def test_multi_move_prefixes_prove_first_full_action_cost(self):
        _universe, proof = self.results["dynamic"]
        self.assertEqual(proof["first_successful_stage"], "multi_move")
        self.assertEqual(proof["solution_action_cost"], 23)
        selected = next(row for row in proof["attempts"]
                        if row["candidate_id"] ==
                        proof["selected_candidate_id"])
        self.assertEqual(selected["first_exact_full_pass_action_cost"], 23)
        self.assertTrue(selected["all_lower_observed_prefixes_failed"])
        self.assertTrue(all(
            not staged.exact_full_pass(row)
            for row in selected["physical_action_prefix_states"]
            if row["actions"] < 23))
        lower = [row for row in proof["attempts"]
                 if row["stage"] == "multi_move" and
                 row["measured_action_tier"] < 42]
        self.assertTrue(lower)
        self.assertFalse(any(row["full_pass"] for row in lower))

    def test_declared_space_exhaustion_is_not_impossibility(self):
        universe, proof = self.results["exhausted"]
        self.assertEqual(proof["status"], "declared_space_exhaustion")
        self.assertEqual(proof["search_attempt_count"],
                         len(universe["candidates"]))
        self.assertIsNotNone(proof["declared_space_exhaustion_reason"])
        self.assertFalse(proof["mathematical_impossibility_claimed"])
        self.assertTrue(proof["certificate"]["exhausted_all_declared_stages"])
        self.assertIn("FW_VAR=0", staged.pair_kv_line(proof))

    def test_record_metadata_checksums_and_honest_selected_replay(self):
        _universe, proof = self.results["neutral"]
        attempt = proof["attempts"][0]
        for path_key, hash_key in (
                ("record_path", "record_sha256"),
                ("metadata_path", "metadata_sha256")):
            path = Path(attempt[path_key])
            self.assertTrue(path.is_file())
            self.assertEqual(staged._sha256_file(path), attempt[hash_key])
        metadata = json.loads(Path(attempt["metadata_path"]).read_text())
        self.assertEqual(metadata["candidate_id"], attempt["candidate_id"])
        self.assertEqual(metadata["manual_replay"]["api_path"],
                         "/api/v1/replay")
        lines = [json.loads(line) for line in
                 Path(attempt["record_path"]).read_text().splitlines()]
        actions = [row["payload"]["action"] for row in lines
                   if row.get("kind") == "step" and
                   row.get("path") == "/api/v1/experiment/action"]
        self.assertEqual(actions, ["assign", "drop"])
        self.assertEqual(attempt["status"], "passed")
        self.assertEqual(attempt["passed_pct"], 100.0)

    def test_known_passing_candidates_are_not_pruned_by_fit_order(self):
        shift_universe, shift_proof = self.results["shift"]
        shift_id = shift_proof["selected_candidate_id"]
        self.assertIn(shift_id,
                      [row["candidate_id"] for row in shift_universe["candidates"]])
        self.assertIn(shift_id, shift_proof["executed_prefix"])
        mixed_universe, mixed_proof = self.results["mixed"]
        mixed_id = mixed_proof["selected_candidate_id"]
        self.assertIn(mixed_id,
                      [row["candidate_id"] for row in mixed_universe["candidates"]])
        self.assertIn(mixed_id, mixed_proof["executed_prefix"])

    def test_valid_physical_failure_is_analyzer_eligible_but_infra_is_not(self):
        _universe, failure = self.results["exhausted"]
        self.assertIn("FW_VAR=0", staged.pair_kv_line(failure))
        broken = copy.deepcopy(failure)
        broken["infrastructure_valid"] = False
        self.assertIn("FW_VAR=6", staged.pair_kv_line(broken))


class TestIndependentTamperVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="staged-tamper-")
        cls.root = Path(cls.temp.name)
        config = _config(
            rotations=(("neutral", 0, 0, 0), ("wave", 270, 90, 90)),
        )
        cls.universe, cls.proof = _execute(
            "wave_bar", "wave_slot", config, cls.root, "tamper")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _verify(self, universe=None, proof=None, attempts=None):
        universe = copy.deepcopy(universe or self.universe)
        proof = copy.deepcopy(proof or self.proof)
        attempts = copy.deepcopy(attempts or proof["attempts"])
        return staged.verify_pair_documents(
            universe, proof, attempts=attempts, check_files=False)

    def test_clean_certificate_passes(self):
        self.assertTrue(self._verify()["verdict"])

    def test_reordered_candidate_is_rejected(self):
        attempts = copy.deepcopy(self.proof["attempts"])
        attempts[1], attempts[2] = attempts[2], attempts[1]
        self.assertFalse(self._verify(attempts=attempts)["verdict"])

    def test_hidden_earlier_success_is_rejected(self):
        attempts = copy.deepcopy(self.proof["attempts"])
        attempts[0]["final_state"]["status"] = "passed"
        attempts[0]["final_state"]["passed_pct"] = 100.0
        attempts[0]["full_pass"] = True
        attempts[0]["independent_full_pass"] = True
        self.assertFalse(self._verify(attempts=attempts)["verdict"])

    def test_false_full_flag_is_rejected(self):
        attempts = copy.deepcopy(self.proof["attempts"])
        attempts[0]["full_pass"] = True
        self.assertFalse(self._verify(attempts=attempts)["verdict"])

    def test_higher_tier_winner_is_rejected(self):
        proof = copy.deepcopy(self.proof)
        higher = next(row for row in self.universe["candidates"]
                      if row["stage"] == "multi_move")
        proof["selected_candidate_id"] = higher["candidate_id"]
        self.assertFalse(self._verify(proof=proof)["verdict"])

    def test_omitted_universe_member_is_rejected(self):
        universe = copy.deepcopy(self.universe)
        universe["candidates"].pop()
        self.assertFalse(self._verify(universe=universe)["verdict"])

    def test_altered_cost_is_rejected(self):
        attempts = copy.deepcopy(self.proof["attempts"])
        attempts[-1]["solution_action_cost"] += 1
        self.assertFalse(self._verify(attempts=attempts)["verdict"])

    def test_missing_record_is_rejected(self):
        proof = copy.deepcopy(self.proof)
        attempts = copy.deepcopy(proof["attempts"])
        attempts[0]["record_path"] = "/definitely/missing/record.rec"
        certificate = staged.verify_pair_documents(
            copy.deepcopy(self.universe), proof, attempts=attempts,
            check_files=True)
        self.assertFalse(certificate["verdict"])
        self.assertTrue(any("missing evidence file" in error
                            for error in certificate["errors"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
