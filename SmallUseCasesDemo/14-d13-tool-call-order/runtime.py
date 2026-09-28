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

"""D13a runtime: collect the rendered configuration and plan, run the orchestrator, judge, emit one record.

A candidate runs, in order:
  HEAD         begin()
  IMPL         impl("<policy>")
  REPETITIONS  repetitions(1|2)
  READ_MODE    read_mode(0|1)
  REVOKE       set_revoke(0..3)          optional; absent means no revocation
  ORDER        plan("A") plan("R") plan("S") in the generated order
  TAIL         finish()
set_revoke may appear anywhere before finish (it is configuration, applied at the declared cut). A
malformed plan or configuration raises before the orchestrator runs (a setup error, BROKEN). The
read stub's controlled error is caught inside the orchestrator and never escapes. PASS needs the
guarded responses and outbox and no unsafe emission. One stdout line:

  app=d13a_tools FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d13a_tools"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, repetitions=None, fail=None, cut=None, cut_set=False, plan=[])


def _need_impl(name):
    if not _state or _state["policy"] is None:
        raise RuntimeError(f"{name}() before impl()")


def impl(policy):
    if not _state or _state["policy"] is not None:
        raise RuntimeError("impl() must follow begin() once")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def repetitions(n):
    _need_impl("repetitions")
    if _state["repetitions"] is not None or n not in (1, 2):
        raise ValueError(f"repetitions({n!r}) repeated or outside 1..2")
    _state["repetitions"] = n


def read_mode(f):
    _need_impl("read_mode")
    if _state["fail"] is not None or f not in (0, 1):
        raise ValueError(f"read_mode({f!r}) repeated or not 0/1")
    _state["fail"] = f


def set_revoke(cut):
    _need_impl("set_revoke")
    if _state["cut_set"] or cut not in (0, 1, 2, 3):
        raise ValueError(f"set_revoke({cut!r}) repeated or outside 0..3")
    _state["cut"], _state["cut_set"] = cut, True


def plan(op):
    _need_impl("plan")
    if op not in "ARS" or op in _state["plan"] or len(op) != 1:
        raise ValueError(f"plan({op!r}) unknown or repeated")
    _state["plan"].append(op)


def finish():
    if not _state or _state["policy"] is None or _state["repetitions"] is None or _state["fail"] is None \
            or sorted(_state["plan"]) != ["A", "R", "S"]:
        raise RuntimeError("finish() without a complete configuration and plan")
    policy, order, n, fail, cut = _state["policy"], "".join(_state["plan"]), _state["repetitions"], _state["fail"], _state["cut"]
    orch = sut.Orchestrator(policy)
    orch.run(order, n, bool(fail), cut)
    ref_sends, ref_outbox = oracle.reference(order, n, cut)
    public = [{k: r[k] for k in ("request", "action", "payload")} for r in orch.send_results]
    viol = oracle.violations(orch.trace)
    decisions_ok, outbox_ok = public == ref_sends, orch.outbox == ref_outbox
    ok = decisions_ok and outbox_ok and not viol
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"P={policy}|O={order}|N={n}|F={fail}|X={'none' if cut is None else cut}"
    rec = {"schema": "d13a.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "order": order,
           "send_repetitions": n, "fail_read": bool(fail), "revoke_cut": cut, "trace": orch.trace,
           "send_results": orch.send_results, "outbox": orch.outbox, "final_state": dict(orch.state),
           "reference_sends": ref_sends, "reference_outbox": ref_outbox, "decisions_ok": decisions_ok, "outbox_ok": outbox_ok,
           "violations": viol, "verdict": verdict, "fw_var": fw_var, "carrier": "IMPL position 2 (legacy positional, not causal)",
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
