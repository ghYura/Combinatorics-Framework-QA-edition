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

"""Independent offline verifier for the D10 evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py, diagnosis.py or derive.py, never connects
to a database, never executes a candidate (candidates and dictionary values are parsed with `ast`).
Readings are recomputed from each label's state code with this file's own probe arithmetic; every
diagnosis certificate is recomputed from the OBSERVED matrix and compared with diagnosis.json and
the frozen predictions.
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
LABELS = [f"F{i:02}" for i in range(1, 13)]
CODE = {f: [1, 2, 4, 8, 7, 15][(i - 1) // 2] for i, f in enumerate(LABELS, start=1)}
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
WITNESSES = ["S=00000011|H=F01", "S=00000011|H=F09", "S=00001111|H=F09", "S=11111111|H=F02", "S=00000000|H=F01"]


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


def full_signature(code):
    f = {k: (code >> i) & 1 for i, k in enumerate("abcd")}
    return [f["a"], f["b"], f["c"], f["d"], (f["a"] + f["b"] + f["d"]) % 2, (f["a"] + f["c"] + f["d"]) % 2,
            (f["b"] + f["c"] + f["d"]) % 2, (f["a"] + f["b"] + f["c"]) % 2]


def expect(mask, label):
    sel = [i for i, ch in enumerate(mask) if ch == "1"]
    sig = full_signature(CODE[label])
    return {"mask": mask, "selected": sel, "sensor_cost": len(sel), "fault": label,
            "latent_bits": [(CODE[label] >> i) & 1 for i in range(4)], "readings": [sig[i] for i in sel],
            "signature": "".join(str(sig[i]) for i in sel)}


FIELDS = ("mask", "selected", "sensor_cost", "fault", "latent_bits", "readings", "signature")


def matrix_guard(records):
    """This verifier's own guard; returns (full signatures per label) or None."""
    cnt = Counter((r["mask"], r["fault"]) for r in records)
    if set(cnt) != {(format(i, "08b"), f) for i in range(256) for f in LABELS} or any(v != 1 for v in cnt.values()):
        return None
    if any(r["verdict"] != "PASS" or r["case_id"] != f"S={r['mask']}|H={r['fault']}" for r in records):
        return None
    full = {r["fault"]: r["readings"] for r in records if r["mask"] == "11111111"}
    if any(r["readings"] != [full[r["fault"]][i] for i, ch in enumerate(r["mask"]) if ch == "1"] for r in records):
        return None
    return full


