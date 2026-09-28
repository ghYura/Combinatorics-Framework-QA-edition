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

"""Independent offline verifier for one D5 phase B evidence directory (campaign B1 or B2).

    python verify.py --run evidence/<run-id> [--inputs-root PHASE-B-DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py or runtime.py, never connects to a database,
never executes a candidate (candidates and dictionary values are parsed with `ast`). The eight
trees and each policy's outputs are re-derived here; Core's rows are re-derived by construct.py
(an independent model of the Framework's construction) from the live dictionary and compared
with the rows Core actually wrote.
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
sys.path.insert(0, str(HERE))
import construct  # noqa: E402  (the construction model; not the SUT, reference or runtime)

GEN = Path(__file__).resolve().parents[3] / "generator_trunk"
POLICIES = ("correct", "flatten_scope", "leak_scope")
INPUT = {"x": 2, "y": 5}
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
EXPECTED = {"B1": 24, "B2": 3}
STRUCT = {"B1": "ROOT", "B2": "BUNDLE"}
WITNESSES = {"B1": {f"{p}_AAN": f"B1|{p}|ZIP=A|CAT=A|TAIL=N" for p in POLICIES},
             "B2": {"correct_bundle": "B2|correct|BUNDLE=all8"}}


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


# ---- the contract's interpreter, re-derived ----
def own_eval(tree, policy):
    rec, trace, cur = dict(INPUT), [], ["x"]
    step = {"A": lambda v: v + 1, "M": lambda v: v * 2, "S": lambda v: v - 3, "N": lambda v: -v}

    def run(nodes, field):
        for n in nodes:
            if isinstance(n, str):
                f = cur[0] if policy == "leak_scope" else field
                rec[f] = step[n](rec[f])
                trace.append({"op": n, "field": f, "value": rec[f]})
            elif policy == "correct":
                run(n["children"], n["scope"])
            elif policy == "flatten_scope":
                run(n["children"], field)
            else:
                cur[0] = n["scope"]
                run(n["children"], cur[0])
    run(tree, "x")
    return rec, trace


def own_trees():
    return {f"ZIP={z}|CAT={c}|TAIL={t}": [{"scope": "x", "children": [{"scope": "y", "children": [z, "N"]}]}, "S",
                                         {"scope": "x", "children": [c]}, t]
            for z, c, t in itertools.product("AM", "AM", "NS")}


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    """(policy, phase, fragment texts in order, inlined sources): one statement per fragment."""
    policy, phase, sources, begun, frags = None, None, None, False, []
    for node in ast.parse(src).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr == "begin":
                begun = True
            elif isinstance(f, ast.Name) and f.id == "impl":
                if policy is not None or frags:
                    raise ValueError("impl out of place")
                policy = ast.literal_eval(node.value.args[0])
            elif isinstance(f, ast.Name):
                frags.append(ast.unparse(node) + ";\n")
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "_D5_SOURCES":
                sources = ast.literal_eval(node.value)
            elif node.targets[0].id == "_verdict":
                phase = ast.literal_eval(node.value.args[0])
    if not begun or policy is None:
        raise ValueError("no begin()/impl()")
    return policy, phase, frags, sources


def log_facts(core_log, key_name):
    before, after = {}, {}
    for m in re.finditer(r"\[DIAG-PASS\] Sheet (\S+) \(key=\d+\) directive\[(\d+)\]='(.*?)' isCombi2=\S+ BEFORE", core_log, re.S):
        before.setdefault(m.group(1), {})[int(m.group(2))] = m.group(3)
    for m in re.finditer(r"\[DIAG-PASS\] Sheet (\S+) \(key=\d+\) directive\[(\d+)\] AFTER: isCombi2=\S+ fw_rows=(\d+) fw2_rows=(\d+)", core_log):
        after.setdefault(m.group(1), {})[int(m.group(2))] = [int(m.group(3)), int(m.group(4))]
    final = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[DIAG\] Sheet (\S+) \(key=\d+\) table=\S+: (\d+) rows AFTER distinctify", core_log)}
    braces = {}
    for m in re.finditer(r"FW_\( brace: key=(\d+) formula=(\S+) excl1=(\S*?)(\[[NG]\])? excl2=(\S*?)(\[[NG]\])?\s*$", core_log, re.M):
        name = lambda k: key_name.get(int(k)) if k and k != "null" else None      # noqa: E731
        braces[key_name[int(m.group(1))]] = {"formula": m.group(2), "excl1": name(m.group(3)), "excl1_mark": m.group(4) or "",
                                            "excl2": name(m.group(5)), "excl2_mark": m.group(6) or ""}
    nested = [(m.group(1), m.group(2), m.group(3), m.group(4)) for m in re.finditer(
        r"resolveNestedFwBrace: (excluded[12]) nested (FW_\(\)G?) → '(\w+)' \(grouped=(\w+)\)", core_log)]
    summary = {}
    for m in re.finditer(r"FW_ReplaceRE summary — sheet (\S+) \(key=\d+\): rows seen=(\d+) rewritten=(\d+) dropped=(\d+); rows changed per pattern: (.*)$",
                         core_log, re.M):
        summary[m.group(1)] = {"seen": int(m.group(2)), "rewritten": int(m.group(3)), "dropped": int(m.group(4)),
                               "per_pattern": [(p, int(n)) for p, n in re.findall(r'"(.*?)"=(\d+)', m.group(5))]}
    completed = [key_name[int(k)] for k in re.findall(r"FW_\( brace: completed for key=(\d+)", core_log)]
    return {"before": before, "after": after, "final": final, "braces": braces, "nested": nested,
            "replace_summary": summary, "braces_completed": completed}


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    campaign = manifest["campaign"]
    struct = STRUCT[campaign]
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    trees = own_trees()
    if campaign == "B1":
        frozen = {c["id"]: c for c in derived["B1_cases"]}
        expected_ids = sorted(f"B1|{p}|{t}" for t in trees for p in POLICIES)
        own_ok = all(frozen[f"B1|{p}|{t}"]["tree"] == tr and frozen[f"B1|{p}|{t}"]["expected"] == own_eval(tr, "correct")[0]
                     and frozen[f"B1|{p}|{t}"]["predicted"] == own_eval(tr, p)[0]
                     and frozen[f"B1|{p}|{t}"]["predicted_outcome"] == ("PASS" if own_eval(tr, p)[0] == own_eval(tr, "correct")[0] else "DOMAIN_FAIL")
                     for t, tr in trees.items() for p in POLICIES)
    else:
        frozen = {c["id"]: c for c in derived["B2_cases"]}
        expected_ids = sorted(f"B2|{p}|BUNDLE=all8" for p in POLICIES)
        own_ok = all(frozen[f"B2|{p}|BUNDLE=all8"]["predicted"] == {t: own_eval(tr, p)[0] for t, tr in trees.items()}
                     and frozen[f"B2|{p}|BUNDLE=all8"]["predicted_outcome"]
                     == ("PASS" if all(own_eval(tr, p)[0] == own_eval(tr, "correct")[0] for tr in trees.values()) else "DOMAIN_FAIL")
                     for p in POLICIES)
    rep.check("space.frozen_equals_own_model", own_ok and sorted(frozen) == expected_ids and len(trees) == 8
              and {t["id"]: t["tree"] for t in derived["trees"]} == trees
              and all(t["expected"] == own_eval(trees[t["id"]], "correct")[0] for t in derived["trees"]),
              {"expected_ids": len(expected_ids)})

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    ps = cmp_["per_slot"]["xlsx"]
    bounds = {k: [ps[k].get("mode"), ps[k].get("lower"), ps[k].get("upper")] for k in ("E1", "E2", "E3", "JZIP", "JCAT", "ROOT", "BUNDLE") if k in ps}
    rep.check("stage.plans", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == cmp_["cardinality"]["xlsx"]
              and not any(cmp_["budget_blocking"].values())
              and (cmp_["cardinality"]["xlsx"]["final"][2] or 0) <= EXPECTED[campaign] <= cmp_["cardinality"]["xlsx"]["final"][3] <= 500
              and bounds["E2"] == ["EXACT", 7, 7] and bounds["E3"] == ["EXACT", 2, 2],
              {"final": cmp_["cardinality"]["xlsx"]["final"], "per_slot": bounds,
               "nested_edges": [e for e in cmp_["normal_graph"]["xlsx"]["edges"] if e[1] == "brace_nested_operand"]})

    # ---- dictionary: align the Core input workbook with NumberToValue1, code by code ----
    db = json.loads((run / "db-export.json").read_text())
    tables = db["main_db"]["tables"]
    books = sorted((run / "run").glob("core_input__*.xlsx"))
    data, group_cell, seq = construct.workbook_sheets(books[0])
    dictionary = sorted((int(r["bigint"]), r["value"]) for r in tables["NumberToValue1"])
    flat = [(name, i, v) for name, vals in data for i, v in enumerate(vals)]
    aligned = len(flat) == len(dictionary) and all(v == dv for (_, _, v), (_, dv) in zip(flat, dictionary)) \
        and [c for c, _ in dictionary] == list(range(len(data) + 1, len(data) + 1 + len(flat)))
    codes = {}
    for (name, _, _), (code, _) in zip(flat, dictionary):
        codes.setdefault(name, []).append(code)
    code2val = dict(dictionary)
    code2sheet = {c: n for n, cs in codes.items() for c in cs}
    key_name = {i + 1: name for i, (name, _) in enumerate(data)}
    rep.check("core.dictionary_alignment", aligned, {"sheets": len(data), "codes": len(dictionary),
                                                     "token_first_codes": {t: codes[t][0] for t in codes if t not in ("HEAD", "IMPL", "TAIL")}})

    # ---- the construction model on live codes ----
    model = construct.construct(codes, group_cell)
    tmp = codes["TMP"][0]
    e1_ok = all(r["row"] == [codes["OPEN_X"][0], c, codes["CLOSE"][0]]
                and r["steps"] == [f"[[{c}]]", f"[[{tmp}, {c}]]", f"[[{codes['OPEN_X'][0]}, {c}]]", f"[[{codes['OPEN_X'][0]}, {c}, {codes['CLOSE'][0]}]]"]
                for c, r in model["E1"].items())
    rep.check("construction.rewrite_order", e1_ok and len(model["E1"]) == 2
              and [r["splice"][0] for r in model["rewrites"]] == ["TMP", "OPEN_X", "CLOSE"]
              and all(v["contains_TMP"] for v in model["reversed_1_2"].values()),
              {"rewrites": model["rewrites"], "E1": model["E1"], "reversed_1_2 (offline only)": model["reversed_1_2"]})
    rep.check("construction.e2_length_filter", len(model["E2_first_pass"]) == 8 and model["E2_lengths"] == [1, 1, 1, 2, 2, 2, 3]
              and len(model["JZIP"]) == 2 and all(len(r) == 6 for r in model["JZIP"]),
              {"E2_lengths": model["E2_lengths"], "JZIP": model["JZIP"]})
    rep.check("construction.joins", len(model["JCAT"]) == 4 and all(len(r) == 4 for r in model["JCAT"])
              and len(model["ROOT"]) == 8 and all(len(r) == 13 for r in model["ROOT"]) and all(tmp not in r for r in model["ROOT"]),
              {"JCAT": model["JCAT"], "ROOT_rows": len(model["ROOT"])})

    # ---- Core's own logs: effective program, nesting, rewrites, counts ----
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    lf = log_facts(core_log, key_name)
    want_final = {"E1": 2, "E2": 7, "E3": 2, "JZIP": 2, "JCAT": 4, "ROOT": 8, **({"BUNDLE": 1, "SEAL": 1} if campaign == "B2" else {})}
    e1_dirs = [lf["before"].get("E1", {}).get(i, "") for i in range(4)]
    want_braces = {"JZIP": {"formula": "1:1", "excl1": "E1", "excl1_mark": "", "excl2": "E2", "excl2_mark": ""},
                   "JCAT": {"formula": "M:N", "excl1": "E1", "excl1_mark": "", "excl2": "E3", "excl2_mark": ""},
                   "ROOT": {"formula": "M:N", "excl1": "JZIP", "excl1_mark": "", "excl2": "JCAT", "excl2_mark": "[N]"}}
    want_nested = [("excluded2", "FW_()", "JCAT", "false")]
    if campaign == "B2":
        want_braces["BUNDLE"] = {"formula": "M:N", "excl1": "ROOT", "excl1_mark": "[G]", "excl2": "SEAL", "excl2_mark": ""}
        want_nested.append(("excluded1", "FW_()G", "ROOT", "true"))
    summ = lf["replace_summary"].get("E1", {})
    rep.check("core.effective_program_log",
              e1_dirs[0] == "FW_Combi(1)" and e1_dirs[1] == "FW_Combi(1)" and e1_dirs[2].startswith("FW_Group") and e1_dirs[3] == "FW_Combi(1)"
              and lf["after"]["E1"][0][0] == 2 and lf["after"]["E1"][3][1] == 2
              and lf["before"]["E2"][0] == "FW_Subsets" and lf["after"]["E2"][0][0] == 8 and lf["after"]["E2"][1][1] == 7
              and {k: lf["final"].get(k) for k in want_final} == want_final
              and {k: lf["braces"].get(k) for k in want_braces} == want_braces and sorted(lf["nested"]) == sorted(want_nested)
              and summ.get("seen") == 2 and summ.get("rewritten") == 2 and summ.get("dropped") == 0
              and [p for p, _ in summ.get("per_pattern", [])] == [r["pattern"] for r in model["rewrites"]]
              and all(n == 2 for _, n in summ.get("per_pattern", [])),
              {k: lf[k] for k in ("braces", "nested", "replace_summary", "braces_completed")} | {
                  "final_counts": {k: lf["final"].get(k) for k in want_final}, "E1_directives": e1_dirs,
                  "E1_after": lf["after"].get("E1"), "E2_after": lf["after"].get("E2")})

    # ---- flags in the Core input: E1 kept for both consumers, intermediates excluded ----
    flags = {}
    for row in seq:
        cells = [c for c in row if isinstance(c, str) and c]
        if cells:
            flags.setdefault(cells[0], set()).update(c for c in cells[1:] if c in ("FW_Exclude", "FW_Reuse", "FW_ReuseTableOnly", "FW_Optional"))
    inter = ["TMP", "OPEN_X", "CLOSE", "E1", "E2", "E3", "PIPE_OPEN", "REL_S", "PIPE_CLOSE", "JZIP", "JCAT"] + (
        ["ROOT", "BUNDLE_OPEN", "SEAL", "BUNDLE_CLOSE"] if campaign == "B2" else [])
    consumers = {k: [b for b, v in want_braces.items() if k in (v["excl1"], v["excl2"])] for k in ("E1", "E2", "E3", "JZIP", "JCAT", "ROOT", "SEAL")}
    rep.check("core.flags_retention_and_exclusion", "FW_Reuse" in flags["E1"] and "FW_Exclude" in flags["E1"]
              and all("FW_Exclude" in flags[k] for k in inter) and not any("FW_Exclude" in flags[k] or "FW_Optional" in flags[k] for k in ("HEAD", "IMPL", struct, "TAIL"))
              and consumers["E1"] == ["JZIP", "JCAT"] and set(want_braces) <= set(lf["braces_completed"]),
              {"flags": {k: sorted(v) for k, v in flags.items() if k in inter + [struct]}, "consumers": consumers})

    # ---- fw_final: only the structural result varies; decode it ----
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    def cell(row, sheet):
        return list(row.get(cols[sheet]) or base.get(cols[sheet]) or [])
    placeholders = {codes[s][0] for s in ("JZIP", "JCAT", "ROOT", "BUNDLE") if s in codes}
    distinct = sorted({tuple(cell(r, struct)) for r in frows})
    decoded, bad_rows, order = [], [], []
    model_root = {tuple(r) for r in model["ROOT"]}
    for r in frows:
        row = cell(r, struct)
        try:
            calls, ts = construct.decode_tree([code2val[c] for c in row])
            ids = [construct.tree_id(t) for t in ts]
            impl = ast.literal_eval(ast.parse(code2val[cell(r, "IMPL")[0]]).body[0].value.args[0])
        except (KeyError, ValueError, SyntaxError) as exc:
            bad_rows.append((r["combi_id"], str(exc)))
            continue
        decoded.append(f"B1|{impl}|{ids[0]}" if campaign == "B1" else f"B2|{impl}|BUNDLE=all8")
    if campaign == "B1":
        struct_ok = len(distinct) == 8 and {tuple(d) for d in distinct} == model_root and all(len(d) == 13 for d in distinct)
        detail = {"distinct_rows": len(distinct), "row_length": sorted({len(d) for d in distinct})}
    else:
        (brow,) = distinct if len(distinct) == 1 else (None,)
        chunks = [tuple(brow[1 + 13 * i: 14 + 13 * i]) for i in range(8)] if brow else []
        order = [construct.tree_id(construct.decode_tree([code2val[c] for c in ch])[1][0]) for ch in chunks] if brow else []
        struct_ok = brow is not None and len(brow) == 107 and brow[0] == codes["BUNDLE_OPEN"][0] and brow[-2] == codes["SEAL"][0] \
            and brow[-1] == codes["BUNDLE_CLOSE"][0] and set(chunks) == model_root and len(set(chunks)) == 8
        detail = {"bundle_length": len(brow) if brow else None, "aggregated_order": order}
    rep.check("core.fw_final_structural_rows", sorted(cols) == sorted(["HEAD", "IMPL", struct, "TAIL"]) and len(frows) == EXPECTED[campaign]
              and count("core", "fw_final") == EXPECTED[campaign] and not bad_rows and struct_ok
              and not any(tmp in cell(r, struct) or placeholders & set(cell(r, struct)) for r in frows)
              and not any(k.startswith("fw_opt") and rows for k, rows in tables.items()),
              {"columns": sorted(cols), "rows": len(frows), "bad_rows": bad_rows[:3], **detail})
    rep.check("identity.core", sorted(decoded) == expected_ids and len(set(decoded)) == EXPECTED[campaign])

    # ---- Reader: rendered candidates ----
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, calls_by_cand, src_ok, errs = {}, {}, True, []
    for name, data_ in cands.items():
        try:
            policy, phase, frags, sources = parse_candidate(data_.decode())
            calls, ts = construct.decode_tree(frags)
            ids = [construct.tree_id(t) for t in ts]
            if phase != campaign or (campaign == "B1" and len(ts) != 1) or (campaign == "B2" and (
                    len(ts) != 8 or [c[0] for c in calls[:1] + calls[-2:]] != ["begin_bundle", "seal_bundle", "end_bundle"])):
                raise ValueError(f"shape: phase={phase} trees={len(ts)}")
        except (ValueError, SyntaxError, KeyError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = f"B1|{policy}|{ids[0]}" if campaign == "B1" else f"B2|{policy}|BUNDLE=all8"
        calls_by_cand[name] = (calls, ts, ids)
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader", not errs and sorted(rendered.values()) == expected_ids and count("reader", "candidates") == EXPECTED[campaign], errs[:3])
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == EXPECTED[campaign] and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values())
              and count("executor", "processed") == EXPECTED[campaign])
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    # ---- every record ----
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    bad, fields = [], 0
    def tree_checks(cid, res, tid, pol):
        exp, ref = own_eval(trees[tid], "correct")
        obs, trace = own_eval(trees[tid], pol)
        verdict = "PASS" if obs == exp else "DOMAIN_FAIL"
        return [(f"{tid}.tree_id", res["tree_id"], tid), (f"{tid}.tree", res["tree"], trees[tid]), (f"{tid}.input", res["input"], INPUT),
                (f"{tid}.expected", res["expected"], exp), (f"{tid}.observed", res["observed"], obs),
                (f"{tid}.observed_types", [type(res["observed"][k]).__name__ for k in sorted(res["observed"])], ["int", "int"]),
                (f"{tid}.sut_trace", res["sut_trace"], trace), (f"{tid}.reference_trace", res["reference_trace"], ref),
                (f"{tid}.verdict", res["verdict"], verdict)]
    for cid, r in records.items():
        if cid not in frozen:
            bad.append((cid, "not_in_frozen_set"))
            continue
        fz, fw = frozen[cid], r["framework"]
        pol = fz["policy"]
        calls, ts, ids = calls_by_cand.get(fw["source_ref"], ([], [], []))
        checks = [("schema", r["schema"], "d5b.observation/v1"), ("phase", r["phase"], campaign), ("policy", r["policy"], pol),
                  ("fragments", r["fragments"], calls), ("rendered_identity", rendered.get(fw["source_ref"]), cid),
                  ("source_sha256", r["source_sha256"], module_sha), ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                  ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0))]
        if campaign == "B1":
            tid = fz["tree_id"]
            checks += tree_checks(cid, r["result"], tid, pol)
            checks += [("frozen_expected", r["result"]["expected"], fz["expected"]), ("frozen_predicted", r["result"]["observed"], fz["predicted"])]
            verdict = r["result"]["verdict"]
        else:
            checks += [("generation_order", r["generation_order"], ids), ("eight_distinct", sorted(r["results"]), sorted(trees))]
            for tid in sorted(trees):
                checks += tree_checks(cid, r["results"][tid], tid, pol)
                checks.append((f"{tid}.frozen_predicted", r["results"][tid]["observed"], fz["predicted"][tid]))
            verdict = "PASS" if all(r["results"][t]["verdict"] == "PASS" for t in trees) else "DOMAIN_FAIL"
            checks.append(("failing_trees", r["failing_trees"], sorted(t for t in trees if r["results"][t]["verdict"] != "PASS")))
        checks += [("verdict", r["verdict"], verdict), ("frozen_outcome", r["verdict"], fz["predicted_outcome"]),
                   ("fw_var", r["fw_var"], 0 if verdict == "PASS" else 2), ("outcome", fw["outcome"], verdict)]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    rep.check("observations.totals", dict(totals) == derived["outcomes"][campaign], {"totals": dict(totals), "by_policy": by_policy})
    tree_evals = sum(len(r["results"]) if campaign == "B2" else 1 for r in records.values())
    extra = {"tree_evaluations": tree_evals, "aggregated_order": order,
             "E1": model["E1"], "reversed_1_2": model["reversed_1_2"], "JZIP": model["JZIP"], "JCAT": model["JCAT"],
             "codes": codes, "structural_rows": [list(d) for d in distinct]}
    if campaign == "B2":
        rep.check("bundle.exact_eight_members_fresh_inputs",
                  all(sorted(r["results"]) == sorted(trees) and all(x["input"] == INPUT for x in r["results"].values())
                      and len(r["generation_order"]) == 8 == len(set(r["generation_order"])) for r in records.values())
                  and tree_evals == 24, {"tree_evaluations": tree_evals, "order_first_record": next(iter(records.values()))["generation_order"]})

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "500", "--budget-final-candidates", "500", "--budget-disk-bytes", "100000000",
                 "--budget-wall-time-seconds", "1200", "--core-props"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx" and Path(argv[2]).parent.name == campaign
              and Path(argv[argv.index("--core-props") + 1]).name == "core-b.fw.properties", argv[2:])
    rep.check("envelope.db", re.fullmatch(rf"as0927_d5{campaign.lower()}_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = core_log + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift and manifest["core_props"]["sha256"] == manifest["inputs_sha256"]["config/core-b.fw.properties"], drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    rep.check("provenance.core_workbook_equals_demo_xlsx", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"]
              == fg.workbook_to_json(root / "spec" / campaign / "demo.xlsx")["sheets"])
    return rep, {"campaign": campaign, "stage_counts": {"log": {k: lf[k] for k in ("final", "braces", "nested", "replace_summary")},
                                                       "fw_final": len(frows), "reader": count("reader", "candidates"),
                                                       "executor": count("executor", "processed"), "results_v2": len(rv2)},
                 "totals": dict(totals), "by_policy": by_policy, "extra": extra, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES[data["campaign"]].items():
        r = data["records"][case]
        body = ({"tree": r["result"]["tree"], "expected": r["result"]["expected"], "observed": r["result"]["observed"],
                 "sut_trace": r["result"]["sut_trace"]} if data["campaign"] == "B1"
                else {"generation_order": r["generation_order"], "failing_trees": r["failing_trees"]})
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], **body, "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d5b.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d5b.verification/v1", "run": run.name, "campaign": data["campaign"], "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "construct_sha256": sha256((HERE / "construct.py").read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES[data["campaign"]].values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
