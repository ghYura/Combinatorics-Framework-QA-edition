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

"""D3 runtime: run one candidate's operations, observing every step, then emit one record.

A candidate calls start("<policy>"), then step("C"|"F"|"N"|"S"|"Q") once per operation, then
finish("<phase>"). Each step applies the operation to the SUT and, before the next step runs,
copies the full public snapshot and checks it against the reference. All failures are kept;
checkpoint k (1-based) is the state after the k-th operation.
Invalid calls raise, so the Executor records BROKEN, never a domain verdict. One stdout line:

  app=d3_workflow FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> final_only=<PASS|DOMAIN_FAIL>
      rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d3_workflow"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def start(policy):
    if _state:
        raise RuntimeError("start() called twice in one candidate")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state.update(policy=policy, service=sut.Service(policy, sut.Ledger()), reference=oracle.initial(),
                  ops=[], checkpoints=[])


def step(op):
    if not _state:
        raise RuntimeError("step() before start()")
    _state["service"] = _state["service"].apply(op)
    observed = _state["service"].snapshot()                # observed before the next step executes
    _state["reference"] = oracle.transition(_state["reference"], op)
    result = oracle.check(observed, _state["reference"])
    _state["ops"].append(op)
    _state["checkpoints"].append({"index": len(_state["checkpoints"]) + 1, "op": op, "observed": observed,
                                  "reference": dict(_state["reference"]), **result})


def case_id(phase, policy, ops):
    core = [o for o in ops if o in "CFN"]
    return "%s|%s|OPS=%s|S=%d|Q=%d" % (phase, policy, "".join(core), "S" in ops, "Q" in ops)


def finish(phase):
    if phase not in ("A", "B") or not _state:
        raise RuntimeError(f"finish({phase!r}) without a started case")
    ops, cps = _state["ops"], _state["checkpoints"]
    core = [o for o in ops if o in "CFN"]
    tail = [o for o in ops if o in "SQ"]
    if len(core) != 3 or ops[:3] != core or tail not in ([], ["S"], ["Q"], ["S", "Q"]) \
            or (phase == "B" and tail):
        raise ValueError(f"operation sequence outside the contract: {ops}")
    failing = [c["index"] for c in cps if not c["ok"]]
    final_ok = cps[-1]["ok"]
    fw_var = 0 if not failing else CARRIER
    rec = {"schema": "d3.observation/v1", "contract": "v1", "case_id": case_id(phase, _state["policy"], ops),
           "phase": phase, "policy": _state["policy"], "ops": ops, "S": int("S" in ops), "Q": int("Q" in ops),
           "checkpoints": cps, "failing_checkpoints": failing,
           "verdict": "PASS" if not failing else "DOMAIN_FAIL",
           "final_only_verdict": "PASS" if final_ok else "DOMAIN_FAIL",
           "hidden_by_final_only": bool(failing) and final_ok,
           "fw_var": fw_var, "carrier": "IMPL position 2 (legacy positional, not causal)",
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % rec["case_id"], "verdict=%s" % rec["verdict"],
                    "final_only=%s" % rec["final_only_verdict"],
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
