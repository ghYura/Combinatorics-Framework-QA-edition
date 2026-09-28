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

"""Independent offline verifier for one D4 campaign (main or controls) evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py or runtime.py, never connects to a database,
never executes a candidate (candidates are parsed with `ast`). Legality, the adapter's expected
output under each policy and the pairwise obligations are re-derived here from CONTRACT.md.
"""
import argparse
import ast
import base64
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
POLICIES = ("correct", "drops_gzip", "ignores_debug_rule")
AXES = ("env", "mode", "transport", "features", "workers", "debug")
BODY = b'{"sensor":7}\n'
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
FEATURE_PAIRS = [list(p) for p in itertools.combinations(("audit", "cache", "gzip"), 2)]


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


def rules(c):
    """Violated rule IDs, written from the CONTRACT's table."""
    f = c["features"]
    out = []
    for rid, bad in (("R1", c["env"] == "prod" and c["transport"] == "http"), ("R2", c["mode"] == "live" and "cache" in f),
                     ("R3", c["mode"] == "live" and c["workers"] < 2), ("R4", c["env"] == "prod" and any(x not in ("audit", "gzip") for x in f)),
                     ("R5", c["mode"] == "batch" and "audit" in f and c["workers"] < 2), ("R6", c["env"] == "prod" and c["debug"])):
        if bad:
            out.append(rid)
    return out


def key(c):
    return "|".join(f"{a}={'+'.join(c[a]) if a == 'features' else int(c[a]) if a == 'debug' else c[a]}" for a in AXES)


def mandatory_configs():
    return [dict(env=e, mode=m, transport=t, features=f, workers=w, debug=False)
            for e, m, t, f, w in itertools.product(("dev", "prod"), ("batch", "live"), ("http", "https"), FEATURE_PAIRS, (1, 2))]


def model(c, policy):
    """Expected SUT output (acceptance, violation IDs, envelope fields) under `policy`."""
    bad = [r for r in rules(c) if not (policy == "ignores_debug_rule" and r == "R6")]
    if bad:
        return {"accepted": False, "violations": bad}
    h = {}
    if "audit" in c["features"]:
        h["X-Audit"] = "1"
    if "cache" in c["features"]:
        h["Cache-Control"] = "max-age=60"
    h["Content-Encoding"] = "gzip" if "gzip" in c["features"] and policy != "drops_gzip" else "identity"
    if c["debug"]:
        h["X-Debug"] = "1"
    return {"accepted": True, "violations": [], "url": f"{c['transport']}://telemetry.invalid/{c['mode']}",
            "workers": c["workers"], "headers": h}


def verdict(c, policy):
    m, want = model(c, policy), rules(c)
    classes = []
    if want and m["accepted"]:
        classes.append("wrong_acceptance")
    elif not want and not m["accepted"]:
        classes.append("wrong_rejection")
    elif want and m["violations"] != want:
        classes.append("wrong_violation_ids")
    if m["accepted"] and not want:
        right = "gzip" if "gzip" in c["features"] else "identity"
        if m["headers"]["Content-Encoding"] != right:
            classes += ["wrong_headers"]                 # the payload itself still decodes to the original
    return classes


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    cfg, policy, phase, sources = {"features": [], "debug": False}, None, None, None
    for node in ast.parse(src).body:
        calls = [node.value] if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else []
        for call in calls:
            if not isinstance(call.func, ast.Name):
                continue
            fn, args = call.func.id, [ast.literal_eval(a) for a in call.args]
            if fn == "impl":
                policy = args[0]
            elif fn == "feature":
                cfg["features"].append(args[0])
            elif fn == "debug":
                cfg["debug"] = True
            elif fn in ("env", "mode", "transport", "workers"):
                if fn in cfg:
                    raise ValueError(f"{fn} twice")
                cfg[fn] = args[0]
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D4_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase = ast.literal_eval(node.value.args[0])
    cfg["features"] = sorted(cfg["features"])
    return f"{phase}|{policy}|{key(cfg)}", cfg, sources


