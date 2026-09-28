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


"""Independent exploration for D14c (no solver, transform, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * inputs: the four instances, all six relabellings of goods {0,1,2} and the dominated-bid edit, rebuilt
    from CONTRACT.md;
  * proofs on every concrete input: relabelling is a bijection of feasible allocations preserving value;
    every feasible allocation containing b4 stays feasible, and gains 1, when b4 is replaced by b0;
  * predictions: exact and planted-mask DP answers as the maximum (value, ID tuple) over subsets that are
    feasible under the full (resp. smallest-item) mask rule; the greedy scan; the exhaustive optimum, feasible
    subset count and all optimal allocations; all 144 cases compared with architect-derived.json;
  * tallies: outcomes, greedy gaps, tied optima, failures whose solver outputs satisfy both output relations.
verify.py re-derives the same objects after the run and compares them with the observations.
"""
import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLE = {"bundle_trap": [({0, 1}, 7), ({0}, 4), ({1}, 4), ({2}, 2)], "tie": [({0, 1}, 8), ({0}, 4), ({1}, 4), ({2}, 2)],
         "disjoint": [({0}, 5), ({1}, 4), ({2}, 3), ({0, 1, 2}, 6)], "overlap": [({0, 1}, 6), ({1, 2}, 5), ({0, 2}, 4), ({2}, 2)]}
POLICIES = ("exact_dp", "greedy_value", "min_only_dp")
PERMS = [list(p) for p in itertools.permutations(range(3))]


def bids(name, perm=(0, 1, 2), edit="none"):
    out = [{"id": "b%d" % k, "items": sorted(perm[i] for i in items), "value": v} for k, (items, v) in enumerate(TABLE[name])]
    return out + ([{"id": "b4", "items": list(out[0]["items"]), "value": out[0]["value"] - 1}] if edit == "dominated" else [])


def subsets(bs):
    for mask in range(1 << len(bs)):
        yield [b for k, b in enumerate(bs) if mask >> k & 1]


def disjoint(sel, key=lambda b: b["items"]):
    seen = []
    for b in sel:
        seen += key(b)
    return len(seen) == len(set(seen))


def reference(bs):
    feas = [(sum(b["value"] for b in s), [b["id"] for b in s]) for s in subsets(bs) if disjoint(s)]
    top = max(v for v, _ in feas)
    return top, len(feas), sorted(ids for v, ids in feas if v == top), 1 << len(bs)


def predict(policy, bs):
    if policy == "greedy_value":
        taken, free = [], {0, 1, 2}
        for b in sorted(bs, key=lambda b: (-b["value"], b["id"])):
            if set(b["items"]) <= free:
                taken.append(b["id"])
                free -= set(b["items"])
        return sorted(taken)
    key = (lambda b: b["items"][:1]) if policy == "min_only_dp" else (lambda b: b["items"])
    return max((sum(b["value"] for b in s), tuple(b["id"] for b in s)) for s in subsets(bs) if disjoint(s, key))[1]


def observe(policy, bs):
    sel = list(predict(policy, bs))
    chosen = [b for b in bs if b["id"] in sel]
    value, feasible = sum(b["value"] for b in chosen), disjoint(chosen)
    top, nfeas, opts, _ = reference(bs)
    return {"bids": bs, "selected": sel, "reported_value": value, "actual_value": value, "feasible": feasible, "value_correct": True,
            "optimum": top, "feasible_subsets": nfeas, "optimal_allocations": opts, "optimal": feasible and value == top,
            "gap": top - value if feasible else None}


def case(policy, name, perm, edit):
    v = {"base": observe(policy, bids(name)), "relabeled": observe(policy, bids(name, perm)), "edited": observe(policy, bids(name, perm, edit))}
    rel = {"reference_relabel": v["base"]["optimum"] == v["relabeled"]["optimum"], "reference_edit": v["relabeled"]["optimum"] == v["edited"]["optimum"],
           "solver_relabel": v["base"]["reported_value"] == v["relabeled"]["reported_value"],
           "solver_edit": v["relabeled"]["reported_value"] == v["edited"]["reported_value"]}
    ok = all(x["feasible"] and x["value_correct"] and x["optimal"] for x in v.values()) and all(rel.values())
    return {"id": f"P={policy}|I={name}|R={''.join(map(str, perm))}|E={edit}", "policy": policy, "instance": name, "permutation": perm,
            "edit": edit, "variants": v, "relations": rel, "predicted_outcome": "PASS" if ok else "DOMAIN_FAIL"}


