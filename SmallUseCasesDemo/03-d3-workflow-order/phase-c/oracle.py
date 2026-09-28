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

"""D3 phase C oracle: independent reference machine and per-event checks (policy-blind).

The reference applies the contract's correct rules to its own state; it never reads the policy
or calls SUT code. `check` compares the whole public snapshot and evaluates the A/B accounting
invariants plus Boolean validation of refund_attempted.
"""

FIELDS = ("epoch", "captures", "refunds", "balance", "refund_attempted")


def initial():
    return {"epoch": 0, "captures": [0], "refunds": [0], "balance": 0, "refund_attempted": False}


def transition(state, op):
    s = {k: (list(v) if isinstance(v, list) else v) for k, v in state.items()}
    e = s["epoch"]
    if op == "C":
        if s["captures"][e] == 0:
            s["captures"][e], s["balance"] = 1, s["balance"] + 100
    elif op == "F":
        s["refund_attempted"] = True
        if s["captures"][e] == 1 and s["refunds"][e] == 0:
            s["refunds"][e], s["balance"] = 1, s["balance"] - 100
    elif op == "N":
        s["epoch"] = e + 1
        s["captures"].append(0)
        s["refunds"].append(0)
        s["refund_attempted"] = False
    elif op in ("S", "Q"):
        s["balance"] = 100 * (sum(s["captures"]) - sum(s["refunds"]))
    elif op != "V":
        raise ValueError(f"unknown operation {op!r}")
    return s


def invariants(snap):
    c, r, e = snap["captures"], snap["refunds"], snap["epoch"]
    return {"count_domain": all(x in (0, 1) for x in c + r) and isinstance(e, int) and e >= 0,
            "refunds_le_captures": len(c) == len(r) and all(y <= x for x, y in zip(c, r)),
            "list_lengths": len(c) == e + 1 and len(r) == e + 1,
            "ledger_balance": snap["balance"] == 100 * (sum(c) - sum(r)),
            "flag_boolean": isinstance(snap["refund_attempted"], bool)}


def check(observed, reference):
    if not all(invariants(reference).values()):
        raise RuntimeError(f"reference violates an invariant: {reference}")
    mismatched = [k for k in FIELDS if observed[k] != reference[k]]
    inv = invariants(observed)
    return {"mismatched_fields": mismatched, "invariants": inv, "ok": not mismatched and all(inv.values())}
