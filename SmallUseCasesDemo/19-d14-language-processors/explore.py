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


"""Independent model exploration for D14a (no compiler, VM, interpreter, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * literal reference controls at x=-1, y=2 (hand-computed): L(+,*) = -1, R(+,*) = -3, L(-,-) = -2;
  * DECL: native FW_Permut() over the two declarations yields exactly the two orders XY and YX;
  * the model: all 432 cases, each with two programs (864 compiled variants / VM executions and 864
    reference evaluations), rebuilt from CONTRACT.md with an own evaluator, emitter and stack machine
    and compared field by field with architect-derived.json (ASTs, bytecode, traces, values, checks);
  * tallies: policy x order x shape, each check's failures, wrong agreements, dead-code outcomes.
verify.py re-derives the same objects after the run and compares them with the observations.
"""
import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICIES = ("faithful", "reverse_sub", "alias_dead_temp")
CHECKS = ("original_differential", "transformed_differential", "metamorphic")
ARITH = {"+": ("ADD", int.__add__), "-": ("SUB", int.__sub__), "*": ("MUL", int.__mul__)}
BY_OPCODE = {code: fn for code, fn in ARITH.values()}


def tree(shape, a, b):
    """L: (x A y) B x; R: x A (y B x). The third leaf is always the variable x."""
    x, y = {"var": "x"}, {"var": "y"}
    if shape == "L":
        return {"op": b, "left": {"op": a, "left": x, "right": y}, "right": x}
    return {"op": a, "left": x, "right": {"op": b, "left": y, "right": x}}


def leaves(node):
    return [node["var"]] if "var" in node else leaves(node["left"]) + leaves(node["right"])


def value_of(node, env):
    if "var" in node:
        return env[node["var"]]
    return ARITH[node["op"]][1](value_of(node["left"], env), value_of(node["right"], env))


def reference(program):
    env = {}
    for b in program["bindings"]:
        env[b["name"]] = b["value"]
    return value_of(program["expr"], env)


def emit(program, policy):
    out = []
    for b in program["bindings"]:
        out.append(["PUSH", b["value"]])
        out.append(["STORE", "x" if (policy == "alias_dead_temp" and b["name"] == "z") else b["name"]])

    def walk(node):
        if "var" in node:
            out.append(["LOAD", node["var"]])
        else:
            first, second = (node["right"], node["left"]) if (policy == "reverse_sub" and node["op"] == "-") else (node["left"], node["right"])
            walk(first)
            walk(second)
            out.append([ARITH[node["op"]][0]])
    walk(program["expr"])
    out.append(["RETURN"])
    return out


def machine(code):
    stack, env, trace, ret = [], {}, [], None
    for ip, ins in enumerate(code):
        if ins[0] == "PUSH":
            stack = stack + [ins[1]]
        elif ins[0] == "STORE":
            env = {**env, ins[1]: stack[-1]}
            stack = stack[:-1]
        elif ins[0] == "LOAD":
            stack = stack + [env[ins[1]]]
        elif ins[0] == "RETURN":
            assert ip == len(code) - 1 and len(stack) == 1
            ret, stack = stack[0], []
        else:
            stack = stack[:-2] + [BY_OPCODE[ins[0]](stack[-2], stack[-1])]
        trace.append({"ip": ip, "instruction": list(ins), "stack": list(stack), "locals": dict(env), "returned": ret})
    return ret, trace


def model_case(policy, order, shape, x, y, a, b):
    value = {"x": x, "y": y}
    first, second = [{"name": n, "value": value[n]} for n in order.lower()]
    expr = tree(shape, a, b)
    progs = {"original": {"bindings": [first, second], "expr": expr},
             "transformed": {"bindings": [first, {"name": "z", "value": 7}, second], "expr": expr}}
    obs = {}
    for kind, prog in progs.items():
        code = emit(prog, policy)
        vm_value, trace = machine(code)
        obs[kind] = {"program": prog, "reference_value": reference(prog), "bytecode": code, "vm_value": vm_value, "vm_trace": trace}
    o, t = obs["original"], obs["transformed"]
    checks = {"original_differential": o["vm_value"] == o["reference_value"], "transformed_differential": t["vm_value"] == t["reference_value"],
              "metamorphic": o["vm_value"] == t["vm_value"]}
    return {"id": f"P={policy}|O={order}|H={shape}|X={x}|Y={y}|A={a}|B={b}", "policy": policy, "order": order, "shape": shape,
            "x": x, "y": y, "op_a": a, "op_b": b, "observations": obs, "checks": checks,
            "predicted_outcome": "PASS" if all(checks.values()) else "DOMAIN_FAIL"}


def all_cases(decl_orders):
    return [model_case(*k) for k in itertools.product(POLICIES, decl_orders, ("L", "R"), (-1, 2), (-1, 2), "+-*", "+-*")]


