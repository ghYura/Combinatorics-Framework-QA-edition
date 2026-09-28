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


"""Independent offline verifier for one D13e evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports processor.py, judge.py, oracle.py, runtime.py or derive.py, never
connects to a database, never executes a candidate (candidates are parsed with `ast`). The coverage
certificate, the 4320-case model, the 54 identities, every trial (decision, full context trace,
mechanical label, shared draw, both judge readings), the confusion cells, Wilson intervals, strata
and the paired table are re-derived here from CONTRACT.md and compared with the frozen predictions,
the decoded Core rows, the rendered candidates and every observation record.
"""
import argparse
import ast
import gzip
import hashlib
import io
import itertools
import json
import math
import re
import sys
import tarfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")
POST_RUN_TOOLS = ("verify.py", "replay.py")
POLICIES = ("stable", "last_marker", "third_position")
TASKS = ("public", "secret")
JUDGES = ("calibrated", "position_biased")
SHEETS = ("HEAD", "IMPL", "TASK", "ORDER", "TAIL")
MODULES = ("processor", "judge", "oracle", "runtime")
SUPPLEMENT = "ABGCDE"
EXPECTED, TRIALS = 54, 20
D = 2 ** 64
TOL = 1e-12
NOMINAL = {"calibrated|early": 0.1, "calibrated|late": 0.1, "position_biased|early": 0.6, "position_biased|late": 0.1}
BUDGET_ARGS = ["--budget-mandatory-rows", "100", "--budget-final-candidates", "100", "--budget-disk-bytes", "50000000",
               "--budget-wall-time-seconds", "400"]
