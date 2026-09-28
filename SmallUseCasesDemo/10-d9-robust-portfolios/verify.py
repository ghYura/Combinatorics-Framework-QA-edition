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

"""Independent offline verifier for the D9 evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py, ranking.py or derive.py, never connects
to a database, never executes a candidate (candidates and dictionary values are parsed with `ast`).
Payoffs are recomputed here with their own arithmetic; the portfolio rankings are recomputed from the
OBSERVED total costs and compared with ranking.json and the frozen predictions.
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
NAMES = ["cache", "quota", "network_backup", "disk_replica", "staff_reserve", "cross_region"]
COSTS = dict(zip(NAMES, [3, 2, 5, 6, 4, 8]))
WORLDS = list(itertools.product(range(4), range(4)))
PROFILES = {"uniform": ([1, 1, 1, 1], [1, 1, 1, 1]), "calm": ([6, 2, 1, 1], [7, 1, 1, 1]), "stress": ([1, 1, 6, 2], [1, 2, 6, 1])}
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
WITNESSES = ["P=000000|D=0|X=0", "P=000000|D=2|X=2", "P=110000|D=2|X=2", "P=110100|D=2|X=2", "P=111111|D=3|X=1"]
FIELDS = ("design", "selected", "demand", "disruption", "fixed_cost", "gross_loss", "reductions", "raw_loss", "residual_loss", "total_cost")


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


def payoff(bits, d, x):
    sel = [n for n, b in zip(NAMES, bits) if b == "1"]
    per = {"cache": [0, 3, 8, 6][d], "quota": [0, 2, 6, 7][d], "network_backup": 11 * (x == 1), "disk_replica": 14 * (x == 2),
           "staff_reserve": 6 * (x == 3), "cross_region": 8 * (x in (1, 2))}
    red = [per[n] if n in sel else 0 for n in NAMES]
    gross = [4, 11, 22, 15][d] + [0, 14, 19, 9][x]
    raw = gross - sum(red)
    fixed = sum(COSTS[n] for n in sel)
    return {"design": bits, "selected": sel, "demand": d, "disruption": x, "fixed_cost": fixed, "gross_loss": gross,
            "reductions": red, "raw_loss": raw, "residual_loss": max(raw, 0), "total_cost": fixed + max(raw, 0)}


def weights(profile):
    dw, xw = PROFILES[profile]
    total = sum(dw) * sum(xw)
    return [Fraction(dw[d] * xw[x], total) for d, x in WORLDS]


def rankings_from(costs):
    """costs: {design: [16 totals in world order]} -> the contract's rankings, exact."""
    ev = lambda b, w: sum((c * q for c, q in zip(costs[b], w)), Fraction(0))       # noqa: E731
    w = {p: weights(p) for p in PROFILES}
    worst = {b: max(v) for b, v in costs.items()}
    minimax = sorted(costs, key=lambda b: (worst[b], ev(b, w["uniform"]), b))
    exp = {p: sorted(costs, key=lambda b: (ev(b, wp), worst[b], b)) for p, wp in w.items()}
    sens = []
    for k in range(11):
        a = Fraction(k, 10)
        wm = [(1 - a) * c + a * s for c, s in zip(w["calm"], w["stress"])]
        order = sorted(costs, key=lambda b: (ev(b, wm), worst[b], b))
        sens.append({"alpha": jsonable(a), "ranking": order, "winner": order[0], "winner_expected": jsonable(ev(order[0], wm))})
    summaries = [{"design": b, "world_count": len(costs[b]), "worst_cost": worst[b],
                  "worst_worlds": [[d, x] for (d, x), c in zip(WORLDS, costs[b]) if c == worst[b]],
                  "expected": {p: jsonable(ev(b, wp)) for p, wp in w.items()}} for b in sorted(costs)]
    return {"minimax_ranking": minimax, "minimax_primary_ties": [b for b in minimax if worst[b] == worst[minimax[0]]],
            "expected_rankings": exp, "sensitivity": sens, "summaries": summaries,
            "world_weights": {p: [jsonable(x) for x in wp] for p, wp in w.items()}, "ev": ev, "w": w, "worst": worst}


def guarded_costs(records):
    """The ranking input guard, written here independently: exactly one PASS row per design/world."""
    cnt = Counter((r["design"], r["demand"], r["disruption"]) for r in records)
    ok = (all(v == 1 for v in cnt.values()) and set(cnt) == {(format(i, "06b"), d, x) for i in range(64) for d, x in WORLDS}
          and all(r["verdict"] == "PASS" and r["case_id"] == f"P={r['design']}|D={r['demand']}|X={r['disruption']}" for r in records))
    if not ok:
        return None
    by = {(r["design"], r["demand"], r["disruption"]): r["total_cost"] for r in records}
    return {format(i, "06b"): [by[(format(i, "06b"), d, x)] for d, x in WORLDS] for i in range(64)}


def cost_ok(r):
    """Every numeric field of an observation equals this verifier's recomputation."""
    want = payoff(r["design"], r["demand"], r["disruption"])
    return all(r[f] == want[f] for f in FIELDS)


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources = [], None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D9_SOURCES":
            sources = ast.literal_eval(node.value)
    return calls, sources


