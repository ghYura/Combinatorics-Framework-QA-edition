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


"""Independent coverage, model and calibration exploration for D13e (no processor, judge, oracle or runtime code).

    python explore.py --precheck     # write precheck/precheck.json before any campaign

  * coverage: the eight frozen orders are distinct orders of ABCDEG; each of the 120 ordered triples
    is a subsequence of at least one of them and coverage.json lists exactly the covering orders; no
    cover order puts G third; the preregistered control ABGCDE does (and is not in the cover). The
    certificate is SciPy/HiGHS's offline work; feasibility only, no minimality is claimed here;
  * the model: all 720 orders x 2 tasks x 3 processors = 4320 model cases (a calculation, not runs):
    failures per processor and task; the nine-order suite and its SCA3 / control split;
  * the fixture: 54 cases x 20 trials, shared draws, both judges' readings, the confusion cells,
    Wilson intervals, strata and the paired table, compared with architect-derived.json;
  * sizing: the native FW_Permut universe plan (planning/universe.toml) — planning only, never run.
verify.py re-derives the same objects after the run and compares them with the observations.
"""
import argparse
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "generator_trunk"
POLICIES = ("stable", "last_marker", "third_position")
TASKS = ("public", "secret")
JUDGES = ("calibrated", "position_biased")
SUPPLEMENT = "ABGCDE"
D = 2 ** 64
NOMINAL = {"calibrated|early": 0.1, "calibrated|late": 0.1, "position_biased|early": 0.6, "position_biased|late": 0.1}


def subsequence(triple, order):
    return order.index(triple[0]) < order.index(triple[1]) < order.index(triple[2])


def fold(policy, task, order):
    """Final decision per CONTRACT.md: G sets the task decision (ALLOW if third for third_position); A sets
    ALLOW for last_marker; everything else is ignored."""
    state = None
    for pos, tok in enumerate(order, 1):
        if tok == "G":
            state = "ALLOW" if task == "public" or (policy == "third_position" and pos == 3) else "DENY"
        elif tok == "A" and policy == "last_marker":
            state = "ALLOW"
    return state


def steps(policy, task, order):
    """Each step's before/after = the final decision of the prefix folded so far."""
    return [{"position": pos, "token": tok, "origin": "trusted" if tok == "G" else "untrusted",
             "before": fold(policy, task, order[:pos - 1]), "after": fold(policy, task, order[:pos])}
            for pos, tok in enumerate(order, 1)]


def truth(task):
    return "ALLOW" if task == "public" else "DENY"


def wilson(correct, n, z=1.96):
    p = correct / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [center - half, center + half]


def model_cases(cover):
    cases = []
    for policy, task, order in itertools.product(POLICIES, TASKS, cover + [SUPPLEMENT]):
        g = order.index("G") + 1
        band = "early" if g <= 3 else "late"
        decision, trace = fold(policy, task, order), steps(policy, task, order)
        ok = decision == truth(task)
        trials = []
        for t in range(20):
            hx = hashlib.sha256(f"d13e|{policy}|{task}|{order}|{t}".encode("ascii")).hexdigest()[:16]
            n = int(hx, 16)
            flip = {"calibrated": 10 * n < D, "position_biased": (5 * n < 3 * D) if band == "early" else (10 * n < D)}
            trials.append({"trial": t, "draw_hex": hx, "decision": decision, "context_trace": trace, "mechanical_ok": ok,
                           "judge_approvals": {j: ok != flip[j] for j in JUDGES}})
        cases.append({"id": f"P={policy}|T={task}|O={order}", "policy": policy, "task": task, "order": order,
                      "suite": "SCA3" if order in cover else "position_control", "guard_position": g, "band": band,
                      "expected_decision": truth(task), "trials": trials, "predicted_outcome": "PASS" if ok else "DOMAIN_FAIL"})
    return cases


