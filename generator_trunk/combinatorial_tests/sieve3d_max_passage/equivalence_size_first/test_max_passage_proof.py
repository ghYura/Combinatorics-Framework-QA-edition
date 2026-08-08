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

"""Proof-oriented checks for the max-passage combinatorial search."""

from __future__ import annotations

import contextlib
import json
import tempfile
import os
import sys
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATOR_ROOT = HERE.parents[2]
sys.path.insert(0, str(GENERATOR_ROOT))

from sut_paths import project_path  # noqa: E402

SUT_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT",
    str(project_path("sieve3d")),
))
sys.path.insert(0, str(HERE))

@contextlib.contextmanager
def _record_output_dir():
    old = os.environ.get("SIEVE3D_REC_OUT_DIR")
    with tempfile.TemporaryDirectory(prefix="sieve3d-proof-records-") as tmp:
        os.environ["SIEVE3D_REC_OUT_DIR"] = tmp
        try:
            yield Path(tmp)
        finally:
            if old is None:
                os.environ.pop("SIEVE3D_REC_OUT_DIR", None)
            else:
                os.environ["SIEVE3D_REC_OUT_DIR"] = old


search = None
if SUT_ROOT.exists():
    import max_passage_search as search  # noqa: E402


class TestMaxPassageProof(unittest.TestCase):
    def setUp(self):
        self._record_context = _record_output_dir()
        self.record_root = self._record_context.__enter__()

    def tearDown(self):
        self._record_context.__exit__(None, None, None)

    def assert_record_artifact(self, candidate):
        rec_path = Path(candidate["record_file"])
        json_path = Path(candidate["record_json"])
        self.assertTrue(rec_path.is_file(), candidate)
        self.assertTrue(json_path.is_file(), candidate)
        self.assertGreater(rec_path.stat().st_size, 0, candidate)
        self.assertNotEqual(rec_path, json_path)

        lines = [
            json.loads(line) for line in rec_path.read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
        self.assertEqual(lines[0]["kind"], "header")
        self.assertEqual(lines[0]["rec"], "sieve3d-rec/1")
        self.assertTrue(any(row.get("kind") == "initial" for row in lines))
        steps = [row for row in lines if row.get("kind") == "step"]
        self.assertEqual(len(steps), candidate["record_steps"])
        self.assertEqual(candidate["record_trace_frames"], 24)
        self.assertEqual(candidate["record_trace_steps"], 27)
        self.assertEqual(len(steps), candidate["record_trace_steps"] + 1)

        self.assertEqual(steps[0]["path"], "/api/v1/passage")
        self.assertEqual(
            steps[0]["payload"]["algorithms"],
            candidate["requested_algorithms"],
        )
        actions = steps[1:]
        self.assertTrue(all(
            row["path"] == "/api/v1/experiment/action" for row in actions))
        action_names = [row["payload"]["action"] for row in actions]
        self.assertEqual(action_names[:3], ["assign", "set_z", "set_pose"])
        self.assertEqual(
            action_names[3:],
            ["set_pose"] * candidate["record_trace_frames"],
        )
        motion = actions[3:]
        z_values = [float(row["payload"]["params"]["z"]) for row in motion]
        self.assertGreater(len(set(z_values)), 20)
        self.assertGreater(z_values[0], z_values[-1])
        self.assertGreater(float(motion[-1]["dt"]) - float(motion[0]["dt"]),
                           0.2)

        metadata = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(Path(metadata["saved_rec"]), rec_path)
        self.assertEqual(Path(metadata["saved_json"]), json_path)
        self.assertEqual(metadata["steps_count"], len(steps))
        self.assertEqual(metadata["portfolio"], candidate["portfolio"])
        self.assertEqual(metadata["requested_algorithms"],
                         candidate["requested_algorithms"])
        self.assertEqual(metadata["record_trace_frames"], 24)
        self.assertEqual(metadata["record_trace_steps"], len(actions))
        states = metadata["record_trace_states"]
        self.assertEqual(len(states), metadata["record_trace_frames"])
        self.assertGreater(states[0]["z"], states[-1]["z"])
        self.assertGreaterEqual(states[-1]["passed_pct"],
                                states[0]["passed_pct"])
        replay = metadata["manual_replay"]
        self.assertEqual(replay["api_path"], "/api/v1/replay")
        self.assertEqual(replay["api_payload"]["file"], rec_path.name)
        self.assertEqual(Path(replay["copy_to"]).parent, SUT_ROOT / "records")
        return rec_path, json_path, metadata
    def test_specs_optimize_outcomes_then_explicit_search_efficiency(self):
        with (HERE / "sieve3d_max_passage.toml").open("rb") as stream:
            main_spec = tomllib.load(stream)
        with (HERE.parent / "api_planner_feedback" /
              "sieve3d_api_planner_feedback.toml").open("rb") as stream:
            api_spec = tomllib.load(stream)

        main_goals = [(g["key"], g["dir"]) for g in main_spec["goals"]]
        self.assertEqual(main_goals, [
            ("full_pass", "max"),
            ("passed_volume_pct", "max"),
            ("solution_actions", "min"),
            ("solution_keyframes", "min"),
            ("changed_parameter_count", "min"),
            ("worst_clearance", "max"),
            ("search_attempts", "min"),
        ])
        self.assertEqual(
            [(g["key"], g["dir"]) for g in api_spec["goals"]],
            [
                ("planner_passed_volume_pct", "max"),
                ("planner_estimated_cost", "min"),
            ],
        )
        algorithms = next(
            slot for slot in api_spec["slots"] if slot["sheet"] == "ALGORITHMS")
        self.assertEqual(algorithms["values"], [
            'ALGORITHMS="core_portfolio";',
            'ALGORITHMS="direct_baseline";',
        ])

    @unittest.skipUnless(search is not None, "external sieve3d project is absent")
    def test_projection_equivalence_preserves_scale(self):
        small = {
            "area": 100.0,
            "perimeter": 40.0,
            "bbox": [-5.0, -5.0, 5.0, 5.0],
            "convex": True,
            "symmetry": 4,
        }
        scaled = {
            "area": 400.0,
            "perimeter": 80.0,
            "bbox": [-10.0, -10.0, 10.0, 10.0],
            "convex": True,
            "symmetry": 4,
        }
        self.assertNotEqual(
            search._projection_equivalence_key(small),
            search._projection_equivalence_key(scaled),
        )

    @unittest.skipUnless(search is not None, "external sieve3d project is absent")
    def test_algorithm_gates_are_request_scoped_and_catalog_dynamic(self):
        advertised = [
            "direct-drop",
            "feedback-thread",
            "future-catalog-thread",
        ]
        label, direct = search._resolve_planner_algorithms(
            advertised, "direct_baseline")
        self.assertEqual(label, "direct_baseline")
        self.assertEqual(direct, ["direct-drop"])

        label, dynamic = search._resolve_planner_algorithms(
            advertised, "catalog_portfolio")
        self.assertEqual(label, "catalog_portfolio")
        self.assertEqual(dynamic, advertised)

        with self.assertRaisesRegex(
                RuntimeError, "catalog_missing_requested"):
            search._resolve_planner_algorithms(
                ["direct-drop"], "feedback_portfolio")

    @unittest.skipUnless(search is not None, "external sieve3d project is absent")
    def test_dynamic_campaign_pair_survives_static_shortlist(self):
        ranking = [{"hole": "arch"}, {"hole": "eye_snake"}]
        selected = search._select_movement_candidates(
            "snake", ranking, budget=1)
        self.assertEqual(
            [row["hole"] for row in selected],
            ["arch", "eye_snake"],
        )

    @unittest.skipUnless(search is not None, "external sieve3d project is absent")
    def test_direct_baseline_is_an_eligible_low_objective_observation(self):
        search.reset()
        summary = search.run_api_probe("snake_eye", "direct_baseline")

        self.assertEqual(search.api_probe_var(), 0, summary)
        self.assertEqual(
            summary["planner"]["requested_algorithms"],
            ["direct-drop"],
        )
        self.assert_record_artifact(summary["planner"])
        self.assertLess(
            summary["metrics"]["planner_passed_volume_pct"],
            search.PLANNER_PROBE_CASES["snake_eye"]["min_pct"],
        )
        kv = search.kv_line(var=search.api_probe_var())
        self.assertIn("record_trace_frames=24", kv)
        self.assertIn("record_trace_steps=27", kv)
        self.assertIn("record_steps=28", kv)
        self.assertEqual(search.fw_var(), 2)


    @unittest.skipUnless(search is not None, "external sieve3d project is absent")
    def test_richer_portfolio_strictly_improves_and_selected_is_arg_best(self):
        report = search.run_portfolio_proof()
        candidates = report["candidates"]
        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            {(row["body"], row["hole"]) for row in candidates},
            {(report["body"], report["hole"])},
        )
        artifact_results = [
            self.assert_record_artifact(row) for row in candidates
        ]
        self.assertEqual(len({rec for rec, _, _ in artifact_results}), 2)
        self.assertEqual(len({meta for _, meta, _ in artifact_results}), 2)
        metadata_by_portfolio = {
            row["portfolio"]: artifact_results[index][2]
            for index, row in enumerate(candidates)
        }
        self.assertEqual(report["record_artifacts"], [
            {
                "portfolio": row["portfolio"],
                "record_file": row["record_file"],
                "record_json": row["record_json"],
                "record_steps": row["record_steps"],
                "record_trace_frames": row["record_trace_frames"],
                "record_trace_steps": row["record_trace_steps"],
            }
            for row in candidates
        ])

        baseline = report["baseline"]
        self.assertEqual(baseline["requested_algorithms"], ["direct-drop"])
        self.assertTrue(report["strict_improvement"], report)
        self.assertGreater(
            report["selected"]["passed_pct"],
            baseline["passed_pct"],
            report,
        )

        independent = max(candidates, key=lambda row: (
            round(float(row["passed_pct"]), 6),
            -int(row["estimated_cost"]),
        ))
        rich = report["selected"]
        self.assertEqual(rich["success"], 1)
        self.assertEqual(rich["passed_pct"], 100.0)
        rich_states = metadata_by_portfolio[
            rich["portfolio"]]["record_trace_states"]
        pose_signatures = {
            tuple(float(state["pose"][key]) for key in search.POSE_KEYS)
            for state in rich_states
        }
        passed_progress = {
            float(state["passed_pct"]) for state in rich_states
        }
        self.assertGreater(len(pose_signatures), 1)
        self.assertGreater(len(passed_progress), 5)
        self.assertEqual(rich_states[-1]["passed_pct"], 100.0)
        self.assertEqual(rich_states[-1]["status"], "passed")
        self.assertEqual(report["selected"], independent)
        self.assertNotEqual(
            report["selected"]["portfolio"],
            baseline["portfolio"],
        )
        for row in candidates:
            self.assertTrue(
                set(row["requested_algorithms"]).issubset(
                    row["catalog_algorithms"]),
                row,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
