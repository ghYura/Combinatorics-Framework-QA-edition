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

"""D14a fixture checks: literal reference controls (hand-computed, independent of any generated
expectation); all 432 cases against the frozen predictions and the verifier's model; reversed SUB
operands; both dead-code placement outcomes; a cancelling expression; statement-order invariance;
fresh state; malformed AST, bytecode and atoms; tampered reference/result records; the oracle's fixture
guard; the verifier's parser on a locally composed candidate (with a two-value DECL cell); policy
blindness; no eval/exec in the interpreter; independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_spec  # noqa: E402
import compiler  # noqa: E402
import explore  # noqa: E402
import interpreter  # noqa: E402
import oracle  # noqa: E402
import runtime  # noqa: E402
import verify  # noqa: E402
import vm  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}
X, Y = {"var": "x"}, {"var": "y"}


def node(op, left, right):
    return {"op": op, "left": left, "right": right}


def prog(bindings, expr):
    return {"bindings": [{"name": n, "value": v} for n, v in bindings], "expr": expr}


def parse(cid):
    f = dict(p.split("=", 1) for p in cid.split("|"))
    return f["P"], f["O"], f["H"], int(f["X"]), int(f["Y"]), f["A"], f["B"]


def run_case(cid):
    p, o, h, x, y, a, b = parse(cid)
    runtime._state.clear()
    runtime.begin()
    runtime.impl(p), runtime.xval(x), runtime.yval(y), runtime.shape(h), runtime.op_a(a), runtime.op_b(b)
    for n in o.lower():
        runtime.declare(n)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(t.split("=", 1) for t in lines[0].split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def vm_value(p, policy="faithful"):
    return vm.execute(compiler.compile_program(p, policy))[0]


def test_literal_reference_controls():
    """x=-1, y=2, written out by hand: (x+y)*x = -1; x+(y*x) = -3; (x-y)-x = -2."""
    b = [("x", -1), ("y", 2)]
    cases = [(node("*", node("+", X, Y), X), -1), (node("+", X, node("*", Y, X)), -3), (node("-", node("-", X, Y), X), -2)]
    for expr, want in cases:
        assert interpreter.evaluate(prog(b, expr)) == want
        assert vm_value(prog(b, expr)) == want
        assert verify.evaluate(prog(b, expr)) == want and explore.reference(prog(b, expr)) == want


def test_all_432_match_frozen_and_the_verifier_model():
    for cid, fz in FROZEN.items():
        fw, rec = run_case(cid)
        own = verify.own_case(*parse(cid))
        assert rec["observations"] == fz["observations"] == own["observations"] and rec["checks"] == fz["checks"]
        assert rec["verdict"] == fz["predicted_outcome"] == own["verdict"] and fw == (0 if rec["verdict"] == "PASS" else 2)
        assert [k for k, got, want in verify.compare_record(rec, own) if got != want] == []
        assert verify.recheck(rec) == rec["checks"]
    got = verify.tallies([run_case(c)[1] for c in FROZEN])
    assert {k: got[k] for k in ("outcomes", "by_policy", "failed_checks")} == {k: DERIVED[k] for k in ("outcomes", "by_policy", "failed_checks")}


def test_reversed_sub_operands_give_equal_wrong_outputs():
    _, rec = run_case("P=reverse_sub|O=XY|H=L|X=-1|Y=2|A=-|B=-")
    o, t = rec["observations"]["original"], rec["observations"]["transformed"]
    assert (o["vm_value"], t["vm_value"], o["reference_value"]) == (-4, -4, -2)
    assert rec["checks"] == {"original_differential": False, "transformed_differential": False, "metamorphic": True}
    assert o["bytecode"][4:] == [["LOAD", "x"], ["LOAD", "y"], ["LOAD", "x"], ["SUB"], ["SUB"], ["RETURN"]]
    _, ok = run_case("P=reverse_sub|O=XY|H=L|X=-1|Y=2|A=+|B=*")                    # no subtraction: identical to faithful
    assert ok["observations"] == run_case("P=faithful|O=XY|H=L|X=-1|Y=2|A=+|B=*")[1]["observations"]


def test_dead_code_placement_both_outcomes():
    _, xy = run_case("P=alias_dead_temp|O=XY|H=L|X=-1|Y=2|A=+|B=*")
    _, yx = run_case("P=alias_dead_temp|O=YX|H=L|X=-1|Y=2|A=+|B=*")
    assert [xy["observations"][k]["vm_value"] for k in ("original", "transformed")] == [-1, 63]
    assert xy["observations"]["transformed"]["vm_trace"][-1]["locals"] == {"x": 7, "y": 2}
    assert xy["checks"] == {"original_differential": True, "transformed_differential": False, "metamorphic": False}
    assert [yx["observations"][k]["vm_value"] for k in ("original", "transformed")] == [-1, -1] and yx["verdict"] == "PASS"
    assert [s["locals"].get("x") for s in yx["observations"]["transformed"]["vm_trace"][:6]] == [None, None, None, 7, 7, -1]   # restored


def test_cancelling_expression_hides_the_alias():
    _, rec = run_case("P=alias_dead_temp|O=XY|H=L|X=-1|Y=2|A=-|B=-")                 # (x - y) - x = -y
    t = rec["observations"]["transformed"]
    assert t["vm_trace"][-1]["locals"]["x"] == 7 and t["vm_value"] == -2 == t["reference_value"] and rec["verdict"] == "PASS"


def test_statement_order_invariance_and_fresh_state():
    for key in [("L", -1, 2, "+", "*"), ("R", 2, -1, "-", "-"), ("L", 2, 2, "*", "-")]:
        xy, yx = verify.own_case("faithful", "XY", *key), verify.own_case("faithful", "YX", *key)
        vals = {c["observations"][k][f] for c in (xy, yx) for k in ("original", "transformed") for f in ("reference_value", "vm_value")}
        assert len(vals) == 1
    vm.execute(compiler.compile_program(prog([("x", 1), ("y", 2)], node("+", X, Y)), "faithful"))
    with pytest.raises(vm.VMError):                                                   # nothing survives from the previous run
        vm.execute([["LOAD", "x"], ["RETURN"]])
    runtime._state.clear()
    runtime.begin()
    with pytest.raises(RuntimeError):
        runtime.begin()


@pytest.mark.parametrize("bad", [
    {"bindings": [], "expr": X},                                                      # unbound variable
    prog([("x", 1)], {"op": "/", "left": X, "right": X}),                             # unknown operator
    prog([("x", 1)], {"op": "+", "left": X}),                                         # missing child
    prog([("x", 1)], {"const": 3}),                                                   # unknown node
    {"bindings": [{"name": "x", "value": 1.5}], "expr": X},                           # non-integer constant
])
def test_malformed_ast_is_a_setup_error(bad):
    with pytest.raises(ValueError):
        interpreter.evaluate(bad)


@pytest.mark.parametrize("code", [
    [["LOAD", "x"], ["RETURN"]],                                                      # unbound
    [["ADD"], ["RETURN"]],                                                            # underflow
    [["PUSH", 1], ["PUSH", 2], ["RETURN"]],                                           # two items at RETURN
    [["PUSH", 1], ["RETURN"], ["PUSH", 2]],                                           # RETURN not final
    [["PUSH", 1]],                                                                    # no RETURN
    [["PUSH", 1], ["DIV"], ["RETURN"]],                                               # invalid instruction
    [["PUSH", "7"], ["RETURN"]],                                                      # non-integer
    [["STORE", "x"], ["RETURN"]],                                                     # STORE underflow
    [],
])
def test_malformed_bytecode_is_an_execution_error(code):
    with pytest.raises(vm.VMError):
        vm.execute(code)


@pytest.mark.parametrize("calls", [
    lambda r: (r.begin(), r.xval(2)),                                                 # out of order
    lambda r: (r.begin(), r.impl("optimizing")),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(3)),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(True)),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(2), r.yval(2), r.shape("M")),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(2), r.yval(2), r.shape("L"), r.op_a("/")),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(2), r.yval(2), r.shape("L"), r.op_a("+"), r.op_b("+"), r.declare("x"), r.declare("x")),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(2), r.yval(2), r.shape("L"), r.op_a("+"), r.op_b("+"), r.declare("z")),
    lambda r: (r.begin(), r.impl("faithful"), r.xval(2), r.yval(2), r.shape("L"), r.op_a("+"), r.op_b("+"), r.declare("x"), r.finish()),
    lambda r: (r.begin(), r.impl("faithful"), r.declare("x")),
])
def test_setup_errors_raise(calls):
    runtime._state.clear()
    with pytest.raises((RuntimeError, ValueError)):
        calls(runtime)


def test_oracle_guards_the_reference_fixture():
    good = {"reference_value": 3, "vm_value": 3}
    assert oracle.judge(good, dict(good)) == ({"original_differential": True, "transformed_differential": True, "metamorphic": True}, "PASS")
    with pytest.raises(ValueError):
        oracle.judge(good, {"reference_value": 4, "vm_value": 4})                     # a transformation that changed the result
    with pytest.raises(ValueError):
        oracle.judge(good, {"reference_value": 3, "vm_value": None})                  # missing evidence
    _, checks_verdict = oracle.judge({"reference_value": -2, "vm_value": -4}, {"reference_value": -2, "vm_value": -4})
    assert checks_verdict == "DOMAIN_FAIL"


def test_tampered_reference_or_result_records_are_detected():
    cid = "P=alias_dead_temp|O=XY|H=L|X=-1|Y=2|A=+|B=*"
    _, rec = run_case(cid)
    own = verify.own_case(*parse(cid))
    for path, value in ((("transformed", "vm_value"), -1), (("original", "reference_value"), 5), (("transformed", "vm_trace", 3, "locals"), {"x": -1})):
        t = copy.deepcopy(rec)
        target = t["observations"]
        for p_ in path[:-1]:
            target = target[p_]
        target[path[-1]] = value
        assert [k for k, g, w in verify.compare_record(t, own) if g != w]
    forged = copy.deepcopy(rec)
    forged["verdict"], forged["checks"] = "PASS", {k: True for k in verify.CHECKS}
    assert verify.recheck(forged) != forged["checks"] and ("verdict", "PASS", "DOMAIN_FAIL") in verify.compare_record(forged, own)
    moved = copy.deepcopy(rec)
    moved["observations"]["transformed"]["reference_value"] = 99
    assert verify.recheck(moved) is None


def test_verifier_parser_on_a_locally_composed_candidate():
    """Preflight: compose one candidate as the Reader renders it (DECL row = two values, then one ending)."""
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, extra = build_spec.layout(head)
    pick = {"IMPL": [1], "XVAL": [0], "YVAL": [1], "SHAPE": [0], "OP_A": [1], "OP_B": [1], "DECL": [1, 0]}
    cells = [[s[1][i] for i in pick.get(s[0], [0])] for s in slots]
    text = verify.join_cells(cells, [s[2] for s in slots])
    assert 'declare("y");declare("x");\n' in text
    calls, inlined = verify.parse_candidate(text)
    cid = verify.case_of(calls[:-1])
    assert calls[-1] == ["finish"] and cid == "P=reverse_sub|O=YX|H=L|X=-1|Y=2|A=-|B=-"
    assert {k: verify.sha256(v.encode()) for k, v in inlined.items()} == digests
    assert [verify.atom(v) for c in cells[1:-1] for v in c] == calls[:-1]
    assert dict((r[0], r[1:]) for r in extra)["DECL"] == ["FW_Permut()", "FW_Combi(size)"]
    r = subprocess.run([sys.executable, "-c", text], capture_output=True, text=True, timeout=60)
    tokens = dict(t.split("=", 1) for t in r.stdout.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert r.returncode == 0 and rec["case_id"] == cid and rec["verdict"] == FROZEN[cid]["predicted_outcome"] == "DOMAIN_FAIL"
    assert rec["observations"] == FROZEN[cid]["observations"] and rec["source_sha256"] == digests and rec["declared"] == ["y", "x"]
    with pytest.raises(ValueError):
        verify.parse_candidate(text.replace("_verdict = finish()", "_verdict = 0"))
    with pytest.raises(ValueError):
        verify.case_of(calls[:-2] + [["declare", "y"]])
    assert verify.join_cells([["a;"], ["b;", "c;"], ["T\n"]], ["", "\n", ""]) == "a;\nb;c;\nT\n"


def test_precheck_model_and_decl_permutations():
    assert explore.all_cases(["XY", "YX"]) == DERIVED["cases"]
    assert ["".join(p).upper() for p in __import__("itertools").permutations("xy")] == ["XY", "YX"]
    t = explore.tallies(DERIVED["cases"])
    assert t["wrong_agreements"] == 64 and t["original_correct_transformed_corrupted"] == 52 and t["alias_passes"] == {"XY": 20, "YX": 72}
    assert all(explore.leaves(c["observations"]["original"]["program"]["expr"]) == ["x", "y", "x"] for c in DERIVED["cases"])


def names_and_literals(path):
    tree = ast.parse((HERE / path).read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} \
        | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args}
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    return names, literals, imports


def test_vm_and_oracle_are_policy_blind_and_the_interpreter_never_compiles():
    for f in ("vm.py", "oracle.py"):
        names, literals, imports = names_and_literals(f)
        assert not any("policy" in n for n in names) and not literals & set(compiler.POLICIES) and not imports, f
    names, literals, imports = names_and_literals("oracle.py")
    assert not {"bytecode", "vm_trace", "program"} & literals                        # values only; bytecode is diagnostic
    names, literals, imports = names_and_literals("interpreter.py")
    assert not imports and not {"eval", "exec", "compile", "compile_program", "execute"} & names
    assert not {"PUSH", "STORE", "LOAD", "RETURN"} & literals


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"compiler", "vm", "interpreter", "oracle", "runtime", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
