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

"""D6 systems under test: two deterministic step machines driven by an explicit schedule.

CONTRACT.md v1. Nothing here knows the reference, the expected traces or the verdict.

Counter: threads A and B each run read then write. A read saves the current counter into the
thread's local; the write depends on the policy:
  atomic_commit  counter = current counter + 1
  split_rw       counter = the thread's saved read value + 1   (loses an interleaved update)
Queue: producer P (enqueue "item", then publish items-nonempty) and consumer C (wait_readable,
then try_pop, which never blocks):
  actual_queue   try_pop removes the first item if the queue holds one, else returns "EMPTY"
  stale_empty    try_pop returns "EMPTY" whenever the published flag is false, item or not
"""

COUNTER_POLICIES = ("atomic_commit", "split_rw")
QUEUE_POLICIES = ("actual_queue", "stale_empty")


class Counter:
    def __init__(self, policy):
        if policy not in COUNTER_POLICIES:
            raise ValueError(f"unknown counter policy {policy!r}")
        self.policy, self.counter, self.locals, self.done = policy, 0, {}, {"A": 0, "B": 0}

    def step(self, thread):
        self.done[thread] += 1
        if self.done[thread] == 1:
            self.locals[thread] = self.counter
            op = "read"
        elif self.done[thread] == 2:
            base = self.counter if self.policy == "atomic_commit" else self.locals[thread]
            self.counter = base + 1
            op = "write"
        else:
            raise RuntimeError(f"thread {thread} has no third step")
        return {"thread": thread, "op": op, "counter": self.counter, "locals": dict(self.locals)}


class Queue:
    def __init__(self, policy):
        if policy not in QUEUE_POLICIES:
            raise ValueError(f"unknown queue policy {policy!r}")
        self.policy, self.items, self.published, self.result, self.done = policy, [], False, None, {"P": 0, "C": 0}

    def step(self, thread):
        self.done[thread] += 1
        n = self.done[thread]
        if thread == "P" and n == 1:
            self.items.append("item")
            op = "enqueue"
        elif thread == "P" and n == 2:
            self.published = bool(self.items)
            op = "publish"
        elif thread == "C" and n == 1:
            op = "wait_readable"                      # the harness only runs it when enabled
        elif thread == "C" and n == 2:
            op = "try_pop"
            stale = self.policy == "stale_empty" and not self.published
            self.result = self.items.pop(0) if self.items and not stale else "EMPTY"
        else:
            raise RuntimeError(f"thread {thread} has no step {n}")
        return {"thread": thread, "op": op, "items": list(self.items), "published_nonempty": self.published,
                "pop_result": self.result}
