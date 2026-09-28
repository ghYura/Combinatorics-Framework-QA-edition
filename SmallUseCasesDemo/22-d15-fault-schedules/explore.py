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


"""Independent schedule exploration for D15 (no worker, harness, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * raw population: 3 implementations x 7 nonempty failed subsets x 4 cuts x 2 kinds x 2 retries = 336;
  * the bond: own evaluation of `forbid KIND = partition AND |FAIL| = 3` on every raw row, the Framework's
    sieve (row_violations over the built companion) on the same rows, and the AI architect's 24 rejected identities;
  * the transition model: CONTRACT.md's seven steps re-implemented here for the 312 valid rows (attempts,
    every snapshot, acknowledged ops, the seven checks) and compared with architect-derived.json;
  * counts: 1062 client attempts, 1224 worker starts, 288 injected kills; per-implementation outcomes; a
    closed-form failure rule checked against every modelled case.
verify.py re-derives the same objects after the run and compares them with the live observations.
"""
import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
IMPLS = ("durable", "volatile_ack", "replay_twice")
SUBSETS = [list(c) for k in (1, 2, 3) for c in itertools.combinations(range(3), k)]
DELTA = {"o1": 1, "o2": 10, "o3": 100}
CHECKS = ("all_logical_ops_acknowledged", "acknowledged_survive_repair", "acknowledged_effects_once", "accepted_logical_ops_once",
          "replicas_agree", "matches_fault_free_reference", "final_wal_matches_accepted")


def case_id(p, f, c, k, r):
    return f"P={p}|F={''.join(map(str, f))}|C={c}|K={k}|R={r}"


def simulate(impl, failed, cut, kind, retry):
    up, gen, acc, wal, eff = [True] * 3, [0] * 3, [[] for _ in range(3)], [[] for _ in range(3)], [[] for _ in range(3)]
    gate, attempts, trace = set(), [], []

    def store(n, key):
        if key not in acc[n]:
            acc[n].append(key)
            eff[n].append(key[:2])
            if impl != "volatile_ack":
                wal[n].append(key)

    def sync(n):
        wal[n] += [k for k in acc[n] if k not in wal[n]]

    def send(k, phase, tag="a1"):
        key = f"o{k}:{tag}"
        tgt = [n for n in range(3) if up[n] and n not in gate]
        for n in tgt:
            store(n, key)
        attempts.append({"op": f"o{k}", "key": key, "phase": phase, "targets": tgt, "status": "ACK" if len(tgt) > 1 else "TIMEOUT"})
        return attempts[-1]["status"]

    def look(label):
        nodes = []
        for n in range(3):
            cnt = {o: eff[n].count(o) for o in DELTA} if up[n] else None
            nodes.append({"node": n, "running": up[n], "reachable": up[n] and n not in gate, "generation": gen[n],
                          "accepted": sorted(acc[n]) if up[n] else None, "wal": list(wal[n]), "effects": list(eff[n]) if up[n] else None,
                          "counts": cnt, "value": sum(DELTA[o] * v for o, v in cnt.items()) if up[n] else None})
        trace.append({"checkpoint": label, "nodes": nodes})

    look("initial")
    for k in range(1, cut + 1):
        send(k, "prefix")
    look("prefix")
    gate |= set(failed)
    if kind == "crash":
        for n in failed:
            up[n], acc[n], eff[n] = False, [], []
    look("faulted")
    timeout = cut < 3 and send(cut + 1, "window") == "TIMEOUT"
    if cut < 3:
        look("window")
    if kind == "crash":
        for n in failed:
            up[n], gen[n], acc[n] = True, 1, list(wal[n])
            eff[n] = [k[:2] for k in wal[n]] * (2 if impl == "replay_twice" else 1)
    gate = set()
    look("reopened")
    union = sorted(set().union(*acc))
    for n in range(3):
        for key in union:
            store(n, key)
        sync(n)
    look("repaired")
    early = sorted({a["op"] for a in attempts if a["status"] == "ACK"})
    if timeout:
        send(cut + 1, "retry", "a1" if retry == "stable" else "a2")
        look("retry")
    for k in range(cut + 2, 4):
        send(k, "suffix")
    for n in range(3):
        sync(n)
    look("final")
    fin, rep = trace[-1]["nodes"], [t for t in trace if t["checkpoint"] == "repaired"][0]["nodes"]
    acked = sorted({a["op"] for a in attempts if a["status"] == "ACK"})
    ones = {o: 1 for o in DELTA}
    checks = {"all_logical_ops_acknowledged": acked == ["o1", "o2", "o3"],
              "acknowledged_survive_repair": all(s["counts"][o] >= 1 for s in rep for o in early),
              "acknowledged_effects_once": all(s["counts"][o] == 1 for s in fin for o in acked),
              "accepted_logical_ops_once": all(Counter(k[:2] for k in s["accepted"]) == ones for s in fin),
              "replicas_agree": all((s["accepted"], s["counts"], s["value"]) == (fin[0]["accepted"], fin[0]["counts"], fin[0]["value"]) for s in fin),
              "matches_fault_free_reference": all(s["counts"] == ones and s["value"] == 111 for s in fin),
              "final_wal_matches_accepted": all(len(s["wal"]) == len(set(s["wal"])) and sorted(s["wal"]) == s["accepted"] for s in fin)}
    return {"id": case_id(impl, failed, cut, kind, retry), "policy": impl, "failed": failed, "cut": cut, "kind": kind, "retry": retry,
            "attempts": attempts, "trace": trace, "acknowledged": acked, "checks": checks,
            "predicted_outcome": "PASS" if all(checks.values()) else "DOMAIN_FAIL"}


