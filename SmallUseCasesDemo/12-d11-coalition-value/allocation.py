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

"""D11 offline allocation from OBSERVED coalition values (not a Framework calculation).

    python allocation.py --run evidence/<run-id>     # write evidence/<run-id>/allocation.json

Input guard: exactly one PASS observation for each of the 64 coalitions, known identities only;
nothing is inferred and equal-value rows are never merged. Certificates, in exact fractions
(numerator/denominator strings): the Shapley value from 192 weighted marginals, the average of
sequential marginals over all 720 player orders, and the equal split of subset dividends. Also the
comparison scores: standalone values, grand-coalition leave-one-out differences and the unweighted
mean of each player's 32 marginals (a different rule, not Shapley).
"""
import argparse
import itertools
import json
import math
import re
from fractions import Fraction
from pathlib import Path

PLAYERS = "ABCDEF"
ID_RE = re.compile(r"C=([01]{6})")


class AllocationInputError(ValueError):
    pass


def q(x):
    x = Fraction(x)
    return {"n": str(x.numerator), "d": str(x.denominator)}


def observed_values(records):
    values = {}
    for r in records:
        m = ID_RE.fullmatch(r.get("case_id", ""))
        if not m or r.get("mask") != m.group(1):
            raise AllocationInputError(f"unknown identity {r.get('case_id')!r}")
        if r.get("verdict") != "PASS":
            raise AllocationInputError(f"non-PASS observation {r['case_id']}")
        if m.group(1) in values:
            raise AllocationInputError(f"duplicate observation {r['case_id']}")
        values[m.group(1)] = r["value"]
    missing = [f"{i:06b}" for i in range(64) if f"{i:06b}" not in values]
    if missing:
        raise AllocationInputError(f"missing coalitions {missing[:4]}")
    return values


def mask_of(s):
    return "".join("1" if p in s else "0" for p in PLAYERS)


def allocate(values):
    coalitions = [{p for p, b in zip(PLAYERS, bits) if b} for bits in itertools.product((0, 1), repeat=6)]
    v = lambda s: values[mask_of(s)]                     # noqa: E731
    phi, rows = {p: Fraction(0) for p in PLAYERS}, []
    for p in PLAYERS:
        for s in coalitions:
            if p not in s:
                w = Fraction(math.factorial(len(s)) * math.factorial(5 - len(s)), math.factorial(6))
                m = v(s | {p}) - v(s)
                phi[p] += w * m
                rows.append({"player": p, "coalition": mask_of(s), "weight": q(w), "marginal": m})
    orders, sums = [], {p: 0 for p in PLAYERS}
    for perm in itertools.permutations(PLAYERS):
        s, inc = set(), []
        for p in perm:
            m = v(s | {p}) - v(s)
            sums[p] += m
            inc.append(m)
            s.add(p)
        orders.append({"order": "".join(perm), "marginals": inc})
    dividends = {}
    for s in sorted(coalitions, key=lambda s: (len(s), mask_of(s))):
        dividends[mask_of(s)] = v(s) - sum(d for k, d in dividends.items() if {p for p, b in zip(PLAYERS, k) if b == "1"} < s)
    split = {p: sum((Fraction(d, k.count("1")) for k, d in dividends.items() if k[PLAYERS.index(p)] == "1"), Fraction(0)) for p in PLAYERS}
    grand = v(set(PLAYERS))
    checks = {"weights_sum_to_one": all(sum(Fraction(int(r["weight"]["n"]), int(r["weight"]["d"])) for r in rows if r["player"] == p) == 1 for p in PLAYERS),
              "permutations_telescope": all(sum(o["marginals"]) == grand for o in orders),
              "three_certificates_agree": phi == split == {p: Fraction(sums[p], 720) for p in PLAYERS},
              "efficiency": sum(phi.values()) == grand,
              "symmetry_AB": all(v(s | {"A"}) == v(s | {"B"}) for s in coalitions if not s & {"A", "B"}),
              "symmetry_CD": all(v(s | {"C"}) == v(s | {"D"}) for s in coalitions if not s & {"C", "D"}),
              "E_constant_4": all(v(s | {"E"}) - v(s) == 4 for s in coalitions if "E" not in s),
              "F_null": all(v(s | {"F"}) == v(s) for s in coalitions if "F" not in s)}
    return {"schema": "d11.allocation/v1", "source": "observed values of all 64 coalitions",
            "shapley": {p: q(x) for p, x in phi.items()}, "marginals": rows, "permutations": orders, "permutation_sums": sums,
            "dividends": dividends, "dividend_split": {p: q(x) for p, x in split.items()},
            "standalone": {p: v({p}) for p in PLAYERS}, "leave_one_out": {p: grand - v(set(PLAYERS) - {p}) for p in PLAYERS},
            "uniform_subset_marginals": {p: q(Fraction(sum(r["marginal"] for r in rows if r["player"] == p), 32)) for p in PLAYERS},
            "grand_value": grand, "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    a = ap.parse_args()
    records = [json.loads(l) for l in (a.run / "observations.jsonl").read_text().splitlines() if l.strip()]
    doc = allocate(observed_values(records))
    (a.run / "allocation.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"shapley": {p: f"{x['n']}/{x['d']}" for p, x in doc["shapley"].items()}, "checks": doc["checks"]}))


if __name__ == "__main__":
    main()
