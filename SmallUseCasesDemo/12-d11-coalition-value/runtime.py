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

"""D11 runtime: rebuild one coalition from the rendered atoms, evaluate, compare, emit one record.

A candidate runs, in order:
  HEAD       begin()                  the empty coalition
  COALITION  enable("<player>") ...   zero to six calls, canonical order A..F, no repeats
  TAIL       finish()
An unknown, repeated or out-of-order player raises before the SUT runs (a setup error, BROKEN).
PASS needs the SUT's value and bonuses to equal the reference. COALITION position 2 is only the
legacy verdict carrier. One stdout line:

  app=d11_coalition FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d11_coalition"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(members=[], done=False)


def enable(player):
    if not _state or _state["done"]:
        raise RuntimeError("enable() must follow begin() and precede finish()")
    if player not in sut.PLAYERS or player in _state["members"] or (
            _state["members"] and sut.PLAYERS.index(player) < sut.PLAYERS.index(_state["members"][-1])):
        raise ValueError(f"player {player!r} unknown, repeated or out of canonical order")
    _state["members"].append(player)


def finish():
    if not _state or _state["done"]:
        raise RuntimeError("finish() without a started coalition")
    _state["done"] = True
    members = list(_state["members"])
    mask = "".join("1" if p in members else "0" for p in sut.PLAYERS)
    got = sut.evaluate(members)
    std, bonuses, value = oracle.expected([int(b) for b in mask])
    ok = (got["standalone_value"], got["interaction_bonuses"], got["value"]) == (std, bonuses, value)
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"C={mask}"
    rec = {"schema": "d11.observation/v1", "contract": "v1", "case_id": case, "mask": mask, "members": members, **got,
           "reference": {"standalone_value": std, "interaction_bonuses": bonuses, "value": value}, "oracle_agrees": ok,
           "verdict": verdict, "fw_var": fw_var, "carrier": "COALITION position 2 (legacy positional, not causal)",
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
