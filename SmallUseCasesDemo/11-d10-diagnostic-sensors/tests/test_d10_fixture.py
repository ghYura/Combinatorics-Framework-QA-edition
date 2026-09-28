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

"""D10 fixture checks: SUT, reference table and verify.py's arithmetic against the frozen cases; the
analysis input guards (missing, duplicate, corrupted reading); the declared healthy control; the
empty selection; refusal to identify within an alias pair; setup errors; independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import importlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import diagnosis  # noqa: E402
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())


def rows():
    return [{"case_id": c["id"], "mask": c["mask"], "fault": c["fault"], "readings": list(c["readings"]), "verdict": "PASS"}
            for c in DERIVED["cases"]]


def test_three_routes_agree_with_frozen():
    for c in DERIVED["cases"]:
        latent, readings = sut.observe(c["fault"], c["selected"])
        assert readings == oracle.expected_readings(c["fault"], c["selected"]) == verify.expect(c["mask"], c["fault"])["readings"] == c["readings"]
        assert latent == c["latent_bits"]


def test_healthy_control_is_declared_not_observed():
    latent, readings = sut.observe("H0", list(range(8)))
    assert latent == [0, 0, 0, 0] and readings == [0] * 8 == oracle.expected_readings("H0", list(range(8)))
    doc = diagnosis.analyse(rows())
    assert doc["classes"][0]["members"] == ["H0"] and "not a Framework observation" in doc["classes"][0]["source"]
    assert not any(r["fault"] == "H0" for r in rows())
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    with pytest.raises(ValueError):
        rt.fault("H0")                                   # not a campaign hypothesis


def test_empty_selection_record():
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.fault("F01")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert rt.finish() == 0
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert (rec["case_id"], rec["readings"], rec["signature"], rec["sensor_cost"]) == ("S=00000000|H=F01", [], "", 0)


def test_guard_rejects_missing():
    r = [x for x in rows() if x["case_id"] != "S=00001111|H=F09"]
    with pytest.raises(diagnosis.DiagnosisInputError):
        diagnosis.analyse(r)
    assert verify.matrix_guard(r) is None


def test_guard_rejects_duplicate():
    r = rows()
    r.append(copy.deepcopy(r[7]))
    with pytest.raises(diagnosis.DiagnosisInputError):
        diagnosis.analyse(r)
    assert verify.matrix_guard(r) is None


def test_guard_rejects_corrupted_reading():
    r = rows()
    victim = next(x for x in r if x["case_id"] == "S=00000011|H=F09")
    victim["readings"] = [1, 1]                         # not the projection of F09's full signature
    with pytest.raises(diagnosis.DiagnosisInputError):
        diagnosis.analyse(r)
    assert verify.matrix_guard(r) is None


def test_refuses_to_identify_within_an_alias_pair():
    doc = diagnosis.analyse(rows())
    full = {x["fault"]: x["readings"] for x in rows() if x["mask"] == "11111111"}
    assert full["F01"] == full["F02"]
    for f in ("F01", "F02"):
        assert diagnosis.identify(full[f], doc["classes"]) == {"class": 1, "members": ["F01", "F02"]}
    assert doc["unquotiented_label_min_distance"] == 0


def test_certificates_match_frozen():
    doc = diagnosis.analyse(rows())
    assert doc["suites"] == DERIVED["suites"] and doc["winners"] == DERIVED["winners"]
    assert doc["adaptive"] == DERIVED["adaptive"] and doc["noise"] == DERIVED["noise"]
    assert [w["cost"] for w in doc["winners"].values()] == [2, 4, 6, 7] and doc["adaptive"]["tree"]["cost"] == 3


@pytest.mark.parametrize("calls", [[("select", 3), ("select", 1)], [("select", 2), ("select", 2)], [("select", 8)], [("fault", "F13")]])
def test_setup_errors_raise(calls):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    with pytest.raises((RuntimeError, ValueError)):
        for fn, arg in calls:
            getattr(rt, fn)(arg)


def test_reference_is_literal_and_independent():
    tree = ast.parse((HERE / "oracle.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports and len(oracle.SIGNATURES) == 7 and all(len(r) == 8 for r in oracle.SIGNATURES)


def test_verifier_imports_nothing_from_the_implementation():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime", "diagnosis", "derive"}


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
