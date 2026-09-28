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

"""Independent offline verifier for the D11 evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py, allocation.py or derive.py, never
connects to a database, never executes a candidate (candidates and dictionary values are parsed with
`ast`). Coalition values are recomputed here; every allocation certificate is recomputed from the
OBSERVED values and compared with allocation.json and the preregistration.
"""
import argparse
import ast
import gzip
import hashlib
import io
import itertools
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
P = "ABCDEF"
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
WITNESSES = ["C=000000", "C=100000", "C=110000", "C=001100", "C=101100"]
FIELDS = ("mask", "members", "standalone_value", "interaction_bonuses", "value")


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


def value_of(mask):
    has = {p: mask[i] == "1" for i, p in enumerate(P)}
    std = 2 * has["A"] + 2 * has["B"] + has["C"] + has["D"] + 4 * has["E"]
    bon = {"AB": 12 * (has["A"] and has["B"]), "ACD": 5 * (has["A"] and has["C"] and has["D"]),
           "BCD": 5 * (has["B"] and has["C"] and has["D"])}
    return {"mask": mask, "members": [p for p in P if has[p]], "standalone_value": std,
            "interaction_bonuses": {k: int(v) for k, v in bon.items()}, "value": std + sum(bon.values())}


def guarded_values(records):
    cnt = Counter(r["mask"] for r in records)
    if set(cnt) != {format(i, "06b") for i in range(64)} or any(n != 1 for n in cnt.values()):
        return None
    if any(r["verdict"] != "PASS" or r["case_id"] != f"C={r['mask']}" for r in records):
        return None
    return {r["mask"]: r["value"] for r in records}


def certificates(values):
    masks = [format(i, "06b") for i in range(64)]
    add = lambda m, p: m[:P.index(p)] + "1" + m[P.index(p) + 1:]          # noqa: E731
    size = lambda m: m.count("1")                                         # noqa: E731
    rows, phi = [], {p: Fraction(0) for p in P}
    for p in P:
        for m in masks:
            if m[P.index(p)] == "0":
                w = Fraction(math.factorial(size(m)) * math.factorial(5 - size(m)), 720)
                d = values[add(m, p)] - values[m]
                rows.append({"player": p, "coalition": m, "weight": jsonable(w), "marginal": d})
                phi[p] += w * d
    orders, sums = [], dict.fromkeys(P, 0)
    for perm in itertools.permutations(P):
        m, inc = "000000", []
        for p in perm:
            d = values[add(m, p)] - values[m]
            inc.append(d)
            sums[p] += d
            m = add(m, p)
        orders.append({"order": "".join(perm), "marginals": inc})
    div = {}
    for m in sorted(masks, key=lambda m: (size(m), m)):
        sub = [t for t in div if t != m and all(a <= b for a, b in zip(t, m))]
        div[m] = values[m] - sum(div[t] for t in sub)
    split = {p: sum((Fraction(d, size(m)) for m, d in div.items() if m[P.index(p)] == "1"), Fraction(0)) for p in P}
    return {"phi": phi, "rows": rows, "orders": orders, "sums": sums, "div": div, "split": split}


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources = [], None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D11_SOURCES":
            sources = ast.literal_eval(node.value)
    return calls, sources


