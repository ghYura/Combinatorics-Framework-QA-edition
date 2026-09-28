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

"""D3 oracle: an independent reference state machine and per-checkpoint checks.

CONTRACT.md v1. The reference follows the frozen transition rules on its own state; it never
reads the policy or calls SUT code. `check` compares one observed snapshot with the reference
snapshot and evaluates four invariants on the observed snapshot: count domains, refunds <=
captures per epoch, list lengths epoch+1, and balance == ledger value.
"""


def initial():
    return {"epoch": 0, "captures": [0], "refunds": [0], "balance": 0}


def transition(state, op):
    """Return the reference snapshot after `op` (a new dict; `state` is not modified)."""
    s = {"epoch": state["epoch"], "captures": list(state["captures"]),
         "refunds": list(state["refunds"]), "balance": state["balance"]}
    e = s["epoch"]
    if op == "C":
        # Literal rule: charge iff captures[epoch] is zero. Under this contract a refund implies a
        # capture, so a refunded epoch already has captures==1 and cannot be charged again.
        if s["captures"][e] == 0:
            s["captures"][e], s["balance"] = 1, s["balance"] + 100
    elif op == "F":
        if s["captures"][e] == 1 and s["refunds"][e] == 0:
            s["refunds"][e], s["balance"] = 1, s["balance"] - 100
    elif op == "N":
        s["epoch"] = e + 1
        s["captures"].append(0)
        s["refunds"].append(0)
    elif op == "S":
        s["balance"] = 100 * (sum(s["captures"]) - sum(s["refunds"]))   # reload from the ledger
    elif op == "Q":
        s["balance"] = 100 * (sum(s["captures"]) - sum(s["refunds"]))
    else:
        raise ValueError(f"unknown operation {op!r}")
    return s


def invariants(snap):
    caps, refs, epoch = snap["captures"], snap["refunds"], snap["epoch"]
    return {
        "count_domain": all(x in (0, 1) for x in caps + refs) and isinstance(epoch, int) and epoch >= 0,
        "refunds_le_captures": len(caps) == len(refs) and all(r <= c for c, r in zip(caps, refs)),
        "list_lengths": len(caps) == epoch + 1 and len(refs) == epoch + 1,
        "ledger_balance": snap["balance"] == 100 * (sum(caps) - sum(refs)),
    }


def check(observed, reference):
    """One checkpoint: field mismatches against the reference, invariant results, overall ok."""
    mismatched = [k for k in ("epoch", "captures", "refunds", "balance") if observed[k] != reference[k]]
    inv = invariants(observed)
    if not all(invariants(reference).values()):
        raise RuntimeError(f"reference violates an invariant: {reference}")
    return {"mismatched_fields": mismatched, "invariants": inv, "ok": not mismatched and all(inv.values())}
