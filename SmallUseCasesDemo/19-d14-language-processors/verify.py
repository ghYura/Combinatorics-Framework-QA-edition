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


"""Independent offline verifier for one D14a evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports compiler.py, vm.py, interpreter.py, oracle.py, runtime.py or derive.py,
never connects to a database, never executes a candidate (candidates are parsed with `ast`). All 432
cases — both program ASTs, reference values, bytecode, every VM transition and output, the three checks
and the verdict — are rebuilt here from CONTRACT.md and compared with the frozen predictions, the
decoded Core rows (including the native FW_Permut DECL rows), the rendered candidates and every
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
POLICIES = ("faithful", "reverse_sub", "alias_dead_temp")
CHECKS = ("original_differential", "transformed_differential", "metamorphic")
SHEETS = ("HEAD", "IMPL", "XVAL", "YVAL", "SHAPE", "OP_A", "OP_B", "DECL", "TAIL")
CONFIG = ("impl", "xval", "yval", "shape", "op_a", "op_b")
MODULES = ("compiler", "vm", "interpreter", "oracle", "runtime")
EXPECTED = 432
DECL_ATOMS = ('declare("x");', 'declare("y");')
BUDGET_ARGS = ["--budget-mandatory-rows", "500", "--budget-final-candidates", "500", "--budget-disk-bytes", "150000000",
               "--budget-wall-time-seconds", "1200"]
WITNESSES = {
    "reverse_sub_equal_but_wrong": "P=reverse_sub|O=XY|H=L|X=-1|Y=2|A=-|B=-",
    "faithful_subtraction_control": "P=faithful|O=XY|H=L|X=-1|Y=2|A=-|B=-",
    "alias_dead_temp_xy_corrupted": "P=alias_dead_temp|O=XY|H=L|X=-1|Y=2|A=+|B=*",
    "alias_dead_temp_yx_restored": "P=alias_dead_temp|O=YX|H=L|X=-1|Y=2|A=+|B=*",
    "faithful_grouping_control": "P=faithful|O=XY|H=R|X=-1|Y=2|A=+|B=*",
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
def apply(op, left, right):
    return left + right if op in ("+", "ADD") else left - right if op in ("-", "SUB") else left * right


def expr_of(shape, a, b):
    x, y = {"var": "x"}, {"var": "y"}
    return ({"op": b, "left": {"op": a, "left": x, "right": y}, "right": x} if shape == "L"
            else {"op": a, "left": x, "right": {"op": b, "left": y, "right": x}})


def leaf_names(node):
    return [node["var"]] if "var" in node else leaf_names(node["left"]) + leaf_names(node["right"])


def evaluate(program):
    env = dict((b["name"], b["value"]) for b in program["bindings"])      # later bindings replace earlier ones
    def ev(n):
        return env[n["var"]] if "var" in n else apply(n["op"], ev(n["left"]), ev(n["right"]))
    return ev(program["expr"])


def compile_model(program, policy):
    code = [ins for b in program["bindings"]
            for ins in (["PUSH", b["value"]], ["STORE", "x" if policy == "alias_dead_temp" and b["name"] == "z" else b["name"]])]
    def gen(n):
        if "var" in n:
            return [["LOAD", n["var"]]]
        l, r = gen(n["left"]), gen(n["right"])
        body = r + l if policy == "reverse_sub" and n["op"] == "-" else l + r
        return body + [[{"+": "ADD", "-": "SUB", "*": "MUL"}[n["op"]]]]
    return code + gen(program["expr"]) + [["RETURN"]]


def run_model(code):
    stack, env, steps, out = [], {}, [], None
    for ip, ins in enumerate(code):
        if ins[0] == "PUSH":
            stack.append(ins[1])
        elif ins[0] == "STORE":
            env[ins[1]] = stack.pop()
        elif ins[0] == "LOAD":
            stack.append(env[ins[1]])
        elif ins[0] == "RETURN":
            if ip != len(code) - 1 or len(stack) != 1:
                raise ValueError("invalid RETURN")
            out = stack.pop()
        else:
            right, left = stack.pop(), stack.pop()
            stack.append(apply(ins[0], left, right))
        steps.append({"ip": ip, "instruction": list(ins), "stack": list(stack), "locals": dict(env), "returned": out})
    return out, steps


def own_case(policy, order, shape, x, y, a, b):
    vals = {"x": x, "y": y}
    decl = [{"name": n, "value": vals[n]} for n in order.lower()]
    expr = expr_of(shape, a, b)
    obs = {}
    for kind, bindings in (("original", decl), ("transformed", [decl[0], {"name": "z", "value": 7}, decl[1]])):
        prog = {"bindings": bindings, "expr": expr}
        code = compile_model(prog, policy)
        value, steps = run_model(code)
        obs[kind] = {"program": prog, "reference_value": evaluate(prog), "bytecode": code, "vm_value": value, "vm_trace": steps}
    o, t = obs["original"], obs["transformed"]
    checks = {"original_differential": o["vm_value"] == o["reference_value"], "transformed_differential": t["vm_value"] == t["reference_value"],
              "metamorphic": o["vm_value"] == t["vm_value"]}
    return {"case_id": f"P={policy}|O={order}|H={shape}|X={x}|Y={y}|A={a}|B={b}", "policy": policy, "order": order, "shape": shape,
            "x": x, "y": y, "op_a": a, "op_b": b, "declared": list(order.lower()), "observations": obs, "checks": checks,
            "verdict": "PASS" if all(checks.values()) else "DOMAIN_FAIL"}


def all_keys():
    return list(itertools.product(POLICIES, ("XY", "YX"), ("L", "R"), (-1, 2), (-1, 2), "+-*", "+-*"))


REC_KEYS = sorted(["schema", "contract", "case_id", "policy", "order", "shape", "x", "y", "op_a", "op_b", "declared", "observations",
                   "checks", "verdict", "fw_var", "carrier_slot", "source_sha256", "framework"])
OBS_KEYS = ["bytecode", "program", "reference_value", "vm_trace", "vm_value"]
STEP_KEYS = ["instruction", "ip", "locals", "returned", "stack"]


def compare_record(r, o):
    """[(field, observed, expected)] for every record field, both variants and every VM transition."""
    checks = [(k, r.get(k), o[k]) for k in ("case_id", "policy", "order", "shape", "x", "y", "op_a", "op_b", "declared", "checks", "verdict")]
    checks += [("schema", r.get("schema"), "d14a.observation/v1"), ("contract", r.get("contract"), "v1"),
               ("fw_var", r.get("fw_var"), 0 if o["verdict"] == "PASS" else 2),
               ("carrier_slot", r.get("carrier_slot"), "IMPL position 2 (legacy positional, not causal)"),
               ("observation_kinds", sorted(r.get("observations") or {}), ["original", "transformed"])]
    for kind in ("original", "transformed"):
        got, want = (r.get("observations") or {}).get(kind) or {}, o["observations"][kind]
        checks.append((f"{kind}.keys", sorted(got), OBS_KEYS))
        checks += [(f"{kind}.{k}", got.get(k), want[k]) for k in ("program", "reference_value", "bytecode", "vm_value")]
        gs, ws = got.get("vm_trace") or [], want["vm_trace"]
        checks.append((f"{kind}.trace_len", len(gs), len(ws)))
        for g, w in zip(gs, ws):
            checks.append((f"{kind}.ip{w['ip']}.keys", sorted(g), STEP_KEYS))
            checks += [(f"{kind}.ip{w['ip']}.{k}", g.get(k), w[k]) for k in STEP_KEYS]
    return checks


def recheck(r):
    """The three relations recomputed from the recorded values alone (policy-blind)."""
    o, t = r["observations"]["original"], r["observations"]["transformed"]
    if o["reference_value"] != t["reference_value"]:
        return None
    return {"original_differential": o["vm_value"] == o["reference_value"], "transformed_differential": t["vm_value"] == t["reference_value"],
            "metamorphic": o["vm_value"] == t["vm_value"]}


def tallies(recs):
    return {"outcomes": dict(Counter(r["verdict"] for r in recs)),
            "by_policy": {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in POLICIES},
            "failed_checks": {p: {k: sum(not r["checks"][k] for r in recs if r["policy"] == p) for k in CHECKS} for p in POLICIES},
            "by_policy_order_shape": {f"{p}|{o}|{h}": dict(Counter(r["verdict"] for r in recs if (r["policy"], r["order"], r["shape"]) == (p, o, h)))
                                      for p in POLICIES for o in ("XY", "YX") for h in ("L", "R")},
            "wrong_agreements": sum(1 for r in recs if r["checks"]["metamorphic"] and not r["checks"]["original_differential"]),
            "original_correct_transformed_corrupted": sum(1 for r in recs if r["checks"]["original_differential"] and not r["checks"]["transformed_differential"])}


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
    """Identity from the six configuration atoms and the two declarations, in slot order."""
    if [c[0] for c in calls] != [*CONFIG, "declare", "declare"] or sorted(c[1] for c in calls[6:]) != ["x", "y"]:
        raise ValueError(f"atom order {calls}")
    v = {c[0]: c[1] for c in calls[:6]}
    order = (calls[6][1] + calls[7][1]).upper()
    return f"P={v['impl']}|O={order}|H={v['shape']}|X={v['xval']}|Y={v['yval']}|A={v['op_a']}|B={v['op_b']}"


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


def join_cells(cells, endings):
    """The Reader's rendering: each column's values back to back, then its sheet ending, or a newline if it
    has none (nothing after the last column when its ending is empty)."""
    parts = []
    for i, (vals, e) in enumerate(zip(cells, endings)):
        parts += ["".join(vals), e if (e or i == len(cells) - 1) else "\n"]
    return "".join(parts)


def spec_view(spec):
    """What a spec means for Core: per-sheet values and endings, the FW_Seq chains and the custom message."""
    slots = [(s.sheet, list(s.values), s.ending) for s in spec.slots]
    chains = ({k: v["directives"] for k, v in spec.program.items()} if spec.program
              else {row[0]: row[1:] for row in spec.seq_extra})
    msgs = [re.sub(r"^FWCUSTOMVAR=\d+ ", "", c.msg) for c in spec.custom_vars]
    return {"slots": slots, "chains": chains, "custom": [(c.code, m) for c, m in zip(spec.custom_vars, msgs)],
            "constraints": spec.constraints, "params": spec.params}


def graph_nodes(plan):
    return {n["id"]: n for n in plan["dependency_graph"]["graph"]["nodes"]}


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in MODULES}

    # ---- frozen inputs ----
    pre = manifest["preflight"]
    hashes = {"CONTRACT.md": pre["contract_sha256"], "architect-derived.json": pre["derived_sha256"], "derive.py": pre["derive_sha256"]}
    rep.check("frozen.contract_prediction_derivation", all(sha256((root / f).read_bytes()) == h for f, h in hashes.items())
              and pre["contract_sha256"] == "02c07e48b20310c2987d960c6c46bc5f09fa142b45b3b38354d75d2208e5ffde"
              and pre["derived_sha256"] == "aa08c2e3ea09442a14c4b422959c1e19d41089a01c7dd0191240af272204e757", hashes)

    # ---- the model ----
    env = {"x": -1, "y": 2}
    lit = {k: evaluate({"bindings": [{"name": "x", "value": -1}, {"name": "y", "value": 2}], "expr": expr_of(h, a, b)})
           for k, (h, a, b) in {"L(+,*)": ("L", "+", "*"), "R(+,*)": ("R", "+", "*"), "L(-,-)": ("L", "-", "-")}.items()}
    rep.check("model.literal_reference_controls", lit == {"L(+,*)": -1, "R(+,*)": -3, "L(-,-)": -2}
              and (-1 + 2) * -1 == -1 and -1 + 2 * -1 == -3 and (-1 - 2) - -1 == -2, {"computed": lit, "env": env})
    own = {c["case_id"]: c for c in (own_case(*k) for k in all_keys())}
    expected_ids = sorted(own)
    fkeys = ("policy", "order", "shape", "x", "y", "op_a", "op_b", "observations", "checks")
    diff = [(i, k) for i in expected_ids for k in fkeys if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    rep.check("model.frozen_equals_own_432", sorted(frozen) == expected_ids and len(own) == EXPECTED and not diff,
              {"cases": len(own), "diff": diff[:4]})
    own_t = tallies(list(own.values()))
    ref_agree = sum(c["observations"]["original"]["reference_value"] == c["observations"]["transformed"]["reference_value"] for c in own.values())
    third = all(leaf_names(c["observations"][k]["program"]["expr"]) == ["x", "y", "x"] for c in own.values() for k in ("original", "transformed"))
    rep.check("model.tallies", {k: own_t[k] for k in ("outcomes", "by_policy", "failed_checks")} == {k: derived[k] for k in ("outcomes", "by_policy", "failed_checks")}
              and own_t["outcomes"] == {"PASS": 316, "DOMAIN_FAIL": 116} and own_t["wrong_agreements"] == 64
              and own_t["original_correct_transformed_corrupted"] == 52 and ref_agree == EXPECTED and third,
              {**own_t, "reference_agreement": ref_agree, "third_leaf_is_x": third})

    # ---- stages, plans, Core rows and identities ----
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    card = cmp_["cardinality"]["xlsx"]
    architect_plan = json.loads((root / "planning" / "plan" / "plan.json").read_text())
    ours = {k: json.loads((run / f"plan-{k}" / "plan.json").read_text()) for k in ("toml", "xlsx")}
    an, xn, tn = graph_nodes(architect_plan), graph_nodes(ours["xlsx"]), graph_nodes(ours["toml"])
    node_diff = {k: (an.get(k), xn.get(k)) for k in set(an) | set(xn) if an.get(k) != xn.get(k)}
    decl_only = (set(node_diff) == {"DECL"} and an["DECL"]["attrs"]["verb"] == "FW_Combi(1)" and xn["DECL"]["attrs"]["verb"] == "FW_Permut()"
                 and {**an["DECL"], "attrs": {**an["DECL"]["attrs"], "verb": "FW_Permut()"}} == xn["DECL"])
    edges = lambda p: sorted(map(json.dumps, p["dependency_graph"]["graph"]["edges"]))
    rep.check("stage.plans_exact_432", cmp_["cardinality"]["toml"] == card and not any(cmp_["budget_blocking"].values())
              and all(card[c] == ["EXACT", 432, 432, 432] for c in ("mandatory", "post_sieve", "final"))
              and card["optional_multiplier"][:2] == ["EXACT", 1] and cmp_["constraints_present"] == {"toml": 0, "xlsx": 0}
              and tn == xn and edges(ours["toml"]) == edges(ours["xlsx"]) == edges(architect_plan) and decl_only
              and ours["xlsx"]["cardinality"]["per_slot"] == architect_plan["cardinality"]["per_slot"],
              {"cardinality": cmp_["cardinality"], "graph_hash": {k: p["dependency_graph"]["graph_hash"] for k, p in ours.items()},
               "architect_shape_plan_graph_hash": architect_plan["dependency_graph"]["graph_hash"],
               "difference_from_architect_plan": "DECL slot verb attribute FW_Combi(1) (TOML placeholder) -> FW_Permut() (effective first verb); "
                                             "edges, chains and per-slot counts equal" if decl_only else node_diff})
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
              and dict(data)["DECL"] == list(DECL_ATOMS),
              {"sheets": [n for n, _ in data], "codes": len(dictionary)})
    endings = {r["sheet"]: r["ending"] for r in tables["names"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {mm.group(2): c for c in (frows or [{}])[0] for mm in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if mm}
    def cell(row, sheet):
        v = row.get(cols[sheet])
        return list(base.get(cols[sheet]) if v is None else v)
    decoded, bad_rows, core_text, row_of, decl_rows = [], [], {}, {}, Counter()
    for r in frows:
        try:
            codes = {s: cell(r, s) for s in SHEETS}
            if any(len(c) != (2 if s == "DECL" else 1) for s, c in codes.items()):
                raise ValueError(f"row cell arity {codes}")
            vals = {s: [code2val[c] for c in codes[s]] for s in SHEETS}
            cid = case_of([atom(vals[s][0]) for s in SHEETS[1:7]] + [atom(v) for v in vals["DECL"]])
            decl_rows[tuple(vals["DECL"])] += 1
            core_text[cid] = join_cells([vals[s] for s in SHEETS], [endings[s] for s in SHEETS])
            row_of[cid] = r["combi_id"]
            decoded.append(cid)
        except (ValueError, KeyError, SyntaxError, AttributeError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    rep.check("core.decl_rows_are_the_two_permutations", dict(decl_rows) == {DECL_ATOMS: 216, DECL_ATOMS[::-1]: 216}
              and endings["DECL"] == "\n", {"decl_rows": {" ".join(k): v for k, v in decl_rows.items()}, "ending": endings.get("DECL")})
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
              and all(n.split("_")[0] == str(c) for n, c in mapping.items()),
              {"errors": errs[:3], "candidate_name_prefix_equals_combi_id": all(n.split("_")[0] == str(c) for n, c in mapping.items())})
    rep.check("reader.inlined_sources", src_ok, module_sha)
    rv2 = {r["candidate_id"]: r for r in db["results_db"]["results_v2"]}
    rep.check("executor.one_attempt_each_repeat_1", len(rv2) == EXPECTED and sorted(f"{k}.py" for k in rv2) == sorted(cands)
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2.values()))
    outcomes = Counter(r["outcome"] for r in rv2.values())
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or ""),
              dict(outcomes))

    # ---- every record, both variants, every VM transition ----
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
    rep.check("identity.executor", sorted(records) == expected_ids and len(records) == EXPECTED)
    bad, fields, steps = [], 0, 0
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_declared_population"))
            continue
        o, fw = own[cid], r["framework"]
        checks = compare_record(r, o)
        checks += [("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("record_keys", sorted(r), REC_KEYS),
                   ("declared_equals_decl_row", "".join(r["declared"]).upper(), r["order"]),
                   ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], o["verdict"]),
                   ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("source_sha256", r["source_sha256"], module_sha),
                   ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])),
                   ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        fields += len(checks)
        steps += sum(len(r["observations"][k]["vm_trace"]) for k in ("original", "transformed"))
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "vm_transitions": steps, "bad": bad[:6]})
    recs = list(records.values())
    rc = [(r["case_id"], recheck(r), r["checks"]) for r in recs]
    rep.check("observations.checks_recomputed_policy_blind", all(c is not None and c == got for _, c, got in rc)
              and all((r["verdict"] == "PASS") == all(r["checks"].values()) for r in recs),
              {"reference_disagreements": [i for i, c, _ in rc if c is None][:3], "mismatch": [i for i, c, g in rc if c is not None and c != g][:3]})
    obs_t = tallies(recs)
    rep.check("observations.totals", obs_t == own_t and obs_t["outcomes"] == derived["outcomes"] == {"PASS": 316, "DOMAIN_FAIL": 116}
              and obs_t["by_policy"] == derived["by_policy"] and obs_t["failed_checks"] == derived["failed_checks"], obs_t)

    # ---- mechanisms (from the observed records) ----
    rs_fail = [r for r in recs if r["policy"] == "reverse_sub" and r["verdict"] != "PASS"]
    al_fail = [r for r in recs if r["policy"] == "alias_dead_temp" and r["verdict"] != "PASS"]
    al_xy_pass = [r for r in recs if r["policy"] == "alias_dead_temp" and r["order"] == "XY" and r["verdict"] == "PASS"]
    cancelling = [r for r in al_xy_pass if len({evaluate({"bindings": [{"name": "x", "value": v}, {"name": "y", "value": r["y"]}],
                                                          "expr": r["observations"]["original"]["program"]["expr"]}) for v in (-1, 2, 7, 11)}) == 1]
    rep.check("mechanism.reverse_sub_equal_but_wrong", len(rs_fail) == 64 and all(r["checks"]["metamorphic"] and not r["checks"]["original_differential"]
                                                                                  and not r["checks"]["transformed_differential"] for r in rs_fail)
              and all(any(n.get("op") == "-" for n in [r["observations"]["original"]["program"]["expr"],
                                                         r["observations"]["original"]["program"]["expr"]["left"],
                                                         r["observations"]["original"]["program"]["expr"]["right"]]) for r in rs_fail),
              {"failures": len(rs_fail), "all_pass_metamorphic": all(r["checks"]["metamorphic"] for r in rs_fail)})
    rep.check("mechanism.alias_dead_temp_placement", len(al_fail) == 52 and all(r["order"] == "XY" and r["checks"]["original_differential"]
                                                                                 and not r["checks"]["transformed_differential"] for r in al_fail)
              and all(r["verdict"] == "PASS" for r in recs if r["policy"] == "alias_dead_temp" and r["order"] == "YX")
              and all(r["observations"]["transformed"]["vm_trace"][-1]["locals"]["x"] == 7 for r in al_fail)
              and len(al_xy_pass) == 20 and len(cancelling) == 20,
              {"failures": len(al_fail), "yx_passes": sum(1 for r in recs if r["policy"] == "alias_dead_temp" and r["order"] == "YX" and r["verdict"] == "PASS"),
               "xy_passes": len(al_xy_pass), "xy_passes_independent_of_x": len(cancelling)})
    diag = sum(1 for r in recs if r["verdict"] == "PASS" and r["policy"] != "faithful"
               and any(r["observations"][k]["bytecode"] != compile_model(r["observations"][k]["program"], "faithful") for k in ("original", "transformed")))
    third_obs = all(leaf_names(r["observations"][k]["program"]["expr"]) == ["x", "y", "x"] for r in recs for k in ("original", "transformed"))
    rep.check("mechanism.faithful_and_diagnostic_bytecode", all(r["verdict"] == "PASS" for r in recs if r["policy"] == "faithful") and third_obs
              and all(r["observations"]["transformed"]["program"]["bindings"][1] == {"name": "z", "value": 7} for r in recs),
              {"passing_candidates_with_non_faithful_bytecode": diag, "third_leaf_is_x": third_obs})

    # ---- envelope and provenance ----
    need = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1", *BUDGET_ARGS]
    rep.check("envelope.command", all(t in argv for t in need) and "--override-budget" not in argv and "--sieve" not in argv
              and Path(argv[2]).name == "demo.xlsx" and all(argv[argv.index(BUDGET_ARGS[i]) + 1] == BUDGET_ARGS[i + 1] for i in range(0, 8, 2)),
              argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d14a_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values())
              and all(manifest["databases"]["exists_after"].values()), manifest["databases"])
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    build = json.loads((root / "spec" / "build.json").read_text())
    rep.check("provenance.build_record", build["module_sha256"] == module_sha
              and build["files"]["spec.toml"] == sha256((run / "inputs" / "spec.toml").read_bytes()) == sha256((root / "spec" / "spec.toml").read_bytes())
              and build["files"]["demo.xlsx"] == sha256((run / "inputs" / "demo.xlsx").read_bytes()), build["files"])
    comp = {a["kind"]: a for st in stages.values() for a in st.get("artifacts", []) if a["kind"].startswith("component.")}
    comp_ok = {k: Path(a["path"]).is_file() and sha256(Path(a["path"]).read_bytes()) == a["sha256"] for k, a in comp.items()}
    rep.check("provenance.framework_components_unchanged", comp_ok and all(comp_ok.values()),
              {k: {"sha256": a["sha256"], "path": a["path"], "unchanged": comp_ok[k]} for k, a in comp.items()})
    x, t = fg.load_spec(root / "spec" / "demo.xlsx"), fg.load_spec(root / "spec" / "spec.toml")
    xv, tv = spec_view(x), spec_view(t)
    rep.check("provenance.xlsx_toml_core_input", sheets == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"]
              == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"] and xv == tv and not xv["constraints"] and not xv["params"]
              and not x.sidecar_path and xv["chains"]["DECL"] == ["FW_Permut()", "FW_Combi(size)"],
              {"slots_equal": xv["slots"] == tv["slots"], "chains_equal": xv["chains"] == tv["chains"], "custom_equal": xv["custom"] == tv["custom"]})
    strata = {p: {f"{o}|{h}": obs_t["by_policy_order_shape"][f"{p}|{o}|{h}"] for o in ("XY", "YX") for h in ("L", "R")} for p in POLICIES}
    return rep, {"stage_counts": counts, "tallies": obs_t, "strata": strata, "decl_rows": {" ".join(k): v for k, v in decl_rows.items()},
                 "diagnostic_bytecode_passes": diag, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        o, t = r["observations"]["original"], r["observations"]["transformed"]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"],
                    "original": {"reference": o["reference_value"], "vm": o["vm_value"], "bytecode": o["bytecode"]},
                    "transformed": {"reference": t["reference_value"], "vm": t["vm_value"], "bytecode": t["bytecode"],
                                    "final_locals": t["vm_trace"][-1]["locals"]},
                    "checks": r["checks"], "verdict": r["verdict"],
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d14a.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d14a.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "tallies", "strata", "decl_rows", "diagnostic_bytecode_passes")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
