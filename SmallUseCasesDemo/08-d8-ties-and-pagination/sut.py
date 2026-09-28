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

"""D8a system under test: one page of a deterministic static listing of records A,B,C,D.

CONTRACT.md v1. Records have fixed input positions i=0..3 and integer ranks; s=+1 (asc) or -1
(desc). Each policy's comparator drives the sort (cmp_to_key), on the full input A,B,C,D every
request:
  stable_cursor      key (s*rank, i); keep records whose key > the incoming composite cursor
  score_only_cursor  key (s*rank,);   keep records whose key > the incoming primary-only cursor
  alternating_ties   key (s*rank, i) on even requests, (s*rank, -i) on odd ones; offset 2*request
Cursor pages take the first two eligible records and return the last key as the cursor.
Nothing here knows the stable-order contract, the expected output or the verdict.
"""
from functools import cmp_to_key

IDS = "ABCD"
POLICIES = ("stable_cursor", "score_only_cursor", "alternating_ties")
PAGE_SIZE = 2


def sort_key(policy, ranks, direction, request, i):
    s = 1 if direction == "asc" else -1
    if policy == "score_only_cursor":
        return (s * ranks[i],)
    if policy == "alternating_ties" and request % 2 == 1:
        return (s * ranks[i], -i)
    return (s * ranks[i], i)


def comparator(policy, ranks, direction, request):
    def cmp(i, j):
        a, b = sort_key(policy, ranks, direction, request, i), sort_key(policy, ranks, direction, request, j)
        return (a > b) - (a < b)
    return cmp


def page(policy, ranks, direction, request, cursor):
    """One request: (full order, sign matrix, returned record indices, outgoing cursor, offset)."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    cmp = comparator(policy, ranks, direction, request)
    order = sorted(range(4), key=cmp_to_key(cmp))
    matrix = [[cmp(i, j) for j in range(4)] for i in range(4)]
    if policy == "alternating_ties":
        offset = PAGE_SIZE * request
        return order, matrix, order[offset:offset + PAGE_SIZE], None, offset
    key = lambda i: sort_key(policy, ranks, direction, request, i)      # noqa: E731
    chosen = [i for i in order if cursor is None or key(i) > tuple(cursor)][:PAGE_SIZE]
    return order, matrix, chosen, (list(key(chosen[-1])) if chosen else None), None