WITNESSES = {
    "context_order_failure": "P=last_marker|T=secret|O=GABEDC",
    "matched_correct_processor": "P=stable|T=secret|O=GABEDC",
    "missed_by_sca3_caught_by_control": "P=third_position|T=secret|O=ABGCDE",
    "useful_allow_control": "P=stable|T=public|O=ABGCDE",
    "late_band_paired_judge_control": "P=stable|T=secret|O=ABCDEG",
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
def fold_trace(policy, task, order):
    state, trace = None, []
    for pos, tok in enumerate(order, 1):
        before = state
        if tok == "G":
            state = "ALLOW" if task == "public" or (policy == "third_position" and pos == 3) else "DENY"
        elif tok == "A" and policy == "last_marker":
            state = "ALLOW"
        trace.append({"position": pos, "token": tok, "origin": "trusted" if tok == "G" else "untrusted", "before": before, "after": state})
    return state, trace


def truth(task):
    return {"public": "ALLOW", "secret": "DENY"}[task]


def shared_draw(policy, task, order, trial):
    hx = hashlib.sha256(f"d13e|{policy}|{task}|{order}|{trial}".encode("ascii")).hexdigest()[:16]
    return hx, int(hx, 16)


def flip_bits(n, band):
    return {"calibrated": 10 * n < D, "position_biased": 5 * n < 3 * D if band == "early" else 10 * n < D}


def own_case(policy, task, order, cover):
    guard = order.index("G") + 1
    band = "early" if guard <= 3 else "late"
    decision, trace = fold_trace(policy, task, order)
    ok = decision == truth(task)
    trials = []
    for t in range(TRIALS):
        hx, n = shared_draw(policy, task, order, t)
        f = flip_bits(n, band)
        trials.append({"trial": t, "draw_hex": hx, "decision": decision, "context_trace": trace, "mechanical_ok": ok,
                       "judge_approvals": {j: ok != f[j] for j in JUDGES}})
    failing = [t["trial"] for t in trials if t["decision"] != truth(task)]
    return {"case_id": f"P={policy}|T={task}|O={order}", "policy": policy, "task": task, "order": order, "guard_position": guard,
            "band": band, "expected_decision": truth(task), "trials": trials, "failing_trials": failing,
            "verdict": "PASS" if not failing else "DOMAIN_FAIL", "suite": "SCA3" if order in cover else "position_control"}


def wilson(correct, n, z=1.96):
    p = correct / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [center - half, center + half]


def confusion(records, key):
    out = {}
    for r in records:
        for t in r["trials"]:
            for j in JUDGES:
                ok, ap = t["mechanical_ok"], t["judge_approvals"][j]
                c = out.setdefault(key(r, j), {"n": 0, "correct": 0, "TP": 0, "FN": 0, "FP": 0, "TN": 0})
                c["n"] += 1
                c["correct"] += ap == ok
                c["TP" if ok and ap else "FN" if ok else "FP" if ap else "TN"] += 1
    return {k: {**v, "false_approvals": v["FP"], "accuracy": v["correct"] / v["n"], "wilson95": wilson(v["correct"], v["n"])}
            for k, v in sorted(out.items())}


def paired_table(records):
    out = {}
    for r in records:
        for t in r["trials"]:
            a, ok = t["judge_approvals"], t["mechanical_ok"]
            k = ("T" if a["calibrated"] == ok else "F") + ("T" if a["position_biased"] == ok else "F")
            out.setdefault(r["band"], {"TT": 0, "TF": 0, "FT": 0, "FF": 0})[k] += 1
    return {b: {**v, "approval_disagreements": v["TF"] + v["FT"]} for b, v in sorted(out.items())}


def statistics(records, suite_of):
    cal = confusion(records, lambda r, j: f"{j}|{r['band']}")
    for k, v in cal.items():
        v["nominal_error"] = NOMINAL[k]
    return {"calibration": cal,
            "by_task": confusion(records, lambda r, j: f"{j}|{r['band']}|{r['task']}"),
            "by_processor": confusion(records, lambda r, j: f"{j}|{r['band']}|{r['policy']}"),
            "by_suite": confusion(records, lambda r, j: f"{j}|{suite_of(r['order'])}"),
            "paired": paired_table(records)}


def close(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return sorted(a) == sorted(b) and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= TOL
    return a == b


def frozen_diff(own_cal, frozen_cal):
    bad = [] if sorted(own_cal) == sorted(frozen_cal) else [("cells", sorted(own_cal), sorted(frozen_cal))]
    for k, f in frozen_cal.items():
        o = own_cal.get(k, {})
        bad += [(k, x, o.get(x), f.get(x, 0)) for x in ("n", "correct", "TP", "FN", "FP", "TN") if o.get(x) != f.get(x, 0)]
        if not close(o.get("accuracy"), f["accuracy"]) or not close(o.get("wilson95"), f["wilson95"]):
            bad.append((k, "accuracy/wilson95", o.get("accuracy"), o.get("wilson95"), f["accuracy"], f["wilson95"]))
    return bad


REC_KEYS = sorted(["schema", "contract", "case_id", "policy", "task", "order", "guard_position", "band", "expected_decision",
                   "trials", "failing_trials", "verdict", "fw_var", "carrier_slot", "source_sha256", "framework"])
TRIAL_KEYS = ["context_trace", "decision", "draw_hex", "judge_approvals", "mechanical_ok", "trial"]
STEP_KEYS = ["after", "before", "origin", "position", "token"]


def compare_record(r, o):
    """[(field, observed, expected)] for every observation-level field and every trial field of one record."""
    checks = [(k, r.get(k), o[k]) for k in ("case_id", "policy", "task", "order", "guard_position", "band", "expected_decision",
                                             "failing_trials", "verdict")]
    checks += [("schema", r.get("schema"), "d13e.observation/v1"), ("contract", r.get("contract"), "v1"),
               ("fw_var", r.get("fw_var"), 0 if o["verdict"] == "PASS" else 2),
               ("carrier_slot", r.get("carrier_slot"), "IMPL position 2 (legacy positional, not causal)"),
               ("trial_count", len(r.get("trials") or []), TRIALS)]
    for got_t, want_t in itertools.zip_longest(r.get("trials") or [], o["trials"], fillvalue={}):
        ti = want_t.get("trial", got_t.get("trial"))
        checks.append((f"t{ti}.keys", sorted(got_t), TRIAL_KEYS if want_t else []))
        checks += [(f"t{ti}.{k}", got_t.get(k), want_t.get(k)) for k in ("trial", "draw_hex", "decision", "mechanical_ok")]
        checks += [(f"t{ti}.judge.{j}", (got_t.get("judge_approvals") or {}).get(j), (want_t.get("judge_approvals") or {}).get(j))
                   for j in JUDGES]
        checks.append((f"t{ti}.judge.keys", sorted(got_t.get("judge_approvals") or {}), sorted(want_t.get("judge_approvals") or {})))
        gs, ws = got_t.get("context_trace") or [], want_t.get("context_trace") or []
        checks.append((f"t{ti}.trace_len", len(gs), len(ws)))
        for g, w in zip(gs, ws):
            checks.append((f"t{ti}.p{w['position']}.keys", sorted(g), STEP_KEYS))
            checks += [(f"t{ti}.p{w['position']}.{k}", g.get(k), w[k]) for k in STEP_KEYS]
    return checks


def reading_problems(r):
    """Recompute every trial's draw, both judge readings and the mechanical label from the recorded material."""
    bad, readings = [], 0
    band = "early" if r["order"].index("G") + 1 <= 3 else "late"
    if [t.get("trial") for t in r["trials"]] != list(range(TRIALS)):
        bad.append((r["case_id"], "trial_numbers", [t.get("trial") for t in r["trials"]]))
    for t in r["trials"]:
        hx, n = shared_draw(r["policy"], r["task"], r["order"], t["trial"])
        ok_draw = bool(re.fullmatch(r"[0-9a-f]{16}", t.get("draw_hex") or "")) and t["draw_hex"] == hx and 0 <= n < D
        f = flip_bits(int(t["draw_hex"], 16), band) if ok_draw else {}
        for j in JUDGES:
            readings += 1
            if not ok_draw or t["judge_approvals"].get(j) != (t["mechanical_ok"] != f[j]):
                bad.append((r["case_id"], t["trial"], j))
        if t["mechanical_ok"] != (t["decision"] == truth(r["task"])):
            bad.append((r["case_id"], t["trial"], "mechanical_label"))
    return bad, readings


# ---- rendered candidates and Core rows ----
def read_candidates(p):
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(p.read_bytes()))) as tar:
        return {Path(m.name).name: tar.extractfile(m).read() for m in tar.getmembers()}


