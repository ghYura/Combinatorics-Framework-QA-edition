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


"""Independent offline verifier for one D15 evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports worker.py, harness.py, oracle.py, runtime.py, preflight.py or derive.py,
never connects to a database, never executes a candidate (candidates are parsed with `ast`; the packed
HEAD sources are decoded with base64 + zlib). The finite transition model (attempts, every snapshot,
acknowledged operations, the seven checks), the bond's truth over all 336 raw rows, the rejected identities
and every persisted WAL payload are rebuilt or re-checked here from CONTRACT.md and compared with the frozen
predictions, the live sieve log, the decoded Core rows (native FW_Subsets FAIL rows), the rendered candidates,
worker provenance and every observation record.
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
import zlib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
IMPLS = ("durable", "volatile_ack", "replay_twice")
SUBSETS = [list(c) for k in (1, 2, 3) for c in itertools.combinations(range(3), k)]
SHEETS = ("HEAD", "IMPL", "FAIL", "CUT", "KIND", "RETRY", "TAIL")
MODULES = ("worker", "harness", "oracle", "runtime")
RAW, EXPECTED = 336, 312
RULE = "nontrivial_partition"
DELTA = {"o1": 1, "o2": 10, "o3": 100}
CHECKS = ("all_logical_ops_acknowledged", "acknowledged_survive_repair", "acknowledged_effects_once", "accepted_logical_ops_once",
          "replicas_agree", "matches_fault_free_reference", "final_wal_matches_accepted")
SEMANTIC_KEYS = ("id", "policy", "failed", "cut", "kind", "retry", "attempts", "trace", "acknowledged", "checks", "verdict")
REC_KEYS = sorted(["schema", "contract", *SEMANTIC_KEYS, "semantic_sha256", "fail_rendered", "fw_var", "carrier_slot", "wal_evidence",
                   "final_payloads", "provenance", "source_sha256", "framework"])
BUDGET_ARGS = ["--budget-mandatory-rows", "400", "--budget-final-candidates", "400", "--budget-disk-bytes", "200000000",
               "--budget-wall-time-seconds", "1200"]
WITNESSES = {
    "durable_stable_partial_quorum_converges": "P=durable|F=01|C=1|K=crash|R=stable",
    "durable_fresh_key_duplicates_uncertain_op": "P=durable|F=01|C=1|K=partition|R=fresh",
    "volatile_ack_loses_acknowledged_work": "P=volatile_ack|F=012|C=2|K=crash|R=stable",
    "replay_twice_single_node_double_effects": "P=replay_twice|F=0|C=3|K=crash|R=stable",
    "replay_twice_uniform_wrong_state_agrees": "P=replay_twice|F=012|C=3|K=crash|R=stable",
}


def jsonable(v):
    if isinstance(v, dict):
        return {(k if isinstance(k, str) else "/".join(map(str, k)) if isinstance(k, tuple) else str(k)): jsonable(x) for k, x in v.items()}
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


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ---- the contract, re-derived (from CONTRACT.md, not from the implementation) ----
def case_id(p, f, c, k, r):
    return f"P={p}|F={''.join(map(str, f))}|C={c}|K={k}|R={r}"


def transitions(impl, failed, cut, kind, retry):
    """CONTRACT.md's seven steps as a pure state machine."""
    live = {n: True for n in range(3)}
    gen = {n: 0 for n in range(3)}
    keys = {n: [] for n in range(3)}          # accepted keys in acceptance order
    log = {n: [] for n in range(3)}           # WAL keys in file order
    eff = {n: [] for n in range(3)}           # logical ops in application order
    blocked, attempts, trace = set(), [], []

    def put(n, key):
        if key in keys[n]:
            return
        if impl in ("durable", "replay_twice"):
            log[n].append(key)
        keys[n].append(key)
        eff[n].append(key.split(":")[0])

    def flush(n):
        for key in keys[n]:
            if key not in log[n]:
                log[n].append(key)

    def write(i, phase, tag="a1"):
        key = f"o{i}:{tag}"
        targets = [n for n in range(3) if live[n] and n not in blocked]
        for n in targets:
            put(n, key)
        attempts.append({"op": f"o{i}", "key": key, "phase": phase, "targets": targets, "status": "ACK" if len(targets) >= 2 else "TIMEOUT"})
        return attempts[-1]["status"]

    def snap(label):
        out = []
        for n in range(3):
            if live[n]:
                counts = {op: eff[n].count(op) for op in DELTA}
                out.append({"node": n, "running": True, "reachable": n not in blocked, "generation": gen[n], "accepted": sorted(keys[n]),
                            "wal": list(log[n]), "effects": list(eff[n]), "counts": counts, "value": sum(DELTA[o] * c for o, c in counts.items())})
            else:
                out.append({"node": n, "running": False, "reachable": False, "generation": gen[n], "accepted": None, "wal": list(log[n]),
                            "effects": None, "counts": None, "value": None})
        trace.append({"checkpoint": label, "nodes": out})

    snap("initial")
    for i in range(1, cut + 1):
        write(i, "prefix")
    snap("prefix")
    blocked = set(failed)
    if kind == "crash":
        for n in failed:
            live[n], keys[n], eff[n] = False, [], []
    snap("faulted")
    timed_out = False
    if cut < 3:
        timed_out = write(cut + 1, "window") == "TIMEOUT"
        snap("window")
    if kind == "crash":
        for n in failed:
            live[n], gen[n], keys[n] = True, 1, list(dict.fromkeys(log[n]))
            eff[n] = [k.split(":")[0] for k in log[n]] * (2 if impl == "replay_twice" else 1)
    blocked = set()
    snap("reopened")
    union = sorted(set(k for n in range(3) for k in keys[n]))
    for n in range(3):
        for key in union:
            put(n, key)
        flush(n)
    snap("repaired")
    early = sorted({a["op"] for a in attempts if a["status"] == "ACK"})
    if timed_out:
        write(cut + 1, "retry", "a1" if retry == "stable" else "a2")
        snap("retry")
    for i in range(cut + 2, 4):
        write(i, "suffix")
    for n in range(3):
        flush(n)
    snap("final")
    fin = trace[-1]["nodes"]
    rep = next(t["nodes"] for t in trace if t["checkpoint"] == "repaired")
    acked = sorted({a["op"] for a in attempts if a["status"] == "ACK"})
    one = {op: 1 for op in DELTA}
    checks = {"all_logical_ops_acknowledged": acked == sorted(DELTA),
              "acknowledged_survive_repair": all(s["counts"][o] >= 1 for s in rep for o in early),
              "acknowledged_effects_once": all(s["counts"][o] == 1 for s in fin for o in acked),
              "accepted_logical_ops_once": all(Counter(k.split(":")[0] for k in s["accepted"]) == one for s in fin),
              "replicas_agree": all((s["accepted"], s["counts"], s["value"]) == (fin[0]["accepted"], fin[0]["counts"], fin[0]["value"]) for s in fin),
              "matches_fault_free_reference": all(s["counts"] == one and s["value"] == 111 for s in fin),
              "final_wal_matches_accepted": all(len(s["wal"]) == len(set(s["wal"])) and sorted(s["wal"]) == s["accepted"] for s in fin)}
    return {"id": case_id(impl, failed, cut, kind, retry), "policy": impl, "failed": failed, "cut": cut, "kind": kind, "retry": retry,
            "attempts": attempts, "trace": trace, "acknowledged": acked, "checks": checks,
            "verdict": "PASS" if all(checks.values()) else "DOMAIN_FAIL"}