def proofs():
    relabel_ok, dominance_ok = True, True
    for name, perm in itertools.product(TABLE, PERMS):
        base, rel = bids(name), bids(name, perm)
        f_base = sorted((sum(b["value"] for b in s), tuple(b["id"] for b in s)) for s in subsets(base) if disjoint(s))
        f_rel = sorted((sum(b["value"] for b in s), tuple(b["id"] for b in s)) for s in subsets(rel) if disjoint(s))
        relabel_ok &= f_base == f_rel                                    # same ID sets are feasible, same values
        ed = bids(name, perm, "dominated")
        by_id = {b["id"]: b for b in ed}
        for s in subsets(ed):
            ids = [b["id"] for b in s]
            if disjoint(s) and "b4" in ids:
                swapped = [by_id["b0"] if b["id"] == "b4" else b for b in s]
                dominance_ok &= "b0" not in ids and disjoint(swapped) and sum(b["value"] for b in swapped) == sum(b["value"] for b in s) + 1
        dominance_ok &= reference(ed)[0] == reference(rel)[0]
    return {"relabel_bijection_on_all_24_inputs": relabel_ok, "dominated_swap_on_all_24_edited_inputs": dominance_ok}


def precheck():
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    cases = [case(*k) for k in itertools.product(POLICIES, TABLE, PERMS, ("none", "dominated"))]
    rep = {"schema": "d14c.precheck/v1", "note": "before execution; independent of the solver, transforms, oracle and runtime"}
    rep["cases_equal_frozen"] = cases == frozen["cases"]
    rep["proofs"] = proofs()
    rep["counts"] = {"cases": len(cases), "solver_calls": 3 * len(cases),
                     "subset_checks": sum(1 << len(v["bids"]) for c in cases for v in c["variants"].values())}
    rep["outcomes"] = dict(Counter(c["predicted_outcome"] for c in cases))
    rep["by_policy"] = {p: dict(Counter(c["predicted_outcome"] for c in cases if c["policy"] == p)) for p in POLICIES}
    rep["greedy_gaps"] = {n: sorted({v["gap"] for c in cases if c["policy"] == "greedy_value" and c["instance"] == n for v in c["variants"].values()})
                          for n in TABLE}
    rep["greedy_all_feasible"] = all(v["feasible"] for c in cases if c["policy"] == "greedy_value" for v in c["variants"].values())
    rep["min_only_fail_at_base"] = all(not c["variants"]["base"]["optimal"] for c in cases if c["policy"] == "min_only_dp")
    rep["output_relations_hold_but_fail"] = sum(1 for c in cases if c["predicted_outcome"] != "PASS"
                                                and c["relations"]["solver_relabel"] and c["relations"]["solver_edit"])
    tie = {p: [c["variants"]["base"]["selected"] for c in cases if c["policy"] == p and c["instance"] == "tie"][0] for p in POLICIES[:2]}
    rep["tie_selections"] = tie
    rep["tie_optima"] = reference(bids("tie"))[2]
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    (HERE / "precheck").mkdir(exist_ok=True)
    rep = precheck()
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    ok = (rep["cases_equal_frozen"] and all(rep["proofs"].values()) and rep["counts"] == {"cases": 144, "solver_calls": 432, "subset_checks": 8064}
          and rep["outcomes"] == {"PASS": 72, "DOMAIN_FAIL": 72}
          and rep["by_policy"] == {"exact_dp": {"PASS": 48}, "greedy_value": {"DOMAIN_FAIL": 24, "PASS": 24}, "min_only_dp": {"DOMAIN_FAIL": 48}}
          and rep["greedy_gaps"] == {"bundle_trap": [1], "tie": [0], "disjoint": [6], "overlap": [0]} and rep["greedy_all_feasible"]
          and rep["min_only_fail_at_base"] and rep["output_relations_hold_but_fail"] == 54
          and rep["tie_selections"] == {"exact_dp": ["b1", "b2", "b3"], "greedy_value": ["b0", "b3"]})
    print(json.dumps({k: rep[k] for k in ("cases_equal_frozen", "proofs", "counts", "outcomes", "greedy_gaps", "output_relations_hold_but_fail",
                                          "tie_selections", "tie_optima")} | {"ok": ok}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
