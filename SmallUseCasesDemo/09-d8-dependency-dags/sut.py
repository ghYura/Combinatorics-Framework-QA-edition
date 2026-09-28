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

"""D8b system under test: an incremental dependency cache over nodes A,B,C,D.

CONTRACT.md v1. An edge u->v means v depends on u; value[v] = base[v] + sum(value[u] for u->v).
The cache is built in A,B,C,D order. After one base input changes (the cache is untouched by the
edit itself), the policy picks dirty nodes and recomputes each once from its parents' CURRENT
cached values:
  closure_forward  edited node + every reachable descendant, increasing index
  direct_only      edited node + its direct successors,      increasing index
  closure_reverse  edited node + every reachable descendant, decreasing index
Nothing here knows the fresh reference, path counts, predictions or the verdict.
"""

IDS = "ABCD"
POLICIES = ("closure_forward", "direct_only", "closure_reverse")


class Cache:
    def __init__(self, edges, base):
        self.edges = sorted(edges)
        self.base = list(base)
        self.values = [0, 0, 0, 0]
        for v in range(4):
            self.values[v] = self._compute(v)[0]

    def parents(self, v):
        return [u for u, w in self.edges if w == v]

    def _compute(self, v):
        reads = [{"node": IDS[u], "value": self.values[u]} for u in self.parents(v)]
        return self.base[v] + sum(r["value"] for r in reads), reads

    def edit(self, node, delta):
        self.base[node] += delta                      # the cache itself is not touched

    def descendants(self, node):
        seen, stack = set(), [node]
        while stack:
            u = stack.pop()
            for a, b in self.edges:
                if a == u and b not in seen:
                    seen.add(b)
                    stack.append(b)
        return seen

    def update(self, policy, node):
        """Recompute the policy's dirty nodes once each; return (dirty, order, updates)."""
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        if policy == "direct_only":
            dirty = sorted({node} | {b for a, b in self.edges if a == node})
        else:
            dirty = sorted({node} | self.descendants(node))
        order = dirty[::-1] if policy == "closure_reverse" else list(dirty)
        updates = []
        for v in order:
            new, reads = self._compute(v)
            previous = self.values[v]
            self.values[v] = new
            updates.append({"node": IDS[v], "base": self.base[v], "parent_reads": reads, "previous": previous,
                            "new": new, "cache": list(self.values)})
        return dirty, order, updates
