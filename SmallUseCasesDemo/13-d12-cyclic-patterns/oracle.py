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

"""D12 reference: directed pair counts dotted with the cost matrix, and rotations from a doubled string.

Written independently of the SUT; never reads frozen results.
"""

MATRIX = [[2, 0, 3], [3, 2, 0], [0, 3, 2]]
INDEX = {"A": 0, "B": 1, "C": 2}


def pair_counts(word):
    n = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    doubled = word + word[0]
    for a, b in zip(doubled, doubled[1:]):
        n[INDEX[a]][INDEX[b]] += 1
    return n


def expected(word):
    n = pair_counts(word)
    transition = sum(n[i][j] * MATRIX[i][j] for i in range(3) for j in range(3))
    counts = [sum(1 for ch in word if ch == c) for c in "ABC"]
    balance = sum((c - 2) * (c - 2) for c in counts)
    ring = word + word
    slices = [ring[k:k + 6] for k in range(6)]
    distinct = sorted(set(slices))
    period = slices[1:].index(word) + 1 if word in slices[1:] else 6
    return {"counts": counts, "edge_counts": n, "transition_cost": transition, "balance_penalty": balance,
            "total_cost": transition + balance, "representative": distinct[0], "orbit_size": len(distinct),
            "period": period, "stabilizer_size": 6 // len(distinct)}