def tallies(cases):
    return {"outcomes": dict(Counter(c["predicted_outcome"] for c in cases)),
            "by_policy": {p: dict(Counter(c["predicted_outcome"] for c in cases if c["policy"] == p)) for p in POLICIES},
            "failed_checks": {p: {k: sum(not c["checks"][k] for c in cases if c["policy"] == p) for k in CHECKS} for p in POLICIES},
            "by_policy_order_shape": {f"{p}|{o}|{h}": dict(Counter(c["predicted_outcome"] for c in cases if (c["policy"], c["order"], c["shape"]) == (p, o, h)))
                                      for p in POLICIES for o in ("XY", "YX") for h in ("L", "R")},
            "wrong_agreements": sum(1 for c in cases if c["checks"]["metamorphic"] and not c["checks"]["original_differential"]),
            "original_correct_transformed_corrupted": sum(1 for c in cases if c["checks"]["original_differential"] and not c["checks"]["transformed_differential"]),
            "alias_passes": {o: sum(1 for c in cases if c["policy"] == "alias_dead_temp" and c["order"] == o and c["predicted_outcome"] == "PASS") for o in ("XY", "YX")},
            "alias_xy_cancelling_passes": sum(1 for c in cases if c["policy"] == "alias_dead_temp" and c["order"] == "XY" and c["predicted_outcome"] == "PASS"
                                              and len({value_of(tree(c["shape"], c["op_a"], c["op_b"]), {"x": v, "y": c["y"]}) for v in (-1, 2, 7, 11)}) == 1)}


def precheck():
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    rep = {"schema": "d14a.precheck/v1", "note": "before execution; independent of the compiler, VM, interpreter, oracle and runtime"}
    env = {"x": -1, "y": 2}
    rep["literal_controls"] = {"L(+,*)": value_of(tree("L", "+", "*"), env), "R(+,*)": value_of(tree("R", "+", "*"), env),
                               "L(-,-)": value_of(tree("L", "-", "-"), env)}
    decl = ["".join(p).upper() for p in itertools.permutations("xy")]
    rep["decl_permutations"] = decl
    cases = all_cases(decl)
    rep["counts"] = {"cases": len(cases), "program_variants": 2 * len(cases), "vm_executions": 2 * len(cases),
                     "reference_evaluations": 2 * len(cases), "distinct_ids": len({c["id"] for c in cases})}
    rep["cases_equal_frozen"] = cases == frozen["cases"]
    rep["reference_agreement"] = all(c["observations"]["original"]["reference_value"] == c["observations"]["transformed"]["reference_value"] for c in cases)
    rep["third_leaf_is_x"] = all(leaves(c["observations"][k]["program"]["expr"]) == ["x", "y", "x"] for c in cases for k in ("original", "transformed"))
    rep["reference_order_invariant"] = all(model_case("faithful", "XY", *k)["observations"]["original"]["reference_value"]
                                           == model_case("faithful", "YX", *k)["observations"]["original"]["reference_value"]
                                           for k in itertools.product(("L", "R"), (-1, 2), (-1, 2), "+-*", "+-*"))
    rep["tallies"] = t = tallies(cases)
    rep["tallies_equal_frozen"] = {k: t[k] for k in ("outcomes", "by_policy", "failed_checks")} == \
        {k: frozen[k] for k in ("outcomes", "by_policy", "failed_checks")}
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    (HERE / "precheck").mkdir(exist_ok=True)
    rep = precheck()
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    ok = (rep["literal_controls"] == {"L(+,*)": -1, "R(+,*)": -3, "L(-,-)": -2} and rep["decl_permutations"] == ["XY", "YX"]
          and rep["counts"] == {"cases": 432, "program_variants": 864, "vm_executions": 864, "reference_evaluations": 864, "distinct_ids": 432}
          and rep["cases_equal_frozen"] and rep["reference_agreement"] and rep["third_leaf_is_x"] and rep["reference_order_invariant"]
          and rep["tallies_equal_frozen"] and rep["tallies"]["outcomes"] == {"PASS": 316, "DOMAIN_FAIL": 116}
          and rep["tallies"]["wrong_agreements"] == 64 and rep["tallies"]["alias_passes"] == {"XY": 20, "YX": 72}
          and rep["tallies"]["alias_xy_cancelling_passes"] == 20)
    print(json.dumps({k: rep[k] for k in ("literal_controls", "decl_permutations", "counts", "cases_equal_frozen", "reference_agreement",
                                          "third_leaf_is_x", "reference_order_invariant", "tallies_equal_frozen")}
                     | {"outcomes": rep["tallies"]["outcomes"], "wrong_agreements": rep["tallies"]["wrong_agreements"],
                        "alias_passes": rep["tallies"]["alias_passes"], "alias_xy_cancelling_passes": rep["tallies"]["alias_xy_cancelling_passes"], "ok": ok}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