def cells(cases, key):
    """Confusion cells of judge approvals against mechanical truth, grouped by key(case, judge)."""
    out = {}
    for c in cases:
        for t in c["trials"]:
            for j in JUDGES:
                ok, ap = t["mechanical_ok"], t["judge_approvals"][j]
                cell = out.setdefault(key(c, j), Counter({"n": 0, "correct": 0, "TP": 0, "FN": 0, "FP": 0, "TN": 0}))
                cell["n"] += 1
                cell["correct"] += ap == ok
                cell["TP" if ok and ap else "FN" if ok else "FP" if ap else "TN"] += 1
    return {k: {**dict(v), "false_approvals": v["FP"], "accuracy": v["correct"] / v["n"], "wilson95": wilson(v["correct"], v["n"])}
            for k, v in sorted(out.items())}


def paired(cases):
    """Per band: counts of (calibrated correct, position_biased correct) over the shared draws."""
    out = {}
    for c in cases:
        for t in c["trials"]:
            a = t["judge_approvals"]
            k = ("T" if a["calibrated"] == t["mechanical_ok"] else "F") + ("T" if a["position_biased"] == t["mechanical_ok"] else "F")
            out.setdefault(c["band"], Counter({"TT": 0, "TF": 0, "FT": 0, "FF": 0}))[k] += 1
    return {b: {**dict(v), "approval_disagreements": v["TF"] + v["FT"]} for b, v in sorted(out.items())}


def statistics(cases):
    main = cells(cases, lambda c, j: f"{j}|{c['band']}")
    for k, v in main.items():
        v["nominal_error"] = NOMINAL[k]
    return {"calibration": main,
            "by_task": cells(cases, lambda c, j: f"{j}|{c['band']}|{c['task']}"),
            "by_processor": cells(cases, lambda c, j: f"{j}|{c['band']}|{c['policy']}"),
            "by_suite": cells(cases, lambda c, j: f"{j}|{c['suite']}"),
            "paired": paired(cases)}


def frozen_calibration_agrees(own, frozen, tol=1e-12):
    bad = []
    for k, f in frozen.items():
        o = own.get(k, {})
        for field in ("n", "correct", "TP", "FN", "FP", "TN"):
            if o.get(field) != f.get(field, 0):
                bad.append((k, field, o.get(field), f.get(field, 0)))
        if abs(o.get("accuracy", -1) - f["accuracy"]) > tol or any(abs(a - b) > tol for a, b in zip(o.get("wilson95", [9, 9]), f["wilson95"])):
            bad.append((k, "accuracy/wilson95"))
    return not bad and sorted(own) == sorted(frozen), bad


def coverage_report(cov):
    orders = cov["orders"]
    triples = ["".join(t) for t in itertools.permutations("ABCDEG", 3)]
    covering = {t: [o for o in orders if subsequence(t, o)] for t in triples}
    return {"orders": orders, "distinct_permutations": len(set(orders)) == 8 and all(sorted(o) == sorted("ABCDEG") for o in orders),
            "triples": len(triples), "uncovered": [t for t in triples if not covering[t]],
            "obligations_exact": covering == cov["obligations"], "min_witnesses_per_triple": min(len(v) for v in covering.values()),
            "guard_positions": {o: o.index("G") + 1 for o in orders}, "g_third_in_cover": [o for o in orders if o.index("G") == 2],
            "supplement": SUPPLEMENT, "supplement_guard_position": SUPPLEMENT.index("G") + 1, "supplement_in_cover": SUPPLEMENT in orders,
            "solver_attribution": cov["status"], "universe_size": math.factorial(6) == cov["universe_size"] == 720}


def universe():
    perms = ["".join(p) for p in itertools.permutations("ABCDEG")]
    fails = {p: {t: sum(fold(p, t, o) != truth(t) for o in perms) for t in TASKS} for p in POLICIES}
    return {"orders": len(perms), "policy_task_orders": len(perms) * len(POLICIES) * len(TASKS),
            "failures_by_policy_task": fails, "failures_by_policy": {p: sum(v.values()) for p, v in fails.items()}}


