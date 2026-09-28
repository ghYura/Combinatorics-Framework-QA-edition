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

"""Independent schedule exploration and bond truth tables for D13c (no SUT, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * enabledness: every raw word explored per mode from prefix delivery counts (an agent has a next
    local message; in after_A_offer, B.inspect needs A's inspect delivered first); proof that the
    after_A_offer feasible set equals "two each and the first letter is A" for this fixture;
  * preemptions: from prefix completion counts (a switch away from an agent whose commit is still
    undelivered) versus the contract's expression, on all 16 words, with switches and the examples;
  * bonds: per-rule raw matches, overlap and sequential survivors over all 288 raw rows, from an own
    evaluation of each bond, compared row by row with the frozen raw truth table; the Framework's own
    sieve (row_violations, reading the built companion) is run over the same rows as a cross-check;
  * the reference population: 54 identities and each mode x cap stratum's denominator.
verify.py re-derives the same tables and compares them with the live sieve log.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
POLICIES = ("compare_version", "trust_offer", "overwrite_owner")
MODES = ("independent", "after_A_offer")
CAPS = (0, 1, 2)
RULES = ("two_each", "causal_ready", "preemption_cap")
WORDS = ["".join(w) for w in itertools.product("AB", repeat=4)]


def explore(word, mode):
    """'feasible', or the first disabled delivery (index, agent), from prefix counts only."""
    done = {"A": 0, "B": 0}
    for i, agent in enumerate(word, 1):
        ready = [a for a in "AB" if done[a] < 2 and not (a == "B" and mode == "after_A_offer" and done["B"] == 0 and done["A"] == 0)]
        if agent not in ready:
            return {"status": "disabled", "at": i, "agent": agent, "enabled": ready}
        done[agent] += 1
    return {"status": "feasible"}


def preemptions(word):
    """Switches away from an agent that has delivered only its inspect (its commit is enabled, undelivered)."""
    return sum(1 for i in range(3) if word[i] != word[i + 1] and word[: i + 1].count(word[i]) == 1)


def switches(word):
    return sum(1 for i in range(3) if word[i] != word[i + 1])


def expression(word):
    a = [int(t == "A") for t in word]
    return int(a[0] != a[1]) + int(a[1] != a[2] and a[0] != a[1]) + int(a[2] != a[3] and a[0] != a[2] and a[1] != a[2])


def own_bonds(row):
    """Violated bond ids for one raw row, from the contract text."""
    a = [int(t == "A") for t in row["word"]]
    hits = []
    if sum(a) != 2:
        hits.append("two_each")
    if not (row["mode"] == "independent" or a[0] == 1):
        hits.append("causal_ready")
    if expression(row["word"]) > row["cap"]:
        hits.append("preemption_cap")
    return hits


def raw_rows():
    return [{"policy": p, "mode": m, "cap": k, "word": w} for p, m, k, w in itertools.product(POLICIES, MODES, CAPS, WORDS)]


def case_id(r):
    return f"P={r['policy']}|M={r['mode']}|K={r['cap']}|S={r['word']}"


def truth_table(bonds):
    rows = raw_rows()
    hits = [bonds(r) for r in rows]
    seq, alive = [len(rows)], list(zip(rows, hits))
    for rule in RULES:
        alive = [(r, h) for r, h in alive if rule not in h]
        seq.append(len(alive))
    return {"raw": len(rows), "per_rule": {rule: sum(rule in h for h in hits) for rule in RULES},
            "overlap": sum(len(h) > 1 for h in hits), "unique_removals": sum(bool(h) for h in hits), "sequential": seq,
            "rows": {case_id(r): {rule: rule not in h for rule in RULES} for r, h in zip(rows, hits)},
            "kept": sorted(case_id(r) for r, h in zip(rows, hits) if not h)}


def framework_bonds():
    """The Framework's sieve over the same raw rows, read from the built companion (cross-check)."""
    sys.path.insert(0, str(GEN))
    from constraints import sieve as sv
    sidecar = json.loads((HERE / "spec" / "demo.constraints.json").read_text())

    def bonds(r):
        row = [{"sheet": "MODE", "value": f'mode("{r["mode"]}");', "pos": 0}, {"sheet": "CAP", "value": f"cap({r['cap']});", "pos": 1}]
        row += [{"sheet": f"S{i}", "value": f'set_step({i},"{t}");', "pos": 1 + i} for i, t in enumerate(r["word"], start=1)]
        return sv.row_violations(row, sidecar)
    return bonds


