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

"""D5 phase A runtime: build one pipeline tree from the rendered fragments, run it, emit one record.

A candidate runs its fragments in decoded row order:
  HEAD   begin()                                   a fresh tree builder (after the inlined sources are checked)
  IMPL   impl("<policy>")                          the adapter policy under test
  OPS    push_op("<op1>") push_op("<op2>") bind("<field>")
                                                   two opcodes, then the field that closes the pipeline
  TAIL   finish("A")                               validate, run SUT and reference, emit the record
Any fragment out of place raises, so the Executor records BROKEN, never a domain verdict.
One stdout line:

  app=d5a_pipeline FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d5a_pipeline"
CARRIER = 2
INPUT = {"x": 2, "y": 5}
OPS = ("A", "M", "S", "N")
FIELDS = ("x", "y")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, ops=[], field=None, fragments=[])


def impl(policy):
    if not _state or _state["policy"] is not None or _state["fragments"]:
        raise RuntimeError("impl() must follow begin() exactly once, before any operation")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def push_op(op):
    if not _state or _state["policy"] is None:
        raise RuntimeError("push_op() before impl()")
    if op not in OPS:
        raise ValueError(f"unknown operation {op!r}")
    if _state["field"] is not None or len(_state["ops"]) >= 2:
        raise RuntimeError(f"push_op({op!r}) after the pipeline has two operations or is bound")
    _state["ops"].append(op)
    _state["fragments"].append(["push_op", op])


def bind(field):
    if not _state or _state["policy"] is None:
        raise RuntimeError("bind() before impl()")
    if field not in FIELDS:
        raise ValueError(f"unknown field {field!r}")
    if _state["field"] is not None or len(_state["ops"]) != 2:
        raise RuntimeError(f"bind({field!r}) needs exactly two operations and an unbound pipeline; have {_state['ops']}")
    _state["field"] = field
    _state["fragments"].append(["bind", field])


def case_id(phase, policy, tree):
    return "%s|%s|OPS=%s|FIELD=%s" % (phase, policy, "".join(tree["ops"]), tree["field"])


def finish(phase):
    if phase != "A" or not _state or _state["policy"] is None:
        raise RuntimeError(f"finish({phase!r}) without a started case")
    ops, field = _state["ops"], _state["field"]
    if field is None or len(ops) != 2 or ops[0] == ops[1] or [f[0] for f in _state["fragments"]] != ["push_op", "push_op", "bind"]:
        raise ValueError(f"malformed tree: ops={ops} field={field} fragments={_state['fragments']}")
    tree = {"field": field, "ops": list(ops)}
    observed, sut_trace = sut.adapt(dict(INPUT), tree, _state["policy"])
    expected, ref_trace = oracle.evaluate(dict(INPUT), tree)
    ok = oracle.same_record(observed, expected)
    fw_var = 0 if ok else CARRIER
    rec = {"schema": "d5a.observation/v1", "contract": "A", "case_id": case_id(phase, _state["policy"], tree),
           "phase": phase, "policy": _state["policy"], "tree": tree, "fragments": _state["fragments"],
           "input": dict(INPUT), "expected": expected, "observed": observed,
           "sut_trace": sut_trace, "reference_trace": ref_trace, "traces_equal": sut_trace == ref_trace,
           "verdict": "PASS" if ok else "DOMAIN_FAIL", "fw_var": fw_var,
           "carrier": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % rec["case_id"], "verdict=%s" % rec["verdict"],
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