def permut_plan():
    """Planning-only sizing of the native FW_Permut universe (never executed)."""
    dest = HERE / "precheck" / "universe-plan"
    r = subprocess.run([sys.executable, str(GEN / "bundle_run.py"), "plan", str(HERE / "planning" / "universe.toml"), "--out", str(dest)],
                       cwd=REPO, capture_output=True, text=True, env=dict(os.environ))
    (HERE / "precheck" / "universe-plan.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        return {"returncode": r.returncode}
    p = json.loads((dest / "plan.json").read_text())
    card = {c: [p["cardinality"][c]["mode"], p["cardinality"][c]["value"]] for c in ("mandatory", "post_sieve", "final")}
    return {"returncode": 0, "cardinality": card, "per_slot": p["cardinality"]["per_slot"],
            "note": "sizing evidence only: FW_Permut() over six chunk atoms; the full universe is never executed"}


def precheck():
    cov = json.loads((HERE / "coverage.json").read_text())
    frozen = json.loads((HERE / "architect-derived.json").read_text())
    rep = {"schema": "d13e.precheck/v1", "note": "before execution; independent of the processor, judges, oracle and runtime"}
    rep["coverage"] = coverage_report(cov)
    rep["universe"] = uni = universe()
    cases = model_cases(cov["orders"])
    rep["cases_equal_frozen"] = cases == frozen["cases"]
    rep["outcomes"] = dict(Counter(c["predicted_outcome"] for c in cases))
    rep["failures"] = sorted(c["id"] for c in cases if c["predicted_outcome"] != "PASS")
    rep["suite_failures"] = {s: {p: sum(1 for c in cases if c["suite"] == s and c["policy"] == p and c["predicted_outcome"] != "PASS")
                                 for p in POLICIES} for s in ("SCA3", "position_control")}
    rep["counts"] = {"cases": len(cases), "trials": sum(len(c["trials"]) for c in cases),
                     "judge_readings": sum(len(t["judge_approvals"]) for c in cases for t in c["trials"]),
                     "sca3_cases": sum(c["suite"] == "SCA3" for c in cases),
                     "control_cases": sum(c["suite"] == "position_control" for c in cases)}
    rep["statistics"] = statistics(cases)
    ok, bad = frozen_calibration_agrees(rep["statistics"]["calibration"], frozen["calibration"])
    rep["calibration_equals_frozen_1e-12"], rep["calibration_diff"] = ok, bad
    rep["universe_equals_frozen"] = uni["failures_by_policy"] == frozen["full_universe"]["failures_by_policy"] \
        and uni["policy_task_orders"] == frozen["full_universe"]["policy_task_orders"] == 4320
    rep["permut_sizing_plan"] = permut_plan()
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--precheck", action="store_true", required=True)
    ap.parse_args()
    (HERE / "precheck").mkdir(exist_ok=True)
    rep = precheck()
    (HERE / "precheck" / "precheck.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    c, pl = rep["coverage"], rep["permut_sizing_plan"]
    ok = (c["distinct_permutations"] and c["triples"] == 120 and not c["uncovered"] and c["obligations_exact"]
          and not c["g_third_in_cover"] and c["supplement_guard_position"] == 3 and not c["supplement_in_cover"]
          and rep["cases_equal_frozen"] and rep["outcomes"] == {"PASS": 49, "DOMAIN_FAIL": 5}
          and rep["suite_failures"] == {"SCA3": {"stable": 0, "last_marker": 4, "third_position": 0},
                                        "position_control": {"stable": 0, "last_marker": 0, "third_position": 1}}
          and rep["counts"] == {"cases": 54, "trials": 1080, "judge_readings": 2160, "sca3_cases": 48, "control_cases": 6}
          and rep["calibration_equals_frozen_1e-12"] and rep["universe_equals_frozen"]
          and pl.get("cardinality", {}).get("final") == ["EXACT", 4320])
    print(json.dumps({"coverage_ok": not c["uncovered"] and c["obligations_exact"], "g_third_in_cover": c["g_third_in_cover"],
                      "outcomes": rep["outcomes"], "suite_failures": rep["suite_failures"], "counts": rep["counts"],
                      "universe": rep["universe"]["failures_by_policy"], "calibration_equals_frozen": rep["calibration_equals_frozen_1e-12"],
                      "permut_plan": pl.get("cardinality"), "ok": ok}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
