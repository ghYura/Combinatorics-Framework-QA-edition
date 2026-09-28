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

"""D13d runtime: rebuild the case from the rendered atoms, drive three requests, judge, emit one record.

A candidate runs, in order:
  HEAD      begin()                 a fresh case (after the inlined sources are checked)
  IMPL      impl("<policy>");
  WRITE_AT  write_at(1|2);
  U1..U3    user_at(<i>,<label>);
  S1..S3    session_at(<i>,<label>);
  R12, R23  reset_cut(1,<bit>); reset_cut(2,<bit>);
  TAIL      finish()
Each label triple must be a canonical restricted-growth string (000, 001, 010, 011, 012) and every
atom must arrive in this order. The harness owns the logical epoch (it increases at each cut even if
an adapter keeps its entries). Anything malformed raises, so the Executor records BROKEN (a setup
error), never a domain verdict. One stdout line:

  app=d13d_memory FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d13d_memory"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, write_at=None, users=[], sessions=[], cuts=[])


def impl(policy):
    if not _state or _state["policy"] is not None:
        raise RuntimeError("impl() must follow begin() exactly once")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def write_at(index):
    if not _state or _state["policy"] is None or _state["write_at"] is not None:
        raise RuntimeError("write_at() must follow impl() once")
    if type(index) is not int or index not in (1, 2):
        raise ValueError(f"write position {index!r} outside the contract")
    _state["write_at"] = index


def _label(seq, i, label, what):
    if i != len(seq) + 1 or i > 3 or type(label) is not int:
        raise ValueError(f"{what}_at({i},{label!r}) out of order after {len(seq)} labels")
    if label < 0 or label > (max(seq) + 1 if seq else 0):
        raise ValueError(f"{what}_at({i},{label}) breaks the canonical restricted-growth string {seq}")
    seq.append(label)


def user_at(i, label):
    if not _state or _state["write_at"] is None or _state["sessions"]:
        raise RuntimeError("user_at() must follow write_at(), before the sessions")
    _label(_state["users"], i, label, "user")


def session_at(i, label):
    if not _state or len(_state["users"]) != 3 or _state["cuts"]:
        raise RuntimeError("session_at() must follow the three users, before the cuts")
    _label(_state["sessions"], i, label, "session")


def reset_cut(c, bit):
    if not _state or len(_state["sessions"]) != 3:
        raise RuntimeError("reset_cut() must follow the three sessions")
    if c != len(_state["cuts"]) + 1 or c > 2 or bit not in (0, 1) or type(bit) is not int:
        raise ValueError(f"reset_cut({c},{bit!r}) out of order or not a bit")
    _state["cuts"].append(bit)


def _run(policy, users, sessions, cuts, w):
    adapter, epoch, trace = sut.MemoryAdapter(policy), 0, []
    for i in (1, 2, 3):
        user, session = users[i - 1], sessions[i - 1]
        cut = i > 1 and cuts[i - 2] == 1
        if cut:
            epoch += 1                                   # the harness's logical epoch
            adapter.reset()
        if i == w:
            adapter.write(user, session, epoch, i, f"D13D_CANARY_R{i}")
            op, reply, calls = "write", "STORED", []
        else:
            op, reply = "read", adapter.read(user, session)
            calls = [{"name": "draft", "argument": reply}] if reply is not None else []
        trace.append({"request_index": i, "user": user, "session": session, "operation": op, "reset_before": cut,
                      "epoch": epoch, "storage_key": list(adapter.key(user, session)), "reply": reply,
                      "tool_calls": calls, "memory": adapter.snapshot()})
    return trace


def finish():
    if not _state or len(_state["cuts"]) != 2:
        raise RuntimeError("finish() before the case is complete")
    policy, w = _state["policy"], _state["write_at"]
    users = "".join(map(str, _state["users"]))
    sessions = "".join(map(str, _state["sessions"]))
    cuts = "".join(map(str, _state["cuts"]))
    observed = _run(policy, _state["users"], _state["sessions"], _state["cuts"], w)
    reference = oracle.reference_trace(users, sessions, cuts, w)
    j = oracle.judge(observed, reference, users, sessions, cuts, w)
    failing = j["failing_checkpoints"]
    verdict = "PASS" if not failing else "DOMAIN_FAIL"
    fw_var = 0 if not failing else CARRIER
    case = f"P={policy}|U={users}|S={sessions}|X={cuts}|W={w}"
    rec = {"schema": "d13d.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "users": users,
           "sessions": sessions, "cuts": cuts, "write_at": w, "observed_trace": observed, "reference_trace": reference,
           "owner": j["owner"], "checks": j["checks"], "leaks": j["leaks"], "leak_occurrences": j["leak_occurrences"],
           "failing_checkpoints": failing, "verdict": verdict, "fw_var": fw_var,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
