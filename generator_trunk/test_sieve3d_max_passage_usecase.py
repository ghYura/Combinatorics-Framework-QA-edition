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

"""Regression tests for the sieve3d maximum-passage combinatorial suite."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fwgen as fg  # noqa: E402
from sut_paths import project_path  # noqa: E402

ROOT = HERE / "combinatorial_tests" / "sieve3d_max_passage" / "equivalence_size_first"
SPEC = ROOT / "sieve3d_max_passage.toml"
API_ROOT = HERE / "combinatorial_tests" / "sieve3d_max_passage" / "api_planner_feedback"
API_SPEC = API_ROOT / "sieve3d_api_planner_feedback.toml"
EXTERNAL_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT",
    str(project_path("sieve3d")),
))


def _slot(spec: fg.Spec, sheet: str):
    for slot in spec.slots:
        if slot.sheet == sheet:
            return slot
    raise AssertionError(f"missing slot {sheet}")


def _candidate(spec: fg.Spec, values: dict[str, str]) -> str:
    out = []
    for slot in spec.slots:
        if slot.sheet in values:
            out.append(values[slot.sheet])
        elif "FW_Optional" not in slot.flags:
            out.append(slot.values[0])
    return "".join(out)


@contextlib.contextmanager
def _candidate_environment(rec_root: str):
    old = {k: os.environ.get(k) for k in (
        "SIEVE3D_ROOT", "SIEVE3D_REC_OUT_DIR", "SIEVE3D_MAX_PASSAGE_ROOT",
        "SIEVE3D_STAGED_EVIDENCE_ROOT", "SIEVE3D_SEARCH_RUN_ID")}
    os.environ["SIEVE3D_ROOT"] = str(EXTERNAL_ROOT)
    os.environ["SIEVE3D_REC_OUT_DIR"] = rec_root
    os.environ["SIEVE3D_MAX_PASSAGE_ROOT"] = str(ROOT)
    os.environ["SIEVE3D_STAGED_EVIDENCE_ROOT"] = rec_root
    os.environ["SIEVE3D_SEARCH_RUN_ID"] = "parent-generated-candidate"
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TestSieve3dMaxPassageUsecase(unittest.TestCase):
    def test_spec_loads_strict_and_has_intentional_cardinality(self):
        spec = fg.load_spec(SPEC, strict=True)
        self.assertEqual([s.sheet for s in spec.slots], [
            "HEAD", "BODY", "HOLE", "FAMILIES", "RIGID_MOVES",
            "POLICY", "MODIFICATION", "RUN", "TAIL",
        ])
        plan = fg.spec_cardinality_plan(spec)
        self.assertEqual(plan.mandatory.value, 200)
        self.assertEqual(plan.optional_multiplier.value, 1)
        self.assertEqual(plan.final.value, 200)
        self.assertEqual(len(spec.constraints), 1)
        self.assertEqual(spec.constraints[0]["id"],
                         "rigid_policy_forbids_scale")

    def test_spec_uses_full_combinatoric_families_moves_and_all_pairs(self):
        spec = fg.load_spec(SPEC, strict=True)
        self.assertEqual(_slot(spec, "BODY").verb, "FW_Combi(1)")
        self.assertEqual(len(_slot(spec, "BODY").values), 10)
        self.assertEqual(_slot(spec, "HOLE").verb, "FW_Combi(1)")
        self.assertEqual(len(_slot(spec, "HOLE").values), 10)
        self.assertEqual(_slot(spec, "FAMILIES").verb,
                         "FW_Subsets_EXACT(6)")
        self.assertEqual(_slot(spec, "RIGID_MOVES").verb,
                         "FW_Subsets_EXACT(8)")
        self.assertEqual(_slot(spec, "POLICY").values,
                         ['search.select_policy("rigid_only");'])
        self.assertEqual(len(_slot(spec, "MODIFICATION").values), 2)
        self.assertFalse(any("FW_Optional" in slot.flags
                             for slot in spec.slots))

        head = _slot(spec, "HEAD").values[0].rstrip()
        tail = _slot(spec, "TAIL").values[0].lstrip()
        self.assertTrue(head.endswith("search.reset_bundle_context()"))
        self.assertTrue(tail.startswith(
            "bundle_fw_var = search.bundle_fw_var()"))
        self.assertIn("FW_VAR = bundle_fw_var", tail)
        self.assertIn("search.bundle_kv_line", tail)

    def test_api_planner_feedback_spec_loads_small_bundle_contract(self):
        spec = fg.load_spec(API_SPEC, strict=True)
        self.assertEqual([s.sheet for s in spec.slots], [
            "HEAD", "CASE", "ALGORITHMS", "RUN", "TAIL",
        ])
        plan = fg.spec_cardinality_plan(spec)
        self.assertEqual(plan.mandatory.value, 2)
        self.assertEqual(plan.optional_multiplier.value, 1)
        self.assertEqual(plan.final.value, 2)
        self.assertEqual(_slot(spec, "CASE").verb, "FW_Combi(1)")
        self.assertIn('CASE_ID="snake_eye"', _slot(spec, "CASE").values[0])
        self.assertIn('ALGORITHMS="core_portfolio"',
                      _slot(spec, "ALGORITHMS").values[0])
        self.assertEqual([(g.key, g.direction) for g in spec.goals], [
            ("planner_passed_volume_pct", "max"),
            ("planner_estimated_cost", "min"),
        ])

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_primary_module_routes_to_all_pair_staged_engine(self):
        sys.path.insert(0, str(ROOT))
        import max_passage_search as search  # noqa: E402
        self.assertEqual(search.BODY_CASES, tuple(search.cc.BODIES))
        self.assertTrue(all(value == 100.0
                            for value in search.TARGET_PCT.values()))
        self.assertIs(search.generate_pair_universe,
                      search.staged.generate_pair_universe)
        universe = search.generate_pair_universe(
            "flower", "flower_hole",
            search.SearchConfig(
                rotation_seeds=(("neutral", 0, 0, 0),
                                ("front", 0, 90, 0)),
                shift_seeds=(("center", 0, 0), ("tiny", 0.1, 0)),
                anchor_seeds=(),
                campaign_rotation_refinement_deg=0,
                campaign_shift_refinement_mm=0,
                dynamic_seed_poses=(("dynamic", 0, 90, 0, 0.1, 0),),
                wiggle_budgets=(1,), pair_wiggle_budgets=(),
                planner_algorithms=("direct-drop",),
                adaptive_queue=("direct-drop",), planner_frames=24,
            ),
        )
        neutral = universe["candidates"][0]
        self.assertEqual([row["action"] for row in neutral["action_plan"]],
                         ["assign", "drop"])

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_generated_api_planner_feedback_candidate_executes(self):
        spec = fg.load_spec(API_SPEC, strict=True)
        values = {
            "CASE": _slot(spec, "CASE").values[0],
            "ALGORITHMS": _slot(spec, "ALGORITHMS").values[0],
            "RUN": _slot(spec, "RUN").values[0],
        }
        code = _candidate(spec, values)
        ns: dict = {}
        buf = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="sieve3d-api-planner-") as rec_root:
            with _candidate_environment(rec_root), contextlib.redirect_stdout(buf):
                exec(compile(code, "<sieve3d-api-planner-candidate>", "exec"), ns)
            self.assertTrue(Path(ns["search"].CTX.rec_file).is_file())
            self.assertTrue(Path(ns["search"].CTX.rec_json).is_file())
            self.assertGreater(
                ns["search"].CTX.metrics["record_steps"], 0)
        out = buf.getvalue()
        self.assertEqual(ns["FW_VAR"], 0, out)
        self.assertIn("app=sieve3d_api_planner_feedback", out)
        self.assertIn("criteria_profile=sieve3d_api_planner_feedback_v1", out)
        self.assertIn("body=snake", out)
        self.assertIn("best_hole=eye_snake", out)
        self.assertIn("planner_algorithm=", out)
        self.assertIn(ns["search"].CTX.planner["best_algorithm"], ns["search"].CTX.planner["requested_algorithms"])
        self.assertIn("planner_success=1", out)
        self.assertIn("planner_algorithms=3", out)
        self.assertIn("feature_points=", out)
        self.assertGreater(ns["search"].CTX.metrics["planner_cycles"], 0, out)
        self.assertGreater(ns["search"].CTX.metrics["planner_evals"], 0, out)
        self.assertGreater(ns["search"].CTX.metrics["feature_edges"], 0, out)

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_generated_candidate_executes_records_and_prints_metrics(self):
        spec = fg.load_spec(SPEC, strict=True)
        values = {
            "BODY": _slot(spec, "BODY").values[1],
            "HOLE": _slot(spec, "HOLE").values[1],
            "FAMILIES": "".join(_slot(spec, "FAMILIES").values),
            "RIGID_MOVES": "".join(_slot(spec, "RIGID_MOVES").values),
            "POLICY": _slot(spec, "POLICY").values[0],
            "MODIFICATION": _slot(spec, "MODIFICATION").values[0],
            "RUN": _slot(spec, "RUN").values[0],
        }
        code = _candidate(spec, values)
        ns: dict = {}
        buf = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="sieve3d-max-passage-") as rec_root:
            with _candidate_environment(rec_root), contextlib.redirect_stdout(buf):
                exec(compile(code, "<sieve3d-max-passage-candidate>", "exec"), ns)
            out = buf.getvalue()
            self.assertEqual(ns["FW_VAR"], 0, out)
            self.assertIn("app=sieve3d_all_pairs_staged", out)
            self.assertIn("criteria_profile=sieve3d_staged_v2", out)
            self.assertIn(
                "criteria_metrics=full_pass:max,passed_volume_pct:max,solution_actions:min,solution_keyframes:min,changed_parameter_count:min,worst_clearance:max,search_attempts:min",
                out,
            )
            self.assertIn("body=flower", out)
            self.assertIn("hole=flower_hole", out)
            self.assertIn("full_pass=1", out)
            self.assertIn("passed_volume_pct=100.00", out)
            self.assertIn("solution_actions=1", out)
            self.assertIn("planner_estimated_cost=", out)
            proof = ns["search"].BUNDLE_CTX.result
            self.assertEqual(proof["search_attempt_count"], 1)
            self.assertTrue(proof["certificate"]["verdict"])
            self.assertTrue(Path(proof["attempts"][0]["record_path"]).is_file())
            self.assertTrue(Path(proof["attempts"][0]["metadata_path"]).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
