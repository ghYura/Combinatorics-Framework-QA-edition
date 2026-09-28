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

"""D3 fixture checks: state transitions, fault variants, per-checkpoint observation, oracle
blindness, emission, and agreement with the frozen predictions and verify.py on all 153 cases.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import importlib
import io
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import oracle   # noqa: E402
import runtime  # noqa: E402
import sut      # noqa: E402


def run(phase, policy, ops):
    importlib.reload(runtime)
    runtime.start(policy)
    for op in ops:
        runtime.step(op)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = runtime.finish(phase)
    tokens = dict(t.split("=", 1) for t in out.getvalue().split())
    return code, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


class Transitions(unittest.TestCase):
    def service(self, policy):
        return sut.Service(policy, sut.Ledger())

    def test_charge_refund_renew_and_history(self):
        s = self.service("correct")
        for op in "CFN":
            s = s.apply(op)
        self.assertEqual(s.snapshot(), {"epoch": 1, "captures": [1, 0], "refunds": [1, 0], "balance": 0})
        s = s.apply("C")
        self.assertEqual(s.snapshot()["captures"], [1, 1])

    def test_refunded_epoch_is_not_charged_again_and_refund_needs_a_charge(self):
        s = self.service("correct")
        for op in "FCFC":
            s = s.apply(op)
        self.assertEqual(s.snapshot(), {"epoch": 0, "captures": [1], "refunds": [1], "balance": 0})

    def test_refund_unchecked_refunds_without_a_charge_and_twice(self):
        s = self.service("refund_unchecked")
        s = s.apply("F").apply("F")
        self.assertEqual(s.snapshot(), {"epoch": 0, "captures": [0], "refunds": [2], "balance": -200})

    def test_restart_keeps_the_ledger_and_only_restart_cache_loses_the_balance(self):
        for policy, balance in (("correct", 100), ("restart_cache", 0)):
            s = self.service(policy).apply("C").apply("S")
            self.assertEqual(s.snapshot(), {"epoch": 0, "captures": [1], "refunds": [0], "balance": balance}, policy)
            self.assertEqual(s.apply("Q").snapshot()["balance"], 100, policy)      # reconcile heals


class Observation(unittest.TestCase):
    def test_every_step_is_observed_and_a_healed_fault_stays_visible(self):
        code, rec = run("A", "restart_cache", list("CNF") + ["S", "Q"])
        self.assertEqual([c["op"] for c in rec["checkpoints"]], ["C", "N", "F", "S", "Q"])
        self.assertEqual(rec["failing_checkpoints"], [4])                       # after S, balance 0 vs 100
        self.assertEqual((rec["verdict"], rec["final_only_verdict"], rec["hidden_by_final_only"]), ("DOMAIN_FAIL", "PASS", True))
        self.assertEqual(code, 2)
        self.assertEqual(rec["checkpoints"][3]["mismatched_fields"], ["balance"])
        self.assertFalse(rec["checkpoints"][3]["invariants"]["ledger_balance"])

    def test_all_failures_are_kept(self):
        _, rec = run("B", "refund_unchecked", list("FFC"))
        self.assertEqual(rec["failing_checkpoints"], [1, 2, 3])
        self.assertFalse(rec["checkpoints"][1]["invariants"]["count_domain"])     # refunds [2]

    def test_contract_violations_are_setup_errors(self):
        importlib.reload(runtime)
        with self.assertRaises(RuntimeError):
            runtime.step("C")                                                     # before start
        runtime.start("correct")
        with self.assertRaises(ValueError):
            runtime.step("X")
        importlib.reload(runtime)
        runtime.start("correct")
        for op in "CF":
            runtime.step(op)
        with self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
            runtime.finish("A")                                                   # two operations only

    def test_oracle_is_policy_blind(self):
        src = (HERE / "oracle.py").read_text()
        imports = {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {"sut", "runtime"})
        for name in sut.POLICIES:
            self.assertNotIn(name, src)


class Agreement(unittest.TestCase):
    """Pre-run self-check: fixture == frozen predictions == verify.py's own model on all 153 cases."""

    def test_fixture_matches_frozen_predictions_and_verifier_model(self):
        import verify
        cases = json.loads((HERE / "architect-derived.json").read_text())["cases"]
        self.assertEqual(sorted(c["id"] for c in cases), verify.enumerate_cases("A") + verify.enumerate_cases("B"))
        for c in cases:
            phase, policy = c["id"].split("|")[:2]
            _, rec = run(phase, policy, c["events"])
            obs, ref = verify.machine(c["events"], policy)
            self.assertEqual(rec["case_id"], c["id"])
            self.assertEqual([k["observed"] for k in rec["checkpoints"]], c["predicted_trace"], c["id"])
            self.assertEqual([k["reference"] for k in rec["checkpoints"]], c["expected_trace"], c["id"])
            self.assertEqual((obs, ref), (c["predicted_trace"], c["expected_trace"]), c["id"])
            self.assertEqual(rec["failing_checkpoints"], c["mismatch_checkpoints"], c["id"])
            self.assertEqual(rec["verdict"], c["predicted_outcome"], c["id"])
            self.assertEqual(rec["final_only_verdict"] == "DOMAIN_FAIL", c["final_only_fail"], c["id"])


if __name__ == "__main__":
    unittest.main()
