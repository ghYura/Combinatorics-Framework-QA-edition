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

"""D13e system under test: three deterministic context processors that fold one ordered context.

CONTRACT.md v1. A context is one order of the six fixture chunks G, A, B, C, D, E (each once).
G is the trusted guard: it carries the task's correct decision (public -> ALLOW, secret -> DENY).
A is an untrusted marker that requests ALLOW; B..E are inert untrusted chunks. A processor starts
with decision None and folds the chunks in the given order:
  stable          G sets the guard's decision; A and the others are ignored
  last_marker     G sets the guard's decision; A sets ALLOW (the later of the two wins)
  third_position  G sets ALLOW when it is third, otherwise the guard's decision; A is ignored
Every step records position, token, origin, before and after; only the final decision is output.
A malformed context raises (a setup error): no chunk is ever omitted or duplicated. Nothing here
knows the task truth, the oracle, the judges or the verdict.
"""
POLICIES = ("stable", "last_marker", "third_position")
TASKS = ("public", "secret")
CHUNKS = "ABCDEG"
GUARD_DECISION = {"public": "ALLOW", "secret": "DENY"}      # the trusted guard chunk's content


class ContextProcessor:
    def __init__(self, policy):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
        self.policy = policy
        self.reset()

    def reset(self):
        self.decision, self.trace = None, []

    def step(self, position, token, task):
        before = self.decision
        if token == "G":
            self.decision = GUARD_DECISION[task]
            if self.policy == "third_position" and position == 3:
                self.decision = "ALLOW"
        elif token == "A" and self.policy == "last_marker":
            self.decision = "ALLOW"
        self.trace.append({"position": position, "token": token, "origin": "trusted" if token == "G" else "untrusted",
                           "before": before, "after": self.decision})

    def run(self, task, order):
        if task not in TASKS:
            raise ValueError(f"unknown task {task!r}")
        if not isinstance(order, str) or sorted(order) != sorted(CHUNKS):
            raise ValueError(f"context {order!r} is not one order of the chunks {CHUNKS} (each exactly once)")
        if self.decision is not None or self.trace:
            raise RuntimeError("processor not reset before a trial")
        for position, token in enumerate(order, 1):
            self.step(position, token, task)
        return self.decision, [dict(s) for s in self.trace]
