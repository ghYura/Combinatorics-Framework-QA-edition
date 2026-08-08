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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""Domain-neutral machinery for a construction-method comparison study.

This module knows nothing about any system under test. It owns the parts of a
comparison that must be *identical* across studies if their results are to be
compared at all: the outcome taxonomy, the suite generators, the scoring loop and
the cost accounting.

It lives in the control plane rather than beside a study because every layer above
the control plane may import it. A second study that had to import the first one
to obtain a comparison function would inherit that study's system under test, its
mutants and its factor space — which is exactly the coupling this module exists to
remove.

What belongs to a *study* and therefore stays out of here: the system under test,
its versioned defects, its factor space, the builder that turns an assignment into
a candidate, and the oracle that judges one. A study supplies those four things
and gets a comparison; it does not get to vary how the comparison is scored.
"""
from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

#: The three versions every mutation study runs: one control and two defects.
#: Fixed here so two studies cannot quietly disagree about what "correct" means.
CORRECT = "correct"
SINGLE_FAULT = "single_fault"
INTERACTION_ONLY = "interaction_only"
VERSIONS = (CORRECT, SINGLE_FAULT, INTERACTION_ONLY)

#: The canonical outcome taxonomy, shared with the Executor's.
PASS = "PASS"
DOMAIN_FAIL = "DOMAIN_FAIL"
BROKEN = "BROKEN"
TIMEOUT = "TIMEOUT"
INFRA_FAIL = "INFRA_FAIL"


@dataclass(frozen=True)
class Verdict:
    """One candidate's outcome. `defect_signature` names the minimal responsible
    combination where the oracle can identify it."""

    outcome: str
    reason: str
    defect_detected: bool
    defect_signature: str = ""
    stages: int = 0
    depth: int = 0
    branches: int = 0
    ops: int = 0
    retained: int = 0

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "reason": self.reason,
                "defect_detected": self.defect_detected,
                "defect_signature": self.defect_signature, "stages": self.stages,
                "depth": self.depth, "branches": self.branches, "ops": self.ops,
                "retained": self.retained}



def candidate_hash(node) -> str:
    return hashlib.sha256(repr(node).encode("utf-8")).hexdigest()[:16]

def cartesian_suite(factors: Mapping) -> "list[dict]":
    """Flat exhaustive product over the same raw factors — every combination,
    but no notion of composition order beyond what the factors encode."""
    keys = list(factors)
    return [dict(zip(keys, values)) for values in itertools.product(*factors.values())]

def twise_suite(factors: Mapping, t: int = 2) -> "list[dict]":
    """A deterministic greedy t-way covering array over the same factors.

    Greedy rather than optimal: the point is a credible, reproducible covering
    array, not a record-small one. Optimality would only shrink it, which would
    make the comparison *less* favourable to the Bundle, not more.

    `t` is the interaction strength the method is designed to cover. Reporting
    t=2 and t=3 side by side is the fair way to ask whether the interaction
    defects in this study are simply a matter of buying more strength: a 3-way
    array covers every triple, so a defect needing exactly three conditions
    should be within its reach by construction.
    """
    keys = list(factors)
    if not 1 <= t <= len(keys):
        raise ValueError(f"t={t} outside 1..{len(keys)} for this factor space")
    combos = list(itertools.combinations(range(len(keys)), t))
    all_candidates = cartesian_suite(factors)
    # Precomputed once: the greedy loop rescans every candidate each round, and
    # recomputing tuple sets inside it makes t=3 on a wide space quadratic for no
    # reason.
    covers = [frozenset((c, tuple(cand[keys[i]] for i in c)) for c in combos)
              for cand in all_candidates]
    uncovered = set().union(*covers) if covers else set()

    suite: "list[dict]" = []
    while uncovered:
        # Greedy MAXIMUM coverage per round, not first-fit. First-fit produced a
        # needlessly large suite, which would have inflated this baseline's cost
        # in the comparison — handicapping a baseline is exactly what this study
        # must not do. Ties break on the first candidate, so it is deterministic.
        best = max(range(len(all_candidates)), key=lambda i: len(covers[i] & uncovered))
        gained = covers[best] & uncovered
        if not gained:
            break
        suite.append(all_candidates[best])
        uncovered -= gained
    return suite

def pairwise_suite(factors: Mapping) -> "list[dict]":
    """The 2-way covering array — the industry default."""
    return twise_suite(factors, t=2)

def threewise_suite(factors: Mapping) -> "list[dict]":
    """The 3-way covering array.

    Included because it is the honest counter-argument to this whole study: if a
    defect needs three conditions, buy a 3-way array. Whether that is cheaper than
    exhaustive construction is exactly what the cost columns are for.
    """
    return twise_suite(factors, t=3)

def random_suite(factors: Mapping, budget: int = 8,
                 seed: int = 0) -> "list[dict]":
    """`budget` assignments drawn uniformly without replacement, deterministically.

    The least flattering baseline available, and the one this study lacked for too
    long: a construction method that cannot beat random sampling at the same
    candidate count has not earned its complexity. Seeded so a reported number can
    be re-derived, and reported over many seeds (see `random_baseline_report`)
    because a single draw measures luck rather than method.
    """
    import random as _random
    space = cartesian_suite(factors)
    budget = min(budget, len(space))
    return _random.Random(seed).sample(space, budget)

def ofat_structural_suite(factors: Mapping) -> "list[dict]":
    """A COMPOSING one-factor-at-a-time suite: start from a baseline assignment
    and vary each factor once, structural factors included.

    This is the fair OFAT. `ofat_nodes` below is the conventional non-composing
    suite; both are reported, because they answer different questions.
    """
    baseline = {k: v[0] for k, v in factors.items()}
    suite = [dict(baseline)]
    for key, values in factors.items():
        for value in values[1:]:
            variant = dict(baseline)
            variant[key] = value
            suite.append(variant)
    return suite

def evaluate_suite(assignments: "Iterable[Mapping]", version: str, builder,
                   judge_fn) -> dict:
    """Run one construction method's suite against one SUT version.

    Cost is measured, not assumed. Finding a defect with 256 candidates is a
    different engineering proposition from finding it with 8, and a comparison
    that reports only detected/missed hides exactly that difference.
    """
    outcomes = {PASS: 0, DOMAIN_FAIL: 0, BROKEN: 0, TIMEOUT: 0, INFRA_FAIL: 0}
    detections, signatures, executed, ops_total = [], set(), 0, 0
    first_index = None
    for assignment in assignments:
        # A method may yield factor assignments (composed via `build`) or, for the
        # flat baseline, prebuilt nodes. Both reach the same SUT and oracle.
        node = assignment if not isinstance(assignment, Mapping) else builder(assignment)
        verdict = judge_fn(node, version)
        outcomes[verdict.outcome] += 1
        executed += 1
        ops_total += verdict.ops
        if verdict.defect_detected:
            if first_index is None:
                first_index = executed          # 1-based: candidates run before you know
            detections.append({"assignment": (dict(assignment)
                                              if isinstance(assignment, Mapping) else repr(node)),
                               "candidate": candidate_hash(node),
                               "reason": verdict.reason,
                               "signature": verdict.defect_signature})
            signatures.add(verdict.defect_signature)
    return {
        "version": version,
        "executed": executed,
        "outcomes": outcomes,
        "detections": len(detections),
        "detected": bool(detections),
        "distinct_signatures": len(signatures),
        "first_detection": detections[0] if detections else None,
        # --- cost -------------------------------------------------------------
        # `ops` is element visits inside the SUT: a machine-independent execution
        # cost that does not depend on this laptop. `candidates_to_first` is the
        # cost that matters in practice — how many candidates you must run before
        # the defect is visible, assuming you stop when you find it.
        "ops": ops_total,
        "candidates_to_first": first_index,
        # A domain rejection is the pipeline's own declared behaviour. Counting
        # it as a defect discovery is the specific way a comparison flatters
        # whichever method generates the most candidates.
        "domain_rejections_not_defects": outcomes[DOMAIN_FAIL] - len(detections),
    }

def compare(factors: Mapping, builder, baselines: Mapping, judge_fn) -> dict:
    """The flagship comparison: every construction method against every SUT
    version, with identical SUT, oracle, corpus and budget.

    `factors`/`builder` let the same comparison run over a WIDER space (the L3
    level) without a second implementation of any method. Widening the space is
    the interesting experiment — a defect that a sampling method finds in a small
    space may or may not survive dilution, and asserting either way without
    measuring would be a guess.
    """
    results = {}
    for name, make_suite in baselines.items():
        suite = make_suite(factors)
        versions = {v: evaluate_suite(suite, v, builder=builder, judge_fn=judge_fn)
                    for v in VERSIONS}
        found = [v for v in VERSIONS if v != CORRECT and versions[v]["detected"]]
        results[name] = {
            "authored_size": len(suite),
            "versions": versions,
            # Both halves of the verdict on a method, in one place: what it found,
            # and what running it costs across the whole study.
            "defects_found": len(found),
            "defects_missed": len(VERSIONS) - 1 - len(found),
            "false_positives": versions[CORRECT]["detections"],
            "total_executions": sum(versions[v]["executed"] for v in VERSIONS),
            "total_ops": sum(versions[v]["ops"] for v in VERSIONS),
        }
    # `sut_revision`, `oracle_revision` and any domain corpus are the STUDY's to
    # add: this module has no opinion about what was under test, only about how
    # the comparison was scored.
    return {"factors": {k: list(v) for k, v in factors.items()}, "methods": results}

def format_comparison(report: dict) -> str:
    """The comparison as a Markdown table, detection AND cost together.

    Emitted from the same dict the tests assert on, so the published table cannot
    drift away from the executed numbers.
    """
    head = ("| Construction method | Candidates | Execs | Ops | "
            "`correct` (false positives) | `single_fault` | `interaction_only` |")
    rule = "|---|---:|---:|---:|---|---|---|"
    rows = [head, rule]
    for name, data in report["methods"].items():
        cells = []
        for version in VERSIONS:
            result = data["versions"][version]
            n = result["executed"]
            if version == CORRECT:
                cells.append("0 — none" if not result["detections"]
                             else f"**{result['detections']}/{n} FALSE POSITIVE**")
            elif result["detected"]:
                cells.append(f"{result['detections']}/{n} found "
                             f"(after {result['candidates_to_first']})")
            else:
                cells.append(f"**0/{n} MISSED**")
        rows.append(f"| {name} | {data['authored_size']} | {data['total_executions']} | "
                    f"{data['total_ops']} | " + " | ".join(cells) + " |")
    return "\n".join(rows)
def random_baseline_report(factors: Mapping, builder, judge_fn, budget: int = 0,
                           seeds: int = 50, versions=VERSIONS) -> dict:
    """Random sampling at a fixed budget, over many seeds.

    A single random draw measures luck, not method, so reporting one seed would be
    the same error as quoting one covering array. This runs `seeds` independent
    draws and reports **in how many of them the defect was found**, which is the
    only honest way to compare a stochastic method against a deterministic one.

    The default budget is the size of the 2-way covering array over the same
    factors: random then gets exactly the candidates pairwise would have spent, so
    the comparison is cost-for-cost rather than method-for-method.
    """
    budget = budget or len(pairwise_suite(factors))
    report = {"budget": budget, "seeds": seeds, "versions": {}}
    for version in versions:
        found, detections = 0, []
        for seed in range(seeds):
            suite = random_suite(factors, budget, seed)
            hits = sum(judge_fn(builder(a), version).defect_detected for a in suite)
            detections.append(hits)
            found += bool(hits)
        report["versions"][version] = {
            "seeds_detecting": found,
            "detection_rate": found / seeds,
            "mean_detections_per_run": sum(detections) / seeds,
            "worst_seed": min(detections),
            "best_seed": max(detections),
        }
    return report

def format_random_report(report: dict) -> str:
    """The random baseline as Markdown: seeds that found it, not a single draw."""
    rows = [f"| SUT version | seeds detecting (of {report['seeds']}) | mean hits per run | worst seed |",
            "|---|---:|---:|---:|"]
    for version, data in report["versions"].items():
        rows.append(f"| `{version}` | {data['seeds_detecting']} "
                    f"({data['detection_rate']:.0%}) | {data['mean_detections_per_run']:.2f} | "
                    f"{data['worst_seed']} |")
    return "\n".join(rows)
