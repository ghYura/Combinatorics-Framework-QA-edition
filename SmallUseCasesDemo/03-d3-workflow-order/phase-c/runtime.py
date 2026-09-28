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

"""D3 phase C runtime: six observed events per candidate, then one record line.

start("<policy>"), then step(X) for each of C, F, N, Q, S, V once, then finish("C"). Each step
applies the event and checks the whole snapshot before the next step runs; checkpoint k
(1-based) follows the k-th event. All failures are kept. Invalid calls raise (BROKEN).

  app=d3c_coverage FW_VAR=<0|2> case=<id> verdict=<...> final_only=<...> rec=<b64 JSON> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d3c_coverage"
CARRIER = 2
SOURCE_SHA256 = {}
_state = {}


def start(policy):
    if _state:
        raise RuntimeError("start() called twice in one candidate")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state.update(policy=policy, service=sut.Service(policy, sut.Durable()), reference=oracle.initial(),
                  ops=[], checkpoints=[])


def step(op):
    if not _state:
        raise RuntimeError("step() before start()")
    _state["service"] = _state["service"].apply(op)
    observed = _state["service"].snapshot()
    _state["reference"] = oracle.transition(_state["reference"], op)
    _state["ops"].append(op)
    _state["checkpoints"].append({"index": len(_state["checkpoints"]) + 1, "op": op, "observed": observed,
                                  "reference": dict(_state["reference"]),
                                  **oracle.check(observed, _state["reference"])})


def finish(phase):
    if phase != "C" or not _state:
        raise RuntimeError(f"finish({phase!r}) without a started phase-C case")
    ops, cps = _state["ops"], _state["checkpoints"]
    if sorted(ops) != sorted("CFNQSV"):
        raise ValueError(f"not a permutation of CFNQSV: {ops}")
    failing = [c["index"] for c in cps if not c["ok"]]
    final_ok = cps[-1]["ok"]
    fw_var = 0 if not failing else CARRIER
    rec = {"schema": "d3c.observation/v1", "contract": "phase-c", "case_id": f"C|{_state['policy']}|OPS={''.join(ops)}",
           "policy": _state["policy"], "ops": ops, "checkpoints": cps, "failing_checkpoints": failing,
           "verdict": "PASS" if not failing else "DOMAIN_FAIL",
           "final_only_verdict": "PASS" if final_ok else "DOMAIN_FAIL",
           "hidden_by_final_only": bool(failing) and final_ok, "fw_var": fw_var,
           "carrier": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % rec["case_id"], "verdict=%s" % rec["verdict"],
                    "final_only=%s" % rec["final_only_verdict"], "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