def case_of(calls):
    if any(c[0] != "enable" for c in calls):
        raise ValueError(f"atoms {[c[0] for c in calls]}")
    mem = [c[1] for c in calls]
    if mem != sorted(set(mem), key=P.index) or any(m not in P for m in mem):
        raise ValueError(f"members {mem}")
    return "C=" + "".join("1" if p in mem else "0" for p in P), len(mem)


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    own = {f"C={format(i, '06b')}": value_of(format(i, "06b")) for i in range(64)}
    expected_ids = sorted(own)
    rep.check("space.identities", len(expected_ids) == 64 and expected_ids == sorted(frozen) and derived["players"] == list(P)
              and len({o["value"] for o in own.values()}) < 64, {"coalitions": 64, "distinct_values": len({o["value"] for o in own.values()})})
    rep.check("space.frozen_equals_own_model", all(all(o[k] == frozen[c][k] for k in FIELDS) and frozen[c]["predicted_outcome"] == "PASS"
                                                   for c, o in own.items()))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 64] and c["mandatory"][:2] == ["EXACT", 64] for c in cmp_["cardinality"].values())
              and all(ps["COALITION"].get("mode") == "EXACT" and ps["COALITION"].get("value") == 64 for ps in cmp_["per_slot"].values()),
              cmp_["cardinality"])
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    after = {int(m.group(1)): [int(m.group(2)), int(m.group(3))] for m in re.finditer(
        r"\[DIAG-PASS\] Sheet COALITION \(key=\d+\) directive\[(\d+)\] AFTER: isCombi2=\S+ fw_rows=(\d+) fw2_rows=(\d+)", core_log)}
    final = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", core_log)}
    work = {"derived": {"first_pass": 64, "second_pass_emissions": 3 ** 6 - 1, "distinct": 64},
            "observed": {"first_pass_fw_rows": after.get(0, [None])[0], "second_pass_fw2_rows_before_distinct": after.get(1, [None, None])[1],
                         "final_after_distinct": final.get("COALITION")}}
    rep.check("core.coalition_subsets_chain", work["observed"] == {"first_pass_fw_rows": 64, "second_pass_fw2_rows_before_distinct": 728,
                                                                  "final_after_distinct": 64} and final.get("TAIL") == 1, work)

    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    decoded, bad_rows, empty_rows = [], [], 0
    for r in frows:
        try:
            v = r.get(cols["COALITION"])
            codes = list(base.get(cols["COALITION"]) or []) if v is None else list(v)     # explicit None: [] is the empty coalition
            calls = [c for code in codes for c in calls_of(code2val[int(code)])[0]]
            cid, k = case_of(calls)
            decoded.append(cid)
            empty_rows += k == 0
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == 64 for v in counts.values()), counts)
    f_pairs = sum(1 for c in decoded if c[-1] == "0" and c[:-1] + "1" in decoded)
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids and empty_rows == 1 and f_pairs == 32
              and sorted(cols) == ["COALITION", "HEAD", "TAIL"] and cols["COALITION"].startswith("combos2_")
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()),
              {"bad_rows": bad_rows[:3], "empty_coalition_rows": empty_rows, "pairs_differing_only_by_F": f_pairs,
               "base_coalition": base.get(cols.get("COALITION", ""))})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, empty_c = {}, True, [], 0
    for name, data in cands.items():
        try:
            calls, sources = calls_of(data.decode())
            rendered[name], k = case_of(calls)
            empty_c += k == 0
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        src_ok &= sources is not None and {k_: sha256(v.encode()) for k_, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids and empty_c == 1,
              {"errors": errs[:3], "empty_coalition_candidates_without_enable": empty_c})
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 64 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    by_id = {r["case_id"]: r for r in records}
    rep.check("identity.executor", sorted(by_id) == expected_ids and len(records) == 64)
    bad, nfields = [], 0
    for cid, r in by_id.items():
        if cid not in own:
            bad.append((cid, "unknown"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [("schema", r["schema"], "d11.observation/v1"), *[(k, r[k], o[k]) for k in FIELDS], *[(f"frozen_{k}", r[k], frozen[cid][k]) for k in FIELDS],
                  ("reference", r["reference"], {k: o[k] for k in ("standalone_value", "interaction_bonuses", "value")}),
                  ("oracle_agrees", r["oracle_agrees"], True), ("verdict", r["verdict"], "PASS"), ("fw_var", r["fw_var"], 0),
                  ("metrics_fw_var", fw["metrics_fw_var"], 0), ("outcome", fw["outcome"], "PASS"), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        nfields += len(checks)
        bad += [(cid, n, str(got)[:60], str(want)[:60]) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": nfields, "bad": bad[:6]})
    rep.check("observations.totals", Counter(r["verdict"] for r in records) == Counter({"PASS": 64}) == Counter(derived["outcomes"]))

    values = guarded_values(records)
    if values is None:
        rep.check("allocation.from_observed_values", False, "the input guard refused the observed rows")
        return rep, {"stage_counts": counts, "totals": dict(Counter(r["verdict"] for r in records)), "extra": {}, "records": by_id}
    cert = certificates(values)
    saved = json.loads((run / "allocation.json").read_text())
    phi_j = {p: jsonable(x) for p, x in cert["phi"].items()}
    same = (saved["shapley"] == phi_j == derived["shapley"] and saved["marginals"] == cert["rows"] == derived["marginals"]
            and saved["permutations"] == cert["orders"] == derived["permutations"] and saved["permutation_sums"] == cert["sums"] == derived["permutation_sums"]
            and saved["dividends"] == cert["div"] == derived["dividends"] and saved["dividend_split"] == {p: jsonable(x) for p, x in cert["split"].items()})
    phi = cert["phi"]
    props = {"weights_per_player_sum_to_one": all(sum(Fraction(int(r["weight"]["n"]), int(r["weight"]["d"])) for r in cert["rows"] if r["player"] == p) == 1 for p in P),
             "orders_telescope_to_32": all(sum(o["marginals"]) == 32 for o in cert["orders"]) and len(cert["orders"]) == 720,
             "marginal_observations": sum(len(o["marginals"]) for o in cert["orders"]),
             "three_routes_agree": phi == cert["split"] == {p: Fraction(cert["sums"][p], 720) for p in P},
             "efficiency": sum(phi.values()) == 32 == values["111111"],
             "nonzero_dividends": {m: d for m, d in cert["div"].items() if d},
             "E_constant_4_over_32": all(r["marginal"] == 4 for r in cert["rows"] if r["player"] == "E"),
             "F_zero_over_32": all(r["marginal"] == 0 for r in cert["rows"] if r["player"] == "F"),
             "symmetry_AB": [r["marginal"] for r in cert["rows"] if r["player"] == "A" and r["coalition"][1] == "0"]
                            == [r["marginal"] for r in cert["rows"] if r["player"] == "B" and r["coalition"][0] == "0"],
             "symmetry_CD": [r["marginal"] for r in cert["rows"] if r["player"] == "C" and r["coalition"][3] == "0"]
                            == [r["marginal"] for r in cert["rows"] if r["player"] == "D" and r["coalition"][2] == "0"]}
    want_div = {"100000": 2, "010000": 2, "001000": 1, "000100": 1, "000010": 4, "110000": 12, "101100": 5, "011100": 5}
    rep.check("allocation.from_observed_values", same and [phi[p] for p in P] == [Fraction(29, 3), Fraction(29, 3), Fraction(13, 3), Fraction(13, 3), 4, 0]
              and props["weights_per_player_sum_to_one"] and props["orders_telescope_to_32"] and props["marginal_observations"] == 4320
              and props["three_routes_agree"] and props["efficiency"] and props["nonzero_dividends"] == want_div
              and props["E_constant_4_over_32"] and props["F_zero_over_32"] and props["symmetry_AB"] and props["symmetry_CD"]
              and len(cert["rows"]) == 192, {"shapley": phi, **props})
    standalone = {p: values[format(1 << (5 - i), "06b")] for i, p in enumerate(P)}
    loo = {p: 32 - values["".join("0" if q == p else "1" for q in P)] for p in P}
    uniform = {p: Fraction(sum(r["marginal"] for r in cert["rows"] if r["player"] == p), 32) for p in P}
    ctx = {"A_alone": values["100000"] - values["000000"], "A_added_to_B": values["110000"] - values["010000"],
           "A_added_to_CD": values["101100"] - values["001100"]}
    shares = {"AB": {"A": Fraction(6), "B": Fraction(6)}, "ACD": {p: Fraction(5, 3) for p in "ACD"}, "BCD": {p: Fraction(5, 3) for p in "BCD"}}
    rep.check("demonstration.comparisons_and_context", standalone == derived["standalone"] == saved["standalone"]
              and list(standalone.values()) == [2, 2, 1, 1, 4, 0] and loo == derived["leave_one_out"] == saved["leave_one_out"]
              and list(loo.values()) == [19, 19, 11, 11, 4, 0] and sum(loo.values()) == 64
              and {p: jsonable(x) for p, x in uniform.items()} == derived["uniform_subset_marginals"] == saved["uniform_subset_marginals"]
              and sum(uniform.values()) == Fraction(59, 2) and ctx == {"A_alone": 2, "A_added_to_B": 14, "A_added_to_CD": 7}
              and max(standalone, key=standalone.get) == "E" and phi["A"] == max(phi.values())
              and all(phi[p] == standalone[p] + sum(s.get(p, 0) for s in shares.values()) for p in P),
              {"standalone": standalone, "leave_one_out": loo, "unweighted_mean_marginals": uniform, "context": ctx, "interaction_shares": shares})

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "100", "--budget-final-candidates", "100", "--budget-disk-bytes", "50000000",
                 "--budget-wall-time-seconds", "300"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    dbm = manifest["databases"]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(r"as0927_d11_[0-9a-z_]+", dbm["name"]) is not None
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
    return rep, {"stage_counts": {**counts, "coalition_work": work}, "totals": dict(Counter(r["verdict"] for r in records)),
                 "extra": {"shapley": phi, "context": ctx, "interaction_shares": shares}, "records": by_id}


def witnesses(run, data):
    out = []
    for case in WITNESSES:
        r = data["records"][case]
        out.append({"case_id": case, "candidate": r["framework"]["source_ref"], **{k: r[k] for k in FIELDS}, "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d11.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d11.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
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