def bond(failed, kind):
    return kind == "partition" and len(failed) == 3


def record_of(key):
    op = key.split(":")[0]
    return {"key": key, "op": op, "delta": DELTA[op]}


def record_problems(r, o):
    """[(field, observed, expected)] for the semantic fields, the digest, WAL evidence, payloads and provenance."""
    checks = [(k, r.get(k), o[k]) for k in SEMANTIC_KEYS]
    checks += [("schema", r.get("schema"), "d15.observation/v1"), ("contract", r.get("contract"), "v1"),
               ("fw_var", r.get("fw_var"), 0 if o["verdict"] == "PASS" else 2),
               ("carrier_slot", r.get("carrier_slot"), "IMPL position 2 (legacy positional, not causal)"),
               ("semantic_sha256", r.get("semantic_sha256"), sha256(canon({k: r.get(k) for k in SEMANTIC_KEYS}).encode("ascii"))),
               ("fail_rendered", r.get("fail_rendered"), o["failed"])]
    final = o["trace"][-1]["nodes"]
    for n in range(3):
        ev = (r.get("wal_evidence") or {}).get(f"n{n}") or {}
        lines = ev.get("lines") or []
        want_lines = [canon(record_of(k)) for k in final[n]["wal"]]
        checks += [(f"wal.n{n}.lines", lines, want_lines),
                   (f"wal.n{n}.sha256", ev.get("sha256"), sha256("".join(l + "\n" for l in want_lines).encode("utf-8")))]
        pay = [p for p in (r.get("final_payloads") or []) if p.get("node") == n]
        want_acc = [record_of(k) for k in final[n]["accepted"]]
        checks += [(f"payload.n{n}.accepted", pay[0]["accepted"] if pay else None, want_acc),
                   (f"payload.n{n}.wal", pay[0]["wal"] if pay else None, [record_of(k) for k in final[n]["wal"]])]
    prov = r.get("provenance") or {}
    events = prov.get("events") or []
    crashed = o["failed"] if o["kind"] == "crash" else []
    starts = [(e.get("node"), e.get("generation")) for e in events if e.get("event") == "start"]
    kills = [(e.get("node"), e.get("returncode"), e.get("signal")) for e in events if e.get("event") == "kill"]
    exits = [(e.get("node"), e.get("returncode")) for e in events if e.get("event") == "exit"]
    pids = [e.get("pid") for e in events if e.get("event") == "start"]
    checks += [("prov.starts", starts, [(n, 0) for n in range(3)] + [(n, 1) for n in crashed]),
               ("prov.kills", kills, [(n, -9, "SIGKILL") for n in crashed]),
               ("prov.exits", sorted(exits), [(n, 0) for n in range(3)]),
               ("prov.counts", (prov.get("worker_starts"), prov.get("injected_kills")), (3 + len(crashed), len(crashed))),
               ("prov.distinct_int_pids", all(type(p) is int for p in pids) and len(set(pids)) == len(pids), True),
               ("prov.argv", all(e["argv"][1:3] == ["-u", prov.get("worker_script")] and e["argv"][3:6] == [str(e["node"]), str(e["generation"]), o["policy"]]
                                 and e["argv"][6].endswith(f"n{e['node']}.wal") for e in events if e.get("event") == "start"), True),
               ("prov.kill_pid_is_live_generation", all(any(s.get("event") == "start" and s["pid"] == k["pid"] and s["generation"] == k["generation"]
                                                            for s in events) for k in events if k.get("event") == "kill"), True)]
    return checks


