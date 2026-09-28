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

"""D5 phase A fixture checks: SUT and reference against the frozen cases and verify.py's own model,
malformed fragment orders raising (BROKEN, never a verdict), reference blindness, verifier
independence and the builder's reproducibility.

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
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE.parent / "architect-derived-A.json").read_text())


def fresh_runtime():
    import runtime
    return importlib.reload(runtime)


def test_sut_and_reference_match_frozen_and_verifier_model():
    assert len(DERIVED["cases"]) == 72
    for c in DERIVED["cases"]:
        observed, trace = sut.adapt(dict(DERIVED["input_record"]), c["tree"], c["policy"])
        expected, ref = oracle.evaluate(dict(DERIVED["input_record"]), c["tree"])
        verdict = "PASS" if oracle.same_record(observed, expected) else "DOMAIN_FAIL"
        m = verify.model(c["tree"], c["policy"])
        assert (observed, expected, verdict) == (c["predicted"], c["expected"], c["predicted_outcome"])
        assert (expected, ref, observed, trace, verdict) == m


def test_contract_witness_values():
    t = {"field": "x", "ops": ["A", "M"]}
    assert sut.adapt({"x": 2, "y": 5}, t, "correct")[0] == {"x": 6, "y": 5}
    assert sut.adapt({"x": 2, "y": 5}, t, "reverse_pair")[0] == {"x": 5, "y": 5}
    assert sut.adapt({"x": 2, "y": 5}, t, "wrong_field")[0] == {"x": 2, "y": 12}
    out, trace = sut.adapt({"x": 2, "y": 5}, {"field": "x", "ops": ["A", "S"]}, "reverse_pair")
    assert out == {"x": 0, "y": 5} and [s["op"] for s in trace] == ["S", "A"]


def test_same_record_is_exact():
    assert oracle.same_record({"x": 1, "y": 2}, {"x": 1, "y": 2})
    assert not oracle.same_record({"x": True, "y": 2}, {"x": 1, "y": 2})
    assert not oracle.same_record({"x": 1, "y": 2, "z": 0}, {"x": 1, "y": 2})
    assert not oracle.same_record({"x": 1.0, "y": 2}, {"x": 1, "y": 2})


def test_runtime_emits_one_record():
    rt = fresh_runtime()
    rt.begin()
    rt.impl("reverse_pair")
    rt.push_op("A")
    rt.push_op("M")
    rt.bind("x")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert rt.finish("A") == 2
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert rec["case_id"] == "A|reverse_pair|OPS=AM|FIELD=x" and rec["observed"] == {"x": 5, "y": 5}
    assert rec["fragments"] == [["push_op", "A"], ["push_op", "M"], ["bind", "x"]] and rec["verdict"] == "DOMAIN_FAIL"


@pytest.mark.parametrize("calls", [
    [("push_op", "A")],                                                 # before impl
    [("impl", "correct"), ("bind", "x")],                               # bind with no operations
    [("impl", "correct"), ("push_op", "A"), ("bind", "x")],             # bind with one operation
    [("impl", "correct"), ("push_op", "A"), ("push_op", "M"), ("push_op", "S")],
    [("impl", "correct"), ("push_op", "A"), ("push_op", "M"), ("bind", "x"), ("push_op", "S")],
    [("impl", "correct"), ("push_op", "A"), ("push_op", "M"), ("bind", "x"), ("bind", "y")],
    [("impl", "correct"), ("push_op", "Q")],
    [("impl", "correct"), ("push_op", "A"), ("push_op", "M"), ("bind", "z")],
    [("impl", "nope")],
    [("impl", "correct"), ("impl", "correct")],
])
def test_malformed_sequences_raise(calls):
    rt = fresh_runtime()
    rt.begin()
    with pytest.raises((RuntimeError, ValueError)):
        for fn, arg in calls:
            getattr(rt, fn)(arg)


@pytest.mark.parametrize("calls", [
    [("impl", "correct"), ("push_op", "A"), ("push_op", "A"), ("bind", "x")],     # not distinct
    [("impl", "correct"), ("push_op", "A"), ("push_op", "M")],                    # never bound
])
def test_finish_rejects_malformed_trees(calls):
    rt = fresh_runtime()
    rt.begin()
    for fn, arg in calls:
        getattr(rt, fn)(arg)
    with pytest.raises(ValueError):
        rt.finish("A")


def test_reference_is_policy_blind_and_independent():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert "policy" not in names and not imports


def test_verifier_imports_no_sut_reference_or_runtime():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime"}


def test_verifier_enumeration_counts():
    pairs, ordered, trees = verify.trees()
    assert (len(pairs), len(ordered), len(trees)) == (6, 12, 24)
    assert len({(tuple(t["ops"]), t["field"]) for t in trees}) == 24


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
