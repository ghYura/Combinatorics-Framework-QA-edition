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

"""Independent offline verifier for the D7 evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py or derive.py, never connects to a
database, never executes a candidate (candidates and dictionary values are parsed with `ast`).
Trees are generated here and each ID is parsed as a nested tuple literal. The binary64 tree result
is re-derived by adding the represented child values as Fractions and rounding that exact sum to a
float at every node (not native float '+'); flat_fsum is checked against the correctly rounded exact
reference (not math.fsum); exact trees must equal the linear rational reference.
"""
import argparse
import ast
import gzip
import hashlib
import io
import json
import math
import re
import sys
import tarfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
POLICIES = ("tree_binary64", "flat_fsum", "tree_rational")
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
BINARY64_BUDGETS = {"small_integers": Fraction(0), "cancellation": Fraction(1, 4), "swamped": Fraction(1),
                    "decimal_inputs": Fraction(1, 2 ** 52)}          # the contract's table
IDEAL_DECIMALS = {"decimal_inputs": [Fraction(1, 10), Fraction(2, 10), Fraction(3, 10), Fraction(4, 10), Fraction(5, 10)]}


def jsonable(v):
    if isinstance(v, Fraction):
        return {"n": str(v.numerator), "d": str(v.denominator)}
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


def rq(r):
    return Fraction(int(r["n"]), int(r["d"]))


# ---- trees, generated and parsed independently ----
def all_trees():
    memo = {}
    def span(lo, hi):
        if (lo, hi) not in memo:
            memo[(lo, hi)] = [lo] if hi - lo == 1 else [(a, b) for mid in range(lo + 1, hi) for a in span(lo, mid) for b in span(mid, hi)]
        return memo[(lo, hi)]
    return span(0, 5)


def tid(t):
    return str(t) if isinstance(t, int) else "(" + tid(t[0]) + "," + tid(t[1]) + ")"


def flat(t):
    return [t] if isinstance(t, int) else flat(t[0]) + flat(t[1])


def rounded_tree(t, xs):
    """(float result, nodes): Fraction sum of the represented children, rounded to binary64 per node."""
    nodes = []
    def go(n):
        if isinstance(n, int):
            return xs[n]
        v = float(Fraction(go(n[0])) + Fraction(go(n[1])))
        nodes.append({"node": tid(n), "hex": v.hex()})
        return v
    return go(t), nodes


def exact_tree(t, xs):
    nodes = []
    def go(n):
        if isinstance(n, int):
            return Fraction(xs[n])
        v = go(n[0]) + go(n[1])
        nodes.append({"node": tid(n), "n": str(v.numerator), "d": str(v.denominator)})
        return v
    return go(t), nodes


def half_ulp(x):
    """Half the unit in the last place of a positive normal binary64 value, exactly."""
    m, e = math.frexp(x)               # x = m * 2**e, 0.5 <= m < 1
    return Fraction(1, 2) * Fraction(2) ** (e - 53)


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources = [], None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D7_SOURCES":
            sources = ast.literal_eval(node.value)
    return calls, sources


def case_of(calls):
    if [c[0] for c in calls] != ["impl", "vector", "tree"]:
        raise ValueError(f"atom order {[c[0] for c in calls]}")
    return f"{calls[0][1]}|V={calls[1][1]}|T={calls[2][1]}", calls[1]


