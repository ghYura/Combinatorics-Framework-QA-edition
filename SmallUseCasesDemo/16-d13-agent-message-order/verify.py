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

"""Independent offline verifier for one D13c evidence directory.

    python verify.py --run evidence/<run-id> [--inputs-root EXAMPLE-DIR] [--out DIR]

Reads files only: never imports sut.py, oracle.py, runtime.py or derive.py, never connects to a
database, never executes a candidate (candidates and dictionary atoms are parsed with `ast`).
Enabled schedules, preemptions, the 288 bond truth rows, both traces, the promise ledger and all
four checks are re-derived here from CONTRACT.md and compared with the frozen predictions, the live
sieve log, the decoded Core rows, the rendered candidates and every observation record.
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
POLICIES = ("compare_version", "trust_offer", "overwrite_owner")
MODES = ("independent", "after_A_offer")
CAPS = (0, 1, 2)
RULES = ("two_each", "causal_ready", "preemption_cap")
CHECKS = ("capacity_ok", "exclusive_promises_ok", "commitments_ok", "reference_ok")
RAW, AFTER_TWO, AFTER_CAUSAL, EXPECTED = 288, 108, 81, 54
ORDER = ("HEAD", "IMPL", "MODE", "CAP", "S1", "S2", "S3", "S4", "TAIL")
WORDS = ["".join(w) for w in itertools.product("AB", repeat=4)]
WITNESSES = {
    "trust_offer_double_allocation": "P=trust_offer|M=independent|K=2|S=ABAB",
    "overwrite_capacity_passes_promises_fail": "P=overwrite_owner|M=independent|K=2|S=ABAB",
    "compare_version_stale_refusal": "P=compare_version|M=independent|K=2|S=ABAB",
    "overwrite_withdraws_earlier_B_promise": "P=overwrite_owner|M=after_A_offer|K=1|S=ABBA",
    "serial_busy_control": "P=trust_offer|M=independent|K=0|S=AABB",
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
def ready(delivered, mode):
    out = []
    for agent in "AB":
        waiting = agent == "B" and mode == "after_A_offer" and delivered["A"] == 0 and delivered["B"] == 0
        if delivered[agent] < 2 and not waiting:
            out.append(agent)
    return out


def feasible(word, mode):
    delivered = {"A": 0, "B": 0}
    for agent in word:
        if agent not in ready(delivered, mode):
            return False
        delivered[agent] += 1
    return delivered == {"A": 2, "B": 2}


def switch_counts(word):
    """(switches, preemptions): a preemption leaves an agent whose commit is enabled but undelivered."""
    sw = [i for i in range(3) if word[i] != word[i + 1]]
    return len(sw), sum(1 for i in sw if word[: i + 1].count(word[i]) == 1)


def bond_expression(word):
    a = [1 if t == "A" else 0 for t in word]
    return int(a[0] != a[1]) + int(a[1] != a[2] and a[0] != a[1]) + int(a[2] != a[3] and a[0] != a[2] and a[1] != a[2])


def bond_truth(mode, cap, word):
    a = [1 if t == "A" else 0 for t in word]
    return {"two_each": sum(a) == 2, "causal_ready": mode == "independent" or a[0] == 1, "preemption_cap": bond_expression(word) <= cap}


def model(policy, mode, word):
    """The frozen event schema for one policy: harness enabledness, agent offers, coordinator state."""
    delivered, offers, alloc, ledger, version, trace = {"A": 0, "B": 0}, {}, {}, {}, 0, []
    for index, agent in enumerate(word, 1):
        before = ready(delivered, mode)
        delivered[agent] += 1
        step = delivered[agent]
        req = {"id": f"{agent}:{'inspect' if step == 1 else 'commit'}", "agent": agent, "kind": "inspect" if step == 1 else "commit",
               "resource": "R"}
        if step == 1:
            reply = {"available": not alloc, "version": version}
            offers[agent] = dict(reply)
        else:
            mine = offers[agent]
            req["offer_version"], req["offer_available"] = mine["version"], mine["available"]
            if not mine["available"]:
                reply = {"status": "BUSY", "ticket": None}
            elif policy == "compare_version" and (alloc or version != mine["version"]):
                reply = {"status": "STALE", "ticket": None}
            else:
                reply = {"status": "GRANTED", "ticket": "R:" + agent}
                if policy == "overwrite_owner":
                    alloc = {}
                alloc = {**alloc, agent: reply["ticket"]}
                ledger = {**ledger, agent: reply["ticket"]}
                version += 1
        trace.append({"index": index, "agent": agent, "local_step": step, "message": req["id"], "enabled_agents_before": before,
                      "request": req, "response": reply, "offers": json.loads(json.dumps(offers)), "version": version,
                      "allocations": dict(alloc), "issued_grants": dict(ledger)})
    return trace


def ledger_from_replies(trace):
    led, out = {}, []
    for e in trace:
        if e["response"].get("status") == "GRANTED":
            led = {**led, e["agent"]: e["response"]["ticket"]}
        out.append(led)
    return out


def own_case(policy, mode, cap, word):
    obs, ref = model(policy, mode, word), model("compare_version", mode, word)
    leds = ledger_from_replies(obs)
    checks = [{"index": o["index"], "capacity_ok": len(o["allocations"]) <= 1, "exclusive_promises_ok": len(led) <= 1,
               "commitments_ok": o["allocations"] == led, "reference_ok": o == r} for o, r, led in zip(obs, ref, leds)]
    failing = [c["index"] for c in checks if not all(c[k] for k in CHECKS)]
    sw, pre = switch_counts(word)
    return {"case_id": f"P={policy}|M={mode}|K={cap}|S={word}", "policy": policy, "mode": mode, "cap": cap, "schedule": word,
            "preemptions": pre, "context_switches": sw, "observed_trace": obs, "reference_trace": ref, "reconstructed_ledgers": leds,
            "integrity_ok": all(o["issued_grants"] == led for o, led in zip(obs, leds)), "checks": checks,
            "all_checks": {k: all(c[k] for c in checks) for k in CHECKS}, "failing_checkpoints": failing,
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
    if [c[0] for c in calls] != ["impl", "mode", "cap", "set_step", "set_step", "set_step", "set_step"] \
            or [c[1] for c in calls[3:]] != [1, 2, 3, 4]:
        raise ValueError(f"atom order {calls}")
    return f"P={calls[0][1]}|M={calls[1][1]}|K={calls[2][1]}|S={''.join(c[2] for c in calls[3:])}"


def parse_candidate(src):
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
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_D13_SOURCES":
            sources = ast.literal_eval(node.value)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_verdict" and begun:
            if ast.unparse(node.value) != "finish()":
                raise ValueError(f"TAIL assigns {ast.unparse(node.value)}")
            calls.append(["finish"])                          # TAIL: _verdict = finish()
    if not begun:
        raise ValueError("no d13.begin()")
    return calls, sources


def verify(run: Path, root: Path):
    rep = Report()
    manifest = json.loads((run / "manifest.json").read_text())
    argv = json.loads((run / "commands.json").read_text())[0]["argv"]
    run_id = manifest["run_id"]
    derived = json.loads((root / "architect-derived.json").read_text())
    frozen = {c["id"]: c for c in derived["cases"]}
    module_sha = {m: sha256((root / f"{m}.py").read_bytes()) for m in ("sut", "oracle", "runtime")}

    # ---- the declared population and the frozen predictions ----
    raw = list(itertools.product(POLICIES, MODES, CAPS, WORDS))
    truth = {f"P={p}|M={m}|K={k}|S={w}": bond_truth(m, k, w) for p, m, k, w in raw}
    own = {c["case_id"]: c for c in (own_case(p, m, k, w) for p, m, k, w in raw if all(truth[f"P={p}|M={m}|K={k}|S={w}"].values()))}
    expected_ids = sorted(own)
    keys = ("policy", "mode", "cap", "schedule", "preemptions", "context_switches", "observed_trace", "reference_trace", "checks",
            "failing_checkpoints")
    diff = [(i, k) for i in expected_ids for k in keys if frozen.get(i, {}).get(k) != own[i][k]]
    diff += [(i, "predicted_outcome") for i in expected_ids if frozen.get(i, {}).get("predicted_outcome") != own[i]["verdict"]]
    frozen_truth = {t["id"]: {r: t[r] for r in RULES} for t in derived["raw_bond_truth"]}
    rep.check("space.frozen_equals_own_model", sorted(frozen) == expected_ids and len(own) == EXPECTED and not diff
              and frozen_truth == truth and len(truth) == RAW and all(c["integrity_ok"] for c in own.values()),
              {"cases": len(own), "diff": diff[:4], "raw_truth_rows": len(truth)})

    feas = {m: [w for w in WORDS if feasible(w, m)] for m in MODES}
    two = [w for w in WORDS if w.count("A") == 2]
    by_stratum = {m: {k: [w for w in feas[m] if switch_counts(w)[1] <= k] for k in CAPS} for m in MODES}
    examples = {w: list(switch_counts(w)) for w in ("AABB", "ABBA", "ABAB")}
    rep.check("schedule.enabledness_and_causal_equivalence",
              feas["independent"] == two and feas["after_A_offer"] == [w for w in two if w[0] == "A"] == derived["feasible_schedules"]["after_A_offer"]
              and feas["independent"] == derived["feasible_schedules"]["independent"]
              and all(truth[f"P=compare_version|M={m}|K=2|S={w}"]["causal_ready"] == (w[0] == "A" or m == "independent") for m in MODES for w in two),
              {"feasible": feas, "excluded_in_after_A_offer": [w for w in two if w not in feas["after_A_offer"]]})
    rep.check("schedule.preemption_expression_and_caps",
              all(bond_expression(w) == switch_counts(w)[1] for w in two) and examples == {"AABB": [1, 0], "ABBA": [2, 1], "ABAB": [3, 2]}
              and [len(by_stratum["independent"][k]) for k in CAPS] == [2, 4, 6] and [len(by_stratum["after_A_offer"][k]) for k in CAPS] == [1, 2, 3],
              {"two_each_words": {w: [bond_expression(w), *switch_counts(w)] for w in two}, "strata": by_stratum, "examples": examples})

    # ---- bonds: own truth table over the raw product versus the live sieve log ----
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
              and line == [RAW, RAW - seq[-1], overlap, EXPECTED] and seq == [RAW, AFTER_TWO, AFTER_CAUSAL, EXPECTED]
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
              and cmp_["constraints_present"] == {"toml": 3, "xlsx": 3},
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
    decoded, bad_rows, core_text = [], [], {}
    for r in frows:
        try:
            codes = {s: cell(r, s) for s in ORDER}
            if any(len(c) != 1 for c in codes.values()):
                raise ValueError(f"row cell arity {codes}")
            cid = case_of([atom(code2val[codes[s][0]]) for s in ORDER[1:-1]])
            parts = []
            for i, s in enumerate(ORDER):
                parts += [code2val[codes[s][0]], endings[s] if (endings[s] or i == len(ORDER) - 1) else "\n"]
            core_text[cid] = "".join(parts)
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
    rendered, src_ok, errs = {}, True, []
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
        src_ok &= sources is not None and {k: sha256(v.encode()) for k, v in sources.items()} == module_sha
    rep.check("identity.reader_equals_core_rows", not errs and sorted(rendered.values()) == expected_ids, errs[:3])
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
    rec_keys = sorted(["schema", "contract", "case_id", "policy", "mode", "cap", "schedule", "preemptions", "context_switches",
                       "observed_trace", "reference_trace", "reconstructed_ledgers", "integrity_ok", "checks", "all_checks",
                       "failing_checkpoints", "verdict", "fw_var", "carrier_slot", "source_sha256", "framework"])
    for cid, r in records.items():
        if cid not in own:
            bad.append((cid, "not_in_declared_population"))
            continue
        o, fw = own[cid], r["framework"]
        checks = [(k, r.get(k), o[k]) for k in (*keys, "case_id", "reconstructed_ledgers", "integrity_ok", "all_checks", "verdict")]
        checks += [("schema", r["schema"], "d13c.observation/v1"), ("contract", r["contract"], "v1"),
                   ("fw_var", r["fw_var"], 0 if o["verdict"] == "PASS" else 2),
                   ("carrier_slot", r["carrier_slot"], "IMPL position 2 (legacy positional, not causal)"),
                   ("frozen_outcome", r["verdict"], frozen[cid]["predicted_outcome"]), ("record_keys", sorted(r), rec_keys),
                   ("supplied_ledger_equals_replies", [e["issued_grants"] for e in r["observed_trace"]], ledger_from_replies(r["observed_trace"])),
                   ("metrics_fw_var", fw["metrics_fw_var"], r["fw_var"]), ("outcome", fw["outcome"], o["verdict"]),
                   ("attempt", (fw["attempt"], fw["repeat_idx"]), (1, 0)), ("source_sha256", r["source_sha256"], module_sha),
                   ("candidate_hash", fw["source_sha256"], sha256(cands[fw["source_ref"]])), ("rendered_identity", rendered.get(fw["source_ref"]), cid)]
        fields += len(checks)
        bad += [(cid, n, got, want) for n, got, want in checks if got != want]
    rep.check("observations.every_field", not bad, {"fields_compared": fields, "bad": bad[:6]})
    recs = list(records.values())
    totals = Counter(r["verdict"] for r in recs)
    by_policy = {p: dict(Counter(r["verdict"] for r in recs if r["policy"] == p)) for p in POLICIES}
    by_cap = {str(k): dict(Counter(r["verdict"] for r in recs if r["cap"] == k)) for k in CAPS}
    rep.check("observations.totals", dict(totals) == derived["outcomes"] and by_policy == derived["by_policy"] and by_cap == derived["by_cap"],
              {"totals": dict(totals), "by_policy": by_policy, "by_cap": by_cap})
    strata = {f"{p}|{m}|K={k}": dict(Counter(r["verdict"] for r in recs if (r["policy"], r["mode"], r["cap"]) == (p, m, k)))
              for p in POLICIES for m in MODES for k in CAPS}
    denominators = {f"{m}|K={k}": sum(1 for r in recs if (r["mode"], r["cap"]) == (m, k)) for m in MODES for k in CAPS}
    schedules = {f"{m}|K={k}": sorted({r["schedule"] for r in recs if (r["mode"], r["cap"]) == (m, k)}) for m in MODES for k in CAPS}
    rep.check("observations.strata_and_schedule_support", denominators == {"independent|K=0": 6, "independent|K=1": 12, "independent|K=2": 18,
                                                                          "after_A_offer|K=0": 3, "after_A_offer|K=1": 6, "after_A_offer|K=2": 9}
              and len({r["schedule"] for r in recs}) == 6 and schedules == {f"{m}|K={k}": by_stratum[m][k] for m in MODES for k in CAPS},
              {"denominators": denominators, "schedules": schedules})

    # ---- mechanisms (from the observed records) ----
    def fails(r, k):
        return not r["all_checks"][k]
    trust_bad = [r for r in recs if r["policy"] == "trust_offer" and r["verdict"] == "DOMAIN_FAIL"]
    over_bad = [r for r in recs if r["policy"] == "overwrite_owner" and r["verdict"] == "DOMAIN_FAIL"]
    rep.check("mechanism.double_booking_vs_silent_withdrawal",
              trust_bad and all(fails(r, "capacity_ok") and fails(r, "exclusive_promises_ok") and r["all_checks"]["commitments_ok"] for r in trust_bad)
              and over_bad and all(r["all_checks"]["capacity_ok"] and fails(r, "exclusive_promises_ok") and fails(r, "commitments_ok") for r in over_bad)
              and all(r["verdict"] == "PASS" for r in recs if r["policy"] == "compare_version")
              and all(len(e["allocations"]) <= 1 for r in over_bad for e in r["observed_trace"]),
              {"trust_offer_fail": len(trust_bad), "overwrite_owner_fail": len(over_bad)})
    stale = [r for r in recs if any(e["response"].get("status") == "STALE" for e in r["observed_trace"])]
    busy = [r for r in recs if any(e["response"].get("status") == "BUSY" for e in r["observed_trace"])]
    granted_each = all(sum(e["response"].get("status") == "GRANTED" for e in r["reference_trace"]) == 1 for r in recs)
    rep.check("mechanism.refusals_and_useful_grants", stale and all(r["policy"] == "compare_version" for r in stale)
              and busy and granted_each and all(r["verdict"] == "PASS" for r in busy) and len(stale) == 9,
              {"records_with_STALE": len(stale), "records_with_BUSY": len(busy), "reference_grants_exactly_one": granted_each})

    need_args = ["--lang", "py", "--sieve", "--execution-policy-profile", "generated-default", "--repeat", "1", "--executor-workers", "1",
                 "--budget-mandatory-rows", "350", "--budget-final-candidates", "350", "--budget-disk-bytes", "50000000",
                 "--budget-wall-time-seconds", "800"]
    rep.check("envelope.command", all(t in argv for t in need_args) and "--override-budget" not in argv and Path(argv[2]).name == "demo.xlsx",
              argv[2:])
    rep.check("envelope.db", re.fullmatch(r"as0927_d13c_[0-9a-z_]+", manifest["databases"]["name"]) is not None
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
                 "totals": dict(totals), "by_policy": by_policy, "by_cap": by_cap, "strata": strata, "denominators": denominators,
                 "schedules": schedules, "records": records}


def witnesses(run, data):
    out = []
    for label, case in WITNESSES.items():
        r = data["records"][case]
        out.append({"label": label, "case_id": case, "candidate": r["framework"]["source_ref"], "schedule": r["schedule"],
                    "observed_trace": r["observed_trace"], "checks": r["checks"], "failing_checkpoints": r["failing_checkpoints"],
                    "verdict": r["verdict"], "replay": f"python replay.py --run evidence/{run.name} --case '{case}'"})
    return {"schema": "d13c.witnesses/v1", "run": run.name, "witnesses": out}


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
    doc = {"schema": "d13c.verification/v1", "run": run.name, "passed": rep.ok, "verifier_sha256": sha256(Path(__file__).read_bytes()),
           "inputs_root": str(a.inputs_root.resolve()), "checks": rep.checks,
           **{k: data[k] for k in ("stage_counts", "totals", "by_policy", "by_cap", "strata", "denominators", "schedules")}}
    (out_dir / "verification.json").write_text(json.dumps(jsonable(doc), indent=2) + "\n", encoding="utf-8")
    if all(c in data["records"] for c in WITNESSES.values()):
        (out_dir / "witnesses.json").write_text(json.dumps(witnesses(run, data), indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in rep.checks if not c["passed"]]
    print(f"verify: {len(rep.checks) - len(failed)}/{len(rep.checks)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    raise SystemExit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
