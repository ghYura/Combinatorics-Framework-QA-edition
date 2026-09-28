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

"""Independent offline verifier for the D8b evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py, topo_orders.py or derive.py, never
connects to a database, never executes a candidate (candidates and dictionary values are parsed with
`ast`). Path counts come from enumerating increasing intermediate-node subsets; fresh values are
sum(base[u] * paths[u][v]); dirty sets use path counts (not graph traversal); every policy trace is
rebuilt and compared field by field.
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
SLOTS = list(itertools.combinations(range(4), 2))
BASE = [1, 2, 4, 8]
POLICIES = ("closure_forward", "direct_only", "closure_reverse")
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
WITNESSES = ["direct_only|G=100100|U=A", "closure_forward|G=100100|U=A", "closure_reverse|G=100100|U=A",
             "direct_only|G=110100|U=A", "closure_forward|G=111111|U=A"]
FIELDS = ("bits", "edges", "edit", "before_inputs", "after_inputs", "before_values", "post_edit_cache", "path_counts", "reference",
          "expected_delta", "affected", "dirty", "evaluation_order", "updates", "after_values", "mismatched_nodes")


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


def paths_of(edges):
    """Directed path counts: for u < v, every increasing chain u < w1 < ... < v whose steps are all edges."""
    e = set(edges)
    p = [[int(u == v) for v in range(4)] for u in range(4)]
    for u in range(4):
        for v in range(u + 1, 4):
            between = range(u + 1, v)
            for k in range(len(between) + 1):
                for mid in itertools.combinations(between, k):
                    chain = (u, *mid, v)
                    p[u][v] += all((a, b) in e for a, b in zip(chain, chain[1:]))
    return p


def fresh(base, p):
    return [sum(base[u] * p[u][v] for u in range(4)) for v in range(4)]


def model(policy, bits, edit):
    edges = [e for e, b in zip(SLOTS, bits) if b]
    p = paths_of(edges)
    before = fresh(BASE, p)
    base = list(BASE)
    base[edit] += 10
    ref = fresh(base, p)
    reach = [v for v in range(4) if p[edit][v]]
    dirty = sorted({edit, *[v for v in range(4) if (edit, v) in edges]}) if policy == "direct_only" else reach
    order = sorted(dirty, reverse=policy == "closure_reverse")
    cache, updates = list(before), []
    for v in order:
        reads = [{"node": IDS[u], "value": cache[u]} for u in range(4) if (u, v) in edges]
        prev, cache[v] = cache[v], base[v] + sum(r["value"] for r in reads)
        updates.append({"node": IDS[v], "base": base[v], "parent_reads": reads, "previous": prev, "new": cache[v], "cache": list(cache)})
    wrong = [IDS[v] for v in range(4) if cache[v] != ref[v]]
    return {"policy": policy, "bits": list(bits), "edges": [list(x) for x in edges], "edit": IDS[edit], "before_inputs": list(BASE),
            "after_inputs": base, "before_values": before, "post_edit_cache": list(before), "path_counts": p, "reference": ref,
            "expected_delta": [10 * p[edit][v] for v in range(4)], "affected": [IDS[v] for v in reach], "dirty": [IDS[v] for v in dirty],
            "evaluation_order": [IDS[v] for v in order], "updates": updates, "after_values": cache, "mismatched_nodes": wrong,
            "verdict": "DOMAIN_FAIL" if wrong else "PASS"}


def topo_proof():
    graphs, adds = [], []
    for bits in itertools.product((0, 1), repeat=6):
        edges = [e for e, b in zip(SLOTS, bits) if b]
        valid = lambda es: ["".join(IDS[v] for v in perm) for perm in itertools.permutations(range(4))       # noqa: E731
                            if all(perm.index(u) < perm.index(v) for u, v in es)]
        o = valid(edges)
        code = "".join(map(str, bits))
        graphs.append({"bits": code, "topological_orders": o})
        p = paths_of(edges)
        for k, (u, v) in enumerate(SLOTS):
            if not bits[k] and p[u][v]:
                after = list(bits)
                after[k] = 1
                o2 = valid(edges + [(u, v)])
                adds.append({"before": code, "after": "".join(map(str, after)), "added_edge": [u, v], "orders_before": o,
                             "orders_after": o2, "equal_sets": o == o2, "lexicographic_minimum": [min(o), min(o2)]})
    return graphs, adds


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
    names = [c[0] for c in calls]
    if names != ["impl"] + ["edge"] * 6 + ["edit"]:
        raise ValueError(f"atom order {names}")
    edges = calls[1:7]
    if [(IDS.index(c[1]), IDS.index(c[2])) for c in edges] != SLOTS or any(c[3] not in (0, 1) for c in edges):
        raise ValueError("edge slots out of order or non-binary")
    return f"{calls[0][1]}|G={''.join(str(c[3]) for c in edges)}|U={calls[7][1]}"


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    graphs = list(itertools.product((0, 1), repeat=6))
    own = {f"{p}|G={''.join(map(str, b))}|U={IDS[e]}": model(p, b, e) for b in graphs for e in range(4) for p in POLICIES}
    expected_ids = sorted(own)
    rep.check("space.graphs_and_identities", len(graphs) == 64 and len(expected_ids) == 768 and expected_ids == sorted(frozen)
              and derived["edge_bit_order"] == [list(s) for s in SLOTS] and derived["before_inputs"] == BASE,
              {"graphs": 64, "identities": len(expected_ids)})
    mism = [c for c, o in own.items() if any(o[f] != frozen[c][f] for f in FIELDS) or o["verdict"] != frozen[c]["predicted_outcome"]]
    rep.check("space.frozen_equals_own_model", not mism, {"mismatches": mism[:5]})

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 768] and c["mandatory"][:2] == ["EXACT", 768] for c in cmp_["cardinality"].values()),
              cmp_["cardinality"])
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    order_sheets = ["IMPL"] + [f"EDGE_{IDS[u]}{IDS[v]}" for u, v in SLOTS] + ["EDIT"]
    decoded, bad_rows = [], []
    for r in frows:
        try:
            calls = []
            for sheet in order_sheets:
                (code,) = r.get(cols[sheet]) or base.get(cols[sheet])
                calls.extend(calls_of(code2val[int(code)])[0])
            decoded.append(case_of(calls))
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == 768 for v in counts.values()), counts)
    bits_seen = {cid.split("|")[1][2:] for cid in decoded}
    axes = {f"EDGE_{IDS[u]}{IDS[v]}": sorted({b[k] for b in bits_seen}) for k, (u, v) in enumerate(SLOTS)}
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids and set(cols) == {"HEAD", "TAIL", *order_sheets}
              and len(bits_seen) == 64 and {"000000", "111111"} <= bits_seen and all(v == ["0", "1"] for v in axes.values())
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3], "edge_axes": axes})

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
    rep.check("executor.one_attempt_each", len(rv2) == 768 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
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
        checks = [("schema", r["schema"], "d8b.observation/v1"), ("policy", r["policy"], o["policy"]),
                  *[(f, r[f], o[f]) for f in FIELDS], *[(f"frozen_{f}", r[f], frozen[cid][f]) for f in FIELDS],
                  ("before_reference", r["before_reference"], o["before_values"]), ("verdict", r["verdict"], o["verdict"]),
                  ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2),
                  ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], o["verdict"]),
                  ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("evaluations_bound", len(r["updates"]) <= 4, True),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        nfields += len(checks)
        bad += [(cid, n, str(got)[:80], str(want)[:80]) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": nfields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    by_edit = {f"{p}/{u}": dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p and r["edit"] == u))
               for p in POLICIES for u in IDS}
    empty_ok = all(records[f"{p}|G=000000|U={u}"]["verdict"] == "PASS" for p in POLICIES for u in IDS)
    rep.check("observations.totals", dict(totals) == derived["outcomes"] == {"PASS": 604, "DOMAIN_FAIL": 164}
              and by_policy == derived["by_policy"] and empty_ok, {"totals": dict(totals), "by_policy": by_policy, "by_edit": by_edit,
                                                                   "empty_graph_passes_all_policies": empty_ok})

    # ---- mechanisms: missing invalidation versus stale parent reads ----
    def stale_reads(r):
        order = r["evaluation_order"]
        return [(up["node"], rd["node"]) for up in r["updates"] for rd in up["parent_reads"]
                if rd["node"] in order and order.index(rd["node"]) > order.index(up["node"])]
    fails = [r for r in records.values() if r["verdict"] == "DOMAIN_FAIL"]
    direct = [r for r in fails if r["policy"] == "direct_only"]
    rev = [r for r in fails if r["policy"] == "closure_reverse"]
    def explained_by_missing(r):
        missed = set(r["affected"]) - set(r["dirty"])
        read_missed = {up["node"] for up in r["updates"] if any(rd["node"] in missed for rd in up["parent_reads"])}
        return bool(missed) and all(m in missed or m in read_missed for m in r["mismatched_nodes"])
    stale_through_dirty = sorted(r["case_id"] for r in direct if not set(r["mismatched_nodes"]) <= set(r["affected"]) - set(r["dirty"]))
    mech = {"direct_only_missing_invalidation": all(r["mismatched_nodes"] and explained_by_missing(r) for r in direct),
            "closure_reverse_dirty_complete_but_stale_reads": all(r["dirty"] == r["affected"] and stale_reads(r) for r in rev),
            "closure_forward_never_fails": not any(r["policy"] == "closure_forward" for r in fails)}
    w = {c: records[c] for c in WITNESSES}
    wit_ok = (w["direct_only|G=100100|U=A"]["dirty"] == ["A", "B"] and w["direct_only|G=100100|U=A"]["mismatched_nodes"] == ["C"]
              and w["closure_forward|G=100100|U=A"]["after_values"] == w["closure_forward|G=100100|U=A"]["reference"]
              and w["closure_reverse|G=100100|U=A"]["evaluation_order"] == ["C", "B", "A"]
              and w["closure_reverse|G=100100|U=A"]["dirty"] == w["closure_reverse|G=100100|U=A"]["affected"] == ["A", "B", "C"]
              and w["closure_reverse|G=100100|U=A"]["verdict"] == "DOMAIN_FAIL"
              and w["direct_only|G=110100|U=A"]["dirty"] == ["A", "B", "C"] and w["direct_only|G=110100|U=A"]["verdict"] == "PASS"
              and w["closure_forward|G=111111|U=A"]["path_counts"][0][3] == 4 and w["closure_forward|G=111111|U=A"]["expected_delta"][3] == 40
              and w["closure_forward|G=111111|U=A"]["verdict"] == "PASS")
    rep.check("demonstration.mechanisms_and_witnesses", all(mech.values()) and wit_ok,
              {**mech, "direct_only_failures": len(direct), "closure_reverse_failures": len(rev),
               "direct_only_dirty_node_wrong_via_missed_parent": stale_through_dirty})
    graphs_p, adds = topo_proof()
    proof = json.loads((root / "proof" / "topological-orders.json").read_text())
    ex = next(a for a in adds if a["before"] == "100010" and a["after"] == "101010")
    rep.check("demonstration.topological_order_proof", proof["graphs"] == graphs_p and proof["redundant_edge_additions"] == adds
              and sum(len(g["topological_orders"]) for g in graphs_p) == 315 and len(adds) == 31 and all(a["equal_sets"] for a in adds)
              and all(x in ex["orders_before"] and x in ex["orders_after"] for x in ("ABCD", "CABD"))
              and graphs_p == derived["topology_proof"]["graphs"]
              and [(a["before"], a["after"], a["added_edge"], a["orders_before"]) for a in adds]
              == [(a["before"], a["after"], a["added_edge"], a["topological_orders"]) for a in derived["topology_proof"]["redundant_edge_additions"]],
              proof["summary"])

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "1000", "--budget-final-candidates", "1000", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "1800"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    dbm = manifest["databases"]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(r"as0927_d8b_[0-9a-z_]+", dbm["name"]) is not None
              and not any(v["exists_before"] for v in dbm["absence_checked"].values()) and set(dbm.get("retained_bytes", {})) == {"main", "results"},
              {"retained_bytes": dbm.get("retained_bytes"), "run_dir_bytes": manifest.get("run_dir_bytes")})
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
                 "extra": {"by_policy_edit": by_edit, "mechanisms": mech, "topology": proof["summary"],
                           "direct_only_dirty_node_wrong_via_missed_parent": stale_through_dirty}, "records": records}


def witnesses(run, data):
    out = []
    for case in WITNESSES:
        r = data["records"][case]
        out.append({"case_id": case, "candidate": r["framework"]["source_ref"], "edges": r["edges"], "before_values": r["before_values"],
                    "post_edit_cache": r["post_edit_cache"], "dirty": r["dirty"], "evaluation_order": r["evaluation_order"],
                    "updates": r["updates"], "after_values": r["after_values"], "reference": r["reference"],
                    "expected_delta": r["expected_delta"], "mismatched_nodes": r["mismatched_nodes"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d8b.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d8b.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
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
