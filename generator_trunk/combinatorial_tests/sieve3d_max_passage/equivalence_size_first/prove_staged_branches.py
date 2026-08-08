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

"""Persist real neutral/rotation/shift/mixed/dynamic/exhaustion evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import staged_passage_search as staged


def config(*, rotations=None, shifts=None, dynamic=None, budgets=(1,),
           frames=24) -> staged.SearchConfig:
    return staged.SearchConfig(
        rotation_seeds=tuple(rotations or (
            ("neutral", 0.0, 0.0, 0.0),
            ("front", 0.0, 90.0, 0.0),
        )),
        shift_seeds=tuple(shifts or (
            ("center", 0.0, 0.0), ("tiny", 0.1, 0.0),
        )),
        anchor_seeds=(),
        campaign_rotation_refinement_deg=0.0,
        campaign_shift_refinement_mm=0.0,
        dynamic_seed_poses=tuple(dynamic or (
            ("dynamic", 0.0, 90.0, 0.0, 0.1, 0.0),
        )),
        wiggle_budgets=tuple(budgets),
        pair_wiggle_budgets=(),
        planner_algorithms=("direct-drop",),
        adaptive_queue=("direct-drop",),
        planner_frames=frames,
        planner_max_steps=4,
        planner_rounds=1,
        planner_evals=20,
        planner_starts=1,
        planner_lookahead=0,
        planner_retreats=0,
        record_attempts=True,
    )


CASES = (
    ("neutral", "flower", "flower_hole", config(),
     {"status": "passed", "stage": "neutral", "actions": 1}),
    ("rotation", "wave_bar", "wave_slot", config(
        rotations=(("neutral", 0, 0, 0), ("wave", 270, 90, 90))),
     {"status": "passed", "stage": "rotation", "actions": 2}),
    ("shift", "snake", "eye_snake", config(
        rotations=(("neutral", 0, 0, 0), ("front", 0, 90, 0)),
        shifts=(("center", 0, 0), ("measured", 0.3119, 0)),
        dynamic=(("snake", 90, 12, 270, 0.3119, 0),)),
     {"status": "passed", "stage": "shift", "actions": 2}),
    ("mixed", "plug", "triangle", config(
        rotations=(("neutral", 0, 0, 0), ("tri", 90, 90, 180)),
        shifts=(("center", 0, 0), ("tri", 0, 1.75)),
        dynamic=(("tri", 90, 90, 180, 0, 1.75),)),
     {"status": "passed", "stage": "mixed", "actions": 2}),
    ("dynamic", "twisted_flower", "flower_hole", config(
        dynamic=(("anchor", 0, 0, 180, 0, 0),),
        budgets=(1, 4, 16, 40), frames=48),
     {"status": "passed", "stage": "multi_move", "actions": 23}),
    ("exhausted", "flower", "round_small", config(),
     {"status": "declared_space_exhaustion", "stage": None,
      "actions": None}),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path,
                        default=staged.HERE / "branch_evidence")
    parser.add_argument("--run-id", default=time.strftime(
        "branches-%Y%m%dT%H%M%S"))
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    run_dir = args.evidence_root / staged._safe(args.run_id)
    rows = []
    proofs = []
    errors = []
    for label, body, hole, scope, expected in CASES:
        universe, deterministic = staged.generate_pair_universe_twice(
            body, hole, scope)
        proof = staged.execute_pair_universe(
            universe,
            evidence_root=args.evidence_root,
            run_id=args.run_id,
            record=True,
            resume=not args.no_resume,
        )
        proofs.append(proof)
        selected = staged._best_observation(proof)
        row = staged.pair_matrix_row(universe, proof)
        row["branch_label"] = label
        row["generated_twice_equal"] = deterministic
        rows.append(row)
        actual = {
            "status": proof["status"],
            "stage": proof["first_successful_stage"],
            "actions": proof["solution_action_cost"],
        }
        if actual != expected:
            errors.append({"branch": label, "expected": expected,
                           "actual": actual})
        if not proof["certificate"]["verdict"]:
            errors.append({"branch": label, "certificate":
                           proof["certificate"]})
        if label == "shift" and selected is not None:
            if abs(float(selected["worst_clearance"]) - 0.1859) > 1e-4:
                errors.append({"branch": label, "clearance":
                               selected["worst_clearance"]})

    attempts_path = run_dir / "attempts.kv"
    attempts_path.write_text(
        "".join(staged._attempt_kv_line(args.run_id, attempt) + "\n"
                for proof in proofs for attempt in proof["attempts"]),
        encoding="utf-8",
    )
    pairs_path = run_dir / "pair_results.kv"
    pairs_path.write_text(
        "".join(staged.pair_kv_line(proof) + "\n" for proof in proofs),
        encoding="utf-8",
    )
    analyzer_dir = run_dir / "analyzer_by_pair"
    analyzer_dir.mkdir(parents=True, exist_ok=True)
    analyzer_corpora = []
    for proof in proofs:
        corpus_path = analyzer_dir / f"{staged._safe(proof['pair_id'])}.kv"
        corpus_path.write_text(
            "".join(staged._attempt_kv_line(args.run_id, attempt) + "\n"
                    for attempt in proof["attempts"]),
            encoding="utf-8",
        )
        analyzer_corpora.append({
            "pair_id": proof["pair_id"],
            "path": str(corpus_path.resolve()),
            "sha256": staged._sha256_file(corpus_path),
            "corpus_count": len(proof["attempts"]),
            "expected_selected_candidate_id": proof[
                "selected_candidate_id"],
            "expected_status": proof["status"],
        })
    dynamic_proof = next(proof for proof in proofs
                         if proof["first_successful_stage"] == "multi_move")
    dynamic_selected = next(
        attempt for attempt in dynamic_proof["attempts"]
        if attempt["candidate_id"] == dynamic_proof["selected_candidate_id"])
    exhausted_proof = next(proof for proof in proofs
                           if proof["status"] == "declared_space_exhaustion")
    final_planner = next(attempt for attempt in exhausted_proof["attempts"]
                         if attempt["stage"] == "screw_thread")
    browser_path = run_dir / "browser_replay_rich" / \
        "browser_replay_report.json"
    browser_report = (json.loads(browser_path.read_text(encoding="utf-8"))
                      if browser_path.is_file() else None)
    formal_reports = []
    for report_path in sorted((run_dir / "formal_analyzer").glob(
            "*/formal_analyzer_report.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        formal_reports.append({
            "path": str(report_path.resolve()),
            "sha256": staged._sha256_file(report_path),
            "corpus": report.get("corpus"),
            "corpus_count": report.get("corpus_count"),
            "expected_candidate_id": report.get("expected_candidate_id"),
            "expected_candidate_present": report.get(
                "expected_candidate_present"),
            "provenance_issue_count": report.get("provenance_issue_count"),
            "verdict": report.get("verdict"),
        })
    manifest = {
        "schema_version": "sieve3d-staged-branch-evidence/2",
        "run_id": args.run_id,
        "rows": rows,
        "errors": errors,
        "verdict": not errors,
        "attempts_kv_path": str(attempts_path.resolve()),
        "attempts_kv_sha256": staged._sha256_file(attempts_path),
        "pair_results_kv_path": str(pairs_path.resolve()),
        "pair_results_kv_sha256": staged._sha256_file(pairs_path),
        "analyzer_goals": (
            "full_pass:max,passed_volume_pct:max,solution_actions:min,"
            "solution_keyframes:min,changed_parameter_count:min,"
            "worst_clearance:max,search_attempts:min"),
        "analyzer_by_pair": analyzer_corpora,
        "formal_analyzer_reports": formal_reports,
        "browser_acceptance": ({
            "path": str(browser_path.resolve()),
            "sha256": staged._sha256_file(browser_path),
            "record_path": browser_report.get("record_path"),
            "record_sha256": browser_report.get("record_sha256"),
            "screenshot_path": browser_report.get("screenshot_path"),
            "sample_count": browser_report.get("sample_count"),
            "unique_body_z_count": browser_report.get(
                "unique_body_z_count"),
            "unique_animation_frame_z_count": browser_report.get(
                "unique_animation_frame_z_count"),
            "unique_canvas_hash_count": browser_report.get(
                "unique_canvas_hash_count"),
            "verdict": browser_report.get("verdict"),
        } if browser_report else None),
        "gui_records": {
            "multi_action_success": {
                "record_path": dynamic_selected["record_path"],
                "metadata_path": dynamic_selected["metadata_path"],
                "api_action_count": dynamic_selected[
                    "solution_action_api_calls"],
                "motion_frame_count": dynamic_selected[
                    "record_response_frame_count"],
                "final_status": dynamic_selected["status"],
                "final_passed_pct": dynamic_selected["passed_pct"],
            },
            "planner_motion_failure": {
                "record_path": final_planner["record_path"],
                "metadata_path": final_planner["metadata_path"],
                "api_action_count": final_planner[
                    "solution_action_api_calls"],
                "motion_frame_count": final_planner[
                    "record_response_frame_count"],
                "final_status": final_planner["status"],
                "final_passed_pct": final_planner["passed_pct"],
            },
        },
        "proof_scope": (
            "focused empirical anchors for all six branches; the complete "
            "100-pair matrix is a separate artifact"),
    }
    staged._write_json(run_dir / "branch_manifest.json", manifest)
    print(json.dumps({
        "verdict": manifest["verdict"],
        "run_id": args.run_id,
        "manifest": str((run_dir / "branch_manifest.json").resolve()),
        "branches": [{"label": row["branch_label"],
                      "status": row["status"],
                      "stage": row["first_successful_stage"],
                      "actions": row["minimum_solution_actions"]}
                     for row in rows],
    }, indent=2, sort_keys=True))
    return 0 if manifest["verdict"] else 6


if __name__ == "__main__":
    raise SystemExit(main())
