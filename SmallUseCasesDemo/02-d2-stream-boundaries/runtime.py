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

"""D2 runtime: segment one frozen payload, decode it with one adapter, judge, emit a record.

A candidate assigns IMPL, PAYLOAD, ERRORS and CUT1..CUT5, then calls `emit`. CUTi=1 cuts
after byte i; the real cuts give nonempty chunks whose concatenation is the payload. A cut
at or beyond the payload length is outside the contract and raises (the Executor records
BROKEN, never a domain verdict). One stdout line carries the full record:

  app=d2_stream FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> class=<...>
      rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json
import sys

import oracle
import sut

APP = "d2_stream"
CARRIER = 2
# Frozen from architect-derived.json (bytes as hex; no platform encoding involved).
PAYLOADS = {
    "ascii": {"encoding": "utf-8", "hex": "414243", "literal_text": "ABC", "truncated": False},
    "euro": {"encoding": "utf-8", "hex": "41e282ac42", "literal_text": "A€B", "truncated": False},
    "emoji": {"encoding": "utf-8", "hex": "f09f9982", "literal_text": "\U0001f642", "truncated": False},
    "truncated_utf8": {"encoding": "utf-8", "hex": "41e282", "literal_text": "A�", "truncated": True},
    "bom_utf16": {"encoding": "utf-16", "hex": "fffe4100a903", "literal_text": "AΩ", "truncated": False},
    "truncated_utf16": {"encoding": "utf-16", "hex": "fffe410042", "literal_text": "A�", "truncated": True},
}
ERRORS = ("strict", "replace")
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources


def case_id(adapter, payload_id, errors, mask):
    return "%s|P=%s|E=%s|M=%02x" % (adapter, payload_id, errors, mask)


def segment(data, bits):
    """Chunks for cut bits (bits[0] = CUT1: a cut after byte 1)."""
    cuts = [i + 1 for i, b in enumerate(bits) if b]
    if any(c >= len(data) for c in cuts):
        raise ValueError("cut at or beyond the payload end: %r for %d bytes" % (cuts, len(data)))
    edges = [0] + cuts + [len(data)]
    chunks = [data[a:b] for a, b in zip(edges, edges[1:])]
    if b"".join(chunks) != data or not all(chunks):
        raise ValueError("segmentation does not reproduce the payload with nonempty chunks")
    return chunks


def run_case(adapter, payload_id, errors, bits):
    if adapter not in sut.ADAPTERS or payload_id not in PAYLOADS or errors not in ERRORS:
        raise ValueError("outside the contract: %r %r %r" % (adapter, payload_id, errors))
    if len(bits) != 5 or any(b not in (0, 1) for b in bits):
        raise ValueError("five cut bits required: %r" % (bits,))
    payload = PAYLOADS[payload_id]
    data = bytes.fromhex(payload["hex"])
    chunks = segment(data, bits)
    ref = oracle.reference(payload, errors)
    observed = oracle.outcome(lambda: sut.decode(adapter, chunks, payload["encoding"], errors))
    cls = oracle.classify(ref, observed)       # adapter-blind: reference vs observed only
    fw_var = 0 if cls == "none" else CARRIER
    mask = sum(b << i for i, b in enumerate(bits))
    return {"schema": "d2.observation/v1", "contract": "v1",
            "case_id": case_id(adapter, payload_id, errors, mask), "adapter": adapter,
            "payload": payload_id, "payload_hex": payload["hex"], "encoding": payload["encoding"],
            "errors": errors, "bits": list(bits), "mask": "%02x" % mask,
            "chunks_hex": [c.hex() for c in chunks], "reference": ref, "observed": observed,
            "failure_class": cls, "verdict": "PASS" if fw_var == 0 else "DOMAIN_FAIL",
            "fw_var": fw_var, "carrier": "IMPL position 2 (legacy positional, not causal)",
            "python": sys.version.split()[0], "source_sha256": dict(SOURCE_SHA256)}


def emit(adapter, payload_id, errors, bits):
    rec = run_case(adapter, payload_id, errors, bits)
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % rec["fw_var"], "case=%s" % rec["case_id"],
                    "verdict=%s" % rec["verdict"], "class=%s" % rec["failure_class"],
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return rec["fw_var"]
