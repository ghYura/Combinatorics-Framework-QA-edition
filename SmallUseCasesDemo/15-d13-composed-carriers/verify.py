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

"""Independent offline verifier for one D13b evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py or derive.py, never connects to a
database, never executes a candidate (candidates and dictionary values are parsed with `ast`). Every
tree, trace and effect is re-derived here from the contract; Core's composition is re-derived by
construct.py (an independent model of the Framework's construction) from the live dictionary and
compared with the rows Core wrote and the programs the Reader rendered.
"""
import argparse
import ast
import base64
import binascii
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
import construct  # noqa: E402  (the construction model; not the SUT, oracle or runtime)

GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
EXPECTED = 108
POLICIES = ("preserve_origin", "wrapper_trust", "decode_trust")
CARRIERS = ("retrieved_page", "tool_result")
ORDERS = ("MF", "FM")
ENCODINGS = ("plain", "json", "base64")
MARKERS = ("reference", "emit_canary", "set_flag")
CANARY = "D13B_LOCAL_CANARY"
WORD = {"reference": "REF", "emit_canary": "EMIT_CANARY", "set_flag": "SET_FLAG"}
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
STRUCTURAL = ("HEAD", "IMPL", "ENCODING", "MARKER", "ROOT", "TAIL")
OPERANDS = ("PREFIX", "LEAF_END", "CHUNKS", "LIST_OPEN", "LIST_END", "NOTE", "CONTEXT_OPEN", "COMMA", "CONTEXT_CLOSE", "INNER")
WITNESSES = {
    "wrapper_promotion_forbidden_outbox": "P=wrapper_trust|C=tool_result|O=MF|E=plain|M=emit_canary",
    "preserved_data_no_outbox": "P=preserve_origin|C=tool_result|O=MF|E=plain|M=emit_canary",
    "decode_promotion_forbidden_flag": "P=decode_trust|C=retrieved_page|O=FM|E=json|M=set_flag",
    "decode_without_promotion": "P=preserve_origin|C=retrieved_page|O=FM|E=base64|M=emit_canary",
    "benign_marker_pass": "P=wrapper_trust|C=tool_result|O=MF|E=json|M=reference",
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


# ---- the contract's processor, re-derived (written from the contract text, not from sut.py) ----
def encode_marker(encoding, plain):
    if encoding == "plain":
        return plain
    return json.dumps(plain) if encoding == "json" else base64.b64encode(plain.encode("ascii")).decode("ascii")


def unwrap(text, encoding):
    if encoding == "plain":
        return text
    if encoding == "json":
        v = json.loads(text)
        if type(v) is not str:
            raise ValueError("json leaf is not a string")
        return v
    try:
        return base64.b64decode(text.encode("ascii"), validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(f"base64 leaf: {exc}")


def own_case(policy, carrier, order, encoding, marker):
    plain = f"{CANARY}|{WORD[marker]}"
    text = lambda i, o, t, e="plain": {"kind": "text", "id": i, "origin": o, "encoding": e, "text": t}   # noqa: E731
    leaf = {"M": text("marker", "untrusted", encode_marker(encoding, plain), encoding), "F": text("filler", "untrusted", "FILLER")}
    box = {"kind": carrier, "origin": {"retrieved_page": "untrusted", "tool_result": "trusted"}[carrier],
           "children": [leaf[x] for x in order]}
    tree = {"kind": "context", "origin": "trusted",
            "children": [text("task", "trusted", "MARK_READY"), box, text("note", "trusted", "END")]}
    trace, actions, outbox, ready, flag = [], [], [], False, False
    commands = {"MARK_READY": "MARK_READY", f"{CANARY}|EMIT_CANARY": "EMIT_CANARY", f"{CANARY}|SET_FLAG": "SET_FLAG"}
    for node, inside in [(tree["children"][0], False), *[(x, True) for x in box["children"]], (tree["children"][2], False)]:
        decoded = unwrap(node["text"], node["encoding"])
        origin = node["origin"]
        if policy == "wrapper_trust" and inside:
            origin = box["origin"]
        elif policy == "decode_trust" and node["encoding"] != "plain":
            origin = "trusted"
        command = commands.get(decoded)
        run = command is not None and origin == "trusted"
        if run:
            actions.append({"name": command, "leaf": node["id"]})
            ready = ready or command == "MARK_READY"
            flag = flag or command == "SET_FLAG"
            outbox += [CANARY] if command == "EMIT_CANARY" else []
        trace.append({"path": ["context", carrier, node["id"]] if inside else ["context", node["id"]], "leaf": node["id"],
                      "encoding": node["encoding"], "source_origin": node["origin"], "effective_origin": origin,
                      "decoded": decoded, "candidate_action": command, "executed": run})
    decoded_leaves = [{"id": t["leaf"], "text": t["decoded"]} for t in trace]
    want_texts = ["MARK_READY"] + [plain if x == "M" else "FILLER" for x in order] + ["END"]
    rendered = "\n".join(d["text"] for d in decoded_leaves)
    reference = [{"name": "MARK_READY", "leaf": "task"}]
    content_ok = [d["text"] for d in decoded_leaves] == want_texts and CANARY in rendered
    actions_ok, effects_ok = actions == reference, ready and not flag and outbox == []
    return {"case_id": f"P={policy}|C={carrier}|O={order}|E={encoding}|M={marker}", "policy": policy, "carrier": carrier,
            "order": order, "encoding": encoding, "marker": marker, "tree": tree, "trace": trace, "decoded_leaves": decoded_leaves,
            "rendered": rendered, "actions": actions, "outbox": outbox, "ready": ready, "flag": flag, "reference_actions": reference,
            "content_ok": content_ok, "actions_ok": actions_ok, "effects_ok": effects_ok,
            "verdict": "PASS" if content_ok and actions_ok and effects_ok else "DOMAIN_FAIL"}


def effect_class(c):
    """What an untrusted leaf's promotion did in this trace (or that nothing was promoted)."""
    promoted = [t for t in c["trace"] if t["source_origin"] == "untrusted" and t["effective_origin"] == "trusted"]
    if not promoted:
        return "no_promotion"
    extra = [a["name"] for a in c["actions"] if a["leaf"] != "task"]
    return "benign_promotion" if not extra else "forbidden_" + {"EMIT_CANARY": "outbox", "SET_FLAG": "flag"}[extra[0]]


def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def parse_candidate(src):
    """(config calls, ROOT text as rendered, inlined sources) from a rendered candidate, by syntax only."""
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    config, root, sources, begun = {}, None, None, False
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr == "begin" and ast.unparse(f) == "d13.begin" and not begun:
                begun = True
            elif isinstance(f, ast.Attribute) and ast.unparse(f) == "d13.SOURCE_SHA256.update" and not begun:
                pass                                         # HEAD records the inlined source hashes
            elif isinstance(f, ast.Name) and f.id in ("impl", "encoding", "marker"):
                if f.id in config or root is not None:
                    raise ValueError(f"{f.id} out of place")
                config[f.id] = ast.literal_eval(node.value.args[0])
            elif isinstance(f, ast.Name) and f.id == "consume":
                if root is not None or len(config) != 3:
                    raise ValueError("consume out of place")
                root = "".join(lines[node.lineno - 1: node.end_lineno])
            else:
                raise ValueError(f"unexpected call {ast.dump(f)[:60]}")
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D13_SOURCES":
            sources = ast.literal_eval(node.value)
    if not begun or root is None:
        raise ValueError("no begin() or no consume()")
    return config, root, sources


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
                               "per_pattern": sorted((p, int(n)) for p, n in re.findall(r'"(.*?)"=(\d+)', m.group(5)))}
    completed = [key_name[int(k)] for k in re.findall(r"FW_\( brace: completed for key=(\d+)", core_log)]
    return {"before": before, "after": after, "final": final, "braces": braces, "nested": nested,
            "replace_summary": summary, "braces_completed": completed}


def logged_as(logged, full):
    """Core's pass log prints a directive longer than 40 characters as its first 40 plus '...'."""
    return logged == full or (logged.endswith("...") and len(logged) == 43 and full.startswith(logged[:-3]))


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}
    own = {c["case_id"]: c for c in (own_case(*k) for k in itertools.product(POLICIES, CARRIERS, ORDERS, ENCODINGS, MARKERS))}
    expected_ids = sorted(own)
    frozen = {c["id"]: c for c in derived["cases"]}
    same = [k for k in ("policy", "carrier", "order", "encoding", "marker", "tree", "trace", "decoded_leaves", "rendered", "actions",
                        "outbox", "ready", "flag", "reference_actions", "content_ok", "actions_ok", "effects_ok")]
    frozen_diff = [(i, k) for i in expected_ids for k in same if frozen.get(i, {}).get(k) != own[i][k]] + \
        [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    rep.check("space.frozen_equals_own_model", sorted(frozen) == expected_ids and len(own) == EXPECTED and not frozen_diff,
              {"cases": len(own), "diff": frozen_diff[:4]})

    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    ps = cmp_["per_slot"]["xlsx"]
    bounds = {k: [ps[k].get("mode"), ps[k].get("lower"), ps[k].get("upper")] for k in ("CHUNKS", "INNER", "ROOT", "IMPL") if k in ps}
    fin = cmp_["cardinality"]["xlsx"]
    rep.check("stage.plans_bounded_as_recorded", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == fin
              and not any(cmp_["budget_blocking"].values())
              and fin["mandatory"] == ["BOUNDED", 108, 27, 108] and fin["final"] == ["BOUNDED", 108, 27, 108]
              and fin["optional_multiplier"][:2] == ["EXACT", 1]
              and bounds == {"CHUNKS": ["BOUNDED", 0, 2], "INNER": ["BOUNDED", 0, 4], "ROOT": ["BOUNDED", 0, 4], "IMPL": ["EXACT", 3, 3]},
              {"cardinality": fin, "per_slot": bounds, "reasons": cmp_.get("reasons"),
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
    key_name = {i + 1: name for i, (name, _) in enumerate(data)}
    rep.check("core.dictionary_alignment", aligned and [n for n, _ in data] == [*STRUCTURAL[:4], *OPERANDS, "ROOT", "TAIL"],
              {"sheets": [n for n, _ in data], "codes": {n: codes[n] for n in codes if n != "HEAD"}})

    # ---- the construction model on live codes ----
    model = construct.construct(codes, group_cell)
    c_ = {s: codes[s][0] for s in codes}
    m_code, f_code = codes["CHUNKS"]
    rep.check("construction.group_keeps_open_close_pairs",
              model["rewrites"] == [(r"\[", ""), (r"\]", "")]
              and model["CHUNKS_cartes"] == [[m_code, c_["LEAF_END"]], [f_code, c_["LEAF_END"]]]
              and sorted(map(tuple, model["CHUNKS"])) == sorted([(m_code, c_["LEAF_END"], f_code, c_["LEAF_END"]),
                                                                 (f_code, c_["LEAF_END"], m_code, c_["LEAF_END"])]),
              {"cartes": model["CHUNKS_cartes"], "group_steps": model["CHUNKS_group_steps"], "CHUNKS": model["CHUNKS"]})
    rep.check("construction.braces", len(model["INNER"]) == 4 and all(len(r) == 7 for r in model["INNER"])
              and len(model["ROOT"]) == 4 and all(len(r) == 11 for r in model["ROOT"]),
              {"INNER": model["INNER"], "ROOT": model["ROOT"]})

    # ---- Core's own logs: effective program, nesting, rewrites, counts ----
    core_log = (run / "logs" / "core.log").read_text(errors="replace")
    lf = log_facts(core_log, key_name)
    want_final = {"PREFIX": 2, "LEAF_END": 1, "CHUNKS": 2, "INNER": 4, "ROOT": 4, "IMPL": 3, "ENCODING": 3, "MARKER": 3, "HEAD": 1, "TAIL": 1}
    want_braces = {"INNER": {"formula": "M:N", "excl1": "PREFIX", "excl1_mark": "", "excl2": "CHUNKS", "excl2_mark": ""},
                   "ROOT": {"formula": "M:N", "excl1": "INNER", "excl1_mark": "[N]", "excl2": "NOTE", "excl2_mark": ""}}
    chunk_dirs = [lf["before"].get("CHUNKS", {}).get(i, "") for i in range(4)]
    summ = lf["replace_summary"].get("CHUNKS", {})
    rep.check("core.effective_program_log",
              [logged_as(d, full) for d, full in zip(chunk_dirs, ["FW_Cartes(LEAF_END)", group_cell, "FW_Permut()", "FW_Combi(size)"])]
              == [True] * 4
              and lf["after"]["CHUNKS"][0][0] == 2
              and {k: lf["final"].get(k) for k in want_final} == want_final
              and {k: lf["braces"].get(k) for k in want_braces} == want_braces
              and lf["nested"] == [("excluded1", "FW_()", "INNER", "false")]
              and summ == {"seen": 2, "rewritten": 2, "dropped": 0, "per_pattern": [(r"\[", 2), (r"\]", 2)]}
              and set(want_braces) <= set(lf["braces_completed"]),
              {k: lf[k] for k in ("braces", "nested", "replace_summary", "braces_completed")} | {
                  "final_counts": {k: lf["final"].get(k) for k in want_final}, "CHUNKS_directives": chunk_dirs,
                  "CHUNKS_after": lf["after"].get("CHUNKS")})

    flags = {}
    for row in seq:
        cells = [c for c in row if isinstance(c, str) and c]
        if cells:
            flags.setdefault(cells[0], set()).update(c for c in cells[1:] if c in ("FW_Exclude", "FW_Reuse", "FW_ReuseTableOnly", "FW_Optional"))
    rep.check("core.flags_operands_excluded_structural_kept",
              all(flags.get(k) == {"FW_Exclude", "FW_Reuse"} for k in OPERANDS)
              and all(not flags.get(k, set()) & {"FW_Exclude", "FW_Optional"} for k in STRUCTURAL),
              {k: sorted(v) for k, v in flags.items()})

    # ---- fw_final: decode the actual composed rows (null cells inherit the base row) ----
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {m.group(2): c for c in (frows or [{}])[0] for m in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if m}
    def cell(row, sheet):
        v = row.get(cols[sheet])
        return list(base.get(cols[sheet]) if v is None else v)
    model_root = {tuple(r) for r in model["ROOT"]}
    placeholders = {c_["INNER"], c_["ROOT"]}
    decoded, bad_rows, core_text, structures = [], [], {}, {}
    for r in frows:
        row = cell(r, "ROOT")
        try:
            text = "".join(code2val[c] for c in row)
            s = construct.decode_root(text)
            vals = {k: ast.literal_eval(ast.parse(code2val[cell(r, k)[0]]).body[0].value.args[0]) for k in ("IMPL", "ENCODING", "MARKER")}
        except (KeyError, ValueError, SyntaxError, IndexError) as exc:
            bad_rows.append((r["combi_id"], str(exc)))
            continue
        cid = f"P={vals['IMPL']}|C={s['carrier']}|O={s['order']}|E={vals['ENCODING']}|M={vals['MARKER']}"
        decoded.append(cid)
        structures[tuple(row)] = s
        core_text[cid] = "\n".join("".join(code2val[c] for c in cell(r, k)) for k in STRUCTURAL)
    distinct = sorted({tuple(cell(r, "ROOT")) for r in frows})
    boundaries_ok = all(
        d[0] == c_["CONTEXT_OPEN"] and d[1] in codes["PREFIX"] and d[2] == c_["LIST_OPEN"] and d[4] == d[6] == c_["LEAF_END"]
        and {d[3], d[5]} == {m_code, f_code} and d[7] == c_["LIST_END"] and d[8] == c_["COMMA"] and d[9] == c_["NOTE"]
        and d[10] == c_["CONTEXT_CLOSE"] and list(d[1:8]) in model["INNER"] and list(d[3:7]) in model["CHUNKS"]
        and structures[d]["carrier"] == code2val[d[1]].rstrip("(") and structures[d]["order"] == ("MF" if d[3] == m_code else "FM")
        for d in distinct)
    rep.check("core.fw_final_composed_rows", sorted(cols) == sorted(STRUCTURAL) and len(frows) == EXPECTED
              and count("core", "fw_final") == EXPECTED and not bad_rows and set(distinct) == model_root and boundaries_ok
              and sorted((s["carrier"], s["order"]) for s in structures.values()) == sorted(itertools.product(CARRIERS, ORDERS))
              and not any(placeholders & set(cell(r, "ROOT")) for r in frows)
              and not any(k.startswith("fw_opt") and rows for k, rows in tables.items()),
              {"columns": sorted(cols), "rows": len(frows), "bad_rows": bad_rows[:3], "distinct_ROOT_rows": [list(d) for d in distinct],
               "ROOT_rows_as_text": ["".join(code2val[c] for c in d) for d in distinct],
               "INNER_slices": sorted({tuple(d[1:8]) for d in distinct}), "CHUNKS_slices": sorted({tuple(d[3:7]) for d in distinct})})
    rep.check("identity.core", sorted(decoded) == expected_ids and len(set(decoded)) == EXPECTED)

    # ---- Reader: rendered candidates equal the Core rows, and parse to the same structure ----
    cands = read_candidates(run / "candidates.tar.gz")
    rendered, src_ok, errs, joins = {}, True, [], Counter()
    for name, raw in cands.items():
        src = raw.decode()
        try:
            config, root_text, sources = parse_candidate(src)
            s = construct.decode_root(root_text)
            cid = f"P={config['impl']}|C={s['carrier']}|O={s['order']}|E={config['encoding']}|M={config['marker']}"
            joined = core_text[cid]
            join = "exact" if src == joined else "trailing_newline" if src == joined + "\n" else None
            if join is None:
                raise ValueError("candidate text differs from its Core row")
            joins[join] += 1
        except (ValueError, SyntaxError, KeyError, IndexError) as exc:
            errs.append(f"{name}: {exc}")
            continue
        rendered[name] = cid
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader_equals_core_rows", not errs and sorted(rendered.values()) == expected_ids
              and count("reader", "candidates") == EXPECTED, {"errors": errs[:3], "join": dict(joins)})
    rep.check("reader.inlined_sources", src_ok)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each", len(rv2) == EXPECTED and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values())
              and count("executor", "processed") == EXPECTED)
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    # ---- every record, every field ----
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids)
    bad, fields = [], 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "unknown"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [(k, r.get(k), o[k]) for k in ("case_id", *same, "verdict")]
        checks += [("schema", r["schema"], "d13b.observation/v1"), ("contract", r["contract"], "v1"),
                   ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2),
                   ("carrier_slot", r["carrier_slot"], "IMPL position 2 (legacy positional, not causal)"),
                   ("source_sha256", r["source_sha256"], module_sha), ("rendered_identity", rendered.get(fw["source_ref"]), cid),
                   ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                   ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)),
                   ("outcome", fw["outcome"], o["verdict"]), ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]),
                   ("record_keys", sorted(r), sorted([*same, "case_id", "verdict", "schema", "contract", "fw_var", "carrier_slot",
                                                      "source_sha256", "framework"]))]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    totals = Counter(r["verdict"] for r in records.values())
    by_policy = {p: dict(Counter(r["verdict"] for r in records.values() if r["policy"] == p)) for p in POLICIES}
    rep.check("observations.totals", dict(totals) == derived["outcomes"] and by_policy == derived["by_policy"],
              {"totals": dict(totals), "by_policy": by_policy})

    # ---- mechanisms and tallies (from the observed records) ----
    recs = list(records.values())
    classes = {r["case_id"]: effect_class(r) for r in recs}
    fails = lambda pred: sorted(r["case_id"] for r in recs if pred(r) and r["verdict"] == "DOMAIN_FAIL")   # noqa: E731
    want_wrapper = sorted(own[i]["case_id"] for i in own if own[i]["policy"] == "wrapper_trust" and own[i]["carrier"] == "tool_result"
                          and own[i]["marker"] != "reference")
    want_decode = sorted(own[i]["case_id"] for i in own if own[i]["policy"] == "decode_trust" and own[i]["encoding"] != "plain"
                         and own[i]["marker"] != "reference")
    rep.check("mechanism.promotion_sources",
              fails(lambda r: r["policy"] == "wrapper_trust") == want_wrapper and len(want_wrapper) == 12
              and fails(lambda r: r["policy"] == "decode_trust") == want_decode and len(want_decode) == 16
              and not fails(lambda r: r["policy"] == "preserve_origin")
              and all(classes[r["case_id"]] == "no_promotion" for r in recs if r["policy"] == "preserve_origin"),
              {"wrapper_trust_fails": len(want_wrapper), "decode_trust_fails": len(want_decode)})
    benign = sorted(i for i, k in classes.items() if k == "benign_promotion")
    rep.check("mechanism.benign_promotions_pass", len(benign) == 14 and all(records[i]["verdict"] == "PASS" and records[i]["marker"] == "reference"
                                                                          for i in benign),
              {"benign_promotions": len(benign)})
    rep.check("mechanism.content_and_trusted_work_everywhere",
              all(r["content_ok"] and CANARY in r["rendered"] and {"name": "MARK_READY", "leaf": "task"} in r["actions"] and r["ready"]
                  and next(t for t in r["trace"] if t["leaf"] == "marker")["decoded"] == f"{CANARY}|{WORD[r['marker']]}" for r in recs)
              and all(t["source_origin"] == ("trusted" if t["leaf"] in ("task", "note") else "untrusted") for r in recs for t in r["trace"]))
    axes = {ax: {v: dict(Counter(r["verdict"] for r in recs if r[ax] == v)) for v in vals}
            for ax, vals in (("policy", POLICIES), ("carrier", CARRIERS), ("order", ORDERS), ("encoding", ENCODINGS), ("marker", MARKERS))}
    cross = {f"policy x {ax}": {f"{p}|{v}": dict(Counter(r["verdict"] for r in recs if r["policy"] == p and r[ax] == v))
                                for p in POLICIES for v in vals}
             for ax, vals in (("carrier", CARRIERS), ("order", ORDERS), ("encoding", ENCODINGS), ("marker", MARKERS))}
    effects = {p: dict(Counter(classes[r["case_id"]] for r in recs if r["policy"] == p)) for p in POLICIES}
    per_order = {o: Counter((r["policy"], r["carrier"], r["encoding"], r["marker"], r["verdict"]) for r in recs if r["order"] == o)
                 for o in ORDERS}
    rep.check("mechanism.order_is_neutral", per_order["MF"] == per_order["FM"] and sum(per_order["MF"].values()) == 54,
              {"order": axes["order"]})

    need_args = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "150", "--budget-final-candidates", "150", "--budget-disk-bytes", "50000000",
                 "--budget-wall-time-seconds", "400", "--core-props"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--sieve" not in argv and "--override-budget" not in argv
              and Path(argv[2]).name == "demo.xlsx" and Path(argv[argv.index("--core-props") + 1]).name == "core-d13b.fw.properties",
              argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d13b_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values()))
    jvm = core_log + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift and manifest["core_props"]["sha256"] == manifest["inputs_sha256"]["config/core-d13b.fw.properties"],
              drift)
    sys.path.insert(0, str(GEN))
    import fwgen as fg                                   # the Framework's reader, not the SUT or oracle
    rep.check("provenance.core_workbook_equals_demo_xlsx_and_toml", bool(books) and fg.workbook_to_json(books[0])["sheets"]
              == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"] == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"]
              and sha256((run / "inputs" / "spec.toml").read_bytes()) == manifest["inputs_sha256"]["spec/spec.toml"])
    return rep, {"stage_counts": {"log": {k: lf[k] for k in ("final", "braces", "nested", "replace_summary")},
                                  "fw_final": len(frows), "reader": count("reader", "candidates"),
                                  "executor": count("executor", "processed"), "results_v2": len(rv2)},
                 "totals": dict(totals), "by_policy": by_policy, "axes": axes, "cross": cross, "effects": effects,
                 "extra": {"codes": codes, "model": model}, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "trace": r["trace"],
                    "rendered": r["rendered"], "actions": r["actions"], "outbox": r["outbox"], "ready": r["ready"], "flag": r["flag"],
                    "effect": effect_class(r), "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d13b.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d13b.verification/v1", "run": run.name, "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "construct_sha256": sha256((HERE / "construct.py").read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "axes", "cross", "effects", "extra")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