# ---- rendered candidates and Core rows ----
def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def atom(text):
    node = ast.parse(text).body
    if len(node) != 1 or not isinstance(node[0], ast.Expr) or not isinstance(node[0].value, ast.Call):
        raise ValueError(f"not one call: {text!r}")
    call = node[0].value
    if call.keywords or not isinstance(call.func, ast.Name) or len(call.args) != 1:
        raise ValueError(f"unexpected call form: {text!r}")
    return [call.func.id, ast.literal_eval(call.args[0])]


def case_of(calls):
    """Identity from impl, the rendered fail atoms, cut, fault and retry, in slot order."""
    names = [c[0] for c in calls]
    k = names.count("fail")
    if names != ["impl"] + ["fail"] * k + ["cut", "fault", "retry"] or not 1 <= k <= 3:
        raise ValueError(f"atom order {calls}")
    failed = [c[1] for c in calls[1:1 + k]]
    if failed != sorted(set(failed)) or not set(failed) <= {0, 1, 2}:
        raise ValueError(f"FAIL row {failed} is not an increasing subset of 0..2")
    return case_id(calls[0][1], failed, calls[1 + k][1], calls[2 + k][1], calls[3 + k][1])


def parse_candidate(src):
    """(configuration calls + finish, inlined sources) from a rendered candidate, by syntax only."""
    calls, sources, begun, tail = [], None, False, []
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            name = ast.unparse(f)
            if isinstance(f, ast.Attribute) and name == "d13.begin" and not begun:
                begun = True
            elif isinstance(f, ast.Attribute) and name in ("d13.SOURCE_SHA256.update", "d13.SOURCES.update") and not begun:
                pass                                          # HEAD records the inlined sources and their hashes
            elif isinstance(f, ast.Name) and begun and not tail and not node.value.keywords and len(node.value.args) == 1:
                calls.append([f.id, ast.literal_eval(node.value.args[0])])
            else:
                raise ValueError(f"unexpected call {name}")
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            if target == "_D13_PACKED" and not begun:
                packed = ast.literal_eval(node.value)
                sources = {k: zlib.decompress(base64.b64decode(v)).decode("utf-8") for k, v in packed.items()}
            elif begun:                                        # TAIL: _verdict = finish(); FW_VAR = _verdict; FW_CUSTOM_VAR = FW_VAR
                tail.append(f"{target} = {ast.unparse(node.value)}")
        elif begun:
            raise ValueError(f"unexpected statement after begin(): {ast.unparse(node)[:60]}")
    if not begun:
        raise ValueError("no d13.begin()")
    if tail != ["_verdict = finish()", "FW_VAR = _verdict", "FW_CUSTOM_VAR = FW_VAR"]:
        raise ValueError(f"TAIL is {tail}")
    return calls + [["finish"]], sources


