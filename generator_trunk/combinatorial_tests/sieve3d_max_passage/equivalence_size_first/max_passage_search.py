#!/usr/bin/env python3
"""Legacy best-hole diagnostics plus compatibility planner probes.

The proof-bearing all-body/all-hole implementation now lives in
``staged_passage_search.py`` and is re-exported below.  The historical
best-hole helpers remain only so the separate API-planner feedback use case and
its old replay artifacts stay regression-testable; they are not used for a
minimality or exhaustion claim.

The legacy diagnostics separate two phases:

1. classify one selected 3D body against every 2D sieve hole by shape
   equivalence class, symmetry, and size ratio;
2. only then try bounded movement profiles and rank by the criteria
   requested in Criterias05072026: passed volume first, fewer actions next.

The functions at the bottom are intentionally small and stateful because they
are called from generated Bundle candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

GENERATOR_ROOT = Path(__file__).resolve().parents[3]
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from sut_paths import project_path  # noqa: E402

SIEVE3D_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT", str(project_path("sieve3d"))))
if str(SIEVE3D_ROOT) not in sys.path:
    sys.path.insert(0, str(SIEVE3D_ROOT))

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE.parent.parent / "sieve3d_complex_bodies"
if str(CASES_DIR) not in sys.path:
    sys.path.insert(0, str(CASES_DIR))

import complex_cases as cc  # noqa: E402
import staged_passage_search as staged  # noqa: E402
from shapely import affinity  # noqa: E402
from sieve3d import api_v1, profiles  # noqa: E402
from sieve3d.bodies import build_body  # noqa: E402


BODY_CASES = tuple(cc.BODIES)
TARGET_PCT = {name: 100.0 for name in BODY_CASES}

# Primary proof API re-exports.  New callers should import
# staged_passage_search directly; these aliases keep the likely historical
# import path useful without routing them through the bounded best-hole logic.
SearchConfig = staged.SearchConfig
generate_pair_universe = staged.generate_pair_universe
generate_pair_universe_twice = staged.generate_pair_universe_twice
execute_pair_universe = staged.execute_pair_universe
verify_pair_documents = staged.verify_pair_documents
verify_pair_proof = staged.verify_pair_proof
run_matrix = staged.run_matrix
exact_full_pass = staged.exact_full_pass

POSE_KEYS = ("spin", "tilt", "turn", "dx", "dy")
ANCHOR_SEEDS = (
    ("axis", 0.0, 0.0),
    ("side_x", 0.0, 90.0),
    ("side_y", 90.0, 90.0),
    ("oblique", 45.0, 55.0),
    ("spin90", 90.0, 0.0),
    ("wave_side", 270.0, 90.0),
)
CANONICAL_POSES = (
    ("axial", {"spin": 0, "tilt": 0, "turn": 0}),
    ("front", {"spin": 0, "tilt": 90, "turn": 0}),
    ("side", {"spin": 0, "tilt": 90, "turn": 90}),
    ("side_spin90", {"spin": 90, "tilt": 90, "turn": 180}),
    ("wave_phase", {"spin": 270, "tilt": 90, "turn": 90}),
)
MOVE_PROFILES = {
    "min_direct": (
        {"name": "direct", "max_steps": 1},
    ),
    "max_step_ladder": (
        {"name": "direct", "max_steps": 1},
        {"name": "step_coarse", "step": 4.0, "max_steps": 24},
        {"name": "step_fine", "step": 1.0, "max_steps": 96},
        {"name": "wiggle", "dz": 1.0, "rounds": 60, "max_steps": 60},
    ),
}

# Ranking policies only have an observable effect when execution is bounded.
# Four holes retain both known plug projections while keeping generated runs
# tractable; a campaign's dynamic target is added even when static fits says no.
MOVEMENT_HOLE_BUDGET = 4
TRACE_FRAME_DELAY_S = 0.02

# Only objective values belong in the Bundle optimizer. Candidate coverage,
# API counters, feature counts, and search depth remain emitted diagnostics and
# contract gates; maximizing them would reward duplicated or expensive work.
CRITERIA_METRICS = {
    "passed_volume_pct": "max",
    "planner_passed_volume_pct": "max",
    "actions": "min",
    "attempts": "min",
    "planner_estimated_cost": "min",
}
CRITERIA_TOKEN = ",".join(
    "%s:%s" % (key, direction) for key, direction in CRITERIA_METRICS.items())
PLANNER_ALGORITHMS = ("direct-drop", "feedback-thread", "lookahead-thread")
PLANNER_PORTFOLIOS: dict[str, tuple[str, ...] | None] = {
    "direct_baseline": ("direct-drop",),
    "feedback_portfolio": ("direct-drop", "feedback-thread"),
    "core_portfolio": PLANNER_ALGORITHMS,
    # None means every algorithm advertised by this request's live catalog.
    "catalog_portfolio": None,
}
PROOF_PORTFOLIOS = ("direct_baseline", "feedback_portfolio")
PLANNER_PROBE_CASES = {
    "plug_triangle": {
        "body": "plug", "hole": "triangle",
        "pose": {"spin": 90, "tilt": 90, "turn": 180, "dy": 1.75},
        "pose_class": "tri_projection", "min_pct": 99.0,
        "expect_feedback": False,
    },
    "pierced_square": {
        "body": "pierced_cube", "hole": "square_snug",
        "pose": {"spin": 0, "tilt": 0, "turn": 0},
        "pose_class": "outer_square", "min_pct": 99.0,
        "expect_feedback": False,
    },
    "snake_eye": {
        "body": "snake", "hole": "eye_snake",
        "pose": {"spin": 90, "tilt": 12, "turn": -90},
        "pose_class": "feedback_thread", "min_pct": 95.0,
        "expect_feedback": True,
    },
}


@dataclass
class Context:
    body: str = "plug"
    holes: list[str] = field(default_factory=list)
    size_rule: str = "clearance_first"
    move_profile: str = "min_direct"
    observers: list[str] = field(default_factory=list)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    movements: list[dict[str, Any]] = field(default_factory=list)
    best: dict[str, Any] | None = None
    planner: dict[str, Any] | None = None
    record_requested: bool = False
    rec_file: str = "none"
    rec_json: str = "none"
    last_error: str = "none"
    metrics: dict[str, float] = field(default_factory=lambda: {
        "passed_volume_pct": 0.0,
        "actions": 0,
        "attempts": 0,
        "clearance": -1e9,
        "geometric_candidates": 0,
        "hole_classes": 0,
        "movement_candidates": 0,
        "min_move_steps": 0,
        "max_move_steps": 0,
        "record_steps": 0,
        "record_trace_frames": 0,
        "record_trace_steps": 0,
        "api_calls": 0,
        "planner_passed_volume_pct": 0.0,
        "planner_success": 0,
        "planner_catalog_algorithms": 0,
        "planner_requested_algorithms": 0,
        "planner_algorithms": 0,
        "planner_candidates": 0,
        "planner_keyframes": 0,
        "planner_evals": 0,
        "planner_cycles": 0,
        "planner_estimated_cost": 0,
        "feature_points": 0,
        "feature_edges": 0,
        "feature_centers": 0,
    })


CTX = Context()


def reset() -> None:
    global CTX
    CTX = Context()


def _safe(text: Any) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_"
                   for ch in str(text))[:180] or "x"


def _normal_pose(pose: dict[str, Any] | None) -> dict[str, float]:
    src = pose or {}
    return {key: float(src.get(key, 0.0) or 0.0) for key in POSE_KEYS}


def _profile_params(spec: dict[str, Any]) -> dict[str, Any]:
    params = dict(spec.get("params") or {})
    for key in ("offset", "angle", "fillet"):
        if key in spec:
            params[key] = spec[key]
    return params


def _shape_family(spec: dict[str, Any]) -> str:
    kind = str(spec.get("kind", "unknown"))
    params = _profile_params(spec)
    if kind == "formula":
        return "formula:%s" % params.get("mode", "unknown")
    if kind == "ring":
        return "ring:island"
    return kind


def _numeric_size_params(spec: dict[str, Any]) -> dict[str, float]:
    params = _profile_params(spec)
    keys = ("r", "rx", "ry", "a", "length", "r_outer", "r_inner", "w",
            "h", "w_bottom", "w_top", "x0", "x1", "offset")
    out = {}
    for key in keys:
        value = params.get(key)
        if isinstance(value, (int, float)):
            out[key] = round(float(value), 4)
    return out


def _clean_poly(poly):
    if poly.is_empty:
        return poly
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.geom_type != "Polygon":
        poly = poly.convex_hull
    return poly


def _symmetry_order(poly) -> int | str:
    poly = _clean_poly(poly)
    if poly.is_empty or poly.area <= 1e-9:
        return 1
    hits = []
    for k in (12, 8, 6, 5, 4, 3, 2):
        rot = affinity.rotate(poly, 360.0 / k, origin=(0, 0))
        if poly.symmetric_difference(rot).area < 0.01 * poly.area:
            hits.append(k)
    if 12 in hits and 8 in hits:
        return "inf"
    return max(hits) if hits else 1


def _shape_signature(poly) -> dict[str, Any]:
    poly = _clean_poly(poly)
    area = float(poly.area)
    per = float(poly.length)
    convex = bool(poly.convex_hull.area - area <= 1e-3 * max(area, 1.0))
    minx, miny, maxx, maxy = poly.bounds
    return {
        "area": round(area, 3),
        "perimeter": round(per, 3),
        "convex": convex,
        "symmetry": _symmetry_order(poly),
        "compactness": round(4 * math.pi * area / max(per * per, 1e-9), 4),
        "bbox": [round(v, 3) for v in (minx, miny, maxx, maxy)],
    }


# Geometry is expressed in millimetres. Fixed absolute quanta preserve scale;
# the previous area / (2% of itself) expression collapsed every area > 25 to
# the same value 50 and therefore did not define a size equivalence at all.
def _projection_equivalence_key(sig: dict[str, Any]) -> tuple[Any, ...]:
    bbox = list(sig.get("bbox") or (0.0, 0.0, 0.0, 0.0))
    width = abs(float(bbox[2]) - float(bbox[0])) if len(bbox) == 4 else 0.0
    height = abs(float(bbox[3]) - float(bbox[1])) if len(bbox) == 4 else 0.0
    short, long = sorted((width, height))
    return (
        int(round(float(sig.get("area") or 0.0) / 0.5)),
        int(round(float(sig.get("perimeter") or 0.0) / 0.25)),
        int(round(short / 0.25)),
        int(round(long / 0.25)),
        bool(sig.get("convex")),
        str(sig.get("symmetry", 1)),
    )


def _signature_scale_token(sig: dict[str, Any]) -> str:
    key = _projection_equivalence_key(sig)
    return "a%d-p%d-b%d_%d" % (key[0], key[1], key[2], key[3])


def _hole_signature(hole: str) -> dict[str, Any]:
    spec = cc.HOLES[hole]
    poly = profiles.build(spec, quality=0.6)
    sig = _shape_signature(poly)
    sig.update({
        "hole": hole,
        "family": _shape_family(spec),
        "size_params": _numeric_size_params(spec),
    })
    return sig


def _body_projection_index(body: str) -> dict[str, Any]:
    obj = build_body(cc.BODIES[body])
    projections = obj.projections(0.6)
    classes = {}
    min_area = None
    for view, poly in projections.items():
        sig = _shape_signature(poly)
        min_area = sig["area"] if min_area is None else min(min_area,
                                                            sig["area"])
        key = _projection_equivalence_key(sig)
        entry = classes.setdefault(
            key, {"views": [], "signature": sig,
                  "equivalence_key": list(key)})
        entry["views"].append(view)
    return {"classes": list(classes.values()), "min_projection_area": min_area}


def _size_bucket(area_ratio: float) -> str:
    if area_ratio < 0.75:
        return "too_small"
    if area_ratio < 1.08:
        return "snug"
    if area_ratio < 1.8:
        return "generous"
    return "oversized"


def _best_projection_match(proj_index: dict[str, Any],
                           hole_sig: dict[str, Any]) -> str:
    best = None
    for cls in proj_index["classes"]:
        sig = cls["signature"]
        area_gap = abs(float(sig["area"]) - float(hole_sig["area"]))
        sym_bonus = 0 if str(sig["symmetry"]) == str(hole_sig["symmetry"]) else 1
        key = (sym_bonus, area_gap)
        if best is None or key < best[0]:
            best = (key, cls)
    return "+".join(best[1]["views"]) if best else "unknown"


def _campaign_pose(body: str, hole: str) -> list[tuple[str, dict[str, float]]]:
    out = []
    for camp in cc.CAMPAIGNS:
        if camp.get("body") != body or camp.get("hole") != hole:
            continue
        pose = camp.get("pose")
        if isinstance(pose, dict):
            out.append(("campaign", _normal_pose(pose)))
    return out


def _candidate_poses(h, body: str, hole: str) -> list[tuple[str, dict[str, float]]]:
    poses: list[tuple[str, dict[str, float]]] = []
    seen = set()

    def add(name: str, pose: dict[str, Any]) -> None:
        p = _normal_pose(pose)
        key = tuple(round(p[k], 3) for k in POSE_KEYS)
        if key not in seen:
            seen.add(key)
            poses.append((name, p))

    for name, pose in _campaign_pose(body, hole):
        add(name, pose)
    for name, pose in CANONICAL_POSES:
        add(name, pose)
    for name, spin, tilt in ANCHOR_SEEDS:
        try:
            anchored = h.call("POST", "/api/v1/anchor", api_v1.h_anchor,
                              {"body": body, "hole": hole,
                               "spin": spin, "tilt": tilt})
            add("anchor_%s" % name, anchored.get("pose") or {})
        except Exception:
            continue
    return poses


def _pose_fit(h, body: str, hole: str,
              pose: dict[str, float]) -> dict[str, Any]:
    try:
        fit = h.fits(body, hole, pose)
        return {
            "ok": True,
            "feasible": bool(fit.get("feasible")),
            "clearance": float(fit.get("clearance")
                               if fit.get("clearance") is not None else -1e9),
            "pose": _normal_pose(fit.get("pose") or pose),
        }
    except api_v1.ApiError as exc:
        return {"ok": False, "feasible": False, "clearance": -1e9,
                "pose": _normal_pose(pose), "error": exc.code}


def rank_holes(body: str, holes: list[str] | None = None,
               size_rule: str = "clearance_first") -> list[dict[str, Any]]:
    holes = list(holes or cc.HOLES)
    h = cc.make_scene([body], holes)
    proj_index = _body_projection_index(body)
    min_proj_area = float(proj_index["min_projection_area"] or 1.0)
    rows = []
    for hole in holes:
        hole_sig = _hole_signature(hole)
        best = {"feasible": False, "clearance": -1e9,
                "pose": _normal_pose(None), "pose_class": "none"}
        for pose_class, pose in _candidate_poses(h, body, hole):
            fit = _pose_fit(h, body, hole, pose)
            if fit["clearance"] > best["clearance"]:
                best = {**fit, "pose_class": pose_class}
        ratio = float(hole_sig["area"]) / min_proj_area
        bucket = _size_bucket(ratio)
        rows.append({
            "body": body,
            "hole": hole,
            "hole_class": "%s|sym=%s|convex=%s|size=%s|scale=%s" % (
                hole_sig["family"], hole_sig["symmetry"],
                hole_sig["convex"], bucket,
                _signature_scale_token(hole_sig)),
            "hole_signature": hole_sig,
            "body_projection_match": _best_projection_match(proj_index,
                                                            hole_sig),
            "area_ratio_to_min_projection": round(ratio, 4),
            "size_bucket": bucket,
            "feasible": bool(best["feasible"] and best["clearance"] > 0.0),
            "clearance": round(float(best["clearance"]), 4),
            "pose": best["pose"],
            "pose_class": best["pose_class"],
        })

    if size_rule == "snug_first":
        rows.sort(key=lambda r: (
            not r["feasible"],
            abs(float(r["area_ratio_to_min_projection"]) - 1.0),
            -float(r["clearance"]),
            r["hole"],
        ))
    else:
        rows.sort(key=lambda r: (
            not r["feasible"],
            -float(r["clearance"]),
            abs(float(r["area_ratio_to_min_projection"]) - 1.0),
            r["hole"],
        ))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def _record_start(h) -> None:
    h.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "action"})


def _record_finish(
        h,
        label: str,
        metadata: dict[str, Any] | None = None,
) -> tuple[str, str, int]:
    try:
        h.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "cut"})
    except api_v1.ApiError as exc:
        if exc.code != "conflict":
            raise
    info = h.call("POST", "/api/v1/record", api_v1.h_record,
                  {"cmd": "retrieve_last_record"})
    out_dir = Path(os.environ.get("SIEVE3D_REC_OUT_DIR",
                                  tempfile.gettempdir()))
    out_dir = out_dir / "sieve3d_rec_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "sieve3d_max_passage_%s_%d_%d" % (
        _safe(label), os.getpid(), int(time.time() * 1000))
    rec_path = out_dir / (stem + ".rec")
    json_path = out_dir / (stem + ".json")
    records = info.get("records") or []
    if not records:
        raise RuntimeError("record_retrieval_returned_no_entries")
    rec_path.write_text("\n".join(json.dumps(r, ensure_ascii=True)
                                  for r in records) + "\n",
                        encoding="utf-8")
    artifact = {
        "format": "sieve3d-rec/1",
        "file": info.get("file"),
        "source_path": info.get("path"),
        "steps_count": int(info.get("steps_count", 0)),
        "saved_rec": str(rec_path),
        "saved_json": str(json_path),
        "manual_replay": {
            "copy_to": str(SIEVE3D_ROOT / "records" / rec_path.name),
            "api_path": "/api/v1/replay",
            "api_payload": {"file": rec_path.name, "speed": 0.1},
            "gui_action": "copy_to_records_then_press_Replay",
        },
    }
    artifact.update(metadata or {})
    json_path.write_text(json.dumps(artifact, sort_keys=True),
                         encoding="utf-8")
    return str(rec_path), str(json_path), int(info.get("steps_count", 0))


def _run_direct(h, body: str, hole: str,
                pose: dict[str, float]) -> None:
    """Historical diagnostic direct action, now genuinely neutral.

    The ``pose`` argument is retained for call compatibility but deliberately
    ignored.  Pose-specific static retries belong to the staged engine.
    """
    h.act(body, "assign", hole=hole)
    h.act(body, "drop", max_dz=300)


def _run_stepwise(h, body: str, hole: str, pose: dict[str, float],
                  step: float, max_steps: int) -> bool:
    h.act(body, "assign", hole=hole)
    st = h.act(body, "set_pose", **pose)["state"]
    last_pct = float(st["passed_pct"])
    monotone = True
    for _ in range(max_steps):
        snap = h.exp()["bodies"][body]
        if snap["status"] == "passed":
            break
        try:
            st = h.act(body, "set_z", z=float(snap["z"]) - step)["state"]
        except api_v1.ApiError:
            break
        if float(st["passed_pct"]) + 1e-6 < last_pct:
            monotone = False
            break
        last_pct = float(st["passed_pct"])
    return monotone


def _run_wiggle(h, body: str, hole: str, pose: dict[str, float],
                dz: float, rounds: int) -> bool:
    h.act(body, "assign", hole=hole)
    h.act(body, "set_pose", **pose)
    try:
        h.act(body, "drop", max_dz=300)
    except api_v1.ApiError:
        pass
    prev_z = float(h.exp()["bodies"][body]["z"])
    monotone = True
    for _ in range(rounds):
        st = h.act(body, "wiggle", dz=dz, evals=45)["state"]
        if float(st["z"]) > prev_z + 1e-9:
            monotone = False
            break
        prev_z = float(st["z"])
        if st["status"] == "passed":
            break
    return monotone


def run_movement(body: str, ranked: dict[str, Any], strategy: dict[str, Any],
                 *, record: bool = False) -> dict[str, Any]:
    hole = ranked["hole"]
    h = cc.make_scene([body], [hole])
    if record:
        _record_start(h)
    error = "none"
    monotone = True
    try:
        if strategy["name"] == "direct":
            _run_direct(h, body, hole, ranked["pose"])
        elif strategy["name"] in ("step_coarse", "step_fine"):
            monotone = _run_stepwise(h, body, hole, ranked["pose"],
                                     float(strategy["step"]),
                                     int(strategy["max_steps"]))
        elif strategy["name"] == "wiggle":
            monotone = _run_wiggle(h, body, hole, ranked["pose"],
                                   float(strategy["dz"]),
                                   int(strategy["rounds"]))
        else:
            raise ValueError("unknown movement strategy %r" %
                             strategy["name"])
    except api_v1.ApiError as exc:
        error = exc.code
    except Exception as exc:
        error = type(exc).__name__

    snap = h.exp()
    st = snap["bodies"][body]
    out = {
        "body": body,
        "hole": hole,
        "hole_class": ranked["hole_class"],
        "size_bucket": ranked["size_bucket"],
        "pose_class": ranked["pose_class"],
        "strategy": strategy["name"],
        "strategy_max_steps": int(strategy.get("max_steps",
                                               strategy.get("rounds", 1))),
        "passed_pct": float(st["passed_pct"]),
        "status": st["status"],
        "actions": int(st["actions"]),
        "attempts": int(st["attempts"]),
        "effort": float(st["effort"]),
        "clearance": float(ranked["clearance"]),
        "api_calls": int(getattr(h, "api_calls", 0)),
        "monotone": bool(monotone),
        "error": error,
        "pose": ranked["pose"],
        "record_file": "none",
        "record_json": "none",
        "record_steps": 0,
    }
    if record:
        rec_file, rec_json, steps = _record_finish(
            h, "%s_%s_%s" % (body, hole, strategy["name"]))
        out["record_file"] = rec_file
        out["record_json"] = rec_json
        out["record_steps"] = steps
    return out


def _feature_counts(features: dict[str, Any]) -> dict[str, int]:
    counts = {"feature_points": 0, "feature_edges": 0, "feature_centers": 0}
    for owner in ("body", "hole"):
        group = features.get(owner) or {}
        edges = group.get("edges") or []
        centers = group.get("edge_centers") or []
        vertices = group.get("vertices") or []
        whole = group.get("whole") or {}
        counts["feature_edges"] += len(edges)
        counts["feature_centers"] += len(centers)
        counts["feature_points"] += len(centers) + len(vertices)
        if isinstance(whole, dict) and whole.get("center") is not None:
            counts["feature_points"] += 1
    return counts


def _resolve_planner_algorithms(
        available: list[str] | tuple[str, ...],
        request: tuple[str, ...] | list[str] | str | None,
) -> tuple[str, list[str]]:
    """Resolve one request without imposing unrelated global algorithms."""
    advertised = list(dict.fromkeys(str(name) for name in available if name))
    if not advertised:
        raise RuntimeError("no_passage_algorithms_advertised")

    label = "custom"
    if isinstance(request, str):
        label = request
        if request in PLANNER_PORTFOLIOS:
            configured = PLANNER_PORTFOLIOS[request]
            requested = advertised if configured is None else list(configured)
        else:
            requested = [request]
    elif request is None:
        label = "catalog_portfolio"
        requested = advertised
    else:
        requested = list(dict.fromkeys(str(name) for name in request if name))

    missing = [name for name in requested if name not in advertised]
    if missing:
        raise RuntimeError(
            "catalog_missing_requested_passage_algorithms:%s" %
            ",".join(missing))
    if not requested:
        raise RuntimeError("empty_passage_algorithm_request")
    return label, requested

def _frame_pose(frame: dict[str, Any]) -> dict[str, float]:
    values = list(frame.get("pose") or ())
    if len(values) < len(POSE_KEYS):
        raise RuntimeError("planner_frame_missing_pose")
    return {key: float(values[i]) for i, key in enumerate(POSE_KEYS)}


def _record_visible_trace(
        h,
        body: str,
        hole: str,
        best: dict[str, Any],
) -> dict[str, Any]:
    """Apply every safe planner frame through the external experiment API."""
    frames = [
        frame for frame in (best.get("frames") or ())
        if frame.get("z") is not None and frame.get("ok") is not False
        and len(frame.get("pose") or ()) >= len(POSE_KEYS)
    ]
    if len(frames) < 4:
        raise RuntimeError("planner_returned_too_few_visible_frames")

    assigned = h.act(body, "assign", hole=hole)["state"]
    safe_z = max(
        float(assigned["z"]),
        max(float(frame["z"]) for frame in frames),
    ) + 5.0
    h.act(body, "set_z", z=safe_z)
    h.act(body, "set_pose", **_frame_pose(frames[0]), z=safe_z)

    states = []
    for index, frame in enumerate(frames):
        if index:
            time.sleep(TRACE_FRAME_DELAY_S)
        state = h.act(
            body,
            "set_pose",
            **_frame_pose(frame),
            z=float(frame["z"]),
        )["state"]
        states.append({
            "frame": index,
            "z": float(state["z"]),
            "pose": dict(state["pose"]),
            "passed_pct": float(state["passed_pct"]),
            "status": str(state["status"]),
        })
    return {
        "record_trace_frames": len(frames),
        "record_trace_steps": len(frames) + 3,
        "record_trace_states": states,
    }



def run_planner(
        body: str,
        ranked: dict[str, Any],
        algorithms: tuple[str, ...] | list[str] | str | None = PLANNER_ALGORITHMS,
        *,
        record: bool = False,
        record_label: str | None = None,
) -> dict[str, Any]:
    """Exercise a request-scoped portfolio against the live API catalog."""
    hole = ranked["hole"]
    h = cc.make_scene([body], [hole])
    catalog = h.call("GET", "/api/v1/catalog", api_v1.h_catalog, {})
    available = list(catalog.get("passage_algorithms") or [])
    portfolio, requested = _resolve_planner_algorithms(available, algorithms)

    pose = ranked.get("pose") or {}
    feat = h.call("POST", "/api/v1/features", api_v1.h_features,
                  {"body": body, "hole": hole, "pose": pose})
    feature_counts = _feature_counts(feat.get("features") or {})
    if feature_counts["feature_points"] <= 0 or feature_counts["feature_edges"] <= 0:
        raise RuntimeError("features_not_interactable")

    passage_payload = {
        "body": body, "hole": hole, "pose": pose, "wait": True,
        "frames": 24, "algorithms": requested, "budget": "normal",
        "max_candidates": 3, "rounds": 1, "evals": 24,
        "starts": 1, "lookahead": 1, "max_steps": 160, "retreats": 2,
        "kp": 0.7, "ki": 0.05, "kd": 0.22,
    }
    if record:
        _record_start(h)
    result = h.call("POST", "/api/v1/passage", api_v1.h_passage,
                    passage_payload)
    if record and int(getattr(h.recorder, "steps", 0)) == 0:
        # Compatibility with SUT versions predating /passage in V1_MUT.
        h.recorder.log("v1", "POST", "/api/v1/passage", passage_payload)

    ranked_algorithms = result.get("ranked") or []
    complexity = result.get("complexity") or {}
    best = result.get("best") or {}
    if int(complexity.get("algorithms") or len(ranked_algorithms)) < len(requested):
        raise RuntimeError("planner_algorithm_count_mismatch")
    best_algorithm = best.get("algorithm") or (ranked_algorithms[0].get("algorithm")
                                               if ranked_algorithms else "none")
    if best_algorithm == "none":
        raise RuntimeError("planner_missing_best_algorithm")

    rec_file, rec_json, rec_steps = "none", "none", 0
    trace_info = {
        "record_trace_frames": 0,
        "record_trace_steps": 0,
        "record_trace_states": [],
    }
    if record:
        trace_info = _record_visible_trace(h, body, hole, best)
    if record:
        rec_file, rec_json, rec_steps = _record_finish(
            h,
            record_label or "%s_%s_%s" % (body, hole, portfolio),
            metadata={
                "body": body,
                "hole": hole,
                "portfolio": portfolio,
                "requested_algorithms": list(requested),
                "best_algorithm": best_algorithm,
                "passed_pct": float(best.get("passed_pct") or 0.0),
                **trace_info,
            },
        )
    return {
        "body": body,
        "hole": hole,
        "portfolio": portfolio,
        "catalog_algorithms": available,
        "requested_algorithms": requested,
        "best_algorithm": best_algorithm,
        "passed_pct": float(best.get("passed_pct") or 0.0),
        "success": int(bool(best.get("success"))),
        "complexity": complexity,
        "ranked": ranked_algorithms,
        "features": feature_counts,
        "record_file": rec_file,
        "record_json": rec_json,
        "record_steps": rec_steps,
        **trace_info,
        "api_calls": int(getattr(h, "api_calls", 0)),
    }


def _apply_planner_metrics(planner: dict[str, Any]) -> None:
    pc = planner.get("complexity") or {}
    pf = planner.get("features") or {}
    CTX.metrics.update({
        "planner_catalog_algorithms": len(
            planner.get("catalog_algorithms") or ()),
        "planner_requested_algorithms": len(
            planner.get("requested_algorithms") or ()),
        "planner_passed_volume_pct": planner["passed_pct"],
        "planner_success": planner["success"],
        "planner_algorithms": int(pc.get("algorithms") or 0),
        "planner_candidates": int(pc.get("candidates") or 0),
        "planner_keyframes": int(pc.get("keyframes") or 0),
        "planner_evals": int(pc.get("evals") or 0),
        "planner_cycles": int(pc.get("cycles") or 0),
        "planner_estimated_cost": int(pc.get("estimated_cost") or 0),
        "feature_points": int(pf.get("feature_points") or 0),
        "feature_edges": int(pf.get("feature_edges") or 0),
        "feature_centers": int(pf.get("feature_centers") or 0),
    })
    CTX.metrics["api_calls"] += int(planner.get("api_calls") or 0)


def run_api_probe(
        case_id: str,
        algorithms: tuple[str, ...] | list[str] | str | None = PLANNER_ALGORITHMS,
        *,
        record: bool = True,
) -> dict[str, Any]:
    """Small Bundle-facing probe for the latest planner/features API."""
    if case_id not in PLANNER_PROBE_CASES:
        raise KeyError(case_id)
    case = PLANNER_PROBE_CASES[case_id]
    ranked = {
        "hole": case["hole"],
        "hole_class": "api_planner_feedback",
        "size_bucket": "selected",
        "pose_class": case["pose_class"],
        "pose": dict(case["pose"]),
        "clearance": 0.0,
    }
    CTX.body = case["body"]
    CTX.holes = [case["hole"]]
    CTX.size_rule = "api_planner_feedback"
    CTX.move_profile = case_id
    CTX.ranking = [ranked]
    CTX.movements = []
    CTX.planner = run_planner(
        case["body"], ranked, algorithms, record=record)
    CTX.rec_file = str(CTX.planner.get("record_file") or "none")
    CTX.rec_json = str(CTX.planner.get("record_json") or "none")
    CTX.metrics["record_steps"] = int(
        CTX.planner.get("record_steps") or 0)
    CTX.metrics["record_trace_frames"] = int(
        CTX.planner.get("record_trace_frames") or 0)
    CTX.metrics["record_trace_steps"] = int(
        CTX.planner.get("record_trace_steps") or 0)
    CTX.planner["case_id"] = case_id
    CTX.planner["expect_feedback"] = bool(case.get("expect_feedback"))
    _apply_planner_metrics(CTX.planner)
    CTX.metrics.update({
        "passed_volume_pct": CTX.planner["passed_pct"],
        "actions": 0,
        "attempts": 0,
        "clearance": float(ranked["clearance"]),
        "geometric_candidates": 1,
        "hole_classes": 1,
        "movement_candidates": 1,
        "min_move_steps": 0,
        "max_move_steps": int(CTX.metrics.get("planner_keyframes", 0)),
    })
    CTX.best = {
        "body": case["body"],
        "hole": case["hole"],
        "hole_class": ranked["hole_class"],
        "size_bucket": ranked["size_bucket"],
        "pose_class": ranked["pose_class"],
        "strategy": CTX.planner["best_algorithm"],
        "passed_pct": CTX.planner["passed_pct"],
        "status": "passed" if CTX.planner["success"] else "blocked",
        "actions": 0,
        "attempts": 0,
        "effort": float(CTX.metrics.get("planner_keyframes", 0)),
        "clearance": float(ranked["clearance"]),
        "monotone": True,
    }
    return summary()


def api_probe_var() -> int:
    """Validate the observation contract without filtering a low objective."""
    planner = CTX.planner or {}
    if not CTX.best or not planner:
        return 6

    if int(planner.get("record_steps") or 0) <= 0 or not Path(
            str(planner.get("record_file") or "")).is_file() or not Path(
                str(planner.get("record_json") or "")).is_file():
        return 6
    if int(planner.get("record_trace_frames") or 0) != 24 or int(
            planner.get("record_trace_steps") or 0) != 27 or int(
                planner.get("record_steps") or 0) != int(
                    planner.get("record_trace_steps") or 0) + 1:
        return 6
    requested = set(planner.get("requested_algorithms") or ())
    if not requested or int(
            CTX.metrics.get("planner_algorithms", 0)) < len(requested):
        return 6
    if int(CTX.metrics.get("feature_points", 0)) <= 0 or int(
            CTX.metrics.get("feature_edges", 0)) <= 0:
        return 6

    needs_feedback = bool(
        planner.get("expect_feedback") and
        requested.difference({"direct-drop"}))
    if needs_feedback:
        if int(CTX.metrics.get("planner_cycles", 0)) <= 0:
            return 3
        if int(CTX.metrics.get("planner_evals", 0)) <= 0:
            return 3
    return 0


def _movement_score(row: dict[str, Any]) -> tuple:
    return (
        round(float(row["passed_pct"]), 6),
        -int(row["actions"]),
        -int(row["attempts"]),
        round(float(row["clearance"]), 6),
        row["hole"],
        row["strategy"],
    )


def _select_movement_candidates(
        body: str,
        ranking: list[dict[str, Any]],
        budget: int = MOVEMENT_HOLE_BUDGET,
) -> list[dict[str, Any]]:
    """Bound execution while retaining known non-static campaign targets."""
    selected = list(ranking[:max(1, int(budget))])
    seen = {row["hole"] for row in selected}
    dynamic_holes = [
        str(camp["hole"]) for camp in cc.CAMPAIGNS
        if camp.get("body") == body and
        not str(camp.get("expect", "")).startswith("impossible")
    ]
    for hole in dynamic_holes:
        if hole in seen:
            continue
        row = next((item for item in ranking if item["hole"] == hole), None)
        if row is not None:
            selected.append(row)
            seen.add(hole)
    return selected


def _planner_candidate_score(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        round(float(candidate["passed_pct"]), 6),
        -int(candidate["estimated_cost"]),
    )


def run_portfolio_proof(
        case_id: str = "snake_eye",
        portfolios: tuple[str, ...] = PROOF_PORTFOLIOS,
) -> dict[str, Any]:
    """Enumerate portfolios and expose all data needed for independent arg-best."""
    if case_id not in PLANNER_PROBE_CASES:
        raise KeyError(case_id)
    if "direct_baseline" not in portfolios:
        raise ValueError("proof requires direct_baseline")

    case = PLANNER_PROBE_CASES[case_id]
    ranked = {
        "hole": case["hole"],
        "pose": dict(case["pose"]),
        "clearance": 0.0,
    }
    candidates = []
    for portfolio in portfolios:
        planner = run_planner(
            case["body"], ranked, portfolio, record=True)
        candidates.append({
            "body": case["body"],
            "hole": case["hole"],
            "portfolio": portfolio,
            "requested_algorithms": list(planner["requested_algorithms"]),
            "catalog_algorithms": list(planner["catalog_algorithms"]),
            "best_algorithm": planner["best_algorithm"],
            "passed_pct": float(planner["passed_pct"]),
            "success": int(planner["success"]),
            "estimated_cost": int(
                (planner.get("complexity") or {}).get("estimated_cost") or 0),
            "record_file": planner["record_file"],
            "record_json": planner["record_json"],
            "record_steps": int(planner["record_steps"]),
            "record_trace_frames": int(planner["record_trace_frames"]),
            "record_trace_steps": int(planner["record_trace_steps"]),
        })

    baseline = next(row for row in candidates
                    if row["portfolio"] == "direct_baseline")
    selected = max(candidates, key=_planner_candidate_score)
    improvement = float(selected["passed_pct"]) - float(baseline["passed_pct"])
    return {
        "schema": "sieve3d-combinatorial-proof-v1",
        "case": case_id,
        "body": case["body"],
        "hole": case["hole"],
        "selection_criterion": (
            "passed_pct:max,estimated_cost:min"),
        "candidates": candidates,
        "record_artifacts": [
            {key: row[key] for key in (
                "portfolio", "record_file", "record_json", "record_steps",
                "record_trace_frames", "record_trace_steps")}
            for row in candidates
        ],
        "baseline": baseline,
        "selected": selected,
        "passed_pct_improvement": improvement,
        "strict_improvement": bool(improvement > 1e-9),
    }


def run_search() -> dict[str, Any]:
    holes = list(CTX.holes or cc.HOLES)
    CTX.ranking = rank_holes(CTX.body, holes, CTX.size_rule)
    profile = MOVE_PROFILES[CTX.move_profile]
    target = TARGET_PCT.get(CTX.body, 95.0)
    move_candidates = _select_movement_candidates(CTX.body, CTX.ranking)

    CTX.movements = []
    for row in move_candidates:
        for strategy in profile:
            result = run_movement(CTX.body, row, strategy)
            CTX.movements.append(result)
            if result["passed_pct"] >= target:
                break

    if CTX.movements:
        CTX.best = max(CTX.movements, key=_movement_score)
    else:
        CTX.best = None
        CTX.last_error = "no_movement_results"

    classes = {row["hole_class"] for row in CTX.ranking}
    min_steps = min(int(s.get("max_steps", s.get("rounds", 1)))
                    for s in profile)
    max_steps = max(int(s.get("max_steps", s.get("rounds", 1)))
                    for s in profile)
    if CTX.best:
        CTX.metrics.update({
            "passed_volume_pct": CTX.best["passed_pct"],
            "actions": CTX.best["actions"],
            "attempts": CTX.best["attempts"],
            "clearance": CTX.best["clearance"],
            "api_calls": sum(m["api_calls"] for m in CTX.movements),
        })
    planner_target = None
    if CTX.best:
        planner_target = next((row for row in CTX.ranking
                               if row["hole"] == CTX.best["hole"]), None)
    if planner_target is None and CTX.ranking:
        planner_target = CTX.ranking[0]
    if planner_target is not None:
        try:
            CTX.planner = run_planner(CTX.body, planner_target)
            _apply_planner_metrics(CTX.planner)
        except Exception as exc:
            CTX.last_error = type(exc).__name__ + ":" + _safe(str(exc))
    CTX.metrics.update({
        "geometric_candidates": len(CTX.ranking),
        "hole_classes": len(classes),
        "movement_candidates": len(move_candidates),
        "min_move_steps": min_steps,
        "max_move_steps": max_steps,
    })
    return summary()


def _record_best_if_needed() -> None:
    if not CTX.record_requested or not CTX.best:
        return
    if CTX.metrics.get("record_steps", 0) > 0:
        return
    ranked = next(row for row in CTX.ranking
                  if row["hole"] == CTX.best["hole"])
    strategy = next(s for s in MOVE_PROFILES[CTX.move_profile]
                    if s["name"] == CTX.best["strategy"])
    rec = run_movement(CTX.body, ranked, strategy, record=True)
    CTX.rec_file = rec["record_file"]
    CTX.rec_json = rec["record_json"]
    CTX.metrics["record_steps"] = rec["record_steps"]


def summary() -> dict[str, Any]:
    return {
        "body": CTX.body,
        "holes": list(CTX.holes or cc.HOLES),
        "size_rule": CTX.size_rule,
        "move_profile": CTX.move_profile,
        "ranking": CTX.ranking,
        "movements": CTX.movements,
        "best": CTX.best,
        "planner": CTX.planner,
        "metrics": dict(CTX.metrics),
        "record_file": CTX.rec_file,
        "record_json": CTX.rec_json,
        "last_error": CTX.last_error,
    }


def select_body(name: str) -> None:
    if name not in BODY_CASES:
        raise KeyError(name)
    CTX.body = name


def include_hole(name: str) -> None:
    if name not in cc.HOLES:
        raise KeyError(name)
    if name not in CTX.holes:
        CTX.holes.append(name)


def include_all_holes() -> None:
    for name in cc.HOLES:
        include_hole(name)


def select_size_rule(name: str) -> None:
    if name not in ("clearance_first", "snug_first"):
        raise KeyError(name)
    CTX.size_rule = name


def select_move_profile(name: str) -> None:
    if name not in MOVE_PROFILES:
        raise KeyError(name)
    CTX.move_profile = name


def observe(name: str) -> None:
    if name not in ("classes", "metrics"):
        raise KeyError(name)
    if name not in CTX.observers:
        CTX.observers.append(name)


def start_recording() -> None:
    CTX.record_requested = True


def finish_recording(label_text: str) -> dict[str, Any]:
    _record_best_if_needed()
    return {"record_file": CTX.rec_file, "record_json": CTX.rec_json,
            "record_steps": int(CTX.metrics.get("record_steps", 0)),
            "label": label_text}


def label() -> str:
    best = CTX.best or {}
    return "%s_%s_%s_%s" % (
        CTX.body, best.get("hole", "none"), CTX.size_rule, CTX.move_profile)


def fw_var() -> int:
    if not CTX.best:
        return 6
    if CTX.record_requested and int(CTX.metrics.get("record_steps", 0)) <= 0:
        return 6
    if not CTX.planner:
        return 6
    requested = len(CTX.planner.get("requested_algorithms") or ())
    if requested <= 0 or int(
            CTX.metrics.get("planner_algorithms", 0)) < requested:
        return 6
    if int(CTX.metrics.get("feature_points", 0)) <= 0 or int(CTX.metrics.get("feature_edges", 0)) <= 0:
        return 6
    if int(CTX.metrics.get("planner_success", 0)) <= 0:
        return 2
    if float(CTX.metrics.get("planner_passed_volume_pct", 0.0)) + 1e-9 < TARGET_PCT.get(
            CTX.body, 95.0):
        return 2
    if float(CTX.best.get("passed_pct", 0.0)) + 1e-9 < TARGET_PCT.get(
            CTX.body, 95.0):
        return 2
    if not bool(CTX.best.get("monotone", True)):
        return 3
    return 0


def kv_line(app: str = "sieve3d_max_passage",
            profile: str = "sieve3d_max_passage_v1",
            var: int | None = None) -> str:
    var = fw_var() if var is None else var
    best = CTX.best or {}
    planner = CTX.planner or {}
    verdict = "passed" if var == 0 else "failed"
    return (
        "app=%s criteria_profile=%s criteria_metrics=%s body=%s "
        "best_hole=%s hole_class=%s size_rule=%s move_profile=%s "
        "strategy=%s passed_volume_pct=%.2f actions=%d attempts=%d "
        "effort=%.1f clearance=%.4f geometric_candidates=%d "
        "hole_classes=%d movement_candidates=%d min_move_steps=%d "
        "max_move_steps=%d move_steps=%d api_calls=%d "
        "planner_portfolio=%s planner_catalog_algorithms=%d "
        "planner_requested_algorithms=%d planner_algorithm=%s planner_passed_volume_pct=%.2f "
        "planner_success=%d planner_algorithms=%d planner_candidates=%d "
        "planner_keyframes=%d planner_evals=%d planner_cycles=%d "
        "planner_estimated_cost=%d feature_points=%d feature_edges=%d "
        "feature_centers=%d record_trace_frames=%d record_trace_steps=%d "
        "record_steps=%d record_file=%s record_json=%s "
        "FW_VAR=%d verdict=%s"
        % (
            app, profile, CRITERIA_TOKEN, _safe(CTX.body),
            _safe(best.get("hole", "none")),
            _safe(best.get("hole_class", "none")), _safe(CTX.size_rule),
            _safe(CTX.move_profile), _safe(best.get("strategy", "none")),
            float(CTX.metrics.get("passed_volume_pct", 0.0)),
            int(CTX.metrics.get("actions", 0)),
            int(CTX.metrics.get("attempts", 0)),
            float(best.get("effort", 0.0) or 0.0),
            float(CTX.metrics.get("clearance", -1e9)),
            int(CTX.metrics.get("geometric_candidates", 0)),
            int(CTX.metrics.get("hole_classes", 0)),
            int(CTX.metrics.get("movement_candidates", 0)),
            int(CTX.metrics.get("min_move_steps", 0)),
            int(CTX.metrics.get("max_move_steps", 0)),
            int(best.get("actions", 0) or 0),
            int(CTX.metrics.get("api_calls", 0)),
            _safe(planner.get("portfolio", "custom")),
            int(CTX.metrics.get("planner_catalog_algorithms", 0)),
            int(CTX.metrics.get("planner_requested_algorithms", 0)),
            _safe(planner.get("best_algorithm", "none")),
            float(CTX.metrics.get("planner_passed_volume_pct", 0.0)),
            int(CTX.metrics.get("planner_success", 0)),
            int(CTX.metrics.get("planner_algorithms", 0)),
            int(CTX.metrics.get("planner_candidates", 0)),
            int(CTX.metrics.get("planner_keyframes", 0)),
            int(CTX.metrics.get("planner_evals", 0)),
            int(CTX.metrics.get("planner_cycles", 0)),
            int(CTX.metrics.get("planner_estimated_cost", 0)),
            int(CTX.metrics.get("feature_points", 0)),
            int(CTX.metrics.get("feature_edges", 0)),
            int(CTX.metrics.get("feature_centers", 0)),
            int(CTX.metrics.get("record_trace_frames", 0)),
            int(CTX.metrics.get("record_trace_steps", 0)),
            int(CTX.metrics.get("record_steps", 0)),
            _safe(CTX.rec_file), _safe(CTX.rec_json), var, verdict,
        )
    )


if __name__ == "__main__":
    raise SystemExit(staged.main())
