#!/usr/bin/env python3
"""Combinatorial metamorphic laws for sieve3d action experiments.

This module is intentionally separate from Claude's campaign harness logic. It
uses the same public in-process API surface and complex body recipes, but the
oracles here are action algebra properties generated from Bundle slots:
commutation, path independence, batch equivalence, reset idempotence, rejected
atomicity, and independent multi-body interleavings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE.parent
if str(CASES_DIR) not in sys.path:
    sys.path.insert(0, str(CASES_DIR))

import complex_cases as cc  # noqa: E402
from sieve3d import api_v1  # noqa: E402

GEOMETRIES: dict[str, dict[str, Any]] = {
    "flower_fit": {"body": "flower", "hole": "flower_hole", "pose": "anchor"},
    "cube_square": {"body": "pierced_cube", "hole": "square_snug", "pose": {"spin": 0, "tilt": 0, "turn": 0}},
    "wave_slot": {"body": "wave_bar", "hole": "wave_slot", "pose": {"spin": 270, "tilt": 90, "turn": 90, "dy": -0.2}},
}
ALL_BODIES = sorted({g["body"] for g in GEOMETRIES.values()})
ALL_HOLES = sorted({g["hole"] for g in GEOMETRIES.values()})

SCALES = {
    "fine": {"xy": 0.25, "turn": 1.0, "z": 0.10},
    "coarse": {"xy": 0.75, "turn": 2.0, "z": 0.25},
}

CRITERIA_METRICS = {
    "law_evals": "max",
    "preconditions_met": "max",
    "precondition_skips": "min",
    "oracle_checks": "max",
    "violations": "min",
    "record_steps": "max",
    "api_calls": "min",
}
CRITERIA_TOKEN = ",".join("%s:%s" % (k, v) for k, v in CRITERIA_METRICS.items())


@dataclass
class Context:
    primary: Any | None = None
    cases: list[str] = field(default_factory=list)
    atoms: list[str] = field(default_factory=list)
    interleave: list[str] = field(default_factory=list)
    fault: str = "unknown_action"
    scale: str = "fine"
    law: str = "unset"
    observers: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=lambda: {
        "law_evals": 0,
        "preconditions_met": 0,
        "precondition_skips": 0,
        "oracle_checks": 0,
        "violations": 0,
        "record_steps": 0,
        "api_calls": 0,
    })
    last_error: str = "none"
    rec_file: str = "none"
    rec_json: str = "none"


CTX = Context()


def reset() -> None:
    global CTX
    CTX = Context()


def _new_harness():
    return cc.make_scene(ALL_BODIES, ALL_HOLES)


def start_recording() -> None:
    CTX.primary = _new_harness()
    CTX.primary.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "action"})


def select_case(name: str) -> None:
    if name not in GEOMETRIES:
        raise KeyError(name)
    if name not in CTX.cases:
        CTX.cases.append(name)


def add_atom(name: str) -> None:
    if name not in ("dx", "dy", "turn", "z"):
        raise KeyError(name)
    CTX.atoms.append(name)


def queue_interleave(name: str) -> None:
    if name not in ("A_dx", "A_dy", "B_dx", "B_dy"):
        raise KeyError(name)
    CTX.interleave.append(name)


def select_fault(name: str) -> None:
    if name not in ("unknown_action", "bad_hole", "unassigned_wiggle"):
        raise KeyError(name)
    CTX.fault = name


def select_scale(name: str) -> None:
    if name not in SCALES:
        raise KeyError(name)
    CTX.scale = name


def _safe(text: Any) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(text))[:180] or "case"


def _case_one() -> str:
    return CTX.cases[0] if CTX.cases else next(iter(GEOMETRIES))


def _selected_cases() -> list[str]:
    return list(CTX.cases) or [_case_one()]


def _case_pair() -> tuple[str, str]:
    cases = list(CTX.cases)
    for key in GEOMETRIES:
        if key not in cases:
            cases.append(key)
        if len(cases) >= 2:
            break
    return cases[0], cases[1]


def _pose_for(h, case_name: str) -> dict:
    g = GEOMETRIES[case_name]
    if g["pose"] == "anchor":
        return cc.anchored_pose(h, g["body"], g["hole"])
    return dict(g["pose"])


def _prepare(h, case_name: str) -> tuple[str, str, dict]:
    g = GEOMETRIES[case_name]
    body, hole = g["body"], g["hole"]
    pose = _pose_for(h, case_name)
    h.act(body, "assign", hole=hole)
    h.act(body, "set_pose", **pose)
    return body, hole, pose


def _atom_params(atom: str) -> dict[str, float]:
    s = SCALES[CTX.scale]
    if atom == "dx":
        return {"ddx": s["xy"]}
    if atom == "dy":
        return {"ddy": s["xy"]}
    if atom == "turn":
        return {"dturn": s["turn"]}
    if atom == "z":
        return {"dz": -s["z"]}
    raise KeyError(atom)


def _apply_atom(h, body: str, atom: str) -> None:
    h.act(body, "nudge", **_atom_params(atom))


def _atom_batch_item(body: str, atom: str) -> dict:
    return {"body": body, "action": "nudge", "params": _atom_params(atom)}


def _state(h, bodies: list[str], *, include_attempts: bool = True, include_last_error: bool = False, include_costs: bool = True) -> dict:
    snap = h.exp()
    out = {}
    for body in bodies:
        st = dict(snap["bodies"][body])
        keep = ["hole", "pose", "z", "status", "passed_pct", "clearance_now"]
        if include_costs:
            keep.extend(["actions", "effort"])
        if include_attempts:
            keep.append("attempts")
        if include_last_error:
            keep.append("last_error")
        out[body] = {k: st.get(k) for k in keep}
    return out


def _register_check(ok: bool, label: str, left: Any = None, right: Any = None) -> None:
    CTX.metrics["oracle_checks"] += 1
    if not ok:
        CTX.metrics["violations"] += 1
        CTX.last_error = "%s:%s!=%s" % (label, _safe(left), _safe(right))


def _precondition_met() -> None:
    CTX.metrics["preconditions_met"] += 1


def _precondition_skip(label: str, detail: Any = None) -> None:
    CTX.metrics["precondition_skips"] += 1
    CTX.last_error = "%s:%s" % (label, _safe(detail))


def _try_atoms(h, body: str, atoms: list[str]) -> tuple[bool, str]:
    try:
        for atom in atoms:
            _apply_atom(h, body, atom)
        return True, "ok"
    except api_v1.ApiError as exc:
        return False, exc.code


def _compare_states(label: str, a, b, bodies: list[str], *, include_attempts: bool = True, include_costs: bool = True) -> None:
    left = _state(a, bodies, include_attempts=include_attempts, include_costs=include_costs)
    right = _state(b, bodies, include_attempts=include_attempts, include_costs=include_costs)
    _register_check(left == right, label, left, right)


def _fresh_secondary():
    return _new_harness()


def run_law(name: str) -> None:
    CTX.law = name
    laws = {
        "commutation": _law_commutation,
        "path_independence": _law_path_independence,
        "batch_equivalence": _law_batch_equivalence,
        "reset_idempotence": _law_reset_idempotence,
        "rejected_atomicity": _law_rejected_atomicity,
    }
    if name not in laws:
        CTX.metrics["violations"] += 1
        CTX.last_error = "KeyError:" + name
        return
    for case in _selected_cases():
        _evaluate_case(laws[name], case)
        # FAULT is a real axis for every candidate, not a label-only product.
        if name != "rejected_atomicity":
            _evaluate_case(_law_rejected_atomicity, case)


def _evaluate_case(law_fn, case: str) -> None:
    CTX.metrics["law_evals"] += 1
    try:
        law_fn(case)
    except Exception as exc:  # infrastructure failures are violations, not silent skips
        CTX.metrics["violations"] += 1
        CTX.last_error = type(exc).__name__ + ":" + str(exc).replace(" ", "_")


def _law_commutation(case: str) -> None:
    atoms = (CTX.atoms or ["dx", "dy"])[:2]
    h1 = CTX.primary
    h2 = _fresh_secondary()
    body, _, _ = _prepare(h1, case)
    _prepare(h2, case)
    ok1, err1 = _try_atoms(h1, body, list(atoms))
    ok2, err2 = _try_atoms(h2, body, list(reversed(atoms)))
    if not (ok1 and ok2):
        _precondition_skip("commutation_path_rejected", {"forward": err1, "reverse": err2})
        return
    _precondition_met()
    _compare_states("commutation", h1, h2, [body])


def _law_path_independence(case: str) -> None:
    atoms = (CTX.atoms or ["dx", "dy"])[:2]
    h1 = CTX.primary
    h2 = _fresh_secondary()
    body, _, _ = _prepare(h1, case)
    _prepare(h2, case)
    base = h2.exp()["bodies"][body]
    target_pose = dict(base["pose"])
    target_z = float(base["z"])
    ok, err = _try_atoms(h1, body, list(atoms))
    if not ok:
        _precondition_skip("path_sequence_rejected", err)
        return
    for atom in atoms:
        p = _atom_params(atom)
        target_pose["dx"] = round(float(target_pose.get("dx", 0.0)) + float(p.get("ddx", 0.0)), 3)
        target_pose["dy"] = round(float(target_pose.get("dy", 0.0)) + float(p.get("ddy", 0.0)), 3)
        target_pose["turn"] = round(float(target_pose.get("turn", 0.0)) + float(p.get("dturn", 0.0)), 3)
        target_z = round(target_z + float(p.get("dz", 0.0)), 3)
    try:
        h2.act(body, "set_pose", **target_pose, z=target_z)
    except api_v1.ApiError as exc:
        _precondition_skip("path_direct_move_rejected", exc.code)
        return
    _precondition_met()
    _compare_states("path_independence", h1, h2, [body], include_attempts=False, include_costs=False)


def _law_batch_equivalence(case: str) -> None:
    atoms = (CTX.atoms or ["dx", "dy"])[:2]
    h1 = CTX.primary
    h2 = _fresh_secondary()
    body, _, _ = _prepare(h1, case)
    _prepare(h2, case)
    res = h1.call("POST", "/api/v1/experiment/action", api_v1.h_exp_action,
                  {"batch": [_atom_batch_item(body, atom) for atom in atoms]})
    if any("error" in r for r in res["results"]):
        _precondition_skip("batch_partial_failure", res)
        return
    ok, err = _try_atoms(h2, body, list(atoms))
    if not ok:
        _precondition_skip("sequential_failure", err)
        return
    _precondition_met()
    _compare_states("batch_equivalence", h1, h2, [body])


def _law_reset_idempotence(case: str) -> None:
    atoms = (CTX.atoms or ["dx", "dy"])[:2]
    h1 = CTX.primary
    h2 = _fresh_secondary()
    body, _, _ = _prepare(h1, case)
    _prepare(h2, case)
    ok1, err1 = _try_atoms(h1, body, list(atoms))
    ok2, err2 = _try_atoms(h2, body, list(atoms))
    if not (ok1 and ok2):
        _precondition_skip("reset_setup_rejected", {"left": err1, "right": err2})
        return
    h1.act(body, "reset")
    h1.act(body, "reset")
    h2.act(body, "reset")
    _precondition_met()
    _compare_states("reset_idempotence", h1, h2, [body])


def _law_rejected_atomicity(case: str) -> None:
    g = GEOMETRIES[case]
    body = g["body"]
    h = CTX.primary
    _prepare(h, case)
    atoms = (CTX.atoms or ["dx", "dy"])[:2]
    ok, err = _try_atoms(h, body, list(atoms))
    if not ok:
        _precondition_skip("rejection_setup_rejected", {
            "case": case, "atoms": atoms, "error": err})
        return
    if CTX.fault == "unassigned_wiggle":
        h.act(body, "assign", hole=None)
    before = _state(h, [body], include_attempts=False, include_last_error=False)
    before_full = h.exp()["bodies"][body]
    raised_code = "none"
    try:
        if CTX.fault == "unknown_action":
            h.act(body, "warp")
        elif CTX.fault == "bad_hole":
            h.act(body, "assign", hole="no_such_hole")
        elif CTX.fault == "unassigned_wiggle":
            h.act(body, "wiggle", dz=SCALES[CTX.scale]["z"],
                  evals=20 + int(SCALES[CTX.scale]["xy"] * 20))
        else:
            raise KeyError(CTX.fault)
    except api_v1.ApiError as exc:
        raised_code = exc.code
    after = _state(h, [body], include_attempts=False, include_last_error=False)
    after_full = h.exp()["bodies"][body]
    expected_code = {
        "unknown_action": "bad_request",
        "bad_hole": "not_found",
        "unassigned_wiggle": "bad_request",
    }[CTX.fault]
    _precondition_met()
    _register_check(raised_code == expected_code, "rejection_code",
                    raised_code, expected_code)
    _register_check(before == after, "rejection_atomic_state", before, after)
    _register_check(after_full["actions"] == before_full["actions"], "rejection_no_action_cost", before_full, after_full)
    _register_check(after_full["attempts"] == before_full["attempts"] + 1, "rejection_attempt_count", before_full, after_full)


def _canonical_interleave(ops: list[str]) -> list[str]:
    expected = ["A_dx", "A_dy", "B_dx", "B_dy"]
    if len(ops) != len(expected) or sorted(ops) != sorted(expected):
        raise ValueError("interleave must contain each operation exactly once")
    # Remove only cross-body interleaving while retaining each body's local order.
    return ([op for op in ops if op.startswith("A_")] +
            [op for op in ops if op.startswith("B_")])


def run_interleaving() -> None:
    CTX.law = "independent_interleave"
    CTX.metrics["law_evals"] += 1
    try:
        case_a, case_b = _case_pair()
        ops = CTX.interleave or ["A_dx", "A_dy", "B_dx", "B_dy"]
        canonical_ops = _canonical_interleave(ops)
        h1 = CTX.primary
        h2 = _fresh_secondary()
        body_a, _, _ = _prepare(h1, case_a)
        body_b, _, _ = _prepare(h1, case_b)
        _prepare(h2, case_a)
        _prepare(h2, case_b)
        mapping = {
            "A_dx": (body_a, "dx"),
            "A_dy": (body_a, "dy"),
            "B_dx": (body_b, "dx"),
            "B_dy": (body_b, "dy"),
        }
        for op in ops:
            body, atom = mapping[op]
            try:
                _apply_atom(h1, body, atom)
            except api_v1.ApiError as exc:
                _precondition_skip("interleaved_action_rejected", {"op": op, "error": exc.code})
                return
        for op in canonical_ops:
            body, atom = mapping[op]
            try:
                _apply_atom(h2, body, atom)
            except api_v1.ApiError as exc:
                _precondition_skip("canonical_action_rejected", {"op": op, "error": exc.code})
                return
        _precondition_met()
        _compare_states("independent_interleave", h1, h2, sorted([body_a, body_b]))
    except Exception as exc:
        CTX.metrics["violations"] += 1
        CTX.last_error = type(exc).__name__ + ":" + str(exc).replace(" ", "_")


def observe(kind: str) -> None:
    h = CTX.primary
    if h is None:
        return
    if kind == "events":
        ev = h.call("GET", "/api/v1/events", api_v1.h_events, {"since": 0, "timeout": 0.01})
        CTX.metrics["api_calls"] = max(CTX.metrics["api_calls"], len(ev.get("events", [])))
    elif kind == "metrics":
        m = h.call("GET", "/api/v1/metrics", api_v1.h_metrics, {})
        CTX.metrics["api_calls"] = max(CTX.metrics["api_calls"], len(m.get("api_calls", [])))
    elif kind == "record_status":
        h.call("GET", "/api/v1/record", api_v1.h_record_status, {})
    else:
        raise KeyError(kind)
    if kind not in CTX.observers:
        CTX.observers.append(kind)


def label() -> str:
    parts = [CTX.law, "+".join(CTX.cases) or "cases", ">".join(CTX.atoms) or ">".join(CTX.interleave) or "ops", CTX.fault, CTX.scale]
    return _safe("__".join(parts))


def finish_recording(label_text: str | None = None) -> dict:
    h = CTX.primary
    if h is None:
        CTX.metrics["violations"] += 1
        CTX.last_error = "no_primary_harness"
        return {"records": [], "steps_count": 0}
    try:
        h.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "cut"})
    except api_v1.ApiError as exc:
        if exc.code != "conflict":
            CTX.metrics["violations"] += 1
            CTX.last_error = "record_cut:" + exc.code
            return {"records": [], "steps_count": 0}
    try:
        info = h.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "retrieve_last_record"})
    except api_v1.ApiError as exc:
        CTX.metrics["violations"] += 1
        CTX.last_error = "record_retrieve:" + exc.code
        return {"records": [], "steps_count": 0}
    CTX.metrics["record_steps"] = int(info.get("steps_count", 0))
    out_dir = Path(os.environ.get("SIEVE3D_REC_OUT_DIR", os.getcwd())) / "sieve3d_rec_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "%s_%s_%d_%d" % ("sieve3d_combinatoric", _safe(label_text or label()), os.getpid(), int(time.time() * 1000))
    rec_path = out_dir / (stem + ".rec")
    json_path = out_dir / (stem + ".json")
    records = info.get("records") or []
    rec_path.write_text("\n".join(json.dumps(r, ensure_ascii=True) for r in records) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps({"file": info.get("file"), "steps_count": info.get("steps_count"), "saved_rec": str(rec_path), "source_path": info.get("path")}, sort_keys=True), encoding="utf-8")
    CTX.rec_file = str(rec_path)
    CTX.rec_json = str(json_path)
    return info


def fw_var() -> int:
    if CTX.metrics.get("record_steps", 0) <= 0:
        return 6
    if CTX.metrics.get("violations", 0) > 0:
        return 2
    if CTX.metrics.get("precondition_skips", 0) > 0:
        return 4
    return 0


def kv_line(app: str, profile: str, fw_var_value: int) -> str:
    cases = "+".join(CTX.cases) or "none"
    atoms = ">".join(CTX.atoms) or ">".join(CTX.interleave) or "none"
    observers = "+".join(CTX.observers) or "none"
    return (
        "app=%s criteria_profile=%s criteria_metrics=%s law=%s cases=%s atoms=%s fault=%s scale=%s "
        "observers=%s law_evals=%d preconditions_met=%d precondition_skips=%d "
        "oracle_checks=%d violations=%d api_calls=%d "
        "record_file=%s record_json=%s record_steps=%d last_error=%s FW_VAR=%d"
        % (
            app,
            profile,
            CRITERIA_TOKEN,
            CTX.law,
            cases,
            atoms,
            CTX.fault,
            CTX.scale,
            observers,
            int(CTX.metrics.get("law_evals", 0)),
            int(CTX.metrics.get("preconditions_met", 0)),
            int(CTX.metrics.get("precondition_skips", 0)),
            int(CTX.metrics.get("oracle_checks", 0)),
            int(CTX.metrics.get("violations", 0)),
            int(CTX.metrics.get("api_calls", 0)),
            _safe(CTX.rec_file),
            _safe(CTX.rec_json),
            int(CTX.metrics.get("record_steps", 0)),
            _safe(CTX.last_error),
            int(fw_var_value),
        )
    )
