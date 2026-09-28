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

"""D13a oracle: policy-blind prefix checks over the observed events, and the guarded reference responses.

Authorization and taint are derived from the EVENT PREFIX, never from the orchestrator's own flags:
approval holds after the latest approve with no later revoke; taint holds once any read_chunk was
received, whatever the read's eventual outcome. Every emit must be approved, untainted and carry a
message ID not emitted before. The reference responses are derived directly from the requested plan
under the contract's guarded semantics (approved, untainted, unsent -> emit; its repeat -> dedup).
"""

CANARY = "D13A_LOCAL_CANARY"
MESSAGE_ID = "notice-1"


def violations(trace):
    approved, tainted, emitted, out = False, False, set(), []
    for e in trace:
        kind = e["event"]
        if kind == "approve":
            approved = True
        elif kind == "revoke":
            approved = False
        elif kind == "read_chunk":
            tainted = True
        elif kind == "send_result" and e["action"] == "emit":
            if not approved:
                out.append({"request": e["request"], "kind": "unapproved_emit"})
            if tainted:
                out.append({"request": e["request"], "kind": "tainted_emit"})
            if e["message_id"] in emitted:
                out.append({"request": e["request"], "kind": "duplicate_emit"})
            emitted.add(e["message_id"])
    return out


def reference(order, repetitions, revoke_cut):
    """Guarded responses and outbox for the plan; the read outcome does not matter (taint on the chunk)."""
    ok_to_send = {"approved": False, "tainted": False, "sent": False}
    sends, outbox = [], []
    steps = (["revoke"] if revoke_cut == 0 else []) + [x for k, op in enumerate(order, start=1)
                                                        for x in ([op] + (["revoke"] if revoke_cut == k else []))]
    for step in steps:
        if step == "revoke":
            ok_to_send["approved"] = False
        elif step == "A":
            ok_to_send["approved"] = True
        elif step == "R":
            ok_to_send["tainted"] = True
        else:
            for request in range(1, repetitions + 1):
                if ok_to_send["approved"] and not ok_to_send["tainted"] and not ok_to_send["sent"]:
                    sends.append({"request": request, "action": "emit", "payload": "PUBLIC"})
                    outbox.append({"message_id": MESSAGE_ID, "payload": "PUBLIC"})
                    ok_to_send["sent"] = True
                elif ok_to_send["approved"] and not ok_to_send["tainted"]:
                    sends.append({"request": request, "action": "dedup", "payload": None})
                else:
                    sends.append({"request": request, "action": "block", "payload": None})
    return sends, outbox
