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

"""D8b auxiliary proof: redundant forward edges preserve the complete set of topological orders (offline).

    python topo_orders.py           # write proof/topological-orders.json

For each of the 64 graphs, keep exactly the node permutations that satisfy every edge (315 pairs in
total). For every absent forward edge u->v already implied by a nonempty path, add it and compare
the COMPLETE order sets: all 31 eligible additions preserve them. This concerns order validity only;
a transitive edge changes the additive values. Not a Framework campaign; no candidates or attempts.
"""
import itertools
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = "ABCD"
SLOTS = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def orders(edges):
    return ["".join(IDS[v] for v in p) for p in itertools.permutations(range(4)) if all(p.index(u) < p.index(v) for u, v in edges)]


def reachable(edges, u, v):
    frontier, seen = [u], set()
    while frontier:
        x = frontier.pop()
        for a, b in edges:
            if a == x and b not in seen:
                seen.add(b)
                frontier.append(b)
    return v in seen


def proof():
    graphs, additions = [], []
    for bits in itertools.product((0, 1), repeat=6):
        code = "".join(map(str, bits))
        edges = [e for e, b in zip(SLOTS, bits) if b]
        o = orders(edges)
        graphs.append({"bits": code, "topological_orders": o})
        for k, (u, v) in enumerate(SLOTS):
            if not bits[k] and reachable(edges, u, v):
                after = list(bits)
                after[k] = 1
                o2 = orders(edges + [(u, v)])
                additions.append({"before": code, "after": "".join(map(str, after)), "added_edge": [u, v],
                                  "orders_before": o, "orders_after": o2, "equal_sets": o == o2,
                                  "lexicographic_minimum": [min(o), min(o2)]})
    example = next(a for a in additions if a["before"] == "100010" and a["after"] == "101010")
    summary = {"graphs": len(graphs), "graph_order_pairs": sum(len(g["topological_orders"]) for g in graphs),
               "eligible_additions": len(additions), "all_preserve_order_sets": all(a["equal_sets"] for a in additions),
               "equal_lexicographic_minima": all(a["lexicographic_minimum"][0] == a["lexicographic_minimum"][1] for a in additions),
               "example_100010_to_101010": {"ABCD_and_CABD_valid_before_and_after": all(x in example["orders_before"] and x in example["orders_after"]
                                                                                       for x in ("ABCD", "CABD")),
                                            "orders": example["orders_before"]}}
    return {"schema": "d8b.topological-orders/v1", "summary": summary, "graphs": graphs, "redundant_edge_additions": additions}


def main():
    doc = proof()
    (HERE / "proof").mkdir(exist_ok=True)
    (HERE / "proof" / "topological-orders.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(doc["summary"]))


if __name__ == "__main__":
    main()
