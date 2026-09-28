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

"""Independent offline verifier for one D1 campaign evidence directory.

    python verify.py --run evidence/<run-id>      # writes verification.json and witnesses.json there

It reads files only. It never imports sut.py, oracle.py or runtime.py, never
connects to a database and never executes a candidate: candidate programs are
parsed with `ast`, and their inlined sources are hashed, not run. Expected
identities and observations are derived here from CONTRACT.md v1 alone:
restricted-growth labels, cuts and restricted peers (§3); prefix effect
counts from key sets, B and E (§5); peer responses from the handler rule of
§2 and the control table of §4. Exit status 0 only if every check passes.
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
import tomllib
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = Path(__file__).resolve().parents[2] / "generator_trunk"

# ---- CONTRACT.md v1 constants ------------------------------------------------------------
POLICIES = ("volatile_transport", "durable_transport", "durable_order", "durable_payload",
            "durable_operation")
CONTROLS = ("none", "retry_fresh_transport", "new_order_equal_payload",
            "new_operation_same_order", "conflicting_retry")
PEER_REQUEST = {"retry_fresh_transport": ("O1", "OP1", 100), "new_order_equal_payload": ("O2", "OP1", 100),
                "new_operation_same_order": ("O1", "OP2", 100), "conflicting_retry": ("O1", "OP1", 101)}
CORE_PASS = {"volatile_transport": 1, "durable_transport": 4, "durable_order": 20,
             "durable_payload": 20, "durable_operation": 20}             # §5 table
PEER_PASS = {"volatile_transport": 2, "durable_transport": 2, "durable_order": 3,
             "durable_payload": 1, "durable_operation": 4}
CONTROL_VERDICTS = {                                                       # §4 table
    "volatile_transport": ("fail", "pass", "pass", "fail"),
    "durable_transport": ("fail", "pass", "pass", "fail"),
    "durable_order": ("pass", "pass", "fail", "pass"),
    "durable_payload": ("pass", "fail", "fail", "fail"),
    "durable_operation": ("pass", "pass", "pass", "pass")}
B_HIST, E_HIST = {1: 4, 2: 12, 3: 4}, {1: 1, 2: 7, 3: 12}
NA = "not_applicable"
POST_RUN_TOOLS = ("verify.py", "replay.py")   # read-only tools; their own hashes go into their outputs
SENSORS = ("core_at_most_once", "receipt_identity", "retry_dedup", "peer_independence",
           "conflict_handling", "contract_valid")
BAD = ("BROKEN", "INFRA_FAIL", "TIMEOUT", "CANCELLED", "SKIPPED")


def jsonable(v):
    """Detail values as JSON: mapping keys become strings, tuples/sets become lists."""
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
        return bool(ok)

    @property
    def ok(self):
        return all(c["passed"] for c in self.checks)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def case_id(impl, labels, cuts, control):
    return f"{impl}|L={labels}|C={cuts}|P={control}"


# ---- §3: the case space, enumerated independently ------------------------------------------
def restricted_growth(labels):
    top = -1
    for x in labels:
        if x > top + 1:
            return False
        top = max(top, x)
    return True


def raw_space():
    """The 600 raw rows as (impl, labels, cuts, control), in sheet-product order."""
    return [(impl, (0, l2, l3), (c1, c2), ctl)
            for impl, l2, l3, c1, c2, ctl in itertools.product(POLICIES, (0, 1), (0, 1, 2), (0, 1), (0, 1), CONTROLS)]


def valid(row):
    impl, labels, cuts, ctl = row
    return restricted_growth(labels) and (ctl == "none" or (labels == (0, 0, 0) and cuts == (0, 0)))


def as_id(row):
    impl, labels, cuts, ctl = row
    return case_id(impl, "".join(map(str, labels)), "".join(map(str, cuts)), ctl)


# ---- the sidecar's bonds, evaluated by this file's own reading of the schema ------------------
def eval_node(node, sel):
    if "all" in node:
        return all(eval_node(n, sel) for n in node["all"])
    if "any" in node:
        return any(eval_node(n, sel) for n in node["any"])
    if "not" in node:
        return not eval_node(node["not"], sel)
    value = sel[node["sheet"]]
    if "in" in node:
        return value in node["in"]
    if "ne" in node:
        return value != node["ne"]
    if "eq" in node:
        return value == node["eq"]
    raise ValueError(f"operator not understood by this verifier: {node}")


def bond_hits(sidecar, sel):
    hits = []
    for c in sidecar["constraints"]:
        if "sets" in c:
            holds = all(sel[s] in vals for s, vals in c["sets"].items())
        elif "assert" in c:
            holds = eval_node(c["assert"], sel)
        else:
            raise ValueError(f"bond form not understood by this verifier: {c}")
        forbid = c.get("polarity", "require" if "assert" in c else "forbid") == "forbid"
        if holds == forbid:
            hits.append(c["id"])
    return hits


# ---- §2, §4, §5: predicted observation for one case ------------------------------------------
def request(transport, order, op, amount):
    return {"transport_id": transport, "order_id": order, "operation_id": op,
            "payload": {"amount_minor": amount, "currency": "TST"}}


def effect(receipt, order, op, amount):
    return {"receipt_id": receipt, "order_id": order, "operation_id": op,
            "payload": {"amount_minor": amount, "currency": "TST"}}


def predict(impl, labels, cuts, control):
    """Predicted observation, sensors and verdict, from key sets and the control rules only."""
    epochs = (0, cuts[0], cuts[0] + cuts[1])
    if impl == "volatile_transport":
        keys = list(zip(labels, epochs))          # E: identity x process lifetime
    elif impl == "durable_transport":
        keys = list(labels)                       # B: identity classes
    else:
        keys = ["O1/OP1"] * 3                     # order, payload and operation keys coincide on the core
    first_rank, deliveries = {}, []
    for i, (label, key) in enumerate(zip(labels, keys)):
        new = key not in first_rank
        if new:
            first_rank[key] = len(first_rank) + 1
        deliveries.append({"index": i + 1, "label": label, "restart_before": i > 0 and cuts[i - 1] == 1,
                           "epoch": epochs[i], "request": request(f"T{label}", "O1", "OP1", 100),
                           "response": {"status": "APPLIED" if new else "REPLAY", "receipt_id": first_rank[key],
                                        "order_id": "O1", "operation_id": "OP1"},
                           "effects_after": len(first_rank)})
    n = len(first_rank)
    pre = [effect(r, "O1", "OP1", 100) for r in range(1, n + 1)]
    obs = {"deliveries": deliveries, "pre_peer_ledger": pre, "pre_peer_multiplicity": {"O1/OP1": n},
           "first_receipt": 1, "peer": None, "post_peer_ledger": pre}
    sensors = {"core_at_most_once": n == 1, "receipt_identity": True,
               "retry_dedup": NA, "peer_independence": NA, "conflict_handling": NA}
    if control != "none":
        order, op, amount = PEER_REQUEST[control]
        req = request("T3", order, op, amount)
        same_key = {"volatile_transport": False, "durable_transport": False,      # T3 is fresh
                    "durable_order": order == "O1", "durable_payload": amount == 100,
                    "durable_operation": (order, op) == ("O1", "OP1")}[impl]
        if not same_key:              # §2 cache miss: append an effect
            resp = {"status": "APPLIED", "receipt_id": n + 1, "order_id": order, "operation_id": op}
            post, delta = pre + [effect(n + 1, order, op, amount)], 1
        elif amount == 100:           # hit, equal payload: stored receipt, stored identity
            resp = {"status": "REPLAY", "receipt_id": 1, "order_id": "O1", "operation_id": "OP1"}
            post, delta = pre, 0
        else:                         # hit, different payload
            resp = {"status": "CONFLICT", "receipt_id": None, "order_id": order, "operation_id": op}
            post, delta = pre, 0
        obs["peer"] = {"restart_before": False, "request": req, "response": resp, "effect_delta": delta}
        obs["post_peer_ledger"] = post
        if resp["status"] == "REPLAY" and (order, op) != ("O1", "OP1"):
            sensors["receipt_identity"] = False
        normative = {"retry_fresh_transport": ("REPLAY", 1, "O1", "OP1", 0),
                     "new_order_equal_payload": ("APPLIED", n + 1, "O2", "OP1", 1),
                     "new_operation_same_order": ("APPLIED", n + 1, "O1", "OP2", 1),
                     "conflicting_retry": ("CONFLICT", None, "O1", "OP1", 0)}[control]
        got = (resp["status"], resp["receipt_id"], resp["order_id"], resp["operation_id"], delta)
        sensor = {"retry_fresh_transport": "retry_dedup", "conflicting_retry": "conflict_handling"}.get(
            control, "peer_independence")
        sensors[sensor] = got == normative
    applicable = [v for v in sensors.values() if v != NA]
    sensors["contract_valid"] = all(applicable)
    sensors["sensors_agree"] = True
    return obs, sensors


# ---- candidate parsing (no execution) ---------------------------------------------------------
def parse_candidate(src: str):
    tree = ast.parse(src)
    values, labels, sources, tail = {}, None, None, False
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("IMPL", "CUT1", "CUT2", "CONTROL"):
                if name in values:
                    raise ValueError(f"{name} assigned twice")
                values[name] = ast.literal_eval(node.value)
            elif name == "L":
                if labels is not None:
                    raise ValueError("L assigned twice")
                labels = list(ast.literal_eval(node.value))
            elif name == "_D1_SOURCES":
                sources = ast.literal_eval(node.value)
            elif name == "_verdict":
                tail = True
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "append"
              and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "L"):
            labels.append(ast.literal_eval(node.value.args[0]))
    if set(values) != {"IMPL", "CUT1", "CUT2", "CONTROL"} or labels is None or len(labels) != 3:
        raise ValueError(f"incomplete assignment set: {sorted(values)}, L={labels}")
    ident = case_id(values["IMPL"], "".join(map(str, labels)), f"{values['CUT1']}{values['CUT2']}", values["CONTROL"])
    return ident, sources, tail


def read_candidates(tar_path: Path):
    out = {}
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tar_path.read_bytes()))) as tar:
        for m in tar.getmembers():
            out[Path(m.name).name] = tar.extractfile(m).read()
    return out


def verify(run: Path, root: Path = HERE):
    """Verify `run` against the D1 inputs under `root` (default: this folder; an input archive
    such as archive/<run-id>/inputs re-verifies a campaign from its frozen inputs)."""
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    commands = json.loads((run / "commands.json").read_text())
    run_id = manifest["run_id"]
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}

    # 1. Independent case space and the bonds -----------------------------------------------------
    rgs = sorted("".join(map(str, l)) for l in itertools.product((0,), (0, 1), (0, 1, 2)) if restricted_growth(l))
    rep.check("space.rgs_partitions", rgs == ["000", "001", "010", "011", "012"], rgs)
    raw = raw_space()
    rep.check("space.raw_600", len(raw) == len(set(raw)) == 600, len(raw))
    after_identity = [r for r in raw if restricted_growth(r[1])]
    expected = sorted(as_id(r) for r in raw if valid(r))
    rep.check("space.after_identity_500", len(after_identity) == 500, len(after_identity))
    rep.check("space.valid_120", len(expected) == len(set(expected)) == 120, len(expected))
    derived = json.loads((root / "architect-derived.json").read_text())
    rep.check("space.equals_architect_derived_ids", expected == sorted(derived["expected_case_ids"]),
              "independent enumeration vs architect-derived.json")

    spec = tomllib.loads((root / "spec" / "spec.toml").read_text())
    vals = {s["sheet"]: s["values"] for s in spec["slots"]}
    rep.check("spec.sheet_order", [s["sheet"] for s in spec["slots"]] ==
              ["HEAD", "IMPL", "L1", "L2", "L3", "CUT1", "CUT2", "CONTROL", "TAIL"])
    rep.check("spec.catalogue_semantics", (
        [ast.literal_eval(v.split("=", 1)[1].strip()) for v in vals["IMPL"]] == list(POLICIES)
        and [ast.literal_eval(v.split("=", 1)[1].strip()) for v in vals["CONTROL"]] == list(CONTROLS)
        and vals["L1"] == ["L = [0]"] and vals["L2"] == [f"L.append({i})" for i in (0, 1)]
        and vals["L3"] == [f"L.append({i})" for i in (0, 1, 2)]
        and vals["CUT1"] == ["CUT1 = 0", "CUT1 = 1"] and vals["CUT2"] == ["CUT2 = 0", "CUT2 = 1"]))
    sidecar_path = root / "spec" / "demo.constraints.json"          # the XLSX input's companion
    sidecar = json.loads(sidecar_path.read_text())
    side_sha = sha256(sidecar_path.read_bytes())
    run_sidecar = run / "run" / "sidecar.json"                        # what the sieve stage recorded
    rep.check("sidecar.sieve_record_equals_companion", run_sidecar.is_file() and
              json.loads(run_sidecar.read_text()) == sidecar, str(run_sidecar))
    run_json = json.loads((run / "run" / "run.json").read_text())
    stages_gen = json.loads((run / "run" / "stages" / "gen.json").read_text())
    gen_side = [a for a in stages_gen.get("artifacts", []) if a["kind"] == "input.constraints_sidecar"]
    wb_copy = run / "run" / "wb__demo.constraints.json"
    chain = {"spec/demo.constraints.json": side_sha,
             "inputs/demo.constraints.json": sha256((run / "inputs" / "demo.constraints.json").read_bytes()),
             "manifest.constraints_companion": (manifest.get("constraints_companion") or {}).get("sha256"),
             "plan-xlsx.constraints_source": (json.loads((run / "plan-xlsx" / "plan.json").read_text())
                                              .get("constraints_source") or {}).get("sha256"),
             "run.json.constraints_sidecar_sha256": run_json.get("constraints_sidecar_sha256"),
             "gen.artifact.input.constraints_sidecar": gen_side[0]["sha256"] if gen_side else None,
             "run wb/demo.constraints.json": sha256(wb_copy.read_bytes()) if wb_copy.is_file() else None}
    rep.check("sidecar.companion_hash_chain", len(set(chain.values())) == 1, chain)
    rep.check("sidecar.order", [c["id"] for c in sidecar["constraints"]] == ["canonical_identity", "peer_baseline"])
    matched, kept, agree = Counter(), 0, True
    for impl, labels, cuts, ctl in raw:
        sel = {"IMPL": vals["IMPL"][POLICIES.index(impl)], "L1": vals["L1"][0],
               "L2": vals["L2"][labels[1]], "L3": vals["L3"][labels[2]],
               "CUT1": vals["CUT1"][cuts[0]], "CUT2": vals["CUT2"][cuts[1]],
               "CONTROL": vals["CONTROL"][CONTROLS.index(ctl)]}
        hits = bond_hits(sidecar, sel)
        matched.update(hits)
        kept += not hits
        agree &= (not hits) == valid((impl, labels, cuts, ctl))
        agree &= ("canonical_identity" in hits) == (not restricted_growth(labels))
    truth = {"scanned": 600, "matched": dict(matched), "retained": kept,
             "after_canonical_identity_alone": 600 - matched["canonical_identity"]}
    rep.check("sidecar.truth_table_600_500_120", kept == 120 and truth["after_canonical_identity_alone"] == 500
              and matched == Counter({"canonical_identity": 100, "peer_baseline": 460}) and agree, truth)

    # 2. Stage counts --------------------------------------------------------------------------
    stages = {p.stem: json.loads(p.read_text()) for p in (run / "run" / "stages").glob("*.json")}
    def count(stage, name):
        return next((c["actual"] for c in stages.get(stage, {}).get("counts", []) if c["name"] == name), None)
    for st in ("gen", "core", "reader", "executor"):
        rep.check(f"stage.{st}.succeeded", stages.get(st, {}).get("status") == "SUCCEEDED",
                  stages.get(st, {}).get("status"))
    plan_toml = json.loads((run / "plan-toml" / "plan.json").read_text())["cardinality"]
    plan_cmp = json.loads((run / "plan-comparison.json").read_text())
    log = (run / "logs" / "bundle_run.log").read_text(errors="replace")
    sieve = {m.group(1): int(m.group(2)) for m in re.finditer(r"rule (\S+): matched (\d+) row", log)}
    m = re.search(r"sieve: scanned (\d+), unique removals (\d+) \(overlap (\d+)\) → fw_final now (\d+)", log)
    sieve_line = [int(x) for x in m.groups()] if m else None
    db = json.loads((run / "db-export.json").read_text())
    counts = {
        "plan_mandatory": (plan_toml["mandatory"]["mode"], plan_toml["mandatory"]["value"]),
        "plan_final": (plan_toml["final"]["mode"], plan_toml["final"]["value"]),
        "core_fw_final_before_sieve": count("core", "fw_final"),
        "sieve_rule_matches": sieve, "sieve_scanned_removed_overlap_kept": sieve_line,
        "after_canonical_identity_alone": (sieve_line[0] - sieve.get("canonical_identity", 0)) if sieve_line else None,
        "fw_final_rows_in_db_after_sieve": len(db["main_db"]["fw_final_after_sieve"]),
        "optional_multiplier": count("core", "optional_multiplier") or 1,
        "reader_candidates": count("reader", "candidates"),
        "executor_processed": count("executor", "processed"),
        "results_v2_rows": len(db["results_db"]["results_v2"]),
    }
    plan_xlsx = json.loads((run / "plan-xlsx" / "plan.json").read_text())
    rep.check("stage.plan_exact_600_120", counts["plan_mandatory"] == ("EXACT", 600)
              and counts["plan_final"] == ("EXACT", 120), [counts["plan_mandatory"], counts["plan_final"]])
    xc = plan_xlsx["cardinality"]
    rep.check("stage.plan_xlsx_two_rules_exact_600_120", plan_xlsx["constraints_present"] == 2
              and (xc["mandatory"]["mode"], xc["mandatory"]["value"], xc["final"]["mode"], xc["final"]["value"])
              == ("EXACT", 600, "EXACT", 120), [plan_xlsx["constraints_present"], xc["mandatory"]["value"],
                                                  xc["final"]["value"]])
    explain = (run / "constraints-explain-xlsx.log").read_text()
    rep.check("stage.explain_xlsx_lists_both_rules", "canonical_identity" in explain and "peer_baseline" in explain
              and "demo.constraints.json" in explain)
    rep.check("stage.plan_toml_xlsx_same_program", plan_cmp["same_sheets_verbs_sizes"]
              and plan_cmp["same_dependency_graph"], plan_cmp["dependency_graph_sha256"])
    rep.check("stage.core_600", counts["core_fw_final_before_sieve"] == 600, counts["core_fw_final_before_sieve"])
    rep.check("stage.sieve_600_500_120", sieve == {"canonical_identity": 100, "peer_baseline": 460}
              and sieve_line == [600, 480, 80, 120] and counts["after_canonical_identity_alone"] == 500,
              {"rules": sieve, "scanned/removed/overlap/kept": sieve_line})
    rep.check("stage.fw_final_120", counts["fw_final_rows_in_db_after_sieve"] == 120)
    rep.check("stage.reader_120", counts["reader_candidates"] == 120, counts["reader_candidates"])
    rep.check("stage.executor_120", counts["executor_processed"] == 120 and counts["results_v2_rows"] == 120,
              [counts["executor_processed"], counts["results_v2_rows"]])

    # fw_final decoded through the dictionary and the base row, independently of the Reader
    code2val = {int(r["bigint"]): (r["value"] or "") for r in db["main_db"]["NumberToValue1"]}
    base_rows = next(iter(db["main_db"]["fw_final_base_tables"].values()), [{}])
    base = base_rows[0] if base_rows else {}
    decoded = []
    col_of = {}                        # "combos<N>_<SHEET>" -> SHEET (the sieve's own column rule)
    for col in (db["main_db"]["fw_final_after_sieve"] or [{}])[0]:
        if col.startswith("combos") and "_" in col:
            col_of[col.split("_", 1)[1]] = col
    rep.check("identity.fw_final_columns", [c for c in col_of] ==
              ["HEAD", "IMPL", "L1", "L2", "L3", "CUT1", "CUT2", "CONTROL", "TAIL"], col_of)
    for row in db["main_db"]["fw_final_after_sieve"]:
        sel = {}
        for sheet in ("IMPL", "L2", "L3", "CUT1", "CUT2", "CONTROL"):
            col = col_of.get(sheet, "")
            arr = row.get(col) or base.get(col) or []     # an empty cell inherits the base row
            sel[sheet] = [code2val[int(c)].strip() for c in arr]
        try:
            impl = ast.literal_eval(sel["IMPL"][0].split("=", 1)[1].strip())
            ctl = ast.literal_eval(sel["CONTROL"][0].split("=", 1)[1].strip())
            labels = "0" + sel["L2"][0][9] + sel["L3"][0][9]
            decoded.append(case_id(impl, labels, sel["CUT1"][0][-1] + sel["CUT2"][0][-1], ctl))
        except (IndexError, KeyError, ValueError, SyntaxError) as exc:
            decoded.append(f"undecodable:{row.get('combi_id')}:{exc}")
    rep.check("identity.fw_final_equals_expected", sorted(decoded) == expected,
              {"missing": sorted(set(expected) - set(decoded))[:5], "extra": sorted(set(decoded) - set(expected))[:5],
               "duplicates": [k for k, v in Counter(decoded).items() if v > 1][:5]})

    # 3. Reader: rendered candidates ------------------------------------------------------------
    cands = read_candidates(run / "candidates.tar.gz")
    head_ok, tail_ok, rendered, errors = True, True, {}, []
    for name, data in sorted(cands.items()):
        try:
            ident, sources, tail = parse_candidate(data.decode("utf-8"))
        except (ValueError, SyntaxError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        rendered[name] = ident
        head_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
        tail_ok &= tail
    rep.check("reader.parse_all", not errors and len(cands) == 120, errors[:5])
    rep.check("reader.inlined_sources_equal_audited_modules", head_ok, module_sha)
    rep.check("reader.tail_present", tail_ok)
    rset = sorted(rendered.values())
    rep.check("identity.reader_equals_expected", rset == expected,
              {"missing": sorted(set(expected) - set(rset))[:5], "extra": sorted(set(rset) - set(expected))[:5],
               "duplicates": [k for k, v in Counter(rset).items() if v > 1][:5]})

    # 4. Executor: attempts and outcomes --------------------------------------------------------
    rv2 = db["results_db"]["results_v2"]
    ids = [r["candidate_id"] for r in rv2]
    rep.check("executor.one_attempt_per_candidate", len(ids) == len(set(ids)) == 120
              and all(r["attempt"] == 1 and r["repeat_idx"] == 0 and r["run_id"] == run_id for r in rv2),
              Counter((r["attempt"], r["repeat_idx"]) for r in rv2))
    rep.check("executor.candidates_match_sources", sorted(f"{i}.py" for i in ids) == sorted(cands),
              "results_v2 candidate ids vs rendered files")
    outcomes = Counter(r["outcome"] for r in rv2)
    summary = json.loads((run / "run" / "executor-summary.json").read_text())
    rep.check("executor.no_infrastructure_outcomes", all(outcomes[b] == 0 for b in BAD)
              and all(summary["outcomes"].get(b, 0) == 0 for b in BAD), dict(outcomes))
    rep.check("executor.summary_matches_results_v2", summary["outcomes"].get("PASS") == outcomes["PASS"]
              and summary["outcomes"].get("DOMAIN_FAIL") == outcomes["DOMAIN_FAIL"]
              and summary.get("sandbox_backend") not in (None, ""), {"summary": summary["outcomes"],
                                                                     "sandbox_backend": summary.get("sandbox_backend")})

    # 5. Observations: every field against the independent prediction ---------------------------
    records = [json.loads(l) for l in (run / "observations.jsonl").read_text().splitlines() if l.strip()]
    obs_ids = sorted(r["case_id"] for r in records)
    rep.check("identity.executor_equals_expected", obs_ids == expected,
              {"missing": sorted(set(expected) - set(obs_ids))[:5], "extra": sorted(set(obs_ids) - set(expected))[:5],
               "duplicates": [k for k, v in Counter(obs_ids).items() if v > 1][:5]})
    by_rv2 = {r["candidate_id"]: r for r in rv2}
    mismatches, field_count, table = [], 0, {}
    for rec in records:
        impl, labels, cuts, ctl = rec["impl"], rec["labels"], rec["cuts"], rec["control"]
        exp_obs, exp_sensors = predict(impl, tuple(int(c) for c in labels), tuple(int(c) for c in cuts), ctl)
        exp_verdict = "PASS" if exp_sensors["contract_valid"] else "DOMAIN_FAIL"
        fw = rec["framework"]
        problems = []
        for key in exp_obs:
            field_count += 1
            if rec["observation"].get(key) != exp_obs[key]:
                problems.append(f"observation.{key}")
        for key in list(SENSORS) + ["sensors_agree"]:
            field_count += 1
            if rec["checks"].get(key) != exp_sensors[key]:
                problems.append(f"checks.{key}")
        cand_name = fw["source_ref"]
        row = by_rv2.get(fw["candidate_id"], {})
        for name, got, want in (
                ("verdict", rec["verdict"], exp_verdict),
                ("fw_var", rec["fw_var"], 0 if exp_verdict == "PASS" else 2),
                ("metrics_fw_var", fw["metrics_fw_var"], rec["fw_var"]),
                ("results_v2.outcome", row.get("outcome"), exp_verdict),
                ("results_v2.verdict_code", row.get("verdict_code"), rec["fw_var"]),
                ("run_id", fw["run_id"], run_id),
                ("rendered_case", rendered.get(cand_name), rec["case_id"]),
                ("candidate_sha256", fw["source_sha256"], sha256(cands.get(cand_name, b""))),
                ("record_source_sha256", rec["source_sha256"], module_sha),
                ("population", rec["population"], "core" if ctl == "none" else "peer")):
            field_count += 1
            if got != want:
                problems.append(f"{name}: {got!r} != {want!r}")
        if problems:
            mismatches.append({"case_id": rec["case_id"], "problems": problems})
        cell = table.setdefault(impl, {"core": [0, 0], "peer": [0, 0]})
        cell[rec["population"]][0 if rec["verdict"] == "PASS" else 1] += 1
    rep.check("observations.all_fields_match_prediction", not mismatches,
              {"fields_compared": field_count, "mismatching_cases": mismatches[:10]})
    rep.check("observations.per_policy_table", all(
        table[p]["core"][0] == CORE_PASS[p] and table[p]["peer"][0] == PEER_PASS[p]
        and sum(table[p]["core"]) == 20 and sum(table[p]["peer"]) == 4 for p in POLICIES), table)
    peer_cells = {p: tuple("pass" if r["verdict"] == "PASS" else "fail" for c in CONTROLS[1:] for r in records
                           if r["impl"] == p and r["control"] == c) for p in POLICIES}
    rep.check("observations.control_table", peer_cells == CONTROL_VERDICTS, peer_cells)
    totals = Counter(r["verdict"] for r in records)
    rep.check("observations.aggregate_77_43", totals == Counter({"PASS": 77, "DOMAIN_FAIL": 43}), dict(totals))
    core = [r for r in records if r["control"] == "none" and r["impl"] == "volatile_transport"]
    b_hist = Counter(len(set(r["labels"])) for r in core)
    e_hist = Counter(len(set(zip(r["labels"], (0, int(r["cuts"][0]), int(r["cuts"][0]) + int(r["cuts"][1])))))
                     for r in core)
    obs_e = Counter(r["observation"]["pre_peer_multiplicity"]["O1/OP1"] for r in core)
    obs_b = Counter(r["observation"]["pre_peer_multiplicity"]["O1/OP1"] for r in records
                    if r["control"] == "none" and r["impl"] == "durable_transport")
    rep.check("observations.B_E_histograms", dict(b_hist) == B_HIST and dict(e_hist) == E_HIST
              and dict(obs_b) == B_HIST and dict(obs_e) == E_HIST,
              {"B": dict(b_hist), "E": dict(e_hist), "observed_durable_transport_effects": dict(obs_b),
               "observed_volatile_transport_effects": dict(obs_e)})

    # 6. Provenance and run envelope ------------------------------------------------------------
    argv = commands[0]["argv"]
    need = ["--sieve", "--lang", "py", "--execution-policy-profile", "generated-default", "--repeat", "1",
            "--executor-workers", "1", "--budget-mandatory-rows", "1000", "--budget-final-candidates", "1000",
            "--budget-disk-bytes", "200000000", "--budget-wall-time-seconds", "600"]
    rep.check("envelope.command_flags", all(t in argv for t in need) and "--override-budget" not in argv
              and "--unleash-initial-productivity-power" not in argv, argv[2:])
    rep.check("envelope.xlsx_is_the_run_input", manifest["input_kind"] == "xlsx"
              and Path(argv[2]).name == "demo.xlsx" and run_json.get("spec_path", "").endswith("demo.xlsx"),
              {"input_kind": manifest["input_kind"], "argv_input": argv[2], "run.json spec_path": run_json.get("spec_path")})
    copies = {n: sha256((run / "inputs" / n).read_bytes()) == sha256((root / "spec" / n).read_bytes())
              for n in ("spec.toml", "demo.xlsx", "demo.constraints.json")}
    rep.check("provenance.input_copies_equal_spec", all(copies.values()), copies)
    dbname = manifest["databases"]["name"]
    rep.check("envelope.owned_db_name", re.fullmatch(r"as0927_d1_[0-9a-z_]+", dbname) is not None
              and all(not v["exists_before"] for v in manifest["databases"]["absence_checked"].values()), dbname)
    jvm = (run / "logs" / "core.log").read_text(errors="replace") + (run / "logs" / "reader.log").read_text(errors="replace")
    rep.check("envelope.jvm_heap_2g", manifest["jvm"]["JAVA_TOOL_OPTIONS"] == "-Xmx2g"
              and jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g") >= 2,
              jvm.count("Picked up JAVA_TOOL_OPTIONS: -Xmx2g"))
    drift = {rel: h for rel, h in manifest["inputs_sha256"].items()
             if rel not in POST_RUN_TOOLS and sha256((root / rel).read_bytes()) != h}
    rep.check("provenance.inputs_unchanged_since_run", not drift, drift)
    rep.check("provenance.contract_hash", manifest["contract_sha256"] == sha256((root / "CONTRACT.md").read_bytes()))
    core_books = sorted((run / "run").glob("core_input__*.xlsx"))
    if core_books:
        sys.path.insert(0, str(GEN))
        import fwgen as fg                                   # Framework reader, not the SUT or oracle
        a = fg.workbook_to_json(core_books[0])["sheets"]
        b = fg.workbook_to_json(root / "spec" / "demo.xlsx")["sheets"]
        diff = [x["name"] for x, y in zip(a, b) if x != y] + (["<sheet list>"] if [x["name"] for x in a] != [y["name"] for y in b] else [])
        rep.check("provenance.core_workbook_equals_demo_xlsx", not diff, {"differing_sheets": diff,
                                                                          "core_input": core_books[0].name})
    else:
        rep.check("provenance.core_workbook_equals_demo_xlsx", False, "no Core input workbook in evidence")

    return rep, {"stage_counts": counts, "sieve_truth_table": truth, "verdict_table": table,
                 "totals": dict(totals), "outcomes": dict(outcomes), "records": records,
                 "rendered": rendered, "expected": expected}


def witnesses(run: Path, data):
    """Pre-declared explanatory witnesses (ARCHITECTURE walkthrough), looked up in the observed records."""
    recs = {r["case_id"]: r for r in data["records"]}
    def brief(cid):
        r = recs[cid]
        o = r["observation"]
        out = {"case_id": cid, "candidate": r["framework"]["source_ref"], "candidate_id": r["framework"]["candidate_id"],
               "candidate_sha256": r["framework"]["source_sha256"], "verdict": r["verdict"],
               "framework_outcome": r["framework"]["outcome"],
               "core": [(d["request"]["transport_id"], d["epoch"], d["response"]["status"], d["response"]["receipt_id"],
                         f'{d["response"]["order_id"]}/{d["response"]["operation_id"]}', d["effects_after"])
                        for d in o["deliveries"]],
               "failing_sensors": [k for k, v in r["checks"].items() if v is False],
               "replay": f"python replay.py --run {run.relative_to(HERE)} --case '{cid}'"}
        if o["peer"]:
            p = o["peer"]
            out["peer"] = {"request": f'{p["request"]["transport_id"]} {p["request"]["order_id"]}/'
                                      f'{p["request"]["operation_id"]} amount={p["request"]["payload"]["amount_minor"]}',
                           "response": p["response"], "effect_delta": p["effect_delta"]}
        return out
    return {
        "schema": "d1.witnesses/v1", "run": run.name,
        "note": "Explanatory witnesses chosen before the run (ARCHITECTURE walkthrough) and looked up in the "
                "complete campaign; not held-out discovery and not a certified minimum suite.",
        "defective_policy_witnesses": [brief(c) for c in (
            "volatile_transport|L=000|C=01|P=none", "durable_transport|L=001|C=00|P=none",
            "durable_order|L=000|C=00|P=new_operation_same_order",
            "durable_payload|L=000|C=00|P=new_order_equal_payload")],
        "positive_control": [brief(f"durable_operation|L=000|C=00|P={c}") for c in CONTROLS],
        "contrast_1_single_retry": [brief(f"{p}|L=000|C=00|P=none") for p in POLICIES],
        "contrast_2_restart_only": [brief(f"{p}|L=000|C=01|P=none") for p in POLICIES],
        "contrast_3_new_transport_identity": [brief(f"{p}|L=001|C=00|P=none") for p in POLICIES],
        "contrast_4_peer_controls": [brief(f"{p}|L=000|C=00|P={c}") for p in POLICIES for c in CONTROLS[1:]],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--inputs-root", type=Path, default=HERE,
                    help="D1 inputs to verify against (default: this folder); e.g. archive/<run-id>/inputs")
    ap.add_argument("--out", type=Path, default=None,
                    help="where to write verification.json / witnesses.json (default: the run directory)")
    a = ap.parse_args()
    run = a.run.resolve()
    out_dir = (a.out or run).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    rep, data = verify(run, a.inputs_root.resolve())
    out = {"schema": "d1.verification/v1", "run": run.name, "passed": rep.ok,
           "verifier_sha256": sha256(Path(__file__).read_bytes()), "inputs_root": str(a.inputs_root.resolve()),
           "checks": rep.checks, "stage_counts": data["stage_counts"],
           "sieve_truth_table": data["sieve_truth_table"], "verdict_table": data["verdict_table"],
           "totals": data["totals"], "executor_outcomes": data["outcomes"]}
    (out_dir / "verification.json").write_text(json.dumps(out, indent=2, default=list) + "\n", encoding="utf-8")
    if all(c in {r["case_id"] for r in data["records"]} for c in data["expected"]):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed"
          + ("" if not failed else "; FAILED: " + ", ".join(c["check"] for c in failed)))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
