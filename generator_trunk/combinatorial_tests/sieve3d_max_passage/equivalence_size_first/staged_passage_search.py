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

"""Deterministic neutral-first passage search for every body/hole pair.

This module is deliberately separate from the historical best-hole campaign in
``max_passage_search.py``.  It models one fixed geometry pair at a time, keeps
the complete user-declared discrete universe, executes only the prefix allowed
by measured action-tier dominance, and writes enough evidence for an
independent verifier to reconstruct the decision.

The proof scope is discrete and explicit.  A failure means only that the
declared candidate universe was exhausted; it is never a claim about all
continuous rigid-body motions.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import csv
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Iterable, Sequence

import numpy as np
from shapely import affinity


HERE = Path(__file__).resolve().parent
TASK_ROOT = HERE.parent.parent
GENERATOR_ROOT = TASK_ROOT.parent
CASES_DIR = TASK_ROOT / "sieve3d_complex_bodies"
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

from sut_paths import project_path  # noqa: E402

SIEVE3D_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT",
    str(project_path("sieve3d")),
))

for _path in (SIEVE3D_ROOT, CASES_DIR, GENERATOR_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import complex_cases as cc  # noqa: E402
import fwgen as fg  # noqa: E402
from sieve3d import api_v1, profiles  # noqa: E402
from sieve3d.bodies import build_body  # noqa: E402
from sieve3d.geometry import rot_zxz  # noqa: E402


CANDIDATE_SCHEMA = "sieve3d-staged-candidate/2"
UNIVERSE_SCHEMA = "sieve3d-staged-universe/2"
ATTEMPT_SCHEMA = "sieve3d-staged-attempt/2"
PAIR_PROOF_SCHEMA = "sieve3d-pair-proof/2"
MATRIX_SCHEMA = "sieve3d-all-pairs-matrix/2"
CERTIFICATE_SCHEMA = "sieve3d-minimality-certificate/2"
POSE_KEYS = ("spin", "tilt", "turn", "dx", "dy")
STAGE_ORDER = {
    "neutral": 0,
    "rotation": 1,
    "shift": 2,
    "mixed": 3,
    "multi_move": 4,
    "screw_thread": 5,
}
EXPECTED_DOMAIN_ERRORS = {"collision", "conflict"}
MAX_RECORD_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_RECORD_STEPS = 10_000
MAX_MOTION_FRAMES = 600
SERIAL_TOL = 1e-9
_PAIR_FIT_CACHE: dict[tuple[str, str, tuple[float, ...]], dict[str, Any]] = {}


class UniverseError(RuntimeError):
    """The declared search space could not be constructed faithfully."""


class EvidenceError(RuntimeError):
    """Persistent evidence is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class SearchConfig:
    """The complete user-authored proof scope for one run.

    Domains are intentionally tuples rather than implicit grids.  Their exact
    values, raw products, reductions, and execution implications are serialized
    into every universe manifest.
    """

    config_id: str = "rigid-discrete-v2"
    rigid_policy: str = "rigid_only"
    modification: str = "none"
    rotation_seeds: tuple[tuple[str, float, float, float], ...] = (
        ("neutral", 0.0, 0.0, 0.0),
        ("front", 0.0, 90.0, 0.0),
        ("side", 0.0, 90.0, 90.0),
        ("tri_projection", 90.0, 90.0, 180.0),
        ("wave_phase", 270.0, 90.0, 90.0),
    )
    shift_seeds: tuple[tuple[str, float, float], ...] = (
        ("center", 0.0, 0.0),
        ("snake_x_local_lo", 0.3000, 0.0),
        ("snake_x_measured", 0.3119, 0.0),
        ("snake_x_local_hi", 0.3200, 0.0),
        ("triangle_y_171", 0.0, 1.7100),
        ("triangle_y_173", 0.0, 1.7300),
        ("triangle_y_175", 0.0, 1.7500),
    )
    anchor_seeds: tuple[tuple[str, float, float], ...] = (
        ("principal_axial", 0.0, 0.0),
        ("principal_side_x", 0.0, 90.0),
        ("principal_side_y", 90.0, 90.0),
    )
    campaign_rotation_refinement_deg: float = 2.0
    campaign_shift_refinement_mm: float = 0.02
    dynamic_seed_poses: tuple[tuple[str, float, float, float, float, float], ...] = (
        ("thread_wire", 90.0, 12.0, 270.0, 0.3119, 0.0),
    )
    wiggle_budgets: tuple[int, ...] = (1, 2)
    pair_wiggle_budgets: tuple[
        tuple[str, str, tuple[int, ...]], ...
    ] = (
        ("twisted_flower", "flower_hole", (1, 4, 16, 40)),
    )
    wiggle_dz: float = 0.8
    wiggle_evals: int = 45
    planner_algorithms: tuple[str, ...] = (
        "direct-drop",
        "feedback-thread",
        "lookahead-thread",
        "multistart-thread",
        "adaptive-switch-thread",
    )
    adaptive_queue: tuple[str, ...] = (
        "direct-drop",
        "feedback-thread",
        "lookahead-thread",
        "multistart-thread",
    )
    planner_budget: str = "declared"
    planner_max_candidates: int = 2
    planner_frames: int = 48
    planner_max_steps: int = 4
    planner_rounds: int = 1
    planner_evals: int = 8
    planner_starts: int = 1
    planner_lookahead: int = 1
    planner_retreats: int = 1
    planner_escape_rounds: int = 0
    planner_escape_starts: int = 1
    planner_escape_evals: int = 8
    planner_handoff_limit: int = 2
    record_attempts: bool = True
    enabled_families: tuple[str, ...] = (
        "neutral", "rotation", "shift", "mixed", "multi_move",
        "screw_thread",
    )

    def validate(self) -> None:
        if self.rigid_policy != "rigid_only":
            raise UniverseError(
                "the main proof requires policy rigid_only; physical "
                "modification belongs in a separate experiment")
        if self.modification != "none":
            raise UniverseError(
                "rigid_only forbids deformation, scaling, erosion, or hole edits")
        if tuple(self.enabled_families) != tuple(STAGE_ORDER):
            raise UniverseError(
                "all six ordered families must be declared exactly once")
        if not self.rotation_seeds or not self.shift_seeds:
            raise UniverseError("rotation and shift domains must be non-empty")
        if not any(any(abs(v) > SERIAL_TOL for v in row[1:])
                   for row in self.rotation_seeds):
            raise UniverseError("rotation domain is a no-op")
        if not any(any(abs(v) > SERIAL_TOL for v in row[1:])
                   for row in self.shift_seeds):
            raise UniverseError("shift domain is a no-op")
        if not self.dynamic_seed_poses or not self.wiggle_budgets:
            raise UniverseError("multi-move domain is empty")
        if any(int(n) <= 0 for n in self.wiggle_budgets):
            raise UniverseError("wiggle budgets must be positive exact lengths")
        if tuple(sorted(set(self.wiggle_budgets))) != self.wiggle_budgets:
            raise UniverseError("wiggle budgets must be unique and ascending")
        all_budgets = list(self.wiggle_budgets)
        for body, hole, budgets in self.pair_wiggle_budgets:
            if body not in cc.BODIES or hole not in cc.HOLES:
                raise UniverseError(
                    f"pair-specific wiggle scope names unknown pair {body}->{hole}")
            if not budgets or tuple(sorted(set(budgets))) != tuple(budgets) or \
                    any(int(n) <= 0 for n in budgets):
                raise UniverseError(
                    f"invalid pair-specific wiggle budgets for {body}->{hole}")
            all_budgets.extend(int(n) for n in budgets)
        if self.planner_frames < 24 or self.planner_frames > MAX_MOTION_FRAMES:
            raise UniverseError("planner frame count must be in [24, 600]")
        if self.planner_frames <= 2 + max(all_budgets):
            raise UniverseError(
                "final planner frames must exceed every declared multi-move "
                "action ceiling so the final stage is strictly more expensive")
        if not self.planner_algorithms:
            raise UniverseError("final planner domain is empty")
        if self.planner_budget != "declared":
            raise UniverseError(
                "the proof run requires the exact caller-owned declared budget")
        if self.planner_max_candidates < 2:
            raise UniverseError(
                "multistart-thread requires at least two declared starts")
        if min(self.planner_max_steps, self.planner_rounds,
               self.planner_evals, self.planner_starts,
               self.planner_escape_starts, self.planner_escape_evals,
               self.planner_handoff_limit) <= 0:
            raise UniverseError("planner declared ceilings must be positive")
        if self.planner_escape_rounds < 0:
            raise UniverseError("planner escape rounds cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class PoseSeed:
    label: str
    pose: dict[str, float]
    sources: tuple[str, ...]


@dataclass
class BundleContext:
    body: str | None = None
    hole: str | None = None
    policy: str = "rigid_only"
    modification: str = "none"
    enabled_families: list[str] = field(default_factory=list)
    enabled_moves: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    last_error: str = "none"


BUNDLE_CTX = BundleContext()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(_jsonable(value)).encode("utf-8"))


def _jsonable(value: Any) -> Any:
    """Convert factor-domain dataclasses/tuples to canonical JSON values."""
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, sort_keys=True, indent=2, ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _safe(value: Any) -> str:
    out = "".join(
        ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value))
    return out[:180] or "x"


def _near_zero(value: float) -> float:
    value = float(value)
    return 0.0 if abs(value) <= SERIAL_TOL else value


def _angle(value: float) -> float:
    out = float(value) % 360.0
    if abs(out - 360.0) <= SERIAL_TOL or abs(out) <= SERIAL_TOL:
        return 0.0
    return round(out, 9)


def normalize_pose(pose: dict[str, Any] | None) -> dict[str, float]:
    src = pose or {}
    return {
        "spin": _angle(src.get("spin", 0.0) or 0.0),
        "tilt": _angle(src.get("tilt", 0.0) or 0.0),
        "turn": _angle(src.get("turn", 0.0) or 0.0),
        "dx": round(_near_zero(src.get("dx", 0.0) or 0.0), 9),
        "dy": round(_near_zero(src.get("dy", 0.0) or 0.0), 9),
    }


def changed_parameter_count(pose: dict[str, Any] | None) -> int:
    p = normalize_pose(pose)
    return sum(abs(float(p[k])) > SERIAL_TOL for k in POSE_KEYS)


def exact_full_pass(state: dict[str, Any]) -> bool:
    """The sole optimization oracle; planner flags are intentionally ignored."""
    return (str(state.get("status")) == "passed" and
            float(state.get("passed_pct", -1.0)) == 100.0)


def _rotation_matrix_signature(pose: dict[str, float]) -> tuple[float, ...]:
    matrix = rot_zxz(pose["spin"], pose["tilt"], pose["turn"])
    return tuple(round(float(v), 9) for v in matrix.ravel())


def _rz(degrees: float) -> np.ndarray:
    a = math.radians(float(degrees))
    c, s = math.cos(a), math.sin(a)
    return np.array(((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0)))


@lru_cache(maxsize=None)
def hole_symmetry_order(hole: str) -> int:
    """Return only symmetries verified against the live hole polygon."""
    poly = profiles.build(cc.HOLES[hole], quality=1.0)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 1e-12:
        raise UniverseError(f"hole {hole!r} has empty geometry")
    valid = []
    for order in (12, 8, 6, 5, 4, 3, 2):
        rotated = affinity.rotate(poly, 360.0 / order, origin=(0.0, 0.0))
        if poly.symmetric_difference(rotated).area <= 1e-7 * max(poly.area, 1.0):
            valid.append(order)
    return max(valid) if valid else 1


def _physical_pose_signature(hole: str,
                             pose: dict[str, Any]) -> tuple[float, ...]:
    """Canonicalize under exact Euler and verified hole symmetries.

    A verified in-plane symmetry permits rotating both body orientation and
    lateral offset together.  No unproved body symmetry is assumed.
    """
    p = normalize_pose(pose)
    matrix = rot_zxz(p["spin"], p["tilt"], p["turn"])
    shift = np.array((p["dx"], p["dy"], 0.0))
    order = hole_symmetry_order(hole)
    signatures = []
    for index in range(order):
        transform = _rz(-360.0 * index / order)
        m = transform @ matrix
        s = transform @ shift
        signatures.append(tuple(
            round(float(v), 8) for v in (*m.ravel(), s[0], s[1])))
    return min(signatures)


@lru_cache(maxsize=None)
def body_geometry_fingerprint(body: str) -> str:
    obj = build_body(copy.deepcopy(cc.BODIES[body]))
    projections = obj.projections(1.0)
    payload = {
        "spec": cc.BODIES[body],
        "volume": round(float(obj.volume(1.0)), 8),
        "projections": {
            name: {
                "area": round(float(poly.area), 8),
                "bounds": [round(float(v), 8) for v in poly.bounds],
                "wkb_sha256": _sha256_bytes(poly.wkb),
            }
            for name, poly in sorted(projections.items())
        },
    }
    return _sha256_json(payload)


