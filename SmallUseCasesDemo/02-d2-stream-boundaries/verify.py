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

"""Independent offline verifier for one D2 campaign evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: no import of sut.py, oracle.py or runtime.py, no database, no candidate
execution (candidates are parsed with `ast`; inlined sources are hashed). Expected identities
come from an independent enumeration of real cut subsets; literal references come straight
from architect-derived.json; adapter outcomes come from this file's own decoding code.
"""
import argparse
import ast
import codecs
import gzip
import hashlib
import io
import itertools
import json
import re
import sys
import tarfile
import tomllib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
ADAPTERS = ("incremental", "per_chunk", "no_final")
POLICIES = ("strict", "replace")
PREDICTED = {"incremental": {"none": 160}, "per_chunk": {"none": 52, "unexpected_rejection": 47, "wrong_text": 61},
             "no_final": {"none": 120, "unexpected_acceptance": 20, "wrong_text": 20}}      # CONTRACT table
RULE_MATCHES = {f"real_boundary_{i}": m for i, m in zip(range(1, 6), (0, 0, 192, 288, 480))}
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")


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


def cid(adapter, payload, errors, mask):
    return f"{adapter}|P={payload}|E={errors}|M={mask:02x}"


# ---- independent structure -------------------------------------------------------------------
def real_masks(n):
    """Masks whose set bits are real cut points 1..n-1 (bit i-1 = a cut after byte i)."""
    out = []
    for cuts in itertools.chain.from_iterable(itertools.combinations(range(1, min(n, 6)), k) for k in range(6)):
        out.append(sum(1 << (c - 1) for c in cuts))
    return sorted(set(out))


def expected_identities(payloads):
    return sorted(cid(a, p, e, m) for a in ADAPTERS for p, v in payloads.items()
                  for e in POLICIES for m in real_masks(len(bytes.fromhex(v["hex"]))))


# ---- this file's own decoding (not the SUT's code) -------------------------------------------
def decode_whole(data, enc, errors):
    try:
        return True, data.decode(enc, errors)
    except UnicodeError as exc:
        return False, type(exc).__name__


def adapter_outcome(adapter, chunks, enc, errors):
    try:
        if adapter == "per_chunk":
            parts = [str(c, enc, errors) for c in chunks]
            return True, "".join(parts)
        dec = codecs.lookup(enc).incrementaldecoder(errors)
        parts = [dec.decode(c) for c in chunks]          # final defaults to False
        if adapter == "incremental":
            parts.append(dec.decode(b"", True))
        return True, "".join(parts)
    except UnicodeError as exc:
        return False, type(exc).__name__


def split(data, mask):
    edges = [0] + [i for i in range(1, 6) if mask >> (i - 1) & 1] + [len(data)]
    return [data[a:b] for a, b in zip(edges, edges[1:])]


def read_candidates(tar_path: Path):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tar_path.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src: str):
    vals, sources, tail = {}, None, False
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("IMPL", "PAYLOAD", "ERRORS", "CUT1", "CUT2", "CUT3", "CUT4", "CUT5"):
                if name in vals:
                    raise ValueError(f"{name} assigned twice")
                vals[name] = ast.literal_eval(node.value)
            elif name == "_D2_SOURCES":
                sources = ast.literal_eval(node.value)
            elif name == "_verdict":
                tail = True
    if len(vals) != 8:
        raise ValueError(f"incomplete assignment set {sorted(vals)}")
    mask = sum(vals[f"CUT{i}"] << (i - 1) for i in range(1, 6))
    return cid(vals["IMPL"], vals["PAYLOAD"], vals["ERRORS"], mask), sources, tail