def witness_ids(frozen):
    cases = sorted(frozen.values(), key=lambda c: (c["tree"], c["policy"]))
    canc = [c for c in cases if c["policy"] == "tree_binary64" and c["vector"] == "cancellation"]
    first_fail = next(c for c in canc if c["predicted_outcome"] == "DOMAIN_FAIL")
    first_pass = next(c for c in canc if c["predicted_outcome"] == "PASS")
    swamped = next(c for c in cases if c["policy"] == "tree_binary64" and c["vector"] == "swamped"
                   and c["predicted_outcome"] == "PASS" and rq(c["absolute_error"]) != 0)
    t = first_fail["tree"]
    return {"binary64_cancellation_first_fail": first_fail["id"], "binary64_cancellation_first_pass": first_pass["id"],
            "binary64_swamped_nonzero_within_budget": swamped["id"],
            "flat_fsum_on_first_failing_tree": f"flat_fsum|V=cancellation|T={t}",
            "tree_rational_on_first_failing_tree": f"tree_rational|V=cancellation|T={t}"}


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    trees = all_trees()
    ids = sorted(tid(t) for t in trees)
    parsed_ok = all(ast.literal_eval(i) == t and flat(t) == [0, 1, 2, 3, 4] for i, t in ((tid(t), t) for t in trees))
    rep.check("space.fourteen_bracketings", len(trees) == 14 and len(set(ids)) == 14 and parsed_ok and ids == derived["trees"], ids)

    # ---- vectors, references and budgets ----
    vec = {}
    for vid, v in derived["vectors"].items():
        xs = [float.fromhex(h) for h in v["hex"]]
        exact = sum((Fraction(x) for x in xs), Fraction(0))
        budgets = {"tree_binary64": BINARY64_BUDGETS[vid], "flat_fsum": half_ulp(float(exact)), "tree_rational": Fraction(0)}
        vec[vid] = {"xs": xs, "exact": exact, "budgets": budgets}
    vec_ok = all(rq(v["exact_sum"]) == vec[k]["exact"] and {p: rq(b) for p, b in v["absolute_budgets"].items()} == vec[k]["budgets"]
                 and all(math.isfinite(x) for x in vec[k]["xs"]) for k, v in derived["vectors"].items())
    ideal = sum(IDEAL_DECIMALS["decimal_inputs"], Fraction(0))
    represented = vec["decimal_inputs"]["exact"]
    rep.check("space.vectors_references_budgets", vec_ok and represented != ideal and list(derived["vectors"]) ==
              ["small_integers", "cancellation", "swamped", "decimal_inputs"],
              {"exact_sums": {k: v["exact"] for k, v in vec.items()}, "budgets": {k: v["budgets"] for k, v in vec.items()},
               "decimal_inputs": {"represented_exact_sum": represented, "ideal_decimal_sum": ideal, "difference": represented - ideal}})

    own = {}
    for vid, v in vec.items():
        for t in trees:
            for p in POLICIES:
                if p == "tree_binary64":
                    res, nodes = rounded_tree(t, v["xs"])
                elif p == "flat_fsum":
                    res, nodes = float(v["exact"]), []            # the correctly rounded exact sum
                else:
                    res, nodes = exact_tree(t, v["xs"])
                err = abs(Fraction(res) - v["exact"])
                own[f"{p}|V={vid}|T={tid(t)}"] = {"policy": p, "vector": vid, "tree": tid(t), "result": res, "nodes": nodes,
                                                  "error": err, "budget": v["budgets"][p],
                                                  "verdict": "PASS" if err <= v["budgets"][p] else "DOMAIN_FAIL"}
    expected_ids = sorted(own)
    rep.check("space.frozen_equals_own_model", expected_ids == sorted(frozen) and len(expected_ids) == 168 and all(
        rq(frozen[c]["predicted_result"]) == Fraction(o["result"]) and rq(frozen[c]["absolute_error"]) == o["error"]
        and rq(frozen[c]["budget"]) == o["budget"] and frozen[c]["predicted_outcome"] == o["verdict"]
        and frozen[c]["predicted_hex"] == (o["result"].hex() if isinstance(o["result"], float) else None) for c, o in own.items()))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 168] for c in cmp_["cardinality"].values()), cmp_["cardinality"])
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    decoded, bad_rows, vec_cells = [], [], {}
    for r in frows:
        try:
            calls = []
            for sheet in ("IMPL", "VECTOR", "TREE"):
                (code,) = r.get(cols[sheet]) or base.get(cols[sheet])
                calls.extend(calls_of(code2val[int(code)])[0])
            cid, vcall = case_of(calls)
            decoded.append(cid)
            vec_cells[vcall[1]] = vcall[2:]
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    cells_ok = all(list(vec_cells[k][0]) == v["hex"] and {p: (b["n"], b["d"]) for p, b in v["absolute_budgets"].items()} == vec_cells[k][1]
                   for k, v in derived["vectors"].items())
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == 168 for v in counts.values()), counts)
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids and sorted(cols) == ["HEAD", "IMPL", "TAIL", "TREE", "VECTOR"]
              and cells_ok and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3]})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            calls, sources = calls_of(data.decode())
            rendered[name] = case_of(calls)[0]
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 168 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    container = manifest.get("python", {}).get("container") or []
    bad, fields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_population"))
            continue
        o, fw = own[cid], r["framework"]
        want_result = {"hex": o["result"].hex()} if isinstance(o["result"], float) else {"n": str(o["result"].numerator), "d": str(o["result"].denominator)}
        checks = [("schema", r["schema"], "d7.observation/v1"), ("policy", r["policy"], o["policy"]), ("vector", r["vector"], o["vector"]),
                  ("tree", r["tree"], o["tree"]), ("leaf_order", r["leaf_order"], [0, 1, 2, 3, 4]),
                  ("input_hex", r["input_hex"], derived["vectors"][o["vector"]]["hex"]), ("result", r["result"], want_result),
                  ("nodes", r["nodes"], o["nodes"]), ("reference", rq(r["reference"]), vec[o["vector"]]["exact"]),
                  ("absolute_error", rq(r["absolute_error"]), o["error"]), ("finite", r["finite"], True),
                  ("budget", rq(r["budget"]), o["budget"]), ("frozen_budget", r["budget"], frozen[cid]["budget"]),
                  ("verdict", r["verdict"], o["verdict"]), ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]),
                  ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("outcome", fw["outcome"], o["verdict"]), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("environment", (r["environment"]["float_radix"], r["environment"]["float_mant_dig"]), (2, 53)),
                  ("container_python", r["environment"]["python"], container[0] if container else None),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        fields += len(checks)
        bad += [(cid, n, str(got), str(want)) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    table = {}
    for vid in vec:
        for p in POLICIES:
            rs = [r for r in records.values() if r["vector"] == vid and r["policy"] == p]
            table[f"{vid}/{p}"] = {"cases": len(rs), "verdicts": dict(Counter(r["verdict"] for r in rs)),
                                   "distinct_outputs": sorted({json.dumps(r["result"], sort_keys=True) for r in rs}),
                                   "max_abs_error": max(rq(r["absolute_error"]) for r in rs)}
    rep.check("observations.totals", dict(totals) == derived["outcomes"] and by_policy == derived["by_policy"]
              and table["cancellation/tree_binary64"]["verdicts"] == {"PASS": 9, "DOMAIN_FAIL": 5}
              and table["swamped/tree_binary64"]["verdicts"] == {"PASS": 7, "DOMAIN_FAIL": 7}, {"totals": dict(totals), "by_policy": by_policy})

    # ---- demonstrations ----
    b64 = {v: {r["tree"]: r["result"]["hex"] for r in records.values() if r["policy"] == "tree_binary64" and r["vector"] == v} for v in vec}
    shape_sensitive = {v: sorted(set(m.values())) for v, m in b64.items() if len(set(m.values())) > 1}
    nonzero_pass = sorted(c for c, r in records.items() if r["verdict"] == "PASS" and rq(r["absolute_error"]) != 0)
    rep.check("demonstration.bracketing_changes_binary64_results", set(shape_sensitive) == {"cancellation", "swamped"}
              and all(len(set(table[f"{v}/{p}"]["distinct_outputs"])) == 1 for v in vec for p in ("flat_fsum", "tree_rational")),
              {"binary64_distinct_by_vector": shape_sensitive})
    rep.check("demonstration.nonzero_error_within_budget", bool(nonzero_pass)
              and any(c.startswith("tree_binary64|V=swamped") for c in nonzero_pass) and any("V=decimal_inputs" in c for c in nonzero_pass),
              {"count": len(nonzero_pass), "vectors": dict(Counter(c.split("|")[1] for c in nonzero_pass))})
    wit = witness_ids(frozen)
    extra = {"per_vector_policy": table, "witnesses": wit, "nonzero_error_passes": nonzero_pass,
             "decimal_inputs": {"represented_exact_sum": represented, "ideal_decimal_sum": ideal, "difference": represented - ideal,
                                "binary64_results": sorted(set(b64["decimal_inputs"].values()))}}

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "200", "--budget-final-candidates", "200", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "600"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d7_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g_and_python", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2
              and container[1:] == ["2", "53"] and manifest["python"]["host"][1:] == ["2", "53"], manifest.get("python"))
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"])
    return rep, {"stage_counts": counts, "totals": dict(totals), "by_policy": by_policy, "extra": extra, "records": records, "witnesses": wit}


def witnesses(run, data):
    out = []
    for label, case in data["witnesses"].items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "result": r["result"], "nodes": r["nodes"],
                    "reference": r["reference"], "absolute_error": r["absolute_error"], "budget": r["budget"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    for case in sorted(c for c in data["records"] if c.startswith("tree_binary64|V=decimal_inputs"))[:1]:
        r = data["records"][case]
        out.append({"label": "decimal_inputs_illustration", "case_id": case, "candidate": r["framework"]["source_ref"], "result": r["result"],
                    "reference": r["reference"], "absolute_error": r["absolute_error"], "budget": r["budget"], "verdict": r["verdict"],
                    "replay": "not replayed: shown from its original observation"})
    return {"schema": "d7.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d7.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: jsonable(data[k]) for k in ("stage_counts", "totals", "by_policy", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in data["witnesses"].values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
