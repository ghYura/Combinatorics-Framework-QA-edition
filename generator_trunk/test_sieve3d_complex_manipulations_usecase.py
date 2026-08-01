#!/usr/bin/env python3
"""
Complex-surface 3D bodies vs the 2D sieve — deep manipulation suite.

A deliberately harder companion to test_sieve3d_external_api_usecase:
instead of six fixed extrusions with known poses it builds a zoo of
formula-surface / bent / twisted / boolean-carved solids, checks the
physical invariants the geometry engine promises, and runs long
multi-action stuffing campaigns (direct drop -> stepwise descent with
lateral jiggling -> wiggle ladders -> full iterative threading),
asserting geometric truths at every step — not just exit codes.

Run:  python3 test_sieve3d_complex_manipulations_usecase.py
Env:  SIEVE3D_ROOT, SIEVE3D_REC_OUT_DIR (Automation bundle conventions)
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "combinatorial_tests" / "sieve3d_complex_bodies"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(CASES_DIR))

from sut_paths import project_path  # noqa: E402

EXTERNAL_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT", str(project_path("sieve3d"))))

if EXTERNAL_ROOT.exists():
    import numpy as np
    import complex_cases as cc
    from sieve3d import api_v1
    from sieve3d.bodies import build_body
    from sieve3d.geometry import rot_zxz


@unittest.skipUnless(EXTERNAL_ROOT.exists(),
                     "external sieve3d project is not present")
class TestZooBuilds(unittest.TestCase):
    """Every complex recipe must compile into positive-volume geometry."""

    def test_all_bodies_and_holes_build(self):
        for name, spec in cc.BODIES.items():
            body = build_body(spec)
            v = body.volume(0.6)
            self.assertGreater(v, 1.0, f"{name}: empty body")
            self.assertGreater(len(body.slabs(0.6)), 0, name)
        from sieve3d import profiles
        for name, spec in cc.HOLES.items():
            poly = profiles.build(spec, quality=0.6)
            self.assertGreater(poly.area, 1.0, f"{name}: empty hole")

    def test_complex_bodies_have_three_distinct_views(self):
        for name in ("wave_bar", "twisted_flower", "plug", "croissant"):
            pr = build_body(cc.BODIES[name]).projections(0.6)
            areas = sorted(p.area for p in pr.values())
            self.assertGreater(areas[0], 1.0, name)
            # at least two of the three simultaneous views must differ
            self.assertGreater(areas[2] - areas[0],
                               0.05 * areas[2],
                               f"{name}: projections suspiciously identical")

    def test_wave_bar_side_view_is_actually_wavy(self):
        side = build_body(cc.BODIES["wave_bar"]).projections(0.8)["side"]
        minx, miny, maxx, maxy = side.bounds
        bbox = (maxx - minx) * (maxy - miny)
        self.assertGreater(bbox - side.area, 8.0,
                           "sinusoid surface lost its waves")


@unittest.skipUnless(EXTERNAL_ROOT.exists(),
                     "external sieve3d project is not present")
class TestPhysicalInvariants(unittest.TestCase):
    """The physics contracts complex manipulations rely on."""

    def test_plasticine_chains_conserve_volume_exactly(self):
        for name in ("hook120", "snake", "helix_bar", "croissant"):
            spec = dict(cc.BODIES[name])
            base = dict(spec, mods=[])
            v0 = build_body(base).volume(1.0)
            v1 = build_body(spec).volume(1.0)
            self.assertAlmostEqual(v1, v0, delta=v0 * 1e-9,
                                   msg=f"{name}: bend/twist changed mass")
        # stretching the S-snake keeps mass too
        stretched = dict(cc.BODIES["snake"])
        stretched["mods"] = list(stretched["mods"]) + [
            {"op": "stretch", "k": 1.5}]
        v0 = build_body(dict(cc.BODIES["snake"], mods=[])).volume(1.0)
        self.assertAlmostEqual(build_body(stretched).volume(1.0), v0,
                               delta=v0 * 1e-9)

    def test_boolean_carving_removes_the_right_amount(self):
        import math
        full = build_body(dict(cc.BODIES["pierced_cube"], mods=[]))
        cut = build_body(cc.BODIES["pierced_cube"])
        removed = full.volume(1.0) - cut.volume(1.0)
        self.assertAlmostEqual(removed, math.pi * 9 * 12,
                               delta=math.pi * 9 * 12 * 0.02)
        # and the bore shows in the top view as an interior ring
        top = cut.projections(0.8)["top"]
        self.assertEqual(len(top.interiors), 1)

    def test_sections_never_escape_the_shadow(self):
        for name in ("wave_bar", "twisted_flower", "snake", "pierced_cube"):
            body = build_body(cc.BODIES[name])
            for angles in ((20, 35, 10), (80, 60, 200)):
                R = rot_zxz(*angles)
                sh = body.shadow(R, 0.7).buffer(1e-4)
                ze = body.z_extent(R, 0.7)
                for z in np.linspace(-ze * 0.9, ze * 0.9, 7):
                    for sec in body.section_polys(R, float(z), 0, 0, 0.7):
                        self.assertTrue(
                            sh.contains(sec),
                            f"{name} R={angles}: section escapes at z={z:.1f}")

    def test_passed_fraction_is_monotone_during_descent(self):
        for name in ("wave_bar", "snake", "plug"):
            body = build_body(cc.BODIES[name])
            R = np.eye(3)
            ze = body.z_extent(R, 1.0)
            fracs = [body.passed_fraction(R, 0, 0, float(z), 1.0)
                     for z in np.linspace(ze + 1, -ze - 1, 12)]
            self.assertAlmostEqual(fracs[0], 0.0, delta=1e-9, msg=name)
            self.assertAlmostEqual(fracs[-1], 1.0, delta=1e-9, msg=name)
            for a, b in zip(fracs, fracs[1:]):
                self.assertGreaterEqual(b, a - 1e-9,
                                        f"{name}: passed% went backwards")

    def test_unassigned_body_lands_on_the_plate(self):
        h = cc.make_scene(["wave_bar"], ["round_generous"])
        out = h.act("wave_bar", "drop", max_dz=300)
        st = out["state"]
        body = build_body(cc.BODIES["wave_bar"])
        self.assertAlmostEqual(st["z"], body.z_extent(np.eye(3), 0.7),
                               delta=0.6,
                               msg="no hole assigned: gravity must stop "
                                   "the body exactly on the plate")
        with self.assertRaises(api_v1.ApiError):
            h.act("wave_bar", "set_z", z=-5.0)


@unittest.skipUnless(EXTERNAL_ROOT.exists(),
                     "external sieve3d project is not present")
class TestSymmetriesAndPredicates(unittest.TestCase):
    """Equivalence classes of poses + predicate/simulation agreement."""

    def test_square_silhouette_four_fold_symmetry(self):
        h = cc.make_scene(["pierced_cube"], ["square_snug"])
        clrs = [h.fits("pierced_cube", "square_snug",
                       {"spin": s})["clearance"] for s in (0, 90, 180, 270)]
        for c in clrs[1:]:
            self.assertAlmostEqual(c, clrs[0], delta=2e-3)
        diag = h.fits("pierced_cube", "square_snug", {"spin": 45})
        self.assertLess(diag["clearance"], clrs[0] - 0.5,
                        "45-degree spin must be much worse than aligned")

    def test_flower_three_fold_symmetry_and_antiphase(self):
        h = cc.make_scene(["flower"], ["flower_hole"])
        aligned = [h.fits("flower", "flower_hole", {"spin": s})["clearance"]
                   for s in (0, 120, 240)]
        for c in aligned[1:]:
            self.assertAlmostEqual(c, aligned[0], delta=5e-3)
        self.assertGreater(aligned[0], 0.2)
        anti = h.fits("flower", "flower_hole", {"spin": 60})["clearance"]
        self.assertLess(anti, 0.0,
                        "lobes-into-notches must collide in antiphase")

    def test_mirror_bend_gives_mirror_silhouettes(self):
        a = dict(cc.BODIES["hook120"])
        b = dict(a, mods=[{"op": "bend", "angle": 120, "plane": 180}])
        pa = build_body(a).projections(0.7)
        pb = build_body(b).projections(0.7)
        for view in ("top", "front", "side"):
            self.assertAlmostEqual(pa[view].area, pb[view].area,
                                   delta=pa[view].area * 1e-3,
                                   msg=f"mirror bend broke {view} view")

    def test_fit_predicate_agrees_with_the_experiment(self):
        """L0 promise vs L3 reality: a certain positive fit must drop
        through; a deep deficit must jam."""
        h = cc.make_scene(["flower", "pierced_cube", "plug"],
                          ["flower_hole", "square_snug", "round_generous"])
        for body in ("flower", "pierced_cube", "plug"):
            for hole in ("flower_hole", "square_snug", "round_generous"):
                pose = cc.anchored_pose(h, body, hole)
                fit = h.fits(body, hole, pose)
                if fit["clearance"] is None:
                    continue
                if fit["feasible"] and fit["clearance"] > 0.15:
                    st = cc.strat_direct(h, body, hole, pose)
                    self.assertEqual(
                        st["status"], "passed",
                        f"{body}->{hole}: predicate said clearance "
                        f"{fit['clearance']} but the drop jammed")
                    h.act(body, "reset")
                elif fit["clearance"] < -0.5:
                    h.act(body, "assign", hole=hole)
                    h.act(body, "set_pose", **pose)
                    st = h.act(body, "drop", max_dz=300)["state"]
                    self.assertNotEqual(
                        st["status"], "passed",
                        f"{body}->{hole}: deficit {fit['clearance']} yet "
                        f"the body fell through?!")
                    h.act(body, "reset")


@unittest.skipUnless(EXTERNAL_ROOT.exists(),
                     "external sieve3d project is not present")
class TestManipulationSafety(unittest.TestCase):
    """Ordering, mid-hole rotation, re-manufacture inside the hole,
    parallel stuffing — the 'many actions' contracts."""

    def test_action_order_violations(self):
        h = cc.make_scene(["flower"], ["flower_hole"])
        with self.assertRaises(api_v1.ApiError) as cm:
            h.act("flower", "assign", hole="no_such_hole")
        self.assertEqual(cm.exception.code, "not_found")
        with self.assertRaises(api_v1.ApiError) as cm:
            h.act("flower", "warp")
        self.assertEqual(cm.exception.code, "bad_request")
        with self.assertRaises(api_v1.ApiError):
            h.act("flower", "wiggle")          # wiggle needs a hole

    def test_rotation_inside_a_snug_hole(self):
        h = cc.make_scene(["pierced_cube"], ["square_snug"])
        h.act("pierced_cube", "assign", hole="square_snug")
        h.act("pierced_cube", "set_pose", spin=0, tilt=0, turn=0)
        h.act("pierced_cube", "set_z", z=0.0)      # halfway through
        st0 = h.exp()["bodies"]["pierced_cube"]
        self.assertEqual(st0["status"], "crossing")
        # a violent quarter-turn must be caught mid-path...
        with self.assertRaises(api_v1.ApiError) as cm:
            h.act("pierced_cube", "nudge", dturn=45)
        self.assertIn("blocked_at", str(cm.exception.hint or ""))
        st1 = h.exp()["bodies"]["pierced_cube"]
        self.assertEqual(st1["pose"], st0["pose"],
                         "rejected rotation must leave the pose intact")
        self.assertEqual(st1["attempts"], st0["attempts"] + 1)
        # ...while a gentle 2-degree turn inside the clearance is fine
        st2 = h.act("pierced_cube", "nudge", dturn=2)["state"]
        self.assertEqual(st2["status"], "crossing")
        st3 = h.act("pierced_cube", "drop", max_dz=300)["state"]
        self.assertEqual(st3["status"], "passed")

    def test_remanufacture_while_inside_the_hole(self):
        """Inflate the piston while it sits in the bore: physical mode
        refuses, geometric mode re-makes the part and the experiment
        immediately notices the new conflict."""
        h = cc.make_scene([], [])
        h.scene.add_body("piston", profile="circle", r=5.8, length=18,
                         mode="physical")
        h.scene.add_hole("bore", profile="circle", r=6.0, at=(0, 0))
        h.after_scene_mutation("replaced")
        h.act("piston", "assign", hole="bore")
        h.act("piston", "set_z", z=0.0)
        self.assertEqual(h.exp()["bodies"]["piston"]["status"], "crossing")

        with self.assertRaises(api_v1.ApiError) as cm:
            h.call("POST", "/api/v1/body/modify", api_v1.h_body_modify,
                   {"name": "piston", "op": "inflate",
                    "params": {"delta": 0.4}})
        self.assertEqual(cm.exception.code, "mode_violation")
        self.assertEqual(h.exp()["bodies"]["piston"]["status"], "crossing")

        h.call("POST", "/api/v1/body/mode", api_v1.h_body_mode,
               {"name": "piston", "mode": "geometric"})
        h.call("POST", "/api/v1/body/modify", api_v1.h_body_modify,
               {"name": "piston", "op": "inflate", "params": {"delta": 0.4}})
        self.assertEqual(h.exp()["bodies"]["piston"]["status"], "conflict",
                         "a fattened piston stuck in the bore must be "
                         "flagged, not silently tolerated")
        h.call("POST", "/api/v1/body/modify", api_v1.h_body_modify,
               {"name": "piston", "op": "inflate", "params": {"delta": -0.4}})
        self.assertEqual(h.exp()["bodies"]["piston"]["status"], "crossing",
                         "slimming it back must clear the conflict")

    def test_parallel_batch_double_stuffing(self):
        h = cc.make_scene(["wave_bar", "flower"],
                          ["wave_slot", "flower_hole"])
        pose_w = {"spin": 270, "tilt": 90, "turn": 90, "dy": -0.2}
        pose_f = cc.anchored_pose(h, "flower", "flower_hole")
        res = h.call("POST", "/api/v1/experiment/action",
                     api_v1.h_exp_action, {"batch": [
            {"body": "wave_bar", "action": "assign",
             "params": {"hole": "wave_slot"}},
            {"body": "flower", "action": "assign",
             "params": {"hole": "flower_hole"}},
            {"body": "wave_bar", "action": "set_pose", "params": pose_w},
            {"body": "flower", "action": "set_pose", "params": pose_f},
            {"body": "wave_bar", "action": "drop",
             "params": {"max_dz": 300}},
            {"body": "flower", "action": "drop",
             "params": {"max_dz": 300}},
        ]})
        self.assertEqual(len(res["results"]), 6)
        for r in res["results"]:
            self.assertNotIn("error", r, r)
        snap = h.exp()
        self.assertEqual(snap["totals"]["bodies_passed"], 2)
        self.assertEqual(snap["totals"]["total_actions"], 4)  # assigns free
        flux = snap["totals"]["per_hole_flux_mm3"]
        for body, hole in (("wave_bar", "wave_slot"),
                           ("flower", "flower_hole")):
            vol = build_body(cc.BODIES[body]).volume(1.0)
            self.assertAlmostEqual(flux[hole], vol, delta=vol * 0.01,
                                   msg=f"{hole}: flux must equal the full "
                                       f"volume of {body}")


@unittest.skipUnless(EXTERNAL_ROOT.exists(),
                     "external sieve3d project is not present")
class TestCampaignMatrix(unittest.TestCase):
    """The full matrix of stuffing campaigns with strategy escalation."""

    def _escalate(self, h, camp):
        body, hole = camp["body"], camp["hole"]
        pose = camp["pose"]
        if pose == "anchor":
            pose = cc.anchored_pose(h, body, hole)
        metrics = {"strategy": "direct"}
        try:
            st = cc.strat_direct(h, body, hole, pose)
        except api_v1.ApiError:
            st = h.exp()["bodies"][body]
        direct_passed = st["status"] == "passed"
        if camp["expect"] in ("maneuver", "maneuver_partial"):
            self.assertFalse(
                direct_passed,
                f"{camp['body']}->{camp['hole']}: was expected to jam on a "
                f"straight drop, but slid through — the case is too easy")
        direct_pct = st["passed_pct"]
        metrics["direct_pct"] = direct_pct
        if not direct_passed and camp["expect"] != "impossible":
            metrics["strategy"] = "wiggle"
            st = cc.strat_wiggle_ladder(
                h, body, hole, pose,
                rounds=camp.get("wiggle_rounds", 40),
                dz=camp.get("wiggle_dz", 1.2))
        if st["status"] != "passed" and camp["expect"] == "maneuver":
            metrics["strategy"] = "thread"
            res = cc.strat_thread(h, body, hole, pose)
            if res["success"]:
                st = dict(st)
                st["passed_pct"] = 100.0
                st["status"] = "passed"
        metrics.update(passed_pct=st["passed_pct"], status=st["status"],
                       actions=h.exp()["bodies"][body]["actions"],
                       attempts=h.exp()["bodies"][body]["attempts"],
                       effort=h.exp()["bodies"][body]["effort"])
        return metrics

    def test_campaign_matrix(self):
        for camp in cc.CAMPAIGNS:
            with self.subTest(body=camp["body"], hole=camp["hole"]):
                h = cc.make_scene([camp["body"]], [camp["hole"]])
                if camp["expect"] == "impossible":
                    self._assert_impossible(h, camp)
                    continue
                m = self._escalate(h, camp)
                m["verdict"] = m["status"]
                print(cc.campaign_summary_line(
                    f"{camp['body']}__{camp['hole']}", m))
                self.assertGreaterEqual(
                    m["passed_pct"], camp["min_pct"],
                    f"{camp['body']}->{camp['hole']} [{camp['note']}]: "
                    f"best strategy '{m['strategy']}' reached only "
                    f"{m['passed_pct']}%")
                if camp["expect"] == "maneuver_partial":
                    self.assertGreaterEqual(
                        m["passed_pct"], m.get("direct_pct", 0.0) + 25.0,
                        f"{camp['body']}: maneuvers won no real depth over "
                        f"the straight drop")
                if camp["expect"] == "direct":
                    self.assertEqual(m["strategy"], "direct",
                                     f"{camp['body']}: should not have "
                                     f"needed an escalation")

    def _assert_impossible(self, h, camp):
        body, hole = camp["body"], camp["hole"]
        worst = -1e9
        for spin, tilt in ((0, 0), (0, 90), (90, 90), (45, 55)):
            a = h.call("POST", "/api/v1/anchor", api_v1.h_anchor,
                       {"body": body, "hole": hole,
                        "spin": spin, "tilt": tilt})
            worst = max(worst, a["clearance"])
        self.assertLess(worst, -0.3,
                        f"{body}->{hole} should be hopeless, best anchored "
                        f"clearance {worst}")
        pose = cc.anchored_pose(h, body, hole)
        try:
            st = cc.strat_direct(h, body, hole, pose)
        except api_v1.ApiError:
            st = h.exp()["bodies"][body]
        self.assertNotEqual(st["status"], "passed")
        self.assertLess(st["passed_pct"], 10.0)
        z0 = h.exp()["bodies"][body]["z"]
        for _ in range(10):
            h.act(body, "wiggle", dz=1.0, evals=40)
        st = h.exp()["bodies"][body]
        self.assertNotEqual(st["status"], "passed")
        self.assertLess(z0 - st["z"], 2.5,
                        f"{body} kept sinking into an impossible hole")
        m = {"strategy": "none", "verdict": "blocked",
             "passed_pct": st["passed_pct"], "actions": st["actions"],
             "attempts": st["attempts"], "effort": st["effort"]}
        print(cc.campaign_summary_line(f"{body}__{hole}", m))

    def test_hook_threading_campaign_is_recorded(self):
        """The hardest case, wrapped in the recording contract."""
        h = cc.make_scene(["hook120"], ["round_small"])
        h.call("POST", "/api/v1/record", api_v1.h_record, {"cmd": "action"})
        pose = {"spin": 90, "tilt": 20, "turn": -90}
        h.act("hook120", "assign", hole="round_small")
        h.act("hook120", "set_pose", **pose)
        try:
            h.act("hook120", "drop", max_dz=300)
        except api_v1.ApiError:
            pass
        st = h.exp()["bodies"]["hook120"]
        self.assertNotEqual(st["status"], "passed",
                            "the needle-eye must resist a plain drop")
        res = cc.strat_thread(h, "hook120", "round_small", pose, frames=30)
        self.assertTrue(res["success"], "threading the hook must succeed")
        self.assertTrue(all(f["ok"] for f in res["frames"]),
                        "threading trajectory must be collision-free")
        rec_path, steps = cc.save_rec_artifact(h, "hook120_round_small")
        self.assertGreaterEqual(steps, 4)
        self.assertTrue(Path(rec_path).is_file())
        print(cc.campaign_summary_line("hook120__round_small_threaded", {
            "passed_pct": 100.0, "actions": st["actions"] + 1,
            "attempts": st["attempts"] + 1,
            "effort": float(res.get("keyframes", 0)),
            "strategy": "thread", "record_steps": steps,
            "verdict": "passed"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
