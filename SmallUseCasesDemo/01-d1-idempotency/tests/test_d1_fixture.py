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

"""Service, oracle and runtime checks for D1. They inspect ledgers and receipts, not verdict tables.

Run: python -m pytest -q -p no:cacheprovider tests   (or: python -m unittest discover tests)
"""
import ast
import base64
import copy
import hashlib
import itertools
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import oracle   # noqa: E402
import runtime  # noqa: E402
import sut      # noqa: E402

PAY = {"amount_minor": 100, "currency": "TST"}


def req(transport, order="O1", op="OP1", amount=100):
    return {"transport_id": transport, "order_id": order, "operation_id": op,
            "payload": {"amount_minor": amount, "currency": "TST"}}


class ServiceBehaviour(unittest.TestCase):
    def fresh(self, policy):
        state = sut.DurableState()
        return state, sut.Service(policy, state)

    def test_equal_payload_replay_returns_original_receipt(self):
        state, svc = self.fresh("durable_operation")
        first = svc.handle(req("T0"))
        again = svc.handle(req("T1"))
        self.assertEqual(first, {"status": "APPLIED", "receipt_id": 1, "order_id": "O1", "operation_id": "OP1"})
        self.assertEqual(again, {"status": "REPLAY", "receipt_id": 1, "order_id": "O1", "operation_id": "OP1"})
        self.assertEqual(len(state.ledger), 1)

    def test_conflicting_retry_adds_nothing_and_overwrites_nothing(self):
        state, svc = self.fresh("durable_operation")
        svc.handle(req("T0"))
        before_ledger, before_cache = copy.deepcopy(state.ledger), copy.deepcopy(state.cache)
        resp = svc.handle(req("T1", amount=101))
        self.assertEqual(resp["status"], "CONFLICT")
        self.assertIsNone(resp["receipt_id"])
        self.assertEqual(state.ledger, before_ledger)
        self.assertEqual(state.cache, before_cache)
        self.assertEqual(svc.handle(req("T2")), {"status": "REPLAY", "receipt_id": 1,
                                                 "order_id": "O1", "operation_id": "OP1"})

    def test_two_operations_in_one_order_each_take_effect(self):
        state, svc = self.fresh("durable_operation")
        a = svc.handle(req("T0", op="OP1"))
        b = svc.handle(req("T1", op="OP2"))
        self.assertEqual((a["status"], b["status"]), ("APPLIED", "APPLIED"))
        self.assertEqual([(e["order_id"], e["operation_id"]) for e in state.ledger], [("O1", "OP1"), ("O1", "OP2")])

    def test_equal_payload_in_different_orders_each_take_effect(self):
        state, svc = self.fresh("durable_operation")
        svc.handle(req("T0", order="O1"))
        resp = svc.handle(req("T1", order="O2"))
        self.assertEqual(resp, {"status": "APPLIED", "receipt_id": 2, "order_id": "O2", "operation_id": "OP1"})
        self.assertEqual(state.ledger[1]["payload"], PAY)

    def test_restart_keeps_ledger_and_durable_cache_but_not_volatile_cache(self):
        for policy in ("durable_transport", "volatile_transport"):
            state, svc = self.fresh(policy)
            svc.handle(req("T0"))
            svc = sut.Service(policy, state)          # restart: new process object, same backing state
            self.assertEqual(len(state.ledger), 1, policy)   # the ledger is durable for every policy
            resp = svc.handle(req("T0"))
            expected = "REPLAY" if policy == "durable_transport" else "APPLIED"
            self.assertEqual(resp["status"], expected, policy)
            self.assertEqual(len(state.ledger), 1 if expected == "REPLAY" else 2, policy)

    def test_transport_keys_duplicate_a_retry_with_new_transport_identity(self):
        for policy in ("volatile_transport", "durable_transport"):
            state, svc = self.fresh(policy)
            svc.handle(req("T0"))
            resp = svc.handle(req("T1"))
            self.assertEqual((resp["status"], resp["receipt_id"]), ("APPLIED", 2), policy)
            self.assertEqual([(e["order_id"], e["operation_id"]) for e in state.ledger], [("O1", "OP1")] * 2)

    def test_order_key_replays_a_foreign_operation(self):
        state, svc = self.fresh("durable_order")
        svc.handle(req("T0", op="OP1"))
        resp = svc.handle(req("T3", op="OP2"))
        self.assertEqual(resp, {"status": "REPLAY", "receipt_id": 1, "order_id": "O1", "operation_id": "OP1"})
        self.assertEqual(len(state.ledger), 1)            # O1/OP2 never took effect

    def test_payload_key_replays_another_orders_receipt(self):
        state, svc = self.fresh("durable_payload")
        svc.handle(req("T0", order="O1"))
        resp = svc.handle(req("T3", order="O2"))
        self.assertEqual(resp, {"status": "REPLAY", "receipt_id": 1, "order_id": "O1", "operation_id": "OP1"})
        self.assertEqual(len(state.ledger), 1)

    def test_consecutive_cases_share_no_state(self):
        first = runtime.run_case("durable_operation", [0, 0, 0], [0, 0], "new_order_equal_payload")
        second = runtime.run_case("durable_operation", [0, 0, 0], [0, 0], "new_order_equal_payload")
        self.assertEqual(first, second)
        self.assertEqual(second["observation"]["first_receipt"], 1)
        self.assertEqual(second["observation"]["deliveries"][0]["effects_after"], 1)

    def test_unknown_policy_is_a_setup_error(self):
        with self.assertRaises(ValueError):
            sut.Service("durable_customer", sut.DurableState())


