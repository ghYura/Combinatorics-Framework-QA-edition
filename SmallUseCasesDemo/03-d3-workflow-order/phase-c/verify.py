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

"""Independent offline verifier for the D3 phase-C benchmark evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py or the AI architect's derive.py, never connects
to a database, never executes a candidate. All 720 orders are enumerated here; the reference
machine and late_restart are re-derived from the contract text; every snapshot is compared; the
suite certificates are recomputed from positions/projection; detection per suite is measured
from the campaign observations, not taken from any certificate.
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
GEN = Path(__file__).resolve().parents[3] / "generator_trunk"
EVENTS = "CFNQSV"
POLICIES = ("correct", "late_restart")
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
SIZES = {"SCA2": 2, "SCA3": 10, "ADJ2": 9, "PROJ": 5, "SCA3_counterexample": 10}
FIELDS = ("epoch", "captures", "refunds", "balance", "refund_attempted")


def jsonable(v):
    if isinstance(v, dict):
        return {(k if isinstance(k, str) else "/".join(map(str, k))): jsonable(x) for k, x in v.items()}
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


def machine(order, policy):
    """(observed, reference) snapshot traces, re-derived from the contract text."""
    def snap(st, bal):
        return {"epoch": st["e"], "captures": list(st["c"]), "refunds": list(st["r"]), "balance": bal,
                "refund_attempted": st["a"]}
    ledgers = [{"e": 0, "c": [0], "r": [0], "a": False}, {"e": 0, "c": [0], "r": [0], "a": False}]
    bal = [0, 0]                                          # [reference, observed]
    obs, ref = [], []
    for op in order:
        for i, st in enumerate(ledgers):
            e = st["e"]
            if op == "C" and st["c"][e] == 0:
                st["c"][e] = 1; bal[i] += 100
            elif op == "F":
                st["a"] = True
                if st["c"][e] == 1 and st["r"][e] == 0:
                    st["r"][e] = 1; bal[i] -= 100
            elif op == "N":
                st["e"] += 1; st["c"].append(0); st["r"].append(0); st["a"] = False
            elif op == "S":
                lost = (i == 1 and policy == "late_restart" and st["e"] == 1 and st["c"] == [1, 0]
                        and st["r"] == [0, 0] and st["a"])
                bal[i] = 0 if lost else 100 * (sum(st["c"]) - sum(st["r"]))
            elif op == "Q":
                bal[i] = 100 * (sum(st["c"]) - sum(st["r"]))
        ref.append(snap(ledgers[0], bal[0])); obs.append(snap(ledgers[1], bal[1]))
    return obs, ref


def invariant_values(s):
    c, r, e = s["captures"], s["refunds"], s["epoch"]
    return {"count_domain": all(x in (0, 1) for x in c + r) and e >= 0,
            "refunds_le_captures": len(c) == len(r) and all(y <= x for x, y in zip(c, r)),
            "list_lengths": len(c) == e + 1 == len(r),
            "ledger_balance": s["balance"] == 100 * (sum(c) - sum(r)),
            "flag_boolean": isinstance(s["refund_attempted"], bool)}


def obligations(row, family):
    if family.startswith("SCA"):
        k = 3 if family.startswith("SCA3") else 2
        return {"".join(row[i] for i in idx) for idx in itertools.combinations(range(len(row)), k)}
    seq = "".join(ch for ch in row if ch in "CFQS") if family == "PROJ" else row
    return {seq[i:i + 2] for i in range(len(seq) - 1)}


def universe_obligations(family):
    if family.startswith("SCA"):
        k = 3 if family.startswith("SCA3") else 2
        return {"".join(p) for p in itertools.permutations(EVENTS, k)}
    return {"".join(p) for p in itertools.permutations("CFQS" if family == "PROJ" else EVENTS, 2)}


def read_candidates(tar_path):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tar_path.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    policy, ops, phase, sources = None, [], None, None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            arg = ast.literal_eval(node.value.args[0])
            if node.value.func.id == "start":
                if policy is not None:
                    raise ValueError("start twice")
                policy = arg
            elif node.value.func.id == "step":
                ops.append(arg)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D3_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase = ast.literal_eval(node.value.args[0])
    if policy is None or phase != "C":
        raise ValueError("start()/finish('C') missing")
    return f"C|{policy}|OPS={''.join(ops)}", sources


def verify(run: Path, root: Path = HERE):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    universe = sorted("".join(p) for p in itertools.permutations(EVENTS))
    expected = sorted(f"C|{p}|OPS={o}" for p in POLICIES for o in universe)
    rep.check("space.universe_and_ids", universe == derived["universe"] and expected == sorted(derived["case_ids"])
              and len(expected) == 1440)

    # stages
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["cardinality"]["full-xlsx"]["final"] == ["EXACT", 1440]
              and cmp_["cardinality"]["catalogue-SCA3-xlsx"]["final"] == ["EXACT", 20]
              and cmp_["dependency_graph_sha256"]["full-toml"] == cmp_["dependency_graph_sha256"]["full-xlsx"]
              and not cmp_["budget_blocking"]["full-xlsx"], cmp_["cardinality"])
    per_sheet = {m.group(1): int(m.group(2)) for m in re.finditer(
        r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", (run / "logs" / "core.log").read_text(errors="replace"))}
    db = json.loads((run / "db-export.json").read_text())
    counts = {"core_per_sheet": per_sheet, "fw_final": db["main_db"]["table_row_counts"].get("fw_final"),
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"),
              "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.core", per_sheet == {"HEAD": 1, "IMPL": 2, "OPS": 720, "TAIL": 1} and counts["fw_final"] == 1440, counts)
    rep.check("stage.reader_executor", counts["reader"] == counts["executor"] == counts["results_v2"] == 1440, counts)
    code2val = {int(r["bigint"]): r["value"] for r in db["main_db"]["NumberToValue1"]}
    rows = db["main_db"]["fw_final_after_sieve"]
    base = (next(iter(db["main_db"]["fw_final_base_tables"].values()), [{}]) or [{}])[0]
    col = {c.split("_", 1)[1]: c for c in (rows or [{}])[0] if c.startswith("combos") and "_" in c}
    lit = lambda code: ast.literal_eval(ast.parse(code2val[int(code)].strip()).body[0].value.args[0])   # noqa: E731
    core_ids = sorted(f"C|{lit((r.get(col['IMPL']) or base.get(col['IMPL']))[0])}|OPS="
                      + "".join(lit(c) for c in (r.get(col["OPS"]) or base.get(col["OPS"]))) for r in rows)
    rep.check("identity.core", core_ids == expected)
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            ident, sources = parse_candidate(data.decode())
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = ident
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 1440 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD)
              and "container" in (summary.get("sandbox_backend") or ""), dict(outcomes))

    # every record against the independent model
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected)
    bad, fields, faults, hidden = [], 0, [], []
    for cid_, r in records.items():
        order = cid_.split("OPS=")[1]
        obs, ref = machine(order, r["policy"])
        fails = [k for k, (o, rf) in enumerate(zip(obs, ref), 1) if o != rf or not all(invariant_values(o).values())]
        final_fail = obs[-1] != ref[-1] or not all(invariant_values(obs[-1]).values())
        cps, fw = r["checkpoints"], r["framework"]
        row = rv2.get(fw["candidate_id"], {})
        checks = [("ops", "".join(r["ops"]), order), ("indices", [c["index"] for c in cps], list(range(1, 7))),
                  ("observed", [c["observed"] for c in cps], obs), ("reference", [c["reference"] for c in cps], ref),
                  ("mismatched", [c["mismatched_fields"] for c in cps], [[f for f in FIELDS if o[f] != rf[f]] for o, rf in zip(obs, ref)]),
                  ("invariants", [c["invariants"] for c in cps], [invariant_values(o) for o in obs]),
                  ("failing", r["failing_checkpoints"], fails), ("verdict", r["verdict"], "DOMAIN_FAIL" if fails else "PASS"),
                  ("final_only", r["final_only_verdict"], "DOMAIN_FAIL" if final_fail else "PASS"),
                  ("hidden", r["hidden_by_final_only"], bool(fails) and not final_fail),
                  ("fw_var", r["fw_var"], 2 if fails else 0), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("results_v2", (row.get("outcome"), row.get("verdict_code")), (r["verdict"], r["fw_var"])),
                  ("rendered", rendered.get(fw["source_ref"]), cid_), ("candidate_sha", fw["source_sha256"], sha256(cands.get(fw["source_ref"], b""))),
                  ("source_sha", r["source_sha256"], module_sha), ("run_id", fw["run_id"], run_id)]
        fields += len(checks)
        wrong = [n for n, got, want in checks if got != want]
        if wrong:
            bad.append({"case": cid_, "fields": wrong})
        if r["verdict"] == "DOMAIN_FAIL":
            faults.append((r["policy"], order))
        if r["hidden_by_final_only"]:
            hidden.append(order)
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    trigger = sorted(o for o in universe if o.index("C") < o.index("N") < o.index("F") < o.index("S"))
    rep.check("observations.faults", all(p == "late_restart" for p, _ in faults)
              and sorted(o for _, o in faults) == sorted(derived["predicted_fault_orders"]) == trigger
              and sorted(hidden) == sorted(derived["predicted_hidden_orders"])
              and dict(totals) == {"PASS": 1410, "DOMAIN_FAIL": 30} and len(hidden) == 6,
              {"totals": dict(totals), "faults": len(faults), "hidden": sorted(hidden)})

    # coverage certificates, recomputed; detection measured from the observations
    suites, measured = derived["suites"], {}
    fault_set = {o for _, o in faults}
    for name, s in suites.items():
        fam = s["family"]
        need = universe_obligations(fam)
        cover = set().union(*(obligations(rw, fam) for rw in s["rows"]))
        cert_ok = all(w in s["rows"] and o in obligations(w, fam) for o, w in s["certificate"].items())
        detected = sorted(rw for rw in s["rows"] if records[f"C|late_restart|OPS={rw}"]["verdict"] == "DOMAIN_FAIL")
        correct_fail = [rw for rw in s["rows"] if records[f"C|correct|OPS={rw}"]["verdict"] != "PASS"]
        measured[name] = {"size": len(s["rows"]), "obligations": len(need), "covered": len(cover & need),
                          "certificate_entries_valid": cert_ok, "measured_late_restart_detections": detected,
                          "correct_failures": correct_fail}
        rep.check(f"certificate.{name}", set(s["rows"]) <= set(universe) and len(s["rows"]) == SIZES[name]
                  and sorted(s["required_obligations"]) == sorted(need) and cover >= need and cert_ok
                  and set(s["certificate"]) == need, measured[name])
        rep.check(f"detection.{name}", detected == sorted(s["predicted_fault_orders"]) and not correct_fail
                  and set(detected) == set(s["rows"]) & fault_set, detected)
    cx = measured["SCA3_counterexample"]
    rep.check("counterexample.covers_all_triples_detects_nothing", cx["covered"] == 120 and cx["measured_late_restart_detections"] == []
              and not set(suites["SCA3_counterexample"]["rows"]) & set(trigger))
    import tomllib
    catalogue = tomllib.loads((root / "spec" / "catalogue-SCA3" / "spec.toml").read_text())
    schedule = next(sl for sl in catalogue["slots"] if sl["sheet"] == "SCHEDULE")
    spec_rows = ["".join(re.findall(r'step\("([A-Z])"\)', v)) for v in schedule["values"]]
    rep.check("catalogue.rows_equal_ordinary_SCA3", spec_rows == suites["SCA3"]["rows"], spec_rows)

    # envelope / provenance
    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "1600", "--budget-final-candidates", "1600", "--budget-disk-bytes", "200000000",
                 "--budget-wall-time-seconds", "1800", "--per-candidate-seconds-min", "0.3", "--per-candidate-seconds-max", "1.2"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).parent.name == "full", argv[2:])
    run_json = json.loads((run / "run" / "run.json").read_text())
    budget = run_json.get("settings", {}).get("budget") or {}
    rep.check("envelope.budget_intent", budget.get("per_candidate_seconds") == [0.3, 1.2] and budget.get("override") is False
              and budget.get("exceeded") == [], budget)
    rep.check("envelope.db", re.fullmatch(r"as0927_d3c_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / "full" / "demo.xlsx")["sheets"])
    return rep, {"stage_counts": counts, "totals": dict(totals), "hidden": sorted(hidden), "suites": measured,
                 "records": records}


WITNESSES = {"late_restart_heals": "C|late_restart|OPS=CNFSQV", "late_restart_persists": "C|late_restart|OPS=QCNFSV",
             "late_restart_nontrigger": "C|late_restart|OPS=CFNSQV", "positive_control": "C|correct|OPS=CNFSQV"}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"],
                    "checkpoints": [{"k": c["index"], "op": c["op"], "observed": c["observed"], "ok": c["ok"]} for c in r["checkpoints"]],
                    "failing_checkpoints": r["failing_checkpoints"], "verdict": r["verdict"],
                    "final_only_verdict": r["final_only_verdict"],
                    "replay": f"python replay.py --run {run.relative_to(HERE)} --case '{case}'"})
    return {"schema": "d3c.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d3c.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "hidden", "suites")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if len(data["records"]) == 1440:
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
