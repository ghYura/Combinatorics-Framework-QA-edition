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

"""D12 offline analysis: rotation partition, population summaries and the words/classes cross-check.

    python analysis.py --words evidence/<words-run>                          # after the words campaign
    python analysis.py --words evidence/<words-run> --classes evidence/<classes-run>

Writes analysis.json into the classes run (if given) or the words run. Input guards: exactly one PASS
row per expected word in each campaign; missing, duplicate or unknown identities are refused. The
partition certificate lists every representative with all distinct member words, orbit size, period,
stabilizer, reflected representative and the (constant) observed cost. Three explicitly labelled
populations, exact fractions: uniform labelled words (729), uniform rotation classes (130) and
orbit-weighted classes (weight = distinct orbit size). Catalogue construction and weighting are this
offline harness's work, not Core canonicalization.
"""
import argparse
import itertools
import json
import math
import re
from collections import Counter
from fractions import Fraction
from pathlib import Path

WORD_RE = re.compile(r"W=([ABC]{6})")
ALL_WORDS = ["".join(w) for w in itertools.product("ABC", repeat=6)]


class AnalysisInputError(ValueError):
    pass


def q(x):
    x = Fraction(x)
    return {"n": str(x.numerator), "d": str(x.denominator)}


def rotations(w):
    return sorted({w[k:] + w[:k] for k in range(6)})


def load(run, campaign, expected):
    rows = {}
    for line in (run / "observations.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        m = WORD_RE.fullmatch(r.get("case_id", ""))
        if not m or r.get("word") != m.group(1) or r.get("campaign") != campaign:
            raise AnalysisInputError(f"unknown identity {r.get('case_id')!r} in {campaign}")
        if r.get("verdict") != "PASS":
            raise AnalysisInputError(f"non-PASS observation {r['case_id']} in {campaign}")
        if m.group(1) in rows:
            raise AnalysisInputError(f"duplicate {r['case_id']} in {campaign}")
        rows[m.group(1)] = r
    if sorted(rows) != sorted(expected):
        raise AnalysisInputError(f"{campaign}: {len(set(expected) - set(rows))} missing, {len(set(rows) - set(expected))} unexpected")
    return rows


def histogram(pairs):
    h = Counter()
    for cost, weight in pairs:
        h[cost] += weight
    return dict(sorted(h.items()))


def mean(pairs):
    total = sum(w for _, w in pairs)
    return Fraction(sum(c * w for c, w in pairs), total)


def analyse(words_run, classes_run=None):
    words = load(words_run, "words", ALL_WORDS)
    reps = sorted({min(rotations(w)) for w in ALL_WORDS})
    orbits = []
    for r in reps:
        members = rotations(r)
        costs = {words[w]["total_cost"] for w in members}
        if len(costs) != 1:
            raise AnalysisInputError(f"orbit {r} has non-constant observed cost {sorted(costs)}")
        period = next(k for k in range(1, 7) if r[k:] + r[:k] == r)
        orbits.append({"representative": r, "members": members, "size": len(members), "period": period,
                       "stabilizer_size": 6 // len(members), "reflected_representative": min(rotations(r[::-1])),
                       "total_cost": costs.pop()})
    burnside = [sum(1 for w in ALL_WORDS if w[k:] + w[:k] == w) for k in range(6)]
    self_ref = sum(o["representative"] == o["reflected_representative"] for o in orbits)
    doc = {"schema": "d12.analysis/v1", "words_run": words_run.name,
           "partition": {"orbits": orbits, "classes": len(orbits), "covered_words": sum(o["size"] for o in orbits),
                         "disjoint_complete": sorted(w for o in orbits for w in o["members"]) == sorted(ALL_WORDS),
                         "burnside_fixed_counts": burnside, "burnside_classes": sum(burnside) // 6,
                         "orbit_size_histogram": dict(sorted(Counter(o["size"] for o in orbits).items())),
                         "self_reflection_classes": self_ref,
                         "mirror_pairs": len({frozenset((o["representative"], o["reflected_representative"])) for o in orbits
                                              if o["representative"] != o["reflected_representative"]})}}
    word_pairs = [(r["total_cost"], 1) for r in words.values()]
    populations = {"words": {"label": "uniform labelled words (729)", "histogram": histogram(word_pairs), "mean": q(mean(word_pairs))}}
    if classes_run is not None:
        classes = load(classes_run, "classes", reps)
        keys = ("counts", "edge_counts", "edge_costs", "transition_cost", "balance_penalty", "total_cost", "representative",
                "orbit_size", "period", "stabilizer_size")
        mism = [r for r in reps if any(classes[r][k] != words[r][k] for k in keys)]
        cost = {r: classes[r]["total_cost"] for r in reps}
        uni = [(cost[r], 1) for r in reps]
        wtd = [(cost[o["representative"]], o["size"]) for o in orbits]
        populations["classes_uniform"] = {"label": "uniform rotation classes (130)", "histogram": histogram(uni), "mean": q(mean(uni))}
        populations["classes_weighted"] = {"label": "orbit-weighted classes (weight = distinct orbit size)", "histogram": histogram(wtd),
                                           "mean": q(mean(wtd))}
        ranking = sorted(reps, key=lambda r: (cost[r], r))
        best = [r for r in ranking if cost[r] == cost[ranking[0]]]
        doc.update(classes_run=classes_run.name,
                   cross_campaign={"representatives_matched": len(reps) - len(mism), "mismatches": mism},
                   ranking=ranking, best_classes=best, best_labelled_words=sorted(w for r in best for w in rotations(r)),
                   masses={"best_class_of_classes": q(Fraction(len(best), len(reps))),
                           "best_words_of_words": q(Fraction(sum(len(rotations(r)) for r in best), len(ALL_WORDS)))},
                   weighted_histogram_equals_words=populations["classes_weighted"]["histogram"] == populations["words"]["histogram"])
    doc["populations"] = populations
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--words", required=True, type=Path)
    ap.add_argument("--classes", type=Path)
    a = ap.parse_args()
    doc = analyse(a.words, a.classes)
    out = (a.classes or a.words) / "analysis.json"
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classes": doc["partition"]["classes"], "means": {k: v["mean"] for k, v in doc["populations"].items()},
                      "best": doc.get("best_classes"), "cross_campaign": doc.get("cross_campaign", {}).get("representatives_matched")}))


if __name__ == "__main__":
    main()