def raw_rows():
    return list(itertools.product(IMPLS, SUBSETS, range(4), ("crash", "partition"), ("stable", "fresh")))


def own_bond(row):
    _, failed, _, kind, _ = row
    return kind == "partition" and len(failed) == 3


def framework_bond():
    sys.path.insert(0, str(GEN))
    from constraints import sieve as sv
    sidecar = json.loads((HERE / "spec" / "demo.constraints.json").read_text())

    def bond(row):
        impl, failed, cut, kind, retry = row
        placed = [{"sheet": "IMPL", "value": f'impl("{impl}");', "pos": 1}] + \
                 [{"sheet": "FAIL", "value": f"fail({n});", "pos": 2} for n in failed] + \
                 [{"sheet": "CUT", "value": f"cut({cut});", "pos": 3}, {"sheet": "KIND", "value": f'fault("{kind}");', "pos": 4},
                  {"sheet": "RETRY", "value": f'retry("{retry}");', "pos": 5}]
        return sv.row_violations(placed, sidecar) == ["nontrivial_partition"]
    return bond


def rule(case):
    """Closed-form failure rule (independent of the transition model)."""
    two_down = len(case["failed"]) == 2 and case["cut"] < 3        # exactly one replica stores the timed-out attempt
    fresh_dup = two_down and case["retry"] == "fresh"
    lost = case["policy"] == "volatile_ack" and case["kind"] == "crash" and len(case["failed"]) == 3 and case["cut"] > 0
    replay = case["policy"] == "replay_twice" and case["kind"] == "crash" and case["cut"] > 0
    return fresh_dup or lost or replay


def precheck():
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    architect = json.loads((HERE / "planning" / "architect-precheck.json").read_text())
    rows = raw_rows()
    own_rej = sorted(case_id(*r) for r in rows if own_bond(r))
    fb = framework_bond()
    fw_rej = sorted(case_id(*r) for r in rows if fb(r))
    cases = [simulate(*r) for r in rows if not own_bond(r)]
    rep = {"schema": "d15.precheck/v1", "note": "before execution; independent of the worker, harness, oracle and runtime",
           "raw": len(rows), "rejected": len(own_rej), "valid": len(cases),
           "rejected_ids_own_eq_framework_eq_astra": own_rej == fw_rej == sorted(architect["rejected_ids"]),
           "rejected_ids": own_rej, "cases_equal_frozen": cases == frozen["cases"]}
    rep["outcomes"] = dict(Counter(c["predicted_outcome"] for c in cases))
    rep["by_policy"] = {p: dict(Counter(c["predicted_outcome"] for c in cases if c["policy"] == p)) for p in IMPLS}
    rep["counts"] = {"attempts": sum(len(c["attempts"]) for c in cases),
                     "worker_starts": sum(3 + (len(c["failed"]) if c["kind"] == "crash" else 0) for c in cases),
                     "injected_kills": sum(len(c["failed"]) for c in cases if c["kind"] == "crash")}
    rep["failure_rule_matches"] = sum(rule(c) == (c["predicted_outcome"] == "DOMAIN_FAIL") for c in cases)
    rep["failed_checks"] = {p: {k: sum(not c["checks"][k] for c in cases if c["policy"] == p) for k in CHECKS} for p in IMPLS}
    rep["fresh_duplicates_per_impl"] = {p: sum(1 for c in cases if c["policy"] == p and c["retry"] == "fresh" and len(c["failed"]) == 2 and c["cut"] < 3)
                                        for p in IMPLS}
    rep["rows_per_subset"] = {"".join(map(str, f)): sum(1 for c in cases if c["failed"] == f) for f in SUBSETS}
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    (HERE / "precheck").mkdir(exist_ok=True)
    rep = precheck()
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    ok = (rep["raw"] == 336 and rep["rejected"] == 24 and rep["valid"] == 312 and rep["rejected_ids_own_eq_framework_eq_astra"]
          and rep["cases_equal_frozen"] and rep["outcomes"] == {"PASS": 216, "DOMAIN_FAIL": 96}
          and rep["by_policy"] == {"durable": {"PASS": 86, "DOMAIN_FAIL": 18}, "volatile_ack": {"PASS": 80, "DOMAIN_FAIL": 24},
                                   "replay_twice": {"PASS": 50, "DOMAIN_FAIL": 54}}
          and rep["counts"] == {"attempts": 1062, "worker_starts": 1224, "injected_kills": 288} and rep["failure_rule_matches"] == 312
          and rep["fresh_duplicates_per_impl"] == {p: 18 for p in IMPLS})
    print(json.dumps({k: rep[k] for k in ("raw", "rejected", "valid", "rejected_ids_own_eq_framework_eq_astra", "cases_equal_frozen", "outcomes",
                                          "by_policy", "counts", "failure_rule_matches", "fresh_duplicates_per_impl", "rows_per_subset")} | {"ok": ok}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
