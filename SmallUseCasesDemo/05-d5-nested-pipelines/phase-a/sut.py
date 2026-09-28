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

"""D5 phase A system under test: a record adapter that runs a two-operation pipeline on one field.

CONTRACT-A.md. A tree is {"field": "x"|"y", "ops": [op1, op2]} over integer operations
A=v+1, M=2*v, S=v-3, N=-v. The correct adapter copies the record, applies op1 then op2 to the
selected field and preserves the other field. Two policies are deliberate fault variants:
  reverse_pair  applies op2 then op1
  wrong_field   applies op1 then op2 to the other field
Nothing here knows the reference, the expected outputs or the verdict.
"""

POLICIES = ("correct", "reverse_pair", "wrong_field")
_OPERATIONS = {"A": lambda v: v + 1, "M": lambda v: 2 * v, "S": lambda v: v - 3, "N": lambda v: -v}


def adapt(record, tree, policy):
    """Return (output record, trace). The trace is diagnostic only: one step per applied operation."""
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    ops, field = list(tree["ops"]), tree["field"]
    if policy == "reverse_pair":
        ops.reverse()
    elif policy == "wrong_field":
        field = "y" if field == "x" else "x"
    out = dict(record)
    trace = []
    for op in ops:
        out[field] = _OPERATIONS[op](out[field])
        trace.append({"op": op, "field": field, "value": out[field]})
    return out, trace
