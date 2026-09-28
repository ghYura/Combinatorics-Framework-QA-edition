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

"""Independent offline verifier for one D13d evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py or derive.py, never connects to a
database, never executes a candidate (candidates and dictionary atoms are parsed with `ast`). The
label partitions, the 1152 bond truth rows, both traces, the input-derived canary owner, all three
checks, leak kinds and channel occurrences are re-derived here from CONTRACT.md and compared with
the frozen predictions, the live sieve log, the decoded Core rows, the rendered candidates and every
observation record.
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
POLICIES = ("scoped", "user_only", "session_only", "ignores_reset")
CUTS = ("00", "01", "10", "11")
RULES = ("user_rgs", "session_rgs")
RAW, AFTER_USER, EXPECTED = 1152, 960, 800
ORDER = ("HEAD", "IMPL", "WRITE_AT", "U1", "U2", "U3", "S1", "S2", "S3", "R12", "R23", "TAIL")
ATOMS = ["impl", "write_at", "user_at", "user_at", "user_at", "session_at", "session_at", "session_at", "reset_cut", "reset_cut"]
TRIPLES = ["0" + str(a) + str(b) for a in range(2) for b in range(3)]
CANARY = "D13D_CANARY_R"
WITNESSES = {
    "session_only_cross_user": "P=session_only|U=010|S=000|X=00|W=1",
    "user_only_cross_session": "P=user_only|U=000|S=010|X=00|W=1",
    "ignores_reset_expired": "P=ignores_reset|U=000|S=000|X=10|W=1",
    "scoped_reset_before_write_retains": "P=scoped|U=000|S=000|X=10|W=2",
    "scoped_reset_after_write_clears": "P=scoped|U=000|S=000|X=01|W=1",
}


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


# ---- the contract, re-derived (from CONTRACT.md, not from sut.py / oracle.py) ----
def rgs(t):
    return all(int(t[i]) <= 1 + max([-1] + [int(c) for c in t[:i]]) for i in range(3))


def epochs(cuts):
    """Logical epoch of requests 1, 2, 3."""
    return [0, int(cuts[0]), int(cuts[0]) + int(cuts[1])]


def adapter_trace(policy, users, sessions, cuts, w):
    ep, entries, trace = epochs(cuts), {}, []
    for i in range(3):
        u, s = int(users[i]), int(sessions[i])
        cut = i > 0 and cuts[i - 1] == "1"
        if cut and policy != "ignores_reset":
            entries = {}
        key = {"user_only": (u,), "session_only": (s,)}.get(policy, (u, s))
        if i + 1 == w:
            entries = {**entries, key: {"value": f"{CANARY}{w}", "write_user": u, "write_session": s, "write_epoch": ep[i],
                                        "write_index": w}}
            op, reply, calls = "write", "STORED", []
        else:
            got = entries.get(key)
            op, reply = "read", (got["value"] if got else None)
            calls = [{"name": "draft", "argument": reply}] if got else []
        trace.append({"request_index": i + 1, "user": u, "session": s, "operation": op, "reset_before": cut, "epoch": ep[i],
                      "storage_key": list(key), "reply": reply, "tool_calls": calls,
                      "memory": [{"key": list(k), **v} for k, v in sorted(entries.items())]})
    return trace


def own_case(policy, users, sessions, cuts, w):
    obs, ref = adapter_trace(policy, users, sessions, cuts, w), adapter_trace("scoped", users, sessions, cuts, w)
    ep = epochs(cuts)
    owner = (int(users[w - 1]), int(sessions[w - 1]), ep[w - 1])
    checks, leaks, occ = [], [], []
    for i, (o, r) in enumerate(zip(obs, ref), 1):
        reader = (int(users[i - 1]), int(sessions[i - 1]), ep[i - 1])
        channels = [] if i == w else ([("reply", o["reply"])] if isinstance(o["reply"], str) and CANARY in o["reply"] else []) + \
            [("tool_argument", c["argument"]) for c in o["tool_calls"] if isinstance(c.get("argument"), str) and CANARY in c["argument"]]
        bad = [ch for ch, v in channels if v != f"{CANARY}{w}" or reader != owner or i < w]
        checks.append({"request_index": i, "response_ok": o["reply"] == r["reply"], "tools_ok": o["tool_calls"] == r["tool_calls"],
                       "isolation_ok": not bad})
        if bad:
            leaks.append({"request_index": i, "kind": "cross_user" if owner[0] != reader[0] else
                          "cross_session" if owner[1] != reader[1] else "expired"})
            occ += [{"request_index": i, "channel": ch} for ch in bad]
    failing = [c["request_index"] for c in checks if not (c["response_ok"] and c["tools_ok"] and c["isolation_ok"])]
    return {"case_id": f"P={policy}|U={users}|S={sessions}|X={cuts}|W={w}", "policy": policy, "users": users, "sessions": sessions,
            "cuts": cuts, "write_at": w, "observed_trace": obs, "reference_trace": ref,
            "owner": {"user": owner[0], "session": owner[1], "epoch": owner[2], "canary": f"{CANARY}{w}"},
            "checks": checks, "leaks": leaks, "leak_occurrences": occ, "failing_checkpoints": failing,
            "verdict": "DOMAIN_FAIL" if failing else "PASS"}


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def atom(text):
    node = ast.parse(text).body
    if len(node) != 1 or not isinstance(node[0], ast.Expr) or not isinstance(node[0].value, ast.Call):
        raise ValueError(f"not one call: {text!r}")
    call = node[0].value
    return [call.func.id, *[ast.literal_eval(a) for a in call.args]]


def case_of(calls):
    """Identity from the ten configuration atoms, in slot order."""
    if [c[0] for c in calls] != ATOMS or [c[1] for c in calls[2:5]] != [1, 2, 3] or [c[1] for c in calls[5:8]] != [1, 2, 3] \
            or [c[1] for c in calls[8:]] != [1, 2]:
        raise ValueError(f"atom order {calls}")
    u, s, x = (''.join(str(c[2]) for c in calls[a:b]) for a, b in ((2, 5), (5, 8), (8, 10)))
    return f"P={calls[0][1]}|U={u}|S={s}|X={x}|W={calls[1][1]}"


def parse_candidate(src):
    """(configuration calls + finish, inlined sources) from a rendered candidate, by syntax only."""
    calls, sources, begun = [], None, False
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and ast.unparse(f) == "d13.begin" and not begun:
                begun = True
            elif isinstance(f, ast.Attribute) and ast.unparse(f) == "d13.SOURCE_SHA256.update" and not begun:
                pass                                          # HEAD records the inlined source hashes
            elif isinstance(f, ast.Name) and begun:
                calls.append([f.id, *[ast.literal_eval(a) for a in node.value.args]])
            else:
                raise ValueError(f"unexpected call {ast.unparse(f)}")
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D13_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict" and begun:
                if ast.unparse(node.value) != "finish()":
                    raise ValueError(f"TAIL assigns {ast.unparse(node.value)}")
                calls.append(["finish"])                      # TAIL: _verdict = finish()
    if not begun:
        raise ValueError("no d13.begin()")
    return calls, sources


def join_row(values, endings):
    """The Reader's rendering: each column's value followed by its sheet ending, or a newline if it has none
    (nothing after the last column when its ending is empty)."""
    parts = []
    for i, (v, e) in enumerate(zip(values, endings)):
        parts += [v, e if (e or i == len(values) - 1) else "\n"]
    return "".join(parts)


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}

    # ---- labels, bonds and the declared population ----
    raw = list(itertools.product(POLICIES, TRIPLES, TRIPLES, CUTS, (1, 2)))
    truth = {f"P={p}|U={u}|S={s}|X={x}|W={w}": {"user_rgs": int(u[2]) <= 1 + int(u[1]), "session_rgs": int(s[2]) <= 1 + int(s[1])}
             for p, u, s, x, w in raw}
    own = {c["case_id"]: c for c in (own_case(p, u, s, x, w) for p, u, s, x, w in raw if rgs(u) and rgs(s))}
    expected_ids = sorted(own)
    keys = ("policy", "users", "sessions", "cuts", "write_at", "observed_trace", "reference_trace", "checks", "leaks", "failing_checkpoints")
    diff = [(i, k) for i in expected_ids for k in keys if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    frozen_truth = {t["id"]: {r: t[r] for r in RULES} for t in derived["raw_bond_truth"]}
    rep.check("space.frozen_equals_own_model", sorted(frozen) == expected_ids and len(own) == EXPECTED and not diff
              and frozen_truth == truth and len(truth) == RAW, {"cases": len(own), "diff": diff[:4], "raw_truth_rows": len(truth)})
    canon = [t for t in TRIPLES if rgs(t)]
    rep.check("labels.canonical_partitions", canon == derived["partitions"] == ["000", "001", "010", "011", "012"]
              and all(rgs(t) == truth[f"P=scoped|U={t}|S=000|X=00|W=1"]["user_rgs"] for t in TRIPLES)
              and len({(c["users"], c["sessions"]) for c in own.values()}) == 25, {"canonical": canon})

    hits = {i: [r for r in RULES if not t[r]] for i, t in truth.items()}
    per_rule = {r: sum(r in h for h in hits.values()) for r in RULES}
    seq, alive = [RAW], dict(hits)
    for r in RULES:
        alive = {i: h for i, h in alive.items() if r not in h}
        seq.append(len(alive))
    overlap = sum(len(h) > 1 for h in hits.values())
    log = (run / "logs" / "bundle_run.log").read_text(errors="replace")
    live = {m.group(1): int(m.group(2)) for m in re.finditer(r"rule (\S+): matched (\d+) row", log)}
    m = re.search(r"sieve: scanned (\d+), unique removals (\d+) \(overlap (\d+)\) → fw_final now (\d+)", log)
    line = [int(x) for x in m.groups()] if m else None
    pre = json.loads((root / "precheck" / "precheck.json").read_text())
    own_table = {"raw": RAW, "per_rule": per_rule, "overlap": overlap, "unique_removals": RAW - seq[-1], "sequential": seq}
    rep.check("sieve.truth_table_and_live_log", sorted(alive) == expected_ids and live == per_rule
              and line == [RAW, RAW - seq[-1], overlap, EXPECTED] and seq == [RAW, AFTER_USER, EXPECTED]
              and pre["truth_table"] == own_table and pre["framework_sieve_offline_agrees"] and pre["raw_rows_equal_frozen_truth"],
              {"own": own_table, "live_rules": live, "live_line": line})

    # ---- stages, plans, Core rows and identities ----
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "sieve", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    card = cmp_["cardinality"]["xlsx"]
    rep.check("stage.plans_bounded_as_recorded", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == card
              and not any(cmp_["budget_blocking"].values()) and card["mandatory"] == ["EXACT", RAW, RAW, RAW]
              and card["post_sieve"][0] == "BOUNDED" and card["post_sieve"][2:] == [0, RAW]
              and card["final"][0] == "BOUNDED" and card["final"][2:] == [0, RAW] and card["optional_multiplier"][:2] == ["EXACT", 1]
              and cmp_["constraints_present"] == {"toml": 2, "xlsx": 2},
              {"cardinality": cmp_["cardinality"], "reasons": cmp_.get("reasons")})
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    sheets = fg.workbook_to_json(books[0])["sheets"]
    data = [(s["name"], [r[0] for r in s["rows"]]) for s in sheets if not s["name"].startswith("FW_")]
    dictionary = sorted((int(r["bigint"]), r["value"]) for r in tables["NumberToValue1"])
    flat = [(name, v) for name, vals in data for v in vals]
    code2val = dict(dictionary)
    rep.check("core.dictionary_alignment", [n for n, _ in data] == list(ORDER) and len(flat) == len(dictionary)
              and all(v == dv for (_, v), (_, dv) in zip(flat, dictionary))
              and [c for c, _ in dictionary] == list(range(len(data) + 1, len(data) + 1 + len(flat))),
              {"sheets": [n for n, _ in data], "codes": len(dictionary)})
    endings = {r["sheet"]: r["ending"] for r in tables["names"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {mm.group(2): c for c in (frows or [{}])[0] for mm in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if mm}
    def cell(row, sheet):
        v = row.get(cols[sheet])
        return list(base.get(cols[sheet]) if v is None else v)
    decoded, bad_rows, core_text, row_of = [], [], {}, {}
    for r in frows:
        try:
            codes = {s: cell(r, s) for s in ORDER}
            if any(len(c) != 1 for c in codes.values()):
                raise ValueError(f"row cell arity {codes}")
            cid = case_of([atom(code2val[codes[s][0]]) for s in ORDER[1:-1]])
            core_text[cid] = join_row([code2val[codes[s][0]] for s in ORDER], [endings[s] for s in ORDER])
            row_of[cid] = r["combi_id"]
            decoded.append(cid)
        except (ValueError, KeyError, SyntaxError, AttributeError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "post_sieve": count("sieve", "post_sieve"), "fw_final_rows": len(frows),
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", counts["core_fw_final"] == RAW and counts["post_sieve"] == EXPECTED
              and counts["fw_final_rows"] == counts["reader"] == counts["executor"] == counts["results_v2"] == EXPECTED, counts)
    rep.check("identity.core_after_sieve", not bad_rows and sorted(decoded) == expected_ids and sorted(cols) == sorted(ORDER)
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3], "columns": sorted(cols)})

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, mapping = {}, True, [], {}
    for name, raw_src in cands.items():
        src = raw_src.decode()
        try:
            calls, sources = parse_candidate(src)
            if calls[-1:] != [["finish"]]:
                raise ValueError("no finish()")
            cid = case_of(calls[:-1])
            if src != core_text.get(cid):
                raise ValueError("candidate text differs from its Core row")
        except (ValueError, SyntaxError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = cid
        mapping[name] = row_of[cid]
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader_equals_core_rows", not errs and sorted(rendered.values()) == expected_ids,
              {"errors": errs[:3], "candidate_name_prefix_equals_combi_id": all(n.split("_")[0] == str(c) for n, c in mapping.items())})
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == EXPECTED and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    # ---- every record, every field ----
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    bad, fields = [], 0
    rec_keys = sorted(["schema", "contract", "case_id", "policy", "users", "sessions", "cuts", "write_at", "observed_trace",
                       "reference_trace", "owner", "checks", "leaks", "leak_occurrences", "failing_checkpoints", "verdict", "fw_var",
                       "carrier_slot", "source_sha256", "framework"])
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_declared_population"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [(k, r.get(k), o[k]) for k in (*keys, "case_id", "owner", "leak_occurrences", "verdict")]
        checks += [("schema", r["schema"], "d13d.observation/v1"), ("contract", r["contract"], "v1"),
                   ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2),
                   ("carrier_slot", r["carrier_slot"], "IMPL position 2 (legacy positional, not causal)"),
                   ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("record_keys", sorted(r), rec_keys),
                   ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], o["verdict"]),
                   ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("source_sha256", r["source_sha256"], module_sha),
                   ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])), ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    recs = list(records.values())
    totals = Counter(r["verdict"] for r in recs)
    by_policy = {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in POLICIES}
    kinds = dict(Counter(x["kind"] for r in recs for x in r["leaks"]))
    occurrences = dict(Counter(x["channel"] for r in recs for x in r["leak_occurrences"]))
    failed_cases = sum(1 for r in recs if r["verdict"] == "DOMAIN_FAIL")
    rep.check("observations.totals_and_leak_counts", dict(totals) == derived["outcomes"] and by_policy == derived["by_policy"]
              and kinds == derived["leak_checkpoints"] == {"cross_user": 30, "cross_session": 30, "expired": 28}
              and occurrences == {"reply": 88, "tool_argument": 88} and failed_cases == 82,
              {"totals": dict(totals), "by_policy": by_policy, "leak_checkpoints": kinds, "occurrences": occurrences,
               "failed_cases": failed_cases, "cases_with_two_leaks": sum(1 for r in recs if len(r["leaks"]) == 2)})
    strata = {ax: {str(v): dict(Counter(r["verdict"] for r in recs if r[ax] == v)) for v in vals}
              for ax, vals in (("policy", POLICIES), ("cuts", CUTS), ("write_at", (1, 2)))}
    cross = {f"{p}|X={x}|W={w}": dict(Counter(r["verdict"] for r in recs if (r["policy"], r["cuts"], r["write_at"]) == (p, x, w)))
             for p in POLICIES for x in CUTS for w in (1, 2)}

    # ---- mechanisms (from the observed records) ----
    kind_by_policy = {p: sorted({x["kind"] for r in recs if r["policy"] == p for x in r["leaks"]}) for p in POLICIES}
    retained = [r for r in recs if any(e["operation"] == "read" and e["reply"] is not None for e in r["reference_trace"])]
    rep.check("mechanism.defect_to_leak_kind", kind_by_policy == {"scoped": [], "user_only": ["cross_session"],
                                                                   "session_only": ["cross_user"], "ignores_reset": ["expired"]}
              and all(r["verdict"] == "PASS" for r in recs if r["policy"] == "scoped")
              and all({o["channel"] for o in r["leak_occurrences"] if o["request_index"] == x["request_index"]} == {"reply", "tool_argument"}
                      for r in recs for x in r["leaks"]),
              {"leak_kinds_by_policy": kind_by_policy})
    rep.check("mechanism.useful_retention_rules_out_erase_all", len(retained) > 0
              and all(r["observed_trace"] == r["reference_trace"] for r in recs if r["policy"] == "scoped")
              and {r["policy"] for r in retained} == set(POLICIES),
              {"records_whose_reference_retains_a_value": len(retained), "per_policy": dict(Counter(r["policy"] for r in retained))})

    need_args = ["--lang", "py", "--sieve", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "1200", "--budget-final-candidates", "1200", "--budget-disk-bytes", "150000000",
                 "--budget-wall-time-seconds", "3000"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--override-budget" not in argv and Path(argv[2]).name == "demo.xlsx",
              argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d13d_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    side = root / "spec" / "demo.constraints.json"
    run_json = json.loads((run / "run" / "run.json").read_text())
    chain = {sha256((run / "inputs" / "demo.constraints.json").read_bytes()), run_json.get("constraints_sidecar_sha256"),
             sha256((run / "run" / "wb__demo.constraints.json").read_bytes())}
    rep.check("provenance.companion_chain", chain == {sha256(side.read_bytes())}
              and json.loads((run / "run" / "sidecar.json").read_text())["constraints"] == json.loads(side.read_text())["constraints"])
    x, t = fg.load_spec(root / "spec" / "demo.xlsx"), fg.load_spec(root / "spec" / "spec.toml")
    rep.check("provenance.xlsx_toml_sidecar_core_input", sheets == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"]
              == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"] and x.constraints == t.constraints and x.params == t.params
              and [c["id"] for c in x.constraints] == list(RULES))
    return rep, {"stage_counts": {**counts, "sieve_rules": live, "sieve_line": line, "truth": own_table},
                 "totals": dict(totals), "by_policy": by_policy, "leak_checkpoints": kinds, "occurrences": occurrences,
                 "strata": strata, "cross": cross, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "observed_trace": r["observed_trace"],
                    "checks": r["checks"], "leaks": r["leaks"], "failing_checkpoints": r["failing_checkpoints"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d13d.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d13d.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "leak_checkpoints", "occurrences", "strata", "cross")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
