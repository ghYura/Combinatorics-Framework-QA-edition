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

"""D10 runtime: rebuild one sensor evaluation from the rendered atoms, read, compare, emit one record.

A candidate runs, in order:
  HEAD     begin()                 an empty selection
  SENSORS  select(<i>) ...         zero to eight calls, increasing index, no repeats
  FAULT    fault("Fxx")            one of the twelve campaign fault labels
  TAIL     finish()
An unknown, repeated or out-of-order sensor, or a label outside F01..F12 (the healthy H0 is a
declared DB-free control, not a campaign hypothesis), raises before the SUT runs: a setup error
(BROKEN). PASS needs the readings to equal the reference table. SENSORS position 2 is only the
legacy verdict carrier. One stdout line:

  app=d10_sensors FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>
"""
import base64
import hashlib
import json

import oracle
import sut

APP = "d10_sensors"
CARRIER = 2
LABELS = tuple(f"F{i:02}" for i in range(1, 13))
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(selected=[], fault=None)


def select(i):
    if not _state or _state["fault"] is not None:
        raise RuntimeError("select() must follow begin() and precede fault()")
    if i not in range(8) or i in _state["selected"] or (_state["selected"] and i < _state["selected"][-1]):
        raise ValueError(f"sensor {i!r} unknown, repeated or out of index order")
    _state["selected"].append(i)


def fault(label):
    if not _state or _state["fault"] is not None:
        raise RuntimeError("fault() must follow the selection once")
    if label not in LABELS:
        raise ValueError(f"{label!r} is not a campaign fault label (H0 is a declared control only)")
    _state["fault"] = label


def finish():
    if not _state or _state["fault"] is None:
        raise RuntimeError("finish() without a complete evaluation")
    sel, label = _state["selected"], _state["fault"]
    mask = "".join("1" if i in sel else "0" for i in range(8))
    latent, readings = sut.observe(label, sel)
    reference = oracle.expected_readings(label, sel)
    ok = readings == reference
    verdict = "PASS" if ok else "DOMAIN_FAIL"
    fw_var = 0 if ok else CARRIER
    case = f"S={mask}|H={label}"
    rec = {"schema": "d10.observation/v1", "contract": "v1", "case_id": case, "mask": mask, "selected": list(sel),
           "sensor_cost": len(sel), "fault": label, "latent_bits": latent, "readings": readings,
           "signature": "".join(map(str, readings)), "reference_readings": reference, "oracle_agrees": ok,
           "verdict": verdict, "fw_var": fw_var, "carrier": "SENSORS position 2 (legacy positional, not causal)",
           "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
