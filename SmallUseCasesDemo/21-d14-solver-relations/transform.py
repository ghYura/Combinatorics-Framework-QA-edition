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

"""D14c inputs and transformations: the four frozen instances, resource relabelling and the dominated-bid edit.

CONTRACT.md v1. Bids are listed b0..b3 in the contract's order. relabel(bids, R) maps every item i to R[i]
(R a permutation of 0, 1, 2), sorts each item set and keeps IDs, order and values. dominated(bids) appends
b4 with transformed b0's item set and value b0.value - 1; it is valid only because b0 is nonempty and every
good has capacity one (b0 and b4 then conflict, and swapping b4 for b0 keeps feasibility and adds 1).
Nothing here solves or judges.
"""
INSTANCES = {
    "bundle_trap": [([0, 1], 7), ([0], 4), ([1], 4), ([2], 2)],
    "tie": [([0, 1], 8), ([0], 4), ([1], 4), ([2], 2)],
    "disjoint": [([0], 5), ([1], 4), ([2], 3), ([0, 1, 2], 6)],
    "overlap": [([0, 1], 6), ([1, 2], 5), ([0, 2], 4), ([2], 2)],
}
EDITS = ("none", "dominated")
GOODS = (0, 1, 2)


def base_bids(name):
    if name not in INSTANCES:
        raise ValueError(f"unknown instance {name!r}")
    return [{"id": f"b{k}", "items": list(items), "value": value} for k, (items, value) in enumerate(INSTANCES[name])]


def relabel(bids, perm):
    if sorted(perm) != list(GOODS) or len(perm) != 3:
        raise ValueError(f"relabelling {perm!r} is not a permutation of {GOODS}")
    return [{"id": b["id"], "items": sorted(perm[i] for i in b["items"]), "value": b["value"]} for b in bids]


def dominated(bids):
    first = bids[0]
    if first["id"] != "b0" or not first["items"] or first["value"] < 2:
        raise ValueError("the dominated-bid edit needs a nonempty b0 with value >= 2")
    return [dict(b, items=list(b["items"])) for b in bids] + [{"id": "b4", "items": list(first["items"]), "value": first["value"] - 1}]


def apply_edit(bids, edit):
    if edit not in EDITS:
        raise ValueError(f"unknown edit {edit!r}")
    return dominated(bids) if edit == "dominated" else [dict(b, items=list(b["items"])) for b in bids]
