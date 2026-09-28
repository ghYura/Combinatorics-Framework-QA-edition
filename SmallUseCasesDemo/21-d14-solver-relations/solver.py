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

"""D14c system under test: three weighted set-packing solvers over goods {0, 1, 2} (capacity one each).

CONTRACT.md v1. A bid is {"id", "items", "value"}; solve(policy, bids) returns the sorted selected IDs and
the value the solver reports.
  exact_dp      DP over occupied-item bitmasks, bids in input order: copy every skip state, add a take
                state only when the bid's mask is disjoint from the occupied mask; keep the best
                (value, sorted ID tuple) per resulting mask; the answer is the maximum pair (ties: the
                lexicographically largest ID tuple). Each bid is used at most once.
  greedy_value  scan bids by descending value, then ascending ID; accept a bid iff all its goods are free.
  min_only_dp   the same DP, but a bid's mask holds only its smallest item (the planted feasibility bug);
                the reported value still sums the full bids' values.
Nothing here enumerates subsets, knows the optimum, or reads an expected result.
"""
POLICIES = ("exact_dp", "greedy_value", "min_only_dp")


def _mask(items, smallest_only):
    chosen = items[:1] if smallest_only else items
    m = 0
    for i in chosen:
        m |= 1 << i
    return m


def _dp(bids, smallest_only):
    best = {0: (0, ())}
    for bid in bids:
        m = _mask(bid["items"], smallest_only)
        nxt = dict(best)                                      # skip states, from the previous iteration only
        for occupied, (value, ids) in best.items():
            if occupied & m:
                continue
            cand = (value + bid["value"], tuple(sorted(ids + (bid["id"],))))
            key = occupied | m
            if key not in nxt or cand > nxt[key]:
                nxt[key] = cand
        best = nxt
    value, ids = max(best.values())
    return list(ids), value


def _greedy(bids):
    used, chosen = set(), []
    for bid in sorted(bids, key=lambda b: (-b["value"], b["id"])):
        if not used.intersection(bid["items"]):
            chosen.append(bid["id"])
            used.update(bid["items"])
    return sorted(chosen), sum(b["value"] for b in bids if b["id"] in chosen)


def solve(policy, bids):
    if policy == "exact_dp":
        selected, value = _dp(bids, smallest_only=False)
    elif policy == "min_only_dp":
        selected, value = _dp(bids, smallest_only=True)
    elif policy == "greedy_value":
        selected, value = _greedy(bids)
    else:
        raise ValueError(f"unknown solver policy {policy!r}")
    return {"selected": selected, "reported_value": value}
