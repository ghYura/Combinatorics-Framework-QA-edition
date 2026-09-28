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

"""D8b runtime: rebuild the graph from the rendered atoms, build the cache, edit, update, judge, emit.

A candidate runs, in order:
  HEAD            begin()
  IMPL            impl("<policy>")
  EDGE_AB..EDGE_CD  edge("<u>","<v>",0|1)   six calls, in the fixed order AB, AC, AD, BC, BD, CD
  EDIT            edit("<node>")
  TAIL            finish()
A malformed or out-of-order edge, a non-binary bit or an unknown node raises before the SUT runs
(a setup error, BROKEN). PASS needs the initial cache to equal the fresh reference and the final
cache to equal the edited fresh reference at all four nodes. One stdout line:

  app=d8b_dag FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d8b_dag"
CARRIER = 2
IDS = "ABCD"
SLOTS = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
BASE = [1, 2, 4, 8]
DELTA = 10
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, bits=[], edit=None)


def impl(policy):
    if not _state or _state["policy"] is not None or _state["bits"] or _state["edit"] is not None:
        raise RuntimeError("impl() must follow begin() exactly once, first")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def edge(u, v, bit):
    if not _state or _state["policy"] is None or _state["edit"] is not None:
        raise RuntimeError("edge() must follow impl() and precede edit()")
    k = len(_state["bits"])
    if k >= 6 or (IDS.index(u) if u in IDS else -1, IDS.index(v) if v in IDS else -1) != SLOTS[k] or bit not in (0, 1):
        raise ValueError(f"edge({u!r},{v!r},{bit!r}) is not slot {k} of the fixed order AB,AC,AD,BC,BD,CD with a 0/1 bit")
    _state["bits"].append(bit)


def edit(node):
    if not _state or len(_state["bits"]) != 6 or _state["edit"] is not None:
        raise RuntimeError("edit() must follow all six edge() calls, once")
    if node not in IDS:
        raise ValueError(f"unknown node {node!r}")
    _state["edit"] = IDS.index(node)


def finish():
    if not _state or _state["edit"] is None:
        raise RuntimeError("finish() without a complete case")
    policy, bits, u = _state["policy"], _state["bits"], _state["edit"]
    edges = [e for e, b in zip(SLOTS, bits) if b]
    cache = sut.Cache(edges, BASE)
    before_values = list(cache.values)
    cache.edit(u, DELTA)
    post_edit = list(cache.values)
    dirty, order, updates = cache.update(policy, u)
    after_inputs = list(BASE)
    after_inputs[u] += DELTA
    before_ref = oracle.fresh(edges, BASE)
    reference = oracle.fresh(edges, after_inputs)
    paths = oracle.path_counts(edges)
    wrong = [IDS[v] for v in range(4) if cache.values[v] != reference[v]]
    ok = before_values == before_ref and not wrong
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"{policy}|G={''.join(map(str, bits))}|U={IDS[u]}"
    rec = {"schema": "d8b.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "bits": list(bits),
           "edges": [list(e) for e in edges], "edit": IDS[u], "before_inputs": list(BASE), "after_inputs": after_inputs,
           "before_values": before_values, "before_reference": before_ref, "post_edit_cache": post_edit,
           "path_counts": paths, "reference": reference, "expected_delta": [DELTA * paths[u][v] for v in range(4)],
           "affected": [IDS[v] for v in range(4) if paths[u][v]], "dirty": [IDS[v] for v in dirty],
           "evaluation_order": [IDS[v] for v in order], "updates": updates, "after_values": list(cache.values),
           "mismatched_nodes": wrong, "verdict": verdict, "fw_var": fw_var,
           "carrier": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
