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

"""D12 system under test: the cost and rotation structure of one oriented cyclic word over A,B,C.

CONTRACT.md v1. The six directed edges w[i] -> w[i+1 mod 6] (including the seam last -> first) are
scored with the matrix below; balance penalty = sum((count - 2)^2); total = transition + balance.
Rotation structure: the representative is the lexicographically smallest distinct rotation; orbit
size is the number of distinct rotations; period is the least positive shift returning the word.
Nothing here knows the reference or the verdict.
"""

ALPHABET = "ABC"
COST = {("A", "A"): 2, ("A", "B"): 0, ("A", "C"): 3, ("B", "A"): 3, ("B", "B"): 2, ("B", "C"): 0,
        ("C", "A"): 0, ("C", "B"): 3, ("C", "C"): 2}


def evaluate(word):
    edges = [(word[i], word[(i + 1) % 6]) for i in range(6)]
    edge_costs = [COST[e] for e in edges]
    counts = [word.count(c) for c in ALPHABET]
    edge_counts = [[sum(1 for e in edges if e == (u, v)) for v in ALPHABET] for u in ALPHABET]
    rotations = {word[k:] + word[:k] for k in range(6)}
    period = next(k for k in range(1, 7) if word[k:] + word[:k] == word)
    balance = sum((n - 2) ** 2 for n in counts)
    return {"counts": counts, "edge_counts": edge_counts, "edge_costs": edge_costs, "transition_cost": sum(edge_costs),
            "balance_penalty": balance, "total_cost": sum(edge_costs) + balance, "representative": min(rotations),
            "orbit_size": len(rotations), "period": period, "stabilizer_size": 6 // len(rotations)}