def case_of(calls):
    names = [c[0] for c in calls]
    k = names.count("enable")
    if names != ["enable"] * k + ["demand", "disruption"]:
        raise ValueError(f"atom order {names}")
    mods = [c[1] for c in calls[:k]]
    if len(set(mods)) != k or any(m not in NAMES for m in mods) or mods != sorted(mods, key=NAMES.index):
        raise ValueError(f"modules {mods}")
    bits = "".join("1" if n in mods else "0" for n in NAMES)
    return f"P={bits}|D={calls[k][1]}|X={calls[k + 1][1]}", k


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    own = {f"P={format(i, '06b')}|D={d}|X={x}": payoff(format(i, "06b"), d, x) for i in range(64) for d, x in WORLDS}
    expected_ids = sorted(own)
    rep.check("space.identities", len(expected_ids) == 1024 and expected_ids == sorted(frozen)
              and {"P=000000|D=0|X=0", "P=111111|D=3|X=3"} <= set(own) and derived["modules"] == NAMES
              and derived["worlds"] == [list(w) for w in WORLDS], {"designs": 64, "worlds": 16})
    rep.check("space.frozen_equals_own_model", all(all(o[f] == frozen[c][f] for f in FIELDS) and frozen[c]["predicted_outcome"] == "PASS"
                                                   for c, o in own.items()))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 1024] and c["mandatory"][:2] == ["EXACT", 1024] for c in cmp_["cardinality"].values())
              and all(ps["DESIGN"].get("mode") == "EXACT" and ps["DESIGN"].get("value") == 64 for ps in cmp_["per_slot"].values()),
              cmp_["cardinality"])
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    after = {int(m.group(1)): [int(m.group(2)), int(m.group(3))] for m in re.finditer(
        r"\[DIAG-PASS\] Sheet DESIGN \(key=\d+\) directive\[(\d+)\] AFTER: isCombi2=\S+ fw_rows=(\d+) fw2_rows=(\d+)", core_log)}
    final = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", core_log)}
    work = {"derived": {"first_pass": 64, "second_pass_emissions": 3 ** 6 - 1, "distinct": 64},
            "observed": {"first_pass_fw_rows": after.get(0, [None])[0], "second_pass_fw2_rows_before_distinct": after.get(1, [None, None])[1],
                         "final_after_distinct": final.get("DESIGN")},
            "other_sheets": {k: final.get(k) for k in ("DEMAND", "DISRUPTION", "TAIL")}}
    rep.check("core.design_subsets_chain", work["observed"] == {"first_pass_fw_rows": 64, "second_pass_fw2_rows_before_distinct": 728,
                                                               "final_after_distinct": 64}
              and work["other_sheets"] == {"DEMAND": 4, "DISRUPTION": 4, "TAIL": 1}, work)

    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    def cell(r, sheet):                         # an explicit None test: an empty design is [] and must not inherit the base
        v = r.get(cols[sheet])
        return list(base.get(cols[sheet]) or []) if v is None else list(v)
    decoded, bad_rows, empty_rows = [], [], 0
    for r in frows:
        try:
            calls = []
            for sheet in ("DESIGN", "DEMAND", "DISRUPTION"):
                for code in cell(r, sheet):
                    calls.extend(calls_of(code2val[int(code)])[0])
            cid, k = case_of(calls)
            decoded.append(cid)
            empty_rows += k == 0
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == 1024 for v in counts.values()), counts)
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids and empty_rows == 16
              and sorted(cols) == sorted(["HEAD", "DESIGN", "DEMAND", "DISRUPTION", "TAIL"]) and cols.get("DESIGN", "").startswith("combos2_")
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()),
              {"bad_rows": bad_rows[:3], "empty_design_rows": empty_rows, "base_design": base.get(cols.get("DESIGN", ""))})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, empty_cands = {}, True, [], 0
    for name, data in cands.items():
        try:
            calls, sources = calls_of(data.decode())
            rendered[name], k = case_of(calls)
            empty_cands += k == 0
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        src_ok &= sources is not None and {k_: sha256(v.encode()) for k_, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids and empty_cands == 16,
              {"errors": errs[:3], "empty_design_candidates_without_enable": empty_cands})
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 1024 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    by_id = {r["case_id"]: r for r in records}
    rep.check("identity.executor", sorted(by_id) == expected_ids and len(records) == 1024)
    bad, nfields = [], 0
    for cid, r in by_id.items():
        if cid not in own:
            bad.append((cid, "unknown"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [("schema", r["schema"], "d9.observation/v1"), *[(f, r[f], o[f]) for f in FIELDS],
                  *[(f"frozen_{f}", r[f], frozen[cid][f]) for f in FIELDS],
                  ("reference", r["reference"], {k: o[k] for k in ("fixed_cost", "gross_loss", "reductions", "raw_loss", "residual_loss", "total_cost")}),
                  ("mismatched_fields", r["mismatched_fields"], []), ("verdict", r["verdict"], "PASS"), ("fw_var", r["fw_var"], 0),
                  ("metrics_fw_var", fw["metrics_fw_var"], 0), ("outcome", fw["outcome"], "PASS"), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        nfields += len(checks)
        bad += [(cid, n, str(got)[:80], str(want)[:80]) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": nfields, "bad": bad[:6]})
    rep.check("observations.totals", Counter(r["verdict"] for r in records) == Counter({"PASS": 1024}) == Counter(derived["outcomes"]))

    # ---- rankings from observed costs ----
    costs = guarded_costs(records)
    rk = rankings_from(costs) if costs else None
    saved = json.loads((run / "ranking.json").read_text())
    same_saved = rk is not None and all(saved[k] == rk[k] for k in ("minimax_ranking", "minimax_primary_ties", "expected_rankings", "sensitivity", "summaries")) \
        and all(saved["profiles"][p]["world_weights"] == rk["world_weights"][p] for p in PROFILES)
    same_frozen = rk is not None and all(derived[k] == rk[k] for k in ("minimax_ranking", "minimax_primary_ties", "expected_rankings", "sensitivity", "summaries")) \
        and all(derived["profiles"][p]["world_weights"] == rk["world_weights"][p] for p in PROFILES)
    rep.check("ranking.from_observed_costs", same_saved and same_frozen and len(rk["summaries"]) == 64
              and all(s["world_count"] == 16 for s in rk["summaries"]),
              {"minimax": rk and rk["minimax_ranking"][:3], "expected_winners": rk and {p: r[0] for p, r in rk["expected_rankings"].items()},
               "sensitivity_winners": rk and [s["winner"] for s in rk["sensitivity"]]})
    if rk is None:
        rep.check("demonstration.decision_facts", False, "the ranking input guard refused the observed rows")
        return rep, {"stage_counts": {**counts, "design_work": work}, "totals": dict(Counter(r["verdict"] for r in records)),
                     "extra": {}, "records": by_id}
    ev, w, worst = rk["ev"], rk["w"], rk["worst"]
    cheapest = min(records, key=lambda r: (r["total_cost"], r["design"], r["demand"], r["disruption"]))
    clamp = [r["case_id"] for r in records if r["raw_loss"] < 0]
    facts = {"cheapest_row": [cheapest["case_id"], cheapest["total_cost"]], "000000_worst": worst["000000"],
             "minimax_winner": [rk["minimax_ranking"][0], worst[rk["minimax_ranking"][0]], ev(rk["minimax_ranking"][0], w["uniform"])],
             "110001": [worst["110001"], ev("110001", w["uniform"])],
             "calm_winner": [rk["expected_rankings"]["calm"][0], ev(rk["expected_rankings"]["calm"][0], w["calm"])],
             "stress_winner": [rk["expected_rankings"]["stress"][0], ev(rk["expected_rankings"]["stress"][0], w["stress"]),
                               worst[rk["expected_rankings"]["stress"][0]]],
             "uniform_winner": [rk["expected_rankings"]["uniform"][0], ev(rk["expected_rankings"]["uniform"][0], w["uniform"])],
             "negative_raw_loss_rows": len(clamp)}
    rep.check("demonstration.decision_facts", facts["cheapest_row"] == ["P=000000|D=0|X=0", 4] == [derived["naive_best_row"], 4]
              and facts["000000_worst"] == 41 and facts["minimax_winner"] == ["110000", 32, Fraction(41, 2)]
              and facts["110001"] == [32, Fraction(49, 2)] and facts["calm_winner"] == ["000000", Fraction(25, 2)]
              and facts["stress_winner"] == ["110100", Fraction(239, 10), 33] and facts["uniform_winner"] == ["110000", Fraction(41, 2)]
              and [s["winner"] for s in rk["sensitivity"]] == ["000000", "010000", "010000"] + ["110000"] * 4 + ["110100"] * 4
              and by_id["P=111111|D=3|X=1"]["raw_loss"] == -3 and by_id["P=111111|D=3|X=1"]["total_cost"] == 28 and clamp,
              facts)

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "1100", "--budget-final-candidates", "1100", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "2400"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    dbm = manifest["databases"]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(r"as0927_d9_[0-9a-z_]+", dbm["name"]) is not None
              and not any(v["exists_before"] for v in dbm["absence_checked"].values()) and set(dbm.get("retained_bytes", {})) == {"main", "results"},
              {"retained_bytes": dbm.get("retained_bytes"), "run_dir_bytes": manifest.get("run_dir_bytes")})
    jvm = core_log + (run / "logs" / "reader.log").read_text(errors="replace")
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
    return rep, {"stage_counts": {**counts, "design_work": work}, "totals": dict(Counter(r["verdict"] for r in records)),
                 "extra": {"decision_facts": facts, "clamp_rows": clamp}, "records": by_id}


def witnesses(run, data):
    out = []
    for case in WITNESSES:
        r = data["records"][case]
        out.append({"case_id": case, "candidate": r["framework"]["source_ref"], **{f: r[f] for f in FIELDS}, "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d9.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d9.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: jsonable(data[k]) for k in ("stage_counts", "totals", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
