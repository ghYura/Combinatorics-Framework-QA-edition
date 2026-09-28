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

"""D14a runtime: rebuild the case from the rendered atoms, run both program variants, emit one record.

A candidate runs, in order:
  HEAD   begin()                      a fresh case (after the inlined sources are checked)
  IMPL   impl("<policy>");
  XVAL   xval(<-1|2>);   YVAL  yval(<-1|2>);
  SHAPE  shape("L"|"R");  OP_A  op_a("+"|"-"|"*");  OP_B  op_b("+"|"-"|"*");
  DECL   declare("x");declare("y");  or  declare("y");declare("x");   (one native FW_Permut row)
  TAIL   finish()
The DECL row alone fixes the binding order. finish() builds the original program (bindings in the
declared order) and the transformed one (z=7 inserted right after the first declaration); each is
evaluated by the interpreter and compiled and run on the VM from fresh state. The oracle's three
checks decide the verdict. Anything malformed raises, so the Executor records BROKEN (a setup or
execution error), never a numeric verdict. One stdout line:

  app=d14a_compiler FW_VAR=<0|2> case=<id> verdict=<PASS|DOMAIN_FAIL> rec=<base64url(JSON)> rec_sha256=<hex>

FW_VAR 2 is the IMPL position's legacy carrier, not a statement of cause.
"""
import base64
import hashlib
import json

import compiler
import interpreter
import oracle
import vm

APP = "d14a_compiler"
CARRIER = 2
SOURCE_SHA256 = {}               # filled by the candidate HEAD after it checks the inlined sources
STEPS = ("impl", "xval", "yval", "shape", "op_a", "op_b")
_state = {}


def begin():
    if _state:
        raise RuntimeError("begin() called twice in one candidate")
    _state.update(config={}, declared=[])


def _set(step, value, allowed):
    if not _state or list(_state["config"]) != list(STEPS[:STEPS.index(step)]) or _state["declared"]:
        raise RuntimeError(f"{step}() out of order after {list(_state.get('config', {}))}")
    if value not in allowed or type(value) is not type(allowed[0]):
        raise ValueError(f"{step}({value!r}) outside {allowed}")
    _state["config"][step] = value


def impl(policy):
    _set("impl", policy, compiler.POLICIES)


def xval(v):
    _set("xval", v, (-1, 2))


def yval(v):
    _set("yval", v, (-1, 2))


def shape(s):
    _set("shape", s, ("L", "R"))


def op_a(o):
    _set("op_a", o, ("+", "-", "*"))


def op_b(o):
    _set("op_b", o, ("+", "-", "*"))


def declare(name):
    if not _state or len(_state["config"]) != len(STEPS):
        raise RuntimeError("declare() before the configuration is complete")
    if name not in ("x", "y") or name in _state["declared"] or len(_state["declared"]) == 2:
        raise ValueError(f"declare({name!r}) after {_state['declared']}: need x and y once each")
    _state["declared"].append(name)


def programs(declared, x, y, shape_, a, b):
    var = {"x": {"var": "x"}, "y": {"var": "y"}}
    node = lambda op, left, right: {"op": op, "left": left, "right": right}
    expr = node(b, node(a, var["x"], var["y"]), var["x"]) if shape_ == "L" else node(a, var["x"], node(b, var["y"], var["x"]))
    value = {"x": x, "y": y}
    bindings = [{"name": n, "value": value[n]} for n in declared]
    return {"original": {"bindings": bindings, "expr": expr},
            "transformed": {"bindings": [bindings[0], {"name": "z", "value": 7}, bindings[1]], "expr": expr}}


def observe(program, policy):
    reference = interpreter.evaluate(program)
    code = compiler.compile_program(program, policy)
    value, trace = vm.execute(code)
    return {"program": program, "reference_value": reference, "bytecode": code, "vm_value": value, "vm_trace": trace}


def finish():
    if not _state or len(_state["declared"]) != 2:
        raise RuntimeError("finish() before both declarations")
    c, declared = _state["config"], _state["declared"]
    order = "".join(declared).upper()
    observations = {kind: observe(p, c["impl"]) for kind, p in
                    programs(declared, c["xval"], c["yval"], c["shape"], c["op_a"], c["op_b"]).items()}
    checks, verdict = oracle.judge(observations["original"], observations["transformed"])
    fw_var = 0 if verdict == "PASS" else CARRIER
    case = f"P={c['impl']}|O={order}|H={c['shape']}|X={c['xval']}|Y={c['yval']}|A={c['op_a']}|B={c['op_b']}"
    rec = {"schema": "d14a.observation/v1", "contract": "v1", "case_id": case, "policy": c["impl"], "order": order,
           "shape": c["shape"], "x": c["xval"], "y": c["yval"], "op_a": c["op_a"], "op_b": c["op_b"],
           "declared": list(declared), "observations": observations, "checks": checks, "verdict": verdict, "fw_var": fw_var,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)", "source_sha256": dict(SOURCE_SHA256)}
    raw = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii")
    print(" ".join(["app=%s" % APP, "FW_VAR=%d" % fw_var, "case=%s" % case, "verdict=%s" % verdict,
                    "rec=%s" % base64.urlsafe_b64encode(raw).decode("ascii"),
                    "rec_sha256=%s" % hashlib.sha256(raw).hexdigest()]), flush=True)
    return fw_var
