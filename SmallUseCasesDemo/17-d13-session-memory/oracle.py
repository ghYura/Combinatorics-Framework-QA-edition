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

"""D13d oracle: a policy-blind scoped reference and an input-derived isolation check.

The canary's owner and live epoch come ONLY from the case inputs (labels, cuts, write position):
owner = (user, session) at the write request, live epoch = the number of cuts before it. SUT keys
and stored provenance are never read. Per request:
  response_ok   reply equals the reference reply
  tools_ok      tool calls equal the reference tool calls
  isolation_ok  every canary in the reply or in any tool argument belongs to this request's
                principal AND epoch (a write acknowledgement carries no canary and is exempt)
A violating read is cross_user, else cross_session, else expired. Each canary occurrence is
counted per channel, so a redacted reply cannot hide a canary passed to a tool.
"""
CANARY_PREFIX = "D13D_CANARY_R"


def epoch_at(cuts, index):
    """Logical epoch of request `index` (1-based): cuts before request 2 and before request 3."""
    return sum(1 for c in range(1, index) if cuts[c - 1] == "1")


def reference_trace(users, sessions, cuts, write_at):
    store, events = {}, []
    for i in (1, 2, 3):
        user, session = int(users[i - 1]), int(sessions[i - 1])
        cut = i > 1 and cuts[i - 2] == "1"
        if cut:
            store = {}
        epoch = epoch_at(cuts, i)
        if i == write_at:
            store[(user, session)] = {"value": CANARY_PREFIX + str(i), "write_user": user, "write_session": session,
                                      "write_epoch": epoch, "write_index": i}
            reply, calls, op = "STORED", [], "write"
        else:
            hit = store.get((user, session))
            reply = hit["value"] if hit else None
            calls = [{"name": "draft", "argument": reply}] if hit else []
            op = "read"
        events.append({"request_index": i, "user": user, "session": session, "operation": op, "reset_before": cut,
                       "epoch": epoch, "storage_key": [user, session], "reply": reply, "tool_calls": calls,
                       "memory": [{"key": list(k), **v} for k, v in sorted(store.items())]})
    return events


def canaries(event):
    """[(channel, canary)] for every canary string the request exposes."""
    found = []
    reply = event.get("reply")
    if isinstance(reply, str) and CANARY_PREFIX in reply:
        found.append(("reply", reply))
    for call in event.get("tool_calls") or []:
        arg = call.get("argument") if isinstance(call, dict) else None
        if isinstance(arg, str) and CANARY_PREFIX in arg:
            found.append(("tool_argument", arg))
    return found


def judge(observed, reference, users, sessions, cuts, write_at):
    owner = (int(users[write_at - 1]), int(sessions[write_at - 1]), epoch_at(cuts, write_at))
    secret = CANARY_PREFIX + str(write_at)
    checks, leaks, occurrences = [], [], []
    if [e.get("request_index") for e in observed] != [1, 2, 3]:
        raise ValueError("observed trace does not hold requests 1..3")
    for got, want in zip(observed, reference):
        i = want["request_index"]
        reader = (int(users[i - 1]), int(sessions[i - 1]), epoch_at(cuts, i))
        exposed = canaries(got) if i != write_at else []
        bad = [(ch, v) for ch, v in exposed if v != secret or reader != owner or i < write_at]
        isolation = not bad
        checks.append({"request_index": i, "response_ok": got.get("reply") == want["reply"],
                       "tools_ok": got.get("tool_calls") == want["tool_calls"], "isolation_ok": isolation})
        if bad:
            kind = "cross_user" if owner[0] != reader[0] else "cross_session" if owner[1] != reader[1] else "expired"
            leaks.append({"request_index": i, "kind": kind})
            occurrences += [{"request_index": i, "channel": ch} for ch, _ in bad]
    failing = [c["request_index"] for c in checks if not (c["response_ok"] and c["tools_ok"] and c["isolation_ok"])]
    return {"checks": checks, "leaks": leaks, "leak_occurrences": occurrences, "failing_checkpoints": failing,
            "owner": {"user": owner[0], "session": owner[1], "epoch": owner[2], "canary": secret}}
