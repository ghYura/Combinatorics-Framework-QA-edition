#!/usr/bin/env python3
"""Focused regressions for non-max-passage combinatorial spec contracts."""

from __future__ import annotations

import contextlib
import inspect
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
GENERATOR_ROOT = HERE.parent
PRINCIPLES_ROOT = (
    HERE / "sieve3d_complex_bodies" / "combinatorial_principles"
)
sys.path.insert(0, str(GENERATOR_ROOT))
sys.path.insert(0, str(PRINCIPLES_ROOT))

import fwgen as fg  # noqa: E402
from sut_paths import project_path  # noqa: E402

LADDER = (
    HERE / "sieve3d_external_api" / "api_ladder" /
    "sieve3d_api_ladder.toml"
)
DEEP_THREAD = (
    HERE / "sieve3d_external_api" / "deep_thread" /
    "sieve3d_api_deep_thread.toml"
)
SIEVE3D_ROOT = Path(os.environ.get(
    "SIEVE3D_ROOT",
    str(project_path("sieve3d")),
))

laws = None
if SIEVE3D_ROOT.exists():
    import metamorphic_laws as laws  # noqa: E402


def _slot(spec: fg.Spec, sheet: str):
    for slot in spec.slots:
        if slot.sheet == sheet:
            return slot
    raise AssertionError("missing slot " + sheet)


@contextlib.contextmanager
def _candidate_environment(rec_root: str):
    old = {
        key: os.environ.get(key)
        for key in ("SIEVE3D_ROOT", "SIEVE3D_REC_OUT_DIR")
    }
    os.environ["SIEVE3D_ROOT"] = str(SIEVE3D_ROOT)
    os.environ["SIEVE3D_REC_OUT_DIR"] = rec_root
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@unittest.skipUnless(SIEVE3D_ROOT.exists(), "external sieve3d project is absent")
class TestExternalApiSpecContracts(unittest.TestCase):
    def test_ladder_action_permutation_orders_cases_on_non_experiment_routes(self):
        spec = fg.load_spec(LADDER, strict=True)
        cases = _slot(spec, "CASE").values
        actions = _slot(spec, "ACTION").values
        routes = _slot(spec, "ROUTE").values
        prefix = (
            _slot(spec, "HEAD").values[0] +
            cases[0] + cases[4] +
            actions[1] + actions[0] +
            routes[0]
        )
        ns: dict = {}
        with tempfile.TemporaryDirectory(prefix="sieve3d-case-order-") as out:
            with _candidate_environment(out):
                exec(compile(prefix, "<ladder-order>", "exec"), ns)
                self.assertEqual(ns["SELECTED_CASES"], [
                    "cylinder_round", "tri_prism_triangle",
                ])
                self.assertEqual(ns["CASE_EXECUTION_ORDER"], [
                    "tri_prism_triangle", "cylinder_round",
                ])
                self.assertEqual(set(ns["CASE_RESULTS"]), {
                    "cylinder_round", "tri_prism_triangle",
                })
                ns["_call"](
                    "POST", "/api/v1/record", ns["api_v1"].h_record,
                    ns["_state"], {"cmd": "cut"},
                )

    def test_ladder_fails_when_one_selected_case_misses_its_own_threshold(self):
        spec = fg.load_spec(LADDER, strict=True)
        cases = _slot(spec, "CASE").values
        actions = _slot(spec, "ACTION").values
        routes = _slot(spec, "ROUTE").values
        prefix = (
            _slot(spec, "HEAD").values[0] +
            cases[0] + cases[4] +
            actions[0] + actions[1] +
            routes[3]
        )
        ns: dict = {}
        with tempfile.TemporaryDirectory(prefix="sieve3d-case-oracle-") as out:
            with _candidate_environment(out):
                exec(compile(prefix, "<ladder-prefix>", "exec"), ns)
                target = ns["CASE_RESULTS"]["tri_prism_triangle"]
                other = ns["CASE_RESULTS"]["cylinder_round"]
                self.assertEqual(target["min_passed"], 90.0)
                self.assertEqual(other["min_passed"], 95.0)

                target["passed_volume_pct"] = target["min_passed"] - 0.01
                other["passed_volume_pct"] = 100.0
                ns["_sync_case_metrics"]()
                self.assertAlmostEqual(
                    ns["METRICS"]["passed_volume_pct"],
                    target["passed_volume_pct"],
                )
                self.assertTrue(any(
                    item.startswith("tri_prism_triangle:passed_")
                    for item in ns["_case_oracle_failures"]()
                ))

                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(
                        _slot(spec, "TAIL").values[0],
                        "<ladder-tail>",
                        "exec",
                    ), ns)
                self.assertEqual(ns["FW_VAR"], 3)

    def test_deep_thread_accumulates_attempt_cost_and_classifies_errors(self):
        spec = fg.load_spec(DEEP_THREAD, strict=True)
        prefix = (
            _slot(spec, "HEAD").values[0] +
            _slot(spec, "START_POSE").values[0]
        )
        ns: dict = {}
        with tempfile.TemporaryDirectory(prefix="sieve3d-thread-accounting-") as out:
            with _candidate_environment(out):
                exec(compile(prefix, "<thread-prefix>", "exec"), ns)
                ns["_prepare"]()
                ns["_snapshot_metrics"]()
                base_effort = ns["METRICS"]["effort"]
                real_call = ns["_call"]

                def failed_thread(method, path, fn, state, payload):
                    if path == "/api/v1/thread":
                        return {"success": False, "keyframes": 7, "frames": []}
                    return real_call(method, path, fn, state, payload)

                ns["_call"] = failed_thread
                ns["_run_tactic"]("thread")
                ns["_run_tactic"]("thread")
                self.assertEqual(ns["METRICS"]["effort"], base_effort + 14)
                self.assertEqual(ns["METRICS"]["domain_errors"], 2)
                self.assertEqual(ns["METRICS"]["api_errors"], 0)

                def collision(method, path, fn, state, payload):
                    if path == "/api/v1/thread":
                        raise ns["api_v1"].ApiError("collision", "expected jam")
                    return real_call(method, path, fn, state, payload)

                ns["_call"] = collision
                ns["_run_tactic"]("thread")
                self.assertEqual(ns["METRICS"]["domain_errors"], 3)
                self.assertEqual(ns["METRICS"]["api_errors"], 0)

                def bad_request(method, path, fn, state, payload):
                    if path == "/api/v1/thread":
                        raise ns["api_v1"].ApiError(
                            "bad_request", "broken tactic contract")
                    return real_call(method, path, fn, state, payload)

                ns["_call"] = bad_request
                ns["_run_tactic"]("thread")
                self.assertEqual(ns["METRICS"]["domain_errors"], 3)
                self.assertEqual(ns["METRICS"]["api_errors"], 1)

                ns["_call"] = real_call
                real_call(
                    "POST", "/api/v1/record", ns["api_v1"].h_record,
                    ns["_state"], {"cmd": "cut"},
                )


