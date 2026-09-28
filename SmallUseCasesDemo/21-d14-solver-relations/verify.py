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


"""Independent offline verifier for one D14c evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports solver.py, transform.py, oracle.py, runtime.py or derive.py, never
connects to a database, never executes a candidate (candidates are parsed with `ast`). The population,
relabelling and dominated-bid transforms, every solver's answer (both DP policies predicted as the
maximum (value, ID tuple) over subsets feasible under their mask rule, the greedy scan), the exhaustive
optimum, feasible-subset count, optimal allocations, gaps, relations and verdicts are rebuilt here from
CONTRACT.md and compared with the frozen predictions, the decoded Core rows (including the native
FW_Permut RELABEL rows), the rendered candidates and every observation record.
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
POLICIES = ("exact_dp", "greedy_value", "min_only_dp")
INSTANCES = ("bundle_trap", "tie", "disjoint", "overlap")
EDITS = ("none", "dominated")
PERMS = [list(p) for p in itertools.permutations(range(3))]
SHEETS = ("HEAD", "IMPL", "INSTANCE", "RELABEL", "EDIT", "TAIL")
MODULES = ("solver", "transform", "oracle", "runtime")
EXPECTED = 144
LABELS = ("label(0);", "label(1);", "label(2);")
TABLE = {"bundle_trap": (((0, 1), 7), ((0,), 4), ((1,), 4), ((2,), 2)), "tie": (((0, 1), 8), ((0,), 4), ((1,), 4), ((2,), 2)),
         "disjoint": (((0,), 5), ((1,), 4), ((2,), 3), ((0, 1, 2), 6)), "overlap": (((0, 1), 6), ((1, 2), 5), ((0, 2), 4), ((2,), 2))}
VARIANT_KEYS = ["actual_value", "bids", "feasible", "feasible_subsets", "gap", "optimal", "optimal_allocations", "optimum",
                "reported_value", "selected", "value_correct"]
REC_KEYS = sorted(["schema", "contract", "id", "policy", "instance", "permutation", "edit", "variants", "relations", "verdict", "fw_var",
                   "solver_calls", "oracle_subset_checks", "carrier_slot", "source_sha256", "framework"])
BUDGET_ARGS = ["--budget-mandatory-rows", "200", "--budget-final-candidates", "200", "--budget-disk-bytes", "150000000",
               "--budget-wall-time-seconds", "600"]
WITNESSES = {
    "tie_exact_dp_three_bids": "P=exact_dp|I=tie|R=210|E=dominated",
    "tie_greedy_two_bids_also_optimal": "P=greedy_value|I=tie|R=210|E=dominated",
    "greedy_gap_6_on_disjoint": "P=greedy_value|I=disjoint|R=012|E=dominated",
    "min_only_symmetry_failure": "P=min_only_dp|I=disjoint|R=102|E=none",
    "min_only_infeasible_with_invariant_outputs": "P=min_only_dp|I=bundle_trap|R=012|E=dominated",
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
def bid_list(name, perm=(0, 1, 2), edit="none"):
    out = [{"id": f"b{k}", "items": sorted(perm[i] for i in items), "value": value} for k, (items, value) in enumerate(TABLE[name])]
    if edit == "dominated":
        out.append({"id": "b4", "items": list(out[0]["items"]), "value": out[0]["value"] - 1})
    return out


def packs(bids, first_item_only=False):
    """[(value, id tuple)] for every subset whose (full or smallest-item) item sets are pairwise disjoint."""
    out = []
    for r in range(len(bids) + 1):
        for combo in itertools.combinations(bids, r):
            items = [i for b in combo for i in (b["items"][:1] if first_item_only else b["items"])]
            if len(items) == len(set(items)):
                out.append((sum(b["value"] for b in combo), tuple(b["id"] for b in combo)))
    return out


def solver_answer(policy, bids):
    if policy == "greedy_value":
        free, out = {0, 1, 2}, []
        for b in sorted(bids, key=lambda b: (-b["value"], b["id"])):
            if free.issuperset(b["items"]):
                out.append(b["id"])
                free.difference_update(b["items"])
        return sorted(out)
    return list(max(packs(bids, policy == "min_only_dp"))[1])


def variant(policy, bids):
    sel = solver_answer(policy, bids)
    chosen = [b for b in bids if b["id"] in sel]
    value = sum(b["value"] for b in chosen)
    items = [i for b in chosen for i in b["items"]]
    feasible = len(items) == len(set(items))
    ref = packs(bids)
    top = max(v for v, _ in ref)
    return {"bids": bids, "selected": sel, "reported_value": value, "actual_value": value, "feasible": feasible, "value_correct": True,
            "optimum": top, "feasible_subsets": len(ref), "optimal_allocations": sorted(list(ids) for v, ids in ref if v == top),
            "optimal": feasible and value == top, "gap": top - value if feasible else None}


def relations_of(v):
    return {"reference_relabel": v["base"]["optimum"] == v["relabeled"]["optimum"], "reference_edit": v["relabeled"]["optimum"] == v["edited"]["optimum"],
            "solver_relabel": v["base"]["reported_value"] == v["relabeled"]["reported_value"],
            "solver_edit": v["relabeled"]["reported_value"] == v["edited"]["reported_value"]}


def own_case(policy, name, perm, edit):
    v = {"base": variant(policy, bid_list(name)), "relabeled": variant(policy, bid_list(name, perm)),
         "edited": variant(policy, bid_list(name, perm, edit))}
    rel = relations_of(v)
    ok = all(x["feasible"] and x["value_correct"] and x["optimal"] for x in v.values()) and all(rel.values())
    return {"id": f"P={policy}|I={name}|R={''.join(map(str, perm))}|E={edit}", "policy": policy, "instance": name, "permutation": list(perm),
            "edit": edit, "variants": v, "relations": rel, "verdict": "PASS" if ok else "DOMAIN_FAIL",
            "oracle_subset_checks": {k: 1 << len(x["bids"]) for k, x in v.items()}}


def compare_record(r, o):
    """[(field, observed, expected)] for every record field and every field of the three variants."""
    checks = [(k, r.get(k), o[k]) for k in ("id", "policy", "instance", "permutation", "edit", "relations", "verdict", "oracle_subset_checks")]
    checks += [("schema", r.get("schema"), "d14c.observation/v1"), ("contract", r.get("contract"), "v1"), ("solver_calls", r.get("solver_calls"), 3),
               ("fw_var", r.get("fw_var"), 0 if o["verdict"] == "PASS" else 2),
               ("carrier_slot", r.get("carrier_slot"), "IMPL position 2 (legacy positional, not causal)"),
               ("variant_kinds", sorted(r.get("variants") or {}), ["base", "edited", "relabeled"])]
    for kind in ("base", "relabeled", "edited"):
        got, want = (r.get("variants") or {}).get(kind) or {}, o["variants"][kind]
        checks.append((f"{kind}.keys", sorted(got), VARIANT_KEYS))
        checks += [(f"{kind}.{k}", got.get(k), want[k]) for k in VARIANT_KEYS]
    return checks


def recheck(r):
    """Feasibility, values and relations recomputed from the recorded bids and selections alone (policy-blind)."""
    out = {}
    for kind, v in r["variants"].items():
        by_id = {b["id"]: b for b in v["bids"]}
        if len(by_id) != len(v["bids"]) or not set(v["selected"]) <= set(by_id) or len(set(v["selected"])) != len(v["selected"]):
            return None
        chosen = [by_id[i] for i in v["selected"]]
        items = [i for b in chosen for i in b["items"]]
        ref = packs(v["bids"])
        top = max(x for x, _ in ref)
        actual, feasible = sum(b["value"] for b in chosen), len(items) == len(set(items))
        out[kind] = {"actual_value": actual, "feasible": feasible, "value_correct": v["reported_value"] == actual, "optimum": top,
                     "optimal": feasible and actual == top, "gap": top - actual if feasible else None}
    return out


def tallies(recs):
    return {"outcomes": dict(Counter(r["verdict"] for r in recs)),
            "by_policy": {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in POLICIES},
            "by_policy_instance": {f"{p}|{i}": dict(Counter(r["verdict"] for r in recs if (r["policy"], r["instance"]) == (p, i)))
                                   for p in POLICIES for i in INSTANCES},
            "greedy_gaps": {i: sorted({v["gap"] for r in recs if r["policy"] == "greedy_value" and r["instance"] == i for v in r["variants"].values()})
                            for i in INSTANCES},
            "output_relations_hold_but_fail": sum(1 for r in recs if r["verdict"] != "PASS" and r["relations"]["solver_relabel"] and r["relations"]["solver_edit"]),
            "infeasible_results": sum(1 for r in recs for v in r["variants"].values() if not v["feasible"]),
            "solver_relabel_failures": sum(1 for r in recs if not r["relations"]["solver_relabel"]),
            "solver_edit_failures": sum(1 for r in recs if not r["relations"]["solver_edit"]),
            "subset_checks": sum(sum(r["oracle_subset_checks"].values()) for r in recs)}


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
    """Identity from impl, instance, the three rendered labels and edit, in slot order."""
    if [c[0] for c in calls] != ["impl", "instance", "label", "label", "label", "edit"] or sorted(c[1] for c in calls[2:5]) != [0, 1, 2] \
            or any(type(c[1]) is not int for c in calls[2:5]):
        raise ValueError(f"atom order {calls}")
    return f"P={calls[0][1]}|I={calls[1][1]}|R={''.join(str(c[1]) for c in calls[2:5])}|E={calls[5][1]}"


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

    # ---- frozen inputs and the model ----
    pre = manifest["preflight"]
    hashes = {"CONTRACT.md": pre["contract_sha256"], "architect-derived.json": pre["derived_sha256"], "derive.py": pre["derive_sha256"]}
    rep.check("frozen.contract_prediction_derivation", all(sha256((root / f).read_bytes()) == h for f, h in hashes.items())
              and pre["contract_sha256"] == "9d5d6024e0c49b95d46e587faa567c36ee3ca423fa2637a736a57e16457c4beb"
              and pre["derived_sha256"] == "0c78df7c00a434d3c49850aeaa1f597898a3c97095a2434c01a98c008ca17310"
              and pre["derive_sha256"] == "6b3802d4626f48a692dc79b845971d6955b8b4db2c06c898ef80a7eeec209312", hashes)
    own = {c["id"]: c for c in (own_case(*k) for k in itertools.product(POLICIES, INSTANCES, PERMS, EDITS))}
    expected_ids = sorted(own)
    fkeys = ("policy", "instance", "permutation", "edit", "variants", "relations")
    diff = [(i, k) for i in expected_ids for k in fkeys if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    own_t = tallies(list(own.values()))
    rep.check("model.frozen_equals_own_144", sorted(frozen) == expected_ids and len(own) == EXPECTED and not diff
              and derived["framework_cases"] == 144 and derived["solver_calls"] == 432 and derived["reference_subset_checks"] == 8064
              and own_t["outcomes"] == derived["outcomes"] == {"PASS": 72, "DOMAIN_FAIL": 72} and own_t["by_policy"] == derived["by_policy"]
              and own_t["subset_checks"] == 8064, {"cases": len(own), "diff": diff[:4], "tallies": own_t})
    tie = packs(bid_list("tie"))
    dom_ok = True
    for name, perm in itertools.product(INSTANCES, PERMS):
        ed = bid_list(name, perm, "dominated")
        b0 = ed[0]
        for v, ids in packs(ed):
            if "b4" in ids:
                swapped = [b0 if b["id"] == "b4" else b for b in ed if b["id"] in ids]
                items = [i for b in swapped for i in b["items"]]
                dom_ok &= "b0" not in ids and len(items) == len(set(items)) and sum(b["value"] for b in swapped) == v + 1
        dom_ok &= max(packs(ed))[0] == max(packs(bid_list(name, perm)))[0]
    rep.check("model.relations_and_ties", dom_ok and sorted(ids for v, ids in tie if v == 10) == [("b0", "b3"), ("b1", "b2", "b3")]
              and own_t["greedy_gaps"] == {"bundle_trap": [1], "tie": [0], "disjoint": [6], "overlap": [0]}
              and own_t["output_relations_hold_but_fail"] == 54 and max(packs([]))[0] == 0 and len(packs([])) == 1,
              {"dominated_swap_valid": dom_ok, "tie_optima": sorted(ids for v, ids in tie if v == 10)})

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
    relabel_only = (set(node_diff) == {"RELABEL"} and an["RELABEL"]["attrs"]["verb"] == "FW_Combi(1)" and xn["RELABEL"]["attrs"]["verb"] == "FW_Permut()"
                    and {**an["RELABEL"], "attrs": {**an["RELABEL"]["attrs"], "verb": "FW_Permut()"}} == xn["RELABEL"])
    edges = lambda p: sorted(map(json.dumps, p["dependency_graph"]["graph"]["edges"]))
    rep.check("stage.plans_exact_144", cmp_["cardinality"]["toml"] == card and not any(cmp_["budget_blocking"].values())
              and all(card[c] == ["EXACT", 144, 144, 144] for c in ("mandatory", "post_sieve", "final"))
              and card["optional_multiplier"][:2] == ["EXACT", 1] and cmp_["constraints_present"] == {"toml": 0, "xlsx": 0}
              and tn == xn and edges(ours["toml"]) == edges(ours["xlsx"]) == edges(architect_plan) and relabel_only
              and ours["xlsx"]["cardinality"]["per_slot"] == architect_plan["cardinality"]["per_slot"],
              {"cardinality": cmp_["cardinality"], "graph_hash": {k: p["dependency_graph"]["graph_hash"] for k, p in ours.items()},
               "architect_shape_plan_graph_hash": architect_plan["dependency_graph"]["graph_hash"],
               "difference_from_architect_plan": "RELABEL slot verb attribute FW_Combi(1) (TOML placeholder) -> FW_Permut() (effective first verb); "
                                             "edges, chains and per-slot counts equal" if relabel_only else node_diff})
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
              and [c for c, _ in dictionary] == list(range(len(data) + 1, len(data) + 1 + len(flat))) and dict(data)["RELABEL"] == list(LABELS),
              {"sheets": [n for n, _ in data], "codes": len(dictionary)})
    endings = {r["sheet"]: r["ending"] for r in tables["names"]}
    frows = tables["fw_final"]
    base = (tables.get("fw_final_base_copy") or [{}])[0]
    cols = {mm.group(2): c for c in (frows or [{}])[0] for mm in [re.fullmatch(r"combos(\d+)_(\w+)", c)] if mm}
    def cell(row, sheet):
        v = row.get(cols[sheet])
        return list(base.get(cols[sheet]) if v is None else v)
    decoded, bad_rows, core_text, row_of, relabel_rows = [], [], {}, {}, Counter()
    for r in frows:
        try:
            codes = {s: cell(r, s) for s in SHEETS}
            if any(len(c) != (3 if s == "RELABEL" else 1) for s, c in codes.items()):
                raise ValueError(f"row cell arity {codes}")
            vals = {s: [code2val[c] for c in codes[s]] for s in SHEETS}
            cid = case_of([atom(vals["IMPL"][0]), atom(vals["INSTANCE"][0])] + [atom(v) for v in vals["RELABEL"]] + [atom(vals["EDIT"][0])])
            relabel_rows[tuple(vals["RELABEL"])] += 1
            core_text[cid] = join_cells([vals[s] for s in SHEETS], [endings[s] for s in SHEETS])
            row_of[cid] = r["combi_id"]
            decoded.append(cid)
        except (ValueError, KeyError, SyntaxError, AttributeError) as exc:
            bad_rows.append((r.get("combi_id"), str(exc)))
    want_rows = {tuple(LABELS[i] for i in p): 24 for p in PERMS}
    rep.check("core.relabel_rows_are_the_six_permutations", dict(relabel_rows) == want_rows and endings["RELABEL"] == "\n",
              {"relabel_rows": {"".join(k): v for k, v in relabel_rows.items()}})
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
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD) and "container" in (summary.get("sandbox_backend") or "")
              and "net=none" in (summary.get("sandbox_backend") or ""), {"outcomes": dict(outcomes), "backend": summary.get("sandbox_backend")})

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
                   ("rendered_identity", rendered.get(fw["source_ref"]), cid),
                   ("record_digest", sha256(json.dumps({k: v for k, v in r.items() if k != "framework"}, sort_keys=True,
                                                       separators=(",", ":")).encode("ascii")), fw.get("rec_sha256"))]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    recs = list(records.values())
    rc = {cid: recheck(r) for cid, r in records.items()}
    rc_bad = [cid for cid, x in rc.items() if x is None or any(x[k][f] != records[cid]["variants"][k][f] for k in x for f in x[k])
              or relations_of(records[cid]["variants"]) != records[cid]["relations"]
              or (records[cid]["verdict"] == "PASS") != (all(v["feasible"] and v["value_correct"] and v["optimal"] for v in records[cid]["variants"].values())
                                                          and all(records[cid]["relations"].values()))]
    rep.check("observations.recomputed_policy_blind", not rc_bad, {"mismatch": rc_bad[:3]})
    obs_t = tallies(recs)
    rep.check("observations.totals", obs_t == own_t and obs_t["outcomes"] == derived["outcomes"] and obs_t["by_policy"] == derived["by_policy"], obs_t)

    # ---- mechanisms (from the observed records) ----
    tie_ok = all(r["verdict"] == "PASS" for r in recs if r["instance"] == "tie" and r["policy"] in ("exact_dp", "greedy_value"))
    sel = {p: records[f"P={p}|I=tie|R=210|E=dominated"]["variants"]["base"]["selected"] for p in ("exact_dp", "greedy_value")}
    mo = [r for r in recs if r["policy"] == "min_only_dp"]
    rep.check("mechanism.ties_gaps_feasibility_symmetry", tie_ok and sel == {"exact_dp": ["b1", "b2", "b3"], "greedy_value": ["b0", "b3"]}
              and all(v["feasible"] for r in recs if r["policy"] == "greedy_value" for v in r["variants"].values())
              and all(not r["variants"]["base"]["optimal"] for r in mo) and all(r["verdict"] == "PASS" for r in recs if r["policy"] == "exact_dp")
              and not records["P=min_only_dp|I=disjoint|R=102|E=none"]["relations"]["solver_relabel"]
              and obs_t["output_relations_hold_but_fail"] == 54,
              {"tie_selections": sel, "min_only_infeasible_results": sum(1 for r in mo for v in r["variants"].values() if not v["feasible"]),
               "min_only_solver_relabel_failures": sum(1 for r in mo if not r["relations"]["solver_relabel"])})

    # ---- envelope and provenance ----
    need = ["--lang", "py", "--execution-policy-profile", "generated-default", "--candidate-origin", "generated", "--repeat", "1",
            "--executor-workers", "1", *BUDGET_ARGS]
    rep.check("envelope.command", all(t in argv for t in need) and "--override-budget" not in argv and "--sieve" not in argv
              and Path(argv[2]).name == "demo.xlsx" and all(argv[argv.index(BUDGET_ARGS[i]) + 1] == BUDGET_ARGS[i + 1] for i in range(0, 8, 2)),
              argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d14c_[0-9a-z_]+", manifest["databases"]["name"]) is not None
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
              {k: {"sha256": a["sha256"], "unchanged": comp_ok[k]} for k, a in comp.items()})
    x, t = fg.load_spec(root / "spec" / "demo.xlsx"), fg.load_spec(root / "spec" / "spec.toml")
    xv, tv = spec_view(x), spec_view(t)
    rep.check("provenance.xlsx_toml_core_input", sheets == fg.workbook_to_json(run / "inputs" / "demo.xlsx")["sheets"]
              == fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"] and xv == tv and not xv["constraints"] and not xv["params"]
              and not x.sidecar_path and xv["chains"]["RELABEL"] == ["FW_Permut()", "FW_Combi(size)"],
              {"slots_equal": xv["slots"] == tv["slots"], "chains_equal": xv["chains"] == tv["chains"], "custom_equal": xv["custom"] == tv["custom"]})
    return rep, {"stage_counts": counts, "tallies": obs_t, "relabel_rows": {"".join(k): v for k, v in relabel_rows.items()}, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"],
                    "variants": {k: {f: v[f] for f in ("selected", "reported_value", "actual_value", "feasible", "optimum", "optimal", "gap")}
                                 for k, v in r["variants"].items()},
                    "relations": r["relations"], "verdict": r["verdict"], "record_sha256": r["framework"].get("rec_sha256"),
                    "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d14c.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d14c.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks, **{k: data[k] for k in ("stage_counts", "tallies", "relabel_rows")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
