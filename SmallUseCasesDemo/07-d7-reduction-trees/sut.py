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

"""D7 system under test: sum five binary64 inputs following a generated bracketing tree.

CONTRACT.md v1. A tree is a leaf index (0..4) or a pair [left, right]. Policies:
  tree_binary64  one ordinary binary64 addition at every internal node (node results kept)
  flat_fsum      collect the tree's leaves left to right, then ONE math.fsum over all five
  tree_rational  exact Fraction addition at every internal node (node results kept)
Nothing here knows the reference, the budgets or the verdict.
"""
import math
from fractions import Fraction

POLICIES = ("tree_binary64", "flat_fsum", "tree_rational")


def canonical(tree):
    return str(tree) if isinstance(tree, int) else f"({canonical(tree[0])},{canonical(tree[1])})"


def leaves(tree):
    return [tree] if isinstance(tree, int) else leaves(tree[0]) + leaves(tree[1])


def evaluate(policy, tree, values):
    """Return (result, node trace). Node trace: post-order internal nodes with their results."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    nodes = []
    if policy == "flat_fsum":
        return math.fsum([values[i] for i in leaves(tree)]), nodes
    exact = policy == "tree_rational"

    def walk(t):
        if isinstance(t, int):
            return Fraction(values[t]) if exact else values[t]
        s = walk(t[0]) + walk(t[1])
        nodes.append({"node": canonical(t), "value": s})
        return s
    return walk(tree), nodes
