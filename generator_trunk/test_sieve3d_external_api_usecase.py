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

"""Static and lightweight runtime checks for the sieve3d external API Bundle specs."""

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

ROOT = HERE / "combinatorial_tests" / "sieve3d_external_api"
LADDER = ROOT / "api_ladder" / "sieve3d_api_ladder.toml"
DEEP = ROOT / "deep_thread" / "sieve3d_api_deep_thread.toml"
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
    old_root = os.environ.get("SIEVE3D_ROOT")
    old_rec = os.environ.get("SIEVE3D_REC_OUT_DIR")
    os.environ["SIEVE3D_ROOT"] = str(EXTERNAL_ROOT)
    os.environ["SIEVE3D_REC_OUT_DIR"] = rec_root
    try:
        yield
    finally:
        if old_root is None:
            os.environ.pop("SIEVE3D_ROOT", None)
        else:
            os.environ["SIEVE3D_ROOT"] = old_root
        if old_rec is None:
            os.environ.pop("SIEVE3D_REC_OUT_DIR", None)
        else:
            os.environ["SIEVE3D_REC_OUT_DIR"] = old_rec


class TestSieve3dExternalApiSpecs(unittest.TestCase):
    def test_specs_load_strict_and_have_expected_cardinality_shape(self):
        ladder = fg.load_spec(LADDER, strict=True)
        deep = fg.load_spec(DEEP, strict=True)

        self.assertEqual([s.sheet for s in ladder.slots],
                         ["HEAD", "CASE", "ACTION", "ROUTE", "OBS", "OPT_RECORD_STATUS", "TAIL"])
        plan = fg.spec_cardinality_plan(ladder)
        self.assertEqual(plan.mandatory.value, 600)
        self.assertEqual(plan.optional_multiplier.value, 2)
        self.assertEqual(plan.post_sieve.value, 600)
        self.assertEqual(plan.final.value, 1200)
        self.assertEqual(len(ladder.constraints), 0)

        self.assertEqual([s.sheet for s in deep.slots], ["HEAD", "START_POSE", "TACTIC", "TAIL"])
        deep_plan = fg.spec_cardinality_plan(deep)
        self.assertEqual(deep_plan.mandatory.value, 18)
        self.assertEqual(deep_plan.final.value, 18)

    def test_ladder_uses_broader_bundle_verb_set_and_recording_contract(self):
        spec = fg.load_spec(LADDER, strict=True)
        self.assertEqual(_slot(spec, "CASE").verb, "FW_Combi(2)")
        self.assertEqual(_slot(spec, "ACTION").verb, "FW_Permut")
        self.assertEqual(_slot(spec, "OBS").verb, "FW_Subsets")
        self.assertIn("FW_Optional", _slot(spec, "OPT_RECORD_STATUS").flags)
        self.assertIn('_run_selected_route("l4_observe", 4)', _slot(spec, "ROUTE").values[-1])

        head = _slot(spec, "HEAD").values[0].rstrip()
        tail = _slot(spec, "TAIL").values[0].lstrip()
        self.assertIn("CRITERIA_METRICS", head)
        self.assertIn('"record_steps"', head)
        self.assertIn('{"cmd": "action"}', head)
        self.assertIn('{"cmd": "cut"}', head)
        self.assertIn('{"cmd": "retrieve_last_record"}', head)
        self.assertIn("V1_MUT", head)
        self.assertTrue(head.endswith("_start_recording()"))
        self.assertTrue(tail.startswith("_REC_INFO = _finish_recording("))
        self.assertIn("record_file=%s record_json=%s record_steps=%d", tail)

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_sample_generated_ladder_candidates_execute_and_save_recording(self):
        spec = fg.load_spec(LADDER, strict=True)
        cases = _slot(spec, "CASE").values
        actions = _slot(spec, "ACTION").values
        routes = _slot(spec, "ROUTE").values
        observers = _slot(spec, "OBS").values

        samples = [
            {
                "CASE": cases[0] + cases[4],
                "ACTION": actions[0] + actions[1],
                "ROUTE": routes[0],
                "OBS": "",
            },
            {
                "CASE": cases[0] + cases[4],
                "ACTION": actions[0] + actions[1],
                "ROUTE": routes[3],
                "OBS": observers[0] + observers[1],
                "OPT_RECORD_STATUS": _slot(spec, "OPT_RECORD_STATUS").values[0],
            },
        ]
        for values in samples:
            code = _candidate(spec, values)
            ns: dict = {}
            buf = io.StringIO()
            with tempfile.TemporaryDirectory(prefix="sieve3d-bundle-rec-") as rec_root:
                with _candidate_environment(rec_root), contextlib.redirect_stdout(buf):
                    exec(compile(code, "<sieve3d-api-ladder-candidate>", "exec"), ns)
                out = buf.getvalue()
                self.assertEqual(ns["FW_VAR"], 0, out)
                self.assertIn("app=sieve3d_api_ladder", out)
                self.assertIn("criteria_profile=sieve3d_api_ladder_v2", out)
                self.assertIn(
                    "criteria_metrics=passed_volume_pct:max,actions:min,clearance:max,api_route_depth:max,record_steps:max",
                    out,
                )
                self.assertIn(" record_file=", out)
                self.assertIn(" record_json=", out)
                self.assertIn(" record_steps=", out)
                self.assertNotIn(" actions_n=", out)
                self.assertGreater(ns["METRICS"]["record_steps"], 0, out)
                self.assertTrue(Path(ns["REC_FILE"]).is_file(), out)
                self.assertTrue(Path(ns["REC_JSON"]).is_file(), out)
                self.assertTrue(Path(ns["REC_FILE"]).read_text(encoding="utf-8").strip(), out)

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_sample_generated_deep_thread_candidate_executes_and_save_recording(self):
        spec = fg.load_spec(DEEP, strict=True)
        tactics = _slot(spec, "TACTIC").values
        values = {
            "START_POSE": _slot(spec, "START_POSE").values[0],
            "TACTIC": tactics[2] + tactics[2],
        }
        code = _candidate(spec, values)
        ns: dict = {}
        buf = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="sieve3d-deep-rec-") as rec_root:
            with _candidate_environment(rec_root), contextlib.redirect_stdout(buf):
                exec(compile(code, "<sieve3d-deep-thread-candidate>", "exec"), ns)
            out = buf.getvalue()
            self.assertEqual(ns["FW_VAR"], 0, out)
            self.assertIn("app=sieve3d_api_deep_thread", out)
            self.assertIn("criteria_profile=sieve3d_api_deep_thread_v2", out)
            self.assertIn(
                "criteria_metrics=passed_volume_pct:max,effort:min,thread_success:max,record_steps:max",
                out,
            )
            self.assertIn("tactics=thread>thread", out)
            self.assertGreater(ns["METRICS"]["record_steps"], 0, out)
            self.assertEqual(ns["METRICS"]["thread_success"], 1, out)
            self.assertTrue(Path(ns["REC_FILE"]).is_file(), out)
            self.assertTrue(Path(ns["REC_JSON"]).is_file(), out)
            self.assertTrue(Path(ns["REC_FILE"]).read_text(encoding="utf-8").strip(), out)

    def test_deep_thread_uses_tactic_sequences_and_recording_contract(self):
        spec = fg.load_spec(DEEP, strict=True)
        self.assertEqual(_slot(spec, "START_POSE").verb, "FW_Combi(1)")
        self.assertEqual(_slot(spec, "TACTIC").verb, "FW_PermutR(2)")
        tactics = "\n".join(_slot(spec, "TACTIC").values)
        self.assertIn("direct_drop", tactics)
        self.assertIn("wiggle", tactics)
        self.assertIn("thread", tactics)

        head = _slot(spec, "HEAD").values[0].rstrip()
        tail = _slot(spec, "TAIL").values[0].lstrip()
        self.assertIn("h_thread", head)
        self.assertIn("CRITERIA_METRICS", head)
        self.assertIn('CRITERIA_PROFILE = "sieve3d_api_deep_thread_v2"', head)
        self.assertIn('"record_steps"', head)
        self.assertTrue(head.endswith("_start_recording()"))
        self.assertTrue(tail.startswith("_REC_INFO = _finish_recording("))
        self.assertIn("criteria_profile=%s", tail)
        self.assertLess(tail.index('METRICS["record_steps"] <= 0'), tail.index('"thread" in TACTICS'))
        self.assertIn("record_file=%s record_json=%s record_steps=%d", tail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