def verify(run: Path, root: Path = HERE):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    campaign = manifest["campaign"]
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"] if c["phase"] == campaign}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    mand = mandatory_configs()
    legal = sorted([dict(c, debug=d) for c in mand for d in (False, True) if not rules(dict(c, debug=d))], key=key)
    if campaign == "main":
        configs = legal
    else:
        configs = derived["invalid_controls"]
        rep.check("controls.each_violates_exactly_one_different_rule",
                  sorted(tuple(rules(c)) for c in configs) == [(r,) for r in ("R1", "R2", "R3", "R4", "R5", "R6")])
    expected = sorted(f"{campaign}|{p}|{key(c)}" for c in configs for p in POLICIES)
    rep.check("space.expected_equals_frozen", expected == sorted(frozen) and len(legal) == 22
              and len(expected) == (66 if campaign == "main" else 18), len(expected))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor") + (("sieve",) if campaign == "main" else ()):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values()), cmp_["cardinality"])
    per_sheet = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify",
                                                                    (run / "logs" / "core.log").read_text(errors="replace"))}
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["table_row_counts"]
    counts = {"core_per_sheet": per_sheet, "core_fw_final": count("core", "fw_final"), "fw_opt": {t: n for t, n in tables.items() if t.startswith("fw_opt")},
              "post_sieve": count("sieve", "post_sieve"), "assembled_before_deferred": count("sieve", "assembled_before_deferred_bonds"),
              "deferred_removals": count("sieve", "deferred_bond_removals"), "reader_expected": count("sieve", "reader_expected"),
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"),
              "results_v2": len(db["results_db"]["results_v2"])}
    log = (run / "logs" / "bundle_run.log").read_text(errors="replace")
    if campaign == "main":
        want_sheets = {"HEAD": 1, "IMPL": 3, "ENV": 2, "MODE": 2, "TRANSPORT": 2, "FEATURES": 3, "WORKERS": 2, "DEBUG": 1, "TAIL": 1}
        sieve = {m.group(1): int(m.group(2)) for m in re.finditer(r"rule (\S+): matched (\d+) row", log)}
        m = re.search(r"sieve: scanned (\d+), unique removals (\d+) \(overlap (\d+)\) → fw_final now (\d+)", log)
        line = [int(x) for x in m.groups()] if m else None
        rows = [(p, c) for p in POLICIES for c in mand]
        own = {r: sum(r in rules(c) for _, c in rows) for r in ("R1", "R2", "R3", "R4", "R5")}
        overlap = sum(len(rules(c)) > 1 for _, c in rows)
        seq, alive = [len(rows)], rows
        for r in ("R1", "R2", "R3", "R4", "R5"):
            alive = [x for x in alive if r not in rules(x[1])]
            seq.append(len(alive))
        truth = {"per_rule": own, "overlap": overlap, "sequential": seq}
        counts.update(sieve_rules=sieve, sieve_line=line, truth=truth)
        rep.check("sidecar.truth_table", own == derived["counts"]["per_rule_raw_matches"]
                  and seq == derived["counts"]["sequential_mandatory_survivors"], truth)
        rep.check("stage.core", per_sheet == want_sheets and counts["core_fw_final"] == 144 and counts["fw_opt"] == {"fw_opt1": 1}, counts)
        rep.check("stage.sieve_live", {r: sieve.get(r) for r in own} == own and sieve.get("R6", 0) == 0
                  and line == [144, 108, overlap, 36] and "deferred" in log, {"rules": sieve, "line": line})
        rep.check("stage.deferred_reader_filter", counts["post_sieve"] == 36 and counts["assembled_before_deferred"] == 72
                  and counts["deferred_removals"] == 6 and counts["reader_expected"] == 66, counts)
        rep.check("stage.reader_executor", counts["reader"] == counts["executor"] == counts["results_v2"] == 66, counts)
        code2val = {int(r["bigint"]): r["value"] for r in db["main_db"]["NumberToValue1"]}
        frows = db["main_db"]["fw_final_after_sieve"]
        base = (next(iter(db["main_db"]["fw_final_base_tables"].values()), [{}]) or [{}])[0]
        col = {c.split("_", 1)[1]: c for c in (frows or [{}])[0] if c.startswith("combos") and "_" in c}
        def lits(sheet, row):
            """The argument of each atom call stored for `sheet` (parsed, never executed)."""
            return [ast.literal_eval(ast.parse(code2val[int(x)].strip()).body[0].value.args[0])
                    for x in (row.get(col[sheet]) or base.get(col[sheet]))]
        decoded = []
        for r in frows:
            cfg = dict(env=lits("ENV", r)[0], mode=lits("MODE", r)[0], transport=lits("TRANSPORT", r)[0],
                       features=sorted(lits("FEATURES", r)), workers=lits("WORKERS", r)[0], debug=False)
            decoded.append((lits("IMPL", r)[0], cfg))
        assembled = [(p, dict(c, debug=d)) for p, c in decoded for d in (False, True)]
        kept = sorted(f"main|{p}|{key(c)}" for p, c in assembled if "R6" not in rules(c))
        rep.check("identity.core_supports_and_reader_filter", len(decoded) == 36 and len(assembled) == 72
                  and len(assembled) - len(kept) == 6 and kept == expected)
    else:
        rep.check("stage.core", per_sheet == {"HEAD": 1, "IMPL": 3, "CONFIG": 6, "TAIL": 1} and counts["core_fw_final"] == 18
                  and "--sieve" not in argv, counts)
        rep.check("stage.reader_executor", counts["reader"] == counts["executor"] == counts["results_v2"] == 18, counts)

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            ident, cfg, sources = parse_candidate(data.decode())
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = ident
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == len(expected) and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""), dict(outcomes))

    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected)
    bad, fields, acc_fail, trans_fail = [], 0, [], []
    for cid, r in records.items():
        if cid not in frozen:                        # a case outside the frozen legal set (e.g. a sieve defect)
            bad.append((cid, "not_in_frozen_set"))
            continue
        c, pol, fz = r["config"], r["policy"], frozen[cid]
        m, want = model(c, pol), rules(c)
        res = r["result"]
        cls = verdict(c, pol)
        checks = [("config", c, fz["config"]), ("expected_violations", r["expected_violations"], want),
                  ("frozen_violations", want, fz["violations"]), ("accepted", res["accepted"], m["accepted"]),
                  ("frozen_acceptance", res["accepted"], fz["predicted_acceptance"]), ("violations", res["violations"], m["violations"])]
        if res["accepted"]:
            env = res["envelope"]
            body = base64.b64decode(env["body_b64"])
            enc = env["headers"].get("Content-Encoding")
            plain = gzip.decompress(body) if enc == "gzip" else body
            checks += [("url", env["url"], m["url"]), ("workers", env["workers"], m["workers"]), ("headers", env["headers"], m["headers"]),
                       ("payload_decodes", plain, BODY)]
        checks += [("failure_classes", sorted(r["failure_classes"]), sorted(cls)), ("verdict", r["verdict"], "PASS" if not cls else "DOMAIN_FAIL"),
                   ("frozen_outcome", r["verdict"], fz["predicted_outcome"]), ("fw_var", r["fw_var"], 0 if not cls else 2),
                   ("results_v2", (rv2.get(r["framework"]["candidate_id"], {}).get("outcome"), rv2.get(r["framework"]["candidate_id"], {}).get("verdict_code")),
                    (r["verdict"], r["fw_var"])), ("metrics_fw_var", r["framework"]["metrics_fw_var"], r["fw_var"]),
                   ("rendered", rendered.get(r["framework"]["source_ref"]), cid),
                   ("candidate_sha", r["framework"]["source_sha256"], sha256(cands.get(r["framework"]["source_ref"], b""))),
                   ("source_sha", r["source_sha256"], module_sha), ("run_id", r["framework"]["run_id"], run_id)]
        fields += len(checks)
        wrong = [n for n, got, w in checks if got != w]
        if wrong:
            bad.append({"case": cid, "fields": wrong})
        if not r["acceptance_ok"]:
            acc_fail.append(cid)
        if isinstance(r["transformation"], dict) and not all(r["transformation"].values()):
            trans_fail.append(cid)
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    rep.check("observations.totals", dict(totals) == derived["outcomes"][campaign], {"totals": dict(totals), "by_policy": by_policy,
              "acceptance_failures": len(acc_fail), "transformation_failures": len(trans_fail)})
    extra = {"acceptance_failures": sorted(acc_fail), "transformation_failures": sorted(trans_fail)}

    if campaign == "main":
        def obligations(c):
            val = lambda a: "+".join(c[a]) if a == "features" else str(int(c[a])) if a == "debug" else str(c[a])   # noqa: E731
            return {f"{a}={val(a)}|{b}={val(b)}" for a, b in itertools.combinations(AXES, 2)}
        need = set().union(*(obligations(c) for c in legal))
        rows = derived["pairwise"]["rows"]
        by_key = {key(c): c for c in legal}
        covered = set().union(*(obligations(by_key[k]) for k in rows if k in by_key))
        detections = {p: sorted(k for k in rows if records[f"main|{p}|{k}"]["verdict"] == "DOMAIN_FAIL") for p in POLICIES}
        pair = {"obligations": len(need), "rows": len(rows), "rows_legal": all(k in by_key for k in rows), "covered": len(covered & need),
                "measured_detections": detections}
        rep.check("pairwise.certificate", sorted(need) == sorted(derived["pairwise"]["obligations"]) and len(need) == 60
                  and pair["rows_legal"] and covered >= need and len(rows) == 9, pair)
        wrong = {"removed_legal_candidates": sum("gzip" in r["config"]["features"] for r in records.values()),
                 "remaining": sum("gzip" not in r["config"]["features"] for r in records.values()),
                 "remaining_domain_fail": sum(r["verdict"] == "DOMAIN_FAIL" and "gzip" not in r["config"]["features"] for r in records.values()),
                 "observed_domain_fail_hidden": sum(r["verdict"] == "DOMAIN_FAIL" and "gzip" in r["config"]["features"] for r in records.values())}
        rep.check("wrong_bond.offline_masking", wrong["removed_legal_candidates"] == derived["wrong_sieve"]["removed_legal_candidates"]
                  and wrong["remaining"] == derived["wrong_sieve"]["remaining_candidates"] and wrong["remaining_domain_fail"] == 0
                  and wrong["observed_domain_fail_hidden"] == 18, wrong)
        prod = next(c for p, c in decoded if c["env"] == "prod")
        shown = {"prod_without_debug": f"main|correct|{key(dict(prod, debug=False))}" in records,
                 "prod_with_debug_filtered": f"main|correct|{key(dict(prod, debug=True))}" not in records,
                 "row": key(prod)}
        rep.check("demonstration.prod_debug_filtered_at_reader", shown["prod_without_debug"] and shown["prod_with_debug_filtered"], shown)
        extra.update(pairwise=pair, wrong_bond=wrong, prod_debug=shown)

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "200", "--budget-final-candidates", "300", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "600"]
    rep.check("envelope.command", all(t in argv for t in need_args) and ("--sieve" in argv) == (campaign == "main")
              and "--override-budget" not in argv and Path(argv[2]).parent.name == campaign, argv[2:])
    rep.check("envelope.db", re.fullmatch(rf"as0927_d4{'main' if campaign == 'main' else 'ctrl'}_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    if campaign == "main":
        side_sha = sha256((root / "spec" / "main" / "demo.constraints.json").read_bytes())
        run_json = json.loads((run / "run" / "run.json").read_text())
        chain = {sha256((run / "inputs" / "demo.constraints.json").read_bytes()), run_json.get("constraints_sidecar_sha256"),
                 sha256((run / "run" / "wb__demo.constraints.json").read_bytes())}
        rep.check("provenance.companion_chain", chain == {side_sha}
                  and json.loads((run / "run" / "sidecar.json").read_text())["constraints"] == json.loads((root / "spec" / "main" / "demo.constraints.json").read_text())["constraints"])
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / campaign / "demo.xlsx")["sheets"])
    return rep, {"campaign": campaign, "stage_counts": counts, "totals": dict(totals), "by_policy": by_policy, "extra": extra,
                 "records": records}


WITNESSES = {"main": {"correct_cache_gzip": "main|correct|env=dev|mode=batch|transport=https|features=cache+gzip|workers=1|debug=0",
                      "drops_gzip_cache_gzip": "main|drops_gzip|env=dev|mode=batch|transport=https|features=cache+gzip|workers=1|debug=0"},
             "controls": {"correct_R6_control": "controls|correct|env=prod|mode=batch|transport=https|features=audit+gzip|workers=2|debug=1",
                          "ignores_debug_rule_R6_control": "controls|ignores_debug_rule|env=prod|mode=batch|transport=https|features=audit+gzip|workers=2|debug=1"}}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES[data["campaign"]].items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "result": r["result"],
                    "failure_classes": r["failure_classes"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run {run.relative_to(HERE)} --case '{case}'"})
    return {"schema": "d4.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d4.verification/v1", "run": run.name, "campaign": data["campaign"], "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES[data["campaign"]].values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
