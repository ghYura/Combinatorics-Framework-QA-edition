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

"""D9 offline ranking of whole portfolios from OBSERVED evaluation costs (not the single-row Analyzer).

    python ranking.py --run evidence/<run-id>      # write evidence/<run-id>/ranking.json

Input guard: exactly one PASS observation for every one of 64 designs x 16 worlds; a missing world,
a duplicate, an unknown identity or a non-PASS record is rejected (nothing is filled, averaged or
renormalized). Objectives, all in exact rationals (serialized as numerator/denominator strings):
  minimax   sort by (worst total cost, uniform mean, bit string)
  expected  per profile uniform/calm/stress: sort by (weighted mean, worst cost, bit string);
            world weight = normalized demand weight x normalized disruption weight
  sensitivity  alpha = 0, 1/10, ..., 1 over the JOINT mixture (1-alpha)*calm + alpha*stress
"""
import argparse
import json
import re
from fractions import Fraction
from pathlib import Path

WORLDS = [(d, x) for d in range(4) for x in range(4)]
PROFILES = {"uniform": ([1, 1, 1, 1], [1, 1, 1, 1]), "calm": ([6, 2, 1, 1], [7, 1, 1, 1]), "stress": ([1, 1, 6, 2], [1, 2, 6, 1])}
ID_RE = re.compile(r"P=([01]{6})\|D=([0-3])\|X=([0-3])")


class RankingInputError(ValueError):
    pass


def q(x):
    x = Fraction(x)
    return {"n": str(x.numerator), "d": str(x.denominator)}


def cost_matrix(records):
    """{design: [16 observed total costs in world order]}, or RankingInputError."""
    seen = {}
    for r in records:
        m = ID_RE.fullmatch(r.get("case_id", ""))
        if not m or (r.get("design"), r.get("demand"), r.get("disruption")) != (m.group(1), int(m.group(2)), int(m.group(3))):
            raise RankingInputError(f"unknown identity {r.get('case_id')!r}")
        if r.get("verdict") != "PASS":
            raise RankingInputError(f"non-PASS observation {r['case_id']}")
        key = (m.group(1), int(m.group(2)), int(m.group(3)))
        if key in seen:
            raise RankingInputError(f"duplicate observation {r['case_id']}")
        seen[key] = r["total_cost"]
    designs = sorted({k[0] for k in seen})
    missing = [f"P={b}|D={d}|X={x}" for b in (format(i, "06b") for i in range(64)) for d, x in WORLDS if (b, d, x) not in seen]
    if missing or len(designs) != 64:
        raise RankingInputError(f"incomplete support: {len(missing)} missing, e.g. {missing[:3]}")
    return {b: [seen[(b, d, x)] for d, x in WORLDS] for b in designs}


def joint(profile):
    dw, xw = PROFILES[profile]
    return [Fraction(dw[d] * xw[x], sum(dw) * sum(xw)) for d, x in WORLDS]


def mean(costs, weights):
    return sum((Fraction(c) * w for c, w in zip(costs, weights)), Fraction(0))


def rank(matrix):
    w = {p: joint(p) for p in PROFILES}
    worst = {b: max(c) for b, c in matrix.items()}
    minimax = sorted(matrix, key=lambda b: (worst[b], mean(matrix[b], w["uniform"]), b))
    expected = {p: sorted(matrix, key=lambda b: (mean(matrix[b], wp), worst[b], b)) for p, wp in w.items()}
    sensitivity = []
    for k in range(11):
        a = Fraction(k, 10)
        wm = [(1 - a) * c + a * s for c, s in zip(w["calm"], w["stress"])]
        order = sorted(matrix, key=lambda b: (mean(matrix[b], wm), worst[b], b))
        sensitivity.append({"alpha": q(a), "ranking": order, "winner": order[0], "winner_expected": q(mean(matrix[order[0]], wm))})
    summaries = [{"design": b, "world_count": 16, "worst_cost": worst[b],
                  "worst_worlds": [[d, x] for (d, x), c in zip(WORLDS, matrix[b]) if c == worst[b]],
                  "expected": {p: q(mean(matrix[b], wp)) for p, wp in w.items()}} for b in sorted(matrix)]
    return {"schema": "d9.ranking/v1", "source": "observed total_cost of every design/world evaluation",
            "profiles": {p: {"demand_weights": PROFILES[p][0], "disruption_weights": PROFILES[p][1],
                             "world_weights": [q(x) for x in w[p]]} for p in PROFILES},
            "minimax_ranking": minimax, "minimax_primary_ties": [b for b in minimax if worst[b] == worst[minimax[0]]],
            "expected_rankings": expected, "sensitivity": sensitivity, "summaries": summaries}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    a = ap.parse_args()
    records = [json.loads(l) for l in (a.run / "observations.jsonl").read_text().splitlines() if l.strip()]
    doc = rank(cost_matrix(records))
    (a.run / "ranking.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"minimax": doc["minimax_ranking"][0], "ties": doc["minimax_primary_ties"],
                      "expected": {p: r[0] for p, r in doc["expected_rankings"].items()},
                      "sensitivity": [s["winner"] for s in doc["sensitivity"]]}))


if __name__ == "__main__":
    main()
