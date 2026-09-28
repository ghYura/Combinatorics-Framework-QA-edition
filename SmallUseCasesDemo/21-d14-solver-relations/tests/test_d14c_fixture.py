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

"""D14c fixture checks: both DPs against exhaustive enumeration on every frozen input (before launching);
all 144 cases against the frozen predictions and the verifier's model; tied optima accepted with different
selections; greedy gaps; infeasible min-only selections with invariant objectives; an actual symmetry
failure; the dominated-bid assumptions and feasible replacement; the empty feasible allocation; lost or
duplicated labels; a wrong objective; malformed results; tampering; the verifier's parser on a locally
composed candidate (three-value RELABEL cell); independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_spec  # noqa: E402
import explore  # noqa: E402
import oracle  # noqa: E402
import runtime  # noqa: E402
import solver  # noqa: E402
import transform  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}


def parse(cid):
    f = dict(p.split("=", 1) for p in cid.split("|"))
    return f["P"], f["I"], [int(c) for c in f["R"]], f["E"]


def run_case(cid):
    p, i, r, e = parse(cid)
    runtime._state.clear()
    runtime.begin()
    runtime.impl(p), runtime.instance(i)
    for g in r:
        runtime.label(g)
    runtime.edit(e)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(t.split("=", 1) for t in lines[0].split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"])), tokens["rec_sha256"]


def all_inputs():
    for name, perm, edit in itertools.product(transform.INSTANCES, itertools.permutations(range(3)), transform.EDITS):
        yield transform.apply_edit(transform.relabel(transform.base_bids(name), list(perm)), edit)


def test_dp_against_exhaustive_enumeration_on_every_frozen_input():
    n = 0
    for bids in all_inputs():
        ref = oracle.enumerate_subsets(bids)
        exact = solver.solve("exact_dp", bids)
        assert exact["reported_value"] == ref["optimum"] and exact["selected"] in ref["optimal_allocations"]
        assert exact["selected"] == max(ref["optimal_allocations"])                       # tie rule: lexicographically largest
        for policy, first_only in (("exact_dp", False), ("min_only_dp", True)):
            want = max(verify.packs(bids, first_only))
            got = solver.solve(policy, bids)
            assert (got["reported_value"], tuple(got["selected"])) == want
            n += 1
    assert n == 2 * 48                                                                   # 48 distinct inputs x 2 DP policies


def test_all_144_match_frozen_and_the_verifier_model():
    checks = 0
    for cid, fz in FROZEN.items():
        fw, rec, digest = run_case(cid)
        own = verify.own_case(*parse(cid))
        assert rec["variants"] == fz["variants"] == own["variants"] and rec["relations"] == fz["relations"]
        assert rec["verdict"] == fz["predicted_outcome"] == own["verdict"] and fw == (0 if rec["verdict"] == "PASS" else 2)
        assert [k for k, g, w in verify.compare_record(rec, own) if g != w] == []
        assert digest == verify.sha256(json.dumps(rec, sort_keys=True, separators=(",", ":")).encode("ascii"))
        checks += sum(rec["oracle_subset_checks"].values())
    assert checks == 8064


def test_tied_optima_accept_different_selections():
    _, ex, _ = run_case("P=exact_dp|I=tie|R=210|E=dominated")
    _, gr, _ = run_case("P=greedy_value|I=tie|R=210|E=dominated")
    assert ex["variants"]["base"]["selected"] == ["b1", "b2", "b3"] and gr["variants"]["base"]["selected"] == ["b0", "b3"]
    assert ex["variants"]["base"]["optimal_allocations"] == [["b0", "b3"], ["b1", "b2", "b3"]]
    assert ex["verdict"] == gr["verdict"] == "PASS" and ex["variants"]["base"]["reported_value"] == gr["variants"]["base"]["reported_value"] == 10


def test_greedy_gaps_are_measured_on_feasible_results():
    for inst, gap in (("bundle_trap", 1), ("disjoint", 6), ("tie", 0), ("overlap", 0)):
        _, rec, _ = run_case(f"P=greedy_value|I={inst}|R=012|E=none")
        assert {v["gap"] for v in rec["variants"].values()} == {gap} and all(v["feasible"] for v in rec["variants"].values())
        assert rec["verdict"] == ("PASS" if gap == 0 else "DOMAIN_FAIL")
    _, rec, _ = run_case("P=greedy_value|I=disjoint|R=012|E=dominated")
    assert rec["variants"]["base"]["selected"] == ["b3"] and rec["variants"]["base"]["optimum"] == 12 and rec["relations"]["solver_edit"]


def test_infeasible_min_only_selection_with_invariant_objectives():
    _, rec, _ = run_case("P=min_only_dp|I=bundle_trap|R=012|E=dominated")
    assert rec["relations"] == {"reference_relabel": True, "reference_edit": True, "solver_relabel": True, "solver_edit": True}
    assert not rec["variants"]["base"]["feasible"] and rec["variants"]["base"]["gap"] is None
    assert rec["variants"]["base"]["reported_value"] > rec["variants"]["base"]["optimum"] and rec["verdict"] == "DOMAIN_FAIL"


def test_an_actual_symmetry_failure():
    _, rec, _ = run_case("P=min_only_dp|I=disjoint|R=102|E=none")
    assert rec["relations"]["solver_relabel"] is False and rec["relations"]["reference_relabel"] is True
    assert rec["variants"]["base"]["reported_value"] != rec["variants"]["relabeled"]["reported_value"]


def test_dominated_bid_assumptions_and_feasible_replacement():
    for bids in (transform.relabel(transform.base_bids(n), list(p)) for n in transform.INSTANCES for p in itertools.permutations(range(3))):
        edited = transform.dominated(bids)
        b0, b4 = edited[0], edited[-1]
        assert b4["items"] == b0["items"] and b4["value"] == b0["value"] - 1 and b4["id"] == "b4"
        assert oracle.enumerate_subsets(edited)["optimum"] == oracle.enumerate_subsets(bids)["optimum"]
        assert all("b4" not in ids for ids in oracle.enumerate_subsets(edited)["optimal_allocations"])   # b4 is never optimal
    with pytest.raises(ValueError):
        transform.dominated([{"id": "b0", "items": [], "value": 5}])                                   # empty b0: relation invalid
    with pytest.raises(ValueError):
        transform.dominated([{"id": "b0", "items": [0], "value": 1}])                                  # b4 would have value 0


def test_empty_feasible_allocation():
    assert oracle.enumerate_subsets([]) == {"optimum": 0, "feasible_subsets": 1, "optimal_allocations": [[]], "subset_checks": 1}
    obs, checks = oracle.observe(transform.base_bids("tie"), {"selected": [], "reported_value": 0})
    assert obs["feasible"] and obs["gap"] == 10 and not obs["optimal"] and checks == 16
    assert solver.solve("exact_dp", []) == {"selected": [], "reported_value": 0} == solver.solve("greedy_value", [])


@pytest.mark.parametrize("labels", [[0, 0], [0, 1, 1], [3], [0, 1], [-1], ["0"], [True]])
def test_lost_or_duplicated_labels_are_setup_errors(labels):
    runtime._state.clear()
    runtime.begin(), runtime.impl("exact_dp"), runtime.instance("tie")
    with pytest.raises((ValueError, RuntimeError)):
        for g in labels:
            runtime.label(g)
        runtime.edit("none")
        runtime.finish()


@pytest.mark.parametrize("calls", [lambda r: (r.begin(), r.instance("tie")), lambda r: (r.begin(), r.impl("ilp")),
                                   lambda r: (r.begin(), r.impl("exact_dp"), r.instance("huge")),
                                   lambda r: (r.begin(), r.impl("exact_dp"), r.instance("tie"), r.edit("none")),
                                   lambda r: (r.begin(), r.impl("exact_dp"), r.instance("tie"), r.label(0), r.label(1), r.label(2), r.edit("swap")),
                                   lambda r: (r.begin(), r.begin())])
def test_atom_order_and_values(calls):
    runtime._state.clear()
    with pytest.raises((ValueError, RuntimeError)):
        calls(runtime)


def test_wrong_objective_is_a_domain_failure():
    bids = transform.base_bids("disjoint")
    obs, _ = oracle.observe(bids, {"selected": ["b0", "b1", "b2"], "reported_value": 13})
    assert obs["feasible"] and not obs["value_correct"] and obs["actual_value"] == 12 and obs["optimal"]
    assert oracle.verdict({"base": obs, "relabeled": obs, "edited": obs}, {k: True for k in ("a", "b")}) == "DOMAIN_FAIL"


@pytest.mark.parametrize("result", [{"selected": ["b9"], "reported_value": 1}, {"selected": ["b1", "b1"], "reported_value": 8},
                                    {"selected": ["b2", "b1"], "reported_value": 8}, {"selected": ["b1"], "reported_value": 4.0},
                                    {"selected": "b1", "reported_value": 4}, {"selected": ["b1"]}, {"reported_value": 4}])
def test_malformed_results_are_infrastructure_errors(result):
    with pytest.raises(ValueError):
        oracle.observe(transform.base_bids("tie"), result)


def test_tampering_is_detected():
    cid = "P=greedy_value|I=bundle_trap|R=012|E=none"
    _, rec, _ = run_case(cid)
    own = verify.own_case(*parse(cid))
    for path, value in ((("variants", "base", "gap"), 0), (("variants", "edited", "optimal"), True), (("relations", "solver_edit"), False),
                        (("verdict",), "PASS"), (("variants", "relabeled", "selected"), ["b1", "b2", "b3"])):
        t = copy.deepcopy(rec)
        tgt = t
        for k in path[:-1]:
            tgt = tgt[k]
        assert tgt[path[-1]] != value                                                  # a real alteration
        tgt[path[-1]] = value
        assert [k for k, g, w in verify.compare_record(t, own) if g != w]
    forged = copy.deepcopy(rec)
    forged["variants"]["base"]["optimal"] = True
    assert verify.recheck(forged)["base"]["optimal"] is False


def test_verifier_parser_on_a_locally_composed_candidate():
    """Preflight: compose one candidate as the Reader renders it (RELABEL row = three values, then one ending)."""
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, extra = build_spec.layout(head)
    pick = {"IMPL": [2], "INSTANCE": [2], "RELABEL": [1, 0, 2], "EDIT": [0]}          # min_only_dp, disjoint, R=102, none
    cells = [[s[1][i] for i in pick.get(s[0], [0])] for s in slots]
    text = verify.join_cells(cells, [s[2] for s in slots])
    assert "label(1);label(0);label(2);\n" in text
    calls, inlined = verify.parse_candidate(text)
    cid = verify.case_of(calls[:-1])
    assert calls[-1] == ["finish"] and cid == "P=min_only_dp|I=disjoint|R=102|E=none"
    assert {k: verify.sha256(v.encode()) for k, v in inlined.items()} == digests
    assert dict((r[0], r[1:]) for r in extra)["RELABEL"] == ["FW_Permut()", "FW_Combi(size)"]
    r = subprocess.run([sys.executable, "-c", text], capture_output=True, text=True, timeout=60)
    tokens = dict(t.split("=", 1) for t in r.stdout.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert r.returncode == 0 and rec["id"] == cid and rec["verdict"] == FROZEN[cid]["predicted_outcome"] == "DOMAIN_FAIL"
    assert rec["variants"] == FROZEN[cid]["variants"] and rec["source_sha256"] == digests and rec["permutation"] == [1, 0, 2]
    with pytest.raises(ValueError):
        verify.case_of(calls[:2] + [["label", 1], ["label", 1], ["label", 2]] + calls[5:6])
    with pytest.raises(ValueError):
        verify.parse_candidate(text.replace("_verdict = finish()", "_verdict = 0"))


def test_precheck_proofs():
    rep = explore.precheck()
    assert rep["cases_equal_frozen"] and all(rep["proofs"].values()) and rep["output_relations_hold_but_fail"] == 54


def test_oracle_is_policy_blind_and_uses_no_dp():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} \
        | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args}
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any("policy" in n or "mask" in n for n in names) and not literals & set(solver.POLICIES)
    assert imports <= {"itertools"}


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"solver", "transform", "oracle", "runtime", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
