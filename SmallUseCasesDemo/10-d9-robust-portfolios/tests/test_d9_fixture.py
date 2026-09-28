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

"""D9 fixture checks: SUT, reference and verify.py's arithmetic against the frozen cases; the ranking
input guard (missing world, duplicate) and cost verification (altered total) as OFFLINE corruption
controls, not campaign cases; setup errors (BROKEN, never a verdict); independence; the builder.

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
import oracle  # noqa: E402
import ranking  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FIELDS = ("fixed_cost", "gross_loss", "reductions", "raw_loss", "residual_loss", "total_cost")


def observed_rows():
    return [{"case_id": c["id"], "design": c["design"], "selected": c["selected"], "demand": c["demand"], "disruption": c["disruption"],
             **{f: c[f] for f in FIELDS}, "verdict": "PASS"} for c in DERIVED["cases"]]


def test_three_formulations_agree_with_frozen():
    for c in DERIVED["cases"]:
        got = sut.evaluate(c["selected"], c["demand"], c["disruption"])
        ref = oracle.expected([int(b) for b in c["design"]], c["demand"], c["disruption"])
        mine = verify.payoff(c["design"], c["demand"], c["disruption"])
        assert all(got[f] == ref[f] == mine[f] == c[f] for f in FIELDS), c["id"]


def test_clamp_example():
    r = sut.evaluate(list(sut.MODULES), 3, 1)
    assert (r["raw_loss"], r["residual_loss"], r["fixed_cost"], r["total_cost"]) == (-3, 0, 28, 28)


def test_ranking_guard_rejects_missing_world():
    rows = observed_rows()
    rows = [r for r in rows if r["case_id"] != "P=110000|D=2|X=2"]
    with pytest.raises(ranking.RankingInputError):
        ranking.cost_matrix(rows)
    assert verify.guarded_costs(rows) is None


def test_ranking_guard_rejects_duplicate():
    rows = observed_rows()
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ranking.RankingInputError):
        ranking.cost_matrix(rows)
    assert verify.guarded_costs(rows) is None


def test_ranking_guard_rejects_non_pass_and_unknown():
    rows = observed_rows()
    rows[5]["verdict"] = "DOMAIN_FAIL"
    with pytest.raises(ranking.RankingInputError):
        ranking.cost_matrix(rows)
    rows = observed_rows()
    rows[0]["case_id"] = "P=0000000|D=0|X=0"
    with pytest.raises(ranking.RankingInputError):
        ranking.cost_matrix(rows)


def test_cost_verification_detects_altered_total():
    rows = observed_rows()
    assert all(verify.cost_ok(r) for r in rows)
    altered = dict(rows[100], total_cost=rows[100]["total_cost"] + 1)
    assert not verify.cost_ok(altered)


def test_rankings_match_frozen_from_costs():
    doc = ranking.rank(ranking.cost_matrix(observed_rows()))
    mine = verify.rankings_from(verify.guarded_costs(observed_rows()))
    for k in ("minimax_ranking", "minimax_primary_ties", "expected_rankings", "sensitivity", "summaries"):
        assert doc[k] == mine[k] == DERIVED[k]


@pytest.mark.parametrize("calls", [
    [("enable", "quota"), ("enable", "cache")],       # out of canonical order
    [("enable", "cache"), ("enable", "cache")],       # repeated
    [("enable", "sprinkler")],                        # unknown
    [("demand", 4)],
    [("demand", 0), ("disruption", -1)],
])
def test_setup_errors_raise(calls):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    with pytest.raises((RuntimeError, ValueError)):
        for fn, arg in calls:
            getattr(rt, fn)(arg)


def test_empty_design_record():
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.demand(0)
    rt.disruption(0)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert rt.finish() == 0
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert rec["case_id"] == "P=000000|D=0|X=0" and rec["selected"] == [] and rec["total_cost"] == 4


def test_reference_reads_no_policy_or_prediction():
    tree = ast.parse((HERE / "oracle.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports


def test_verifier_imports_nothing_from_the_implementation():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime", "ranking", "derive"}


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
