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

"""Independent offline verifier for the D13a evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports tools.py, sut.py, oracle.py, runtime.py, analysis.py or derive.py, never
connects to a database, never executes a candidate (candidates and dictionary values are parsed with
`ast`). Policy traces, the policy-blind prefix check and the guarded reference are rebuilt here; the
480 identities are reassembled from 96 mandatory fw_final rows x (absent + 4 fw_opt1 rows).
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
POLICIES = ("guarded", "sticky_approval", "success_only_taint", "no_dedup")
CANARY, MID = "D13A_LOCAL_CANARY", "notice-1"
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
WITNESSES = ["P=sticky_approval|O=ASR|N=1|F=0|X=1", "P=guarded|O=ASR|N=1|F=0|X=1", "P=success_only_taint|O=ARS|N=1|F=1|X=none",
             "P=no_dedup|O=ASR|N=2|F=0|X=none", "P=guarded|O=ASR|N=2|F=1|X=3"]
FIELDS = ("policy", "order", "send_repetitions", "fail_read", "revoke_cut", "trace", "send_results", "outbox", "final_state",
          "reference_sends", "reference_outbox", "decisions_ok", "outbox_ok", "violations")


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


def cid(p, o, n, f, x):
    return f"P={p}|O={o}|N={n}|F={f}|X={'none' if x is None else x}"


def run_policy(p, order, n, fail, cut):
    """This verifier's own rendering of the four orchestrators (the observable event protocol)."""
    st = dict(approved=False, tainted=False, sent_once=False, buffer="PUBLIC")
    trace, results, box = [], [], []
    ev = lambda name, **kw: trace.append({"event": name, **kw, "state": dict(st), "outbox_size": len(box)})    # noqa: E731
    def revoke(c):
        st["approved"] = st["approved"] if p == "sticky_approval" else False
        ev("revoke", cut=c)
    plan = (["X"] if cut == 0 else []) + [s for k, op in enumerate(order, 1) for s in [op] + (["X"] if cut == k else [])]
    for step in plan:
        if step == "X":
            revoke(plan.index("X") if cut == 0 else cut)
        elif step == "A":
            st["approved"] = True
            ev("approve")
        elif step == "R":
            ev("read_start")
            st["buffer"] = CANARY
            st["tainted"] = st["tainted"] or p != "success_only_taint"
            ev("read_chunk", payload=CANARY)
            if not fail:
                st["tainted"] = True
            ev("read_error" if fail else "read_ok")
        else:
            for q in range(1, n + 1):
                ev("send_request", request=q, message_id=MID)
                if not st["approved"]:
                    act, why = "block", "no_approval"
                elif st["tainted"]:
                    act, why = "block", "tainted"
                elif st["sent_once"] and p != "no_dedup":
                    act, why = "dedup", "duplicate"
                else:
                    act, why = "emit", "allowed"
                pay = st["buffer"] if act == "emit" else None
                if act == "emit":
                    box.append({"message_id": MID, "payload": pay})
                    st["sent_once"] = True
                results.append({"request": q, "action": act, "reason": why, "payload": pay})
                ev("send_result", request=q, action=act, reason=why, payload=pay, message_id=MID)
    return trace, results, box, dict(st)


def prefix_violations(trace):
    out = []
    for i, e in enumerate(trace):
        if e["event"] == "send_result" and e["action"] == "emit":
            before = trace[:i]
            last = [x["event"] for x in before if x["event"] in ("approve", "revoke")]
            if not last or last[-1] != "approve":
                out.append({"request": e["request"], "kind": "unapproved_emit"})
            if any(x["event"] == "read_chunk" for x in before):
                out.append({"request": e["request"], "kind": "tainted_emit"})
            if any(x["event"] == "send_result" and x["action"] == "emit" and x["message_id"] == e["message_id"] for x in before):
                out.append({"request": e["request"], "kind": "duplicate_emit"})
    return out


def model(p, order, n, fail, cut):
    trace, results, box, final = run_policy(p, order, n, fail, cut)
    gtrace, gres, gbox, _ = run_policy("guarded", order, n, fail, cut)
    ref = [{k: r[k] for k in ("request", "action", "payload")} for r in gres]
    pub = [{k: r[k] for k in ("request", "action", "payload")} for r in results]
    viol = prefix_violations(trace)
    ok = pub == ref and box == gbox and not viol
    return {"policy": p, "order": order, "send_repetitions": n, "fail_read": bool(fail), "revoke_cut": cut, "trace": trace,
            "send_results": results, "outbox": box, "final_state": final, "reference_sends": ref, "reference_outbox": gbox,
            "decisions_ok": pub == ref, "outbox_ok": box == gbox, "violations": viol, "verdict": "PASS" if ok else "DOMAIN_FAIL"}


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources = [], None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D13_SOURCES":
            sources = ast.literal_eval(node.value)
    return calls, sources


