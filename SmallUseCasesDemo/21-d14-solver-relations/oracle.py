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

"""D14c oracle: exhaustive, policy-blind checking of one solver result against the actual input bids.

CONTRACT.md v1. For a bid list it enumerates all 2^n subsets (pairwise item-set intersections checked
directly, no DP), giving the optimum, the number of feasible subsets (the empty one included) and every
optimal allocation (sorted ID lists, sorted). For a result it recomputes the selected allocation's
feasibility and value: value_correct = reported == actual; optimal = feasible and actual == optimum;
gap = optimum - actual for feasible results, else None. Unknown, duplicate or unsorted IDs and non-integer
values raise (an infrastructure error, never a verdict). relations() compares adjacent true optima and
adjacent reported values; PASS needs all three results feasible, value-correct and optimal, and all four
relations true.
"""
from itertools import combinations


def enumerate_subsets(bids):
    feasible, checks = [], 0
    for r in range(len(bids) + 1):
        for combo in combinations(bids, r):
            checks += 1
            if all(not set(a["items"]) & set(b["items"]) for a, b in combinations(combo, 2)):
                feasible.append((sum(b["value"] for b in combo), [b["id"] for b in combo]))
    optimum = max(v for v, _ in feasible)
    optimal = sorted(ids for v, ids in feasible if v == optimum)
    return {"optimum": optimum, "feasible_subsets": len(feasible), "optimal_allocations": optimal, "subset_checks": checks}


def observe(bids, result):
    ids = [b["id"] for b in bids]
    selected, reported = result.get("selected"), result.get("reported_value")
    if not isinstance(selected, list) or any(not isinstance(s, str) for s in selected) or selected != sorted(set(selected)) \
            or not set(selected) <= set(ids) or type(reported) is not int:
        raise ValueError(f"malformed solver result {result!r} for bids {ids}")
    chosen = [b for b in bids if b["id"] in selected]
    feasible = all(not set(a["items"]) & set(b["items"]) for a, b in combinations(chosen, 2))
    actual = sum(b["value"] for b in chosen)
    ref = enumerate_subsets(bids)
    return {"bids": bids, "selected": selected, "reported_value": reported, "actual_value": actual, "feasible": feasible,
            "value_correct": reported == actual, "optimum": ref["optimum"], "feasible_subsets": ref["feasible_subsets"],
            "optimal_allocations": ref["optimal_allocations"], "optimal": feasible and actual == ref["optimum"],
            "gap": ref["optimum"] - actual if feasible else None}, ref["subset_checks"]


def relations(base, relabeled, edited):
    return {"reference_relabel": base["optimum"] == relabeled["optimum"], "reference_edit": relabeled["optimum"] == edited["optimum"],
            "solver_relabel": base["reported_value"] == relabeled["reported_value"],
            "solver_edit": relabeled["reported_value"] == edited["reported_value"]}


def verdict(variants, rels):
    ok = all(v["feasible"] and v["value_correct"] and v["optimal"] for v in variants.values()) and all(rels.values())
    return "PASS" if ok else "DOMAIN_FAIL"
