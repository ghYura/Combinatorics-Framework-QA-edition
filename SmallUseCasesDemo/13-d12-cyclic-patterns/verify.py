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

"""Independent offline verifier for one D12 evidence directory (campaign words or classes).

    python verify.py --run evidence/<words-run> [--inputs-root DIR] [--out DIR]
    python verify.py --run evidence/<classes-run> --words-run evidence/<words-run>

Reads files only: never imports sut.py, oracle.py, runtime.py, analysis.py or derive.py, never
connects to a database, never executes a candidate (candidates and dictionary values are parsed with
`ast`). Scores and rotation structure are recomputed here; the partition, the three population
summaries and (for classes) the agreement with the words run are recomputed from observed rows.
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
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
M = {"AA": 2, "AB": 0, "AC": 3, "BA": 3, "BB": 2, "BC": 0, "CA": 0, "CB": 3, "CC": 2}
WORDS = ["".join(w) for w in itertools.product("ABC", repeat=6)]
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
EXPECTED = {"words": 729, "classes": 130}
WITNESSES = {"words": ["W=AAAAAB", "W=BAAAAA", "W=ABCABC", "W=ACBACB"], "classes": ["W=ABCABC"]}
FIELDS = ("word", "counts", "edge_counts", "edge_costs", "transition_cost", "balance_penalty", "total_cost", "representative",
          "orbit_size", "period", "stabilizer_size")


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


def orbit(w):
    return sorted({w[i:] + w[:i] for i in range(6)})


def score(w):
    edges = [w[i] + w[(i + 1) % 6] for i in range(6)]
    counts = [w.count(c) for c in "ABC"]
    ec = [[edges.count(a + b) for b in "ABC"] for a in "ABC"]
    t = sum(M[e] for e in edges)
    bal = sum((c - 2) ** 2 for c in counts)
    o = orbit(w)
    per = min(k for k in range(1, 7) if w[k:] + w[:k] == w)
    return {"word": w, "counts": counts, "edge_counts": ec, "edge_costs": [M[e] for e in edges], "transition_cost": t,
            "balance_penalty": bal, "total_cost": t + bal, "representative": o[0], "orbit_size": len(o), "period": per,
            "stabilizer_size": 6 // len(o)}


def open_score(w):
    """A defective scorer that drops the closing edge (used by the tests and the seam demonstration)."""
    t = sum(M[w[i] + w[i + 1]] for i in range(5))
    return t + sum((w.count(c) - 2) ** 2 for c in "ABC")


def rows_of(run, campaign, expected):
    recs = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    cnt = Counter(r["case_id"] for r in recs)
    ok = sorted(cnt) == sorted(f"W={w}" for w in expected) and all(n == 1 for n in cnt.values()) \
        and all(r["verdict"] == "PASS" and r["campaign"] == campaign and r["case_id"] == f"W={r['word']}" for r in recs)
    return ({r["word"]: r for r in recs} if ok else None), recs


def populations(word_costs, class_costs, reps):
    sizes = {r: len(orbit(r)) for r in reps}
    def hist(pairs):
        h = Counter()
        for c, w in pairs:
            h[c] += w
        return {str(k): v for k, v in sorted(h.items())}
    def mean(pairs):
        return Fraction(sum(c * w for c, w in pairs), sum(w for _, w in pairs))
    words = [(word_costs[w], 1) for w in WORDS]
    uni = [(class_costs[r], 1) for r in reps]
    wtd = [(class_costs[r], sizes[r]) for r in reps]
    return {"words": (hist(words), mean(words)), "classes_uniform": (hist(uni), mean(uni)), "classes_weighted": (hist(wtd), mean(wtd))}


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources, phase = [], None, None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D12_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase = ast.literal_eval(node.value.args[0])
    return calls, sources, phase


def word_of(calls, campaign):
    if campaign == "words":
        if [c[0] for c in calls] != ["place"] * 6 or [c[1] for c in calls] != list(range(6)) or any(c[2] not in "ABC" for c in calls):
            raise ValueError(f"place atoms {calls}")
        return "".join(c[2] for c in calls)
    if [c[0] for c in calls] != ["pattern"] or orbit(calls[0][1])[0] != calls[0][1]:
        raise ValueError(f"pattern atoms {calls}")
    return calls[0][1]


def verify(run: Path, root: Path, words_run: Path | None):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    campaign = manifest["campaign"]
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["word"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    reps = sorted({orbit(w)[0] for w in WORDS})
    population = WORDS if campaign == "words" else reps
    own = {w: score(w) for w in WORDS}
    expected_ids = sorted(f"W={w}" for w in population)
    rep.check("space.identities", len(population) == EXPECTED[campaign] and len(reps) == 130 and reps == derived["representatives"]
              and sorted(frozen) == WORDS, {"campaign": campaign, "population": len(population)})
    rep.check("space.frozen_equals_own_model", all(all(own[w][k] == frozen[w][k] for k in FIELDS) and frozen[w]["predicted_outcome"] == "PASS"
                                                   for w in WORDS))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    n = EXPECTED[campaign]
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", n] and c["mandatory"][:2] == ["EXACT", n] for c in cmp_["cardinality"].values()),
              cmp_["cardinality"])
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    sheets = [f"P{i}" for i in range(6)] if campaign == "words" else ["PATTERN"]
    decoded, bad_rows = [], []
    for r in frows:
        try:
            calls = []
            for sheet in sheets:
                (code,) = r.get(cols[sheet]) or base.get(cols[sheet])
                calls.extend(calls_of(code2val[int(code)])[0])
            decoded.append(f"W={word_of(calls, campaign)}")
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == n for v in counts.values()), counts)
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids and set(cols) == {"HEAD", "TAIL", *sheets}
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3], "columns": sorted(cols)})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            calls, sources, phase = calls_of(data.decode())
            rendered[name] = f"W={word_of(calls, campaign)}"
            if phase != campaign:
                raise ValueError(f"phase {phase}")
        except (ValueError, SyntaxError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == n and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    rows, recs = rows_of(run, campaign, population)
    rep.check("identity.executor", rows is not None and sorted(f"W={w}" for w in rows) == expected_ids)
    bad, nf = [], 0
    for r in recs:
        w, fw = r["word"], r["framework"]
        checks = [("schema", r["schema"], "d12.observation/v1"), ("campaign", r["campaign"], campaign),
                  *[(k, r[k], own[w][k]) for k in FIELDS], *[(f"frozen_{k}", r[k], frozen[w][k]) for k in FIELDS],
                  ("reference", {k: r["reference"][k] for k in r["reference"]}, {k: own[w][k] for k in r["reference"]}),
                  ("oracle_agrees", r["oracle_agrees"], True), ("verdict", r["verdict"], "PASS"), ("fw_var", r["fw_var"], 0),
                  ("metrics_fw_var", fw["metrics_fw_var"], 0), ("outcome", fw["outcome"], "PASS"), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), r["case_id"])]
        nf += len(checks)
        bad += [(r["case_id"], k, str(g)[:60], str(x)[:60]) for k, g, x in checks if g != x]
    rep.check("observations.every_field", not bad, {"fields_compared": nf, "bad": bad[:6]})
    rep.check("observations.totals", Counter(r["verdict"] for r in recs) == Counter({"PASS": n}) and derived["outcomes"][campaign] == {"PASS": n})

    saved = json.loads((run / "analysis.json").read_text())
    # ---- partition certificate (from this campaign's own words run) ----
    wrows = rows if campaign == "words" else rows_of(words_run, "words", WORDS)[0] if words_run else None
    if wrows is None:
        rep.check("partition.certificate", False, "no complete verified words rows available")
        return rep, {"campaign": campaign, "stage_counts": counts, "extra": {}, "records": {r["case_id"]: r for r in recs}}
    orbits = [{"representative": r, "members": orbit(r), "size": len(orbit(r)), "period": own[r]["period"],
               "stabilizer_size": own[r]["stabilizer_size"], "reflected_representative": orbit(r[::-1])[0],
               "total_cost": wrows[r]["total_cost"]} for r in reps]
    constant = all(len({wrows[m]["total_cost"] for m in o["members"]}) == 1 for o in orbits)
    burn = [sum(1 for w in WORDS if w[k:] + w[:k] == w) for k in range(6)]
    self_ref = sum(o["representative"] == o["reflected_representative"] for o in orbits)
    mirror = len({frozenset((o["representative"], o["reflected_representative"])) for o in orbits if o["representative"] != o["reflected_representative"]})
    size_hist = Counter(o["size"] for o in orbits)
    part_ok = (constant and orbits == derived["orbits"] == saved["partition"]["orbits"] and burn == [729, 3, 9, 27, 9, 3] == saved["partition"]["burnside_fixed_counts"]
               and sum(burn) // 6 == 130 and dict(size_hist) == {1: 3, 2: 3, 3: 8, 6: 116} and sum(o["size"] for o in orbits) == 729
               and sorted(m for o in orbits for m in o["members"]) == WORDS and self_ref == 54 and mirror == 38 and 130 - mirror == 92
               and all(own[w]["representative"] == min(own[w]["representative"], w) for w in WORDS))
    rep.check("partition.certificate", part_ok, {"burnside": burn, "orbit_size_histogram": dict(size_hist), "self_reflections": self_ref,
                                                 "mirror_pairs": mirror, "classes_if_reflection_were_quotiented": 130 - mirror,
                                                 "orbit_costs_constant": constant})
    seam = {"AAAAAB": [own["AAAAAB"]["total_cost"], open_score("AAAAAB")], "BAAAAA": [own["BAAAAA"]["total_cost"], open_score("BAAAAA")]}
    rep.check("demonstration.seam_and_reflection", seam == {"AAAAAB": [25, 22], "BAAAAA": [25, 25]}
              and wrows["AAAAAB"]["total_cost"] == wrows["BAAAAA"]["total_cost"] == 25
              and wrows["ABCABC"]["total_cost"] == 0 and wrows["ACBACB"]["total_cost"] == 18 and orbit("CBACBA")[0] == "ACBACB"
              and [own[w]["orbit_size"] for w in ("AAAAAA", "ABABAB", "ABCABC", "AAAAAB")] == [1, 2, 3, 6]
              and wrows["AAAAAB"]["edge_costs"] != wrows["BAAAAA"]["edge_costs"],
              {"seam_total_vs_open_path": seam, "ABCABC": 0, "ACBACB": 18,
               "edge_costs": {w: wrows[w]["edge_costs"] for w in ("AAAAAB", "BAAAAA")}})
    extra = {"seam": seam}
    if campaign == "classes":
        crow = rows
        mism = [r for r in reps if any(crow[r][k] != wrows[r][k] for k in FIELDS)]
        pops = populations({w: wrows[w]["total_cost"] for w in WORDS}, {r: crow[r]["total_cost"] for r in reps}, reps)
        ranking = sorted(reps, key=lambda r: (crow[r]["total_cost"], r))
        best = [r for r in ranking if crow[r]["total_cost"] == crow[ranking[0]]["total_cost"]]
        pj = {k: {"histogram": h, "mean": jsonable(m)} for k, (h, m) in pops.items()}
        ok = (not mism and all(saved["populations"][k]["histogram"] == pj[k]["histogram"] == derived["histograms"][k]
                               and saved["populations"][k]["mean"] == pj[k]["mean"] == derived["means"][k] for k in pj)
              and pops["words"][1] == 14 and pops["classes_weighted"][1] == 14 and pops["classes_uniform"][1] == Fraction(942, 65)
              and pj["classes_weighted"]["histogram"] == pj["words"]["histogram"]
              and ranking == derived["ranking"] == saved["ranking"] and best == ["ABCABC"] == saved["best_classes"]
              and sorted(orbit("ABCABC")) == derived["best_labelled_words"] == saved["best_labelled_words"]
              and saved["masses"] == {"best_class_of_classes": {"n": "1", "d": "130"}, "best_words_of_words": {"n": "1", "d": "243"}}
              and saved["cross_campaign"] == {"representatives_matched": 130, "mismatches": []})
        rep.check("classes.cross_campaign_and_populations", ok,
                  {"mismatches": mism, "means": {k: v["mean"] for k, v in pj.items()}, "best": best, "words_run": words_run.name})
        extra.update(means={k: v["mean"] for k, v in pj.items()}, ranking_top=ranking[:5])
    else:
        rep.check("words.analysis_saved", saved["partition"]["classes"] == 130 and saved["partition"]["disjoint_complete"]
                  and saved["populations"]["words"]["mean"] == {"n": "14", "d": "1"}
                  and saved["populations"]["words"]["histogram"] == {str(k): v for k, v in sorted({int(k): v for k, v in derived["histograms"]["words"].items()}.items())})

    budgets = {"words": ["800", "800", "100000000", "1800"], "classes": ["150", "150", "50000000", "400"]}[campaign]
    need = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
            "--budget-mandatory-rows", budgets[0], "--budget-final-candidates", budgets[1], "--budget-disk-bytes", budgets[2],
            "--budget-wall-time-seconds", budgets[3]]
    rep.check("envelope.command", all(t in argv for t in need) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx" and Path(argv[2]).parent.name == campaign, argv[2:])
    dbm = manifest["databases"]
    tag = {"words": "d12a", "classes": "d12b"}[campaign]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(rf"as0927_{tag}_[0-9a-z_]+", dbm["name"]) is not None
              and not any(v["exists_before"] for v in dbm["absence_checked"].values()) and set(dbm.get("retained_bytes", {})) == {"main", "results"},
              {"retained_bytes": dbm.get("retained_bytes"), "run_dir_bytes": manifest.get("run_dir_bytes")})
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    xl, tm = fg.load_spec(root / "spec" / campaign / "demo.xlsx"), fg.load_spec(root / "spec" / campaign / "spec.toml")
    rep.check("provenance.workbook_toml_and_core_input", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / campaign / "demo.xlsx")["sheets"]
              and [(s.sheet, list(s.values)) for s in xl.slots] == [(s.sheet, list(s.values)) for s in tm.slots])
    return rep, {"campaign": campaign, "stage_counts": counts, "extra": extra, "records": {r["case_id"]: r for r in recs}}


def witnesses(run, data):
    out = []
    for case in WITNESSES[data["campaign"]]:
        r = data["records"][case]
        out.append({"case_id": case, "campaign": data["campaign"], "candidate": r["framework"]["source_ref"], **{k: r[k] for k in FIELDS},
                    "verdict": r["verdict"], "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d12.witnesses/v1", "run": run.name, "witnesses": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--words-run", type=Path)
    ap.add_argument("--inputs-root", type=Path, default=HERE)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    run = a.run.resolve()
    out_dir = (a.out or run).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rep, data = verify(run, a.inputs_root.resolve(), a.words_run.resolve() if a.words_run else None)
    doc = {"schema": "d12.verification/v1", "run": run.name, "campaign": data["campaign"], "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: jsonable(data[k]) for k in ("stage_counts", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES[data["campaign"]]):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
