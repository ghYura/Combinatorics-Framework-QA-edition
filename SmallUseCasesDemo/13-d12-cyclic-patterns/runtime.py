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

"""D12 runtime: rebuild one word from the rendered atoms, evaluate, compare, emit one record.

A candidate runs, in order:
  HEAD      begin()
  words:    place(0,"X") ... place(5,"X")   one letter per explicit position, in order
  classes:  pattern("XXXXXX")               one complete canonical representative
  TAIL      finish("words"|"classes")
A missing, repeated or out-of-order position, a letter outside A,B,C, or a non-canonical classes
pattern raises before the SUT runs (a setup error, BROKEN). PASS needs every SUT field to equal the
reference. The second mandatory slot is only the legacy verdict carrier. One stdout line:

  app=d12_cyclic FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d12_cyclic"
CARRIER = 2
COMPARED = ("counts", "edge_counts", "transition_cost", "balance_penalty", "total_cost", "representative", "orbit_size",
            "period", "stabilizer_size")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(letters=[], pattern=None)


def place(i, letter):
    if not _state or _state["pattern"] is not None:
        raise RuntimeError("place() must follow begin() and cannot mix with pattern()")
    if i != len(_state["letters"]) or i > 5 or letter not in sut.ALPHABET:
        raise ValueError(f"place({i!r},{letter!r}) out of order or outside A,B,C")
    _state["letters"].append(letter)


def pattern(word):
    if not _state or _state["letters"] or _state["pattern"] is not None:
        raise RuntimeError("pattern() must follow begin() once, without place()")
    if not isinstance(word, str) or len(word) != 6 or set(word) - set(sut.ALPHABET):
        raise ValueError(f"malformed pattern {word!r}")
    if min(word[k:] + word[:k] for k in range(6)) != word:
        raise ValueError(f"pattern {word!r} is not a canonical rotation representative")
    _state["pattern"] = word


def finish(campaign):
    if not _state:
        raise RuntimeError("finish() without begin()")
    if campaign == "words":
        if _state["pattern"] is not None or len(_state["letters"]) != 6:
            raise ValueError("a words case needs exactly six place() calls")
        word = "".join(_state["letters"])
    elif campaign == "classes":
        if _state["pattern"] is None:
            raise ValueError("a classes case needs pattern()")
        word = _state["pattern"]
    else:
        raise RuntimeError(f"unknown campaign {campaign!r}")
    got = sut.evaluate(word)
    ref = oracle.expected(word)
    mismatched = [k for k in COMPARED if got[k] != ref[k]]
    ok = not mismatched
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"W={word}"
    rec = {"schema": "d12.observation/v1", "contract": "v1", "campaign": campaign, "case_id": case, "word": word, **got,
           "reference": ref, "mismatched_fields": mismatched, "oracle_agrees": ok, "verdict": verdict, "fw_var": fw_var,
           "carrier": "second mandatory slot (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
