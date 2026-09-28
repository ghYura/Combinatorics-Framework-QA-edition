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


"""Independent offline verifier for one D14b evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports adapter.py, model.py, oracle.py, runtime.py, fixture.py or derive.py,
never connects to a database or container, never executes a candidate (candidates are parsed with
`ast`). The fixture joins, three-valued truth, all query/partition/recombined bags and verdicts are
rebuilt here from CONTRACT.md and compared with the frozen predictions, the decoded Core rows, the
rendered candidates and every observation record. Live provenance is checked against the fixture's
server SQL log, the before/after fixture exports, the setup record and the persisted sandbox policy.
"""
import argparse
import ast
import csv
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
POLICIES = ("union_all", "omit_unknown", "dedup_union")
QUERIES = ("scan", "filtered", "inner_join", "left_join")
PREDS = ("gt0", "eq1", "flag", "and", "or", "is_null")
PTEXT = {"gt0": "i.val > 0", "eq1": "i.val = 1", "flag": "i.flag", "and": "(i.val > 0) AND i.flag", "or": "(i.val = 1) OR i.flag",
         "is_null": "i.val IS NULL"}
BRANCHES = ("base", "true", "false", "unknown")
SHEETS = ("HEAD", "IMPL", "QUERY", "PREDICATE", "TAIL")
MODULES = ("adapter", "model", "oracle", "runtime")
EXPECTED = 72
READER = "as0927_d14b_reader"
BEGIN = "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
PROVENANCE_SQL = ("SELECT current_database(), current_user, current_setting('transaction_isolation'), "
                  "current_setting('transaction_read_only'), pg_backend_pid(), pg_current_snapshot()::text, version(), "
                  "current_setting('application_name'), current_setting('statement_timeout')")
BUDGET_ARGS = ["--budget-mandatory-rows", "100", "--budget-final-candidates", "100", "--budget-disk-bytes", "200000000",
               "--budget-wall-time-seconds", "600"]
