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

"""Independent schedule exploration and bond truth tables for D6 (no SUT, reference or runtime code).

    python explore.py --precheck     # write precheck/<counter|queue>.json before any campaign

  * counter: for all 16 raw words, preemptions from prefix completion counts versus the contract's
    expression over a-attributes; context switches; the caps' retained schedules;
  * queue: reference-state exploration of every raw word (well-formedness, then enabledness of each
    step on an own actual-queue state); proof that the feasible two-each schedules are exactly the
    ones starting with P, and that the two bonds retain exactly them;
  * both: per-rule raw matches, overlap and sequential survivors over the raw Core product, from an
    own evaluation of each bond; the Framework's own sieve (row_violations) is run over the same
    rows as a cross-check (it reads the companion, not the SUT).
verify.py re-derives the same tables and compares them with the live sieve log.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
THREADS = {"counter": "AB", "queue": "PC"}
POLICIES = {"counter": ["atomic_commit", "split_rw"], "queue": ["actual_queue", "stale_empty"]}


def words(campaign):
    return ["".join(w) for w in itertools.product(THREADS[campaign], repeat=4)]


def two_each(w):
    return len(set(w)) == 2 and w.count(w[0]) == 2


def prefix_preemptions(w):
    """A switch at i counts when the outgoing thread has completed fewer than 2 steps by i."""
    total = 0
    for i in range(3):
        if w[i] != w[i + 1] and w[: i + 1].count(w[i]) < 2:
            total += 1
    return total


def expression(w):
    a = [int(t == "A") for t in w]
    return int(a[0] != a[1]) + int(a[1] != a[2] and a[0] != a[1]) + int(a[2] != a[3] and a[0] != a[2] and a[1] != a[2])


def switches(w):
    return sum(w[i] != w[i + 1] for i in range(3))


def explore_queue(w):
    """(status, detail): 'malformed' | 'disabled' (first disabled step) | 'feasible', on an own state."""
    if not two_each(w):
        return "malformed", "not two steps per thread"
    items, done = 0, {"P": 0, "C": 0}
    for i, t in enumerate(w, start=1):
        done[t] += 1
        if t == "C" and done[t] == 1 and items == 0:
            return "disabled", i                        # wait_readable on an empty queue
        if t == "P" and done[t] == 1:
            items += 1
        if t == "C" and done[t] == 2 and items:
            items -= 1
    return "feasible", None


def own_bonds(campaign, row):
    """Violated bond ids for one raw row {'cap': n or None, 'word': w}, from the contract's text."""
    w, hits = row["word"], []
    first = THREADS[campaign][0]
    if sum(t == first for t in w) != 2:
        hits.append("two_each")
    if campaign == "counter":
        if expression(w) > row["cap"]:
            hits.append("preemption_cap")
    elif w[0] != "P":
        hits.append("producer_first")
    return hits


def raw_rows(campaign):
    caps = (0, 1, 2) if campaign == "counter" else (None,)
    return [{"policy": p, "cap": c, "word": w} for p in POLICIES[campaign] for c in caps for w in words(campaign)]


def truth_table(campaign, bonds):
    rows = raw_rows(campaign)
    ids = ["two_each", "preemption_cap"] if campaign == "counter" else ["two_each", "producer_first"]
    hits = [bonds(campaign, r) for r in rows]
    per_rule = {i: sum(i in h for h in hits) for i in ids}
    seq, alive = [len(rows)], list(zip(rows, hits))
    for i in ids:
        alive = [(r, h) for r, h in alive if i not in h]
        seq.append(len(alive))
    return {"raw": len(rows), "per_rule": per_rule, "overlap": sum(len(h) > 1 for h in hits),
            "unique_removals": sum(bool(h) for h in hits), "sequential": seq,
            "kept": sorted({(r["policy"], r["cap"], r["word"]) for r, h in zip(rows, hits) if not h}, key=str)}


def framework_bonds(campaign):
    """The Framework's sieve over the same raw rows, read from the built companion (cross-check)."""
    sys.path.insert(0, str(GEN))
    from constraints import sieve as sv
    sidecar = json.loads((HERE / "spec" / campaign / "demo.constraints.json").read_text())

    def bonds(_c, r):
        row = []
        if r["cap"] is not None:
            row.append({"sheet": "CAP", "value": f"cap({r['cap']});", "pos": 0})
        row += [{"sheet": f"S{i}", "value": f'set_step({i},"{t}");', "pos": i} for i, t in enumerate(r["word"], start=1)]
        return sv.row_violations(row, sidecar)
    return bonds


def precheck(campaign):
    rep = {"schema": "d6.precheck/v1", "campaign": campaign, "note": "before execution; independent of the SUT and runtime"}
    ws = words(campaign)
    if campaign == "counter":
        rep["words"] = {w: {"two_each": two_each(w), "prefix_preemptions": prefix_preemptions(w), "expression": expression(w),
                            "context_switches": switches(w)} for w in ws}
        rep["expression_equals_prefix_count_on_all_16"] = all(v["prefix_preemptions"] == v["expression"] for v in rep["words"].values())
        rep["schedules_by_cap"] = {c: sorted(w for w in ws if two_each(w) and prefix_preemptions(w) <= c) for c in (0, 1, 2)}
    else:
        rep["words"] = {w: dict(zip(("status", "detail"), explore_queue(w))) for w in ws}
        feasible = sorted(w for w, v in rep["words"].items() if v["status"] == "feasible")
        rep["feasible"] = feasible
        rep["infeasible_two_each"] = {w: v["detail"] for w, v in rep["words"].items() if v["status"] == "disabled"}
        rep["feasible_equals_first_letter_P"] = feasible == sorted(w for w in ws if two_each(w) and w[0] == "P")
    own = truth_table(campaign, own_bonds)
    fw = truth_table(campaign, framework_bonds(campaign))
    rep["truth_table"] = {k: v for k, v in own.items() if k != "kept"}
    rep["kept_rows"] = own["kept"]
    rep["framework_sieve_offline_agrees"] = own == fw
    if campaign == "queue":
        rep["bonds_retain_exactly_feasible"] = sorted({w for _, _, w in own["kept"]}) == rep["feasible"]
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    (HERE / "precheck").mkdir(exist_ok=True)
    for campaign in ("counter", "queue"):
        rep = precheck(campaign)
        (HERE / "precheck" / f"{campaign}.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        keys = ["truth_table", "framework_sieve_offline_agrees"] + (
            ["expression_equals_prefix_count_on_all_16", "schedules_by_cap"] if campaign == "counter"
            else ["feasible", "infeasible_two_each", "feasible_equals_first_letter_P", "bonds_retain_exactly_feasible"])
        print(campaign, json.dumps({k: rep[k] for k in keys}))


if __name__ == "__main__":
    main()