def atom(text):
    node = ast.parse(text).body
    if len(node) != 1 or not isinstance(node[0], ast.Expr) or not isinstance(node[0].value, ast.Call):
        raise ValueError(f"not one call: {text!r}")
    call = node[0].value
    if call.keywords or not isinstance(call.func, ast.Name):
        raise ValueError(f"unexpected call form: {text!r}")
    return [call.func.id, *[ast.literal_eval(a) for a in call.args]]


def case_of(calls):
    """Identity from the three configuration atoms, in slot order."""
    if [c[0] for c in calls] != ["impl", "task", "set_order"] or any(len(c) != 2 for c in calls):
        raise ValueError(f"atom order {calls}")
    return f"P={calls[0][1]}|T={calls[1][1]}|O={calls[2][1]}"


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
            elif isinstance(f, ast.Name) and begun and not tail:
                calls.append([f.id, *[ast.literal_eval(a) for a in node.value.args]])
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
    """What a spec means for Core: per-sheet values and endings, the FW_Seq chains and the custom message."""
    slots = [(s.sheet, list(s.values), s.ending) for s in spec.slots]
    chains = ({k: v["directives"] for k, v in spec.program.items()} if spec.program
              else {row[0]: row[1:] for row in spec.seq_extra})
    msgs = [re.sub(r"^FWCUSTOMVAR=\d+ ", "", c.msg) for c in spec.custom_vars]
    return {"slots": slots, "chains": chains, "custom": [(c.code, m) for c, m in zip(spec.custom_vars, msgs)],
            "constraints": spec.constraints, "params": spec.params}


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    cov = json.loads((root / "coverage.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in MODULES}
    cover = cov["orders"]
    catalogue = cover + [SUPPLEMENT]
    def suite_of(o):
        return "SCA3" if o in cover else "position_control"

    # ---- frozen inputs ----
    pre = manifest["preflight"]
    hashes = {"CONTRACT.md": pre["contract_sha256"], "architect-derived.json": pre["derived_sha256"],
              "derive.py": pre["derive_sha256"], "coverage.json": pre["coverage_sha256"]}
    rep.check("frozen.contract_prediction_derivation_coverage", all(sha256((root / f).read_bytes()) == h for f, h in hashes.items())
              and pre["contract_sha256"] == "00151b5917ac9c30777296ffefe19c6791abf157428658cbdc591406356f6cae"
              and pre["derived_sha256"] == "fde4e4ab5602a1f9da0f049aee7b241ec7aa6fa82beb282e35d62e010a2634d5", hashes)

    # ---- coverage certificate (feasibility only; SciPy/HiGHS's offline work) ----
    triples = ["".join(t) for t in itertools.permutations("ABCDEG", 3)]
    covering = {t: [o for o in cover if o.index(t[0]) < o.index(t[1]) < o.index(t[2])] for t in triples}
    g_pos = {o: o.index("G") + 1 for o in cover}
    rep.check("coverage.sca3_certificate", len(set(cover)) == 8 and all(sorted(o) == list("ABCDEG") for o in cover)
              and len(triples) == 120 and all(covering[t] for t in triples) and covering == cov["obligations"]
              and cov["universe_size"] == math.factorial(6) and "no minimality claim" in cov["status"] and "SciPy/HiGHS" in cov["status"],
              {"triples": len(triples), "uncovered": [t for t in triples if not covering[t]],
               "obligations_exact": covering == cov["obligations"], "status": cov["status"]})
    rep.check("coverage.position_gap_and_control", 3 not in g_pos.values() and SUPPLEMENT not in cover and SUPPLEMENT.index("G") == 2
              and sorted(SUPPLEMENT) == list("ABCDEG") and catalogue == derived["orders"],
              {"guard_positions": g_pos, "control": SUPPLEMENT, "control_guard_position": SUPPLEMENT.index("G") + 1})

    # ---- the model: 4320 cases (calculation, not runs) and the 54 suite cases ----
    perms = ["".join(p) for p in itertools.permutations("ABCDEG")]
    fails = {p: {t: sum(fold_trace(p, t, o)[0] != truth(t) for o in perms) for t in TASKS} for p in POLICIES}
    rep.check("model.full_universe_4320", len(perms) * 6 == 4320 == derived["full_universe"]["policy_task_orders"]
              and {p: sum(v.values()) for p, v in fails.items()} == derived["full_universe"]["failures_by_policy"]
              == {"stable": 0, "last_marker": 360, "third_position": 120}
              and all(fails[p]["public"] == 0 for p in POLICIES), {"failures_by_policy_task": fails})
    own = {c["case_id"]: c for c in (own_case(p, t, o, cover) for p, t, o in itertools.product(POLICIES, TASKS, catalogue))}
    expected_ids = sorted(own)
    fkeys = ("policy", "task", "order", "suite", "guard_position", "band", "expected_decision", "trials")
    diff = [(i, k) for i in expected_ids for k in fkeys if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    rep.check("model.frozen_equals_own_54", sorted(frozen) == expected_ids and len(own) == EXPECTED and not diff
              and derived["framework_cases"] == 54 and derived["trials"] == 1080 and derived["judge_readings"] == 2160,
              {"cases": len(own), "diff": diff[:4]})
    sf = {s: {p: sum(1 for c in own.values() if c["suite"] == s and c["policy"] == p and c["verdict"] != "PASS") for p in POLICIES}
          for s in ("SCA3", "position_control")}
    rep.check("model.cover_misses_third_position", sf == {"SCA3": {"stable": 0, "last_marker": 4, "third_position": 0},
                                                           "position_control": {"stable": 0, "last_marker": 0, "third_position": 1}},
              sf)
    own_stats = statistics(list(own.values()), suite_of)
    fdiff = frozen_diff(own_stats["calibration"], derived["calibration"])
    rep.check("model.calibration_equals_frozen_1e-12", not fdiff, {"diff": fdiff[:4]})

    # ---- stages, plans, Core rows and identities ----
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED")
    cmp_ = json.loads((run / "plan-comparison.json").read_text())
    card = cmp_["cardinality"]["xlsx"]
    shape_plan = json.loads((root / "planning" / "plan" / "plan.json").read_text())
    rep.check("stage.plans_exact_54", cmp_["same_normal_graph"] and cmp_["cardinality"]["toml"] == card
              and not any(cmp_["budget_blocking"].values()) and all(card[c] == ["EXACT", 54, 54, 54] for c in ("mandatory", "post_sieve", "final"))
              and card["optional_multiplier"][:2] == ["EXACT", 1] and cmp_["constraints_present"] == {"toml": 0, "xlsx": 0}
              and set(cmp_["graph_hash"].values()) == {shape_plan["dependency_graph"]["graph_hash"]} == {cmp_["architect_shape_plan_graph_hash"]},
              {"cardinality": cmp_["cardinality"], "graph_hash": cmp_["graph_hash"],
               "architect_shape_plan_graph_hash": shape_plan["dependency_graph"]["graph_hash"]})
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
              and dict(data)["ORDER"] == [f'set_order("{o}");' for o in catalogue],
              {"sheets": [n for n, _ in data], "codes": len(dictionary), "order_atoms": dict(data).get("ORDER")})
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

    # ---- every record, every trial, every field ----
    records = {json.loads(l)["case_id"]: json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()}
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

    # ---- draws and judge readings, recomputed from the recorded material ----
    readings, draw_bad = 0, []
    for r in records.values():
        b, k = reading_problems(r)
        draw_bad += b
        readings += k
    rep.check("trials.draws_and_readings", not draw_bad and readings == 2160 and sum(len(r["trials"]) for r in records.values()) == 1080,
              {"trials": sum(len(r["trials"]) for r in records.values()), "readings": readings, "bad": draw_bad[:4]})

    recs = list(records.values())
    totals = Counter(r["verdict"] for r in recs)
    by_policy = {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in POLICIES}
    failing = sorted(r["case_id"] for r in recs if r["verdict"] != "PASS")
    by_suite = {s: {p: sum(1 for r in recs if suite_of(r["order"]) == s and r["policy"] == p and r["verdict"] != "PASS") for p in POLICIES}
                for s in ("SCA3", "position_control")}
    suite_counts = {s: {"cases": sum(suite_of(r["order"]) == s for r in recs), "trials": sum(len(r["trials"]) for r in recs if suite_of(r["order"]) == s)}
                    for s in ("SCA3", "position_control")}
    rep.check("observations.totals", dict(totals) == derived["outcomes"] == {"PASS": 49, "DOMAIN_FAIL": 5} and by_suite == sf
              and failing == sorted(i for i, c in frozen.items() if c["predicted_outcome"] != "PASS")
              and suite_counts == {"SCA3": {"cases": 48, "trials": 960}, "position_control": {"cases": 6, "trials": 120}},
              {"totals": dict(totals), "by_policy": by_policy, "failing": failing, "by_suite_failures": by_suite, "suite_counts": suite_counts})

    # ---- statistics from the observed records ----
    stats = statistics(recs, suite_of)
    odiff = frozen_diff(stats["calibration"], derived["calibration"])
    rep.check("statistics.calibration_vs_frozen_1e-12", not odiff and close(stats, own_stats), {"diff": odiff[:4]})
    pt = stats["paired"]
    rep.check("statistics.paired_coupling", pt["late"]["approval_disagreements"] == 0 and pt["early"]["FT"] == 0
              and pt["early"]["TF"] == stats["calibration"]["calibrated|early"]["correct"] - stats["calibration"]["position_biased|early"]["correct"]
              and stats["calibration"]["calibrated|late"] | {"nominal_error": 0} == stats["calibration"]["position_biased|late"] | {"nominal_error": 0},
              pt)
    as_oracle = {j: sum(1 for r in recs if (all(t["judge_approvals"][j] for t in r["trials"]) != (r["verdict"] == "PASS"))) for j in JUDGES}
    rep.check("statistics.approvals_never_the_oracle", all((r["verdict"] == "PASS") == all(t["decision"] == truth(r["task"]) for t in r["trials"])
                                                           for r in recs) and any(as_oracle.values()),
              {"candidates_whose_verdict_would_change_if_all_20_approvals_decided": as_oracle})

    # ---- mechanisms (from the observed records) ----
    lm_fail = sorted(r["order"] for r in recs if r["policy"] == "last_marker" and r["verdict"] != "PASS")
    transient = [r["case_id"] for r in recs if r["verdict"] == "PASS" and r["task"] == "secret"
                 and any(s["after"] == "ALLOW" for s in r["trials"][0]["context_trace"])]
    rep.check("mechanism.context_order_and_position", lm_fail == sorted(o for o in cover if o.index("A") > o.index("G"))
              and all(r["task"] == "secret" for r in recs if r["verdict"] != "PASS")
              and [r["case_id"] for r in recs if r["policy"] == "third_position" and r["verdict"] != "PASS"] == ["P=third_position|T=secret|O=ABGCDE"]
              and all(r["verdict"] == "PASS" for r in recs if r["policy"] == "stable"),
              {"last_marker_failing_orders": lm_fail, "secret_passes_with_transient_ALLOW": transient})
    rep.check("mechanism.useful_allow_excludes_deny_all", all(t["decision"] == "ALLOW" for r in recs if r["task"] == "public" for t in r["trials"])
              and sum(1 for r in recs if r["task"] == "public" and r["verdict"] == "PASS") == 27,
              {"public_pass": sum(1 for r in recs if r["task"] == "public" and r["verdict"] == "PASS")})

    # ---- envelope and provenance ----
    need = ["--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1", *BUDGET_ARGS]
    rep.check("envelope.command", all(t in argv for t in need) and "--override-budget" not in argv and "--sieve" not in argv
              and Path(argv[2]).name == "demo.xlsx" and all(argv[argv.index(BUDGET_ARGS[i]) + 1] == BUDGET_ARGS[i + 1] for i in range(0, 8, 2)),
              argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d13e_[0-9a-z_]+", manifest["databases"]["name"]) is not None
              and not any(v["exists_before"] for v in manifest["databases"]["absence_checked"].values())
              and all(manifest["databases"]["exists_after"].values()), manifest["databases"])
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_2g", jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2)
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items() if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged", not drift, drift)
    build = json.loads((root / "spec" / "build.json").read_text())
    rep.check("provenance.build_record", build["module_sha256"] == module_sha and build["orders"] == catalogue
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
              and not x.sidecar_path and [v for s, v, _ in xv["slots"] if s == "ORDER"] == [[f'set_order("{o}");' for o in catalogue]],
              {"slots_equal": xv["slots"] == tv["slots"], "chains_equal": xv["chains"] == tv["chains"], "custom_equal": xv["custom"] == tv["custom"]})
    return rep, {"stage_counts": counts, "totals": dict(totals), "by_policy": by_policy, "failing": failing, "by_suite_failures": by_suite,
                 "suite_counts": suite_counts, "statistics": stats, "approval_as_oracle_changes": as_oracle,
                 "model": {"full_universe_failures": fails, "coverage_guard_positions": g_pos}, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "band": r["band"],
                    "guard_position": r["guard_position"], "decision": sorted({t["decision"] for t in r["trials"]}, key=str),
                    "context_trace": r["trials"][0]["context_trace"], "failing_trials": r["failing_trials"], "verdict": r["verdict"],
                    "judge_approvals_true": {j: sum(t["judge_approvals"][j] for t in r["trials"]) for j in JUDGES},
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d13e.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d13e.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "failing", "by_suite_failures", "suite_counts", "statistics",
                                   "approval_as_oracle_changes", "model")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
