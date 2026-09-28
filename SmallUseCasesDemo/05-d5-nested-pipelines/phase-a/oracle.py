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

"""D5 phase A reference: the fold a tree specifies, written independently of the SUT.

CONTRACT-A.md. The reference reads only the tree and the input record; it never reads the policy
or calls SUT code. `same_record` is the verdict comparison: exact key set and exact integer values.
"""


def step(op, value):
    if op == "A":
        return value + 1
    if op == "M":
        return value * 2
    if op == "S":
        return value - 3
    if op == "N":
        return 0 - value
    raise ValueError(f"unknown operation {op!r}")


def evaluate(record, tree):
    """Return (expected output record, reference trace): op1 then op2 on the selected field only."""
    field = tree["field"]
    if field not in record:
        raise ValueError(f"tree field {field!r} is not in the record")
    expected = {k: v for k, v in record.items()}
    value, trace = record[field], []
    for op in tree["ops"]:
        value = step(op, value)
        trace.append({"op": op, "field": field, "value": value})
    expected[field] = value
    return expected, trace


def same_record(observed, expected):
    """Exact key set and exact integers (bool is not an integer here)."""
    return (isinstance(observed, dict) and sorted(observed) == sorted(expected)
            and all(type(observed[k]) is int and type(expected[k]) is int and observed[k] == expected[k] for k in expected))
