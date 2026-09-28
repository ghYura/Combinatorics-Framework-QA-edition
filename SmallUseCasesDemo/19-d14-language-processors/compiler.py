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

"""D14a system under test: a tiny AST-to-stack-machine compiler with three back-end policies.

CONTRACT.md v1. A program is {"bindings": [{"name", "value"}, ...], "expr": node}; a node is
{"var": name} or {"op": "+"|"-"|"*", "left": node, "right": node}. Emission:
  PUSH value; STORE name      for each binding, in order
  LOAD name                   for a variable
  left, right, ADD|SUB|MUL    for a binary node
  RETURN                      last
Policies:
  faithful          no change
  reverse_sub       emit the right child before the left child for subtraction nodes only
  alias_dead_temp   compile STORE z as STORE x (every other instruction stays faithful)
The faulty policies still emit well-formed bytecode. Nothing here evaluates, runs or judges code.
"""
POLICIES = ("faithful", "reverse_sub", "alias_dead_temp")
OPCODES = {"+": "ADD", "-": "SUB", "*": "MUL"}


def compile_program(program, policy):
    if policy not in POLICIES:
        raise ValueError(f"unknown compiler policy {policy!r}")
    code = []
    for binding in program["bindings"]:
        name = binding["name"]
        if policy == "alias_dead_temp" and name == "z":
            name = "x"
        code += [["PUSH", binding["value"]], ["STORE", name]]

    def emit(node):
        if "var" in node:
            code.append(["LOAD", node["var"]])
            return
        if node.get("op") not in OPCODES:
            raise ValueError(f"cannot compile node {node!r}")
        sides = ("right", "left") if policy == "reverse_sub" and node["op"] == "-" else ("left", "right")
        for side in sides:
            emit(node[side])
        code.append([OPCODES[node["op"]]])

    emit(program["expr"])
    return code + [["RETURN"]]
