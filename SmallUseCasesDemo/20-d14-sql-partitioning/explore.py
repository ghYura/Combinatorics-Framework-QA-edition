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


"""Independent three-valued-logic and bag exploration for D14b (no adapter, model, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * truth tables: Kleene NOT/AND/OR over TRUE, FALSE, UNKNOWN, and each predicate on each fixture item;
  * row counts of the four shapes (6/3/6/8) and the concrete controls named in CONTRACT.md;
  * all 72 cases (sql, query rows and bags, recombined rows and bag, tlp_ok, set_equal, outcome) rebuilt
    from the contract and compared with architect-derived.json; 24 families, 288 data SELECTs;
  * where each faulty adapter legitimately passes, and where set equality would hide a failure.
verify.py re-derives the same objects after the run and compares them with the live observations.
"""
import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICIES = ("union_all", "omit_unknown", "dedup_union")
QUERIES = ("scan", "filtered", "inner_join", "left_join")
PREDS = ("gt0", "eq1", "flag", "and", "or", "is_null")
TEXT = {"gt0": "i.val > 0", "eq1": "i.val = 1", "flag": "i.flag", "and": "(i.val > 0) AND i.flag", "or": "(i.val = 1) OR i.flag",
        "is_null": "i.val IS NULL"}
T, F, U = "TRUE", "FALSE", "UNKNOWN"


def NOT(a):
    return {T: F, F: T, U: U}[a]


def AND(a, b):
    return F if F in (a, b) else U if U in (a, b) else T


def OR(a, b):
    return T if T in (a, b) else U if U in (a, b) else F


def cmp(v, fn):
    return U if v is None else (T if fn(v) else F)


def pred(item, name):
    v, f = item["val"], item["flag"]
    fl = U if f is None else (T if f else F)
    return {"gt0": lambda: cmp(v, lambda x: x > 0), "eq1": lambda: cmp(v, lambda x: x == 1), "flag": lambda: fl,
            "and": lambda: AND(cmp(v, lambda x: x > 0), fl), "or": lambda: OR(cmp(v, lambda x: x == 1), fl),
            "is_null": lambda: T if v is None else F}[name]()


def shape_rows(fx, query):
    items, tags = fx["items"], fx["tags"]
    if query in ("scan", "filtered"):
        return [i for i in items if query == "scan" or i["grp"] == "a"]
    out = []
    for i in items:
        k = sum(1 for t in tags if t["item_id"] == i["id"])
        out += [i] * (k if query == "inner_join" else max(k, 1))
    return out


def canon(vals):
    return sorted([[v] for v in vals], key=lambda r: (r[0] is not None, r[0] or 0))


def bagof(rows):
    c = Counter(r[0] for r in rows)
    return [{"row": [k], "count": c[k]} for k in sorted(c, key=lambda v: (v is not None, v or 0))]


def sql(query, p):
    join = {"inner_join": " JOIN fixture.tags AS t ON t.item_id=i.id", "left_join": " LEFT JOIN fixture.tags AS t ON t.item_id=i.id"}.get(query, "")
    base = "i.grp = 'a'" if query == "filtered" else "TRUE"
    head = "SELECT i.val FROM fixture.items AS i" + join + " WHERE "
    return {"base": head + base, "true": head + f"({base}) AND ({TEXT[p]})", "false": head + f"({base}) AND NOT ({TEXT[p]})",
            "unknown": head + f"({base}) AND (({TEXT[p]}) IS NULL)"}


def case(fx, policy, query, p):
    src = shape_rows(fx, query)
    qr = {"base": canon(i["val"] for i in src)}
    for branch, keep in (("true", lambda i: pred(i, p) == T), ("false", lambda i: NOT(pred(i, p)) == T), ("unknown", lambda i: pred(i, p) == U)):
        qr[branch] = canon(i["val"] for i in src if keep(i))
    parts = [qr["true"], qr["false"]] + ([] if policy == "omit_unknown" else [qr["unknown"]])
    merged = [r[0] for part in parts for r in part]
    if policy == "dedup_union":
        merged = list(dict.fromkeys(merged))
    comb = canon(merged)
    ok = bagof(qr["base"]) == bagof(comb)
    return {"id": f"P={policy}|Q={query}|F={p}", "policy": policy, "query": query, "predicate": p, "sql": sql(query, p),
            "query_rows": qr, "query_bags": {k: bagof(v) for k, v in qr.items()}, "combined_rows": comb, "combined_bag": bagof(comb),
            "tlp_ok": ok, "set_equal": {r[0] for r in qr["base"]} == {r[0] for r in comb}, "predicted_outcome": "PASS" if ok else "DOMAIN_FAIL"}


