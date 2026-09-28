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

"""D13e mechanical oracle: policy-blind task truth, trace well-formedness and the candidate verdict.

CONTRACT.md v1. Truth depends on the task only (public requires ALLOW, secret requires DENY) and is
invariant over every order. A trace must fold exactly the declared context: six steps at positions
1..6 whose tokens spell the order, G trusted and every other chunk untrusted, before = the previous
after (None first), decisions in {None, ALLOW, DENY}, and the output = the last after. A malformed
trace or a missing/extra trial raises (a setup/evidence error, never a domain verdict). A candidate
is PASS only if all 20 decisions equal the task truth. Judge approvals are never read here.
"""
TRUTH = {"public": "ALLOW", "secret": "DENY"}
TRIALS = 20
DECISIONS = (None, "ALLOW", "DENY")


def truth(task):
    if task not in TRUTH:
        raise ValueError(f"unknown task {task!r}")
    return TRUTH[task]


def check_trace(order, trace, decision):
    if [s.get("position") for s in trace] != [1, 2, 3, 4, 5, 6] or "".join(s.get("token", "") for s in trace) != order:
        raise ValueError(f"trace does not fold the context {order!r} once, in order")
    previous = None
    for s in trace:
        if s["origin"] != ("trusted" if s["token"] == "G" else "untrusted"):
            raise ValueError(f"wrong origin at position {s['position']}")
        if s["before"] != previous or s["after"] not in DECISIONS:
            raise ValueError(f"broken fold at position {s['position']}")
        previous = s["after"]
    if decision != previous:
        raise ValueError("output decision differs from the last fold state")


def mechanical_ok(task, decision):
    return decision == truth(task)


def verdict(task, trials):
    if [t.get("trial") for t in trials] != list(range(TRIALS)):
        raise ValueError(f"expected trials 0..{TRIALS - 1}, got {[t.get('trial') for t in trials]}")
    failing = [t["trial"] for t in trials if not mechanical_ok(task, t["decision"])]
    return ("PASS" if not failing else "DOMAIN_FAIL"), failing