def certificates(full):
    by_sig = {}
    for f in LABELS:
        by_sig.setdefault(tuple(full[f]), []).append(f)
    classes = [{"class": 0, "members": ["H0"], "signature": [0] * 8}]
    for k, (sig, mem) in enumerate(sorted(by_sig.items(), key=lambda kv: LABELS.index(kv[1][0])), start=1):
        classes.append({"class": k, "members": mem, "signature": list(sig)})
    S = [c["signature"] for c in classes]
    suites = []
    for i in range(256):
        mask = format(i, "08b")
        idx = [k for k in range(8) if mask[k] == "1"]
        w = ["".join(str(s[k]) for k in idx) for s in S]
        dist = [{"classes": [a, b], "distance": sum(x != y for x, y in zip(w[a], w[b]))} for a in range(7) for b in range(a + 1, 7)]
        md = min(d["distance"] for d in dist)
        suites.append({"mask": mask, "cost": len(idx), "signatures": w, "distances": dist, "min_distance": md,
                       "detect": w[0] not in w[1:], "separate": md > 0, "erasure": md > 1, "error": md > 2})
    winners = {}
    for g in ("detect", "separate", "erasure", "error"):
        ok = [s for s in suites if s[g]]
        c0 = min(s["cost"] for s in ok)
        tied = sorted(s["mask"] for s in ok if s["cost"] == c0)
        winners[g] = {"mask": tied[0], "cost": c0, "feasible_count": len(ok), "minimum_cost_masks": tied}
    # adaptive: bottom-up over beliefs by size
    opt = {}
    for size in range(1, 8):
        for belief in itertools.combinations(range(7), size):
            if size == 1:
                opt[belief] = (0, None)
                continue
            best = None
            for s in range(8):
                zero = tuple(c for c in belief if S[c][s] == 0)
                one = tuple(c for c in belief if S[c][s] == 1)
                if zero and one:
                    cand = (1 + max(opt[zero][0], opt[one][0]), s)
                    best = cand if best is None or cand < best else best
            opt[belief] = best
    dp = [{"belief": [i for i in range(7) if fl[i]], "cost": opt[tuple(i for i in range(7) if fl[i])][0],
           "sensor": opt[tuple(i for i in range(7) if fl[i])][1]} for fl in itertools.product((0, 1), repeat=7) if any(fl)]

    def build(belief):
        cost, s = opt[belief]
        if s is None:
            return {"class": belief[0], "cost": 0}
        return {"sensor": s, "cost": cost, "branches": {str(v): build(tuple(c for c in belief if S[c][s] == v)) for v in (0, 1)}}
    tree = build(tuple(range(7)))
    paths = []
    for cl in range(7):
        node, steps = tree, []
        while "sensor" in node:
            v = S[cl][node["sensor"]]
            steps.append({"sensor": node["sensor"], "reading": v})
            node = node["branches"][str(v)]
        paths.append({"class": cl, "steps": steps, "cost": len(steps), "leaf": node["class"]})
    noise = {}
    for g in ("erasure", "error"):
        words = next(s for s in suites if s["mask"] == winners[g]["mask"])["signatures"]
        rows = []
        for cl, w in enumerate(words):
            for pos in range(-1, len(w)):
                o = w if pos < 0 else w[:pos] + ("?" if g == "erasure" else "10"[int(w[pos])]) + w[pos + 1:]
                keep = [c for c, x in enumerate(words) if (all(a in ("?", b) for a, b in zip(o, x)) if g == "erasure"
                                                            else sum(a != b for a, b in zip(o, x)) <= 1)]
                rows.append({"class": cl, "position": pos, "observed": o, "decoded": keep})
        noise[g] = rows
    return {"classes": classes, "suites": suites, "winners": winners, "dp": dp, "tree": tree, "paths": paths, "noise": noise}


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def calls_of(src):
    calls, sources = [], None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D10_SOURCES":
            sources = ast.literal_eval(node.value)
    return calls, sources


