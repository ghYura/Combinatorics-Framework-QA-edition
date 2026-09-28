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

"""D8a reference: the declared stable-order contract and the observable obligations, policy-blind.

The expected listing orders records by (s*rank, input position): ties keep input order in BOTH
directions. The obligations follow the frozen field meanings (adjacent pairs of the concatenated
output); the comparator laws are checked on each observed 4x4 sign matrix.
"""

IDS = "ABCD"


def expected_order(ranks, direction):
    s = 1 if direction == "asc" else -1
    return [IDS[i] for i in sorted(range(4), key=lambda i: (s * ranks[i], i))]


def obligations(ranks, direction, collected, last_page_empty):
    pos = {c: IDS.index(c) for c in IDS}
    rank = {c: ranks[pos[c]] for c in IDS}
    pairs = list(zip(collected, collected[1:]))
    in_order = (lambda a, b: rank[a] <= rank[b]) if direction == "asc" else (lambda a, b: rank[a] >= rank[b])
    return {"multiset_ok": sorted(collected) == list(IDS),
            "primary_order_ok": all(in_order(a, b) for a, b in pairs),
            "stable_ties_ok": all(pos[a] <= pos[b] for a, b in pairs if rank[a] == rank[b]),
            "terminated": last_page_empty}


def comparator_laws(matrix, ranks, direction):
    s = 1 if direction == "asc" else -1
    n = range(4)
    sign = lambda x: (x > 0) - (x < 0)      # noqa: E731
    return {"signs_ok": all(matrix[i][j] in (-1, 0, 1) for i in n for j in n),
            "reflexive": all(matrix[i][i] == 0 for i in n),
            "antisymmetric": all(matrix[i][j] == -matrix[j][i] for i in n for j in n),
            "transitive_le": all(matrix[i][k] <= 0 for i in n for j in n for k in n if matrix[i][j] <= 0 and matrix[j][k] <= 0),
            "primary_direction": all(matrix[i][j] == sign(s * (ranks[i] - ranks[j])) for i in n for j in n if ranks[i] != ranks[j])}