@lru_cache(maxsize=None)
def hole_geometry_fingerprint(hole: str) -> str:
    poly = profiles.build(cc.HOLES[hole], quality=1.0)
    if not poly.is_valid:
        poly = poly.buffer(0)
    payload = {
        "spec": cc.HOLES[hole],
        "area": round(float(poly.area), 8),
        "perimeter": round(float(poly.length), 8),
        "bounds": [round(float(v), 8) for v in poly.bounds],
        "wkb_sha256": _sha256_bytes(poly.wkb),
    }
    return _sha256_json(payload)


@lru_cache(maxsize=1)
def sut_source_fingerprint() -> str:
    """Bind proof identities to the exact live physics/API/recording code."""
    relative_files = (
        "sieve3d/api_v1.py", "sieve3d/bodies.py", "sieve3d/experiment.py",
        "sieve3d/geometry.py", "sieve3d/passage.py", "sieve3d/profiles.py",
        "sieve3d/recorder.py", "sieve3d/scene.py", "sieve3d/server.py",
        "sieve3d/wiggle.py",
    )
    payload = {}
    for relative in relative_files:
        path = SIEVE3D_ROOT / relative
        if not path.is_file():
            raise UniverseError(f"required SUT source is missing: {path}")
        payload[relative] = _sha256_file(path)
    return _sha256_json(payload)


def live_bodies() -> tuple[str, ...]:
    return tuple(cc.BODIES)


def live_holes() -> tuple[str, ...]:
    return tuple(cc.HOLES)


def _framework_product(name: str,
                       factors: Sequence[tuple[str, Sequence[Any]]]
                       ) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    """Enumerate a full product through the repository's FW_Combi model."""
    slots = []
    decoded: dict[str, dict[str, Any]] = {}
    for sheet, domain in factors:
        if not domain:
            raise UniverseError(f"factor {sheet} has an empty domain")
        values = []
        decoded[sheet] = {}
        for index, item in enumerate(domain):
            token = f"{sheet}:{index}:{_sha256_json(item)[:12]}"
            values.append(token)
            decoded[sheet][token] = item
        slots.append(fg.Slot(
            sheet=sheet, key=sheet.lower(), values=values,
            verb="FW_Combi(1)", raw=False,
        ))
    spec = fg.Spec(name=name, title=name, slots=slots, spec_version="1")
    plan = fg.spec_cardinality_plan(spec)
    if plan.mandatory.value is None:
        raise UniverseError(f"Framework could not prove cardinality for {name}")
    combos = []
    for row in fg.cartesian(spec):
        combos.append(tuple(
            decoded[slot.sheet][token] for slot, token in zip(slots, row)))
    raw = math.prod(len(domain) for _, domain in factors)
    if len(combos) != raw or plan.mandatory.value != raw:
        raise UniverseError(
            f"Framework cardinality mismatch for {name}: "
            f"raw={raw}, plan={plan.mandatory.value}, emitted={len(combos)}")
    provenance = {
        "mechanism": "fwgen.Spec + FW_Combi(1) + fwgen.cartesian",
        "factors": [
            {
                "sheet": sheet,
                "verb": "FW_Combi(1)",
                "domain_cardinality": len(domain),
                "physical_meaning": _factor_meaning(sheet),
            }
            for sheet, domain in factors
        ],
        "raw_cartesian_cardinality": raw,
        "framework_cardinality": plan.mandatory.value,
        "emitted_cardinality": len(combos),
        "coverage_design": "full_product",
        "nwise_reduction": False,
        "hard_cap": None,
    }
    return combos, provenance


def _factor_meaning(sheet: str) -> str:
    meanings = {
        "ROTATION": "one declared rigid SO(3) orientation representative",
        "SHIFT": "one declared lateral translation relative to the fixed hole",
        "DYNAMIC_SEED": "starting rigid pose for a multi-move descent",
        "WIGGLE_BUDGET": "exact number of post-drop wiggle actions",
        "PLANNER": "one declared final-stage planner or adaptive queue",
        "PLANNER_SEED": "starting rigid pose for a final-stage trajectory",
    }
    return meanings.get(sheet, "user-declared experiment factor")


def _campaign_pose_rows(body: str, hole: str) -> list[PoseSeed]:
    out = []
    for index, campaign in enumerate(cc.CAMPAIGNS):
        if campaign.get("body") != body or campaign.get("hole") != hole:
            continue
        pose = campaign.get("pose")
        if isinstance(pose, dict):
            out.append(PoseSeed(
                label=f"campaign_{index}",
                pose=normalize_pose(pose),
                sources=(f"cc.CAMPAIGNS[{index}]",),
            ))
    return out


def _anchor_pose_rows(body: str, hole: str,
                      config: SearchConfig) -> list[PoseSeed]:
    harness = cc.make_scene([body], [hole])
    out = []
    for label, spin, tilt in config.anchor_seeds:
        try:
            response = harness.call(
                "POST", "/api/v1/anchor", api_v1.h_anchor,
                {"body": body, "hole": hole,
                 "spin": float(spin), "tilt": float(tilt)},
            )
        except Exception as exc:  # candidate derivation failure is infrastructure
            raise UniverseError(
                f"anchor derivation failed for {body}->{hole}/{label}: "
                f"{type(exc).__name__}: {exc}") from exc
        out.append(PoseSeed(
            label=f"anchor_{label}",
            pose=normalize_pose(response.get("pose") or {}),
            sources=(
                "api_v1.h_anchor",
                "geometry.principal_axis",
                f"anchor_seed:{label}",
            ),
        ))
    return out


def _source_pose_domains(body: str, hole: str,
                         config: SearchConfig
                         ) -> tuple[list[PoseSeed], list[PoseSeed],
                                    list[PoseSeed], dict[str, Any]]:
    rotations = [PoseSeed(
        label=label,
        pose=normalize_pose({"spin": spin, "tilt": tilt, "turn": turn}),
        sources=("user.rotation_seeds", f"named:{label}"),
    ) for label, spin, tilt, turn in config.rotation_seeds]
    shifts = [PoseSeed(
        label=label,
        pose=normalize_pose({"dx": dx, "dy": dy}),
        sources=("user.shift_seeds", f"named:{label}"),
    ) for label, dx, dy in config.shift_seeds]

    campaigns = _campaign_pose_rows(body, hole)
    anchors = _anchor_pose_rows(body, hole, config)
    rotations.extend(PoseSeed(
        label=f"{seed.label}_rotation",
        pose=normalize_pose({k: seed.pose[k]
                             for k in ("spin", "tilt", "turn")}),
        sources=seed.sources + ("audited_candidate_poses",),
    ) for seed in campaigns + anchors)
    shifts.extend(PoseSeed(
        label=f"{seed.label}_shift",
        pose=normalize_pose({k: seed.pose[k] for k in ("dx", "dy")}),
        sources=seed.sources + ("feature_or_centroid_alignment",),
    ) for seed in campaigns + anchors)

    delta_ang = float(config.campaign_rotation_refinement_deg)
    delta_xy = float(config.campaign_shift_refinement_mm)
    if delta_ang > 0:
        for seed in campaigns:
            key = next((name for name in ("spin", "tilt", "turn")
                        if abs(seed.pose[name]) > SERIAL_TOL), "turn")
            for sign in (-1.0, 1.0):
                pose = dict(seed.pose)
                pose[key] += sign * delta_ang
                rotations.append(PoseSeed(
                    label=f"{seed.label}_{key}_{sign:+.0f}",
                    pose=normalize_pose({k: pose[k] for k in
                                         ("spin", "tilt", "turn")}),
                    sources=seed.sources + (
                        f"deterministic_rotation_refinement:{key}:"
                        f"{sign * delta_ang:+g}",),
                ))
    if delta_xy > 0:
        for seed in campaigns:
            if abs(seed.pose["dx"]) <= SERIAL_TOL and abs(
                    seed.pose["dy"]) <= SERIAL_TOL:
                continue
            for key in (name for name in ("dx", "dy")
                        if abs(seed.pose[name]) > SERIAL_TOL):
                for sign in (-1.0, 1.0):
                    pose = dict(seed.pose)
                    pose[key] += sign * delta_xy
                    shifts.append(PoseSeed(
                        label=f"{seed.label}_{key}_{sign:+.0f}",
                        pose=normalize_pose({"dx": pose["dx"],
                                             "dy": pose["dy"]}),
                        sources=seed.sources + (
                            f"deterministic_shift_refinement:{key}:"
                            f"{sign * delta_xy:+g}",),
                    ))

    dynamic = [PoseSeed(
        label=label,
        pose=normalize_pose(dict(zip(POSE_KEYS, values))),
        sources=("user.dynamic_seed_poses", f"named:{label}"),
    ) for label, *values in config.dynamic_seed_poses]
    dynamic.extend(campaigns)
    anchor_campaign = any(
        campaign.get("body") == body and campaign.get("hole") == hole and
        campaign.get("pose") == "anchor"
        for campaign in cc.CAMPAIGNS)
    if anchor_campaign and anchors:
        dynamic.append(PoseSeed(
            label="campaign_live_anchor",
            pose=anchors[0].pose,
            sources=(
                "complex_cases.CAMPAIGNS:pose=anchor",
                "api_v1.h_anchor",
                "geometry.principal_axis",
            ),
        ))

    provenance = {
        "canonical_pose_source": "SearchConfig.rotation_seeds",
        "campaign_pose_source": "complex_cases.CAMPAIGNS",
        "audited_candidate_pose_source": (
            "canonical + campaign + live /api/v1/anchor"),
        "anchor_source": "api_v1.h_anchor/principal_axis",
        "user_angular_samples": len(config.rotation_seeds),
        "user_shift_samples": len(config.shift_seeds),
        "anchor_samples": len(anchors),
        "campaign_samples": len(campaigns),
        "rotation_refinement_delta_deg": delta_ang,
        "shift_refinement_delta_mm": delta_xy,
    }
    return rotations, shifts, dynamic, provenance


def _wiggle_budgets_for_pair(body: str, hole: str,
                             config: SearchConfig) -> tuple[int, ...]:
    for configured_body, configured_hole, budgets in \
            config.pair_wiggle_budgets:
        if configured_body == body and configured_hole == hole:
            return tuple(int(n) for n in budgets)
    return tuple(int(n) for n in config.wiggle_budgets)


def _dedupe_pose_seeds(hole: str, seeds: Iterable[PoseSeed],
                       *, reject_zero: bool = False
                       ) -> tuple[list[PoseSeed], dict[str, Any]]:
    merged: dict[tuple[float, ...], PoseSeed] = {}
    raw = 0
    zero_signature = _physical_pose_signature(hole, normalize_pose(None))
    no_op = 0
    for seed in seeds:
        raw += 1
        pose = normalize_pose(seed.pose)
        signature = _physical_pose_signature(hole, pose)
        if reject_zero and signature == zero_signature:
            no_op += 1
            continue
        previous = merged.get(signature)
        if previous is None:
            merged[signature] = PoseSeed(seed.label, pose, tuple(seed.sources))
        else:
            sources = tuple(dict.fromkeys(previous.sources + seed.sources))
            merged[signature] = PoseSeed(previous.label, previous.pose, sources)
    out = list(merged.values())
    out.sort(key=lambda seed: (
        _physical_pose_signature(hole, seed.pose), seed.label, seed.sources))
    return out, {
        "raw": raw,
        "rejected_no_op": no_op,
        "equivalence_reductions": raw - no_op - len(out),
        "normalized_unique": len(out),
        "normalization": (
            "angles modulo 360; near-zero offsets; exact rotation matrices; "
            f"verified hole symmetry order {hole_symmetry_order(hole)}"),
    }


def _fit_evidence(harness: Any, body: str, hole: str,
                  pose: dict[str, float]) -> dict[str, Any]:
    try:
        fit = harness.fits(body, hole, pose)
    except Exception as exc:
        raise UniverseError(
            f"fit derivation failed for {body}->{hole}: "
            f"{type(exc).__name__}: {exc}") from exc
    clearance = fit.get("clearance")
    return {
        "fit_feasible": bool(fit.get("feasible")),
        "estimated_clearance": round(
            float(clearance if clearance is not None else -1e9), 8),
    }