def case_of(calls):
    names = [c[0] for c in calls]
    k = names.count("select")
    if names != ["select"] * k + ["fault"]:
        raise ValueError(f"atom order {names}")
    sel = [c[1] for c in calls[:k]]
    if sel != sorted(set(sel)) or any(s not in range(8) for s in sel) or calls[k][1] not in LABELS:
        raise ValueError(f"selection {sel} / label {calls[k][1]}")
    return f"S={''.join('1' if i in sel else '0' for i in range(8))}|H={calls[k][1]}", k


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    own = {f"S={format(i, '08b')}|H={f}": expect(format(i, "08b"), f) for i in range(256) for f in LABELS}
    expected_ids = sorted(own)
    rep.check("space.identities", len(expected_ids) == 3072 and expected_ids == sorted(frozen), {"masks": 256, "labels": 12})
    rep.check("space.frozen_equals_own_model", all(all(o[k] == frozen[c][k] for k in FIELDS) and frozen[c]["predicted_outcome"] == "PASS"
                                                   for c, o in own.items()))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_dependency_graph"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 3072] and c["mandatory"][:2] == ["EXACT", 3072] for c in cmp_["cardinality"].values())
              and all(ps["SENSORS"].get("mode") == "EXACT" and ps["SENSORS"].get("value") == 256 for ps in cmp_["per_slot"].values()),
              cmp_["cardinality"])
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    after = {int(m.group(1)): [int(m.group(2)), int(m.group(3))] for m in re.finditer(
        r"\[DIAG-PASS\] Sheet SENSORS \(key=\d+\) directive\[(\d+)\] AFTER: isCombi2=\S+ fw_rows=(\d+) fw2_rows=(\d+)", core_log)}
    final = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", core_log)}
    work = {"derived": {"first_pass": 256, "second_pass_emissions": 3 ** 8 - 1, "distinct": 256},
            "observed": {"first_pass_fw_rows": after.get(0, [None])[0], "second_pass_fw2_rows_before_distinct": after.get(1, [None, None])[1],
                         "final_after_distinct": final.get("SENSORS")},
            "other_sheets": {k: final.get(k) for k in ("FAULT", "TAIL")}}
    rep.check("core.sensors_subsets_chain", work["observed"] == {"first_pass_fw_rows": 256, "second_pass_fw2_rows_before_distinct": 6560,
                                                                "final_after_distinct": 256}
              and work["other_sheets"] == {"FAULT": 12, "TAIL": 1}, work)

    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    def cell(r, sheet):                         # explicit None test: an empty selection is [] and must not inherit the base
        v = r.get(cols[sheet])
        return list(base.get(cols[sheet]) or []) if v is None else list(v)
    decoded, bad_rows = [], []
    for r in frows:
        try:
            calls = []
            for sheet in ("SENSORS", "FAULT"):
                for code in cell(r, sheet):
                    calls.extend(calls_of(code2val[int(code)])[0])
            decoded.append(case_of(calls)[0])
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", all(v == 3072 for v in counts.values()), counts)
    ec = Counter(c.split("|")[0] for c in decoded)
    rep.check("identity.core", not bad_rows and sorted(decoded) == expected_ids and ec["S=00000000"] == 12 and ec["S=11111111"] == 12
              and sorted(cols) == sorted(["HEAD", "SENSORS", "FAULT", "TAIL"]) and cols.get("SENSORS", "").startswith("combos2_")
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()),
              {"bad_rows": bad_rows[:3], "empty_mask_rows": ec["S=00000000"], "full_mask_rows": ec["S=11111111"],
               "base_sensors": base.get(cols.get("SENSORS", ""))})

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
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids and empty_c == 12,
              {"errors": errs[:3], "empty_selection_candidates_without_select": empty_c})
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 3072 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    by_id = {r["case_id"]: r for r in records}
    rep.check("identity.executor", sorted(by_id) == expected_ids and len(records) == 3072)
    bad, nfields = [], 0
    for cid, r in by_id.items():
        if cid not in own:
            bad.append((cid, "unknown"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [("schema", r["schema"], "d10.observation/v1"), *[(k, r[k], o[k]) for k in FIELDS], *[(f"frozen_{k}", r[k], frozen[cid][k]) for k in FIELDS],
                  ("reference_readings", r["reference_readings"], o["readings"]), ("oracle_agrees", r["oracle_agrees"], True),
                  ("verdict", r["verdict"], "PASS"), ("fw_var", r["fw_var"], 0), ("metrics_fw_var", fw["metrics_fw_var"], 0),
                  ("outcome", fw["outcome"], "PASS"), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        nfields += len(checks)
        bad += [(cid, n, str(got)[:60], str(want)[:60]) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": nfields, "bad": bad[:6]})
    rep.check("observations.totals", Counter(r["verdict"] for r in records) == Counter({"PASS": 3072}) == Counter(derived["outcomes"]))

    # ---- diagnosis certificates from the observed matrix ----
    full = matrix_guard(records)
    cert = certificates(full) if full else None
    saved = json.loads((run / "diagnosis.json").read_text())
    pairs_ok = cert is not None and [c["members"] for c in cert["classes"][1:]] == [[f"F{2 * k - 1:02}", f"F{2 * k:02}"] for k in range(1, 7)]
    same = cert is not None and saved["suites"] == cert["suites"] == derived["suites"] and saved["winners"] == cert["winners"] == derived["winners"] \
        and saved["adaptive"]["dp"] == cert["dp"] == derived["adaptive"]["dp"] and saved["adaptive"]["tree"] == cert["tree"] == derived["adaptive"]["tree"] \
        and saved["noise"] == cert["noise"] == derived["noise"] \
        and [dict((k, p[k]) for k in ("class", "steps", "cost")) for p in cert["paths"]] == derived["adaptive"]["paths"] == saved["adaptive"]["paths"] \
        and [(c["class"], c["members"], c["signature"]) for c in cert["classes"]] == [(c["class"], c["members"], c["signature"]) for c in derived["classes"]]
    rep.check("diagnosis.from_observed_matrix", pairs_ok and same, {
        "classes": cert and [(c["class"], c["members"], "".join(map(str, c["signature"]))) for c in cert["classes"]],
        "winners": cert and {g: {k: v for k, v in w.items() if k != "minimum_cost_masks"} for g, w in cert["winners"].items()},
        "adaptive_cost": cert and cert["tree"]["cost"], "dp_entries": cert and len(cert["dp"])})
    if cert is None:
        rep.check("diagnosis.properties", False, "the observed-matrix guard refused the rows")
    else:
        paths_ok = all(p["leaf"] == p["class"] and len({s["sensor"] for s in p["steps"]}) == len(p["steps"]) for p in cert["paths"])
        noise_ok = all(r["decoded"] == [r["class"]] for g in cert["noise"] for r in cert["noise"][g])
        alias_zero = min(sum(x != y for x, y in zip(full[a], full[b])) for a, b in itertools.combinations(LABELS, 2)) == 0
        g = lambda c: by_id[c]["signature"]                                      # noqa: E731
        facts = {"detect_F01": g("S=00000011|H=F01"), "detect_F09": g("S=00000011|H=F09"), "separate_F01": g("S=00001111|H=F01"),
                 "separate_F09": g("S=00001111|H=F09"), "full_F01": g("S=11111111|H=F01"), "full_F02": g("S=11111111|H=F02"),
                 "empty_F01": [by_id["S=00000000|H=F01"]["readings"], g("S=00000000|H=F01"), by_id["S=00000000|H=F01"]["sensor_cost"]]}
        costs = {k: w["cost"] for k, w in cert["winners"].items()}
        rep.check("diagnosis.properties", paths_ok and noise_ok and alias_zero and costs == {"detect": 2, "separate": 4, "erasure": 6, "error": 7}
                  and cert["tree"]["cost"] == 3 and len(cert["dp"]) == 127 and len(cert["noise"]["erasure"]) == 49 and len(cert["noise"]["error"]) == 56
                  and facts["detect_F01"] == facts["detect_F09"] == "01" and facts["separate_F01"] == "1101" and facts["separate_F09"] == "0001"
                  and facts["full_F01"] == facts["full_F02"] and facts["empty_F01"] == [[], "", 0]
                  and saved["identify_examples"]["F02"] == {"class": 1, "members": ["F01", "F02"]},
                  {"facts": facts, "paths": [[(s["sensor"], s["reading"]) for s in p["steps"]] for p in cert["paths"]],
                   "noise_controls": {k: len(v) for k, v in cert["noise"].items()}, "unquotiented_label_min_distance": 0 if alias_zero else None})

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "3200", "--budget-final-candidates", "3200", "--budget-disk-bytes", "150000000",
                 "--budget-wall-time-seconds", "7200"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx", argv[2:])
    dbm = manifest["databases"]
    rep.check("envelope.db_and_retained_sizes", re.fullmatch(r"as0927_d10_[0-9a-z_]+", dbm["name"]) is not None
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
    return rep, {"stage_counts": {**counts, "sensors_work": work}, "totals": dict(Counter(r["verdict"] for r in records)),
                 "extra": {"winners": cert and cert["winners"], "adaptive_paths": cert and cert["paths"]}, "records": by_id}


def witnesses(run, data):
    out = []
    for case in WITNESSES:
        r = data["records"][case]
        out.append({"case_id": case, "candidate": r["framework"]["source_ref"], **{k: r[k] for k in FIELDS}, "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d10.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d10.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
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
