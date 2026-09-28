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

"""Independent offline verifier for one D3 campaign (phase A or B) evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only; never imports sut.py, oracle.py or runtime.py, never connects to a database,
never executes a candidate (candidates are parsed with `ast`). Case sets are enumerated here;
the reference machine and the two fault variants are re-derived here from CONTRACT.md's text;
every checkpoint is compared with both this derivation and the frozen architect-derived.json.
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
POLICIES = ("correct", "refund_unchecked", "restart_cache")
MASKS = ((0, 0), (0, 1), (1, 0), (1, 1))                 # (S, Q)
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
PHASE = {"A": {"core": 18, "opt": {"fw_opt1": 2, "fw_opt2": 1}, "cases": 72, "ops_sheet": 6,
               "budget": ["500", "200", "100000000", "600"]},
         "B": {"core": 81, "opt": {}, "cases": 81, "ops_sheet": 27, "budget": ["500", "200", "100000000", "600"]}}


def jsonable(v):
    if isinstance(v, dict):
        return {(k if isinstance(k, str) else "/".join(map(str, k)) if isinstance(k, tuple) else str(k)): jsonable(x)
                for k, x in v.items()}
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


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def cid(phase, policy, ops3, s, q):
    return f"{phase}|{policy}|OPS={ops3}|S={s}|Q={q}"


def enumerate_cases(phase):
    orders = (["".join(p) for p in itertools.permutations("CFN")] if phase == "A"
              else ["".join(p) for p in itertools.product("CFN", repeat=3)])
    masks = MASKS if phase == "A" else ((0, 0),)
    return sorted(cid(phase, pol, o, s, q) for pol in POLICIES for o in orders for s, q in masks)


# ---- the contract's machine, written here independently ----------------------------------
def machine(ops, policy):
    """(observed trace, reference trace) for one case; `policy` only changes the SUT model."""
    def snap(st):
        return {"epoch": st["e"], "captures": list(st["c"]), "refunds": list(st["r"]), "balance": st["b"]}
    ref = {"e": 0, "c": [0], "r": [0], "b": 0}
    sut = {"e": 0, "c": [0], "r": [0], "b": 0}
    obs_trace, ref_trace = [], []
    for op in ops:
        for st, faulty in ((ref, None), (sut, policy)):
            e = st["e"]
            if op == "C" and st["c"][e] == 0:
                st["c"][e] = 1; st["b"] += 100
            elif op == "F":
                if faulty == "refund_unchecked":
                    st["r"][e] += 1; st["b"] -= 100
                elif st["c"][e] == 1 and st["r"][e] == 0:
                    st["r"][e] = 1; st["b"] -= 100
            elif op == "N":
                st["e"] += 1; st["c"].append(0); st["r"].append(0)
            elif op == "S":
                st["b"] = 0 if faulty == "restart_cache" else 100 * (sum(st["c"]) - sum(st["r"]))
            elif op == "Q":
                st["b"] = 100 * (sum(st["c"]) - sum(st["r"]))
        obs_trace.append(snap(sut)); ref_trace.append(snap(ref))
    return obs_trace, ref_trace


def invariant_values(s):
    c, r, e = s["captures"], s["refunds"], s["epoch"]
    return {"count_domain": all(x in (0, 1) for x in c + r) and e >= 0,
            "refunds_le_captures": all(y <= x for x, y in zip(c, r)) and len(c) == len(r),
            "list_lengths": len(c) == e + 1 == len(r),
            "ledger_balance": s["balance"] == 100 * (sum(c) - sum(r))}


def read_candidates(tar_path):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tar_path.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    policy, ops, phase, sources, tail = None, [], None, None, False
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            fn, args = node.value.func.id, [ast.literal_eval(a) for a in node.value.args]
            if fn == "start":
                if policy is not None:
                    raise ValueError("start twice")
                policy = args[0]
            elif fn == "step":
                ops.append(args[0])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D3_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase, tail = ast.literal_eval(node.value.args[0]), True
    if policy is None or phase is None:
        raise ValueError("start()/finish() missing")
    core = "".join(o for o in ops if o in "CFN")
    return cid(phase, policy, core, int("S" in ops), int("Q" in ops)), ops, sources, tail


def verify(run: Path, root: Path = HERE):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    phase = manifest["phase"]
    P = PHASE[phase]
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = {c["id"]: c for c in json.loads((root / "architect-derived.json").read_text())["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    expected = enumerate_cases(phase)
    rep.check("space.enumeration_equals_frozen_ids", expected == sorted(k for k in derived if k.startswith(phase + "|"))
              and len(expected) == P["cases"], len(expected))

    # stages ------------------------------------------------------------------------------
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans_same_program", cmp_["same_dependency_graph"], cmp_["dependency_graph_sha256"])
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    per_sheet = {m.group(1): int(m.group(2)) for m in
                 re.finditer(r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", core_log)}
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["table_row_counts"]
    opt_counts = {t: n for t, n in tables.items() if t.startswith("fw_opt")}
    counts = {"core_per_sheet": per_sheet, "fw_final": tables.get("fw_final"), "fw_opt": opt_counts,
              "optional_multiplier": count("core", "optional_multiplier") or 1,
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"),
              "results_v2": len(db["results_db"]["results_v2"])}
    want_sheets = {"HEAD": 1, "IMPL": 3, "OPS": P["ops_sheet"], "TAIL": 1, **({"S": 1, "Q": 1} if phase == "A" else {})}
    rep.check("stage.core_per_sheet", per_sheet == want_sheets, per_sheet)
    rep.check("stage.core_fw_final_and_optional", tables.get("fw_final") == P["core"] and opt_counts == P["opt"]
              and counts["optional_multiplier"] == (4 if phase == "A" else 1), counts)
    rep.check("stage.reader_executor", counts["reader"] == counts["executor"] == counts["results_v2"] == P["cases"], counts)
    code2val = {int(r["bigint"]): (r["value"] or "") for r in db["main_db"]["NumberToValue1"]}
    rows = db["main_db"]["fw_final_after_sieve"]
    base = (next(iter(db["main_db"]["fw_final_base_tables"].values()), [{}]) or [{}])[0]
    col = {c.split("_", 1)[1]: c for c in (rows or [{}])[0] if c.startswith("combos") and "_" in c}
    def lit(code):
        """The string argument of a `start("x")` / `step("X")` value, parsed (never executed)."""
        return ast.literal_eval(ast.parse(code2val[int(code)].strip()).body[0].value.args[0])
    finals = []
    for row in rows:
        pol = lit((row.get(col["IMPL"]) or base.get(col["IMPL"]))[0])
        ops = "".join(lit(c) for c in (row.get(col["OPS"]) or base.get(col["OPS"])))
        finals.append((pol, ops))
    supports = [(0, 0)]
    for t, trs in db["main_db"].get("fw_opt_tables", {}).items():
        for r in trs:
            present = {s for s in ("S", "Q") for c, v in r.items() if c.startswith("combos") and c.endswith("_" + s) and v}
            supports.append((int("S" in present), int("Q" in present)))
    core_ids = sorted(cid(phase, pol, ops, s, q) for pol, ops in finals for s, q in supports)
    rep.check("identity.core_expanded", core_ids == expected and len(finals) == P["core"],
              {"fw_final": len(finals), "optional_supports": sorted(supports)})

    # Reader and Executor identity sets -----------------------------------------------------
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, sources_ok, order_ok, errs = {}, True, True, []
    for name, data in cands.items():
        try:
            ident, ops, sources, tail = parse_candidate(data.decode())
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = (ident, ops)
        sources_ok &= tail and sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
        order_ok &= ops[:3] == [o for o in ops if o in "CFN"] and [o for o in ops if o in "SQ"] in ([], ["S"], ["Q"], ["S", "Q"])
    rep.check("identity.reader", not errs and sorted(v[0] for v in rendered.values()) == expected, errs[:3])
    rep.check("reader.sources_order_tail", sources_ok and order_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == P["cases"] and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD)
              and "container" in (summary.get("sandbox_backend") or ""), dict(outcomes))

    # every record -------------------------------------------------------------------------
    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    rep.check("identity.executor", sorted(r["case_id"] for r in records) == expected)
    bad, fields, table, hidden = [], 0, Counter(), 0
    for r in records:
        fz = derived[r["case_id"]]
        obs, ref = machine(fz["events"], r["policy"])
        fails, cps = [], r["checkpoints"]
        for k, (o, rf) in enumerate(zip(obs, ref), start=1):
            inv = invariant_values(o)
            if o != rf or not all(inv.values()):
                fails.append(k)
        verdict = "PASS" if not fails else "DOMAIN_FAIL"
        final_fail = obs[-1] != ref[-1] or not all(invariant_values(obs[-1]).values())
        fw, row = r["framework"], rv2.get(r["framework"]["candidate_id"], {})
        checks = [("ops", r["ops"], fz["events"]), ("S/Q", (r["S"], r["Q"]), (int("S" in fz["events"]), int("Q" in fz["events"]))),
                  ("n_checkpoints", len(cps), len(fz["events"])), ("indices", [c["index"] for c in cps], list(range(1, len(cps) + 1))),
                  ("cp.op", [c["op"] for c in cps], fz["events"]),
                  ("observed=own", [c["observed"] for c in cps], obs), ("reference=own", [c["reference"] for c in cps], ref),
                  ("observed=frozen", [c["observed"] for c in cps], fz["predicted_trace"]),
                  ("reference=frozen", [c["reference"] for c in cps], fz["expected_trace"]),
                  ("mismatched_fields", [c["mismatched_fields"] for c in cps],
                   [[f for f in ("epoch", "captures", "refunds", "balance") if o[f] != rf[f]] for o, rf in zip(obs, ref)]),
                  ("invariants", [c["invariants"] for c in cps], [invariant_values(o) for o in obs]),
                  ("failing=own", r["failing_checkpoints"], fails), ("failing=frozen", r["failing_checkpoints"], fz["mismatch_checkpoints"]),
                  ("verdict=own", r["verdict"], verdict), ("verdict=frozen", r["verdict"], fz["predicted_outcome"]),
                  ("final_only=frozen", r["final_only_verdict"] == "DOMAIN_FAIL", fz["final_only_fail"]),
                  ("final_only=own", r["final_only_verdict"], "DOMAIN_FAIL" if final_fail else "PASS"),
                  ("hidden", r["hidden_by_final_only"], bool(fails) and not final_fail),
                  ("fw_var", r["fw_var"], 0 if not fails else 2), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("results_v2.outcome", row.get("outcome"), verdict), ("results_v2.code", row.get("verdict_code"), r["fw_var"]),
                  ("rendered", rendered.get(fw["source_ref"], (None,))[0], r["case_id"]),
                  ("rendered_ops", rendered.get(fw["source_ref"], (None, None))[1], fz["events"]),
                  ("candidate_sha", fw["source_sha256"], sha256(cands.get(fw["source_ref"], b""))),
                  ("source_sha", r["source_sha256"], module_sha), ("run_id", fw["run_id"], run_id)]
        fields += len(checks)
        wrong = [n for n, got, want in checks if got != want]
        if wrong:
            bad.append({"case": r["case_id"], "fields": wrong})
        table[(r["policy"], r["verdict"])] += 1
        hidden += r["hidden_by_final_only"]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:8]})
    by_policy = {p: {v: table[(p, v)] for (pp, v) in table if pp == p} for p in POLICIES}
    frozen_summary = json.loads((root / "architect-derived.json").read_text())["summary"][phase]
    totals = Counter(r["verdict"] for r in records)
    rep.check("observations.summary_equals_frozen", by_policy == frozen_summary["by_policy"]
              and dict(totals) == frozen_summary["outcomes"] and hidden == frozen_summary["hidden_by_final_only"],
              {"by_policy": by_policy, "totals": dict(totals), "hidden_by_final_only": hidden})

    # B: the CombiR -> Permut(IDENTICAL) alternative, planned only -----------------------------
    alt = None
    if phase == "B":
        multisets = list(itertools.combinations_with_replacement("CFN", 3))
        distinct = sorted({"".join(p) for m in multisets for p in itertools.permutations(m)})
        c = cmp_["cardinality"]
        alt = {"multisets": len(multisets), "distinct_orders": len(distinct),
               "equals_B_product": distinct == sorted("".join(p) for p in itertools.product("CFN", repeat=3)),
               "plan_toml": c.get("B-alt-toml"), "plan_xlsx": c.get("B-alt-xlsx"),
               "plan_ops": cmp_["per_slot"].get("B-alt-toml", {}).get("OPS")}
        m = c["B-alt-toml"]["mandatory"]
        rep.check("b_alt.enumeration_and_bound", alt["multisets"] == 10 and alt["distinct_orders"] == 27 and alt["equals_B_product"]
                  and m[0] == "BOUNDED" and m[2] <= 81 <= m[3] and c["B-alt-toml"] == c["B-alt-xlsx"], alt)

    # envelope / provenance ------------------------------------------------------------------
    b = P["budget"]
    need = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
            "--budget-mandatory-rows", b[0], "--budget-final-candidates", b[1], "--budget-disk-bytes", b[2],
            "--budget-wall-time-seconds", b[3]]
    rep.check("envelope.command", all(t in argv for t in need) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx" and Path(argv[2]).parent.name == phase, argv[2:])
    rep.check("envelope.db", re.fullmatch(rf"as0927_d3{phase.lower()}_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS
             and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    copies = {n: sha256((run / "inputs" / n).read_bytes()) == sha256((root / "spec" / phase / n).read_bytes())
              for n in ("spec.toml", "demo.xlsx")}
    rep.check("provenance.input_copies", all(copies.values()), copies)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / phase / "demo.xlsx")["sheets"])
    return rep, {"phase": phase, "stage_counts": counts, "by_policy": by_policy, "totals": dict(totals),
                 "hidden_by_final_only": hidden, "b_alt": alt, "records": records}


WITNESSES = {
    "A": {"refund_before_charge": "A|refund_unchecked|OPS=FCN|S=0|Q=0",
          "restart_breaks_reconcile_heals": "A|restart_cache|OPS=CNF|S=1|Q=1",
          "restart_without_reconcile": "A|restart_cache|OPS=CNF|S=1|Q=0",
          "positive_control": "A|correct|OPS=CNF|S=1|Q=1"},
    "B": {"duplicate_refund": "B|refund_unchecked|OPS=CFF|S=0|Q=0"},
}


def witnesses(run, data):
    recs = {r["case_id"]: r for r in data["records"]}
    out = []
    for label, case in WITNESSES[data["phase"]].items():
        r = recs[case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "ops": r["ops"],
                    "checkpoints": [{"k": c["index"], "op": c["op"], "observed": c["observed"], "reference": c["reference"],
                                     "ok": c["ok"]} for c in r["checkpoints"]],
                    "failing_checkpoints": r["failing_checkpoints"], "verdict": r["verdict"],
                    "final_only_verdict": r["final_only_verdict"], "framework_outcome": r["framework"]["outcome"],
                    "replay": f"python replay.py --run {run.relative_to(HERE)} --case '{case}'"})
    return {"schema": "d3.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d3.verification/v1", "run": run.name, "phase": data["phase"], "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()),
           "checks": rep.checks, **{k: data[k] for k in ("stage_counts", "by_policy", "totals", "hidden_by_final_only", "b_alt")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if sorted(r["case_id"] for r in data["records"]) == enumerate_cases(data["phase"]):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