def _candidate(
        body: str,
        hole: str,
        stage: str,
        family: str,
        tier: int,
        pose: dict[str, Any],
        action_plan: list[dict[str, Any]],
        dynamic_options: dict[str, Any],
        sources: Sequence[str],
        config: SearchConfig,
        body_fp: str,
        hole_fp: str,
        parent_candidate_id: str | None,
) -> dict[str, Any]:
    normalized = normalize_pose(pose)
    signature_payload = {
        "body": body,
        "hole": hole,
        "stage": stage,
        "family": family,
        "tier": tier,
        "physical_pose_signature": _physical_pose_signature(hole, normalized),
        "action_plan": action_plan,
        "dynamic_options": dynamic_options,
        "policy": config.rigid_policy,
        "modification": config.modification,
        "config_digest": config.digest,
        "sut_source_fingerprint": sut_source_fingerprint(),
    }
    signature = _canonical_json(signature_payload)
    digest = _sha256_bytes(signature.encode("utf-8"))
    candidate_id = (
        f"{_safe(body)}--{_safe(hole)}--{STAGE_ORDER[stage]}-"
        f"{_safe(family)}--{digest[:16]}")
    return {
        "schema_version": CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "body": body,
        "hole": hole,
        "body_geometry_fingerprint": body_fp,
        "hole_geometry_fingerprint": hole_fp,
        "sut_source_fingerprint": sut_source_fingerprint(),
        "stage": stage,
        "semantic_family": family,
        "measured_action_tier": int(tier),
        "parent_candidate_id": parent_candidate_id,
        "provenance_sources": list(dict.fromkeys(sources)),
        "pose": normalized,
        "action_plan": action_plan,
        "dynamic_options": dynamic_options,
        "canonical_signature": signature,
        "canonical_signature_sha256": digest,
        "fit_rank": 0,
        "fit_feasible": False,
        "estimated_clearance": -1e9,
        "solution_action_cost": int(tier),
        "user_declared_execution_scope": {
            "config_id": config.config_id,
            "config_digest": config.digest,
            "policy": config.rigid_policy,
            "modification": config.modification,
            "continuous_space_claimed": False,
        },
        "changed_parameter_count": changed_parameter_count(normalized),
    }


def generate_pair_universe(body: str, hole: str,
                           config: SearchConfig | None = None
                           ) -> dict[str, Any]:
    config = config or SearchConfig()
    config.validate()
    if body not in cc.BODIES:
        raise UniverseError(f"unknown body {body!r}")
    if hole not in cc.HOLES:
        raise UniverseError(f"unknown hole {hole!r}")
    body_fp = body_geometry_fingerprint(body)
    hole_fp = hole_geometry_fingerprint(hole)
    rotation_raw, shift_raw, dynamic_raw, source_provenance = \
        _source_pose_domains(body, hole, config)
    rotations, rotation_counts = _dedupe_pose_seeds(
        hole, rotation_raw, reject_zero=True)
    shifts, shift_counts = _dedupe_pose_seeds(
        hole, shift_raw, reject_zero=True)
    dynamic_seeds, dynamic_counts = _dedupe_pose_seeds(
        hole, dynamic_raw, reject_zero=True)
    if not rotations or not shifts:
        raise UniverseError(
            f"normalization made a required factor empty for {body}->{hole}")
    if not dynamic_seeds:
        raise UniverseError(
            f"normalization made the dynamic seed factor empty for {body}->{hole}")

    factors: dict[str, Any] = {
        "source_derivation": source_provenance,
        "rotation": rotation_counts,
        "shift": shift_counts,
        "dynamic_seed": dynamic_counts,
    }
    candidates: list[dict[str, Any]] = []
    neutral = _candidate(
        body, hole, "neutral", "neutral_drop", 1, normalize_pose(None),
        [
            {"action": "assign", "params": {"hole": hole}, "cost": 0},
            {"action": "drop", "params": {"max_dz": 300.0}, "cost": 1},
        ],
        {},
        ("required_stage_0", "true_neutral_pose"),
        config, body_fp, hole_fp, None,
    )
    candidates.append(neutral)
    neutral_id = neutral["candidate_id"]

    rotation_rows, rotation_product = _framework_product(
        f"{body}_{hole}_rotation", (("ROTATION", rotations),))
    factors["rotation"]["framework"] = rotation_product
    for (seed,) in rotation_rows:
        candidates.append(_candidate(
            body, hole, "rotation", "rotation_then_drop", 2, seed.pose,
            [
                {"action": "assign", "params": {"hole": hole}, "cost": 0},
                {"action": "set_pose",
                 "params": {k: seed.pose[k] for k in
                            ("spin", "tilt", "turn")}, "cost": 1},
                {"action": "drop", "params": {"max_dz": 300.0}, "cost": 1},
            ],
            {}, seed.sources, config, body_fp, hole_fp, neutral_id,
        ))

    shift_rows, shift_product = _framework_product(
        f"{body}_{hole}_shift", (("SHIFT", shifts),))
    factors["shift"]["framework"] = shift_product
    for (seed,) in shift_rows:
        candidates.append(_candidate(
            body, hole, "shift", "shift_then_drop", 2, seed.pose,
            [
                {"action": "assign", "params": {"hole": hole}, "cost": 0},
                {"action": "set_pose",
                 "params": {k: seed.pose[k] for k in ("dx", "dy")},
                 "cost": 1},
                {"action": "drop", "params": {"max_dz": 300.0}, "cost": 1},
            ],
            {}, seed.sources, config, body_fp, hole_fp, neutral_id,
        ))

    mixed_rows, mixed_product = _framework_product(
        f"{body}_{hole}_mixed",
        (("ROTATION", rotations), ("SHIFT", shifts)),
    )
    mixed_seeds = []
    for rotation, shift in mixed_rows:
        pose = dict(rotation.pose)
        pose["dx"], pose["dy"] = shift.pose["dx"], shift.pose["dy"]
        mixed_seeds.append(PoseSeed(
            label=f"{rotation.label}+{shift.label}",
            pose=normalize_pose(pose),
            sources=rotation.sources + shift.sources +
            ("full_rotation_x_shift_product",),
        ))
    mixed_unique, mixed_counts = _dedupe_pose_seeds(
        hole, mixed_seeds, reject_zero=True)
    factors["mixed"] = {
        **mixed_counts,
        "framework": mixed_product,
        "raw_rotation_x_shift_cardinality": (
            len(rotations) * len(shifts)),
    }
    for seed in mixed_unique:
        candidates.append(_candidate(
            body, hole, "mixed", "atomic_rotation_plus_shift_then_drop",
            2, seed.pose,
            [
                {"action": "assign", "params": {"hole": hole}, "cost": 0},
                {"action": "set_pose", "params": dict(seed.pose), "cost": 1},
                {"action": "drop", "params": {"max_dz": 300.0}, "cost": 1},
            ],
            {"atomic_pose_update": True}, seed.sources,
            config, body_fp, hole_fp, neutral_id,
        ))

    wiggle_budgets = _wiggle_budgets_for_pair(body, hole, config)
    dynamic_rows, dynamic_product = _framework_product(
        f"{body}_{hole}_dynamic",
        (("DYNAMIC_SEED", dynamic_seeds),
         ("WIGGLE_BUDGET", wiggle_budgets)),
    )
    factors["multi_move"] = {
        "framework": dynamic_product,
        "declared_wiggle_action_ceilings": list(wiggle_budgets),
        "normalized_unique": len(dynamic_rows),
        "sequence_semantics": (
            "assign -> one non-neutral set_pose -> drop -> at most N "
            "wiggles; every response state proves the deterministic prefix "
            "and execution stops at the first exact full pass"),
    }
    for seed, budget in dynamic_rows:
        plan = [
            {"action": "assign", "params": {"hole": hole}, "cost": 0},
            {"action": "set_pose", "params": dict(seed.pose), "cost": 1},
            {"action": "drop", "params": {"max_dz": 300.0}, "cost": 1},
        ]
        plan.extend({
            "action": "wiggle",
            "params": {"dz": config.wiggle_dz,
                       "evals": config.wiggle_evals},
            "cost": 1,
        } for _ in range(int(budget)))
        candidates.append(_candidate(
            body, hole, "multi_move", "wiggle_descent",
            2 + int(budget), seed.pose, plan,
            {
                "maximum_wiggle_actions": int(budget),
                "all_lower_prefix_states_recorded": True,
                "sequence_length": len(plan) - 1,
                "stop_on_full_pass": True,
            },
            seed.sources + ("user_exact_multi_move_budget",),
            config, body_fp, hole_fp, neutral_id,
        ))

    planner_specs = []
    for algorithm in config.planner_algorithms:
        spec = {"algorithm": algorithm}
        if algorithm == "adaptive-switch-thread":
            spec["algorithm_queue"] = list(config.adaptive_queue)
        planner_specs.append(spec)
    planner_rows, planner_product = _framework_product(
        f"{body}_{hole}_planner",
        (("PLANNER", planner_specs), ("PLANNER_SEED", dynamic_seeds)),
    )
    factors["screw_thread"] = {
        "framework": planner_product,
        "algorithms": list(config.planner_algorithms),
        "adaptive_queue": list(config.adaptive_queue),
        "budget": config.planner_budget,
        "max_candidates": config.planner_max_candidates,
        "frames_per_segment": config.planner_frames,
        "max_steps": config.planner_max_steps,
        "evals": config.planner_evals,
        "starts": config.planner_starts,
        "lookahead": config.planner_lookahead,
        "retreats": config.planner_retreats,
        "escape_rounds": config.planner_escape_rounds,
        "escape_starts": config.planner_escape_starts,
        "escape_evals": config.planner_escape_evals,
        "normalized_unique": len(planner_rows),
    }
    final_declared_tier = config.planner_frames
    for planner, seed in planner_rows:
        algorithm = planner["algorithm"]
        candidates.append(_candidate(
            body, hole, "screw_thread", algorithm, final_declared_tier,
            seed.pose,
            [
                {"action": "plan_passage", "params": dict(planner),
                 "cost": 0},
                {"action": "assign", "params": {"hole": hole}, "cost": 0},
                {"action": "apply_planner_frames",
                 "params": {"declared_frames": config.planner_frames},
                 "cost": config.planner_frames},
            ],
            {
                **planner,
                "frames": config.planner_frames,
                "budget": config.planner_budget,
                "max_candidates": config.planner_max_candidates,
                "max_steps": config.planner_max_steps,
                "rounds": config.planner_rounds,
                "evals": config.planner_evals,
                "starts": config.planner_starts,
                "lookahead": config.planner_lookahead,
                "retreats": config.planner_retreats,
                "escape_rounds": config.planner_escape_rounds,
                "escape_starts": config.planner_escape_starts,
                "escape_evals": config.planner_escape_evals,
                "handoff_limit": config.planner_handoff_limit,
                "rigid_only": True,
            },
            seed.sources + ("final_stage_declared_planner",),
            config, body_fp, hole_fp, neutral_id,
        ))

    # Fit is ordering evidence only.  It never deletes a candidate.
    fit_harness = cc.make_scene([body], [hole])
    fit_cache: dict[tuple[float, ...], dict[str, Any]] = {}
    for candidate in candidates:
        sig = _physical_pose_signature(hole, candidate["pose"])
        if sig not in fit_cache:
            cache_key = (body, hole, sig)
            if cache_key not in _PAIR_FIT_CACHE:
                _PAIR_FIT_CACHE[cache_key] = _fit_evidence(
                    fit_harness, body, hole, candidate["pose"])
            fit_cache[sig] = dict(_PAIR_FIT_CACHE[cache_key])
        candidate.update(fit_cache[sig])

    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate["stage"], []).append(candidate)
    ordered = []
    for stage in STAGE_ORDER:
        rows = grouped.get(stage, [])
        if stage == "neutral":
            if len(rows) != 1:
                raise UniverseError("neutral stage must contain exactly one candidate")
        else:
            rows.sort(key=lambda row: (
                -int(bool(row["fit_feasible"])),
                -float(row["estimated_clearance"]),
                int(row["measured_action_tier"]),
                row["canonical_signature_sha256"],
            ))
        for rank, row in enumerate(rows, 1):
            row["fit_rank"] = rank
        ordered.extend(rows)

    ids = [row["candidate_id"] for row in ordered]
    if len(ids) != len(set(ids)):
        raise UniverseError("canonical candidate-id collision")
    static_count = sum(row["stage"] in {"rotation", "shift", "mixed"}
                       for row in ordered)
    max_declared_actions = sum(int(row["measured_action_tier"])
                               for row in ordered)
    pre_normalization_stage_cardinalities = {
        "neutral": 1,
        "rotation": int(rotation_counts["raw"]),
        "shift": int(shift_counts["raw"]),
        "mixed": int(rotation_counts["raw"]) * int(shift_counts["raw"]),
        "multi_move": int(dynamic_counts["raw"]) * len(wiggle_budgets),
        "screw_thread": int(dynamic_counts["raw"]) * len(planner_specs),
    }
    raw_candidate_cardinality = sum(
        pre_normalization_stage_cardinalities.values())
    universe = {
        "schema_version": UNIVERSE_SCHEMA,
        "body": body,
        "hole": hole,
        "pair_id": f"{body}--{hole}",
        "body_geometry_fingerprint": body_fp,
        "hole_geometry_fingerprint": hole_fp,
        "sut_source_fingerprint": sut_source_fingerprint(),
        "policy": config.to_dict(),
        "policy_digest": config.digest,
        "factors": factors,
        "raw_candidate_cardinality": raw_candidate_cardinality,
        "normalized_unique_cardinality": len(ordered),
        "pre_normalization_stage_cardinalities": (
            pre_normalization_stage_cardinalities),
        "stage_cardinalities": {
            stage: sum(row["stage"] == stage for row in ordered)
            for stage in STAGE_ORDER
        },
        "resource_implications": {
            "maximum_attempts_if_exhausted": len(ordered),
            "maximum_declared_solution_actions_summed": max_declared_actions,
            "maximum_record_files": len(ordered) if config.record_attempts else 0,
            "static_candidates": static_count,
            "planner_candidates": sum(
                row["stage"] == "screw_thread" for row in ordered),
            "hidden_candidate_cap": None,
            "downsampling": False,
            "covering_array_fallback": False,
        },
        "ordering": {
            "semantic_stage_order": list(STAGE_ORDER),
            "within_stage": (
                "fit feasible, clearance descending, measured tier, "
                "canonical signature"),
            "selection_tie_break": [
                "exact_full_pass",
                "solution_action_cost",
                "solution_keyframes",
                "changed_parameter_count",
                "worst_clearance_desc",
                "candidate_id",
            ],
        },
        "proof_scope": (
            "minimum successful measured-action tier within the complete "
            "user-declared candidate universe realized for this fixed "
            "geometry and policy"),
        "continuous_global_optimum_claimed": False,
        "mathematical_impossibility_claimed": False,
        "candidates": ordered,
    }
    universe["canonical_sha256"] = _sha256_json({
        key: value for key, value in universe.items()
        if key != "canonical_sha256"
    })
    return universe