def verify(run: Path, root: Path = HERE):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    payloads = derived["payloads"]
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}

    # 1. structure and bonds -----------------------------------------------------------------
    expected = expected_identities(payloads)
    segs = {p: len(real_masks(len(bytes.fromhex(v["hex"])))) for p, v in payloads.items()}
    rep.check("space.segmentations", segs == {p: v["segmentations"] for p, v in payloads.items()} and sum(segs.values()) == 80, segs)
    rep.check("space.expected_480_equals_architect", len(expected) == 480 and expected == sorted(derived["expected_case_ids"]))
    spec = tomllib.loads((root / "spec" / "spec.toml").read_text())
    side = json.loads((root / "spec" / "demo.constraints.json").read_text())
    vals = {s["sheet"]: s["values"] for s in spec["slots"]}
    rep.check("spec.sheet_order", [s["sheet"] for s in spec["slots"]] ==
              ["HEAD", "IMPL", "PAYLOAD", "ERRORS", "CUT1", "CUT2", "CUT3", "CUT4", "CUT5", "TAIL"])
    rep.check("spec.catalogue", [ast.literal_eval(v.split("=", 1)[1].strip()) for v in vals["IMPL"]] == list(ADAPTERS)
              and [ast.literal_eval(v.split("=", 1)[1].strip()) for v in vals["PAYLOAD"]] == list(payloads)
              and [ast.literal_eval(v.split("=", 1)[1].strip()) for v in vals["ERRORS"]] == list(POLICIES)
              and all(vals[f"CUT{i}"] == [f"CUT{i} = 0", f"CUT{i} = 1"] for i in range(1, 6)))
    want_params = {"PAYLOAD": {f'PAYLOAD = "{p}"': {"n": len(bytes.fromhex(v["hex"]))} for p, v in payloads.items()},
                   **{f"CUT{i}": {f"CUT{i} = {b}": {"bit": b} for b in (0, 1)} for i in range(1, 6)}}
    rep.check("spec.params_n_and_bit", side["params"] == want_params, side["params"].get("PAYLOAD"))
    rules = side["constraints"]
    rep.check("spec.five_require_bonds", [(c["id"], c["polarity"], c["sheets"], c["when"]) for c in rules] ==
              [(f"real_boundary_{i}", "require", ["PAYLOAD", f"CUT{i}"], f"CUT{i}.bit == 0 or PAYLOAD.n > {i}")
               for i in range(1, 6)])
    ns = {p: len(bytes.fromhex(v["hex"])) for p, v in payloads.items()}
    raw = list(itertools.product(ADAPTERS, payloads, POLICIES, range(32)))
    matched, alive, seq, overlap = Counter(), 0, [len(raw)], 0
    survivors = list(raw)
    for i in range(1, 6):                       # rule i forbids CUTi=1 when n <= i (own reading)
        survivors = [r for r in survivors if not (r[3] >> (i - 1) & 1 and ns[r[1]] <= i)]
        seq.append(len(survivors))
    for r in raw:
        hits = [i for i in range(1, 6) if r[3] >> (i - 1) & 1 and ns[r[1]] <= i]
        for i in hits:
            matched[f"real_boundary_{i}"] += 1
        overlap += len(hits) > 1
    truth = {"raw": len(raw), "matched": {k: matched[k] for k in RULE_MATCHES}, "sequential": seq,
             "overlap": overlap, "retained": seq[-1]}
    rep.check("sidecar.truth_table", truth["matched"] == RULE_MATCHES and seq == derived["sequential_survivors"]
              and seq[-1] == 480 and sorted(cid(*r) for r in survivors) == expected, truth)

    # 2. stages ------------------------------------------------------------------------------
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    plans = {k: json.loads((run / f"plan-{k}" / "plan.json").read_text()) for k in ("toml", "xlsx")}
    rep.check("stage.plans_exact_1152_480", all(
        (p["cardinality"]["mandatory"]["mode"], p["cardinality"]["mandatory"]["value"], p["cardinality"]["final"]["mode"],
         p["cardinality"]["final"]["value"], p["constraints_present"]) == ("EXACT", 1152, "EXACT", 480, 5)
        for p in plans.values()))
    rep.check("stage.plans_same_program", json.loads((run / "plan-comparison.json").read_text())["same_dependency_graph"])
    log = (run / "logs" / "bundle_run.log").read_text(errors="replace")
    sieve = {m.group(1): int(m.group(2)) for m in re.finditer(r"rule (\S+): matched (\d+) row", log)}
    m = re.search(r"sieve: scanned (\d+), unique removals (\d+) \(overlap (\d+)\) → fw_final now (\d+)", log)
    line = [int(x) for x in m.groups()] if m else None
    db = json.loads((run / "db-export.json").read_text())
    counts = {"core_fw_final": count("core", "fw_final"), "sieve_rules": sieve, "sieve_line": line,
              "fw_final_rows": len(db["main_db"]["fw_final_after_sieve"]), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.core_1152", counts["core_fw_final"] == 1152, counts["core_fw_final"])
    rep.check("stage.sieve", {k: sieve.get(k, 0) for k in RULE_MATCHES} == RULE_MATCHES
              and line == [1152, 672, overlap, 480], {"rules": sieve, "line": line, "expected_overlap": overlap})
    rep.check("stage.480_through_reader_executor", counts["fw_final_rows"] == counts["reader"] == counts["executor"]
              == counts["results_v2"] == 480, counts)
    code2val = {int(r["bigint"]): (r["value"] or "").strip() for r in db["main_db"]["NumberToValue1"]}
    base = (next(iter(db["main_db"]["fw_final_base_tables"].values()), [{}]) or [{}])[0]
    col = {c.split("_", 1)[1]: c for c in (db["main_db"]["fw_final_after_sieve"] or [{}])[0] if c.startswith("combos") and "_" in c}
    decoded = []
    for row in db["main_db"]["fw_final_after_sieve"]:
        v = {s: code2val[int((row.get(col[s]) or base.get(col[s]))[0])] for s in
             ("IMPL", "PAYLOAD", "ERRORS", "CUT1", "CUT2", "CUT3", "CUT4", "CUT5")}
        lit = {s: ast.literal_eval(x.split("=", 1)[1].strip()) for s, x in v.items()}
        decoded.append(cid(lit["IMPL"], lit["PAYLOAD"], lit["ERRORS"], sum(lit[f"CUT{i}"] << (i - 1) for i in range(1, 6))))
    rep.check("identity.core_after_sieve", sorted(decoded) == expected, {"dups": [k for k, n in Counter(decoded).items() if n > 1][:3]})

    # 3. Reader and Executor identity sets ---------------------------------------------------
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, head_ok, tail_ok, errs = {}, True, True, []
    for name, data in cands.items():
        try:
            ident, sources, tail = parse_candidate(data.decode())
        except (ValueError, SyntaxError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = ident
        head_ok &= sources is not None and {k: sha256(s.encode()) for k, s in sources.items()} == module_sha
        tail_ok &= tail
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected, errs[:3])
    rep.check("reader.inlined_sources_and_tail", head_ok and tail_ok, module_sha)
    rv2 = db["results_db"]["results_v2"]
    by_rv2 = {r["candidate_id"]: r for r in rv2}
    rep.check("executor.one_attempt_each", len(by_rv2) == 480 and all(r["attempt"] == 1 and r["repeat_idx"] == 0
              and r["run_id"] == run_id for r in rv2) and sorted(f"{k}.py" for k in by_rv2) == sorted(cands))
    outcomes = Counter(r["outcome"] for r in rv2)
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD)
              and "container" in (summary.get("sandbox_backend") or ""), {"outcomes": dict(outcomes), "backend": summary.get("sandbox_backend")})

    # 4. every record against the independent checker ----------------------------------------
    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    rep.check("identity.executor", sorted(r["case_id"] for r in records) == expected)
    literal_ok, bad, fields, table, pythons = True, [], 0, Counter(), Counter()
    for p, v in payloads.items():                                  # literal references first
        for e in POLICIES:
            ok, text = decode_whole(bytes.fromhex(v["hex"]), v["encoding"], e)
            want_reject = p.startswith("truncated") and e == "strict"
            literal_ok &= (not ok) if want_reject else (ok and text == v["literal_text"])
    rep.check("reference.whole_stream_equals_literals", literal_ok)
    for r in records:
        p = payloads[r["payload"]]
        data, mask = bytes.fromhex(p["hex"]), int(r["mask"], 16)
        chunks = split(data, mask)
        want_reject = r["payload"].startswith("truncated") and r["errors"] == "strict"
        ref = {"accepted": False, "text": None} if want_reject else {"accepted": True, "text": p["literal_text"]}
        ok, val = adapter_outcome(r["adapter"], chunks, p["encoding"], r["errors"])
        if not ref["accepted"]:
            cls = "none" if not ok else "unexpected_acceptance"
        else:
            cls = "unexpected_rejection" if not ok else ("none" if val == ref["text"] else "wrong_text")
        fw = r["framework"]
        row = by_rv2.get(fw["candidate_id"], {})
        checks = [("payload_hex", r["payload_hex"], p["hex"]), ("encoding", r["encoding"], p["encoding"]),
                  ("bits", r["bits"], [mask >> i & 1 for i in range(5)]), ("chunks", r["chunks_hex"], [c.hex() for c in chunks]),
                  ("chunks_rebuild", b"".join(bytes.fromhex(c) for c in r["chunks_hex"]), data),
                  ("chunks_nonempty", all(r["chunks_hex"]), True),
                  ("ref.accepted", r["reference"]["accepted"], ref["accepted"]), ("ref.text", r["reference"]["text"], ref["text"]),
                  ("obs.accepted", r["observed"]["accepted"], ok),
                  ("obs.text", r["observed"]["text"], val if ok else None),
                  ("obs.error", r["observed"]["error"], None if ok else val),
                  ("failure_class", r["failure_class"], cls),
                  ("verdict", r["verdict"], "PASS" if cls == "none" else "DOMAIN_FAIL"),
                  ("fw_var", r["fw_var"], 0 if cls == "none" else 2), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("results_v2.outcome", row.get("outcome"), r["verdict"]), ("results_v2.code", row.get("verdict_code"), r["fw_var"]),
                  ("rendered", rendered.get(fw["source_ref"]), r["case_id"]),
                  ("candidate_sha", fw["source_sha256"], sha256(cands.get(fw["source_ref"], b""))),
                  ("source_sha", r["source_sha256"], module_sha), ("run_id", fw["run_id"], run_id)]
        fields += len(checks)
        wrong = [n for n, got, want in checks if got != want]
        if wrong:
            bad.append({"case": r["case_id"], "fields": wrong})
        table[(r["adapter"], r["failure_class"])] += 1
        pythons[r["python"]] += 1
    rep.check("observations.every_field", not bad, {"fields": fields, "bad": bad[:8]})
    got = {a: {c: table[(a, c)] for (aa, c) in table if aa == a} for a in ADAPTERS}
    rep.check("observations.adapter_table", got == PREDICTED, got)
    totals = Counter(r["verdict"] for r in records)
    rep.check("observations.totals_332_148", totals == Counter({"PASS": 332, "DOMAIN_FAIL": 148}), dict(totals))

    # 5. envelope and provenance -------------------------------------------------------------
    need = ["--sieve", "--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1",
            "--executor-workers", "1", "--budget-mandatory-rows", "2000", "--budget-final-candidates", "600",
            "--budget-disk-bytes", "200000000", "--budget-wall-time-seconds", "1200"]
    rep.check("envelope.command", all(t in argv for t in need) and Path(argv[2]).name == "demo.xlsx"
              and "--override-budget" not in argv, argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d2_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    run_json = json.loads((run / "run" / "run.json").read_text())
    stage_gen = json.loads((run / "run" / "stages" / "gen.json").read_text())
    side_sha = sha256((root / "spec" / "demo.constraints.json").read_bytes())
    chain = {"inputs copy": sha256((run / "inputs" / "demo.constraints.json").read_bytes()),
             "plan-xlsx": (plans["xlsx"].get("constraints_source") or {}).get("sha256"),
             "run.json": run_json.get("constraints_sidecar_sha256"),
             "gen artifact": next((a["sha256"] for a in stage_gen["artifacts"] if a["kind"] == "input.constraints_sidecar"), None),
             "run wb copy": sha256((run / "run" / "wb__demo.constraints.json").read_bytes())}
    rep.check("provenance.companion_chain", set(chain.values()) == {side_sha}, chain)
    rep.check("provenance.sieve_record_equals_companion", json.loads((run / "run" / "sidecar.json").read_text()) == side)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items()
             if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    core_books = sorted((run / "run").glob("core_input__*.xlsx"))
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    same = bool(core_books) and fg.workbook_to_json(core_books[0])["sheets"] == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"]
    rep.check("provenance.core_workbook_equals_demo_xlsx", same)
    return rep, {"stage_counts": counts, "truth": truth, "adapter_table": got, "totals": dict(totals),
                 "python_in_candidates": dict(pythons), "records": records}


WITNESSES = {
    "valid_multibyte_split_incremental": "incremental|P=euro|E=strict|M=02",
    "per_chunk_failure_on_that_split": "per_chunk|P=euro|E=strict|M=02",
    "missing_eof_strict_no_cuts": "no_final|P=truncated_utf8|E=strict|M=00",
    "missing_eof_replace_no_cuts": "no_final|P=truncated_utf8|E=replace|M=00",
    "positive_control_eof_rejected": "incremental|P=truncated_utf8|E=strict|M=00",
}


def witnesses(run: Path, data):
    recs = {r["case_id"]: r for r in data["records"]}
    out = {}
    for label, case in WITNESSES.items():
        r = recs[case]
        out[label] = {"case_id": case, "candidate": r["framework"]["source_ref"], "chunks_hex": r["chunks_hex"],
                      "reference": r["reference"], "observed": r["observed"], "failure_class": r["failure_class"],
                      "verdict": r["verdict"], "framework_outcome": r["framework"]["outcome"],
                      "replay": f"python replay.py --run {run.relative_to(HERE)} --case '{case}'"}
    return {"schema": "d2.witnesses/v1", "run": run.name, "witnesses": [dict(label=k, **v) for k, v in out.items()]}


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
    doc = {"schema": "d2.verification/v1", "run": run.name, "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()),
           "host_python": sys.version.split()[0], "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "truth", "adapter_table", "totals", "python_in_candidates")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if sorted(r["case_id"] for r in data["records"]) == expected_identities(
            json.loads((a.inputs_root / "architect-derived.json").read_text())["payloads"]):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
