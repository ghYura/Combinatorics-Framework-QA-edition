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

"""D14a reference interpreter: evaluates the program AST directly (no compiler, no bytecode, no eval).

CONTRACT.md v1. Bindings are evaluated in order into a fresh environment (a later binding of the
same name replaces the earlier one); the expression is then evaluated recursively over mathematical
integers. A malformed AST (unknown node or operator, non-integer constant, unbound variable) raises
ValueError: a setup error, never a reference value.
"""
OPS = {"+": lambda l, r: l + r, "-": lambda l, r: l - r, "*": lambda l, r: l * r}


def evaluate(program):
    env = {}
    for binding in program["bindings"]:
        if not isinstance(binding.get("name"), str) or type(binding.get("value")) is not int:
            raise ValueError(f"malformed binding {binding!r}")
        env[binding["name"]] = binding["value"]

    def visit(node):
        if set(node) == {"var"}:
            if node["var"] not in env:
                raise ValueError(f"unbound variable {node['var']!r}")
            return env[node["var"]]
        if set(node) != {"op", "left", "right"} or node["op"] not in OPS:
            raise ValueError(f"malformed expression node {node!r}")
        return OPS[node["op"]](visit(node["left"]), visit(node["right"]))

    return visit(program["expr"])
