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

"""Independent offline verifier for one D5 phase A evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root D5-DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py or runtime.py, never connects to a database,
never executes a candidate (candidates and dictionary values are parsed with `ast`). The 24 trees,
each policy's output and each verdict are re-derived here from CONTRACT-A.md. --inputs-root is the
D5 folder (or an archive of it): it holds CONTRACT-A.md, architect-derived-A.json and phase-a/.
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
POLICIES = ("correct", "reverse_pair", "wrong_field")
OPS = ("A", "M", "S", "N")
FIELDS = ("x", "y")
INPUT = {"x": 2, "y": 5}
CHAIN = ["FW_Combi(2)", "FW_Permut()", "FW_Group", "FW_Cartes(FIELD)"]
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("phase-a/verify.py", "phase-a/replay.py")
WITNESSES = {"correct_AM_x": "A|correct|OPS=AM|FIELD=x", "reverse_pair_AM_x": "A|reverse_pair|OPS=AM|FIELD=x",
             "wrong_field_AM_x": "A|wrong_field|OPS=AM|FIELD=x", "reverse_pair_AS_x": "A|reverse_pair|OPS=AS|FIELD=x"}


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
def apply(op, v):
    return {"A": v + 1, "M": v * 2, "S": v - 3, "N": -v}[op]


def run_tree(ops, field):
    rec, trace = dict(INPUT), []
    for op in ops:
        rec[field] = apply(op, rec[field])
        trace.append({"op": op, "field": field, "value": rec[field]})
    return rec, trace


def model(tree, policy):
    """(expected, reference trace, observed under policy, SUT trace, verdict)."""
    expected, ref = run_tree(tree["ops"], tree["field"])
    ops = tree["ops"][::-1] if policy == "reverse_pair" else tree["ops"]
    field = ({"x": "y", "y": "x"}[tree["field"]]) if policy == "wrong_field" else tree["field"]
    observed, trace = run_tree(ops, field)
    return expected, ref, observed, trace, "PASS" if observed == expected else "DOMAIN_FAIL"


def trees():
    """P(4,2) ordered pairs of distinct operations x 2 fields = 24, via the contract's own chain:
    six unordered pairs, each permuted, then each ordered pair bound to each field."""
    pairs = list(itertools.combinations(OPS, 2))
    ordered = [list(p) for pair in pairs for p in itertools.permutations(pair)]
    return pairs, ordered, [{"field": f, "ops": o} for o in ordered for f in FIELDS]


def case_id(policy, tree):
    return f"A|{policy}|OPS={''.join(tree['ops'])}|FIELD={tree['field']}"


def call_of(src):
    """(function name, literal argument) of a one-call fragment, parsed, never executed."""
    body = ast.parse(src).body
    if len(body) != 1 or not isinstance(body[0], ast.Expr) or not isinstance(body[0].value, ast.Call):
        raise ValueError(f"not a single call: {src!r}")
    call = body[0].value
    return call.func.id, ast.literal_eval(call.args[0])


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    """The fragment calls in rendered order, the policy, the tree and the inlined sources."""
    calls, sources, phase, begun = [], None, None, False
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Name) and f.id in ("impl", "push_op", "bind"):
                calls.append([f.id, ast.literal_eval(node.value.args[0])])
            elif isinstance(f, ast.Attribute) and f.attr == "begin":
                begun = True
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D5_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase = ast.literal_eval(node.value.args[0])
    shape = [c[0] for c in calls]
    if not begun or phase != "A" or shape != ["impl", "push_op", "push_op", "bind"]:
        raise ValueError(f"fragment order {shape} begun={begun} phase={phase}")
    tree = {"field": calls[3][1], "ops": [calls[1][1], calls[2][1]]}
    return case_id(calls[0][1], tree), calls, sources


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived-A.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / "phase-a" / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    pairs, ordered, all_trees = trees()
    expected_ids = sorted(case_id(p, t) for t in all_trees for p in POLICIES)
    derived_counts = {"Combi2": len(pairs), "Permut": len(ordered), "grouped_Cartes": len(all_trees), "cases": len(expected_ids)}
    rep.check("space.expected_equals_frozen", expected_ids == sorted(frozen) and derived_counts == derived["counts"]
              and derived["input_record"] == INPUT, derived_counts)
    own = {case_id(p, t): (t, p, model(t, p)) for t in all_trees for p in POLICIES}
    rep.check("space.frozen_predictions_equal_own_model",
              all(frozen[c]["tree"] == t and frozen[c]["expected"] == m[0] and frozen[c]["predicted"] == m[2]
                  and frozen[c]["predicted_outcome"] == m[4] and frozen[c]["policy"] == p for c, (t, p, m) in own.items()))

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    rep.check("stage.plans", cmp_["same_nodes"] and cmp_["edges"]["xlsx"] == [{"dst": "FIELD", "kind": "cartes", "src": "OPS"}]
              and cmp_["cardinality"]["toml"] == cmp_["cardinality"]["xlsx"] and not any(cmp_["budget_blocking"].values())
              and all(c["final"][:2] == ["EXACT", 72] and c["mandatory"][:2] == ["EXACT", 72] for c in cmp_["cardinality"].values())
              and all(o.get("mode") == "EXACT" and o.get("value") == 24 for o in cmp_["ops_slot"].values()),
              {"cardinality": cmp_["cardinality"], "ops_slot": cmp_["ops_slot"], "edges": cmp_["edges"]})

    # ---- Core: the effective chain as Core logged it, and the rows it retained ----
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    before = {int(m.group(1)): m.group(2) for m in re.finditer(
        r"\[DIAG-PASS\] Sheet OPS \(key=\d+\) directive\[(\d+)\]='([^']*)' isCombi2=\S+ BEFORE", core_log)}
    after = {int(m.group(1)): {"fw_rows": int(m.group(2)), "fw2_rows": int(m.group(3))} for m in re.finditer(
        r"\[DIAG-PASS\] Sheet OPS \(key=\d+\) directive\[(\d+)\] AFTER: isCombi2=\S+ fw_rows=(\d+) fw2_rows=(\d+)", core_log)}
    per_sheet = {m.group(1): int(m.group(2)) for m in re.finditer(
        r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", core_log)}
    chain = {"directives": [before.get(i) for i in range(len(before))], "after": after, "per_sheet_after_distinctify": per_sheet}
    rep.check("core.effective_chain_log", chain["directives"] == CHAIN and after.get(0, {}).get("fw_rows") == 6
              and after.get(1, {}).get("fw2_rows") == 12 and after.get(3, {}).get("fw_rows") == 12
              and after.get(3, {}).get("fw2_rows") == 24 and per_sheet.get("OPS") == 24
              and {k: per_sheet.get(k) for k in ("HEAD", "IMPL", "TAIL")} == {"HEAD": 1, "IMPL": 3, "TAIL": 1}, chain)

    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    code2val = {int(r["bigint"]): r["value"] for r in tables["NumberToValue1"]}
    counts = {"core_fw_final": count("core", "fw_final"), "fw_final_rows": len(frows), "fw_final_columns": sorted(cols),
              "reader": count("reader", "candidates"), "executor": count("executor", "processed"),
              "results_v2": len(db["results_db"]["results_v2"]), "chain": chain}
    rep.check("core.fw_final_excludes_field", sorted(cols) == ["HEAD", "IMPL", "OPS", "TAIL"] and len(frows) == 72
              and counts["core_fw_final"] == 72 and 1 * 3 * per_sheet.get("OPS", 0) * 1 == 72
              and not any(k.startswith("fw_opt") and rows for k, rows in tables.items()), counts)

    def cell(row, sheet):
        return list(row.get(cols[sheet]) or base.get(cols[sheet]) or [])
    op_codes = sorted(c for c, v in code2val.items() if v.startswith("push_op("))
    field_codes = sorted(c for c, v in code2val.items() if v.startswith("bind("))
    encoded, decoded_ids, bad_rows = {}, [], []
    for r in frows:
        codes = cell(r, "OPS")
        try:
            frags = [call_of(code2val[c]) for c in codes]
            impl = call_of(code2val[cell(r, "IMPL")[0]])
        except (KeyError, ValueError, SyntaxError) as exc:
            bad_rows.append((r["combi_id"], str(exc)))
            continue
        if [f[0] for f in frags] != ["push_op", "push_op", "bind"] or impl[0] != "impl" \
                or codes[0] not in op_codes or codes[1] not in op_codes or codes[2] not in field_codes:
            bad_rows.append((r["combi_id"], frags))
            continue
        tree = {"field": frags[2][1], "ops": [frags[0][1], frags[1][1]]}
        encoded[tuple(codes)] = {"codes": codes, "values": [code2val[c] for c in codes], "tree": tree}
        decoded_ids.append(case_id(impl[1], tree))
    ops_rows = sorted((e["tree"]["ops"], e["tree"]["field"]) for e in encoded.values())
    rep.check("core.decoded_ops_rows_equal_enumeration", not bad_rows and len(encoded) == 24
              and ops_rows == sorted((t["ops"], t["field"]) for t in all_trees) and len(op_codes) == 4 and len(field_codes) == 2,
              {"bad_rows": bad_rows[:5], "distinct_ops_rows": len(encoded), "op_codes": op_codes, "field_codes": field_codes})
    rep.check("identity.core", sorted(decoded_ids) == expected_ids and len(set(decoded_ids)) == 72)

    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs = {}, True, []
    for name, data in cands.items():
        try:
            ident, calls, sources = parse_candidate(data.decode())
        except (ValueError, SyntaxError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = ident
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids and counts["reader"] == 72, errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == 72 and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values())
              and counts["executor"] == counts["results_v2"] == 72)
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    bad, fields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_frozen_set"))
            continue
        tree, pol, (exp, ref, obs, trace, verdict) = own[cid]
        fz, fw = frozen[cid], r["framework"]
        checks = [("schema", r["schema"], "d5a.observation/v1"), ("phase", r["phase"], "A"), ("policy", r["policy"], pol),
                  ("tree", r["tree"], tree), ("frozen_tree", r["tree"], fz["tree"]), ("input", r["input"], INPUT),
                  ("fragments", r["fragments"], [["push_op", tree["ops"][0]], ["push_op", tree["ops"][1]], ["bind", tree["field"]]]),
                  ("expected", r["expected"], exp), ("frozen_expected", r["expected"], fz["expected"]),
                  ("observed", r["observed"], obs), ("frozen_predicted", r["observed"], fz["predicted"]),
                  ("observed_types", [type(r["observed"][k]).__name__ for k in sorted(r["observed"])], ["int", "int"]),
                  ("sut_trace", r["sut_trace"], trace), ("reference_trace", r["reference_trace"], ref),
                  ("traces_equal", r["traces_equal"], trace == ref),
                  ("verdict", r["verdict"], verdict), ("frozen_outcome", r["verdict"], fz["predicted_outcome"]),
                  ("fw_var", r["fw_var"], 0 if verdict == "PASS" else 2), ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]),
                  ("outcome", fw["outcome"], verdict), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                  ("source_sha256", r["source_sha256"], module_sha),
                  ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    rep.check("observations.totals", dict(totals) == derived["outcomes"] and by_policy == derived["by_policy"],
              {"totals": dict(totals), "by_policy": by_policy})
    commute = sorted(k for k, r in records.items() if r["policy"] == "reverse_pair" and r["verdict"] == "PASS")
    own_commute = sorted(case_id("reverse_pair", t) for t in all_trees
                         if all(apply(t["ops"][1], apply(t["ops"][0], v)) == apply(t["ops"][0], apply(t["ops"][1], v)) for v in (2, 5)))
    rep.check("observations.reverse_pair_passes_only_commuting_pairs",
              commute == own_commute and len(commute) == 8 and {"".join(sorted(records[k]["tree"]["ops"])) for k in commute} == {"AS", "MN"}
              and all(not records[k]["traces_equal"] for k in commute),
              {"passing": commute, "note": "output equivalence for these inputs; the traces differ"})
    extra = {"encoded_ops_rows": sorted(encoded.values(), key=lambda e: e["codes"]), "reverse_pair_passes": commute}

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "500", "--budget-final-candidates", "500", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "1200"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv
              and "--override-budget" not in argv and Path(argv[2]).name == "demo.xlsx", argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d5a_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = core_log + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"]
              == fg.workbook_to_json(root / "phase-a" / "spec" / "demo.xlsx")["sheets"])
    return rep, {"stage_counts": counts, "totals": dict(totals), "by_policy": by_policy, "extra": extra, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "tree": r["tree"],
                    "expected": r["expected"], "observed": r["observed"], "sut_trace": r["sut_trace"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d5a.witnesses/v1", "run": run.name, "witnesses": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--inputs-root", type=Path, default=HERE.parent)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    run = a.run.resolve()
    out_dir = (a.out or run).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rep, data = verify(run, a.inputs_root.resolve())
    doc = {"schema": "d5a.verification/v1", "run": run.name, "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
