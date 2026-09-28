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

"""D5 phase B runtime: a stack-based tree builder fed by the rendered fragments, then one record.

A candidate runs its fragments in decoded row order:
  HEAD   begin()                        a fresh builder (after the inlined sources are checked)
  IMPL   impl("<policy>")
  ROOT   begin_pipeline() open_scope("x") ... op("A") ... close_scope() ... end_pipeline()
  or BUNDLE  begin_bundle() <eight pipelines> seal_bundle() end_bundle()
  TAIL   finish("B1"|"B2")              evaluate every tree on a fresh record, emit the record
poison_tmp() is the rewrite marker that must never reach a candidate. Any fragment out of place
raises, so the Executor records BROKEN, never a domain verdict. One stdout line:

  app=d5b_scopes FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d5b_scopes"
CARRIER = 2
INPUT = {"x": 2, "y": 5}
OPS = ("A", "M", "S", "N")
FIELDS = ("x", "y")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def _need(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def begin():
    _need(not _state, "begin() called twice in one candidate")
    _state.update(policy=None, stack=None, trees=[], fragments=[], bundle=None)


def impl(policy):
    _need(_state and _state["policy"] is None and not _state["fragments"], "impl() must follow begin() once, first")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def _log(*call):
    _need(_state and _state["policy"] is not None, f"{call[0]}() before impl()")
    _state["fragments"].append(list(call))


def begin_bundle():
    _log("begin_bundle")
    _need(_state["bundle"] is None and _state["stack"] is None and not _state["trees"], "begin_bundle() out of place")
    _state["bundle"] = "open"


def seal_bundle():
    _log("seal_bundle")
    _need(_state["bundle"] == "open" and _state["stack"] is None and _state["trees"], "seal_bundle() out of place")
    _state["bundle"] = "sealed"


def end_bundle():
    _log("end_bundle")
    _need(_state["bundle"] == "sealed", "end_bundle() before seal_bundle()")
    _state["bundle"] = "closed"


def begin_pipeline():
    _log("begin_pipeline")
    _need(_state["stack"] is None and _state["bundle"] in (None, "open"), "begin_pipeline() inside an open pipeline or a sealed bundle")
    _need(_state["bundle"] == "open" or not _state["trees"], "a second pipeline outside a bundle")
    _state["stack"] = [[]]


def open_scope(field):
    _log("open_scope", field)
    _need(_state["stack"] is not None, "open_scope() outside a pipeline")
    if field not in FIELDS:
        raise ValueError(f"unknown field {field!r}")
    node = {"scope": field, "children": []}
    _state["stack"][-1].append(node)
    _state["stack"].append(node["children"])


def op(code):
    _log("op", code)
    _need(_state["stack"] is not None, "op() outside a pipeline")
    if code not in OPS:
        raise ValueError(f"unknown operation {code!r}")
    _state["stack"][-1].append(code)


def close_scope():
    _log("close_scope")
    _need(_state["stack"] is not None and len(_state["stack"]) > 1, "close_scope() without an open scope")
    _state["stack"].pop()


def end_pipeline():
    _log("end_pipeline")
    _need(_state["stack"] is not None and len(_state["stack"]) == 1, "end_pipeline() with an open scope or no pipeline")
    _state["trees"].append(_state["stack"][0])
    _state["stack"] = None


def poison_tmp():
    raise RuntimeError("the TMP rewrite marker reached a candidate")


def tree_id(tree):
    """ZIP=z|CAT=c|TAIL=t for the contract's shape Sequence(Scope(x,[Scope(y,[z,N])]), S, Scope(x,[c]), t)."""
    try:
        outer, s, cat, t = tree
        (inner,) = outer["children"]
        z, n = inner["children"]
        (c,) = cat["children"]
        ok = (outer["scope"], inner["scope"], n, s, cat["scope"]) == ("x", "y", "N", "S", "x") \
            and z in ("A", "M") and c in ("A", "M") and t in ("N", "S")
    except (TypeError, ValueError, KeyError):
        ok = False
    if not ok:
        raise ValueError(f"tree outside the contract's shape: {tree}")
    return f"ZIP={z}|CAT={c}|TAIL={t}"


def _evaluate(tree):
    observed, sut_trace = sut.evaluate(tree, _state["policy"])
    expected, ref_trace = oracle.evaluate(tree)
    ok = oracle.same_record(observed, expected)
    return {"tree_id": tree_id(tree), "tree": tree, "input": dict(INPUT), "expected": expected, "observed": observed,
            "sut_trace": sut_trace, "reference_trace": ref_trace, "verdict": "PASS" if ok else "DOMAIN_FAIL"}


def finish(phase):
    _need(_state and _state["policy"] is not None and _state["stack"] is None, f"finish({phase!r}) with an open pipeline")
    policy, trees = _state["policy"], _state["trees"]
    if phase == "B1":
        _need(_state["bundle"] is None and len(trees) == 1, "B1 needs exactly one pipeline and no bundle")
        result = _evaluate(trees[0])
        case, verdict, body = f"B1|{policy}|{result['tree_id']}", result["verdict"], {"result": result}
    elif phase == "B2":
        _need(_state["bundle"] == "closed" and len(trees) == 8, f"B2 needs one closed bundle of 8 trees; have {len(trees)}")
        results = [_evaluate(t) for t in trees]
        if len({r["tree_id"] for r in results}) != 8:
            raise ValueError("the bundle does not hold eight distinct trees")
        verdict = "PASS" if all(r["verdict"] == "PASS" for r in results) else "DOMAIN_FAIL"
        case = f"B2|{policy}|BUNDLE=all8"
        body = {"generation_order": [r["tree_id"] for r in results],
                "results": {r["tree_id"]: r for r in results},
                "failing_trees": sorted(r["tree_id"] for r in results if r["verdict"] != "PASS")}
    else:
        raise RuntimeError(f"unknown phase {phase!r}")
    fw_var = 0 if verdict == "PASS" else CARRIER
    rec = {"schema": "d5b.observation/v1", "contract": "B", "case_id": case, "phase": phase, "policy": policy,
           "fragments": _state["fragments"], **body, "verdict": verdict, "fw_var": fw_var,
           "carrier": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
