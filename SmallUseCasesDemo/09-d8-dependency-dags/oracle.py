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

"""D8b reference: fresh evaluation from base inputs, policy-blind and without incremental state.

value(v) is evaluated recursively with a fresh memo for every call of `fresh`; reachability and
path counts come from a memoized recursion over successors (one length-zero path from a node to
itself). Nothing here reads a policy name or reuses a cache.
"""

IDS = "ABCD"


def fresh(edges, base):
    memo = {}

    def value(v):
        if v not in memo:
            memo[v] = base[v] + sum(value(u) for u, w in edges if w == v)
        return memo[v]
    return [value(v) for v in range(4)]


def path_counts(edges):
    memo = {}

    def paths(u, v):
        if (u, v) not in memo:
            memo[(u, v)] = 1 if u == v else sum(paths(w, v) for a, w in edges if a == u)
        return memo[(u, v)]
    return [[paths(u, v) for v in range(4)] for u in range(4)]