def precheck():
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    fx = frozen["fixture"]
    rep = {"schema": "d14b.precheck/v1", "note": "before execution; independent of the adapter, model, oracle and runtime"}
    rep["kleene"] = {"not": {a: NOT(a) for a in (T, F, U)}, "and": {f"{a}|{b}": AND(a, b) for a in (T, F, U) for b in (T, F, U)},
                     "or": {f"{a}|{b}": OR(a, b) for a in (T, F, U) for b in (T, F, U)}}
    rep["truth"] = {p: {str(i["id"]): pred(i, p) for i in fx["items"]} for p in PREDS}
    rep["row_counts"] = {q: len(shape_rows(fx, q)) for q in QUERIES}
    cases = [case(fx, *k) for k in itertools.product(POLICIES, QUERIES, PREDS)]
    by = {c["id"]: c for c in cases}
    rep["cases_equal_frozen"] = cases == [{k: c[k] for k in cases[0]} for c in frozen["cases"]] and [c["id"] for c in frozen["cases"]] == list(by)
    scan_flag = by["P=union_all|Q=scan|F=flag"]["query_rows"]
    rep["controls"] = {
        "scan_bag": by["P=union_all|Q=scan|F=gt0"]["query_bags"]["base"],
        "scan_flag_branches": {k: [r[0] for r in scan_flag[k]] for k in ("true", "false", "unknown")},
        "omit_unknown_scan_flag": {k: by["P=omit_unknown|Q=scan|F=flag"][k] for k in ("set_equal", "tlp_ok")},
        "unknown_empty_families": sorted(f"{c['query']}|{c['predicate']}" for c in cases if c["policy"] == "union_all" and not c["query_rows"]["unknown"]),
        "distinct_base_families": sorted(f"{c['query']}|{c['predicate']}" for c in cases if c["policy"] == "union_all"
                                         and len({r[0] for r in c["query_rows"]["base"]}) == len(c["query_rows"]["base"]))}
    rep["counts"] = {"cases": len(cases), "families": len({(c["query"], c["predicate"]) for c in cases}), "data_selects": 4 * len(cases)}
    rep["outcomes"] = dict(Counter(c["predicted_outcome"] for c in cases))
    rep["by_policy"] = {p: dict(Counter(c["predicted_outcome"] for c in cases if c["policy"] == p)) for p in POLICIES}
    rep["passes"] = {p: sorted(f"{c['query']}|{c['predicate']}" for c in cases if c["policy"] == p and c["predicted_outcome"] == "PASS") for p in POLICIES[1:]}
    rep["failures_hidden_by_sets"] = sorted(c["id"] for c in cases if c["predicted_outcome"] != "PASS" and c["set_equal"])
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    (HERE / "precheck").mkdir(exist_ok=True)
    rep = precheck()
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    c = rep["controls"]
    ok = (rep["cases_equal_frozen"] and rep["row_counts"] == {"scan": 6, "filtered": 3, "inner_join": 6, "left_join": 8}
          and c["scan_bag"] == [{"row": [None], "count": 2}, {"row": [0], "count": 1}, {"row": [1], "count": 2}, {"row": [2], "count": 1}]
          and c["scan_flag_branches"] == {"true": [None, 1], "false": [0, 2], "unknown": [None, 1]}
          and c["omit_unknown_scan_flag"] == {"set_equal": True, "tlp_ok": False}
          and c["unknown_empty_families"] == sorted(["scan|is_null", "filtered|is_null", "inner_join|is_null", "left_join|is_null", "filtered|or", "inner_join|or"])
          and c["distinct_base_families"] == sorted(f"filtered|{p}" for p in PREDS)
          and rep["counts"] == {"cases": 72, "families": 24, "data_selects": 288} and rep["outcomes"] == {"PASS": 36, "DOMAIN_FAIL": 36}
          and rep["by_policy"] == {"union_all": {"PASS": 24}, "omit_unknown": {"DOMAIN_FAIL": 18, "PASS": 6}, "dedup_union": {"DOMAIN_FAIL": 18, "PASS": 6}}
          and rep["passes"]["omit_unknown"] == c["unknown_empty_families"] and rep["passes"]["dedup_union"] == c["distinct_base_families"])
    print(json.dumps({"row_counts": rep["row_counts"], "cases_equal_frozen": rep["cases_equal_frozen"], "counts": rep["counts"],
                      "outcomes": rep["outcomes"], "passes": rep["passes"], "failures_hidden_by_sets": len(rep["failures_hidden_by_sets"]), "ok": ok}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
