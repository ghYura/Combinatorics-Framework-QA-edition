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

"""D5 phase B reference: the scope semantics the contract specifies, written independently.

Policy-blind: an explicit work stack of (node, field) frames replaces recursion. A scope pushes
its children under its own field, so the enclosing field is back in force when they are done.
`same_record` is the verdict comparison: exact key set and exact integers.
"""


def apply(op, value):
    if op == "A":
        return value + 1
    if op == "M":
        return value * 2
    if op == "S":
        return value - 3
    if op == "N":
        return 0 - value
    raise ValueError(f"unknown operation {op!r}")


def evaluate(tree):
    """Return (expected record, reference trace) for one tree from {x:2, y:5}, field x."""
    record = {"x": 2, "y": 5}
    trace = []
    work = [(node, "x") for node in reversed(tree)]
    while work:
        node, field = work.pop()
        if isinstance(node, dict):
            if node.get("scope") not in record:
                raise ValueError(f"scope field {node.get('scope')!r} is not in the record")
            work.extend((child, node["scope"]) for child in reversed(node["children"]))
        else:
            record[field] = apply(node, record[field])
            trace.append({"op": node, "field": field, "value": record[field]})
    return record, trace


def same_record(observed, expected):
    return (isinstance(observed, dict) and sorted(observed) == sorted(expected)
            and all(type(observed[k]) is int and type(expected[k]) is int and observed[k] == expected[k] for k in expected))
