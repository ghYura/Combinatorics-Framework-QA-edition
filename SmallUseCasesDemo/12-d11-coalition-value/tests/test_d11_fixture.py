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

"""D11 fixture checks: SUT, reference and verify.py's values against the frozen cases; the allocation
input guard (missing, duplicate) and detection of an altered value; empty, null-player and symmetry
controls; setup errors; independence; the builder.

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
from fractions import Fraction
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import allocation  # noqa: E402
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())


def rows():
    return [{"case_id": c["id"], "mask": c["mask"], "value": c["value"], "verdict": "PASS"} for c in DERIVED["cases"]]


def test_three_routes_agree_with_frozen():
    for c in DERIVED["cases"]:
        got = sut.evaluate(c["members"])
        std, bon, val = oracle.expected([int(b) for b in c["mask"]])
        mine = verify.value_of(c["mask"])
        assert (got["standalone_value"], got["interaction_bonuses"], got["value"]) == (std, bon, val) == \
            (mine["standalone_value"], mine["interaction_bonuses"], mine["value"]) == \
            (c["standalone_value"], c["interaction_bonuses"], c["value"])


def test_empty_coalition_record():
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert rt.finish() == 0
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert (rec["case_id"], rec["members"], rec["value"]) == ("C=000000", [], 0)
    assert rec["interaction_bonuses"] == {"AB": 0, "ACD": 0, "BCD": 0}


def test_null_player_and_symmetry_controls():
    doc = allocation.allocate(allocation.observed_values(rows()))
    assert doc["checks"]["F_null"] and doc["checks"]["E_constant_4"]
    assert doc["checks"]["symmetry_AB"] and doc["checks"]["symmetry_CD"]
    assert doc["shapley"]["F"] == {"n": "0", "d": "1"} and doc["shapley"]["A"] == doc["shapley"]["B"]
    v = {r["mask"]: r["value"] for r in rows()}
    assert all(v[m[:-1] + "1"] == v[m] for m in v if m[-1] == "0")          # equal values, distinct identities


def test_guard_rejects_missing_and_duplicate():
    r = [x for x in rows() if x["case_id"] != "C=101100"]
    with pytest.raises(allocation.AllocationInputError):
        allocation.observed_values(r)
    assert verify.guarded_values(r) is None
    r = rows() + [copy.deepcopy(rows()[3])]
    with pytest.raises(allocation.AllocationInputError):
        allocation.observed_values(r)
    assert verify.guarded_values(r) is None


def test_altered_value_is_detected():
    r = rows()
    r[12]["value"] += 1
    mine = verify.value_of(r[12]["mask"])
    assert r[12]["value"] != mine["value"]
    certs = verify.certificates(verify.guarded_values(r))
    assert sum(certs["phi"].values()) == r[-1]["value"] and {k: str(v) for k, v in certs["phi"].items()} != \
        {p: str(Fraction(int(x["n"]), int(x["d"]))) for p, x in DERIVED["shapley"].items()}


def test_certificates_match_frozen():
    doc = allocation.allocate(allocation.observed_values(rows()))
    for k in ("shapley", "marginals", "permutations", "permutation_sums", "dividends", "standalone", "leave_one_out", "uniform_subset_marginals"):
        assert doc[k] == DERIVED[k], k
    assert all(doc["checks"].values())


@pytest.mark.parametrize("calls", [["B", "A"], ["A", "A"], ["G"]])
def test_setup_errors_raise(calls):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    with pytest.raises((RuntimeError, ValueError)):
        for p in calls:
            rt.enable(p)


def test_reference_is_independent():
    tree = ast.parse((HERE / "oracle.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports


def test_verifier_imports_nothing_from_the_implementation():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime", "allocation", "derive"}


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