def precheck():
    rep = {"schema": "d13c.precheck/v1", "note": "before execution; independent of the SUT, oracle and runtime"}
    rep["enabledness"] = {m: {w: explore(w, m) for w in WORDS} for m in MODES}
    feasible = {m: sorted(w for w in WORDS if rep["enabledness"][m][w]["status"] == "feasible") for m in MODES}
    two = sorted(w for w in WORDS if w.count("A") == 2)
    rep["feasible"] = feasible
    rep["independent_feasible_equals_two_each"] = feasible["independent"] == two
    rep["after_A_offer_feasible_equals_first_letter_A"] = feasible["after_A_offer"] == sorted(w for w in two if w[0] == "A")
    rep["after_A_offer_excluded"] = {w: rep["enabledness"]["after_A_offer"][w] for w in two if w not in feasible["after_A_offer"]}
    rep["words"] = {w: {"two_each": w in two, "prefix_preemptions": preemptions(w), "expression": expression(w),
                        "context_switches": switches(w)} for w in WORDS}
    rep["expression_equals_prefix_count_on_two_each"] = all(expression(w) == preemptions(w) for w in two)
    rep["expression_equals_prefix_count_on_all_16"] = all(expression(w) == preemptions(w) for w in WORDS)
    rep["contract_examples"] = {w: [switches(w), preemptions(w)] for w in ("AABB", "ABBA", "ABAB")}
    rep["schedules_by_mode_cap"] = {m: {k: [w for w in feasible[m] if preemptions(w) <= k] for k in CAPS} for m in MODES}
    own, fw = truth_table(own_bonds), truth_table(framework_bonds())
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    frozen_rows = {t["id"]: {rule: t[rule] for rule in RULES} for t in frozen["raw_bond_truth"]}
    rep["truth_table"] = {k: v for k, v in own.items() if k not in ("rows", "kept")}
    rep["raw_rows_equal_frozen_truth"] = own["rows"] == frozen_rows and len(frozen_rows) == 288
    rep["framework_sieve_offline_agrees"] = own == fw
    rep["population"] = own["kept"]
    rep["population_equals_frozen_ids"] = own["kept"] == sorted(c["id"] for c in frozen["cases"])
    rep["strata"] = {f"{m}|K={k}": sum(1 for c in own["kept"] if f"|M={m}|K={k}|" in c) for m in MODES for k in CAPS}
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    rep = precheck()
    (HERE / "precheck").mkdir(exist_ok=True)
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    keys = ("feasible", "independent_feasible_equals_two_each", "after_A_offer_feasible_equals_first_letter_A", "contract_examples",
            "expression_equals_prefix_count_on_two_each", "expression_equals_prefix_count_on_all_16", "truth_table",
            "raw_rows_equal_frozen_truth", "framework_sieve_offline_agrees", "population_equals_frozen_ids", "strata")
    print(json.dumps({k: rep[k] for k in keys}))
    ok = (rep["independent_feasible_equals_two_each"] and rep["after_A_offer_feasible_equals_first_letter_A"]
          and rep["expression_equals_prefix_count_on_two_each"] and rep["contract_examples"] == {"AABB": [1, 0], "ABBA": [2, 1], "ABAB": [3, 2]}
          and rep["truth_table"]["sequential"] == [288, 108, 81, 54] and rep["raw_rows_equal_frozen_truth"]
          and rep["framework_sieve_offline_agrees"] and rep["population_equals_frozen_ids"])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
