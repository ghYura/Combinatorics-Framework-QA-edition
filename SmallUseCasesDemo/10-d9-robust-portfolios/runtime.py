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

"""D9 runtime: rebuild one evaluation from the rendered atoms, compute, compare, emit one record.

A candidate runs, in order:
  HEAD        begin()                      an empty selection
  DESIGN      enable("<module>") ...       zero to six calls, canonical order, no repeats
  DEMAND      demand(<0..3>)
  DISRUPTION  disruption(<0..3>)
  TAIL        finish()
An unknown, repeated or out-of-order module, or a demand/disruption outside 0..3, raises before the
SUT runs (a setup error, BROKEN). PASS needs every SUT field to equal the independent reference.
DESIGN at position 2 is only the legacy verdict carrier. One stdout line:

  app=d9_portfolio FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d9_portfolio"
CARRIER = 2
FIELDS = ("fixed_cost", "gross_loss", "reductions", "raw_loss", "residual_loss", "total_cost")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(selected=[], demand=None, disruption=None)


def enable(module):
    if not _state or _state["demand"] is not None:
        raise RuntimeError("enable() must follow begin() and precede demand()")
    if module not in sut.MODULES or module in _state["selected"]:
        raise ValueError(f"unknown or repeated module {module!r}")
    if _state["selected"] and sut.MODULES.index(module) < sut.MODULES.index(_state["selected"][-1]):
        raise ValueError(f"module {module!r} out of canonical order")
    _state["selected"].append(module)


def demand(d):
    if not _state or _state["demand"] is not None:
        raise RuntimeError("demand() must follow the design once")
    if d not in (0, 1, 2, 3):
        raise ValueError(f"demand {d!r} outside 0..3")
    _state["demand"] = d


def disruption(x):
    if not _state or _state["demand"] is None or _state["disruption"] is not None:
        raise RuntimeError("disruption() must follow demand() once")
    if x not in (0, 1, 2, 3):
        raise ValueError(f"disruption {x!r} outside 0..3")
    _state["disruption"] = x


def finish():
    if not _state or _state["disruption"] is None:
        raise RuntimeError("finish() without a complete evaluation")
    sel, d, x = _state["selected"], _state["demand"], _state["disruption"]
    bits = "".join("1" if m in sel else "0" for m in sut.MODULES)
    got = sut.evaluate(sel, d, x)
    ref = oracle.expected([int(b) for b in bits], d, x)
    ok = all(got[f] == ref[f] for f in FIELDS)
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"P={bits}|D={d}|X={x}"
    rec = {"schema": "d9.observation/v1", "contract": "v1", "case_id": case, "design": bits, "selected": list(sel),
           "demand": d, "disruption": x, **got, "reference": ref, "mismatched_fields": [f for f in FIELDS if got[f] != ref[f]],
           "verdict": verdict, "fw_var": fw_var, "carrier": "DESIGN position 2 (legacy positional, not causal)",
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