def case_of(calls):
    names = [c[0] for c in calls]
    cfg = {c[0]: c[1] for c in calls if c[0] != "plan"}
    order = "".join(c[1] for c in calls if c[0] == "plan")
    if names[0] != "impl" or Counter(names) - Counter({"set_revoke": 1}) != Counter({"impl": 1, "repetitions": 1, "read_mode": 1, "plan": 3}) \
            or sorted(order) != ["A", "R", "S"]:
        raise ValueError(f"atoms {names}")
    return cid(cfg["impl"], order, cfg["repetitions"], cfg["read_mode"], cfg.get("set_revoke")), names


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("tools", "sut", "oracle", "runtime")}
    own = {cid(p, "".join(o), n, f, x): model(p, "".join(o), n, f, x) for p in POLICIES for o in itertools.permutations("ARS")
           for n in (1, 2) for f in (0, 1) for x in (None, 0, 1, 2, 3)}
    expected_ids = sorted(own)
    rep.check("space.identities", len(expected_ids) == 480 and expected_ids == sorted(frozen), {"identities": 480})
    mism = [c for c, o in own.items() if any(o[k] != frozen[c][k] for k in FIELDS) or o["verdict"] != frozen[c]["predicted_outcome"]]
    rep.check("space.frozen_equals_own_model", not mism, {"mismatches": mism[:5]})

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["mandatory"][:2] == ["EXACT", 96] and c["optional_multiplier"][:2] == ["EXACT", 5] and c["final"][:2] == ["EXACT", 480]
                      for c in cmp_["cardinality"].values()), cmp_["cardinality"])
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows, orows = tables["fw_final"], tables.get("fw_opt1", [])
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    def cell(r, sheet):
        v = r.get(cols[sheet])
        return list(base.get(cols[sheet]) or []) if v is None else list(v)
    mandatory, bad_rows = [], []
    for r in frows:
        try:
            calls = [c for sheet in ("IMPL", "REPETITIONS", "READ_MODE", "ORDER") for code in cell(r, sheet) for c in calls_of(code2val[int(code)])[0]]
            if r.get(cols["REVOKE"]) is not None:
                raise ValueError("a mandatory row carries REVOKE")
            mandatory.append(calls)
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    cuts = []
    for r in orows:
        (code,) = r[cols["REVOKE"]]
        cuts.append(calls_of(code2val[int(code)])[0][0])
    assembled = [case_of(m + ([c] if c else []))[0] for m in mandatory for c in [None, *cuts]]
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "fw_opt1_rows": len(orows),
              "assembled": len(assembled), "reader": count("reader", "candidates"), "executor": count("executor", "processed"),
              "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", counts["core_fw_final"] == counts["fw_final_rows"] == 96 and counts["fw_opt1_rows"] == 4
              and counts["assembled"] == counts["reader"] == counts["executor"] == counts["results_v2"] == 480, counts)
    rep.check("identity.core_mandatory_x_optional", not bad_rows and sorted(assembled) == expected_ids and len(set(assembled)) == 480
              and sorted(c[1] for c in cuts) == [0, 1, 2, 3] and set(cols) == {"HEAD", "IMPL", "REPETITIONS", "READ_MODE", "REVOKE", "ORDER", "TAIL"}
              and not any(k.startswith("fw_opt") and k != "fw_opt1" and v for k, v in tables.items()),
              {"bad_rows": bad_rows[:3], "optional_cuts": sorted(c[1] for c in cuts)})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, positions = {}, True, [], Counter()
    for name, data in cands.items():
        try:
            calls, sources = calls_of(data.decode())
            rendered[name], names = case_of(calls)
            positions[names.index("set_revoke") if "set_revoke" in names else "absent"] += 1
        except (ValueError, SyntaxError, KeyError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids,
              {"errors": errs[:3], "set_revoke_atom_position": dict(positions)})
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 480 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    by_id = {r["case_id"]: r for r in records}
    rep.check("identity.executor", sorted(by_id) == expected_ids and len(records) == 480)
    bad, nf = [], 0
    for c, r in by_id.items():
        if c not in own:
            bad.append((c, "unknown"))
            continue
        o, fw = own[c], r["framework"]
        checks = [("schema", r["schema"], "d13a.observation/v1"), *[(k, r[k], o[k]) for k in FIELDS], *[(f"frozen_{k}", r[k], frozen[c][k]) for k in FIELDS],
                  ("verdict", r["verdict"], o["verdict"]), ("frozen_outcome", r["verdict"], frozen[c]["predicted_outcome"]),
                  ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("outcome", fw["outcome"], o["verdict"]), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("no_escaped_tool_error", any(e["event"] == "read_error" for e in r["trace"]) == r["fail_read"], True),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), c)]
        nf += len(checks)
        bad += [(c, k, str(g)[:60], str(x)[:60]) for k, g, x in checks if g != x]
    rep.check("observations.every_field", not bad, {"fields_compared": nf, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records)
    by_policy = {p: dict(Counter(r["verdict"] for r in records if r["policy"] == p)) for p in POLICIES}
    kinds = {p: dict(Counter(v["kind"] for r in records if r["policy"] == p for v in r["violations"])) for p in POLICIES}
    rep.check("observations.totals", dict(totals) == derived["outcomes"] and by_policy == derived["by_policy"]
              and kinds == {"guarded": {}, "sticky_approval": {"unapproved_emit": 4}, "success_only_taint": {"tainted_emit": 14},
                            "no_dedup": {"duplicate_emit": 8}}, {"totals": dict(totals), "by_policy": by_policy, "violation_kinds": kinds})
    saved = json.loads((run / "analysis.json").read_text())
    w = {c: by_id[c] for c in WITNESSES}
    mech = (w[WITNESSES[0]]["send_results"][0]["action"] == "emit" and w[WITNESSES[0]]["violations"] == [{"request": 1, "kind": "unapproved_emit"}]
            and w[WITNESSES[0]]["outbox"] == [{"message_id": MID, "payload": "PUBLIC"}]
            and w[WITNESSES[1]]["send_results"][0]["action"] == "block" and w[WITNESSES[1]]["verdict"] == "PASS"
            and w[WITNESSES[2]]["outbox"] == [{"message_id": MID, "payload": CANARY}] and w[WITNESSES[2]]["violations"] == [{"request": 1, "kind": "tainted_emit"}]
            and [e["event"] for e in w[WITNESSES[2]]["trace"]][:4] == ["approve", "read_start", "read_chunk", "read_error"]
            and len(w[WITNESSES[3]]["outbox"]) == 2 and w[WITNESSES[3]]["violations"] == [{"request": 2, "kind": "duplicate_emit"}]
            and [s["action"] for s in w[WITNESSES[4]]["send_results"]] == ["emit", "dedup"] and w[WITNESSES[4]]["verdict"] == "PASS"
            and not prefix_violations(w[WITNESSES[4]]["trace"]))
    deny_all_fails = sum(1 for o in own.values() if o["policy"] == "guarded" and any(r["action"] == "emit" for r in o["reference_sends"]))
    rep.check("demonstration.mechanisms", mech and saved["by_policy"] == {p: dict(v) for p, v in by_policy.items()}
              and saved["violation_kinds"] == kinds and saved["counts"]["framework_attempts"] == 480 and deny_all_fails > 0,
              {"witness_outcomes": {c: w[c]["verdict"] for c in WITNESSES}, "counts": saved["counts"],
               "configurations_where_deny_all_would_fail": deny_all_fails})

    need = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
            "--budget-mandatory-rows", "150", "--budget-final-candidates", "500", "--budget-disk-bytes", "100000000",
            "--budget-wall-time-seconds", "1200"]
    rep.check("envelope.command", all(t in argv for t in need) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    dbm = manifest["databases"]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(r"as0927_d13a_[0-9a-z_]+", dbm["name"]) is not None
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
    return rep, {"stage_counts": counts, "totals": dict(totals), "by_policy": by_policy, "extra": {"violation_kinds": kinds}, "records": by_id}


def witnesses(run, data):
    out = []
    for case in WITNESSES:
        r = data["records"][case]
        out.append({"case_id": case, "candidate": r["framework"]["source_ref"], "events": [e["event"] for e in r["trace"]],
                    "send_results": r["send_results"], "outbox": r["outbox"], "reference_sends": r["reference_sends"],
                    "violations": r["violations"], "verdict": r["verdict"], "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d13a.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d13a.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
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