def generate_pair_universe_twice(
        body: str, hole: str, config: SearchConfig | None = None
) -> tuple[dict[str, Any], bool]:
    first = generate_pair_universe(body, hole, config)
    second = generate_pair_universe(body, hole, config)
    equal = _canonical_json(first) == _canonical_json(second)
    if not equal:
        raise UniverseError(
            f"non-deterministic universe generation for {body}->{hole}")
    return first, True


def _record_start(harness: Any) -> None:
    harness.call(
        "POST", "/api/v1/record", api_v1.h_record, {"cmd": "action"})


def _motion_frame_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    frames = value.get("frames")
    count = len(frames) if isinstance(frames, list) else 0
    best = value.get("best")
    if isinstance(best, dict) and best is not value:
        count = max(count, _motion_frame_count(best))
    return count


def _finish_record(
        harness: Any,
        candidate: dict[str, Any],
        record_dir: Path,
        run_id: str,
        attempt_index: int,
) -> dict[str, Any]:
    try:
        harness.call(
            "POST", "/api/v1/record", api_v1.h_record, {"cmd": "cut"})
    except api_v1.ApiError as exc:
        if exc.code != "conflict":
            raise
    info = harness.call(
        "POST", "/api/v1/record", api_v1.h_record,
        {"cmd": "retrieve_last_record"},
    )
    records = list(info.get("records") or ())
    if not records:
        raise EvidenceError("record retrieval returned no entries")
    record_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{attempt_index:04d}_{_safe(candidate['candidate_id'])}"
    rec_path = record_dir / f"{stem}.rec"
    metadata_path = record_dir / f"{stem}.json"
    rec_path.write_text(
        "".join(_canonical_json(row) + "\n" for row in records),
        encoding="utf-8",
    )
    steps = [row for row in records if row.get("kind") == "step"]
    response_frames = sum(
        _motion_frame_count(row.get("response")) for row in steps)
    if rec_path.stat().st_size > MAX_RECORD_UPLOAD_BYTES:
        raise EvidenceError(
            f"record exceeds {MAX_RECORD_UPLOAD_BYTES} bytes")
    if len(steps) > MAX_RECORD_STEPS:
        raise EvidenceError(f"record exceeds {MAX_RECORD_STEPS} steps")
    if response_frames > MAX_MOTION_FRAMES:
        raise EvidenceError(
            f"record exceeds {MAX_MOTION_FRAMES} response motion frames")
    metadata = {
        "schema_version": "sieve3d-attempt-record-metadata/2",
        "run_id": run_id,
        "attempt_index": int(attempt_index),
        "candidate_id": candidate["candidate_id"],
        "body": candidate["body"],
        "hole": candidate["hole"],
        "source_record_file": info.get("file"),
        "source_record_path": info.get("path"),
        "saved_record_path": str(rec_path.resolve()),
        "record_step_count": len(steps),
        "response_motion_frame_count": response_frames,
        "snapshot_only": len(steps) == 0,
        "bounds": {
            "bytes": rec_path.stat().st_size,
            "max_bytes": MAX_RECORD_UPLOAD_BYTES,
            "steps": len(steps),
            "max_steps": MAX_RECORD_STEPS,
            "motion_frames": response_frames,
            "max_motion_frames": MAX_MOTION_FRAMES,
        },
        "manual_replay": {
            "copy_to": str(
                (SIEVE3D_ROOT / "records" / rec_path.name).resolve()),
            "api_path": "/api/v1/replay",
            "api_payload": {"file": rec_path.name, "speed": 0.1},
            "gui_steps": "File -> select record file -> Replay",
        },
        "record_sha256": _sha256_file(rec_path),
    }
    _write_json(metadata_path, metadata)
    return {
        "record_path": str(rec_path.resolve()),
        "metadata_path": str(metadata_path.resolve()),
        "record_sha256": metadata["record_sha256"],
        "metadata_sha256": _sha256_file(metadata_path),
        "record_step_count": len(steps),
        "record_response_frame_count": response_frames,
        "snapshot_only_record": len(steps) == 0,
    }


def _response_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"type": type(value).__name__}
    state = value.get("state") if isinstance(value.get("state"), dict) else {}
    best = value.get("best") if isinstance(value.get("best"), dict) else {}
    return {
        key: item for key, item in {
            "action": value.get("action"),
            "state_status": state.get("status"),
            "state_passed_pct": state.get("passed_pct"),
            "state_actions": state.get("actions"),
            "state_attempts": state.get("attempts"),
            "job": value.get("job"),
            "success": value.get("success", best.get("success")),
            "passed_pct": value.get("passed_pct", best.get("passed_pct")),
            "algorithm": value.get("algorithm", best.get("algorithm")),
            "frames": _motion_frame_count(value),
        }.items() if item is not None
    }


def _frame_pose(frame: dict[str, Any]) -> dict[str, float]:
    values = list(frame.get("pose") or ())
    if len(values) < len(POSE_KEYS):
        raise EvidenceError("planner frame is missing a five-parameter pose")
    return {key: float(values[index])
            for index, key in enumerate(POSE_KEYS)}


def _state_clearance(snapshot: dict[str, Any], body: str) -> float | None:
    state = (snapshot.get("bodies") or {}).get(body) or {}
    value = state.get("clearance_now")
    return float(value) if value is not None else None


def _execute_declared_actions(
        harness: Any,
        candidate: dict[str, Any],
        request_log: list[dict[str, Any]],
        response_log: list[dict[str, Any]],
        clearance_samples: list[float],
) -> dict[str, Any] | None:
    body = candidate["body"]
    last_state = None
    for item in candidate["action_plan"]:
        action = item["action"]
        if action in {"plan_passage", "apply_planner_frames"}:
            continue
        request = {
            "method": "POST",
            "path": "/api/v1/experiment/action",
            "body": body,
            "action": action,
            "params": dict(item.get("params") or {}),
        }
        request_log.append(request)
        result = harness.act(body, action, **request["params"])
        response_log.append(_response_summary(result))
        last_state = result.get("state")
        snapshot = harness.exp()
        request_log.append({"method": "GET", "path": "/api/v1/experiment"})
        response_log.append({
            "state_status": snapshot["bodies"][body]["status"],
            "state_passed_pct": snapshot["bodies"][body]["passed_pct"],
        })
        clearance = _state_clearance(snapshot, body)
        if clearance is not None:
            clearance_samples.append(clearance)
        if exact_full_pass(snapshot["bodies"][body]):
            break
    return last_state


def _execute_planner_candidate(
        harness: Any,
        candidate: dict[str, Any],
        request_log: list[dict[str, Any]],
        response_log: list[dict[str, Any]],
        clearance_samples: list[float],
) -> dict[str, Any]:
    body, hole = candidate["body"], candidate["hole"]
    options = dict(candidate["dynamic_options"])
    algorithm = str(options["algorithm"])

    request_log.append({"method": "GET", "path": "/api/v1/catalog"})
    catalog = harness.call("GET", "/api/v1/catalog", api_v1.h_catalog, {})
    response_log.append({
        "passage_algorithms": list(catalog.get("passage_algorithms") or ())})
    advertised = set(catalog.get("passage_algorithms") or ())
    if algorithm not in advertised:
        raise EvidenceError(
            f"planner {algorithm!r} is absent from the live API catalog")

    feature_payload = {
        "body": body, "hole": hole, "pose": candidate["pose"]}
    request_log.append({
        "method": "POST", "path": "/api/v1/features",
        "payload": feature_payload,
    })
    features = harness.call(
        "POST", "/api/v1/features", api_v1.h_features, feature_payload)
    feature_data = features.get("features") or {}
    feature_count = sum(
        len(((feature_data.get(owner) or {}).get(key) or ()))
        for owner in ("body", "hole")
        for key in ("edges", "edge_centers", "vertices"))
    response_log.append({"feature_count": feature_count})
    if feature_count <= 0:
        raise EvidenceError("planner features are empty")

    payload = {
        "body": body,
        "hole": hole,
        "sut_source_fingerprint": candidate["sut_source_fingerprint"],
        "pose": dict(candidate["pose"]),
        "wait": True,
        "frames": int(options["frames"]),
        "algorithms": [algorithm],
        "budget": str(options["budget"]),
        "max_candidates": int(options["max_candidates"]),
        "rounds": int(options["rounds"]),
        "evals": int(options["evals"]),
        "starts": int(options["starts"]),
        "lookahead": int(options["lookahead"]),
        "max_steps": int(options["max_steps"]),
        "retreats": int(options["retreats"]),
        "escape_rounds": int(options["escape_rounds"]),
        "escape_starts": int(options["escape_starts"]),
        "escape_evals": int(options["escape_evals"]),
        "handoff_limit": int(options["handoff_limit"]),
        "kp": 0.7,
        "ki": 0.05,
        "kd": 0.22,
    }
    if algorithm == "adaptive-switch-thread":
        payload["algorithm_queue"] = list(options["algorithm_queue"])
    request_log.append({
        "method": "POST", "path": "/api/v1/passage",
        "payload": copy.deepcopy(payload),
    })
    planner = harness.call(
        "POST", "/api/v1/passage", api_v1.h_passage, payload)
    response_log.append(_response_summary(planner))
    best = planner.get("best") or {}
    frames = list(best.get("frames") or ())
    if not frames:
        raise EvidenceError("planner returned no physical motion frames")
    if len(frames) > MAX_MOTION_FRAMES:
        raise EvidenceError("planner returned too many physical motion frames")

    request_log.append({
        "method": "POST", "path": "/api/v1/experiment/action",
        "body": body, "action": "assign", "params": {"hole": hole},
    })
    assigned = harness.act(body, "assign", hole=hole)
    response_log.append(_response_summary(assigned))
    applied = 0
    for index, frame in enumerate(frames):
        params = _frame_pose(frame)
        params["z"] = float(frame["z"])
        request_log.append({
            "method": "POST", "path": "/api/v1/experiment/action",
            "body": body, "action": "set_pose", "params": dict(params),
            "planner_frame": index,
        })
        result = harness.act(body, "set_pose", **params)
        response_log.append(_response_summary(result))
        applied += 1
        snapshot = harness.exp()
        request_log.append({"method": "GET", "path": "/api/v1/experiment"})
        response_log.append({
            "state_status": snapshot["bodies"][body]["status"],
            "state_passed_pct": snapshot["bodies"][body]["passed_pct"],
            "planner_frame": index,
        })
        clearance = _state_clearance(snapshot, body)
        if clearance is not None:
            clearance_samples.append(clearance)
    return {
        "planner": planner,
        "planner_reported_success": bool(best.get("success")),
        "planner_reported_passed_pct": float(best.get("passed_pct") or 0.0),
        "planner_algorithm": best.get("algorithm") or algorithm,
        "planner_response_frames": len(frames),
        "planner_frames_physically_applied": applied,
        "planner_estimated_cost": int(
            (planner.get("complexity") or {}).get("estimated_cost") or 0),
        "planner_keyframes": int(
            (planner.get("complexity") or {}).get("keyframes") or
            best.get("keyframes") or 0),
        "planner_worst_clearance": best.get("worst_clearance"),
        "feature_count": feature_count,
    }


