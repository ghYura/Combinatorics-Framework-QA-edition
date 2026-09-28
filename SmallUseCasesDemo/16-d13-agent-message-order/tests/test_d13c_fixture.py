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

"""D13c fixture checks: models against the frozen predictions; double booking and silent promise
withdrawal; correct STALE refusal and serial BUSY; deny-all; missing, mutated and dropped promises;
wrong offer versions; disabled B.inspect; malformed local order; caps versus switches; invalid
messages (unit level only); the bond truth tables; independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import explore  # noqa: E402
import oracle  # noqa: E402
import runtime  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}


def run_case(policy, mode, cap, schedule):
    runtime._state.clear()
    runtime.begin()
    runtime.impl(policy)
    runtime.mode(mode)
    runtime.cap(cap)
    for i, a in enumerate(schedule, 1):
        runtime.set_step(i, a)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(t.split("=", 1) for t in lines[0].split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def statuses(rec):
    return [e["response"].get("status") for e in rec["observed_trace"] if e["request"]["kind"] == "commit"]


def test_all_54_match_frozen_and_the_verifier_model():
    keys = ("policy", "mode", "cap", "schedule", "preemptions", "context_switches", "observed_trace", "reference_trace", "checks",
            "failing_checkpoints")
    for cid, fz in FROZEN.items():
        fw, rec = run_case(fz["policy"], fz["mode"], fz["cap"], fz["schedule"])
        own = verify.own_case(fz["policy"], fz["mode"], fz["cap"], fz["schedule"])
        assert rec["case_id"] == cid and {k: rec[k] for k in keys} == {k: fz[k] for k in keys} == {k: own[k] for k in keys}
        assert rec["verdict"] == fz["predicted_outcome"] == own["verdict"] and fw == (0 if rec["verdict"] == "PASS" else 2)
        assert rec["reconstructed_ledgers"] == [e["issued_grants"] for e in rec["observed_trace"]]


def test_trust_offer_double_books():
    _, rec = run_case("trust_offer", "independent", 2, "ABAB")
    last = rec["observed_trace"][-1]
    assert statuses(rec) == ["GRANTED", "GRANTED"] and last["allocations"] == {"A": "R:A", "B": "R:B"}
    assert rec["all_checks"] == {"capacity_ok": False, "exclusive_promises_ok": False, "commitments_ok": True, "reference_ok": False}
    assert rec["failing_checkpoints"] == [4] and rec["verdict"] == "DOMAIN_FAIL"


def test_overwrite_owner_passes_capacity_but_withdraws_a_promise():
    _, rec = run_case("overwrite_owner", "independent", 2, "ABAB")
    last = rec["observed_trace"][-1]
    assert last["allocations"] == {"B": "R:B"} and last["issued_grants"] == {"A": "R:A", "B": "R:B"}
    assert all(len(e["allocations"]) <= 1 for e in rec["observed_trace"])           # capacity alone sees nothing
    assert rec["all_checks"] == {"capacity_ok": True, "exclusive_promises_ok": False, "commitments_ok": False, "reference_ok": False}
    _, b_first = run_case("overwrite_owner", "after_A_offer", 1, "ABBA")
    assert b_first["observed_trace"][2]["response"] == {"status": "GRANTED", "ticket": "R:B"}
    assert b_first["observed_trace"][3]["allocations"] == {"A": "R:A"} and b_first["verdict"] == "DOMAIN_FAIL"


def test_compare_version_refuses_the_stale_offer():
    _, rec = run_case("compare_version", "independent", 2, "ABAB")
    assert rec["observed_trace"][3]["request"]["offer_version"] == 0 and rec["observed_trace"][2]["version"] == 1
    assert statuses(rec) == ["GRANTED", "STALE"] and rec["verdict"] == "PASS"


@pytest.mark.parametrize("policy", sut.POLICIES)
def test_serial_schedule_gives_busy_and_passes(policy):
    _, rec = run_case(policy, "independent", 0, "AABB")
    assert rec["observed_trace"][2]["response"] == {"available": False, "version": 1}
    assert statuses(rec) == ["GRANTED", "BUSY"] and rec["verdict"] == "PASS"


def test_deny_all_fails(monkeypatch):
    real = sut.Coordinator.deliver
    def deny(self, request):
        reply = real(self, request) if request["kind"] == "inspect" else None
        return reply if reply is not None else {"status": "STALE", "ticket": None}
    monkeypatch.setattr(sut.Coordinator, "deliver", deny)
    _, rec = run_case("compare_version", "independent", 0, "AABB")
    assert rec["all_checks"] == {"capacity_ok": True, "exclusive_promises_ok": True, "commitments_ok": True, "reference_ok": False}
    assert rec["verdict"] == "DOMAIN_FAIL"


def test_missing_or_mutated_promises_fail_integrity(monkeypatch):
    real = sut.Coordinator.deliver
    def forgetful(self, request):
        reply = real(self, request)
        self.issued_grants.clear()                     # the ledger forgets every promise
        return reply
    monkeypatch.setattr(sut.Coordinator, "deliver", forgetful)
    with pytest.raises(RuntimeError, match="issued_grants disagrees"):
        run_case("compare_version", "independent", 0, "AABB")
    trace = verify.model("overwrite_owner", "independent", "ABAB")
    mutated = copy.deepcopy(trace)
    mutated[3]["issued_grants"] = {"B": "R:B"}         # hides the withdrawn promise to A
    j = oracle.judge(mutated, oracle.reference_trace("ABAB", "independent"))
    assert j["integrity_ok"] is False and j["integrity_failures"] == [4] and j["checks"] is None


def test_dropped_replies_are_detected():
    trace = verify.model("compare_version", "independent", "AABB")
    ref = oracle.reference_trace("AABB", "independent")
    dropped = copy.deepcopy(trace)
    dropped[1]["response"] = {}                         # the GRANTED reply to A:commit is lost
    assert oracle.judge(dropped, ref)["integrity_ok"] is False
    assert oracle.judge(trace[:3], ref)["integrity_failures"] == ["length"]
    assert oracle.judge(trace, ref) == {"integrity_ok": True, "integrity_failures": [],
                                        "checks": FROZEN["P=compare_version|M=independent|K=0|S=AABB"]["checks"], "failing_checkpoints": []}


def test_wrong_offer_version_is_detected(monkeypatch):
    real = sut.Coordinator.deliver
    def skewed(self, request):
        reply = real(self, request)
        return dict(reply, version=reply["version"] + 1) if request["kind"] == "inspect" else reply
    monkeypatch.setattr(sut.Coordinator, "deliver", skewed)
    _, rec = run_case("compare_version", "independent", 0, "AABB")
    assert rec["observed_trace"][1]["request"]["offer_version"] == 1 and statuses(rec) == ["STALE", "STALE"]    # no useful grant
    assert not rec["all_checks"]["reference_ok"] and rec["verdict"] == "DOMAIN_FAIL"


def test_disabled_b_inspect_is_a_setup_error():
    with pytest.raises(ValueError, match="disabled in after_A_offer"):
        run_case("compare_version", "after_A_offer", 2, "BAAB")
    with pytest.raises(ValueError):
        oracle.reference_trace("BABA", "after_A_offer")
    assert oracle.enabled({"A": 0, "B": 0}, "after_A_offer") == ["A"] and oracle.enabled({"A": 1, "B": 0}, "after_A_offer") == ["A", "B"]


@pytest.mark.parametrize("calls", [
    lambda r: (r.begin(), r.impl("compare_version"), r.mode("independent"), r.cap(2), r.set_step(2, "A")),   # out of order
    lambda r: (r.begin(), r.impl("compare_version"), r.mode("independent"), r.cap(2),
               [r.set_step(i, a) for i, a in enumerate("AAAB", 1)], r.finish()),                           # three A messages
    lambda r: (r.begin(), r.impl("compare_version"), r.mode("independent"), r.cap(2), r.set_step(1, "C")),
    lambda r: (r.begin(), r.impl("first_come"),),
    lambda r: (r.begin(), r.impl("compare_version"), r.mode("causal")),
    lambda r: (r.begin(), r.impl("compare_version"), r.mode("independent"), r.cap(3)),
    lambda r: (r.begin(), r.mode("independent")),
    lambda r: (r.begin(), r.finish()),
])
def test_setup_errors_raise(calls):
    runtime._state.clear()
    with pytest.raises((RuntimeError, ValueError)):
        calls(runtime)


def test_cap_counts_preemptions_not_switches():
    assert runtime.switches_and_preemptions("AABB") == (1, 0) and runtime.switches_and_preemptions("ABBA") == (2, 1)
    assert runtime.switches_and_preemptions("ABAB") == (3, 2)
    run_case("compare_version", "independent", 0, "AABB")         # one switch, allowed at cap 0
    run_case("compare_version", "independent", 1, "ABBA")         # two switches, one preemption: cap 1
    with pytest.raises(ValueError, match="above cap 1"):
        run_case("compare_version", "independent", 1, "ABAB")


@pytest.mark.parametrize("request_", [
    {"id": "A:inspect", "agent": "A", "kind": "inspect", "resource": "Q"},
    {"id": "A:release", "agent": "A", "kind": "release", "resource": "R"},
    {"id": "B:commit", "agent": "A", "kind": "commit", "resource": "R", "offer_version": 0, "offer_available": True},
    {"id": "A:commit", "agent": "A", "kind": "commit", "resource": "R", "offer_version": 0},
    {"id": "A:commit", "agent": "A", "kind": "commit", "resource": "R", "offer_version": "0", "offer_available": True},
    {"id": "C:inspect", "agent": "C", "kind": "inspect", "resource": "R"},
])
def test_invalid_message_unit_level(request_):
    c = sut.Coordinator("compare_version")
    with pytest.raises(ValueError):
        c.deliver(request_)
    assert c.snapshot() == {"version": 0, "allocations": {}, "issued_grants": {}}


def test_bonds_truth_tables_and_causal_filter():
    own, fw = explore.truth_table(explore.own_bonds), explore.truth_table(explore.framework_bonds())
    assert own == fw and own["sequential"] == [288, 108, 81, 54] and own["per_rule"] == {"two_each": 180, "causal_ready": 72, "preemption_cap": 84}
    assert own["rows"] == {t["id"]: {r: t[r] for r in explore.RULES} for t in DERIVED["raw_bond_truth"]}
    kept = {(c.split("|")[1], c.split("|")[3]) for c in own["kept"]}
    for p in sut.POLICIES:                                        # the causal filter never reads resource state
        assert {(c.split("|")[1], c.split("|")[3]) for c in own["kept"] if c.startswith(f"P={p}|")} == kept
    assert {w for m, w in kept if m == "M=after_A_offer"} == {"S=AABB", "S=ABAB", "S=ABBA"}


def test_oracle_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments)
                                                                        for a in n.args}
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any("policy" in n for n in names) and not literals & set(sut.POLICIES)


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"sut", "oracle", "runtime", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
