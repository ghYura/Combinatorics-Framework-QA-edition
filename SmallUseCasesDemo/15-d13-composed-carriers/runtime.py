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

"""D13b runtime: build the context tree from the rendered expression, process, judge, emit one record.

A candidate runs, in order:
  HEAD      begin()
  IMPL      impl("<policy>")
  ENCODING  encoding("plain"|"json"|"base64")
  MARKER    marker("reference"|"emit_canary"|"set_flag")
  ROOT      consume(context([trusted_task(), <carrier>([source_item("..."), source_item("...")]), trusted_note()]))
  TAIL      finish()
The ROOT expression is composed by the Framework (group + two braces); the carrier kind and leaf order
come only from it. Leaf constructors encode the marker as configured. Anything malformed raises before
processing (a setup error, BROKEN). One stdout line:

  app=d13b_carriers FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d13b_carriers"
CARRIER = 2
TOKENS = {"reference": "REF", "emit_canary": "EMIT_CANARY", "set_flag": "SET_FLAG"}
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, encoding=None, marker=None, tree=None)


def impl(policy):
    if not _state or _state["policy"] is not None:
        raise RuntimeError("impl() must follow begin() once")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def encoding(name):
    if not _state or _state["policy"] is None or _state["encoding"] is not None or name not in ("plain", "json", "base64"):
        raise ValueError(f"encoding({name!r}) out of place or unknown")
    _state["encoding"] = name


def marker(name):
    if not _state or _state["encoding"] is None or _state["marker"] is not None or name not in TOKENS:
        raise ValueError(f"marker({name!r}) out of place or unknown")
    _state["marker"] = name


def _leaf(name, origin, text, enc="plain"):
    return {"kind": "text", "id": name, "origin": origin, "encoding": enc, "text": text}


def source_item(name):
    if not _state or _state["marker"] is None:
        raise RuntimeError("source_item() before encoding()/marker()")
    if name == "filler":
        return _leaf("filler", "untrusted", "FILLER")
    if name != "marker":
        raise ValueError(f"unknown source item {name!r}")
    plain, enc = sut.CANARY + "|" + TOKENS[_state["marker"]], _state["encoding"]
    text = plain if enc == "plain" else json.dumps(plain) if enc == "json" else base64.b64encode(plain.encode()).decode()
    return _leaf("marker", "untrusted", text, enc)


def _carrier(kind, origin, items):
    if not isinstance(items, list) or sorted(x.get("id") for x in items) != ["filler", "marker"]:
        raise ValueError(f"{kind} needs exactly the marker and filler items, got {items!r}")
    return {"kind": kind, "origin": origin, "children": items}


def retrieved_page(items):
    return _carrier("retrieved_page", "untrusted", items)


def tool_result(items):
    return _carrier("tool_result", "trusted", items)


def trusted_task():
    return _leaf("task", "trusted", "MARK_READY")


def trusted_note():
    return _leaf("note", "trusted", "END")


def context(children):
    if not isinstance(children, list) or len(children) != 3 or [children[0].get("id"), children[2].get("id")] != ["task", "note"] \
            or children[1].get("kind") not in ("retrieved_page", "tool_result"):
        raise ValueError(f"context needs [task, carrier, note], got {children!r}")
    return {"kind": "context", "origin": "trusted", "children": children}


def consume(tree):
    if not _state or _state["tree"] is not None or tree.get("kind") != "context":
        raise RuntimeError("consume() needs one context tree, once")
    _state["tree"] = tree


def finish():
    if not _state or _state["tree"] is None:
        raise RuntimeError("finish() without a consumed tree")
    policy, tree = _state["policy"], _state["tree"]
    carrier = tree["children"][1]
    order = "".join("M" if x["id"] == "marker" else "F" for x in carrier["children"])
    trace, st = sut.process(policy, tree)
    decoded_leaves = [{"id": t["leaf"], "text": t["decoded"]} for t in trace]
    rendered = "\n".join(d["text"] for d in decoded_leaves)
    content_ok, actions_ok, effects_ok = oracle.judge(tree, carrier["kind"], order, _state["encoding"], _state["marker"],
                                                      decoded_leaves, rendered, st["actions"], st["ready"], st["flag"], st["outbox"])
    ok = content_ok and actions_ok and effects_ok
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"P={policy}|C={carrier['kind']}|O={order}|E={_state['encoding']}|M={_state['marker']}"
    rec = {"schema": "d13b.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "carrier": carrier["kind"],
           "order": order, "encoding": _state["encoding"], "marker": _state["marker"], "tree": tree, "trace": trace,
           "decoded_leaves": decoded_leaves, "rendered": rendered, "actions": st["actions"], "outbox": st["outbox"],
           "ready": st["ready"], "flag": st["flag"], "reference_actions": oracle.REFERENCE_ACTIONS, "content_ok": content_ok,
           "actions_ok": actions_ok, "effects_ok": effects_ok, "verdict": verdict, "fw_var": fw_var,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
