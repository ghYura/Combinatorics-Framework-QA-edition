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

"""`bundle iterate` — implementation and argparse front end.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from ..cliargs import _add_budget_ceiling_args, _add_bundle_config_args
from ..cliutil import _UNSET, _resolve_bundle_config, _with_db
from ..config import BundleConfig
from ..errors import BundleError, PreflightError, StageError, ok, report_and_exit
from ..jsonio import read_json, write_json_atomic
from ..runs import file_sha256, generate_run_id
from ..stages import preflight


ITERATE_SCHEMA = "bundle.iterate/v1"


def _stage_count_value(run_dir: Path, stage: str, name: str, field: str = "actual"):
    try:
        data = read_json(run_dir / "stages" / f"{stage}.json")
    except FileNotFoundError:
        return None
    for c in data.get("counts", []):
        if c.get("name") == name:
            return c.get(field)
    return None


def _winner_candidate_id(winner: dict) -> str | None:
    kv = winner.get("kvPairs") or {}
    if isinstance(kv, dict):
        for key in ("candidate_id", "combi_id", "id"):
            val = kv.get(key)
            if isinstance(val, str) and val:
                return val
    line = winner.get("originalLine") or ""
    if isinstance(line, str):
        for token in line.split():
            if token.startswith("candidate_id="):
                return token.split("=", 1)[1]
    return None


def _seed_front_ids(seed_doc: dict) -> list[str]:
    winners = seed_doc.get("winners") or []
    front = [_winner_candidate_id(w) for w in winners if isinstance(w, dict) and w.get("role") == "pareto"]
    front = [x for x in front if x]
    if not front:
        front = [_winner_candidate_id(w) for w in winners if isinstance(w, dict)]
        front = [x for x in front if x]
    return sorted(set(front))


def _cmd_iterate(a) -> None:
    # Imported at call time: the orchestrator stays in `cli`, which imports this
    # module, and `cli._run` remains the patchable name it always was.
    from ..cli import _run

    if a.iterations < 1:
        raise PreflightError("--iterations must be >= 1")
    if not a.analyzer or a.analyzer is _UNSET:
        raise PreflightError("bundle iterate requires --analyzer goals; no goals means no winners and no feedback loop")
    if getattr(a, "legacy_scratch", False):
        raise PreflightError("bundle iterate requires journaled run directories; --legacy-scratch is not supported")
    a.seed_output = True
    cfg, _sources = _resolve_bundle_config(a)
    a.main_port, a.results_port, a.mode, a.analyzer = (
        cfg.main_db_port, cfg.results_db_port, cfg.run_mode, cfg.analyzer_goals)
    a.seed_output, a.exploration_floor, a.min_winner_support = (
        cfg.seed_output, cfg.exploration_floor, cfg.min_winner_support)
    spec, _toml_path, scratch = preflight(_with_db(a), cfg)
    runs_root = Path(a.runs_root) if a.runs_root else scratch / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    base_run_id = generate_run_id(a.run_id or None)
    lineage_path = runs_root / f"{base_run_id}-iterate.json"
    lineage = {
        "schema": ITERATE_SCHEMA,
        "status": "RUNNING",
        "base_run_id": base_run_id,
        "spec_name": spec.name,
        "db": a.db,
        "iterations_requested": a.iterations,
        "stop_when_stable": a.stop_when_stable,
        "exploration_floor": cfg.exploration_floor,
        "min_winner_support": cfg.min_winner_support,
        "iterations": [],
    }
    write_json_atomic(lineage_path, lineage)

    previous_seed = None
    previous_front: set[str] | None = None
    stable = 0
    final_status = "COMPLETED"
    for i in range(1, a.iterations + 1):
        it = argparse.Namespace(**vars(a))
        it.run_id = f"{base_run_id}-it{i}"
        it.runs_root = str(runs_root)
        it.seed_output = True
        it.seed_from = str(previous_seed) if previous_seed is not None else ""
        it.sieve = bool(getattr(a, "sieve", False) or it.seed_from)
        it.draw = False
        it.draw_exact = False
        it.legacy_scratch = False
        it.legacy_handoff = getattr(a, "legacy_handoff", False)
        print(f"\n[iterate {i}/{a.iterations}] run_id={it.run_id}" + (f" seed_from={it.seed_from}" if it.seed_from else " full-space seed run"))
        try:
            _run(it)
        except BundleError as exc:
            final_status = "FAILED"
            lineage["status"] = final_status
            lineage["error"] = str(exc)
            write_json_atomic(lineage_path, lineage)
            raise
        run_dir = runs_root / it.run_id
        seed_path = run_dir / "bundle_seed.json"
        if not seed_path.exists() or seed_path.stat().st_size == 0:
            final_status = "FAILED"
            lineage["status"] = final_status
            lineage["error"] = f"iteration {i} produced no bundle_seed.json; candidates may emit no harvestable metrics"
            write_json_atomic(lineage_path, lineage)
            raise StageError(lineage["error"])
        seed_doc = read_json(seed_path)
        front_ids = _seed_front_ids(seed_doc)
        if not front_ids:
            final_status = "FAILED"
            lineage["status"] = final_status
            lineage["error"] = f"iteration {i} seed has no joinable Pareto/front candidate ids"
            write_json_atomic(lineage_path, lineage)
            raise StageError(lineage["error"])
        front_set = set(front_ids)
        if previous_front is not None and front_set == previous_front:
            stable += 1
        else:
            stable = 0
        previous_front = front_set

        plan_path = run_dir / "bias_plan.json"
        plan_doc = read_json(plan_path) if plan_path.exists() else None
        plan_status = (plan_doc or {}).get("status") if isinstance(plan_doc, dict) else None
        entry = {
            "iteration": i,
            "run_id": it.run_id,
            "run_dir": str(run_dir),
            "input_seed": str(previous_seed) if previous_seed is not None else None,
            "input_seed_sha256": file_sha256(previous_seed) if previous_seed is not None else None,
            "seed": str(seed_path),
            "seed_sha256": file_sha256(seed_path),
            "plan": str(plan_path) if plan_path.exists() else None,
            "plan_sha256": file_sha256(plan_path) if plan_path.exists() else None,
            "candidate_count": _stage_count_value(run_dir, "reader", "candidates"),
            "core_fw_final": _stage_count_value(run_dir, "core", "fw_final"),
            "post_sieve": _stage_count_value(run_dir, "sieve", "post_sieve"),
            "pre_bias_estimate": _stage_count_value(run_dir, "seed_bias", "pre_bias_estimate"),
            "post_bias_estimate": _stage_count_value(run_dir, "seed_bias", "post_bias_estimate"),
            "winner_count": len(seed_doc.get("winners") or []),
            "front_ids": front_ids,
            "stable_transitions": stable,
            "plan_status": plan_status,
        }
        lineage["iterations"].append(entry)
        lineage["status"] = "RUNNING"
        write_json_atomic(lineage_path, lineage)
        pre = entry["pre_bias_estimate"] or entry["candidate_count"] or "?"
        post = entry["candidate_count"] or entry["post_bias_estimate"] or "?"
        keep = "?"
        if isinstance(pre, int) and isinstance(post, int) and pre:
            keep = f"{(post / pre) * 100:.1f}%"
        print(f"[iterate {i}/{a.iterations}] candidates {pre}->{post} (bias kept {keep}) · front={len(front_ids)} · stable={stable}/{a.stop_when_stable or '-'}")
        previous_seed = seed_path
        if plan_status == "CONVERGED_NO_SIGNAL":
            final_status = "CONVERGED_NO_SIGNAL"
            break
        if a.stop_when_stable and stable >= a.stop_when_stable:
            final_status = "STABLE_FRONT"
            break
    lineage["status"] = final_status
    write_json_atomic(lineage_path, lineage)
    ok(f"iterate -> {lineage_path} ({final_status})")


def _main_iterate(argv):
    ap = argparse.ArgumentParser(prog="bundle_run iterate",
                                 description="Run Bundle N times, biasing iteration i+1 from iteration i's BundleSeed")
    ap.add_argument("spec_dir")
    ap.add_argument("--db", default="")
    ap.add_argument("--lang", default="py", choices=["py", "python", "java"])
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--stop-when-stable", type=int, default=0, metavar="K")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--runs-root", default="")
    ap.add_argument("--main-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"main DB port (default: {BundleConfig().main_db_port})")
    ap.add_argument("--results-port", type=int, default=_UNSET, metavar="PORT",
                    help=f"results DB port (default: {BundleConfig().results_db_port})")
    ap.add_argument("--analyzer", required=True,
                    help='AnalyzeKv goals, e.g. "dq_score:max,latency_ms:min"')
    ap.add_argument("--analysis-mode", default="exploratory", choices=["formal", "exploratory"])
    ap.add_argument("--mode", default=_UNSET, choices=["verdict", "stress"])
    ap.add_argument("--sieve", action="store_true")
    ap.add_argument("--seed-from", default="")
    ap.add_argument("--base-url", default="http://127.0.0.1:8121")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--duration", type=float, default=10)
    ap.add_argument("--ramp", type=float, default=3)
    ap.add_argument("--slo-p99", type=float, default=1500)
    ap.add_argument("--err-budget", type=float, default=0.01)
    ap.add_argument("--legacy-scratch", action="store_true")
    ap.add_argument("--legacy-handoff", action="store_true")
    _add_budget_ceiling_args(ap)
    ap.add_argument("--override-budget", default=None, metavar="REASON")
    ap.add_argument("--allow-extreme", action="store_true")
    ap.add_argument("--unleash-initial-productivity-power", dest="unleash_initial_productivity_power",
                    default=_UNSET, action="store_const", const=True)
    ap.add_argument("--cost-per-candidate", type=float, default=None, metavar="PRICE")
    _add_bundle_config_args(ap)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args(argv)
    try:
        _cmd_iterate(a)
    except BundleError as exc:
        report_and_exit(exc, debug=a.debug)