@unittest.skipUnless(laws is not None, "external sieve3d project is absent")
class TestMetamorphicFactorContracts(unittest.TestCase):
    def tearDown(self):
        laws.reset()

    def test_action_law_dispatch_exercises_every_selected_case_and_fault(self):
        laws.reset()
        laws.select_case("flower_fit")
        laws.select_case("cube_square")
        seen = []

        def core(case):
            seen.append(("core", case))

        def rejection(case):
            seen.append(("fault", case))

        with (
            mock.patch.object(laws, "_law_commutation", core),
            mock.patch.object(laws, "_law_rejected_atomicity", rejection),
        ):
            laws.run_law("commutation")

        self.assertEqual(seen, [
            ("core", "flower_fit"),
            ("fault", "flower_fit"),
            ("core", "cube_square"),
            ("fault", "cube_square"),
        ])
        self.assertEqual(laws.CTX.metrics["law_evals"], 4)

        source = inspect.getsource(laws._law_rejected_atomicity)
        self.assertIn("CTX.atoms", source)
        self.assertIn("SCALES[CTX.scale]", source)

    def test_any_selected_case_precondition_skip_rejects_candidate(self):
        laws.reset()
        laws.CTX.metrics["record_steps"] = 1
        laws.CTX.metrics["preconditions_met"] = 3
        laws.CTX.metrics["precondition_skips"] = 1
        self.assertEqual(laws.fw_var(), 4)

    def test_interleaving_canonical_form_preserves_generated_local_order(self):
        generated = ["B_dy", "A_dy", "B_dx", "A_dx"]
        self.assertEqual(laws._canonical_interleave(generated), [
            "A_dy", "A_dx", "B_dy", "B_dx",
        ])
        with self.assertRaises(ValueError):
            laws._canonical_interleave(["A_dx", "A_dx", "B_dx", "B_dy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
