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

"""D14a stack machine: the shared, correct, policy-blind executor of compiled bytecode.

CONTRACT.md v1. PUSH v appends v; STORE n pops into local n; LOAD n pushes local n; ADD/SUB/MUL pop
right, then left, and push left op right; RETURN must be the final instruction and consume the only
stack item, an integer. After every instruction the trace records the zero-based ip, the instruction,
the stack, the locals and the returned value (None until RETURN). An invalid instruction, stack
underflow, unbound variable or invalid return raises VMError: an execution error, never a number.
Every call starts from a fresh, empty state. The VM never sees a compiler policy or an expected value.
"""
ARITH = {"ADD": lambda l, r: l + r, "SUB": lambda l, r: l - r, "MUL": lambda l, r: l * r}


class VMError(Exception):
    pass


def _int(v):
    if type(v) is not int:
        raise VMError(f"non-integer value {v!r}")
    return v


def execute(code):
    stack, local, trace, result = [], {}, [], None
    if not code or code[-1] != ["RETURN"]:
        raise VMError("bytecode does not end with RETURN")
    for ip, ins in enumerate(code):
        if not isinstance(ins, list) or not ins:
            raise VMError(f"malformed instruction at ip {ip}: {ins!r}")
        op, args = ins[0], ins[1:]
        if op == "PUSH" and len(args) == 1:
            stack.append(_int(args[0]))
        elif op in ("STORE", "LOAD") and len(args) == 1 and isinstance(args[0], str):
            if op == "STORE":
                if not stack:
                    raise VMError(f"stack underflow at ip {ip}")
                local[args[0]] = stack.pop()
            else:
                if args[0] not in local:
                    raise VMError(f"unbound variable {args[0]!r} at ip {ip}")
                stack.append(local[args[0]])
        elif op in ARITH and not args:
            if len(stack) < 2:
                raise VMError(f"stack underflow at ip {ip}")
            right, left = stack.pop(), stack.pop()
            stack.append(ARITH[op](left, right))
        elif op == "RETURN" and not args:
            if ip != len(code) - 1 or len(stack) != 1:
                raise VMError(f"invalid RETURN at ip {ip} with stack {stack}")
            result = _int(stack.pop())
        else:
            raise VMError(f"invalid instruction at ip {ip}: {ins!r}")
        trace.append({"ip": ip, "instruction": list(ins), "stack": list(stack), "locals": dict(local), "returned": result})
    return result, trace
