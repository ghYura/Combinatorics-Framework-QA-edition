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

"""D5 phase B fixture checks: SUT, reference and verify.py's model against the frozen cases; the
stack builder's happy paths and malformed sequences (BROKEN, never a verdict); reference blindness;
verifier independence; the pre-execution construction model; the builder's reproducibility.

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
import construct  # noqa: E402
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
AAN = [{"scope": "x", "children": [{"scope": "y", "children": ["A", "N"]}]}, "S", {"scope": "x", "children": ["A"]}, "N"]


def fresh_runtime():
    import runtime
    return importlib.reload(runtime)


def emit(rt, tree):
    rt.begin_pipeline()
    def walk(nodes):
        for n in nodes:
            if isinstance(n, str):
                rt.op(n)
            else:
                rt.open_scope(n["scope"])
                walk(n["children"])
                rt.close_scope()
    walk(tree)
    rt.end_pipeline()


def finish_record(rt, phase):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fw = rt.finish(phase)
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def test_models_match_frozen():
    for c in DERIVED["B1_cases"]:
        obs, trace = sut.evaluate(c["tree"], c["policy"])
        exp, ref = oracle.evaluate(c["tree"])
        assert (obs, exp) == (c["predicted"], c["expected"])
        assert verify.own_eval(c["tree"], c["policy"]) == (obs, trace) and verify.own_eval(c["tree"], "correct") == (exp, ref)
    for b in DERIVED["B2_cases"]:
        assert {t["id"]: sut.evaluate(t["tree"], b["policy"])[0] for t in DERIVED["trees"]} == b["predicted"]


def test_contract_example():
    assert sut.evaluate(AAN, "correct")[0] == {"x": 0, "y": -6}
    assert sut.evaluate(AAN, "flatten_scope")[0] == {"x": 5, "y": 5}
    assert sut.evaluate(AAN, "leak_scope")[0] == {"x": -3, "y": -9}


def test_same_record_is_exact():
    assert oracle.same_record({"x": 1, "y": 2}, {"x": 1, "y": 2})
    assert not oracle.same_record({"x": True, "y": 2}, {"x": 1, "y": 2})
    assert not oracle.same_record({"x": 1, "y": 2, "z": 3}, {"x": 1, "y": 2})


def test_b1_record():
    rt = fresh_runtime()
    rt.begin()
    rt.impl("leak_scope")
    emit(rt, AAN)
    fw, rec = finish_record(rt, "B1")
    assert fw == 2 and rec["case_id"] == "B1|leak_scope|ZIP=A|CAT=A|TAIL=N" and rec["result"]["observed"] == {"x": -3, "y": -9}
    assert rec["fragments"][0] == ["begin_pipeline"] and rec["fragments"][-1] == ["end_pipeline"] and len(rec["fragments"]) == 13


def test_b2_bundle_record():
    rt = fresh_runtime()
    rt.begin()
    rt.impl("correct")
    rt.begin_bundle()
    for t in DERIVED["trees"]:
        emit(rt, t["tree"])
    rt.seal_bundle()
    rt.end_bundle()
    fw, rec = finish_record(rt, "B2")
    assert fw == 0 and rec["case_id"] == "B2|correct|BUNDLE=all8" and len(rec["results"]) == 8 and rec["failing_trees"] == []


def run_calls(calls, phase=None):
    rt = fresh_runtime()
    rt.begin()
    rt.impl("correct")
    for c in calls:
        getattr(rt, c[0])(*c[1:])
    if phase:
        with contextlib.redirect_stdout(io.StringIO()):
            rt.finish(phase)


@pytest.mark.parametrize("calls,phase", [
    ([("op", "A")], None),                                                        # outside a pipeline
    ([("begin_pipeline",), ("close_scope",)], None),                             # close without open
    ([("begin_pipeline",), ("open_scope", "x"), ("end_pipeline",)], None),       # ends inside a scope
    ([("begin_pipeline",), ("begin_pipeline",)], None),                          # nested pipeline
    ([("begin_pipeline",), ("poison_tmp",)], None),                              # the TMP marker
    ([("begin_pipeline",), ("op", "Q")], None),
    ([("begin_pipeline",), ("open_scope", "z")], None),
    ([("begin_bundle",), ("seal_bundle",)], None),                               # seal with no pipeline
    ([("begin_bundle",), ("end_bundle",)], None),                                # end before seal
    ([("begin_pipeline",), ("end_pipeline",), ("begin_pipeline",)], None),       # second pipeline, no bundle
    ([("begin_pipeline",), ("op", "A"), ("end_pipeline",)], "B1"),               # tree outside the shape
    ([("begin_bundle",), ("begin_pipeline",), ("end_pipeline",), ("seal_bundle",), ("end_bundle",)], "B2"),   # not 8
])
def test_malformed_sequences_raise(calls, phase):
    with pytest.raises((RuntimeError, ValueError)):
        run_calls(calls, phase)


def test_bundle_rejects_duplicate_trees():
    rt = fresh_runtime()
    rt.begin()
    rt.impl("correct")
    rt.begin_bundle()
    for _ in range(8):
        emit(rt, AAN)
    rt.seal_bundle()
    rt.end_bundle()
    with pytest.raises(ValueError), contextlib.redirect_stdout(io.StringIO()):
        rt.finish("B2")


def test_reference_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert "policy" not in names and not imports


@pytest.mark.parametrize("tool", ["verify.py", "construct.py"])
def test_offline_tools_import_no_sut_reference_or_runtime(tool):
    tree = ast.parse((HERE / tool).read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime"}


@pytest.mark.parametrize("campaign", ["B1", "B2"])
def test_construction_precheck(campaign):
    rep = construct.precheck(campaign)
    assert rep["counts"] == {"E1": 2, "E2_after_subsets": 8, "E2_after_identity": 7, "E3": 2, "JZIP": 2, "JCAT": 4, "ROOT": 8}
    assert rep["row_lengths"] == {"E1_rows": [3], "JZIP": [6], "JCAT": [4], "ROOT": [13]}
    assert rep["trees_equal_frozen"] and rep["no_TMP_in_valid_rows"] and rep["reversed_rules_leave_TMP"]
    assert campaign == "B1" or rep["BUNDLE_length"] == 107


def test_splice_matches_core_parse():
    assert construct.splice('"[[" + TMP + ", "', lambda s: 17) == ("TMP", "[[17, ")
    assert construct.splice('", " + CLOSE + "]]"', lambda s: 22) == ("CLOSE", ", 22]]")
    assert construct.splice('"[[" + OPEN_X + ", "', lambda s: 21) == ("OPEN_X", "[[21, ")


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
