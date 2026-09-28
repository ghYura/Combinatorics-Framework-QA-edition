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

"""D8b fixture checks: runtime records against the frozen cases and verify.py's independent model;
path counts by two routes; witnesses; setup errors (BROKEN, never a verdict); reference blindness;
offline-tool independence; the topological-order proof; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import importlib
import io
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import oracle  # noqa: E402
import topo_orders  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())


def run_case(policy, bits, edit):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.impl(policy)
    for (u, v), b in zip(rt.SLOTS, bits):
        rt.edge("ABCD"[u], "ABCD"[v], b)
    rt.edit(edit)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fw = rt.finish()
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def test_all_cases_match_frozen_and_verifier_model():
    for c in DERIVED["cases"]:
        fw, rec = run_case(c["policy"], c["bits"], c["edit"])
        own = verify.model(c["policy"], tuple(c["bits"]), "ABCD".index(c["edit"]))
        assert all(rec[f] == c[f] == own[f] for f in verify.FIELDS), c["id"]
        assert rec["verdict"] == c["predicted_outcome"] == own["verdict"] and rec["before_reference"] == c["before_values"]


def test_path_counts_two_routes():
    for bits in itertools.product((0, 1), repeat=6):
        edges = [e for e, b in zip(verify.SLOTS, bits) if b]
        assert oracle.path_counts(edges) == verify.paths_of(edges)
        assert oracle.fresh(edges, verify.BASE) == verify.fresh(verify.BASE, verify.paths_of(edges))


def test_witnesses():
    assert run_case("direct_only", [1, 0, 0, 1, 0, 0], "A")[1]["mismatched_nodes"] == ["C"]
    assert run_case("closure_forward", [1, 0, 0, 1, 0, 0], "A")[1]["verdict"] == "PASS"
    rec = run_case("closure_reverse", [1, 0, 0, 1, 0, 0], "A")[1]
    assert rec["evaluation_order"] == ["C", "B", "A"] and rec["verdict"] == "DOMAIN_FAIL"
    assert run_case("direct_only", [1, 1, 0, 1, 0, 0], "A")[1]["verdict"] == "PASS"
    rec = run_case("closure_forward", [1] * 6, "A")[1]
    assert rec["path_counts"][0][3] == 4 and rec["after_values"][3] - rec["before_values"][3] == 40


@pytest.mark.parametrize("calls", [
    [("edge", "A", "C", 0)],                     # slot 0 must be AB
    [("edge", "A", "B", 2)],                     # not a bit
    [("edge", "B", "A", 1)],                     # backward edge
    [("edit", "A")],                             # edit before the edges
])
def test_setup_errors_raise(calls):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.impl("closure_forward")
    with pytest.raises((RuntimeError, ValueError)):
        for c in calls:
            getattr(rt, c[0])(*c[1:])


def test_unknown_edit_node_raises():
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.impl("closure_forward")
    for u, v in rt.SLOTS:
        rt.edge("ABCD"[u], "ABCD"[v], 0)
    with pytest.raises(ValueError):
        rt.edit("E")


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
    assert not imports & {"sut", "oracle", "runtime", "derive", "topo_orders"}


def test_topological_order_proof():
    doc = topo_orders.proof()
    graphs, adds = verify.topo_proof()
    assert doc["graphs"] == graphs == DERIVED["topology_proof"]["graphs"] and doc["redundant_edge_additions"] == adds
    assert doc["summary"]["graph_order_pairs"] == 315 and doc["summary"]["eligible_additions"] == 31
    assert doc["summary"]["all_preserve_order_sets"] and doc["summary"]["example_100010_to_101010"]["ABCD_and_CABD_valid_before_and_after"]


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
