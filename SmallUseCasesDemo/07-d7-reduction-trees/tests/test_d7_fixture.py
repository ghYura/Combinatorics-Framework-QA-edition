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

"""D7 fixture checks: SUT, reference and verify.py's independent routes against the frozen cases;
tree parsing and setup errors (BROKEN, never a numeric verdict); budgets and exact encodings;
reference blindness; verifier independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import importlib
import io
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
Q = lambda r: Fraction(int(r["n"]), int(r["d"]))       # noqa: E731


def fresh_runtime():
    import runtime
    return importlib.reload(runtime)


def run_case(policy, vid, tree):
    rt = fresh_runtime()
    v = DERIVED["vectors"][vid]
    rt.begin()
    rt.impl(policy)
    rt.vector(vid, tuple(v["hex"]), {p: (b["n"], b["d"]) for p, b in v["absolute_budgets"].items()})
    rt.tree(tree)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fw = rt.finish()
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def test_models_and_verifier_routes_match_frozen():
    rt = fresh_runtime()
    for c in DERIVED["cases"]:
        v = DERIVED["vectors"][c["vector"]]
        xs = [float.fromhex(h) for h in v["hex"]]
        t = rt.parse_tree(c["tree"])
        res, _ = sut.evaluate(c["policy"], t, xs)
        assert Fraction(res) == Q(c["predicted_result"]) and oracle.reference(v["hex"]) == Q(v["exact_sum"])
        tt = ast.literal_eval(c["tree"])
        if c["policy"] == "tree_binary64":
            assert verify.rounded_tree(tt, xs)[0].hex() == res.hex()
        elif c["policy"] == "flat_fsum":
            assert float(Q(v["exact_sum"])).hex() == res.hex()
        else:
            assert verify.exact_tree(tt, xs)[0] == res == Q(v["exact_sum"])


def test_budgets_are_the_contract_values():
    for vid, v in DERIVED["vectors"].items():
        b = {p: Q(x) for p, x in v["absolute_budgets"].items()}
        assert b["tree_binary64"] == verify.BINARY64_BUDGETS[vid] and b["tree_rational"] == 0
        assert b["flat_fsum"] == verify.half_ulp(float(Q(v["exact_sum"])))
    assert [Q(DERIVED["vectors"][v]["absolute_budgets"]["flat_fsum"]) for v in DERIVED["vectors"]] == \
        [Fraction(1, 2 ** 50), Fraction(1, 2 ** 52), Fraction(1, 2 ** 52), Fraction(1, 2 ** 53)]


def test_records():
    fw, rec = run_case("tree_binary64", "cancellation", "((((0,1),2),3),4)")
    assert fw == 2 and rec["result"] == {"hex": "0x1.0000000000000p+1"} and Q(rec["absolute_error"]) == 1 and len(rec["nodes"]) == 4
    fw, rec = run_case("tree_binary64", "swamped", "((0,((1,2),3)),4)")
    assert fw == 0 and Q(rec["absolute_error"]) == 1 == Q(rec["budget"])            # nonzero error, inclusive budget
    fw, rec = run_case("tree_rational", "decimal_inputs", "(0,(1,(2,(3,4))))")
    assert fw == 0 and Q(rec["result"]) == Q(DERIVED["vectors"]["decimal_inputs"]["exact_sum"]) != Fraction(3, 2)
    fw, rec = run_case("flat_fsum", "cancellation", "((((0,1),2),3),4)")
    assert fw == 0 and rec["nodes"] == [] and rec["result"] == {"hex": "0x1.8000000000000p+1"}


@pytest.mark.parametrize("text", ["((0,1),2)", "((((0,2),1),3),4)", "((((0,1),2),3),4",
                                  "(((0,1),2),(3,4),5)", "((((0,1),2),3),4)x", "(((( 0,1),2),3),4)", "((((0,0),2),3),4)"])
def test_malformed_trees_are_setup_errors(text):
    rt = fresh_runtime()
    with pytest.raises(ValueError):
        rt.parse_tree(text)


def test_nonfinite_is_domain_fail():
    err, finite, ok = oracle.judge(float("inf"), Fraction(3), Fraction(1))
    assert (err, finite, ok) == (None, False, False)


def test_reference_is_policy_and_tree_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not {"policy", "tree"} & names and imports <= {"math", "fractions"}


def test_verifier_imports_no_sut_reference_runtime_or_derive():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime", "derive"}


def test_fourteen_trees():
    ids = sorted(verify.tid(t) for t in verify.all_trees())
    assert ids == DERIVED["trees"] and len(set(ids)) == 14


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
