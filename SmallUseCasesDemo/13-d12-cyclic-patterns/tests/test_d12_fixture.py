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

"""D12 fixture checks: SUT, reference and verify.py's scoring against the frozen cases; analysis input
guards (missing, duplicate); detection of an altered score and of a scorer that omits the wraparound
edge; setup errors; independence; the builder.

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
import analysis  # noqa: E402
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
KEYS = ("counts", "edge_counts", "transition_cost", "balance_penalty", "total_cost", "representative", "orbit_size", "period", "stabilizer_size")


def write_rows(tmp, campaign, words, mutate=None):
    by = {c["word"]: c for c in DERIVED["cases"]}
    rows = [dict(by[w], case_id=f"W={w}", campaign=campaign, verdict="PASS") for w in words]
    if mutate:
        rows = mutate(rows)
    d = tmp / campaign
    d.mkdir()
    (d / "observations.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return d


def test_three_routes_agree_with_frozen():
    for c in DERIVED["cases"]:
        got, ref, mine = sut.evaluate(c["word"]), oracle.expected(c["word"]), verify.score(c["word"])
        assert all(got[k] == ref[k] == mine[k] == c[k] for k in KEYS) and got["edge_costs"] == mine["edge_costs"] == c["edge_costs"]


def test_seam_scorer_without_wraparound_is_detected():
    assert verify.score("AAAAAB")["total_cost"] == verify.score("BAAAAA")["total_cost"] == 25
    assert (verify.open_score("AAAAAB"), verify.open_score("BAAAAA")) == (22, 25)       # depends on the starting position
    assert any(verify.open_score(c["word"]) != c["total_cost"] for c in DERIVED["cases"])


def test_altered_score_is_detected():
    c = dict(DERIVED["cases"][100])
    c["total_cost"] += 1
    assert verify.score(c["word"])["total_cost"] != c["total_cost"]


def test_guards_reject_missing_and_duplicate(tmp_path):
    words = [c["word"] for c in DERIVED["cases"]]
    d = write_rows(tmp_path, "words", words, lambda rows: rows[:-1])
    with pytest.raises(analysis.AnalysisInputError):
        analysis.analyse(d)
    assert verify.rows_of(d, "words", words)[0] is None
    d2 = tmp_path / "dup"
    d2.mkdir()
    d = write_rows(d2, "words", words, lambda rows: rows + [rows[0]])
    with pytest.raises(analysis.AnalysisInputError):
        analysis.analyse(d)
    assert verify.rows_of(d, "words", words)[0] is None


def test_analysis_matches_frozen(tmp_path):
    w = write_rows(tmp_path, "words", [c["word"] for c in DERIVED["cases"]])
    c = write_rows(tmp_path, "classes", DERIVED["representatives"])
    doc = json.loads(json.dumps(analysis.analyse(w, c)))
    assert doc["partition"]["orbits"] == DERIVED["orbits"] and doc["partition"]["self_reflection_classes"] == 54
    assert {k: v["mean"] for k, v in doc["populations"].items()} == DERIVED["means"]
    assert doc["ranking"] == DERIVED["ranking"] and doc["weighted_histogram_equals_words"]


@pytest.mark.parametrize("calls,campaign", [
    ([("place", 1, "A")], "words"),               # out of order
    ([("place", 0, "D")], "words"),               # outside the alphabet
    ([("pattern", "BAAAAA")], "classes"),         # not canonical
    ([("pattern", "ABC")], "classes"),            # malformed
])
def test_setup_errors_raise(calls, campaign):
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    with pytest.raises((RuntimeError, ValueError)):
        for c in calls:
            getattr(rt, c[0])(*c[1:])
        with contextlib.redirect_stdout(io.StringIO()):
            rt.finish(campaign)


def test_classes_record():
    import runtime
    rt = importlib.reload(runtime)
    rt.begin()
    rt.pattern("ABCABC")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert rt.finish("classes") == 0
    rec = json.loads(base64.urlsafe_b64decode(dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)["rec"]))
    assert (rec["campaign"], rec["total_cost"], rec["orbit_size"], rec["period"]) == ("classes", 0, 3, 3)


def test_reference_is_independent():
    tree = ast.parse((HERE / "oracle.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports


def test_verifier_imports_nothing_from_the_implementation():
    tree = ast.parse((HERE / "verify.py").read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime", "analysis", "derive"}


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
