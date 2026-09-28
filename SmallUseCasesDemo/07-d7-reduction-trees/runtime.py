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

"""D7 runtime: take the rendered policy, vector and tree, evaluate, judge, emit one record.

A candidate runs, in order:
  HEAD   begin()
  IMPL   impl("<policy>")
  VECTOR vector("<id>", (<five binary64 hex strings>), {<policy>: ("<num>", "<den>"), ...})
  TREE   tree("<canonical bracketing>")
  TAIL   finish()
The tree string must parse to a full binary tree over leaves 0,1,2,3,4 in that order, each once, and
the environment must be binary64 (radix 2, 53-bit mantissa). Anything else raises before the SUT
runs, so the Executor records BROKEN (a setup error), never a numeric verdict. Floats are recorded
with float.hex(), rationals as decimal numerator/denominator strings. One stdout line:

  app=d7_trees FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json
import platform
import sys
from fractions import Fraction

import oracle
import sut

APP = "d7_trees"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, vector=None, tree=None)


def impl(policy):
    if not _state or _state["policy"] is not None or _state["vector"] or _state["tree"]:
        raise RuntimeError("impl() must follow begin() exactly once, first")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def vector(vid, input_hex, budgets):
    if not _state or _state["policy"] is None or _state["vector"] is not None or _state["tree"] is not None:
        raise RuntimeError("vector() must follow impl() once")
    if len(input_hex) != 5 or set(budgets) != set(sut.POLICIES):
        raise ValueError("a vector needs five hex inputs and a budget per policy")
    _state["vector"] = {"id": vid, "hex": list(input_hex), "budgets": {p: Fraction(int(n), int(d)) for p, (n, d) in budgets.items()}}


def parse_tree(text):
    """Parse '((0,1),2)'-style text into ints / [left, right]; raise on anything else."""
    pos = 0

    def node():
        nonlocal pos
        if pos < len(text) and text[pos].isdigit():
            start = pos
            while pos < len(text) and text[pos].isdigit():
                pos += 1
            return int(text[start:pos])
        if pos >= len(text) or text[pos] != "(":
            raise ValueError(f"malformed tree {text!r} at {pos}")
        pos += 1
        left = node()
        if pos >= len(text) or text[pos] != ",":
            raise ValueError(f"malformed tree {text!r} at {pos}")
        pos += 1
        right = node()
        if pos >= len(text) or text[pos] != ")":
            raise ValueError(f"malformed tree {text!r} at {pos}")
        pos += 1
        return [left, right]
    t = node()
    if pos != len(text):
        raise ValueError(f"trailing text in tree {text!r}")
    if sut.leaves(t) != [0, 1, 2, 3, 4]:
        raise ValueError(f"tree {text!r} does not hold leaves 0..4 once each, in order")
    if sut.canonical(t) != text:
        raise ValueError(f"tree {text!r} is not canonical")
    return t


def tree(text):
    if not _state or _state["vector"] is None or _state["tree"] is not None:
        raise RuntimeError("tree() must follow vector() once")
    _state["tree"] = (text, parse_tree(text))


def rat(q):
    q = Fraction(q)
    return {"n": str(q.numerator), "d": str(q.denominator)}


def show(v):
    return {"hex": v.hex()} if isinstance(v, float) else rat(v)


def finish():
    if not _state or _state["tree"] is None:
        raise RuntimeError("finish() without a complete case")
    if sys.float_info.radix != 2 or sys.float_info.mant_dig != 53:
        raise RuntimeError(f"unsupported floating-point environment: {sys.float_info}")
    policy, vec, (text, t) = _state["policy"], _state["vector"], _state["tree"]
    values = [float.fromhex(h) for h in vec["hex"]]
    result, nodes = sut.evaluate(policy, t, values)
    ref = oracle.reference(vec["hex"])
    budget = vec["budgets"][policy]
    err, finite, ok = oracle.judge(result, ref, budget)
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"{policy}|V={vec['id']}|T={text}"
    rec = {"schema": "d7.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "vector": vec["id"],
           "tree": text, "leaf_order": sut.leaves(t), "input_hex": vec["hex"], "result": show(result),
           "nodes": [{"node": n["node"], **show(n["value"])} for n in nodes], "reference": rat(ref),
           "absolute_error": rat(err) if err is not None else None, "finite": finite, "budget": rat(budget),
           "verdict": verdict, "fw_var": fw_var, "carrier": "IMPL position 2 (legacy positional, not causal)",
           "environment": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                           "float_radix": sys.float_info.radix, "float_mant_dig": sys.float_info.mant_dig},
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
