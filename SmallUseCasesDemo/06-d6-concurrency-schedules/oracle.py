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

"""D6 reference: policy-blind expectations, schedule structure and queue enabledness.

CONTRACT.md v1. Written independently of sut.py; never reads a policy.
  * counter: the expected counter after each step is the number of writes completed so far;
  * queue: actual-queue semantics on the reference's own state, with each step's enabledness
    checked on that state BEFORE the step (C1 needs a nonempty queue);
  * schedule structure: local order is positional (nth occurrence = nth step), context switches
    and preemptions from prefix completion counts.
"""


def occurrences(schedule):
    """[(thread, local step number)] — the nth occurrence of a thread is its nth step."""
    seen, out = {}, []
    for t in schedule:
        seen[t] = seen.get(t, 0) + 1
        out.append((t, seen[t]))
    return out


def context_switches(schedule):
    return sum(1 for i in range(len(schedule) - 1) if schedule[i] != schedule[i + 1])


def preemptions(schedule, steps_per_thread=2):
    """Switches whose outgoing thread still has an unexecuted local step."""
    occ = occurrences(schedule)
    return sum(1 for i in range(len(schedule) - 1) if schedule[i] != schedule[i + 1] and occ[i][1] < steps_per_thread)


def counter_expected(schedule):
    writes, out = 0, []
    for _, n in occurrences(schedule):
        writes += n == 2
        out.append(writes)
    return out


def queue_reference(schedule):
    """(reference trace, first disabled step or None). Stops at the first disabled step."""
    items, published, result, trace = [], False, None, []
    for i, (t, n) in enumerate(occurrences(schedule)):
        if (t, n) == ("C", 1) and len(items) == 0:
            return trace, i + 1
        if (t, n) == ("P", 1):
            items = items + ["item"]
        elif (t, n) == ("P", 2):
            published = len(items) > 0
        elif (t, n) == ("C", 2):
            if items:
                result, items = items[0], items[1:]
            else:
                result = "EMPTY"
        elif (t, n) != ("C", 1):
            raise ValueError(f"step {t}{n} outside the contract")
        trace.append({"items": list(items), "pop_result": result})
    return trace, None
