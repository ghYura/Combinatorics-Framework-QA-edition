#!/usr/bin/env python3
"""Combinatorial-principles tests for complex 3D bodies vs 2D sieve.

These are brand-new Bundle-driven tests: they do not reuse Claude's unittest
campaigns. The point is to test the claim in the handoff directly: when the
oracle is a metamorphic law, combinatorics over entities and action orders is
useful and catches state-machine defects independent of hand-picked geometry
truth tables.
"""

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

ROOT = HERE / "combinatorial_tests" / "sieve3d_complex_bodies" / "combinatorial_principles"
ACTION = ROOT / "action_laws" / "sieve3d_action_laws.toml"
INTER = ROOT / "interleavings" / "sieve3d_interleavings.toml"
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
    old = {k: os.environ.get(k) for k in (
        "SIEVE3D_ROOT", "SIEVE3D_REC_OUT_DIR", "SIEVE3D_COMBI_PRINCIPLES_ROOT")}
    os.environ["SIEVE3D_ROOT"] = str(EXTERNAL_ROOT)
    os.environ["SIEVE3D_REC_OUT_DIR"] = rec_root
    os.environ["SIEVE3D_COMBI_PRINCIPLES_ROOT"] = str(ROOT)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TestSieve3dCombinatorialPrinciples(unittest.TestCase):
    def test_specs_load_strict_and_have_intentional_cardinality(self):
        action = fg.load_spec(ACTION, strict=True)
        inter = fg.load_spec(INTER, strict=True)

        self.assertEqual([s.sheet for s in action.slots], [
            "HEAD", "CASESET", "ACTION_WORD", "FAULT", "SCALE", "LAW",
            "OBS", "OPT_RECORD_STATUS", "TAIL",
        ])
        plan = fg.spec_cardinality_plan(action)
        self.assertEqual(plan.mandatory.value, 5760)
        self.assertEqual(plan.optional_multiplier.value, 2)
        self.assertEqual(plan.final.value, 11520)

        self.assertEqual([s.sheet for s in inter.slots], [
            "HEAD", "BODYPAIR", "SCALE", "INTERLEAVE", "RUN", "OBS",
            "OPT_RECORD_STATUS", "TAIL",
        ])
        inter_plan = fg.spec_cardinality_plan(inter)
        self.assertEqual(inter_plan.mandatory.value, 576)
        self.assertEqual(inter_plan.optional_multiplier.value, 2)
        self.assertEqual(inter_plan.final.value, 1152)

    def test_specs_use_dedicated_combinatoric_rules_and_recording_contract(self):
        action = fg.load_spec(ACTION, strict=True)
        inter = fg.load_spec(INTER, strict=True)

        self.assertEqual(_slot(action, "CASESET").verb, "FW_Combi(2)")
        self.assertEqual(_slot(action, "ACTION_WORD").verb, "FW_PermutR(2)")
        self.assertEqual(_slot(action, "OBS").verb, "FW_Subsets")
        self.assertIn("FW_Optional", _slot(action, "OPT_RECORD_STATUS").flags)
        self.assertIn("rejected_atomicity", "\n".join(_slot(action, "LAW").values))

        self.assertEqual(_slot(inter, "BODYPAIR").verb, "FW_Combi(2)")
        self.assertEqual(_slot(inter, "INTERLEAVE").verb, "FW_Permut")
        self.assertEqual(_slot(inter, "OBS").verb, "FW_Subsets")
        self.assertIn("FW_Optional", _slot(inter, "OPT_RECORD_STATUS").flags)

        for spec in (action, inter):
            head = _slot(spec, "HEAD").values[0].rstrip()
            tail = _slot(spec, "TAIL").values[0].lstrip()
            self.assertTrue(head.endswith("laws.start_recording()"))
            self.assertTrue(tail.startswith("_REC_INFO = laws.finish_recording("))
            self.assertIn("laws.kv_line", tail)

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_generated_action_law_candidates_execute_and_save_recording(self):
        spec = fg.load_spec(ACTION, strict=True)
        cases = _slot(spec, "CASESET").values
        atoms = _slot(spec, "ACTION_WORD").values
        faults = _slot(spec, "FAULT").values
        scales = _slot(spec, "SCALE").values
        laws = _slot(spec, "LAW").values
        observers = _slot(spec, "OBS").values

        samples = []
        for law_value in laws[:4]:
            samples.append({
                "CASESET": cases[0] + cases[1],
                "ACTION_WORD": atoms[0] + atoms[1],
                "FAULT": faults[0],
                "SCALE": scales[0],
                "LAW": law_value,
                "OBS": observers[1],
            })
        samples.append({
            "CASESET": cases[1] + cases[2],
            "ACTION_WORD": atoms[2] + atoms[3],
            "FAULT": faults[2],
            "SCALE": scales[1],
            "LAW": laws[4],
            "OBS": observers[0] + observers[1],
            "OPT_RECORD_STATUS": _slot(spec, "OPT_RECORD_STATUS").values[0],
        })
        for values in samples:
            ns: dict = {}
            buf = io.StringIO()
            code = _candidate(spec, values)
            with tempfile.TemporaryDirectory(prefix="sieve3d-action-laws-") as rec_root:
                with _candidate_environment(rec_root), contextlib.redirect_stdout(buf):
                    exec(compile(code, "<sieve3d-action-law-candidate>", "exec"), ns)
                out = buf.getvalue()
                self.assertEqual(ns["FW_VAR"], 0, out)
                self.assertIn("app=sieve3d_action_laws", out)
                self.assertIn("criteria_profile=sieve3d_action_laws_v1", out)
                self.assertIn("criteria_metrics=law_evals:max,preconditions_met:max,precondition_skips:min,oracle_checks:max,violations:min,record_steps:max,api_calls:min", out)
                self.assertIn("precondition_skips=0", out)
                self.assertIn("violations=0", out)
                self.assertGreater(ns["laws"].CTX.metrics["preconditions_met"], 0, out)
                self.assertGreater(ns["laws"].CTX.metrics["oracle_checks"], 0, out)
                self.assertGreater(ns["laws"].CTX.metrics["record_steps"], 0, out)
                self.assertTrue(Path(ns["laws"].CTX.rec_file).is_file(), out)
                self.assertTrue(Path(ns["laws"].CTX.rec_json).is_file(), out)
                self.assertTrue(Path(ns["laws"].CTX.rec_file).read_text(encoding="utf-8").strip(), out)

    @unittest.skipUnless(EXTERNAL_ROOT.exists(), "external sieve3d project is not present")
    def test_generated_independent_interleaving_candidate_executes_and_save_recording(self):
        spec = fg.load_spec(INTER, strict=True)
        pairs = _slot(spec, "BODYPAIR").values
        interleave = _slot(spec, "INTERLEAVE").values
        values = {
            "BODYPAIR": pairs[0] + pairs[1],
            "SCALE": _slot(spec, "SCALE").values[0],
            "INTERLEAVE": interleave[2] + interleave[0] + interleave[3] + interleave[1],
            "RUN": _slot(spec, "RUN").values[0],
            "OBS": _slot(spec, "OBS").values[1],
        }
        ns: dict = {}
        buf = io.StringIO()
        code = _candidate(spec, values)
        with tempfile.TemporaryDirectory(prefix="sieve3d-interleave-") as rec_root:
            with _candidate_environment(rec_root), contextlib.redirect_stdout(buf):
                exec(compile(code, "<sieve3d-interleaving-candidate>", "exec"), ns)
            out = buf.getvalue()
            self.assertEqual(ns["FW_VAR"], 0, out)
            self.assertIn("app=sieve3d_interleavings", out)
            self.assertIn("criteria_profile=sieve3d_interleavings_v1", out)
            self.assertIn("law=independent_interleave", out)
            self.assertIn("precondition_skips=0", out)
            self.assertIn("violations=0", out)
            self.assertGreater(ns["laws"].CTX.metrics["preconditions_met"], 0, out)
            self.assertGreater(ns["laws"].CTX.metrics["oracle_checks"], 0, out)
            self.assertGreater(ns["laws"].CTX.metrics["record_steps"], 0, out)
            self.assertTrue(Path(ns["laws"].CTX.rec_file).is_file(), out)
            self.assertTrue(Path(ns["laws"].CTX.rec_json).is_file(), out)
            self.assertTrue(Path(ns["laws"].CTX.rec_file).read_text(encoding="utf-8").strip(), out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