NEW_STORAGE_LIMIT = 200_000_000
LOG_RE = re.compile(r"^(\S+ \S+ UTC) \[(\d+)\] user=(\S*) db=(\S*) app=(.*?) vxid=(\S*) (LOG|ERROR|FATAL|WARNING|STATEMENT):  (.*)$")
WITNESSES = {
    "omit_unknown_sets_agree_bags_differ": "P=omit_unknown|Q=scan|F=flag",
    "union_all_keeps_unknown_multiplicity": "P=union_all|Q=scan|F=flag",
    "dedup_union_destroys_join_multiplicity": "P=dedup_union|Q=inner_join|F=eq1",
    "omit_unknown_no_unknown_rows_passes": "P=omit_unknown|Q=filtered|F=or",
    "dedup_union_distinct_rows_passes": "P=dedup_union|Q=filtered|F=is_null",
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


# ---- the contract, re-derived (from CONTRACT.md, not from the implementation) ----
TV = {True: "T", False: "F", None: "U"}


def tv_not(a):
    return {"T": "F", "F": "T", "U": "U"}[a]


def tv_and(a, b):
    return "F" if "F" in (a, b) else "U" if "U" in (a, b) else "T"


def tv_or(a, b):
    return "T" if "T" in (a, b) else "U" if "U" in (a, b) else "F"


def truth(item, p):
    v, flag = item["val"], TV[item["flag"]]
    gt = "U" if v is None else TV[v > 0]
    eq = "U" if v is None else TV[v == 1]
    return {"gt0": gt, "eq1": eq, "flag": flag, "and": tv_and(gt, flag), "or": tv_or(eq, flag), "is_null": TV[v is None]}[p]


def scanned(fx, query):
    tags = Counter(t["item_id"] for t in fx["tags"])
    rows = []
    for item in fx["items"]:
        if query == "filtered" and item["grp"] != "a":
            continue
        n = {"scan": 1, "filtered": 1, "inner_join": tags[item["id"]], "left_join": max(1, tags[item["id"]])}[query]
        rows += [item] * n
    return rows


def rows_of(values):
    return sorted([[v] for v in values], key=lambda r: (r[0] is not None, r[0] if r[0] is not None else 0))


def bag_of(rows):
    counts = Counter(r[0] for r in rows)
    return [{"row": [v], "count": counts[v]} for v in sorted(counts, key=lambda v: (v is not None, v if v is not None else 0))]


def sql_of(query, p):
    join = {"inner_join": " JOIN fixture.tags AS t ON t.item_id=i.id", "left_join": " LEFT JOIN fixture.tags AS t ON t.item_id=i.id"}.get(query, "")
    base = "i.grp = 'a'" if query == "filtered" else "TRUE"
    head = f"SELECT i.val FROM fixture.items AS i{join} WHERE "
    return {"base": head + base, "true": f"{head}({base}) AND ({PTEXT[p]})", "false": f"{head}({base}) AND NOT ({PTEXT[p]})",
            "unknown": f"{head}({base}) AND (({PTEXT[p]}) IS NULL)"}


def own_case(fx, policy, query, p):
    src = scanned(fx, query)
    qr = {"base": rows_of(i["val"] for i in src), "true": rows_of(i["val"] for i in src if truth(i, p) == "T"),
          "false": rows_of(i["val"] for i in src if tv_not(truth(i, p)) == "T"), "unknown": rows_of(i["val"] for i in src if truth(i, p) == "U")}
    kept = [r for b in (("true", "false") if policy == "omit_unknown" else ("true", "false", "unknown")) for r in qr[b]]
    if policy == "dedup_union":
        kept = [list(t) for t in dict.fromkeys(tuple(r) for r in kept)]
    comb = rows_of(r[0] for r in kept)
    tlp = bag_of(qr["base"]) == bag_of(comb)
    return {"id": f"P={policy}|Q={query}|F={p}", "policy": policy, "query": query, "predicate": p, "sql": sql_of(query, p),
            "query_rows": qr, "query_bags": {b: bag_of(qr[b]) for b in BRANCHES}, "combined_rows": comb, "combined_bag": bag_of(comb),
            "tlp_ok": tlp, "set_equal": {r[0] for r in qr["base"]} == {r[0] for r in comb},
            "query_checks": {b: True for b in BRANCHES}, "verdict": "PASS" if tlp else "DOMAIN_FAIL"}


FROZEN_KEYS = ("policy", "query", "predicate", "sql", "query_rows", "query_bags", "combined_rows", "combined_bag", "tlp_ok", "set_equal")
REC_KEYS = sorted(["schema", "contract", "id", *FROZEN_KEYS, "query_checks", "verdict", "fw_var", "carrier_slot", "source_sha256",
                   "provenance", "framework"])


def compare_record(r, o):
    """[(field, observed, expected)] for every mathematical field of one record (provenance is checked separately)."""
    checks = [(k, r.get(k), o[k]) for k in ("id", *FROZEN_KEYS, "query_checks", "verdict")]
    checks += [("schema", r.get("schema"), "d14b.observation/v1"), ("contract", r.get("contract"), "v1"),
               ("fw_var", r.get("fw_var"), 0 if o["verdict"] == "PASS" else 2),
               ("carrier_slot", r.get("carrier_slot"), "IMPL position 2 (legacy positional, not causal)")]
    return checks


def provenance_problems(r, fixture, version):
    p, bad = r.get("provenance") or {}, []
    want = {"fixture": fixture, "database": fixture, "user": READER, "transaction_isolation": "repeatable read",
            "transaction_read_only": "on", "application_name": ("d14b:" + r["id"])[:63], "statement_timeout": "5s", "version": version}
    bad += [(k, p.get(k), v) for k, v in want.items() if p.get(k) != v]
    if type(p.get("backend_pid")) is not int or not re.fullmatch(r"\d+:\d+:[\d,]*", str(p.get("snapshot"))):
        bad.append(("pid/snapshot", p.get("backend_pid"), p.get("snapshot")))
    seq = [(s.get("kind"), s.get("sql"), s.get("rows")) for s in p.get("statements") or []]
    want_seq = [("begin", BEGIN, None), ("provenance", PROVENANCE_SQL, 1)] + \
        [(f"data:{b}", r["sql"][b], len(r["query_rows"][b])) for b in BRANCHES] + [("end", "COMMIT", None)]
    if seq != want_seq:
        bad.append(("statements", seq, want_seq))
    return bad


def parse_log(text):
    out = []
    for line in text.splitlines():
        m = LOG_RE.match(line)
        if m:
            out.append(dict(zip(("ts", "pid", "user", "db", "app", "vxid", "level", "msg"), m.groups())))
    return out


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
    """Identity from the three configuration atoms, in slot order."""
    if [c[0] for c in calls] != ["impl", "query", "predicate"] or any(len(c) != 2 for c in calls):
        raise ValueError(f"atom order {calls}")
    return f"P={calls[0][1]}|Q={calls[1][1]}|F={calls[2][1]}"


def parse_candidate(src):
    """(configuration calls + finish, inlined sources) from a rendered candidate, by syntax only."""
    calls, sources, begun, tail = [], None, False, []
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and ast.unparse(f) == "d13.begin" and not begun:
                begun = True
            elif isinstance(f, ast.Attribute) and ast.unparse(f) == "d13.SOURCE_SHA256.update" and not begun:
                pass                                          # HEAD records the inlined source hashes
            elif isinstance(f, ast.Name) and begun and not tail and not node.value.keywords and len(node.value.args) == 1:
                calls.append([f.id, ast.literal_eval(node.value.args[0])])
            else:
                raise ValueError(f"unexpected call {ast.unparse(f)}")
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == "_D13_SOURCES" and not begun:
                sources = ast.literal_eval(node.value)
            elif begun:                                        # TAIL: _verdict = finish(); FW_VAR = _verdict; FW_CUSTOM_VAR = FW_VAR
                tail.append(f"{name} = {ast.unparse(node.value)}")
        elif begun:
            raise ValueError(f"unexpected statement after begin(): {ast.unparse(node)[:60]}")
    if not begun:
        raise ValueError("no d13.begin()")
    if tail != ["_verdict = finish()", "FW_VAR = _verdict", "FW_CUSTOM_VAR = FW_VAR"]:
        raise ValueError(f"TAIL is {tail}")
    return calls + [["finish"]], sources


def join_row(values, endings):
    """The Reader's rendering: each column's value followed by its sheet ending, or a newline if it has none
    (nothing after the last column when its ending is empty)."""
    parts = []
    for i, (v, e) in enumerate(zip(values, endings)):
        parts += [v, e if (e or i == len(values) - 1) else "\n"]
    return "".join(parts)


def spec_view(spec):
    slots = [(s.sheet, list(s.values), s.ending) for s in spec.slots]
    chains = ({k: v["directives"] for k, v in spec.program.items()} if spec.program
              else {row[0]: row[1:] for row in spec.seq_extra})
    msgs = [re.sub(r"^FWCUSTOMVAR=\d+ ", "", c.msg) for c in spec.custom_vars]
    return {"slots": slots, "chains": chains, "custom": [(c.code, m) for c, m in zip(spec.custom_vars, msgs)],
            "constraints": spec.constraints, "params": spec.params}


def csv_fixture(items_csv, tags_csv):
    conv = {"int": lambda v: None if v == "NULL" else int(v), "text": lambda v: v, "bool": lambda v: None if v == "NULL" else v == "t"}
    items = [{"id": conv["int"](r["id"]), "grp": r["grp"], "val": conv["int"](r["val"]), "flag": conv["bool"](r["flag"])}
             for r in csv.DictReader(io.StringIO(items_csv))]
    tags = [{"item_id": int(r["item_id"]), "tag": r["tag"]} for r in csv.DictReader(io.StringIO(tags_csv))]
    return {"items": items, "tags": tags}


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    fx = derived["fixture"]
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in MODULES}
    fix = manifest["fixture"]
    fixture, stamp = fix["names"]["container"], fix["stamp"]
    setup = json.loads((root / "evidence" / f"fixture-{stamp}" / "setup.json").read_text())

    # ---- frozen inputs and the model ----
    pre = manifest["preflight"]
    hashes = {"CONTRACT.md": pre["contract_sha256"], "architect-derived.json": pre["derived_sha256"], "derive.py": pre["derive_sha256"]}
    rep.check("frozen.contract_prediction_derivation", all(sha256((root / f).read_bytes()) == h for f, h in hashes.items())
              and pre["contract_sha256"] == "8f9fa5cf9f9e69d4a4ae8fd2a69eeae877f75ddc35011ee38de45e5bc0c4289d"
              and pre["derived_sha256"] == "bb459f09c6409461a4efcc7a827279475f718530647263ed6c9ac3b6d19aa9c1", hashes)
    own = {c["id"]: c for c in (own_case(fx, *k) for k in itertools.product(POLICIES, QUERIES, PREDS))}
    expected_ids = sorted(own)
    diff = [(i, k) for i in expected_ids for k in FROZEN_KEYS if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    own_tally = {p: dict(Counter(c["verdict"] for c in own.values() if c["policy"] == p)) for p in POLICIES}
    rep.check("model.frozen_equals_own_72", sorted(frozen) == expected_ids and len(own) == EXPECTED and not diff
              and own_tally == derived["by_policy"] and derived["framework_cases"] == 72 and derived["families"] == 24
              and derived["data_queries"] == 288, {"cases": len(own), "diff": diff[:4], "by_policy": own_tally})
    scan_flag = own["P=union_all|Q=scan|F=flag"]["query_rows"]
    counts_by_shape = {q: len(scanned(fx, q)) for q in QUERIES}
    rep.check("model.controls", counts_by_shape == {"scan": 6, "filtered": 3, "inner_join": 6, "left_join": 8}
              and own["P=union_all|Q=scan|F=gt0"]["query_bags"]["base"] == [{"row": [None], "count": 2}, {"row": [0], "count": 1},
                                                                              {"row": [1], "count": 2}, {"row": [2], "count": 1}]
              and {b: [r[0] for r in scan_flag[b]] for b in ("true", "false", "unknown")} == {"true": [None, 1], "false": [0, 2], "unknown": [None, 1]}
              and own["P=omit_unknown|Q=scan|F=flag"]["set_equal"] and not own["P=omit_unknown|Q=scan|F=flag"]["tlp_ok"]
              and tv_not("U") == "U" and tv_and("U", "F") == "F" and tv_or("U", "T") == "T" and tv_and("U", "T") == "U",
              {"row_counts": counts_by_shape})

    # ---- stages, plans, Core rows and identities ----
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    card = cmp_["cardinality"]["xlsx"]
    shape_plan = json.loads((root / "planning" / "plan" / "plan.json").read_text())
    rep.check("stage.plans_exact_72", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == card
              and not any(cmp_["budget_blocking"].values()) and all(card[c] == ["EXACT", 72, 72, 72] for c in ("mandatory", "post_sieve", "final"))
              and card["optional_multiplier"][:2] == ["EXACT", 1] and cmp_["constraints_present"] == {"toml": 0, "xlsx": 0}
              and set(cmp_["graph_hash"].values()) == {shape_plan["dependency_graph"]["graph_hash"]},
              {"cardinality": cmp_["cardinality"], "graph_hash": cmp_["graph_hash"], "architect": shape_plan["dependency_graph"]["graph_hash"]})
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
            codes = {s: cell(r, s) for s in SHEETS}
            if any(len(c) != 1 for c in codes.values()):
                raise ValueError(f"row cell arity {codes}")
            cid = case_of([atom(code2val[codes[s][0]]) for s in SHEETS[1:-1]])
            core_text[cid] = join_row([code2val[codes[s][0]] for s in SHEETS], [endings[s] for s in SHEETS])
            row_of[cid] = r["combi_id"]
            decoded.append(cid)
        except (ValueError, KeyError, SyntaxError, AttributeError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "reader": count("reader", "candidates"),
              "executor": count("executor", "processed"), "results_v2": len(db["results_db"]["results_v2"])}
    rep.check("stage.counts", counts["core_fw_final"] == counts["fw_final_rows"] == counts["reader"] == counts["executor"]
              == counts["results_v2"] == EXPECTED and "sieve" not in stages and "--sieve" not in argv, counts)
    rep.check("identity.core_rows", not bad_rows and sorted(decoded) == expected_ids and sorted(cols) == sorted(SHEETS)
              and not any(k.startswith("fw_opt") and v for k, v in tables.items()), {"bad_rows": bad_rows[:3], "columns": sorted(cols)})
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, mapping = {}, True, [], {}
    for name, raw_src in cands.items():
        src = raw_src.decode()
        try:
            calls, sources = parse_candidate(src)
            cid = case_of(calls[:-1])
            if src != core_text.get(cid):
                raise ValueError("candidate text differs from its Core row")
        except (ValueError, SyntaxError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = cid
        mapping[name] = row_of[cid]
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader_equals_core_rows", not errs and sorted(rendered.values()) == expected_ids
              and all(n.split("_")[0] == str(c) for n, c in mapping.items()), {"errors": errs[:3]})
    rep.check("reader.inlined_sources", src_ok, module_sha)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each_repeat_1", len(rv2) == EXPECTED and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    backend = summary.get("sandbox_backend") or ""
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in backend
              and f"image={fix['names']['image']}" in backend and "net=internal:" in backend, {"outcomes": dict(outcomes), "backend": backend})

    # ---- every record ----
    records = {json.loads(l)["id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids and len(records) == EXPECTED)
    bad, fields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_declared_population"))
            continue
        o, fw = own[cid], r["framework"]
        checks = compare_record(r, o)
        checks += [("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("record_keys", sorted(r), REC_KEYS),
                   ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], o["verdict"]),
                   ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("source_sha256", r["source_sha256"], module_sha),
                   ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                   ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    recs = list(records.values())
    tally = {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in POLICIES}
    totals = dict(Counter(r["verdict"] for r in recs))
    rep.check("observations.totals", totals == derived["outcomes"] == {"PASS": 36, "DOMAIN_FAIL": 36} and tally == derived["by_policy"]
              and all(all(r["query_checks"].values()) for r in recs), {"totals": totals, "by_policy": tally})

    # ---- live provenance, SQL log, fixture exports, isolation, sandbox ----
    version = setup["export_setup"]["version"]
    prov_bad = {cid: provenance_problems(r, fixture, version) for cid, r in records.items()}
    prov_bad = {k: v for k, v in prov_bad.items() if v}
    pids = [r["provenance"]["backend_pid"] for r in recs]
    rep.check("provenance.transactions", not prov_bad and len(set(pids)) == EXPECTED,
              {"problems": dict(list(prov_bad.items())[:2]), "distinct_backend_pids": len(set(pids)), "version": version})
    fdir = run / "fixture"
    log = parse_log((fdir / "campaign-sql.log").read_text())
    stmts = [e for e in log if e["level"] == "LOG" and e["msg"].startswith("statement: ")]
    errors = [e for e in log if e["level"] in ("ERROR", "FATAL")]
    by_pid = {}
    for e in stmts:
        by_pid.setdefault(int(e["pid"]), []).append(e)
    data_sql = [e["msg"][len("statement: "):] for e in stmts if e["msg"][len("statement: "):].startswith("SELECT i.val ")]
    log_bad = []
    for cid, r in records.items():
        entries = by_pid.get(r["provenance"]["backend_pid"], [])
        got = [(e["user"], e["db"], e["app"], e["msg"][len("statement: "):]) for e in entries]
        want = [(READER, fixture, ("d14b:" + cid)[:63], s["sql"]) for s in r["provenance"]["statements"]]
        if got != want or len({e["vxid"] for e in entries}) != 1:
            log_bad.append((cid, len(got), len(want)))
    expected_data = Counter(r["sql"][b] for r in recs for b in BRANCHES)
    rep.check("sql_log.corroborates_every_transaction", not log_bad and not errors and len(data_sql) == 288
              and Counter(data_sql) == expected_data and len(stmts) == 7 * EXPECTED and set(by_pid) == set(pids)
              and all(e["user"] == READER for e in stmts),
              {"statements": len(stmts), "data_selects": len(data_sql), "errors": len(errors), "mismatch": log_bad[:3],
               "campaign_log_sha256": sha256((fdir / "campaign-sql.log").read_bytes())})
    ex = {lab: json.loads((fdir / f"export-{lab}.json").read_text()) for lab in ("before", "after")}
    rows = {lab: csv_fixture((fdir / f"items-{lab}.csv").read_text(), (fdir / f"tags-{lab}.csv").read_text()) for lab in ex}
    catalog = (fdir / "catalog-after.tsv").read_text().splitlines()
    kinds = Counter(l.split("\t")[0] for l in catalog)
    rep.check("fixture.exports_before_after", all(rows[lab] == fx for lab in ex)
              and all(ex["before"][k] == ex["after"][k] == setup["export_setup"][k] for k in ("items_sha256", "tags_sha256", "catalog_sha256"))
              and [l for l in catalog if l.startswith("index\t")] == ["index\tfixture.items_pkey"] and kinds.get("trigger", 0) == 4
              and all(re.fullmatch(r"trigger\tRI_ConstraintTrigger_[ac]_\d+", l) for l in catalog if l.startswith("trigger\t"))
              and sorted(l.split("_")[2] for l in catalog if l.startswith("trigger\t")) == ["a", "a", "c", "c"]
              and sorted(l.split("\t")[1] for l in catalog if l.startswith("table\t")) == ["fixture.items", "fixture.tags"]
              and sorted(l.split("\t")[1] for l in catalog if l.startswith("grant\t") and l.split("\t")[1].startswith(READER))
              == [f"{READER}:items:SELECT", f"{READER}:tags:SELECT"],
              {"items_sha256": ex["after"]["items_sha256"], "tags_sha256": ex["after"]["tags_sha256"], "catalog": catalog})
    probe = (setup["probe"].get("result") or {})
    rep.check("fixture.isolation_and_probe", setup["network_internal"] is True and not setup["published_ports"]
              and setup["memory_bytes"] == 256 * 1024 * 1024 and setup["container_networks"] == [fix["names"]["network"]]
              and setup["rows_equal_frozen_fixture"] and setup["probe"]["exit_code"] == 0 and setup["probe"]["attached_targets"] == 1
              and probe.get("provenance", [None])[:4] == [fixture, READER, "repeatable read", "on"] and probe.get("counts") == [6, 6]
              and "read-only transaction" in str(probe.get("write_refused")) and str(probe.get("external_dns")).startswith("blocked")
              and fix["pre_run"]["published_ports"] == {} and fix["pre_run"]["networks"] == [fix["names"]["network"]]
              and fix["pre_run"]["image_id"] == setup["client"]["image_id"] and setup["images"]["postgres"]["id"] == fix["pre_run"]["fixture_image_id"],
              {"setup_sha256": sha256((root / "evidence" / f"fixture-{stamp}" / "setup.json").read_bytes()), "probe": probe})
    pol = json.loads((run / "run" / "handshake__handoff__execution_policy.json").read_text())["policy"]
    run_json = json.loads((run / "run" / "run.json").read_text())
    exe_log = (run / "logs" / "executor.log").read_text(errors="replace")
    origin = ((run_json.get("settings") or {}).get("execution_authorization") or {}).get("origin")     # where run.json records it
    rep.check("sandbox.networked_api_probe_allowlist", pol["profile"] == "networked-api-probe" and pol["network"] == "allowlist"
              and pol["network_allowlist"] == [fixture] and "D14B_FIXTURE" in pol["env_allowlist"] and pol["trusted"] is False
              and pol["backend"] == "container" and origin == "generated"
              and "sandbox allowlist → attached 1 target(s)" in exe_log, {"policy": pol, "origin": origin})

    # ---- mechanisms (from the observed records) ----
    om = [r for r in recs if r["policy"] == "omit_unknown"]
    dd = [r for r in recs if r["policy"] == "dedup_union"]
    hidden = sorted(r["id"] for r in recs if r["verdict"] != "PASS" and r["set_equal"])
    rep.check("mechanism.adapters", all(r["verdict"] == "PASS" for r in recs if r["policy"] == "union_all")
              and all((r["verdict"] == "PASS") == (not r["query_rows"]["unknown"]) for r in om)
              and all((r["verdict"] == "PASS") == (len({x[0] for x in r["query_rows"]["base"]}) == len(r["query_rows"]["base"])) for r in dd)
              and records["P=omit_unknown|Q=scan|F=flag"]["set_equal"] and not records["P=omit_unknown|Q=scan|F=flag"]["tlp_ok"]
              and len(hidden) == 23,
              {"omit_unknown_passes": sorted(r["id"] for r in om if r["verdict"] == "PASS"),
               "dedup_union_passes": sorted(r["id"] for r in dd if r["verdict"] == "PASS"), "failures_with_equal_sets": len(hidden)})

    # ---- envelope and provenance ----
    need = ["--lang", "py", "--execution-policy-profile", "networked-api-probe", "--candidate-origin", "generated", "--repeat", "1",
            "--executor-workers", "1", "--sandbox-network-allowlist", fixture, "--sandbox-candidate-env", f"D14B_FIXTURE={fixture}", *BUDGET_ARGS]
    env = json.loads((run / "commands.json").read_text())[0]["env"]
    rep.check("envelope.command", all(t in argv for t in need) and "--override-budget" not in argv and "--sieve" not in argv
              and "trusted-local" not in argv and Path(argv[2]).name == "demo.xlsx"
              and all(argv[argv.index(BUDGET_ARGS[i]) + 1] == BUDGET_ARGS[i + 1] for i in range(0, 8, 2))
              and env == {"JAVA_TOOL_OPTIONS": "-Xmx2g", "BUNDLE_SANDBOX_IMAGE": fix["names"]["image"]}, {"argv": argv[2:], "env": env})
    rep.check("envelope.db", re.fullmatch(r"as0927_d14b_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not manifest["databases"]["name"].startswith("as0927_d14b_sql_")
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values())
              and all(manifest["databases"]["exists_after"].values()) and re.fullmatch(r"as0927_d14b_sql_[0-9a-z]+", fixture) is not None,
              manifest["databases"])
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    new = manifest["storage_after"]["new_docker_bytes"] + manifest.get("run_dir_bytes", 0)
    rep.check("envelope.new_storage_below_200MB", new < NEW_STORAGE_LIMIT,
              {"new_docker_bytes": manifest["storage_after"]["new_docker_bytes"], "run_dir_bytes": manifest.get("run_dir_bytes"), "total": new,
               "before": manifest["storage_before"], "after": manifest["storage_after"]})
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    build = json.loads((root / "spec" / "build.json").read_text())
    rep.check("provenance.build_record", build["module_sha256"] == module_sha
              and build["files"]["spec.toml"] == sha256((run / "inputs" / "spec.toml").read_bytes()) == sha256((root / "spec" / "spec.toml").read_bytes())
              and build["files"]["demo.xlsx"] == sha256((run / "inputs" / "demo.xlsx").read_bytes()), build["files"])
    comp = {a["kind"]: a for st in stages.values() for a in st.get("artifacts", []) if a["kind"].startswith("component.")}
    comp_ok = {k: Path(a["path"]).is_file() and sha256(Path(a["path"]).read_bytes()) == a["sha256"] for k, a in comp.items()}
    rep.check("provenance.framework_components_unchanged", comp_ok and all(comp_ok.values()),
              {k: {"sha256": a["sha256"], "unchanged": comp_ok[k]} for k, a in comp.items()})
    x, t = fg.load_spec(root / "spec" / "demo.xlsx"), fg.load_spec(root / "spec" / "spec.toml")
    xv, tv = spec_view(x), spec_view(t)
    rep.check("provenance.xlsx_toml_core_input", sheets == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"]
              == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"] and xv == tv and not xv["constraints"] and not xv["params"]
              and not x.sidecar_path, {"slots_equal": xv["slots"] == tv["slots"], "chains_equal": xv["chains"] == tv["chains"]})
    strata = {p: {q: dict(Counter(r["verdict"] for r in recs if r["policy"] == p and r["query"] == q)) for q in QUERIES} for p in POLICIES}
    return rep, {"stage_counts": counts, "totals": totals, "by_policy": tally, "strata": strata, "failures_with_equal_sets": hidden,
                 "sql_log": {"statements": len(stmts), "data_selects": len(data_sql)}, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"],
                    "query_rows": {b: [x[0] for x in r["query_rows"][b]] for b in BRANCHES},
                    "combined_rows": [x[0] for x in r["combined_rows"]], "tlp_ok": r["tlp_ok"], "set_equal": r["set_equal"],
                    "verdict": r["verdict"], "backend_pid": r["provenance"]["backend_pid"], "snapshot": r["provenance"]["snapshot"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d14b.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d14b.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "strata", "failures_with_equal_sets", "sql_log")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
