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

"""Independent offline verifier for the D8a evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py, allowed_orders.py or derive.py, never
connects to a database, never executes a candidate (candidates and dictionary values are parsed with
`ast`). Rank vectors come from ordered set partitions (surjections onto k levels); pages, cursors and
sign matrices are rebuilt with key-based sorting, a route separate from the SUT's cmp_to_key.
"""
import argparse
import ast
import gzip
import hashlib
import io
import itertools
import json
import re
import sys
import tarfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
IDS = "ABCD"
POLICIES = ("stable_cursor", "score_only_cursor", "alternating_ties")
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
WITNESSES = ["score_only_cursor|D=asc|R=1110", "stable_cursor|D=asc|R=1110", "alternating_ties|D=asc|R=0000",
             "alternating_ties|D=asc|R=0122", "stable_cursor|D=desc|R=0000"]


def jsonable(v):
    if isinstance(v, dict):
        return {(k if isinstance(k, str) else str(k)): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x) for x in v]
    return v


class Report:
    def __init__(self):
        self.checks = []

    def check(self, name, ok, detail=None):
        self.checks.append({"check": name, "passed": bool(ok), "detail": jsonable(detail)})

    @property
    def ok(self):
        return all(c["passed"] for c in self.checks)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def rank_vectors():
    """Ordered set partitions of four records: surjections onto levels 0..k-1, for k = 1..4."""
    by_k = {}
    for k in range(1, 5):
        by_k[k] = sorted(r for r in itertools.product(range(k), repeat=4) if len(set(r)) == k)
    return sorted(r for v in by_k.values() for r in v), {k: len(v) for k, v in by_k.items()}


def key(policy, ranks, direction, request, i):
    s = 1 if direction == "asc" else -1
    return (s * ranks[i],) if policy == "score_only_cursor" else (s * ranks[i], -i if policy == "alternating_ties" and request % 2 else i)


def model(policy, ranks, direction):
    pages, got, cursor = [], [], None
    for request in range(3):
        k = {i: key(policy, ranks, direction, request, i) for i in range(4)}
        order = sorted(range(4), key=lambda i: k[i])                   # keys are distinct except score-only ties
        matrix = [[(k[i] > k[j]) - (k[i] < k[j]) for j in range(4)] for i in range(4)]
        if policy == "alternating_ties":
            chosen, out, offset = order[2 * request: 2 * request + 2], None, 2 * request
        else:
            chosen = [i for i in order if cursor is None or k[i] > tuple(cursor)][:2]
            out, offset = (list(k[chosen[-1]]) if chosen else None), None
        pages.append({"request": request, "cursor_in": cursor, "offset": offset, "full_order": [IDS[i] for i in order],
                      "comparisons": matrix, "ids": [IDS[i] for i in chosen], "cursor_out": out})
        got += [IDS[i] for i in chosen]
        if not chosen:
            break
        cursor = out
    s = 1 if direction == "asc" else -1
    expected = [IDS[i] for i in sorted(range(4), key=lambda i: (s * ranks[i], i))]
    rk = {IDS[i]: ranks[i] for i in range(4)}
    adj = list(zip(got, got[1:]))
    obl = {"multiset_ok": Counter(got) == Counter(IDS),
           "primary_order_ok": all(s * rk[a] <= s * rk[b] for a, b in adj),
           "stable_ties_ok": all(IDS.index(a) <= IDS.index(b) for a, b in adj if rk[a] == rk[b]),
           "terminated": not pages[-1]["ids"]}
    laws = [laws_of(p["comparisons"], ranks, s) for p in pages]
    lawful = all(all(x.values()) for x in laws)
    verdict = "PASS" if got == expected and all(obl.values()) and lawful else "DOMAIN_FAIL"
    return {"pages": pages, "collected": got, "expected": expected, **obl, "comparator_laws": laws, "comparators_lawful": lawful,
            "verdict": verdict}


def laws_of(m, ranks, s):
    ix = range(4)
    return {"signs_ok": all(m[i][j] in (-1, 0, 1) for i in ix for j in ix),
            "reflexive": all(m[i][i] == 0 for i in ix),
            "antisymmetric": all(m[i][j] + m[j][i] == 0 for i in ix for j in ix),
            "transitive_le": not any(m[i][j] <= 0 and m[j][k] <= 0 and m[i][k] > 0 for i, j, k in itertools.product(ix, repeat=3)),
            "primary_direction": all((m[i][j] > 0) == (s * ranks[i] > s * ranks[j]) for i in ix for j in ix if ranks[i] != ranks[j])}


