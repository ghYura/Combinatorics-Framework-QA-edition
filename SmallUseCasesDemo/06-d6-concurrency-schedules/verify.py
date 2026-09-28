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

"""Independent offline verifier for one D6 evidence directory (campaign counter or queue).

    python verify.py --run evidence/<run-id> [--inputs-root DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py or runtime.py, never connects to a database,
never executes a candidate (candidates and dictionary atoms are parsed with `ast`). Schedules,
local order, preemptions, enabledness, traces, verdicts and the bond truth tables are re-derived
here from CONTRACT.md and compared with the frozen predictions, the live sieve log, the decoded
Core rows, the rendered candidates and every observation record.
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
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
POLICIES = {"counter": ("atomic_commit", "split_rw"), "queue": ("actual_queue", "stale_empty")}
THREADS = {"counter": "AB", "queue": "PC"}
RULES = {"counter": ["two_each", "preemption_cap"], "queue": ["two_each", "producer_first"]}
EXPECTED = {"counter": 24, "queue": 6}
RAW = {"counter": 96, "queue": 32}
WITNESSES = {"counter": {"split_rw_CAP2_ABAB": "counter|split_rw|CAP=2|SEQ=ABAB",
                         "atomic_commit_CAP2_ABAB": "counter|atomic_commit|CAP=2|SEQ=ABAB",
                         "serial_control_split_rw_CAP0_AABB": "counter|split_rw|CAP=0|SEQ=AABB"},
             "queue": {"stale_empty_PCCP": "queue|stale_empty|SEQ=PCCP", "actual_queue_PCCP": "queue|actual_queue|SEQ=PCCP"}}
REPLAYED = {"counter": ["counter|split_rw|CAP=2|SEQ=ABAB", "counter|atomic_commit|CAP=2|SEQ=ABAB"],
            "queue": ["queue|stale_empty|SEQ=PCCP", "queue|actual_queue|SEQ=PCCP"]}


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


def sha256(b):
    return hashlib.sha256(b).hexdigest()


# ---- the contract, re-derived ----
def words(campaign):
    return ["".join(w) for w in itertools.product(THREADS[campaign], repeat=4)]


def two_each(w):
    return sorted(Counter(w).values()) == [2, 2]


def step_numbers(w):
    return [w[: i + 1].count(t) for i, t in enumerate(w)]


def preemptions(w):
    n = step_numbers(w)
    return sum(1 for i in range(3) if w[i] != w[i + 1] and n[i] == 1)


def switches(w):
    return sum(1 for i in range(3) if w[i] != w[i + 1])


def cap_expression(w):
    a = [1 if t == "A" else 0 for t in w]
    return int(a[0] != a[1]) + int(a[1] != a[2] and a[0] != a[1]) + int(a[2] != a[3] and a[0] != a[2] and a[1] != a[2])


def counter_model(w, policy):
    value, saved, trace, ref, writes = 0, {}, [], [], 0
    for t, n in zip(w, step_numbers(w)):
        if n == 1:
            saved[t] = value
            op = "read"
        else:
            value = (value if policy == "atomic_commit" else saved[t]) + 1
            op = "write"
            writes += 1
        trace.append({"thread": t, "op": op, "counter": value, "locals": dict(saved)})
        ref.append(writes)
    return trace, ref


def queue_model(w, policy):
    """(trace, reference trace, first disabled step on the reference)."""
    q, flag, res, trace = [], False, None, []
    rq, rres, ref = [], None, []
    for i, (t, n) in enumerate(zip(w, step_numbers(w)), start=1):
        if (t, n) == ("C", 1) and not rq:
            return None, None, i
        if (t, n) == ("P", 1):
            q.append("item"); rq.append("item"); op = "enqueue"
        elif (t, n) == ("P", 2):
            flag = bool(q); op = "publish"
        elif n == 1:
            op = "wait_readable"
        else:
            op = "try_pop"
            res = q.pop(0) if q and (policy == "actual_queue" or flag) else "EMPTY"
            rres = rq.pop(0) if rq else "EMPTY"
        trace.append({"thread": t, "op": op, "items": list(q), "published_nonempty": flag, "pop_result": res})
        ref.append({"items": list(rq), "pop_result": rres})
    return trace, ref, None


def bond_hits(campaign, cap, w):
    hits = []
    if w.count(THREADS[campaign][0]) != 2:
        hits.append("two_each")
    if campaign == "counter" and cap_expression(w) > cap:
        hits.append("preemption_cap")
    if campaign == "queue" and w[0] != "P":
        hits.append("producer_first")
    return hits


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    calls, sources, phase = [], None, None
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            calls.append([node.value.func.id, *[ast.literal_eval(a) for a in node.value.args]])
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D6_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase = ast.literal_eval(node.value.args[0])
    return calls, phase, sources


def case_of(campaign, calls):
    names = [c[0] for c in calls]
    want = ["impl"] + (["cap"] if campaign == "counter" else []) + ["set_step"] * 4
    if names != want or [c[1] for c in calls if c[0] == "set_step"] != [1, 2, 3, 4]:
        raise ValueError(f"atom order {names}")
    w = "".join(c[2] for c in calls if c[0] == "set_step")
    return (f"counter|{calls[0][1]}|CAP={calls[1][1]}|SEQ={w}" if campaign == "counter" else f"queue|{calls[0][1]}|SEQ={w}"), w


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    campaign = manifest["campaign"]
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived[f"{campaign}_cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    ws = words(campaign)
    caps = (0, 1, 2) if campaign == "counter" else (None,)

    # ---- the declared population, re-derived ----
    own = {}
    for cap in caps:
        for w in ws:
            if not two_each(w):
                continue
            if campaign == "counter":
                if preemptions(w) > cap:
                    continue
                for p in POLICIES[campaign]:
                    tr, ref = counter_model(w, p)
                    fails = [i + 1 for i, (o, e) in enumerate(zip(tr, ref)) if o["counter"] != e]
                    own[f"counter|{p}|CAP={cap}|SEQ={w}"] = {"policy": p, "cap": cap, "schedule": w, "trace": tr, "reference": ref, "failing": fails}
            else:
                if queue_model(w, "actual_queue")[2] is not None:
                    continue
                for p in POLICIES[campaign]:
                    tr, ref, _ = queue_model(w, p)
                    fails = [i + 1 for i, (o, e) in enumerate(zip(tr, ref)) if (o["items"], o["pop_result"]) != (e["items"], e["pop_result"])]
                    own[f"queue|{p}|SEQ={w}"] = {"policy": p, "cap": None, "schedule": w, "trace": tr, "reference": ref, "failing": fails}
    expected_ids = sorted(own)
    def frozen_ok(cid, o):
        f = frozen[cid]
        ref_f = [x["counter"] for x in f["reference_trace"]] if campaign == "counter" else \
            [{"items": x["items"], "pop_result": x["pop_result"]} for x in f["reference_trace"]]
        return (f["predicted_trace"] == o["trace"] and ref_f == o["reference"] and f["failing_checkpoints"] == o["failing"]
                and f["predicted_outcome"] == ("DOMAIN_FAIL" if o["failing"] else "PASS") and f["schedule"] == o["schedule"]
                and (campaign == "queue" or (f["cap"] == o["cap"] and f["preemptions"] == preemptions(o["schedule"])
                                              and f["context_switches"] == switches(o["schedule"]))))
    rep.check("space.frozen_equals_own_model", expected_ids == sorted(frozen) and all(frozen_ok(c, o) for c, o in own.items())
              and len(expected_ids) == EXPECTED[campaign], {"cases": len(expected_ids)})
    if campaign == "counter":
        by_cap = {c: sorted({o["schedule"] for o in own.values() if o["cap"] == c}) for c in caps}
        examples = {w: (switches(w), preemptions(w)) for w in ("AABB", "ABBA", "ABAB")}
        rep.check("schedule.preemption_expression_all_16_words", all(cap_expression(w) == preemptions(w) for w in ws)
                  and [len(by_cap[c]) for c in caps] == [2, 4, 6]
                  and examples == {"AABB": (1, 0), "ABBA": (2, 1), "ABAB": (3, 2)},
                  {"words": {w: [cap_expression(w), preemptions(w), switches(w)] for w in ws}, "schedules_by_cap": by_cap,
                   "contract_examples": examples})
    else:
        status = {w: ("malformed" if not two_each(w) else "disabled" if queue_model(w, "actual_queue")[2] else "feasible") for w in ws}
        feasible = sorted(w for w, s in status.items() if s == "feasible")
        rep.check("schedule.enabledness_exploration", feasible == ["PCCP", "PCPC", "PPCC"]
                  and feasible == sorted(w for w in ws if two_each(w) and w[0] == "P")
                  and {w: queue_model(w, "actual_queue")[2] for w, s in status.items() if s == "disabled"} == {"CCPP": 1, "CPCP": 1, "CPPC": 1}
                  and sorted(r["schedule"] for r in derived["queue_rejected"]) == ["CCPP", "CPCP", "CPPC"],
                  {"status": status, "feasible": feasible})

    # ---- bonds: own truth table over the raw product versus the live sieve log ----
    rows = [(p, cap, w) for p in POLICIES[campaign] for cap in caps for w in ws]
    hits = [bond_hits(campaign, cap, w) for _, cap, w in rows]
    per_rule = {r: sum(r in h for h in hits) for r in RULES[campaign]}
    seq, alive = [len(rows)], list(zip(rows, hits))
    for r in RULES[campaign]:
        alive = [x for x in alive if r not in x[1]]
        seq.append(len(alive))
    overlap = sum(len(h) > 1 for h in hits)
    kept = sorted(f"{campaign}|{p}|CAP={cap}|SEQ={w}" if campaign == "counter" else f"queue|{p}|SEQ={w}" for (p, cap, w), h in zip(rows, hits) if not h)
    log = (run / "logs" / "bundle_run.log").read_text(errors="replace")
    live = {m.group(1): int(m.group(2)) for m in re.finditer(r"rule (\S+): matched (\d+) row", log)}
    m = re.search(r"sieve: scanned (\d+), unique removals (\d+) \(overlap (\d+)\) → fw_final now (\d+)", log)
    line = [int(x) for x in m.groups()] if m else None
    pre = json.loads((root / "precheck" / f"{campaign}.json").read_text())
    truth = {"per_rule": per_rule, "overlap": overlap, "unique_removals": len(rows) - seq[-1], "sequential": seq}
    rep.check("sieve.truth_table_and_live_log", kept == expected_ids and live == per_rule
              and line == [RAW[campaign], len(rows) - seq[-1], overlap, EXPECTED[campaign]]
              and seq == [RAW[campaign], {"counter": 36, "queue": 12}[campaign], EXPECTED[campaign]]
              and pre["truth_table"] == {"raw": len(rows), **truth} and pre["framework_sieve_offline_agrees"],
              {"own": truth, "live_rules": live, "live_line": line})

    # ---- stages, Core rows and identities ----
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "sieve", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    card = cmp_["cardinality"]["xlsx"]
    rep.check("stage.plans", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == card and not any(cmp_["budget_blocking"].values())
              and card["mandatory"][:2] == ["EXACT", RAW[campaign]] and (card["final"][2] or 0) <= EXPECTED[campaign] <= card["final"][3] <= 150
              and cmp_["constraints_present"] == {"toml": 2, "xlsx": 2}, cmp_["cardinality"])
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    code2val = {int(r["bigint"]): r["value"].strip() for r in tables["NumberToValue1"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {mm.group(2): c for c in (frows or [{}])[0] for mm in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if mm}
    order = ["HEAD", "IMPL"] + (["CAP"] if campaign == "counter" else []) + ["S1", "S2", "S3", "S4", "TAIL"]
    decoded, bad_rows = [], []
    for r in frows:
        try:
            calls = []
            for sheet in order[1:-1]:
                (code,) = r.get(cols[sheet]) or base.get(cols[sheet])
                node = ast.parse(code2val[int(code)]).body[0].value
                calls.append([node.func.id, *[ast.literal_eval(a) for a in node.args]])
            decoded.append(case_of(campaign, calls)[0])
        except (ValueError, KeyError, SyntaxError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "post_sieve": count("sieve", "post_sieve"), "fw_final_rows": len(frows),
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", counts["core_fw_final"] == RAW[campaign] and counts["post_sieve"] == EXPECTED[campaign]
              and counts["fw_final_rows"] == counts["reader"] == counts["executor"] == counts["results_v2"] == EXPECTED[campaign], counts)
    rep.check("identity.core_after_sieve", not bad_rows and sorted(decoded) == expected_ids and set(cols) == set(order) and len(cols) == len(order)
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3], "columns": sorted(cols)})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            calls, phase, sources = parse_candidate(data.decode())
            cid, _ = case_of(campaign, calls)
            if phase != campaign:
                raise ValueError(f"phase {phase}")
        except (ValueError, SyntaxError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = cid
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == EXPECTED[campaign] and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    # ---- every record ----
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    bad, fields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_declared_population"))
            continue
        o, fw = own[cid], r["framework"]
        w = o["schedule"]
        verdict = "DOMAIN_FAIL" if o["failing"] else "PASS"
        checks = [("schema", r["schema"], "d6.observation/v1"), ("campaign", r["campaign"], campaign), ("policy", r["policy"], o["policy"]),
                  ("schedule", r["schedule"], w), ("local_steps", r["local_steps"], [f"{t}{n}" for t, n in zip(w, step_numbers(w))]),
                  ("context_switches", r["context_switches"], switches(w)), ("preemptions", r["preemptions"], preemptions(w)),
                  ("observed_trace", r["observed_trace"], o["trace"]), ("frozen_trace", r["observed_trace"], frozen[cid]["predicted_trace"]),
                  ("failing_checkpoints", r["failing_checkpoints"], o["failing"]), ("verdict", r["verdict"], verdict),
                  ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("fw_var", r["fw_var"], 0 if verdict == "PASS" else 2),
                  ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], verdict),
                  ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("source_sha256", r["source_sha256"], module_sha),
                  ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])), ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        if campaign == "counter":
            checks += [("cap", r["cap"], o["cap"]), ("reference_counters", r["reference_counters"], o["reference"]),
                       ("within_cap", r["preemptions"] <= r["cap"], True)]
        else:
            checks += [("reference_trace", r["reference_trace"], o["reference"]), ("enabled_on_reference", r["enabled_on_reference"], [True] * 4)]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES[campaign]}
    extra = {}
    if campaign == "counter":
        per_cap = {c: dict(Counter(r["verdict"] for r in records.values() if r["cap"] == c)) for c in caps}
        per_cap_schedules = {c: len({r["schedule"] for r in records.values() if r["cap"] == c}) for c in caps}
        want_cap = {0: {"PASS": 4}, 1: {"PASS": 6, "DOMAIN_FAIL": 2}, 2: {"PASS": 8, "DOMAIN_FAIL": 4}}
        extra.update(per_cap=per_cap, per_cap_distinct_schedules=per_cap_schedules,
                     distinct_schedules_overall=len({r["schedule"] for r in records.values()}))
        rep.check("observations.per_cap", per_cap == want_cap and per_cap_schedules == {0: 2, 1: 4, 2: 6}
                  and all(r["verdict"] == "PASS" for r in records.values() if r["policy"] == "atomic_commit")
                  and {r["schedule"] for r in records.values() if r["policy"] == "split_rw" and r["verdict"] == "DOMAIN_FAIL"} == {"ABAB", "ABBA", "BAAB", "BABA"},
                  extra)
    else:
        rep.check("observations.infeasible_excluded", not any(w in cid for cid in list(records) + decoded for w in ("CCPP", "CPCP", "CPPC"))
                  and {cid for cid, r in records.items() if r["verdict"] == "DOMAIN_FAIL"} == {"queue|stale_empty|SEQ=PCCP"},
                  {"excluded": ["CCPP", "CPCP", "CPPC"], "domain_fail": sorted(c for c, r in records.items() if r["verdict"] == "DOMAIN_FAIL")})
    rep.check("observations.totals", dict(totals) == derived["outcomes"][campaign], {"totals": dict(totals), "by_policy": by_policy})

    need_args = ["--lang", "py", "--sieve", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "150", "--budget-final-candidates", "150", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "600"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx" and Path(argv[2]).parent.name == campaign, argv[2:])
    rep.check("envelope.db", re.fullmatch(rf"as0927_d6{campaign}_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    side = root / "spec" / campaign / "demo.constraints.json"
    run_json = json.loads((run / "run" / "run.json").read_text())
    chain = {sha256((run / "inputs" / "demo.constraints.json").read_bytes()), run_json.get("constraints_sidecar_sha256"),
             sha256((run / "run" / "wb__demo.constraints.json").read_bytes())}
    rep.check("provenance.companion_chain", chain == {sha256(side.read_bytes())}
              and json.loads((run / "run" / "sidecar.json").read_text())["constraints"] == json.loads(side.read_text())["constraints"])
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(root / "spec" / campaign / "demo.xlsx")["sheets"])
    return rep, {"campaign": campaign, "stage_counts": {**counts, "sieve_rules": live, "sieve_line": line, "truth": truth},
                 "totals": dict(totals), "by_policy": by_policy, "extra": extra, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES[data["campaign"]].items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "schedule": r["schedule"],
                    "preemptions": r["preemptions"], "context_switches": r["context_switches"], "observed_trace": r["observed_trace"],
                    "failing_checkpoints": r["failing_checkpoints"], "verdict": r["verdict"],
                    "replay": (f"python replay.py --run evidence/{run.name} --case '{case}'" if case in REPLAYED[data["campaign"]]
                               else "not replayed: shown from its original observation")})
    return {"schema": "d6.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d6.verification/v1", "run": run.name, "campaign": data["campaign"], "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES[data["campaign"]].values()):
        w = witnesses(run, data)
        (out_dir / "witnesses.json").write_text(json.dumps(w, indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