def execute_candidate(
        candidate: dict[str, Any],
        *,
        run_id: str,
        attempt_index: int,
        record_dir: Path,
        record: bool = True,
) -> dict[str, Any]:
    """Execute one candidate in a fresh real-SUT harness."""
    started = time.perf_counter()
    body, hole = candidate["body"], candidate["hole"]
    harness = cc.make_scene([body], [hole])
    request_log: list[dict[str, Any]] = []
    response_log: list[dict[str, Any]] = []
    clearance_samples: list[float] = []
    domain_errors: list[dict[str, Any]] = []
    unexpected_exception = None
    infrastructure_valid = True
    planner_evidence: dict[str, Any] = {}
    record_evidence: dict[str, Any] = {
        "record_path": "none",
        "metadata_path": "none",
        "record_sha256": "none",
        "metadata_sha256": "none",
        "record_step_count": 0,
        "record_response_frame_count": 0,
        "snapshot_only_record": True,
    }
    if record:
        _record_start(harness)
    try:
        if candidate["stage"] == "screw_thread":
            planner_evidence = _execute_planner_candidate(
                harness, candidate, request_log, response_log,
                clearance_samples)
        else:
            _execute_declared_actions(
                harness, candidate, request_log, response_log,
                clearance_samples)
    except api_v1.ApiError as exc:
        details = dict(getattr(exc, "details", {}) or {})
        domain_errors.append({
            "code": exc.code,
            "message": str(exc),
            "details": details,
            "request_index": len(request_log) - 1,
        })
        response_log.append({
            "error": {"code": exc.code, "message": str(exc),
                      "details": details}})
        if exc.code not in EXPECTED_DOMAIN_ERRORS:
            infrastructure_valid = False
    except (EvidenceError, UniverseError) as exc:
        infrastructure_valid = False
        unexpected_exception = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001 - serialized as invalid evidence
        infrastructure_valid = False
        unexpected_exception = f"{type(exc).__name__}: {exc}"

    try:
        snapshot = harness.exp()
        request_log.append({"method": "GET", "path": "/api/v1/experiment"})
        response_log.append({
            "state_status": snapshot["bodies"][body]["status"],
            "state_passed_pct": snapshot["bodies"][body]["passed_pct"],
            "final": True,
        })
    except Exception as exc:  # noqa: BLE001
        snapshot = {"bodies": {body: {
            "status": "infrastructure_invalid", "passed_pct": -1.0,
            "actions": -1, "attempts": -1, "pose": {}, "z": 0.0,
        }}}
        infrastructure_valid = False
        unexpected_exception = unexpected_exception or (
            f"final_snapshot:{type(exc).__name__}: {exc}")

    final_state = copy.deepcopy(snapshot["bodies"][body])
    full_pass = exact_full_pass(final_state)
    if record:
        try:
            record_evidence = _finish_record(
                harness, candidate, record_dir, run_id, attempt_index)
        except Exception as exc:  # noqa: BLE001
            infrastructure_valid = False
            unexpected_exception = unexpected_exception or (
                f"record_finish:{type(exc).__name__}: {exc}")

    action_requests = [
        row for row in request_log
        if row.get("path") == "/api/v1/experiment/action"]
    frame_count = int(planner_evidence.get(
        "planner_frames_physically_applied", 0))
    solution_actions = int(final_state.get("actions", -1))
    physical_state_observations = [
        {
            "actions": int(row["state_actions"]),
            "status": str(row.get("state_status")),
            "passed_pct": float(row.get("state_passed_pct", -1.0)),
        }
        for row in response_log if row.get("state_actions") is not None
    ]
    first_full_action_cost = next((
        row["actions"] for row in physical_state_observations
        if exact_full_pass({
            "status": row["status"], "passed_pct": row["passed_pct"]})
    ), None)
    solution_keyframes = (
        frame_count if candidate["stage"] == "screw_thread"
        else max(solution_actions, 0)
    )
    worst_values = list(clearance_samples)
    planner_clearance = planner_evidence.get("planner_worst_clearance")
    if planner_clearance is not None:
        worst_values.append(float(planner_clearance))
    if not worst_values and candidate.get("estimated_clearance") is not None:
        worst_values.append(float(candidate["estimated_clearance"]))
    worst_clearance = min(worst_values) if worst_values else -1e9
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "attempt_index": int(attempt_index),
        "candidate_id": candidate["candidate_id"],
        "deterministic_run_identity": _sha256_json({
            "run_id": run_id,
            "attempt_index": attempt_index,
            "candidate_id": candidate["candidate_id"],
            "candidate_signature": candidate["canonical_signature_sha256"],
        }),
        "run_id": run_id,
        "body": body,
        "hole": hole,
        "sut_source_fingerprint": candidate["sut_source_fingerprint"],
        "stage": candidate["stage"],
        "semantic_family": candidate["semantic_family"],
        "measured_action_tier": candidate["measured_action_tier"],
        "request_summary": request_log,
        "response_summary": response_log,
        "status": str(final_state.get("status")),
        "passed_pct": float(final_state.get("passed_pct", -1.0)),
        "full_pass": bool(full_pass),
        "independent_full_pass": bool(exact_full_pass(final_state)),
        "final_state": final_state,
        "estimated_clearance": float(candidate["estimated_clearance"]),
        "worst_clearance": round(float(worst_clearance), 8),
        "clearance_samples": [round(float(v), 8)
                              for v in clearance_samples],
        "collision_evidence": domain_errors,
        "solution_action_cost": solution_actions,
        "physical_action_prefix_states": physical_state_observations,
        "first_exact_full_pass_action_cost": first_full_action_cost,
        "all_lower_observed_prefixes_failed": (
            first_full_action_cost is None or all(
                not exact_full_pass({
                    "status": row["status"],
                    "passed_pct": row["passed_pct"],
                })
                for row in physical_state_observations
                if row["actions"] < first_full_action_cost)),
        "solution_api_calls": len(request_log),
        "solution_action_api_calls": len(action_requests),
        "solution_keyframes": int(solution_keyframes),
        "planner_estimated_cost": int(
            planner_evidence.get("planner_estimated_cost", 0)),
        "changed_parameter_count": int(
            candidate["changed_parameter_count"]),
        "response_frame_count": int(
            planner_evidence.get("planner_response_frames", 0)),
        "final_scene_fingerprint": _sha256_json(snapshot),
        "planner_evidence": planner_evidence,
        "unexpected_exception": unexpected_exception,
        "infrastructure_valid": bool(infrastructure_valid),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        **record_evidence,
    }
    return attempt


def _selection_key(attempt: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(attempt["solution_action_cost"]),
        int(attempt["solution_keyframes"]),
        int(attempt["changed_parameter_count"]),
        -float(attempt["worst_clearance"]),
        str(attempt["candidate_id"]),
    )