class OracleJudgement(unittest.TestCase):
    def test_oracle_source_is_policy_blind(self):
        src = (HERE / "oracle.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                    for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertFalse(imported & {"sut", "runtime"})
        for name in sut.POLICIES + runtime.CONTROLS[1:]:
            self.assertNotIn(name, src)

    def test_wrong_identity_replay_fails_even_with_replay_status(self):
        obs = runtime.observe("durable_operation", [0, 0, 0], [0, 0], "new_order_equal_payload")
        forged = copy.deepcopy(obs)
        forged["peer"]["response"] = {"status": "REPLAY", "receipt_id": 1, "order_id": "O2", "operation_id": "OP1"}
        forged["peer"]["effect_delta"] = 0
        forged["post_peer_ledger"] = forged["pre_peer_ledger"]
        checks = oracle.judge(forged)
        self.assertFalse(checks["receipt_identity"])
        self.assertFalse(checks["peer_independence"])
        self.assertFalse(checks["contract_valid"])

    def test_overwritten_prior_payload_fails_conflict_handling(self):
        obs = runtime.observe("durable_operation", [0, 0, 0], [0, 0], "conflicting_retry")
        forged = copy.deepcopy(obs)
        forged["post_peer_ledger"][0]["payload"]["amount_minor"] = 101
        checks = oracle.judge(forged)
        self.assertFalse(checks["conflict_handling"])
        self.assertFalse(checks["contract_valid"])

    def test_defective_policies_rejected_on_declared_witnesses(self):
        witnesses = {
            ("volatile_transport", "000", "01", "none"): "core_at_most_once",
            ("durable_transport", "001", "00", "none"): "core_at_most_once",
            ("durable_order", "000", "00", "new_operation_same_order"): "peer_independence",
            ("durable_payload", "000", "00", "new_order_equal_payload"): "peer_independence",
        }
        for (impl, labels, cuts, control), sensor in witnesses.items():
            rec = runtime.run_case(impl, [int(c) for c in labels], [int(c) for c in cuts], control)
            obs = rec["observation"]
            self.assertEqual(rec["verdict"], "DOMAIN_FAIL", impl)
            self.assertFalse(rec["checks"][sensor], impl)
            if sensor == "core_at_most_once":        # a second durable effect of the same operation
                self.assertEqual(obs["pre_peer_multiplicity"], {"O1/OP1": 2})
            else:                                     # the peer got someone else's receipt
                self.assertEqual(obs["peer"]["response"]["status"], "REPLAY")
                self.assertEqual(obs["peer"]["response"]["receipt_id"], 1)
                self.assertEqual(obs["peer"]["effect_delta"], 0)
                self.assertFalse(rec["checks"]["receipt_identity"])

    def test_operation_key_positive_control(self):
        for control in runtime.CONTROLS:
            rec = runtime.run_case("durable_operation", [0, 0, 0], [0, 0], control)
            self.assertEqual(rec["verdict"], "PASS", control)
        rec = runtime.run_case("durable_operation", [0, 1, 2], [1, 1], "none")
        self.assertEqual([d["response"]["receipt_id"] for d in rec["observation"]["deliveries"]], [1, 1, 1])
        self.assertEqual([d["epoch"] for d in rec["observation"]["deliveries"]], [0, 1, 2])

    def test_sensors_agree_with_aggregate_over_the_whole_raw_domain(self):
        for impl, l2, l3, c1, c2, control in itertools.product(
                sut.POLICIES, (0, 1), (0, 1, 2), (0, 1), (0, 1), runtime.CONTROLS):
            rec = runtime.run_case(impl, [0, l2, l3], [c1, c2], control)
            self.assertTrue(rec["checks"]["sensors_agree"], rec["case_id"])


class VerifierAgreement(unittest.TestCase):
    """Pre-run self-check: verify.py's contract-derived model and the fixture agree on every valid case.

    verify.py never imports the fixture; only this test puts the two side by side."""

    def test_independent_prediction_matches_fixture_on_all_120_cases(self):
        import verify
        rows = [r for r in verify.raw_space() if verify.valid(r)]
        self.assertEqual(len(rows), 120)
        for impl, labels, cuts, control in rows:
            rec = runtime.run_case(impl, list(labels), list(cuts), control)
            obs, sensors = verify.predict(impl, labels, cuts, control)
            self.assertEqual(rec["observation"], obs, rec["case_id"])
            self.assertEqual({k: rec["checks"][k] for k in sensors}, sensors, rec["case_id"])


class Emission(unittest.TestCase):
    def test_metrics_line_round_trips_the_full_record(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = runtime.emit("durable_transport", [0, 0, 1], [0, 0], "none")
        line = out.getvalue().strip()
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertTrue(line.startswith("app=d1_idempotency FW_VAR=2 "))
        tokens = dict(t.split("=", 1) for t in line.split())
        raw = base64.urlsafe_b64decode(tokens["rec"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), tokens["rec_sha256"])
        rec = json.loads(raw)
        self.assertEqual((code, rec["fw_var"], rec["case_id"]), (2, 2, "durable_transport|L=001|C=00|P=none"))

    def test_invalid_inputs_raise_instead_of_failing_the_domain(self):
        for args in (("durable_order", [0, 0, 3], [0, 0], "none"),
                     ("durable_order", [1, 0, 0], [0, 0], "none"),
                     ("durable_order", [0, 0, 0], [0, 2], "none"),
                     ("durable_order", [0, 0, 0], [0, 0], "replay_everything")):
            with self.assertRaises(ValueError):
                runtime.run_case(*args)


if __name__ == "__main__":
    unittest.main()
