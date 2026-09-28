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

"""D3 phase C fixture checks: the flag, V, late_restart's branch, per-event observation, oracle
blindness, and agreement with the frozen predictions and verify.py's own model on all 1440 cases.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import importlib
import io
import itertools
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import runtime  # noqa: E402
import sut      # noqa: E402


def run(policy, order):
    importlib.reload(runtime)
    runtime.start(policy)
    for op in order:
        runtime.step(op)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        runtime.finish("C")
    return json.loads(base64.urlsafe_b64decode(dict(t.split("=", 1) for t in out.getvalue().split())["rec"]))


class Machine(unittest.TestCase):
    def test_flag_set_by_refund_attempt_reset_by_renewal_kept_across_restart(self):
        s = sut.Service("correct", sut.Durable())
        s = s.apply("F")
        self.assertTrue(s.snapshot()["refund_attempted"])
        s = s.apply("S")
        self.assertTrue(s.snapshot()["refund_attempted"])
        s = s.apply("N")
        self.assertFalse(s.snapshot()["refund_attempted"])

    def test_view_changes_nothing(self):
        s = sut.Service("correct", sut.Durable()).apply("C")
        before = s.snapshot()
        self.assertEqual(s.apply("V").snapshot(), before)

    def test_late_restart_branch_only_on_its_exact_state(self):
        def final(policy, order):
            s = sut.Service(policy, sut.Durable())
            for op in order:
                s = s.apply(op)
            return s.snapshot()
        faulty = final("late_restart", "CNFS")
        self.assertEqual((faulty["balance"], final("correct", "CNFS")["balance"]), (0, 100))   # the branch fires
        for order in ("CFNS", "CNS", "NCFS", "CNFNS", "CNQS"):                              # its state is not reached
            self.assertEqual(final("late_restart", order), final("correct", order), order)


class Observation(unittest.TestCase):
    def test_heal_persist_and_nontrigger(self):
        heal, persist, nontrigger = run("late_restart", "CNFSQV"), run("late_restart", "QCNFSV"), run("late_restart", "CFNSQV")
        self.assertEqual((heal["failing_checkpoints"], heal["final_only_verdict"], heal["hidden_by_final_only"]), ([4], "PASS", True))
        self.assertEqual((persist["failing_checkpoints"], persist["final_only_verdict"]), ([5, 6], "DOMAIN_FAIL"))
        self.assertEqual(nontrigger["verdict"], "PASS")
        self.assertEqual(run("correct", "CNFSQV")["verdict"], "PASS")

    def test_contract_violations_are_setup_errors(self):
        importlib.reload(runtime)
        runtime.start("correct")
        for op in "CFNQS":
            runtime.step(op)
        with self.assertRaises(ValueError), contextlib.redirect_stdout(io.StringIO()):
            runtime.finish("C")                                    # V missing

    def test_oracle_is_policy_blind(self):
        src = (HERE / "oracle.py").read_text()
        imports = {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {"sut", "runtime"})
        literals = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertFalse(literals & set(sut.POLICIES))          # no policy name is ever compared or read
        self.assertNotIn("late_restart", src)


class Agreement(unittest.TestCase):
    """Pre-run self-check over all 1440 cases: fixture == verify.py model; faults == frozen predictions."""

    def test_all_cases(self):
        import verify
        derived = json.loads((HERE / "architect-derived.json").read_text())
        faults, hidden = [], []
        for policy in ("correct", "late_restart"):
            for order in ("".join(p) for p in itertools.permutations("CFNQSV")):
                rec = run(policy, order)
                obs, ref = verify.machine(order, policy)
                self.assertEqual([c["observed"] for c in rec["checkpoints"]], obs, (policy, order))
                self.assertEqual([c["reference"] for c in rec["checkpoints"]], ref, (policy, order))
                if rec["verdict"] == "DOMAIN_FAIL":
                    faults.append((policy, order))
                if rec["hidden_by_final_only"]:
                    hidden.append(order)
        self.assertEqual(sorted(o for _, o in faults), sorted(derived["predicted_fault_orders"]))
        self.assertTrue(all(p == "late_restart" for p, _ in faults))
        self.assertEqual(sorted(hidden), sorted(derived["predicted_hidden_orders"]))


if __name__ == "__main__":
    unittest.main()