def _load_resumable_attempt(path: Path,
                            candidate: dict[str, Any]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        attempt = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if attempt.get("schema_version") != ATTEMPT_SCHEMA or \
            attempt.get("candidate_id") != candidate["candidate_id"]:
        return None
    for key in ("record_path", "metadata_path"):
        value = attempt.get(key)
        if value not in (None, "none") and not Path(value).is_file():
            return None
    return attempt


def _attempt_one(
        candidate: dict[str, Any],
        *,
        run_id: str,
        attempt_index: int,
        pair_dir: Path,
        record: bool,
        resume: bool,
) -> dict[str, Any]:
    attempts_dir = pair_dir / "attempts"
    path = attempts_dir / f"{attempt_index:04d}_{_safe(candidate['candidate_id'])}.json"
    if resume:
        loaded = _load_resumable_attempt(path, candidate)
        if loaded is not None:
            loaded["attempt_path"] = str(path.resolve())
            loaded["attempt_sha256"] = _sha256_file(path)
            return loaded
    attempt = execute_candidate(
        candidate,
        run_id=run_id,
        attempt_index=attempt_index,
        record_dir=pair_dir / "records",
        record=record,
    )
    _write_json(path, attempt)
    attempt["attempt_path"] = str(path.resolve())
    attempt["attempt_sha256"] = _sha256_file(path)
    return attempt


def _attempt_task_worker(task: tuple[dict[str, Any], str, int, Path, bool,
                                     bool]) -> dict[str, Any]:
    candidate, run_id, attempt_index, pair_dir, record, resume = task
    return _attempt_one(
        candidate,
        run_id=run_id,
        attempt_index=attempt_index,
        pair_dir=pair_dir,
        record=record,
        resume=resume,
    )


def _execute_group(
        candidates: Sequence[dict[str, Any]],
        attempts: list[dict[str, Any]],
        *,
        run_id: str,
        pair_dir: Path,
        record: bool,
        resume: bool,
        workers: int = 1,
) -> tuple[list[dict[str, Any]], bool]:
    group_attempts = []
    tasks = [
        (candidate, run_id, len(attempts) + offset, pair_dir, record, resume)
        for offset, candidate in enumerate(candidates, 1)
    ]
    if workers > 1 and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
            ordered_attempts = list(pool.map(_attempt_task_worker, tasks))
    else:
        ordered_attempts = [_attempt_task_worker(task) for task in tasks]
    for attempt in ordered_attempts:
        attempts.append(attempt)
        group_attempts.append(attempt)
        if not attempt["infrastructure_valid"]:
            return group_attempts, False
    return group_attempts, True


def execute_pair_universe(
        universe: dict[str, Any],
        *,
        evidence_root: Path,
        run_id: str,
        record: bool | None = None,
        resume: bool = True,
        candidate_workers: int = 1,
) -> dict[str, Any]:
    """Run the exact cost-dominance prefix and persist one pair proof."""
    started = time.perf_counter()
    pair_dir = evidence_root / _safe(run_id) / "pairs" / _safe(
        universe["pair_id"])
    pair_dir.mkdir(parents=True, exist_ok=True)
    universe_path = pair_dir / "universe.json"
    _write_json(universe_path, universe)
    record = (bool(universe["policy"].get("record_attempts", True))
              if record is None else bool(record))
    candidate_workers = int(candidate_workers)
    if candidate_workers < 1:
        raise UniverseError("candidate_workers must be at least one")
    candidates = list(universe["candidates"])
    by_stage = {
        stage: [row for row in candidates if row["stage"] == stage]
        for stage in STAGE_ORDER
    }
    attempts: list[dict[str, Any]] = []
    successful_group: list[dict[str, Any]] = []
    infrastructure_valid = True

    neutral_attempts, infrastructure_valid = _execute_group(
        by_stage["neutral"], attempts, run_id=run_id, pair_dir=pair_dir,
        record=record, resume=resume, workers=candidate_workers)
    if infrastructure_valid and any(a["full_pass"] for a in neutral_attempts):
        successful_group = neutral_attempts

    if infrastructure_valid and not successful_group:
        static = (by_stage["rotation"] + by_stage["shift"] +
                  by_stage["mixed"])
        static_attempts, infrastructure_valid = _execute_group(
            static, attempts, run_id=run_id, pair_dir=pair_dir,
            record=record, resume=resume, workers=candidate_workers)
        if infrastructure_valid and any(a["full_pass"] for a in static_attempts):
            successful_group = static_attempts

    if infrastructure_valid and not successful_group:
        dynamic = by_stage["multi_move"]
        for tier in sorted({int(row["measured_action_tier"])
                            for row in dynamic}):
            tier_candidates = [
                row for row in dynamic
                if int(row["measured_action_tier"]) == tier]
            tier_attempts, infrastructure_valid = _execute_group(
                tier_candidates, attempts, run_id=run_id,
                pair_dir=pair_dir, record=record, resume=resume,
                workers=candidate_workers)
            if not infrastructure_valid:
                break
            if any(a["full_pass"] for a in tier_attempts):
                successful_group = tier_attempts
                break

    if infrastructure_valid and not successful_group:
        final_attempts, infrastructure_valid = _execute_group(
            by_stage["screw_thread"], attempts, run_id=run_id,
            pair_dir=pair_dir, record=record, resume=resume,
            workers=candidate_workers)
        if infrastructure_valid and any(a["full_pass"] for a in final_attempts):
            successful_group = final_attempts

    full_candidates = [row for row in successful_group if row["full_pass"]]
    selected = min(full_candidates, key=_selection_key) if full_candidates else None
    attempted_ids = [row["candidate_id"] for row in attempts]
    unattempted = [row for row in candidates
                   if row["candidate_id"] not in set(attempted_ids)]
    if not infrastructure_valid:
        skipped_reason = "infrastructure_invalid"
        status = "infrastructure_invalid"
    elif selected is not None:
        skipped_reason = "skipped_due_to_cost_dominance"
        status = "passed"
    else:
        skipped_reason = "none"
        status = "declared_space_exhaustion"
    skipped = [
        {"candidate_id": row["candidate_id"], "reason": skipped_reason}
        for row in unattempted
    ]

    proof = {
        "schema_version": PAIR_PROOF_SCHEMA,
        "run_id": run_id,
        "pair_id": universe["pair_id"],
        "body": universe["body"],
        "hole": universe["hole"],
        "body_geometry_fingerprint": universe[
            "body_geometry_fingerprint"],
        "hole_geometry_fingerprint": universe[
            "hole_geometry_fingerprint"],
        "sut_source_fingerprint": universe["sut_source_fingerprint"],
        "universe_path": str(universe_path.resolve()),
        "universe_sha256": _sha256_file(universe_path),
        "universe_canonical_sha256": universe["canonical_sha256"],
        "complete_universe_cardinality": len(candidates),
        "executed_prefix": attempted_ids,
        "attempts": attempts,
        "skipped_candidates": skipped,
        "selected_candidate_id": (
            selected["candidate_id"] if selected else None),
        "first_successful_stage": selected["stage"] if selected else None,
        "first_successful_family": (
            selected["semantic_family"] if selected else None),
        "first_successful_measured_tier": (
            selected["solution_action_cost"] if selected else None),
        "status": status,
        "declared_space_exhaustion_reason": (
            "every candidate in the complete user-declared discrete universe "
            "returned valid negative physical evidence"
            if status == "declared_space_exhaustion" else None),
        "infrastructure_valid": bool(infrastructure_valid),
        "selection_key": list(_selection_key(selected)) if selected else None,
        "solution_action_cost": (
            int(selected["solution_action_cost"]) if selected else None),
        "solution_api_calls": (
            int(selected["solution_api_calls"]) if selected else None),
        "solution_keyframes": (
            int(selected["solution_keyframes"]) if selected else None),
        "planner_estimated_cost": (
            int(selected["planner_estimated_cost"]) if selected else None),
        "changed_parameter_count": (
            int(selected["changed_parameter_count"]) if selected else None),
        "search_action_cost": sum(
            max(0, int(row["solution_action_cost"])) for row in attempts),
        "search_api_calls": sum(
            int(row["solution_api_calls"]) for row in attempts),
        "search_attempt_count": len(attempts),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "proof_claim": universe["proof_scope"],
        "continuous_global_optimum_claimed": False,
        "mathematical_impossibility_claimed": False,
    }
    certificate = verify_pair_documents(
        universe, proof, attempts=attempts, check_files=record)
    proof["certificate"] = certificate
    proof_path = pair_dir / "proof.json"
    _write_json(proof_path, proof)
    proof["proof_path"] = str(proof_path.resolve())
    proof["proof_sha256"] = _sha256_file(proof_path)
    return proof


def _required_candidate_fields() -> set[str]:
    return {
        "schema_version", "candidate_id", "body", "hole",
        "body_geometry_fingerprint", "hole_geometry_fingerprint", "stage",
        "sut_source_fingerprint",
        "semantic_family", "measured_action_tier", "parent_candidate_id",
        "provenance_sources", "pose", "action_plan", "dynamic_options",
        "canonical_signature", "fit_rank", "estimated_clearance",
        "solution_action_cost", "user_declared_execution_scope",
    }


def _expected_execution_ids(
        candidates: list[dict[str, Any]],
        attempts_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    by_stage = {
        stage: [row for row in candidates if row["stage"] == stage]
        for stage in STAGE_ORDER
    }
    expected: list[str] = []
    success_group: list[str] = []

    neutral = by_stage["neutral"]
    expected.extend(row["candidate_id"] for row in neutral)
    if any(exact_full_pass(attempts_by_id[row["candidate_id"]]["final_state"])
           for row in neutral if row["candidate_id"] in attempts_by_id):
        return expected, [row["candidate_id"] for row in neutral]

    static = by_stage["rotation"] + by_stage["shift"] + by_stage["mixed"]
    expected.extend(row["candidate_id"] for row in static)
    if all(row["candidate_id"] in attempts_by_id for row in static) and any(
            exact_full_pass(attempts_by_id[row["candidate_id"]]["final_state"])
            for row in static):
        return expected, [row["candidate_id"] for row in static]

    dynamic = by_stage["multi_move"]
    for tier in sorted({int(row["measured_action_tier"]) for row in dynamic}):
        group = [row for row in dynamic
                 if int(row["measured_action_tier"]) == tier]
        expected.extend(row["candidate_id"] for row in group)
        if all(row["candidate_id"] in attempts_by_id for row in group) and any(
                exact_full_pass(attempts_by_id[row["candidate_id"]]["final_state"])
                for row in group):
            return expected, [row["candidate_id"] for row in group]

    final = by_stage["screw_thread"]
    expected.extend(row["candidate_id"] for row in final)
    if all(row["candidate_id"] in attempts_by_id for row in final) and any(
            exact_full_pass(attempts_by_id[row["candidate_id"]]["final_state"])
            for row in final):
        success_group = [row["candidate_id"] for row in final]
    return expected, success_group


def verify_pair_documents(
        universe: dict[str, Any],
        proof: dict[str, Any],
        *,
        attempts: Sequence[dict[str, Any]] | None = None,
        check_files: bool = True,
) -> dict[str, Any]:
    """Independent certificate reconstruction; no runner booleans are trusted."""
    errors: list[str] = []
    candidates = list(universe.get("candidates") or ())
    attempt_rows = list(attempts if attempts is not None
                        else proof.get("attempts") or ())
    candidate_ids = [row.get("candidate_id") for row in candidates]
    attempt_ids = [row.get("candidate_id") for row in attempt_rows]
    candidate_map = {row.get("candidate_id"): row for row in candidates}
    attempt_map = {row.get("candidate_id"): row for row in attempt_rows}

    canonical_payload = {
        key: value for key, value in universe.items()
        if key != "canonical_sha256"
    }
    if universe.get("canonical_sha256") != _sha256_json(canonical_payload):
        errors.append("universe canonical checksum mismatch")
    if universe.get("sut_source_fingerprint") != sut_source_fingerprint():
        errors.append("universe SUT source fingerprint differs from live code")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("duplicate candidate id in universe")
    if len(attempt_ids) != len(set(attempt_ids)):
        errors.append("duplicate candidate attempt")
    required = _required_candidate_fields()
    for row in candidates:
        missing = sorted(required - set(row))
        if missing:
            errors.append(
                f"candidate {row.get('candidate_id')} missing fields {missing}")
        if row.get("schema_version") != CANDIDATE_SCHEMA:
            errors.append(f"candidate {row.get('candidate_id')} schema mismatch")
        if row.get("stage") not in STAGE_ORDER:
            errors.append(f"candidate {row.get('candidate_id')} bad stage")
        if row.get("sut_source_fingerprint") != universe.get(
                "sut_source_fingerprint"):
            errors.append(
                f"candidate {row.get('candidate_id')} SUT fingerprint mismatch")
    if len(candidates) != int(universe.get(
            "normalized_unique_cardinality", -1)):
        errors.append("universe normalized cardinality mismatch")
    stage_counts = universe.get("stage_cardinalities") or {}
    for stage in STAGE_ORDER:
        actual = sum(row.get("stage") == stage for row in candidates)
        if int(stage_counts.get(stage, -1)) != actual:
            errors.append(f"stage cardinality mismatch for {stage}")

    neutral = [row for row in candidates if row.get("stage") == "neutral"]
    neutral_pose_exact = len(neutral) == 1 and all(
        abs(float(neutral[0]["pose"].get(key, 0.0))) <= SERIAL_TOL
        for key in POSE_KEYS)
    neutral_actions = ([item.get("action") for item in neutral[0]["action_plan"]]
                       if neutral else [])
    neutral_plan_exact = neutral_actions == ["assign", "drop"]
    if not neutral_pose_exact:
        errors.append("neutral pose is not exact zero")
    if not neutral_plan_exact or "set_pose" in neutral_actions:
        errors.append("neutral plan is not assign then drop only")

    for attempt in attempt_rows:
        cid = attempt.get("candidate_id")
        candidate = candidate_map.get(cid)
        if candidate is None:
            errors.append(f"attempt references unknown candidate {cid}")
            continue
        if attempt.get("sut_source_fingerprint") != candidate.get(
                "sut_source_fingerprint"):
            errors.append(f"attempt SUT fingerprint mismatch for {cid}")
        computed_full = exact_full_pass(attempt.get("final_state") or {})
        if bool(attempt.get("full_pass")) != computed_full or bool(
                attempt.get("independent_full_pass")) != computed_full:
            errors.append(f"false full-pass flag for {cid}")
        final_actions = int((attempt.get("final_state") or {}).get(
            "actions", -999))
        if int(attempt.get("solution_action_cost", -998)) != final_actions:
            errors.append(f"altered action cost for {cid}")
        prefix_states = list(attempt.get("physical_action_prefix_states") or ())
        computed_first_full = next((
            int(row["actions"]) for row in prefix_states
            if exact_full_pass(row)), None)
        if attempt.get("first_exact_full_pass_action_cost") != computed_first_full:
            errors.append(f"altered first-full prefix cost for {cid}")
        if computed_full and computed_first_full != final_actions:
            errors.append(f"hidden earlier success or missing final prefix for {cid}")
        if computed_first_full is not None and any(
                exact_full_pass(row) for row in prefix_states
                if int(row["actions"]) < computed_first_full):
            errors.append(f"hidden earlier full-pass prefix for {cid}")
        if not bool(attempt.get("infrastructure_valid")):
            errors.append(f"infrastructure-invalid attempt {cid}")
        if attempt.get("unexpected_exception") not in (None, "none"):
            errors.append(f"unexpected exception in attempt {cid}")
        if check_files:
            for path_key, sha_key in (
                    ("record_path", "record_sha256"),
                    ("metadata_path", "metadata_sha256")):
                raw_path = attempt.get(path_key)
                if not raw_path or raw_path == "none":
                    errors.append(f"missing {path_key} for {cid}")
                    continue
                path = Path(raw_path)
                if not path.is_file():
                    errors.append(f"missing evidence file {raw_path}")
                elif attempt.get(sha_key) != _sha256_file(path):
                    errors.append(f"checksum mismatch for {raw_path}")

    expected_ids, success_group_ids = _expected_execution_ids(
        candidates, attempt_map)
    infrastructure_prefix = all(
        bool(row.get("infrastructure_valid")) for row in attempt_rows)
    if infrastructure_prefix:
        if attempt_ids != expected_ids:
            errors.append("executed prefix is skipped, reordered, or has an extra attempt")
    else:
        if attempt_ids != expected_ids[:len(attempt_ids)]:
            errors.append("invalid execution is not an exact declared prefix")
    if proof.get("executed_prefix") != attempt_ids:
        errors.append("proof executed_prefix differs from attempts")

    skipped_ids = [row.get("candidate_id")
                   for row in proof.get("skipped_candidates") or ()]
    expected_skipped = candidate_ids[len(attempt_ids):]
    if skipped_ids != expected_skipped:
        errors.append("skipped candidate manifest is incomplete or reordered")
    if set(candidate_ids) != set(attempt_ids) | set(skipped_ids):
        errors.append("universe member omitted from executed/skipped partition")

    successful_attempts = [
        attempt_map[cid] for cid in success_group_ids
        if cid in attempt_map and exact_full_pass(attempt_map[cid]["final_state"])]
    independently_selected = (
        min(successful_attempts, key=_selection_key)
        if successful_attempts else None)
    selected_id = proof.get("selected_candidate_id")
    if selected_id != (independently_selected.get("candidate_id")
                       if independently_selected else None):
        errors.append("selected candidate is not independent argmin")
    if selected_id is not None and not exact_full_pass(
            (attempt_map.get(selected_id) or {}).get("final_state") or {}):
        errors.append("selected candidate is not an exact full pass")

    has_any_success = bool(successful_attempts)
    all_exhausted = len(attempt_ids) == len(candidate_ids) and not has_any_success
    if proof.get("status") == "declared_space_exhaustion" and not all_exhausted:
        errors.append("false declared-space-exhaustion claim")
    if all_exhausted and proof.get("status") != "declared_space_exhaustion":
        errors.append("missing declared-space-exhaustion status")

    certificate = {
        "schema_version": CERTIFICATE_SCHEMA,
        "verdict": not errors,
        "errors": errors,
        "direct_attempted_first": bool(attempt_ids and neutral and
                                       attempt_ids[0] == neutral[0]["candidate_id"]),
        "neutral_pose_was_exact": neutral_pose_exact and neutral_plan_exact,
        "earlier_success_absent": not any(
            exact_full_pass(row.get("final_state") or {})
            for row in attempt_rows[:max(0, len(attempt_rows) -
                                         len(success_group_ids))]),
        "retries_only_after_failure": bool(
            not attempt_rows[1:] or
            not exact_full_pass(attempt_rows[0].get("final_state") or {})),
        "candidate_ids_follow_declared_policy": (
            attempt_ids == expected_ids if infrastructure_prefix
            else attempt_ids == expected_ids[:len(attempt_ids)]),
        "all_lower_cost_tiers_exhausted": (
            attempt_ids == expected_ids if infrastructure_prefix else False),
        "first_successful_tier_fully_exhausted": (
            not success_group_ids or all(cid in attempt_map
                                         for cid in success_group_ids)),
        "selected_is_independent_argmin": selected_id == (
            independently_selected.get("candidate_id")
            if independently_selected else None),
        "selected_is_exact_full_pass": (
            selected_id is None or bool(
                attempt_map.get(selected_id) and exact_full_pass(
                    attempt_map[selected_id]["final_state"]))),
        "no_attempt_after_tier_completion": (
            attempt_ids == expected_ids if infrastructure_prefix else False),
        "higher_tiers_skipped_only_by_cost_dominance": (
            not expected_skipped or all(
                row.get("reason") == "skipped_due_to_cost_dominance"
                for row in proof.get("skipped_candidates") or ())),
        "exhausted_all_declared_stages": all_exhausted,
        "independent_selected_candidate_id": (
            independently_selected.get("candidate_id")
            if independently_selected else None),
        "executed_count": len(attempt_rows),
        "universe_count": len(candidates),
    }
    return certificate


def verify_pair_proof(proof_path: Path,
                      *, check_files: bool = True) -> dict[str, Any]:
    proof = json.loads(Path(proof_path).read_text(encoding="utf-8"))
    universe = json.loads(Path(proof["universe_path"]).read_text(
        encoding="utf-8"))
    return verify_pair_documents(
        universe, proof, attempts=proof.get("attempts"),
        check_files=check_files)


def _best_observation(proof: dict[str, Any]) -> dict[str, Any] | None:
    attempts = list(proof.get("attempts") or ())
    selected_id = proof.get("selected_candidate_id")
    if selected_id:
        return next((row for row in attempts
                     if row["candidate_id"] == selected_id), None)
    if not attempts:
        return None
    return max(attempts, key=lambda row: (
        float(row.get("passed_pct", -1.0)),
        -max(0, int(row.get("solution_action_cost", 10**9))),
        float(row.get("worst_clearance", -1e9)),
        row.get("candidate_id", ""),
    ))


def pair_matrix_row(universe: dict[str, Any],
                    proof: dict[str, Any]) -> dict[str, Any]:
    selected = _best_observation(proof)
    neutral = next((row for row in proof.get("attempts") or ()
                    if row.get("stage") == "neutral"), None)
    return {
        "body": proof["body"],
        "hole": proof["hole"],
        "body_geometry_fingerprint": proof[
            "body_geometry_fingerprint"],
        "hole_geometry_fingerprint": proof[
            "hole_geometry_fingerprint"],
        "sut_source_fingerprint": proof["sut_source_fingerprint"],
        "neutral_status": neutral.get("status") if neutral else None,
        "neutral_passed_pct": neutral.get("passed_pct") if neutral else None,
        "neutral_full_pass": bool(neutral and neutral.get("full_pass")),
        "first_successful_family": proof.get("first_successful_family"),
        "first_successful_stage": proof.get("first_successful_stage"),
        "minimum_solution_actions": proof.get("solution_action_cost"),
        "selected_candidate_id": proof.get("selected_candidate_id"),
        "selected_pose": (
            next((candidate["pose"] for candidate in universe["candidates"]
                  if candidate["candidate_id"] ==
                  proof.get("selected_candidate_id")), None)),
        "selected_trajectory": (
            selected.get("planner_evidence") if selected else None),
        "status": proof["status"],
        "passed_pct": selected.get("passed_pct") if selected else None,
        "worst_clearance": (
            selected.get("worst_clearance") if selected else None),
        "search_attempts": proof["search_attempt_count"],
        "search_actions": proof["search_action_cost"],
        "search_api_calls": proof["search_api_calls"],
        "search_runtime_seconds": proof["runtime_seconds"],
        "raw_candidate_count": universe["raw_candidate_cardinality"],
        "reduced_candidate_count": universe[
            "normalized_unique_cardinality"],
        "record_path": selected.get("record_path") if selected else None,
        "metadata_path": selected.get("metadata_path") if selected else None,
        "record_sha256": selected.get("record_sha256") if selected else None,
        "metadata_sha256": (
            selected.get("metadata_sha256") if selected else None),
        "proof_path": proof.get("proof_path"),
        "proof_sha256": proof.get("proof_sha256"),
        "certificate_verdict": bool(
            (proof.get("certificate") or {}).get("verdict")),
        "declared_space_exhaustion_reason": proof.get(
            "declared_space_exhaustion_reason"),
        "provenance_issues": len(
            (proof.get("certificate") or {}).get("errors") or ()),
    }


def _per_body_report(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    report = []
    for body in live_bodies():
        group = [row for row in rows if row["body"] == body]
        if not group:
            continue
        successful = [row for row in group if row["status"] == "passed"]
        best = min(successful, key=lambda row: (
            int(row["minimum_solution_actions"]),
            -float(row["worst_clearance"]),
            row["hole"],
        )) if successful else None
        report.append({
            "body": body,
            "pair_count": len(group),
            "neutral_holes": [row["hole"] for row in group
                              if row["first_successful_stage"] == "neutral"],
            "rotation_holes": [row["hole"] for row in group
                               if row["first_successful_stage"] == "rotation"],
            "shift_holes": [row["hole"] for row in group
                            if row["first_successful_stage"] == "shift"],
            "mixed_holes": [row["hole"] for row in group
                            if row["first_successful_stage"] == "mixed"],
            "dynamic_holes": [row["hole"] for row in group
                              if row["first_successful_stage"] in
                              {"multi_move", "screw_thread"}],
            "exhausted_pairs": [row["hole"] for row in group
                                if row["status"] ==
                                "declared_space_exhaustion"],
            "infrastructure_invalid_pairs": [
                row["hole"] for row in group
                if row["status"] == "infrastructure_invalid"],
            "best_hole": best["hole"] if best else None,
            "best_solution_actions": (
                best["minimum_solution_actions"] if best else None),
            "raw_candidate_count": sum(
                int(row["raw_candidate_count"]) for row in group),
            "reduced_candidate_count": sum(
                int(row["reduced_candidate_count"]) for row in group),
            "provenance_issues": sum(
                int(row["provenance_issues"]) for row in group),
        })
    return report


def _attempt_kv_line(run_id: str, attempt: dict[str, Any]) -> str:
    valid = bool(attempt.get("infrastructure_valid"))
    full = exact_full_pass(attempt.get("final_state") or {})
    sentinel = 1_000_000_000
    solution_actions = (int(attempt["solution_action_cost"])
                        if full else sentinel)
    solution_keyframes = (int(attempt["solution_keyframes"])
                          if full else sentinel)
    changed = (int(attempt["changed_parameter_count"])
               if full else sentinel)
    clearance = (float(attempt["worst_clearance"]) if full else -1e9)
    return (
        "app=sieve3d_staged_attempt "
        f"candidate_id={_safe(attempt['candidate_id'])} "
        f"run_id={_safe(run_id)} body={_safe(attempt['body'])} "
        f"hole={_safe(attempt['hole'])} stage={_safe(attempt['stage'])} "
        f"family={_safe(attempt['semantic_family'])} "
        f"full_pass={int(full)} passed_volume_pct="
        f"{float(attempt['passed_pct']):.6f} "
        f"solution_actions={solution_actions} "
        f"solution_keyframes={solution_keyframes} "
        f"changed_parameter_count={changed} "
        f"worst_clearance={clearance:.8f} "
        f"search_attempts=1 planner_estimated_cost="
        f"{int(attempt['planner_estimated_cost'])} "
        f"FW_VAR={0 if valid else 6}")


def pair_kv_line(proof: dict[str, Any]) -> str:
    selected = _best_observation(proof)
    full = proof.get("status") == "passed" and selected is not None and \
        exact_full_pass(selected.get("final_state") or {})
    sentinel = 1_000_000_000
    provenance_candidate = (proof.get("selected_candidate_id") or
                            f"{proof['pair_id']}--declared-exhaustion")
    source_ref = proof.get("proof_path") or proof.get("universe_path") or "none"
    return (
        "app=sieve3d_all_pairs_staged "
        "criteria_profile=sieve3d_staged_v2 "
        "criteria_metrics=full_pass:max,passed_volume_pct:max,"
        "solution_actions:min,solution_keyframes:min,"
        "changed_parameter_count:min,worst_clearance:max,search_attempts:min "
        f"candidate_id={_safe(provenance_candidate)} "
        f"run_id={_safe(proof['run_id'])} source_ref={_safe(source_ref)} "
        f"pair_id={_safe(proof['pair_id'])} body={_safe(proof['body'])} "
        f"hole={_safe(proof['hole'])} full_pass={int(full)} "
        f"passed_volume_pct={float(selected.get('passed_pct', 0.0) if selected else 0.0):.6f} "
        f"solution_actions={int(proof['solution_action_cost']) if full else sentinel} "
        f"solution_keyframes={int(proof['solution_keyframes']) if full else sentinel} "
        f"changed_parameter_count={int(proof['changed_parameter_count']) if full else sentinel} "
        f"worst_clearance={float(selected.get('worst_clearance', -1e9) if full else -1e9):.8f} "
        f"search_attempts={int(proof['search_attempt_count'])} "
        f"search_actions={int(proof['search_action_cost'])} "
        f"search_api_calls={int(proof['search_api_calls'])} "
        f"planner_estimated_cost={int(proof.get('planner_estimated_cost') or 0)} "
        f"certificate={int(bool((proof.get('certificate') or {}).get('verdict')))} "
        f"status={_safe(proof['status'])} "
        f"FW_VAR={0 if proof.get('infrastructure_valid') and (proof.get('certificate') or {}).get('verdict') else 6}")


def _write_matrix_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "body", "hole", "body_geometry_fingerprint",
        "hole_geometry_fingerprint", "sut_source_fingerprint", "neutral_status",
        "neutral_passed_pct", "neutral_full_pass",
        "first_successful_family", "first_successful_stage",
        "minimum_solution_actions", "selected_candidate_id", "status",
        "passed_pct", "worst_clearance", "search_attempts",
        "search_actions", "search_api_calls", "search_runtime_seconds",
        "raw_candidate_count", "reduced_candidate_count", "record_path",
        "metadata_path", "record_sha256", "metadata_sha256", "proof_path",
        "proof_sha256", "certificate_verdict",
        "declared_space_exhaustion_reason", "provenance_issues",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _persist_matrix_state(
        run_dir: Path,
        run_id: str,
        config: SearchConfig,
        requested_bodies: Sequence[str],
        requested_holes: Sequence[str],
        rows: Sequence[dict[str, Any]],
        resource_plan: dict[str, Any],
        started: float,
) -> dict[str, Any]:
    expected_pairs = {(body, hole) for body in requested_bodies
                      for hole in requested_holes}
    observed_pairs = {(row["body"], row["hole"]) for row in rows}
    all_live_scope = (tuple(requested_bodies) == live_bodies() and
                      tuple(requested_holes) == live_holes())
    payload = {
        "schema_version": MATRIX_SCHEMA,
        "run_id": run_id,
        "config": config.to_dict(),
        "config_digest": config.digest,
        "live_bodies": list(live_bodies()),
        "live_holes": list(live_holes()),
        "requested_bodies": list(requested_bodies),
        "requested_holes": list(requested_holes),
        "expected_pair_count": len(expected_pairs),
        "observed_pair_count": len(observed_pairs),
        "all_live_scope": all_live_scope,
        "every_requested_pair_exactly_once": (
            observed_pairs == expected_pairs and len(rows) == len(expected_pairs)),
        "rows": list(rows),
        "per_body": _per_body_report(rows),
        "resource_plan": resource_plan,
        "totals": {
            "passed_pairs": sum(row["status"] == "passed" for row in rows),
            "exhausted_pairs": sum(
                row["status"] == "declared_space_exhaustion" for row in rows),
            "infrastructure_invalid_pairs": sum(
                row["status"] == "infrastructure_invalid" for row in rows),
            "neutral_pairs": sum(
                row["first_successful_stage"] == "neutral" for row in rows),
            "rotation_pairs": sum(
                row["first_successful_stage"] == "rotation" for row in rows),
            "shift_pairs": sum(
                row["first_successful_stage"] == "shift" for row in rows),
            "mixed_pairs": sum(
                row["first_successful_stage"] == "mixed" for row in rows),
            "multi_move_pairs": sum(
                row["first_successful_stage"] == "multi_move" for row in rows),
            "screw_thread_pairs": sum(
                row["first_successful_stage"] == "screw_thread" for row in rows),
            "search_attempts": sum(int(row["search_attempts"]) for row in rows),
            "search_actions": sum(int(row["search_actions"]) for row in rows),
            "runtime_seconds": round(time.perf_counter() - started, 6),
        },
        "proof_scope": (
            "one independent discrete minimum/exhaustion certificate per fixed "
            "body/hole geometry; no easiest-hole substitution"),
        "continuous_global_optimum_claimed": False,
        "mathematical_impossibility_claimed": False,
    }
    _write_json(run_dir / "matrix.json", payload)
    _write_json(run_dir / "per_body.json", payload["per_body"])
    _write_matrix_csv(run_dir / "matrix.csv", rows)
    return payload


def _plan_pair_worker(task: tuple[str, str, SearchConfig, Path, bool]
                      ) -> tuple[str, str, str, dict[str, Any]]:
    """Construct and persist one deterministic universe in an isolated worker."""
    body, hole, config, path, resume = task
    if resume and path.is_file():
        universe = json.loads(path.read_text(encoding="utf-8"))
        generated_twice_equal = True
    else:
        universe, generated_twice_equal = generate_pair_universe_twice(
            body, hole, config)
        _write_json(path, universe)
    plan_row = {
        "body": body,
        "hole": hole,
        "universe_path": str(path.resolve()),
        "universe_sha256": _sha256_file(path),
        "generated_twice_canonical_json_equal": generated_twice_equal,
        "raw_candidate_count": universe["raw_candidate_cardinality"],
        "normalized_candidate_count": universe[
            "normalized_unique_cardinality"],
        "stage_cardinalities": universe["stage_cardinalities"],
        "resource_implications": universe["resource_implications"],
    }
    return body, hole, str(path), plan_row


def _execute_pair_worker(task: tuple[Path, Path, str, bool | None, bool, int]
                         ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute one fixed-pair universe; pair-specific paths avoid collisions."""
    universe_path, evidence_root, run_id, record, resume, candidate_workers = task
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    proof = execute_pair_universe(
        universe,
        evidence_root=evidence_root,
        run_id=run_id,
        record=record,
        resume=resume,
        candidate_workers=candidate_workers,
    )
    return proof, pair_matrix_row(universe, proof)


def run_matrix(
        *,
        evidence_root: Path,
        run_id: str,
        config: SearchConfig | None = None,
        bodies: Sequence[str] | None = None,
        holes: Sequence[str] | None = None,
        record: bool | None = None,
        resume: bool = True,
        universe_only: bool = False,
        workers: int = 1,
        pair_workers: int = 1,
) -> dict[str, Any]:
    """Plan exact resources first, then execute the requested fixed-pair matrix."""
    started = time.perf_counter()
    config = config or SearchConfig()
    config.validate()
    workers = int(workers)
    if workers < 1:
        raise UniverseError("workers must be at least one")
    pair_workers = int(pair_workers)
    if pair_workers < 1:
        raise UniverseError("pair_workers must be at least one")
    requested_bodies = tuple(bodies or live_bodies())
    requested_holes = tuple(holes or live_holes())
    unknown_bodies = sorted(set(requested_bodies) - set(live_bodies()))
    unknown_holes = sorted(set(requested_holes) - set(live_holes()))
    if unknown_bodies or unknown_holes:
        raise UniverseError(
            f"unknown matrix members: bodies={unknown_bodies}, holes={unknown_holes}")
    if len(requested_bodies) != len(set(requested_bodies)) or \
            len(requested_holes) != len(set(requested_holes)):
        raise UniverseError("matrix registries contain duplicates")

    run_dir = evidence_root / _safe(run_id)
    universe_store = run_dir / "planned_universes"
    universe_store.mkdir(parents=True, exist_ok=True)
    plan_rows = []
    universe_paths: dict[tuple[str, str], Path] = {}
    plan_tasks = []
    for body in requested_bodies:
        for hole in requested_holes:
            path = universe_store / f"{_safe(body)}--{_safe(hole)}.json"
            plan_tasks.append((body, hole, config, path, resume))
    if workers == 1:
        planned = map(_plan_pair_worker, plan_tasks)
        for body, hole, path_text, plan_row in planned:
            universe_paths[(body, hole)] = Path(path_text)
            plan_rows.append(plan_row)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for body, hole, path_text, plan_row in pool.map(
                    _plan_pair_worker, plan_tasks):
                universe_paths[(body, hole)] = Path(path_text)
                plan_rows.append(plan_row)
    resource_plan = {
        "schema_version": "sieve3d-pre-execution-resource-plan/2",
        "run_id": run_id,
        "pair_count": len(plan_rows),
        "raw_candidate_count": sum(
            int(row["raw_candidate_count"]) for row in plan_rows),
        "normalized_candidate_count": sum(
            int(row["normalized_candidate_count"]) for row in plan_rows),
        "maximum_record_files": sum(
            int(row["resource_implications"]["maximum_record_files"])
            for row in plan_rows),
        "hidden_candidate_cap": None,
        "downsampling": False,
        "covering_array_fallback": False,
        "worker_processes": workers,
        "candidate_workers_per_pair": pair_workers,
        "maximum_concurrent_attempts": workers * pair_workers,
        "pairs": plan_rows,
    }
    _write_json(run_dir / "pre_execution_resource_plan.json", resource_plan)
    if universe_only:
        return {
            "schema_version": MATRIX_SCHEMA,
            "run_id": run_id,
            "status": "planned_not_executed",
            "resource_plan": resource_plan,
        }

    rows: list[dict[str, Any]] = []
    proofs: list[dict[str, Any]] = []
    execute_tasks = [
        (universe_paths[(body, hole)], evidence_root, run_id, record, resume,
         pair_workers)
        for body in requested_bodies for hole in requested_holes
    ]

    def accept_result(result: tuple[dict[str, Any], dict[str, Any]]) -> None:
        proof, row = result
        proofs.append(proof)
        rows.append(row)
        _persist_matrix_state(
            run_dir, run_id, config, requested_bodies,
            requested_holes, rows, resource_plan, started)

    if workers == 1:
        for result in map(_execute_pair_worker, execute_tasks):
            accept_result(result)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(_execute_pair_worker, execute_tasks):
                accept_result(result)

    attempts_kv = run_dir / "attempts.kv"
    attempts_kv.write_text(
        "".join(_attempt_kv_line(run_id, attempt) + "\n"
                for proof in proofs for attempt in proof["attempts"]),
        encoding="utf-8",
    )
    pair_kv = run_dir / "pair_results.kv"
    pair_kv.write_text(
        "".join(pair_kv_line(proof) + "\n" for proof in proofs),
        encoding="utf-8",
    )
    matrix = _persist_matrix_state(
        run_dir, run_id, config, requested_bodies, requested_holes,
        rows, resource_plan, started)
    matrix["attempts_kv_path"] = str(attempts_kv.resolve())
    matrix["attempts_kv_sha256"] = _sha256_file(attempts_kv)
    matrix["pair_results_kv_path"] = str(pair_kv.resolve())
    matrix["pair_results_kv_sha256"] = _sha256_file(pair_kv)
    matrix["provenance_issues"] = sum(
        int(row["provenance_issues"]) for row in rows)
    _write_json(run_dir / "matrix.json", matrix)
    return matrix


def reset_bundle_context() -> None:
    global BUNDLE_CTX
    BUNDLE_CTX = BundleContext()


def select_body(name: str) -> None:
    if name not in cc.BODIES:
        raise KeyError(name)
    BUNDLE_CTX.body = name


def select_hole(name: str) -> None:
    if name not in cc.HOLES:
        raise KeyError(name)
    BUNDLE_CTX.hole = name


def select_policy(name: str) -> None:
    if name != "rigid_only":
        raise UniverseError("the main experiment permits only rigid_only")
    BUNDLE_CTX.policy = name


def select_modification(name: str) -> None:
    if name not in {"none", "scale"}:
        raise KeyError(name)
    BUNDLE_CTX.modification = name


def enable_family(name: str) -> None:
    if name not in STAGE_ORDER:
        raise KeyError(name)
    if name not in BUNDLE_CTX.enabled_families:
        BUNDLE_CTX.enabled_families.append(name)


def enable_move(name: str) -> None:
    if name not in POSE_KEYS + ("drop", "wiggle", "thread"):
        raise KeyError(name)
    if name not in BUNDLE_CTX.enabled_moves:
        BUNDLE_CTX.enabled_moves.append(name)


def run_configured_pair() -> dict[str, Any]:
    if BUNDLE_CTX.body is None or BUNDLE_CTX.hole is None:
        raise UniverseError("Bundle candidate did not select body and hole")
    enabled = tuple(BUNDLE_CTX.enabled_families or STAGE_ORDER)
    declared_moves = tuple(BUNDLE_CTX.enabled_moves)
    required_moves = POSE_KEYS + ("drop", "wiggle", "thread")
    if enabled != tuple(STAGE_ORDER):
        raise UniverseError(
            "Bundle candidate did not assemble all six staged families in "
            "their authored order")
    if declared_moves != required_moves:
        raise UniverseError(
            "Bundle candidate did not assemble all eight rigid moves in "
            "their authored order")
    config = SearchConfig(
        rigid_policy=BUNDLE_CTX.policy,
        modification=BUNDLE_CTX.modification,
        enabled_families=enabled,
    )
    evidence_root = Path(os.environ.get(
        "SIEVE3D_STAGED_EVIDENCE_ROOT",
        str(HERE / "all_pairs_evidence"),
    ))
    run_id = os.environ.get(
        "SIEVE3D_SEARCH_RUN_ID", "bundle-staged-all-pairs-v2")
    try:
        planned_path = (
            evidence_root / _safe(run_id) / "planned_universes" /
            f"{_safe(BUNDLE_CTX.body)}--{_safe(BUNDLE_CTX.hole)}.json")
        if planned_path.is_file():
            universe = json.loads(planned_path.read_text(encoding="utf-8"))
            if universe.get("policy_digest") != config.digest:
                raise EvidenceError(
                    "preplanned universe config digest differs from Bundle "
                    f"candidate: {planned_path}")
        else:
            universe, _equal = generate_pair_universe_twice(
                BUNDLE_CTX.body, BUNDLE_CTX.hole, config)
        BUNDLE_CTX.result = execute_pair_universe(
            universe,
            evidence_root=evidence_root,
            run_id=run_id,
            record=True,
            resume=True,
        )
        BUNDLE_CTX.last_error = "none"
    except Exception as exc:  # candidate emits an infrastructure verdict
        BUNDLE_CTX.result = None
        BUNDLE_CTX.last_error = f"{type(exc).__name__}:{_safe(str(exc))}"
    return BUNDLE_CTX.result or {"error": BUNDLE_CTX.last_error}


def bundle_fw_var() -> int:
    result = BUNDLE_CTX.result
    if not result:
        return 6
    if not result.get("infrastructure_valid"):
        return 6
    if not (result.get("certificate") or {}).get("verdict"):
        return 6
    return 0


def bundle_kv_line() -> str:
    if not BUNDLE_CTX.result:
        return (
            "app=sieve3d_all_pairs_staged full_pass=0 "
            "passed_volume_pct=0 solution_actions=1000000000 "
            "solution_keyframes=1000000000 changed_parameter_count=1000000000 "
            "worst_clearance=-1000000000 search_attempts=0 "
            f"error={_safe(BUNDLE_CTX.last_error)} FW_VAR=6")
    return pair_kv_line(BUNDLE_CTX.result)


def _cli_config(args: argparse.Namespace) -> SearchConfig:
    return SearchConfig(record_attempts=not args.no_record)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="deterministic neutral-first staged passage proof")
    parser.add_argument("--body", action="append", choices=live_bodies())
    parser.add_argument("--hole", action="append", choices=live_holes())
    parser.add_argument("--all", action="store_true",
                        help="explicitly select every live body and hole")
    parser.add_argument("--run-id", default=time.strftime(
        "staged-%Y%m%dT%H%M%S"))
    parser.add_argument("--evidence-root", type=Path,
                        default=HERE / "all_pairs_evidence")
    parser.add_argument("--universe-only", action="store_true")
    parser.add_argument("--no-record", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1,
                        help="bounded concurrent fixed-pair workers (default: 1)")
    parser.add_argument(
        "--pair-workers", type=int, default=1,
        help="bounded fresh-process candidates inside one active tier (default: 1)")
    parser.add_argument("--verify", type=Path,
                        help="verify one existing pair proof and exit")
    args = parser.parse_args(argv)
    if args.verify:
        certificate = verify_pair_proof(args.verify, check_files=True)
        print(json.dumps(certificate, sort_keys=True, indent=2))
        return 0 if certificate["verdict"] else 6
    bodies = live_bodies() if args.all or not args.body else tuple(args.body)
    holes = live_holes() if args.all or not args.hole else tuple(args.hole)
    result = run_matrix(
        evidence_root=args.evidence_root,
        run_id=args.run_id,
        config=_cli_config(args),
        bodies=bodies,
        holes=holes,
        record=not args.no_record,
        resume=not args.no_resume,
        universe_only=args.universe_only,
        workers=args.workers,
        pair_workers=args.pair_workers,
    )
    print(json.dumps({
        "run_id": result["run_id"],
        "status": result.get("status", "complete"),
        "expected_pair_count": result.get("expected_pair_count"),
        "observed_pair_count": result.get("observed_pair_count"),
        "totals": result.get("totals"),
        "resource_plan": {
            key: result["resource_plan"].get(key)
            for key in ("pair_count", "raw_candidate_count",
                        "normalized_candidate_count", "maximum_record_files")
        },
        "matrix_path": str(
            (args.evidence_root / _safe(args.run_id) / "matrix.json").resolve()),
    }, sort_keys=True, indent=2))
    failures = int((result.get("totals") or {}).get(
        "infrastructure_invalid_pairs", 0))
    return 0 if failures == 0 else 6


if __name__ == "__main__":
    raise SystemExit(main())
