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

"""D8a fixture checks: runtime records against the frozen cases and verify.py's independent model;
comparator laws; the named mechanisms; setup errors (BROKEN, never a verdict); reference blindness;
offline-tool independence; the auxiliary allowed-order proof; the builder.

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
import allowed_orders  # noqa: E402
import oracle  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FIELDS = ("pages", "collected", "expected", "multiset_ok", "primary_order_ok", "stable_ties_ok", "terminated")


def run_case(policy, ranks, direction):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.impl(policy)
    rt.ranks(ranks)
    rt.direction(direction)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fw = rt.finish()
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def test_all_cases_match_frozen_and_verifier_model():
    for c in DERIVED["cases"]:
        fw, rec = run_case(c["policy"], "".join(map(str, c["ranks"])), c["direction"])
        own = verify.model(c["policy"], c["ranks"], c["direction"])
        assert all(rec[f] == c[f] == own[f] for f in FIELDS), c["id"]
        assert rec["verdict"] == c["predicted_outcome"] == own["verdict"] and rec["comparators_lawful"]
        assert rec["comparator_laws"] == own["comparator_laws"]


def test_named_mechanisms():
    ids = lambda p, r: [pg["ids"] for pg in run_case(p, r, "asc")[1]["pages"]]      # noqa: E731
    assert ids("score_only_cursor", "1110") == [["D", "A"], []]
    assert ids("stable_cursor", "1110") == [["D", "A"], ["B", "C"], []]
    assert ids("alternating_ties", "0000") == [["A", "B"], ["B", "A"], []]
    assert ids("alternating_ties", "0122") == [["A", "B"], ["D", "C"], []]


def test_laws_detect_an_unlawful_matrix():
    bad = [[0, -1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]      # not antisymmetric
    assert not oracle.comparator_laws(bad, [0, 0, 0, 0], "asc")["antisymmetric"]
    assert not verify.laws_of(bad, [0, 0, 0, 0], 1)["antisymmetric"]


@pytest.mark.parametrize("ranks", ["0123x", "013", "1111", "0022", "0124", ""])
def test_malformed_rank_vectors_are_setup_errors(ranks):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.impl("stable_cursor")
    with pytest.raises(ValueError):
        rt.ranks(ranks)


def test_reference_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "policy" not in names and not imports


def test_verifier_imports_nothing_from_the_implementation():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime", "derive", "allowed_orders"}


def test_rank_vectors_and_allowed_orders():
    vectors, by_k = verify.rank_vectors()
    assert by_k == {1: 1, 2: 14, 3: 36, 4: 24} and [list(v) for v in vectors] == DERIVED["rank_vectors"]
    doc = allowed_orders.proof()
    assert doc["summary"] == {"alternatives": 150, "valid": 150, "stable_rejected": 102, "stable_accepted": 48,
                              "rejected_exactly_the_tied": True}
    assert doc["rows"] == verify.allowed_orders(vectors)
    assert doc["example_0000_asc"]["alternative"] == ["D", "C", "B", "A"]


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
