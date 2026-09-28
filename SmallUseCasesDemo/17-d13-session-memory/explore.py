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

"""Independent label-space exploration and bond truth tables for D13d (no SUT, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * labels: all six raw triples per alphabet (U1/S1 in {0}, U2/S2 in {0,1}, U3/S3 in {0,1,2}); which
    are canonical restricted-growth strings (each label at most one above the largest before it),
    and that they are exactly the Bell(3) = 5 set partitions of three positions;
  * bonds: per-rule raw matches, overlap and sequential survivors over all 1152 raw rows, from an own
    evaluation of each bond, compared row by row with the frozen raw truth table; the Framework's own
    sieve (row_violations, reading the built companion) is run over the same rows as a cross-check;
  * the population: 800 identities, all 25 user x session partition pairs, per-stratum denominators.
verify.py re-derives the same tables and compares them with the live sieve log.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
POLICIES = ("scoped", "user_only", "session_only", "ignores_reset")
CUTS = ("00", "01", "10", "11")
RULES = ("user_rgs", "session_rgs")
TRIPLES = ["0" + str(a) + str(b) for a in range(2) for b in range(3)]


def canonical(t):
    seen = -1
    for ch in t:
        if int(ch) > seen + 1:
            return False
        seen = max(seen, int(ch))
    return True


def partition(t):
    """The set partition of positions {1,2,3} a label string induces (labels only mark equality)."""
    blocks = {}
    for pos, ch in enumerate(t, 1):
        blocks.setdefault(ch, []).append(pos)
    return sorted(blocks.values())


def own_bonds(row):
    hits = []
    if int(row["u"][2]) > 1 + int(row["u"][1]):
        hits.append("user_rgs")
    if int(row["s"][2]) > 1 + int(row["s"][1]):
        hits.append("session_rgs")
    return hits


def raw_rows():
    return [{"policy": p, "u": u, "s": s, "x": x, "w": w} for p, u, s, x, w in itertools.product(POLICIES, TRIPLES, TRIPLES, CUTS, (1, 2))]


def case_id(r):
    return f"P={r['policy']}|U={r['u']}|S={r['s']}|X={r['x']}|W={r['w']}"


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
        row = [{"sheet": f"U{i}", "value": f"user_at({i},{r['u'][i - 1]});", "pos": i} for i in (1, 2, 3)]
        row += [{"sheet": f"S{i}", "value": f"session_at({i},{r['s'][i - 1]});", "pos": 3 + i} for i in (1, 2, 3)]
        return sv.row_violations(row, sidecar)
    return bonds


def precheck():
    rep = {"schema": "d13d.precheck/v1", "note": "before execution; independent of the SUT, oracle and runtime"}
    rep["triples"] = {t: {"canonical": canonical(t), "partition": partition(t)} for t in TRIPLES}
    canon = [t for t in TRIPLES if canonical(t)]
    all_partitions = {json.dumps(partition(t)) for t in ("".join(map(str, p)) for p in itertools.product(range(3), repeat=3))}
    rep["canonical"] = canon
    rep["canonical_are_the_bell3_partitions"] = len(canon) == 5 and {json.dumps(partition(t)) for t in canon} == all_partitions
    rep["bond_equals_canonical_on_slot_domain"] = all((int(t[2]) <= 1 + int(t[1])) == canonical(t) for t in TRIPLES)
    own, fw = truth_table(own_bonds), truth_table(framework_bonds())
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    frozen_rows = {t["id"]: {rule: t[rule] for rule in RULES} for t in frozen["raw_bond_truth"]}
    rep["truth_table"] = {k: v for k, v in own.items() if k not in ("rows", "kept")}
    rep["raw_rows_equal_frozen_truth"] = own["rows"] == frozen_rows and len(frozen_rows) == 1152
    rep["framework_sieve_offline_agrees"] = own == fw
    rep["population_equals_frozen_ids"] = own["kept"] == sorted(c["id"] for c in frozen["cases"])
    pairs = {tuple(c.split("|")[1:3]) for c in own["kept"]}
    rep["partition_pairs"] = len(pairs)
    rep["strata"] = {"policy": {p: sum(c.startswith(f"P={p}|") for c in own["kept"]) for p in POLICIES},
                     "cuts": {x: sum(f"|X={x}|" in c for c in own["kept"]) for x in CUTS},
                     "write_at": {w: sum(c.endswith(f"|W={w}") for c in own["kept"]) for w in (1, 2)}}
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    rep = precheck()
    (HERE / "precheck").mkdir(exist_ok=True)
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    keys = ("canonical", "canonical_are_the_bell3_partitions", "bond_equals_canonical_on_slot_domain", "truth_table",
            "raw_rows_equal_frozen_truth", "framework_sieve_offline_agrees", "population_equals_frozen_ids", "partition_pairs", "strata")
    print(json.dumps({k: rep[k] for k in keys}))
    ok = (rep["canonical_are_the_bell3_partitions"] and rep["bond_equals_canonical_on_slot_domain"]
          and rep["truth_table"]["sequential"] == [1152, 960, 800] and rep["raw_rows_equal_frozen_truth"]
          and rep["framework_sieve_offline_agrees"] and rep["population_equals_frozen_ids"] and rep["partition_pairs"] == 25)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
