#!/usr/bin/env python3
"""
Complex-surface 3D bodies vs 2D sieve — the shared case library.

This is the deep companion to the Automation `sieve3d_external_api` specs.
Where those drive API *routes* over six hard-coded extrusions, this
library builds a zoo of genuinely complex solids (formula surfaces,
bends, twists, S-chains, boolean-pierced and boolean-carved bodies, the
tri-projection plug) plus matched-but-not-identical complex holes, and
scripts *long manipulation campaigns* for stuffing them through.

Everything runs in-process against the real sieve3d.api_v1 handlers via
one canonical harness (the same contract AppState implements), so the
suite exercises exactly the surface an external program would use —
while asserting geometric/physical invariants, not just exit codes.

Environment:
    SIEVE3D_ROOT         path to the 3Dprofile-VS-2Dsieve project
    SIEVE3D_REC_OUT_DIR  where campaign .rec artifacts are copied
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import tempfile
import time
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[2]
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from sut_paths import project_path  # noqa: E402

SIEVE3D_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT", str(project_path("sieve3d"))))
if str(SIEVE3D_ROOT) not in sys.path:
    sys.path.insert(0, str(SIEVE3D_ROOT))

import numpy as np                                    # noqa: E402

from sieve3d import api_v1                            # noqa: E402
from sieve3d.api import Scene                         # noqa: E402
from sieve3d.bodies import build_body                 # noqa: E402
from sieve3d.experiment import Experiment             # noqa: E402
from sieve3d.geometry import rot_zxz                  # noqa: E402
from sieve3d.recorder import MOTION_PATHS, Recorder, V1_MUT  # noqa: E402
from sieve3d.scene import SceneData                   # noqa: E402
from sieve3d.store import StateStore                  # noqa: E402
from sieve3d import profiles as pf                    # noqa: E402


# =========================================================================
# canonical in-process harness (the AppState contract, no HTTP)
# =========================================================================

class Harness:
    """State object accepted by every api_v1 handler."""

    def __init__(self, scene: Scene | None = None):
        self.scene = scene or Scene()
        self.store = StateStore()
        self.experiment = Experiment(self.scene, self.store)
        self.results_cache = None
        self.workers = 2
        self.recorder = Recorder(
            self.store, Path(tempfile.mkdtemp(prefix="sieve3d-cx-rec-")))
        self.api_calls = 0

    # --- AppState contract -------------------------------------------
    def initial_snapshot(self):
        return {"scene": self.scene.data.to_dict(),
                "experiment": self.experiment.snapshot()["bodies"],
                "versions": dict(self.store.versions)}

    def replace_scene(self, newdata):
        if isinstance(newdata, SceneData) and newdata is not self.scene.data:
            self.scene = Scene(newdata)
        self.after_scene_mutation("replaced")

    def after_scene_mutation(self, etype, name=None):
        self.results_cache = None
        self.experiment.scene = self.scene
        self.experiment.sync_scene(reset=(etype == "replaced"))
        self.store.bump("scene", etype, {"name": name} if name else None)

    def get_job(self, jid=None):
        return None

    # --- enveloped call: every response contract-checked --------------
    def call(self, method: str, path: str, handler, payload: dict | None = None):
        payload = payload or {}
        t0 = time.perf_counter()
        self.api_calls += 1
        try:
            data = handler(self, payload)
        except api_v1.ApiError as exc:
            env, code = api_v1.envelope(self.store, error=exc)
            assert env["ok"] is False and code >= 400, "error envelope broken"
            assert env["error"]["code"] == exc.code
            self.store.record_call(f"{method} {path}",
                                   (time.perf_counter() - t0) * 1e3, False)
            raise
        env, code = api_v1.envelope(
            self.store, data, elapsed_ms=(time.perf_counter() - t0) * 1e3)
        for key in ("ok", "api", "seq", "versions", "time", "elapsed_ms"):
            assert key in env, f"envelope missing {key}"
        assert env["ok"] is True and code == 200
        self.store.record_call(f"{method} {path}", env["elapsed_ms"], True)
        if method == "POST" and path in V1_MUT:
            self.recorder.log(
                "v1", method, path, payload,
                response=data if path in MOTION_PATHS else None,
            )
        return data

    # --- sugar ---------------------------------------------------------
    def act(self, body: str, action: str, **params):
        return self.call("POST", "/api/v1/experiment/action",
                         api_v1.h_exp_action,
                         {"body": body, "action": action, "params": params})

    def fits(self, body: str, hole: str, pose: dict | None = None):
        p = {"body": body, "hole": hole}
        if pose:
            p["pose"] = pose
        return self.call("POST", "/api/v1/fits", api_v1.h_fits, p)

    def exp(self):
        return self.call("GET", "/api/v1/experiment", api_v1.h_exp_get)


# =========================================================================
# the complex-body zoo
# =========================================================================
# Each recipe: body spec (recipes re-execute on build: formula surfaces,
# plasticine mods, boolean carving), a "home" hole it is meant for, and
# an expectation label used by the campaign matrix:
#   direct        — a single anchored drop must push it fully through
#   maneuver      — a straight drop must jam; wiggling/threading must win
#   impossible    — nothing may push it through its "blocked" hole
# =========================================================================

def S(kind, **kw):
    return pf.spec(kind, **kw)


BODIES: dict[str, dict] = {
    # -- formula surfaces ------------------------------------------------
    "wave_bar": {                    # side view is a sinusoid (the classic ask)
        "type": "formula", "mode_f": "graph",
        "top": "4+1.2*sin(0.5*z)", "bot": "-4", "x0": -5, "x1": 5,
        "length": 26},
    "flower": {                      # 3-lobed polar profile, straight prism
        "type": "formula", "mode_f": "polar",
        "r": "6+1.4*sin(3*t)", "length": 18},
    "twisted_flower": {              # lobes screw along the axis: r(t, z)
        "type": "formula", "mode_f": "polar",
        "r": "6+1.4*sin(3*t+0.35*z)", "length": 18},
    # -- plasticine chains ------------------------------------------------
    "hook120": {
        "type": "extrusion", "profile": S("circle", r=4), "length": 36,
        "mode": "physical", "mods": [{"op": "bend", "angle": 120}]},
    "snake": {                       # S-shaped double bend
        "type": "extrusion", "profile": S("circle", r=3.4), "length": 40,
        "mode": "physical",
        "mods": [{"op": "bend", "angle": 70},
                 {"op": "bend", "angle": -70}]},
    "helix_bar": {                   # square bar twisted 120 degrees
        "type": "extrusion", "profile": S("square", a=9), "length": 30,
        "mode": "physical", "mods": [{"op": "twist", "angle": 120}]},
    "croissant": {                   # bent stadium-profile prism
        "type": "extrusion", "profile": S("stadium", length=14, r=4),
        "length": 30, "mods": [{"op": "bend", "angle": 90, "plane": 90}]},
    # -- boolean-carved solids --------------------------------------------
    "pierced_cube": {                # cube with a through-bore
        "type": "extrusion", "profile": S("square", a=12), "length": 12,
        "mods": [{"op": "cut", "pose": {},
                  "tool": {"type": "extrusion",
                           "profile": S("circle", r=3), "length": 40}}]},
    "half_pipe": {                   # tube cut open lengthwise (concave!)
        "type": "extrusion", "profile": S("ring", r_outer=6, r_inner=4),
        "length": 24,
        "mods": [{"op": "cut", "pose": {"dx": 6},
                  "tool": {"type": "extrusion",
                           "profile": S("rect", w=12, h=14),
                           "length": 40}}]},
    # -- defined by its three projections ---------------------------------
    "plug": {
        "type": "triprofile",
        "profile_xy": S("circle", r=6),
        "profile_xz": S("square", a=12),
        "profile_yz": S("trapezoid", w_bottom=12, w_top=0.8, h=12),
        "length": 12},
}

HOLES: dict[str, dict] = {
    "wave_slot": S("formula", mode="graph", top="4+1.2*sin(0.5*x)",
                   bot="-4", x0=-13, x1=13, offset=0.55),
    "flower_hole": S("formula", mode="polar", r="6+1.4*sin(3*t)",
                     offset=0.55),
    "round_small": S("circle", r=4.6),          # hook's needle-eye
    "round_generous": S("circle", r=7.5),
    "square_snug": S("square", a=12, offset=0.5),
    "square_9": S("square", a=9, offset=0.6),
    "arch": S("stadium", length=42, r=11),
    "eye_snake": S("circle", r=3.9),
    "triangle": S("trapezoid", w_bottom=12, w_top=0.8, h=12, offset=0.5),
    "ring_gap": S("ring", r_outer=6.55, r_inner=3.45),
}

HOLE_GRID = [(-64, 30), (0, 30), (64, 30), (-64, -30), (0, -30), (64, -30),
             (-64, 0), (64, 0), (0, 0), (-32, 0)]


def make_scene(body_names, hole_names) -> Harness:
    """Fresh harness with the requested zoo members on a large plate."""
    sc = Scene()
    sc.set_plate(w=200, h=140)
    for n in body_names:
        sc.add_body(n, body=json.loads(json.dumps(BODIES[n])))
    for i, n in enumerate(hole_names):
        sc.add_hole(n, profile=json.loads(json.dumps(HOLES[n])),
                    at=HOLE_GRID[i % len(HOLE_GRID)])
    return Harness(sc)


# =========================================================================
# manipulation strategies — "more actions, more ways of stuffing"
# =========================================================================

def anchored_pose(h: Harness, body: str, hole: str, spin=0.0, tilt=0.0):
    a = h.call("POST", "/api/v1/anchor", api_v1.h_anchor,
               {"body": body, "hole": hole, "spin": spin, "tilt": tilt})
    return dict(a["pose"])


def strat_direct(h: Harness, body: str, hole: str, pose: dict) -> dict:
    """assign -> pose -> one drop."""
    h.act(body, "assign", hole=hole)
    h.act(body, "set_pose", **pose)
    out = h.act(body, "drop", max_dz=300)
    return out["state"]


def strat_stepwise(h: Harness, body: str, hole: str, pose: dict,
                   step: float = 2.0, jiggle: float = 0.5,
                   max_steps: int = 120) -> dict:
    """
    Careful stuffing: descend in small set_z steps; on every rejection
    jiggle laterally (+dx/-dx/+dy/-dy) and retry — many small actions.
    Asserts en route: passed_pct never decreases; a rejected move never
    changes the state.
    """
    h.act(body, "assign", hole=hole)
    st = h.act(body, "set_pose", **pose)["state"]
    last_pct = st["passed_pct"]
    for _ in range(max_steps):
        z_before = h.exp()["bodies"][body]["z"]
        try:
            st = h.act(body, "set_z", z=z_before - step)["state"]
        except api_v1.ApiError:
            after = h.exp()["bodies"][body]
            assert abs(after["z"] - z_before) < 1e-9, \
                "rejected set_z must not move the body"
            moved = False
            for ddx, ddy in ((jiggle, 0), (-2 * jiggle, 0),
                             (jiggle, jiggle), (0, -2 * jiggle), (0, jiggle)):
                try:
                    h.act(body, "nudge", ddx=ddx, ddy=ddy)
                    h.act(body, "set_z", z=z_before - step * 0.5)
                    moved = True
                    break
                except api_v1.ApiError:
                    continue
            if not moved:
                break
            st = h.exp()["bodies"][body]
        assert st["passed_pct"] >= last_pct - 1e-6, \
            f"passed_pct went backwards while descending: " \
            f"{last_pct} -> {st['passed_pct']}"
        last_pct = st["passed_pct"]
        if st["status"] == "passed":
            break
    return h.exp()["bodies"][body]


def strat_wiggle_ladder(h: Harness, body: str, hole: str, pose: dict,
                        rounds: int = 40, dz: float = 1.2) -> dict:
    """assign -> pose -> drop as far as it goes -> many wiggle rounds."""
    h.act(body, "assign", hole=hole)
    h.act(body, "set_pose", **pose)
    try:
        h.act(body, "drop", max_dz=300)
    except api_v1.ApiError:
        pass
    prev_z = h.exp()["bodies"][body]["z"]
    for _ in range(rounds):
        st = h.act(body, "wiggle", dz=dz, evals=45)["state"]
        assert st["z"] <= prev_z + 1e-9, "wiggle must never lift the body"
        prev_z = st["z"]
        if st["status"] == "passed":
            break
    return h.exp()["bodies"][body]


def strat_thread(h: Harness, body: str, hole: str, pose: dict,
                 frames: int = 30) -> dict:
    """The full iterative threading solver, synchronous."""
    res = h.call("POST", "/api/v1/thread", api_v1.h_thread,
                 {"body": body, "hole": hole, "pose": pose, "wait": True,
                  "frames": frames})
    return res


STRATEGIES = {"direct": strat_direct, "stepwise": strat_stepwise,
              "wiggle": strat_wiggle_ladder}


# =========================================================================
# the campaign matrix: complex body x hole x expectation
# =========================================================================
# expectation:
#   direct     — strat_direct reaches >= min_pct
#   maneuver   — strat_direct jams below 60%, but escalation
#                (stepwise -> wiggle -> thread) reaches >= min_pct
#   impossible — every strategy (incl. threading) fails; deficit < 0
# pose: starting orientation ("anchor" = centroid/principal snap)

CAMPAIGNS = [
    dict(body="wave_bar", hole="wave_slot", expect="direct", min_pct=99.0,
         pose={"spin": 270, "tilt": 90, "turn": 90},
         note="sinusoid surface must phase-lock into the wave slot"),
    dict(body="flower", hole="flower_hole", expect="direct", min_pct=99.0,
         pose="anchor",
         note="3-lobed polar profile, straight in"),
    dict(body="plug", hole="triangle", expect="direct", min_pct=99.0,
         pose={"spin": 90, "tilt": 90, "turn": 180, "dy": 1.75},
         note="tri-projection plug entering by its TRIANGLE face"),
    dict(body="plug", hole="square_snug", expect="direct", min_pct=99.0,
         pose={"spin": 0, "tilt": 90, "turn": 0},
         note="same plug, now by its SQUARE silhouette"),
    dict(body="pierced_cube", hole="square_snug", expect="direct",
         min_pct=99.0, pose="anchor",
         note="boolean-pierced cube keeps its outer silhouette"),
    dict(body="helix_bar", hole="square_9", expect="maneuver", min_pct=95.0,
         pose={"spin": 60, "tilt": 0, "turn": 0},
         wiggle_dz=0.8, wiggle_rounds=130,
         note="twisted bar cannot fall through straight; it must be "
              "screwed through (entry section pre-phased by +60 deg)"),
    dict(body="hook120", hole="round_small", expect="maneuver", min_pct=95.0,
         pose={"spin": 90, "tilt": 20, "turn": -90},
         note="the sewing-needle classic: only threading wins"),
    dict(body="croissant", hole="arch", expect="direct", min_pct=95.0,
         pose="anchor",
         note="bent oval prism through a wide arch"),
    dict(body="twisted_flower", hole="flower_hole", expect="maneuver",
         min_pct=90.0, pose="anchor",
         note="screwed lobes against a matching straight hole: must "
              "rotate while descending"),
    dict(body="flower", hole="round_small", expect="impossible", min_pct=0,
         pose="anchor", note="7.4mm lobes vs a 4.6mm eye: no way"),
    dict(body="snake", hole="eye_snake", expect="maneuver_partial",
         min_pct=35.0, pose={"spin": 90, "tilt": 12, "turn": -90},
         wiggle_dz=0.7, wiggle_rounds=80,
         note="the wire-through-eyelet classic: the S wanders +-3mm "
              "laterally, a 0.5mm-margin eye forces continuous steering"),
    dict(body="half_pipe", hole="ring_gap", expect="impossible", min_pct=0,
         pose="anchor",
         note="open channel cannot thread a ring with an island: the cut "
              "mouth never clears the island bridge"),
]


def campaign_summary_line(name: str, metrics: dict) -> str:
    """Automation-analyzer-compatible one-liner."""
    token = ",".join(f"{k}:{v}" for k, v in
                     [("passed_volume_pct", "max"), ("actions", "min"),
                      ("attempts", "min"), ("record_steps", "max")])
    return ("app=sieve3d_complex_bodies criteria_profile="
            "sieve3d_complex_bodies_v1 criteria_metrics=%s case=%s "
            "passed_volume_pct=%.2f actions=%d attempts=%d effort=%.1f "
            "strategy=%s record_steps=%d verdict=%s"
            % (token, name, metrics.get("passed_pct", 0.0),
               metrics.get("actions", 0), metrics.get("attempts", 0),
               metrics.get("effort", 0.0), metrics.get("strategy", "none"),
               metrics.get("record_steps", 0), metrics.get("verdict", "?")))


def save_rec_artifact(h: Harness, label: str) -> tuple[str, int]:
    """Cut the recording and copy it Automation-style to SIEVE3D_REC_OUT_DIR."""
    try:
        h.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "cut"})
    except api_v1.ApiError:
        pass
    info = h.call("POST", "/api/v1/record", api_v1.h_record,
                  {"cmd": "retrieve_last_record"})
    out_dir = Path(os.environ.get("SIEVE3D_REC_OUT_DIR",
                                  tempfile.gettempdir()))
    out_dir = out_dir / "sieve3d_rec_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in label)
    path = out_dir / (f"complex_{safe}_{int(time.time() * 1000)}.rec")
    path.write_text("\n".join(json.dumps(r, ensure_ascii=True)
                              for r in info["records"]) + "\n",
                    encoding="utf-8")
    return str(path), int(info["steps_count"])