def join_cells(cells, endings):
    """The Reader's rendering: each column's values back to back, then its sheet ending, or a newline if it
    has none (nothing after the last column when its ending is empty)."""
    parts = []
    for i, (vals, e) in enumerate(zip(cells, endings)):
        parts += ["".join(vals), e if (e or i == len(cells) - 1) else "\n"]
    return "".join(parts)


def spec_view(spec):
    slots = [(s.sheet, list(s.values), s.ending) for s in spec.slots]
    chains = ({k: v["directives"] for k, v in spec.program.items()} if spec.program else {row[0]: row[1:] for row in spec.seq_extra})
    msgs = [re.sub(r"^FWCUSTOMVAR=\d+ ", "", c.msg) for c in spec.custom_vars]
    return {"slots": slots, "chains": chains, "custom": [(c.code, m) for c, m in zip(spec.custom_vars, msgs)],
            "constraints": spec.constraints, "params": spec.params}


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    architect = json.loads((root / "planning" / "architect-precheck.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in MODULES}

    # ---- frozen inputs, population, bond and model ----
    pre = manifest["preflight"]
    hashes = {"CONTRACT.md": pre["contract_sha256"], "architect-derived.json": pre["derived_sha256"], "derive.py": pre["derive_sha256"]}
    rep.check("frozen.contract_prediction_derivation", all(sha256((root / f).read_bytes()) == h for f, h in hashes.items())
              and pre["contract_sha256"] == "5a456c93a60d992a9aeddceb5cf57d661732fc0ecfaca3afd42fac3ae9670478"
              and pre["derived_sha256"] == "bbb3317de87c2a155e198073b0ac8608b8e2672752696a31a36e1f83c0716a01"
              and pre["derive_sha256"] == "c793a8dbaacd7acf4e14654ee14e7647853349e7fa1a0a84bf13d233fe581e9a", hashes)
    raw = list(itertools.product(IMPLS, SUBSETS, range(4), ("crash", "partition"), ("stable", "fresh")))
    rejected = sorted(case_id(*r) for r in raw if bond(r[1], r[3]))
    own = {c["id"]: c for c in (transitions(*r) for r in raw if not bond(r[1], r[3]))}
    expected_ids = sorted(own)
    fkeys = ("policy", "failed", "cut", "kind", "retry", "attempts", "trace", "acknowledged", "checks")
    diff = [(i, k) for i in expected_ids for k in fkeys if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    by_policy = {p: dict(Counter(c["verdict"] for c in own.values() if c["policy"] == p)) for p in IMPLS}
    counts_model = {"attempts": sum(len(c["attempts"]) for c in own.values()),
                    "worker_starts": sum(3 + (len(c["failed"]) if c["kind"] == "crash" else 0) for c in own.values()),
                    "injected_kills": sum(len(c["failed"]) for c in own.values() if c["kind"] == "crash")}
    rep.check("model.frozen_equals_own_312", len(raw) == RAW and len(rejected) == 24 and len(own) == EXPECTED and sorted(frozen) == expected_ids
              and not diff and by_policy == derived["by_policy"] and dict(Counter(c["verdict"] for c in own.values())) == derived["outcomes"]
              and counts_model == {k: derived[k] for k in counts_model} == {"attempts": 1062, "worker_starts": 1224, "injected_kills": 288}
              and rejected == sorted(architect["rejected_ids"]), {"diff": diff[:4], "by_policy": by_policy, "counts": counts_model})

    # ---- sieve: live log and plans ----
    log = (run / "logs" / "bundle_run.log").read_text(errors="replace")
    live = {m.group(1): int(m.group(2)) for m in re.finditer(r"rule (\S+): matched (\d+) row", log)}
    m = re.search(r"sieve: scanned (\d+), unique removals (\d+) \(overlap (\d+)\) → fw_final now (\d+)", log)
    line = [int(x) for x in m.groups()] if m else None
    pre_json = json.loads((root / "precheck" / "precheck.json").read_text())
    rep.check("sieve.truth_and_live_log", live == {RULE: 24} and line == [RAW, 24, 0, EXPECTED] and pre_json["rejected_ids"] == rejected
              and pre_json["rejected_ids_own_eq_framework_eq_astra"], {"live_rules": live, "live_line": line})
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "sieve", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    card = cmp_["cardinality"]["xlsx"]
    shape_plan = json.loads((root / "planning" / "plan" / "plan.json").read_text())
    rep.check("stage.plans_bounded_as_recorded", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == card
              and not any(cmp_["budget_blocking"].values()) and card["mandatory"] == ["EXACT", RAW, RAW, RAW]
              and card["post_sieve"] == ["BOUNDED", RAW, 0, RAW] and card["final"] == ["BOUNDED", RAW, 0, RAW]
              and card["optional_multiplier"][:2] == ["EXACT", 1] and cmp_["constraints_present"] == {"toml": 1, "xlsx": 1}
              and set(cmp_["graph_hash"].values()) == {shape_plan["dependency_graph"]["graph_hash"]}
              and cmp_["per_slot"]["xlsx"] == shape_plan["cardinality"]["per_slot"],
              {"cardinality": cmp_["cardinality"], "graph_hash": cmp_["graph_hash"], "reasons": cmp_.get("reasons")})

    # ---- Core rows and identities ----
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the implementation
    sheets = fg.workbook_to_json(books[0])["sheets"]
    data = [(s["name"], [r[0] for r in s["rows"]]) for s in sheets if not s["name"].startswith("FW_")]
    dictionary = sorted((int(r["bigint"]), r["value"]) for r in tables["NumberToValue1"])
    flat = [(name, v) for name, vals in data for v in vals]
    code2val = dict(dictionary)
    rep.check("core.dictionary_alignment", [n for n, _ in data] == list(SHEETS) and len(flat) == len(dictionary)
              and all(v == dv for (_, v), (_, dv) in zip(flat, dictionary))
              and [c for c, _ in dictionary] == list(range(len(data) + 1, len(data) + 1 + len(flat)))
              and dict(data)["FAIL"] == ["fail(0);", "fail(1);", "fail(2);"], {"sheets": [n for n, _ in data], "codes": len(dictionary)})
    endings = {r["sheet"]: r["ending"] for r in tables["names"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {mm.group(2): c for c in (frows or [{}])[0] for mm in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if mm}
    def cell(row, sheet):
        v = row.get(cols[sheet])
        return list(base.get(cols[sheet]) if v is None else v)
    decoded, bad_rows, core_text, row_of, fail_rows = [], [], {}, {}, Counter()
    for r in frows:
        try:
            codes = {s: cell(r, s) for s in SHEETS}
            if any(len(c) != 1 for s, c in codes.items() if s != "FAIL") or not 1 <= len(codes["FAIL"]) <= 3:
                raise ValueError(f"row cell arity {codes}")
            vals = {s: [code2val[c] for c in codes[s]] for s in SHEETS}
            cid = case_of([atom(vals["IMPL"][0])] + [atom(v) for v in vals["FAIL"]] + [atom(vals[s][0]) for s in ("CUT", "KIND", "RETRY")])
            fail_rows["".join(vals["FAIL"])] += 1
            core_text[cid] = join_cells([vals[s] for s in SHEETS], [endings[s] for s in SHEETS])
            row_of[cid] = r["combi_id"]
            decoded.append(cid)
        except (ValueError, KeyError, SyntaxError, AttributeError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    want_fail = {"".join(f"fail({n});" for n in f): (24 if len(f) == 3 else 48) for f in SUBSETS}
    rep.check("core.fail_rows_are_the_seven_native_subsets", dict(fail_rows) == want_fail and endings["FAIL"] == "\n",
              {"fail_rows": dict(fail_rows)})
    counts = {"core_fw_final": count("core", "fw_final"), "post_sieve": count("sieve", "post_sieve"), "fw_final_rows": len(frows),
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", counts["core_fw_final"] == RAW and counts["post_sieve"] == EXPECTED
              and counts["fw_final_rows"] == counts["reader"] == counts["executor"] == counts["results_v2"] == EXPECTED and "--sieve" in argv, counts)
    raw_ids = sorted(case_id(*r) for r in raw)
    rep.check("identity.core_after_sieve", not bad_rows and sorted(decoded) == expected_ids and sorted(cols) == sorted(SHEETS)
              and sorted(set(raw_ids) - set(decoded)) == rejected and not any(k.startswith("fw_opt") and v for k, v in tables.items()),
              {"bad_rows": bad_rows[:3], "rejected_identities": rejected})
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, mapping = {}, True, [], {}
    for name, raw_src in cands.items():
        src = raw_src.decode()
        try:
            calls, sources = parse_candidate(src)
            cid = case_of(calls[:-1])
            if src != core_text.get(cid):
                raise ValueError("candidate text differs from its Core row")
        except (ValueError, SyntaxError, IndexError, zlib.error) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = cid
        mapping[name] = row_of[cid]
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader_equals_core_rows", not errs and sorted(rendered.values()) == expected_ids
              and all(n.split("_")[0] == str(c) for n, c in mapping.items()), {"errors": errs[:3]})
    rep.check("reader.inlined_sources_including_worker_entry", src_ok, module_sha)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each_repeat_1", len(rv2) == EXPECTED and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or "")
              and "net=none" in (summary.get("sandbox_backend") or ""), {"outcomes": dict(outcomes), "backend": summary.get("sandbox_backend")})

    # ---- every record: semantics, WAL payloads, provenance, digests ----
    records = {json.loads(l)["id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids and len(records) == EXPECTED)
    bad, fields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_declared_population"))
            continue
        o, fw = own[cid], r["framework"]
        checks = record_problems(r, o)
        checks += [("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("record_keys", sorted(r), REC_KEYS),
                   ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], o["verdict"]),
                   ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("source_sha256", r["source_sha256"], module_sha),
                   ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                   ("rendered_identity", rendered.get(fw["source_ref"]), cid),
                   ("record_digest", sha256(canon({k: v for k, v in r.items() if k != "framework"}).encode("ascii")), fw.get("rec_sha256"))]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    recs = list(records.values())
    totals = dict(Counter(r["verdict"] for r in recs))
    tally = {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in IMPLS}
    live_counts = {"attempts": sum(len(r["attempts"]) for r in recs), "worker_starts": sum(r["provenance"]["worker_starts"] for r in recs),
                   "injected_kills": sum(r["provenance"]["injected_kills"] for r in recs)}
    rep.check("observations.totals", totals == derived["outcomes"] == {"PASS": 216, "DOMAIN_FAIL": 96} and tally == derived["by_policy"]
              and live_counts == {"attempts": 1062, "worker_starts": 1224, "injected_kills": 288},
              {"totals": totals, "by_policy": tally, "counts": live_counts})

    # ---- mechanisms (from the observed records) ----
    def failing(pred):
        return sum(1 for r in recs if pred(r) and r["verdict"] != "PASS")
    fresh_dup = {p: failing(lambda r, p=p: r["policy"] == p and r["retry"] == "fresh" and len(r["failed"]) == 2 and r["cut"] < 3) for p in IMPLS}
    lost = [r["id"] for r in recs if not r["checks"]["acknowledged_survive_repair"]]
    agree_but_wrong = sorted(r["id"] for r in recs if r["checks"]["replicas_agree"] and not r["checks"]["matches_fault_free_reference"])
    rep.check("mechanism.missing_duplicate_convergence", fresh_dup == {p: 18 for p in IMPLS}
              and all(r["verdict"] == "PASS" for r in recs if r["policy"] == "durable" and r["retry"] == "stable")
              and sorted(lost) == sorted(r["id"] for r in recs if r["policy"] == "volatile_ack" and r["kind"] == "crash" and len(r["failed"]) == 3 and r["cut"] > 0)
              and all(not r["checks"]["acknowledged_effects_once"] for r in recs if r["policy"] == "replay_twice" and r["kind"] == "crash" and r["cut"] > 0)
              and records[WITNESSES["replay_twice_uniform_wrong_state_agrees"]]["checks"]["replicas_agree"]
              and not records[WITNESSES["replay_twice_uniform_wrong_state_agrees"]]["checks"]["matches_fault_free_reference"],
              {"fresh_key_duplicates": fresh_dup, "lost_acknowledged": len(lost), "replicas_agree_but_wrong": len(agree_but_wrong)})
    ctrl = json.loads((root / manifest["preflight"]["sandbox_preflight"]["path"]).read_text())
    rep.check("preflight.controls_and_restart_cases", ctrl["ok"] and ctrl["module_sha256"] == module_sha and len(ctrl["controls"]) == 3
              and all(c["record"]["ok"] and all(s["value"] == 111 and s["counts"] == {"o1": 1, "o2": 1, "o3": 1} for s in c["record"]["final"]["nodes"])
                      for c in ctrl["controls"])
              and all(x["ok"] and x["kills"] == [-9, -9, -9] and x["restarts"] == 3 for x in ctrl["restart_cases"]),
              {"controls": [c["record"]["policy"] for c in ctrl["controls"]], "sandbox": ctrl["sandbox"]})

    # ---- envelope and provenance ----
    need = ["--lang", "py", "--sieve", "--execution-policy-profile", "generated-default", "--candidate-origin", "generated", "--repeat", "1",
            "--executor-workers", "1", *BUDGET_ARGS]
    rep.check("envelope.command", all(t in argv for t in need) and "--override-budget" not in argv and Path(argv[2]).name == "demo.xlsx"
              and all(argv[argv.index(BUDGET_ARGS[i]) + 1] == BUDGET_ARGS[i + 1] for i in range(0, 8, 2)), argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d15_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values())
              and all(manifest["databases"]["exists_after"].values()), manifest["databases"])
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    build = json.loads((root / "spec" / "build.json").read_text())
    rep.check("provenance.build_record", build["module_sha256"] == module_sha
              and all(build["files"][f] == sha256((run / "inputs" / f).read_bytes()) for f in ("spec.toml", "demo.xlsx", "demo.constraints.json")),
              build["files"])
    comp = {a["kind"]: a for st in stages.values() for a in st.get("artifacts", []) if a["kind"].startswith("component.")}
    comp_ok = {k: Path(a["path"]).is_file() and sha256(Path(a["path"]).read_bytes()) == a["sha256"] for k, a in comp.items()}
    rep.check("provenance.framework_components_unchanged", comp_ok and all(comp_ok.values()),
              {k: {"sha256": a["sha256"], "unchanged": comp_ok[k]} for k, a in comp.items()})
    side = root / "spec" / "demo.constraints.json"
    run_json = json.loads((run / "run" / "run.json").read_text())
    chain = {sha256((run / "inputs" / "demo.constraints.json").read_bytes()), run_json.get("constraints_sidecar_sha256"),
             sha256((run / "run" / "wb__demo.constraints.json").read_bytes())}
    x, t = fg.load_spec(root / "spec" / "demo.xlsx"), fg.load_spec(root / "spec" / "spec.toml")
    xv, tv = spec_view(x), spec_view(t)
    rep.check("provenance.xlsx_toml_sidecar_core_input", chain == {sha256(side.read_bytes())}
              and json.loads((run / "run" / "sidecar.json").read_text())["constraints"] == json.loads(side.read_text())["constraints"]
              and sheets == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"] == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"]
              and xv["slots"] == tv["slots"] and xv["chains"] == tv["chains"] and xv["custom"] == tv["custom"]
              and x.constraints == t.constraints and [c["id"] for c in x.constraints] == [RULE] and xv["chains"]["FAIL"] == ["FW_Subsets", "FW_Combi(size)"],
              {"slots_equal": xv["slots"] == tv["slots"], "chains_equal": xv["chains"] == tv["chains"]})
    strata = {p: {k: dict(Counter(r["verdict"] for r in recs if r["policy"] == p and r["kind"] == k)) for k in ("crash", "partition")} for p in IMPLS}
    failed_checks = {p: {c: sum(not r["checks"][c] for r in recs if r["policy"] == p) for c in CHECKS} for p in IMPLS}
    return rep, {"stage_counts": {**counts, "sieve_rules": live, "sieve_line": line}, "totals": totals, "by_policy": tally, "strata": strata,
                 "failed_checks": failed_checks, "counts": live_counts, "rejected_ids": rejected, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "attempts": r["attempts"],
                    "final": [{k: s[k] for k in ("node", "generation", "accepted", "wal", "effects", "value")} for s in r["trace"][-1]["nodes"]],
                    "checks": r["checks"], "verdict": r["verdict"], "semantic_sha256": r["semantic_sha256"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d15.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d15.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "strata", "failed_checks", "counts", "rejected_ids")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
