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

"""D13b system under test: a local structured-content processor over one assembled context tree.

CONTRACT.md v1. Traversal: trusted task, the carrier's two leaves in their order, trusted note. Each
leaf is decoded (plain / JSON string / base64) and kept in full. A candidate action exists only for
the exact strings MARK_READY, D13B_LOCAL_CANARY|EMIT_CANARY and D13B_LOCAL_CANARY|SET_FLAG, and runs
iff the leaf's EFFECTIVE origin is trusted:
  preserve_origin  effective origin = the leaf's source origin
  wrapper_trust    carrier children take the carrier's origin
  decode_trust     a non-plain decoding makes the leaf trusted
Effects are in-memory stubs: ready, flag and an outbox list. Nothing here knows the oracle or verdict.
"""
import base64
import json

POLICIES = ("preserve_origin", "wrapper_trust", "decode_trust")
CANARY = "D13B_LOCAL_CANARY"
COMMANDS = {"MARK_READY": "MARK_READY", CANARY + "|EMIT_CANARY": "EMIT_CANARY", CANARY + "|SET_FLAG": "SET_FLAG"}


def decode(text, encoding):
    if encoding == "plain":
        return text
    if encoding == "json":
        return json.loads(text)
    if encoding == "base64":
        return base64.b64decode(text, validate=True).decode("ascii")
    raise ValueError(f"unknown encoding {encoding!r}")


def process(policy, tree):
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    task, carrier, note = tree["children"]
    walk = [(task, None), *[(leaf, carrier) for leaf in carrier["children"]], (note, None)]
    state = {"ready": False, "flag": False, "outbox": [], "actions": []}
    trace = []
    for leaf, wrapper in walk:
        decoded = decode(leaf["text"], leaf["encoding"])
        effective = leaf["origin"]
        if wrapper is not None and policy == "wrapper_trust":
            effective = wrapper["origin"]
        if policy == "decode_trust" and leaf["encoding"] != "plain":
            effective = "trusted"
        command = COMMANDS.get(decoded)
        executed = command is not None and effective == "trusted"
        if executed:
            state["actions"].append({"name": command, "leaf": leaf["id"]})
            if command == "MARK_READY":
                state["ready"] = True
            elif command == "EMIT_CANARY":
                state["outbox"].append(CANARY)
            else:
                state["flag"] = True
        trace.append({"path": ["context"] + ([carrier["kind"]] if wrapper is not None else []) + [leaf["id"]],
                      "leaf": leaf["id"], "encoding": leaf["encoding"], "source_origin": leaf["origin"],
                      "effective_origin": effective, "decoded": decoded, "candidate_action": command, "executed": executed})
    return trace, state
