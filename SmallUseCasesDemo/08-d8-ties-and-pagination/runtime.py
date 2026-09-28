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

"""D8a runtime: rebuild the case from the rendered atoms, run the request loop, judge, emit one record.

A candidate runs, in order:
  HEAD      begin()
  IMPL      impl("<policy>")
  RANKS     ranks("<four rank digits>")
  DIRECTION direction("asc"|"desc")
  TAIL      finish()
The runtime owns the loop: requests 0,1,2 at most, stopping at the first empty page (recorded);
no hidden request, retry, deduplication, repair or fallback. A malformed rank vector raises before
the SUT runs (a setup error, BROKEN). PASS needs the exact stable output, termination within the
bound, every obligation and lawful comparators. One stdout line:

  app=d8a_pagination FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d8a_pagination"
CARRIER = 2
MAX_REQUESTS = 3
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(policy=None, ranks=None, direction=None)


def impl(policy):
    if not _state or any(_state[k] is not None for k in ("policy", "ranks", "direction")):
        raise RuntimeError("impl() must follow begin() exactly once, first")
    if policy not in sut.POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    _state["policy"] = policy


def ranks(code):
    if not _state or _state["policy"] is None or _state["ranks"] is not None or _state["direction"] is not None:
        raise RuntimeError("ranks() must follow impl() once")
    r = [int(c) for c in code] if isinstance(code, str) and code.isdigit() else None
    if r is None or len(r) != 4 or set(r) != set(range(max(r) + 1)):
        raise ValueError(f"malformed rank vector {code!r}: need four ranks using exactly 0..max")
    _state["ranks"] = r


def direction(d):
    if not _state or _state["ranks"] is None or _state["direction"] is not None:
        raise RuntimeError("direction() must follow ranks() once")
    if d not in ("asc", "desc"):
        raise ValueError(f"unknown direction {d!r}")
    _state["direction"] = d


def finish():
    if not _state or _state["direction"] is None:
        raise RuntimeError("finish() without a complete case")
    policy, r, d = _state["policy"], _state["ranks"], _state["direction"]
    pages, collected, cursor = [], [], None
    for request in range(MAX_REQUESTS):
        order, matrix, chosen, cursor_out, offset = sut.page(policy, r, d, request, cursor)
        ids = [sut.IDS[i] for i in chosen]
        pages.append({"request": request, "cursor_in": list(cursor) if cursor is not None else None, "offset": offset,
                      "full_order": [sut.IDS[i] for i in order], "comparisons": matrix, "ids": ids, "cursor_out": cursor_out})
        collected.extend(ids)
        if not ids:
            break
        cursor = cursor_out
    expected = oracle.expected_order(r, d)
    obl = oracle.obligations(r, d, collected, not pages[-1]["ids"])
    laws = [oracle.comparator_laws(p["comparisons"], r, d) for p in pages]
    lawful = all(all(x.values()) for x in laws)
    ok = collected == expected and obl["terminated"] and all(obl.values()) and lawful
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"{policy}|D={d}|R={''.join(map(str, r))}"
    rec = {"schema": "d8a.observation/v1", "contract": "v1", "case_id": case, "policy": policy, "direction": d, "ranks": r,
           "input_ids": list(sut.IDS), "page_size": sut.PAGE_SIZE, "pages": pages, "collected": collected, "expected": expected,
           **obl, "comparator_laws": laws, "comparators_lawful": lawful, "verdict": verdict, "fw_var": fw_var,
           "carrier": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