def allowed_orders(vectors):
    rows = []
    for r in vectors:
        for d in ("asc", "desc"):
            s = 1 if d == "asc" else -1
            st = [IDS[i] for i in sorted(range(4), key=lambda i: (s * r[i], i))]
            alt = []
            for _, grp in itertools.groupby(st, key=lambda c: r[IDS.index(c)]):
                alt += list(grp)[::-1]
            rk = [r[IDS.index(c)] for c in alt]
            valid = sorted(alt) == list(IDS) and all(s * a <= s * b for a, b in zip(rk, rk[1:]))
            stable = valid and all(IDS.index(a) < IDS.index(b) for a, b in zip(alt, alt[1:]) if r[IDS.index(a)] == r[IDS.index(b)])
            rows.append({"ranks": "".join(map(str, r)), "direction": d, "stable": st, "alternative": alt,
                         "has_tie": len(set(r)) < 4, "valid_order": valid, "stable_order": stable})
    return rows


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources = [], None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D8_SOURCES":
            sources = ast.literal_eval(node.value)
    return calls, sources


def case_of(calls):
    if [c[0] for c in calls] != ["impl", "ranks", "direction"]:
        raise ValueError(f"atom order {[c[0] for c in calls]}")
    return f"{calls[0][1]}|D={calls[2][1]}|R={calls[1][1]}"


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    vectors, by_k = rank_vectors()
    own = {f"{p}|D={d}|R={''.join(map(str, r))}": {"policy": p, "direction": d, "ranks": list(r), **model(p, r, d)}
           for r in vectors for d in ("asc", "desc") for p in POLICIES}
    expected_ids = sorted(own)
    rep.check("space.rank_vectors_and_identities", len(vectors) == 75 and by_k == {1: 1, 2: 14, 3: 36, 4: 24}
              and [list(r) for r in vectors] == derived["rank_vectors"] and expected_ids == sorted(frozen) and len(expected_ids) == 450,
              {"by_block_count": by_k})
    fields = ("pages", "collected", "expected", "multiset_ok", "primary_order_ok", "stable_ties_ok", "terminated")
    mism = [c for c, o in own.items() if any(o[f] != frozen[c][f] for f in fields) or o["verdict"] != frozen[c]["predicted_outcome"]
            or o["ranks"] != frozen[c]["ranks"]]
    rep.check("space.frozen_equals_own_model", not mism, {"mismatches": mism[:5]})
    rep.check("comparators.laws_all_cases", all(o["comparators_lawful"] for o in own.values()),
              {"pages_checked": sum(len(o["pages"]) for o in own.values())})

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 450] and c["mandatory"][:2] == ["EXACT", 450] for c in cmp_["cardinality"].values()),
              cmp_["cardinality"])
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    decoded, bad_rows = [], []
    for r in frows:
        try:
            calls = []
            for sheet in ("IMPL", "RANKS", "DIRECTION"):
                (code,) = r.get(cols[sheet]) or base.get(cols[sheet])
                calls.extend(calls_of(code2val[int(code)])[0])
            decoded.append(case_of(calls))
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == 450 for v in counts.values()), counts)
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids
              and sorted(cols) == sorted(["HEAD", "IMPL", "RANKS", "DIRECTION", "TAIL"])
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3]})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            calls, sources = calls_of(data.decode())
            rendered[name] = case_of(calls)
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 450 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    bad, nfields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_population"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [("schema", r["schema"], "d8a.observation/v1"), ("policy", r["policy"], o["policy"]), ("direction", r["direction"], o["direction"]),
                  ("ranks", r["ranks"], o["ranks"]), ("input_ids", r["input_ids"], list(IDS)), ("page_size", r["page_size"], 2),
                  *[(f, r[f], o[f]) for f in fields], *[(f"frozen_{f}", r[f], frozen[cid][f]) for f in fields],
                  ("comparator_laws", r["comparator_laws"], o["comparator_laws"]), ("comparators_lawful", r["comparators_lawful"], True),
                  ("verdict", r["verdict"], o["verdict"]), ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]),
                  ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("outcome", fw["outcome"], o["verdict"]), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("requests_bound", len(r["pages"]) <= 3, True), ("source_sha256", r["source_sha256"], module_sha),
                  ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])), ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        nfields += len(checks)
        bad += [(cid, n, str(got)[:80], str(want)[:80]) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": nfields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    by_pd = {f"{p}/{d}": dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p and r["direction"] == d))
             for p in POLICIES for d in ("asc", "desc")}
    tie = {f"{p}/{'tied' if len(set(r_['ranks'])) < 4 else 'strict'}": None for p in POLICIES for r_ in records.values()}
    for k in tie:
        p, kind = k.split("/")
        tie[k] = dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p and (len(set(r["ranks"])) < 4) == (kind == "tied")))
    rep.check("observations.totals", dict(totals) == derived["outcomes"] == {"PASS": 330, "DOMAIN_FAIL": 120} and by_policy == derived["by_policy"]
              and by_pd == {"stable_cursor/asc": {"PASS": 75}, "stable_cursor/desc": {"PASS": 75},
                            "score_only_cursor/asc": {"PASS": 54, "DOMAIN_FAIL": 21}, "score_only_cursor/desc": {"PASS": 54, "DOMAIN_FAIL": 21},
                            "alternating_ties/asc": {"PASS": 36, "DOMAIN_FAIL": 39}, "alternating_ties/desc": {"PASS": 36, "DOMAIN_FAIL": 39}}
              and all(tie[f"{p}/strict"] == {"PASS": 48} for p in POLICIES),
              {"totals": dict(totals), "by_policy": by_policy, "by_policy_direction": by_pd, "tied_vs_strict": tie})
    fails = [r for r in records.values() if r["verdict"] == "DOMAIN_FAIL"]
    kinds = Counter((r["policy"], "omission" if not r["multiset_ok"] and len(r["collected"]) < 4 else
                     "duplicate+omission" if not r["multiset_ok"] else "unstable_ties" if not r["stable_ties_ok"] else "other") for r in fails)
    ids = lambda c: [p["ids"] for p in records[c]["pages"]]          # noqa: E731
    mech = {"score_only_cursor|D=asc|R=1110": ids("score_only_cursor|D=asc|R=1110"), "stable_cursor|D=asc|R=1110": ids("stable_cursor|D=asc|R=1110"),
            "alternating_ties|D=asc|R=0000": ids("alternating_ties|D=asc|R=0000"), "alternating_ties|D=asc|R=0122": ids("alternating_ties|D=asc|R=0122")}
    rep.check("demonstration.mechanisms", mech == {"score_only_cursor|D=asc|R=1110": [["D", "A"], []],
                                                   "stable_cursor|D=asc|R=1110": [["D", "A"], ["B", "C"], []],
                                                   "alternating_ties|D=asc|R=0000": [["A", "B"], ["B", "A"], []],
                                                   "alternating_ties|D=asc|R=0122": [["A", "B"], ["D", "C"], []]}
              and all(records[c]["comparators_lawful"] for c in mech), {"pages": mech, "failure_kinds": {f"{p}/{k}": n for (p, k), n in kinds.items()}})
    proof = json.loads((root / "proof" / "allowed-orders.json").read_text())
    rows = allowed_orders(vectors)
    rep.check("demonstration.allowed_order_proof", rows == proof["rows"] and len(rows) == 150 and all(x["valid_order"] for x in rows)
              and sum(not x["stable_order"] for x in rows) == 102 and sum(x["stable_order"] for x in rows) == 48
              and all(x["stable_order"] != x["has_tie"] for x in rows)
              and next(x for x in rows if x["ranks"] == "0000" and x["direction"] == "asc")["alternative"] == ["D", "C", "B", "A"],
              proof["summary"])

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "500", "--budget-final-candidates", "500", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "1200"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    dbm = manifest["databases"]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(r"as0927_d8a_[0-9a-z_]+", dbm["name"]) is not None
              and not any(v["exists_before"] for v in dbm["absence_checked"].values())
              and set(dbm.get("retained_bytes", {})) == {"main", "results"}, {"retained_bytes": dbm.get("retained_bytes"),
                                                                              "run_dir_bytes": manifest.get("run_dir_bytes")})
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    xl, tm = fg.load_spec(root / "spec" / "demo.xlsx"), fg.load_spec(root / "spec" / "spec.toml")
    rep.check("provenance.workbook_toml_and_core_input", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"]
              and [(s.sheet, list(s.values)) for s in xl.slots] == [(s.sheet, list(s.values)) for s in tm.slots])
    return rep, {"stage_counts": counts, "totals": dict(totals), "by_policy": by_policy,
                 "extra": {"by_policy_direction": by_pd, "tied_vs_strict": tie, "mechanisms": mech,
                           "failure_kinds": {f"{p}/{k}": n for (p, k), n in kinds.items()}, "allowed_orders": proof["summary"]},
                 "records": records}


def witnesses(run, data):
    out = []
    for case in WITNESSES:
        r = data["records"][case]
        out.append({"case_id": case, "candidate": r["framework"]["source_ref"],
                    "pages": [{k: p[k] for k in ("request", "cursor_in", "offset", "full_order", "ids", "cursor_out")} for p in r["pages"]],
                    "collected": r["collected"], "expected": r["expected"],
                    "obligations": {k: r[k] for k in ("multiset_ok", "primary_order_ok", "stable_ties_ok", "terminated")},
                    "comparators_lawful": r["comparators_lawful"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d8a.witnesses/v1", "run": run.name, "witnesses": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--inputs-root", type=Path, default=HERE)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    run = a.run.resolve()
    out_dir = (a.out or run).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rep, data = verify(run, a.inputs_root.resolve())
    doc = {"schema": "d8a.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: jsonable(data[k]) for k in ("stage_counts", "totals", "by_policy", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
