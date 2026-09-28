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

"""D5 phase B system under test: a record interpreter for nested field scopes.

CONTRACT.md (phase B). A tree is a list of nodes; a node is an operation letter
(A=v+1, M=2*v, S=v-3, N=-v) or {"scope": field, "children": [...]}. Every tree starts from
{x:2, y:5} with current field x. Three policies:
  correct        a scope evaluates its children under its field, then restores the previous one
  flatten_scope  ignores scope bindings: every operation acts on the incoming field
  leak_scope     changes the current field at scope entry and never restores it
Nothing here knows the reference, the expected outputs or the verdict.
"""

POLICIES = ("correct", "flatten_scope", "leak_scope")
_OPERATIONS = {"A": lambda v: v + 1, "M": lambda v: 2 * v, "S": lambda v: v - 3, "N": lambda v: -v}


class Interpreter:
    def __init__(self, policy):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.record = {"x": 2, "y": 5}
        self.current = "x"
        self.trace = []

    def run(self, nodes):
        self._walk(nodes, "x")
        return dict(self.record), self.trace

    def _walk(self, nodes, field):
        for node in nodes:
            if isinstance(node, str):
                target = self.current if self.policy == "leak_scope" else field
                self.record[target] = _OPERATIONS[node](self.record[target])
                self.trace.append({"op": node, "field": target, "value": self.record[target]})
            elif self.policy == "flatten_scope":
                self._walk(node["children"], field)
            elif self.policy == "leak_scope":
                self.current = node["scope"]
                self._walk(node["children"], self.current)
            else:
                self._walk(node["children"], node["scope"])


def evaluate(tree, policy):
    """Return (final record, trace) of one tree on a fresh record and field context."""
    return Interpreter(policy).run(tree)
