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

"""D13e runtime: rebuild the case from the rendered atoms, run 20 internal trials, emit one record.

A candidate runs, in order:
  HEAD   begin()                 a fresh case (after the inlined sources are checked)
  IMPL   impl("<policy>");
  TASK   task("<public|secret>");
  ORDER  set_order("<six chunks>");
  TAIL   finish()
Each of the 20 trials (0..19) resets the processor, folds the context, checks the trace with the
mechanical oracle and computes both judge readings from the trial's shared draw. The verdict is the
oracle's (all 20 decisions meet task truth); judge approvals are reported only. Anything malformed
raises, so the Executor records BROKEN (a setup error), never a domain verdict. One stdout line:

  app=d13e_context FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause. Framework repeat stays 1:
the trials are internal calls, not Framework repeats or distinct contexts.
"""
import base64
import hashlib
import json

import judge
import oracle
import processor

APP = "d13e_context"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, task=None, order=None)


def impl(policy):
    if not _state or _state["policy"] is not None:
        raise RuntimeError("impl() must follow begin() exactly once")
    if policy not in processor.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def task(name):
    if not _state or _state["policy"] is None or _state["task"] is not None:
        raise RuntimeError("task() must follow impl() exactly once")
    oracle.truth(name)                                   # raises on an unknown task
    _state["task"] = name


def set_order(order):
    if not _state or _state["task"] is None or _state["order"] is not None:
        raise RuntimeError("set_order() must follow task() exactly once")
    if not isinstance(order, str) or len(order) != 6 or sorted(order) != sorted(processor.CHUNKS):
        raise ValueError(f"context {order!r} must hold each of {processor.CHUNKS} exactly once")
    _state["order"] = order


def trials(policy, name, order):
    proc, guard = processor.ContextProcessor(policy), order.index("G") + 1
    out = []
    for t in range(oracle.TRIALS):
        proc.reset()
        decision, trace = proc.run(name, order)
        oracle.check_trace(order, trace, decision)
        ok = oracle.mechanical_ok(name, decision)
        draw_hex, n = judge.draw(policy, name, order, t)
        out.append({"trial": t, "draw_hex": draw_hex, "decision": decision, "context_trace": trace,
                    "mechanical_ok": ok, "judge_approvals": judge.approvals(ok, judge.flips(n, guard))})
    return out


def finish():
    if not _state or _state["order"] is None:
        raise RuntimeError("finish() before the case is complete")
    policy, name, order = _state["policy"], _state["task"], _state["order"]
    records = trials(policy, name, order)
    verdict, failing = oracle.verdict(name, records)
    fw_var = 0 if verdict == "PASS" else CARRIER
    guard = order.index("G") + 1
    case = f"P={policy}|T={name}|O={order}"
    rec = {"schema": "d13e.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "task": name,
           "order": order, "guard_position": guard, "band": judge.band(guard), "expected_decision": oracle.truth(name),
           "trials": records, "failing_trials": failing, "verdict": verdict, "fw_var": fw_var,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
