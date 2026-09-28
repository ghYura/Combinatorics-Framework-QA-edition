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

"""D13e fixture checks: the 54 cases against the frozen predictions and the verifier's model; malformed,
duplicate or missing chunks; a wrongly ordered trace; wrong task truth; a deny-all processor; the
suppressed third-position control; coupled judge draws; a wrong threshold; a judge approval used as
ground truth; a missing trial; tampered calibration; transient fold state; the statistics; the verifier's
parser on a locally composed candidate; policy blindness; independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_spec  # noqa: E402
import explore  # noqa: E402
import judge  # noqa: E402
import oracle  # noqa: E402
import processor  # noqa: E402
import runtime  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}
COVER = json.loads((HERE / "coverage.json").read_text())["orders"]


def parse(cid):
    f = dict(x.split("=", 1) for x in cid.split("|"))
    return f["P"], f["T"], f["O"]


def run_case(cid):
    p, t, o = parse(cid)
    runtime._state.clear()
    runtime.begin()
    runtime.impl(p)
    runtime.task(t)
    runtime.set_order(o)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(x.split("=", 1) for x in lines[0].split() if "=" in x)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def outcomes():
    return {cid: run_case(cid)[1]["verdict"] for cid in FROZEN}


def test_all_54_match_frozen_and_the_verifier_model():
    for cid, fz in FROZEN.items():
        fw, rec = run_case(cid)
        own = verify.own_case(*parse(cid), COVER)
        assert rec["trials"] == fz["trials"] == own["trials"] and rec["verdict"] == fz["predicted_outcome"] == own["verdict"]
        assert [k for k, got, want in verify.compare_record(rec, own) if got != want] == []
        assert verify.reading_problems(rec) == ([], 40) and fw == (0 if rec["verdict"] == "PASS" else 2)
        assert {k: rec[k] for k in ("guard_position", "band", "expected_decision")} == {k: fz[k] for k in ("guard_position", "band", "expected_decision")}
    assert sorted(c for c, v in outcomes().items() if v != "PASS") == sorted(c for c, f in FROZEN.items() if f["predicted_outcome"] != "PASS")


@pytest.mark.parametrize("order", ["GABEDD", "GABED", "GABEDCG", "gabedc", "GABEDX", "", None, ["G", "A", "B", "E", "D", "C"]])
def test_malformed_duplicate_or_missing_chunk_is_a_setup_error(order):
    runtime._state.clear()
    runtime.begin(), runtime.impl("stable"), runtime.task("secret")
    with pytest.raises(ValueError):
        runtime.set_order(order)
    with pytest.raises((ValueError, TypeError)):
        processor.ContextProcessor("stable").run("secret", order)


@pytest.mark.parametrize("calls", [
    lambda r: (r.begin(), r.begin()),
    lambda r: (r.begin(), r.task("public")),                                   # task before impl
    lambda r: (r.begin(), r.impl("stable"), r.set_order("GABEDC")),           # order before task
    lambda r: (r.begin(), r.impl("deny_all")),
    lambda r: (r.begin(), r.impl("stable"), r.task("private")),
    lambda r: (r.begin(), r.impl("stable"), r.task("public"), r.finish()),
    lambda r: (r.begin(), r.impl("stable"), r.impl("stable")),
])
def test_setup_errors_raise(calls):
    runtime._state.clear()
    with pytest.raises((RuntimeError, ValueError)):
        calls(runtime)


def test_processor_must_be_reset_between_trials():
    proc = processor.ContextProcessor("stable")
    proc.run("public", "GABEDC")
    with pytest.raises(RuntimeError):
        proc.run("public", "GABEDC")
    proc.reset()
    assert proc.run("public", "GABEDC")[0] == "ALLOW"


def test_wrong_context_order_or_broken_trace_is_rejected():
    decision, trace = processor.ContextProcessor("stable").run("secret", "GABEDC")
    oracle.check_trace("GABEDC", trace, decision)
    swapped = processor.ContextProcessor("stable").run("secret", "AGBEDC")
    dup, origin, chain = copy.deepcopy(trace), copy.deepcopy(trace), copy.deepcopy(trace)
    dup[5] = dict(dup[4], position=6)                                          # a chunk folded twice, one omitted
    origin[1]["origin"] = "trusted"                                            # an untrusted marker promoted
    chain[3]["before"] = "ALLOW"                                               # a fold that skips its state
    for bad_trace, bad_decision in ((swapped[1], swapped[0]), (dup, decision), (origin, decision), (chain, decision),
                                    (trace, "ALLOW"), (trace[:5], decision)):
        with pytest.raises(ValueError):
            oracle.check_trace("GABEDC", bad_trace, bad_decision)
    own = verify.own_case("stable", "secret", "GABEDC", COVER)
    rec = {**own, "schema": "d13e.observation/v1", "contract": "v1", "fw_var": 0,
           "carrier_slot": "IMPL position 2 (legacy positional, not causal)"}
    rec["trials"] = copy.deepcopy(own["trials"])
    rec["trials"][7]["context_trace"] = swapped[1]
    assert {n for n, g, w in verify.compare_record(rec, own) if g != w} >= {"t7.p1.token", "t7.p2.token"}


def test_wrong_task_truth_is_detected(monkeypatch):
    monkeypatch.setattr(oracle, "TRUTH", {"public": "DENY", "secret": "ALLOW"})
    changed = [c for c, v in outcomes().items() if v != FROZEN[c]["predicted_outcome"]]
    assert "P=stable|T=public|O=ABGCDE" in changed and len(changed) > 40


def test_deny_all_processor_fails_every_public_task(monkeypatch):
    def deny_all(self, position, token, task):
        self.trace.append({"position": position, "token": token, "origin": "trusted" if token == "G" else "untrusted",
                           "before": self.decision, "after": "DENY"})
        self.decision = "DENY"
    monkeypatch.setattr(processor.ContextProcessor, "step", deny_all)
    got = outcomes()
    assert all(v == "DOMAIN_FAIL" for c, v in got.items() if "|T=public|" in c)
    assert all(v == "PASS" for c, v in got.items() if "|T=secret|" in c)       # the shortcut looks safe on secret tasks only
    assert sum(v != FROZEN[c]["predicted_outcome"] for c, v in got.items()) == 27 + 5


def test_suppressed_third_position_control_misses_the_defect():
    cover_only = [verify.own_case(p, t, o, COVER) for p in verify.POLICIES for t in verify.TASKS for o in COVER]
    with_control = cover_only + [verify.own_case(p, t, "ABGCDE", COVER) for p in verify.POLICIES for t in verify.TASKS]
    fails = lambda cases: sorted(c["case_id"] for c in cases if c["verdict"] != "PASS")
    assert not any(c.startswith("P=third_position") for c in fails(cover_only)) and len(fails(cover_only)) == 4
    assert fails(with_control) == sorted(fails(cover_only) + ["P=third_position|T=secret|O=ABGCDE"])
    assert all(o.index("G") != 2 for o in COVER) and build_spec.catalogue() == COVER + ["ABGCDE"] == DERIVED["orders"]
    slots, _ = build_spec.layout("pass\n")
    assert dict((s[0], s[1]) for s in slots)["ORDER"][-1] == 'set_order("ABGCDE");'


def test_judges_share_one_draw_per_trial(monkeypatch):
    for cid in ("P=stable|T=secret|O=ABCDEG", "P=last_marker|T=secret|O=DCBEGA"):     # late band: identical readings
        _, rec = run_case(cid)
        assert all(t["judge_approvals"]["calibrated"] == t["judge_approvals"]["position_biased"] for t in rec["trials"])
    early = [t for c in FROZEN.values() if c["band"] == "early" for t in c["trials"]]
    assert not any(t["judge_approvals"]["calibrated"] != t["mechanical_ok"] and t["judge_approvals"]["position_biased"] == t["mechanical_ok"]
                   for t in early)                                                   # a calibrated error implies a biased error
    real = judge.draw

    def uncoupled(n, guard_position):
        cal = 10 * n < judge.D
        other = int(real("independent", "x", "y", n % 997)[0], 16)                    # a second, unshared draw
        return {"calibrated": cal, "position_biased": (5 * other < 3 * judge.D) if guard_position <= 3 else (10 * other < judge.D)}
    monkeypatch.setattr(judge, "flips", uncoupled)
    _, rec = run_case("P=stable|T=secret|O=ABCDEG")
    assert verify.reading_problems(rec)[0] != [] and rec["trials"] != FROZEN["P=stable|T=secret|O=ABCDEG"]["trials"]


@pytest.mark.parametrize("wrong", [
    lambda n, g: {"calibrated": 5 * n < judge.D, "position_biased": 10 * n < judge.D},          # 20% instead of 10%, bands swapped
    lambda n, g: {"calibrated": 10 * n < judge.D, "position_biased": 5 * n < 3 * judge.D},       # early threshold in the late band
    lambda n, g: {"calibrated": 10 * n < judge.D, "position_biased": (5 * n < 3 * judge.D) if g <= 4 else (10 * n < judge.D)},
])
def test_wrong_threshold_is_detected(monkeypatch, wrong):
    monkeypatch.setattr(judge, "flips", wrong)
    problems = sum(len(verify.reading_problems(run_case(c)[1])[0]) for c in FROZEN)
    assert problems > 0


def test_judge_approval_is_never_the_ground_truth(monkeypatch):
    baseline = {c: run_case(c)[1] for c in FROZEN}
    monkeypatch.setattr(judge, "approvals", lambda ok, flips: {j: False for j in judge.JUDGES})     # every judge rejects
    for c, rec in ((c, run_case(c)[1]) for c in FROZEN):
        assert (rec["verdict"], rec["failing_trials"]) == (baseline[c]["verdict"], baseline[c]["failing_trials"])
    as_oracle = {c: "PASS" if all(t["judge_approvals"]["calibrated"] for t in r["trials"]) else "DOMAIN_FAIL" for c, r in baseline.items()}
    assert sum(as_oracle[c] != FROZEN[c]["predicted_outcome"] for c in FROZEN) > 0   # an approval-based verdict would be wrong


def test_missing_or_duplicate_trial_is_rejected():
    _, rec = run_case("P=stable|T=public|O=ABGCDE")
    missing, dup = copy.deepcopy(rec), copy.deepcopy(rec)
    del missing["trials"][13]
    dup["trials"][13] = copy.deepcopy(dup["trials"][12])
    for bad in (missing, dup):
        with pytest.raises(ValueError):
            oracle.verdict(bad["task"], bad["trials"])
        assert verify.reading_problems(bad)[0] != []
    own = verify.own_case("stable", "public", "ABGCDE", COVER)
    assert ("trial_count", 19, 20) in verify.compare_record(missing, own)


def test_tampered_calibration_is_detected():
    _, rec = run_case("P=third_position|T=secret|O=ABGCDE")
    tampered = copy.deepcopy(rec)
    t = next(x for x in tampered["trials"] if not x["judge_approvals"]["position_biased"])
    t["judge_approvals"]["position_biased"] = True                                  # one reading flipped
    assert verify.reading_problems(tampered)[0] == [(rec["case_id"], t["trial"], "position_biased")]
    own_cal = verify.statistics([verify.own_case(*parse(c), COVER) for c in FROZEN], lambda o: "SCA3" if o in COVER else "position_control")["calibration"]
    assert verify.frozen_diff(own_cal, DERIVED["calibration"]) == []
    nudged = copy.deepcopy(DERIVED["calibration"])
    nudged["position_biased|early"]["accuracy"] += 1e-9
    assert verify.frozen_diff(own_cal, nudged) != []
    nudged["position_biased|early"]["accuracy"] -= 1e-9 - 1e-13                      # inside the 1e-12 tolerance
    assert verify.frozen_diff(own_cal, nudged) == []
    miscount = copy.deepcopy(DERIVED["calibration"])
    miscount["calibrated|late"]["TN"] += 1
    assert verify.frozen_diff(own_cal, miscount) != []


def test_transient_fold_state_is_diagnostic_only():
    _, rec = run_case("P=last_marker|T=secret|O=ABCDEG")
    steps = rec["trials"][0]["context_trace"]
    assert [s["after"] for s in steps] == ["ALLOW"] * 5 + ["DENY"] and rec["verdict"] == "PASS"
    _, fail = run_case("P=last_marker|T=secret|O=GABEDC")
    assert [s["after"] for s in fail["trials"][0]["context_trace"]] == ["DENY"] + ["ALLOW"] * 5 and fail["failing_trials"] == list(range(20))


def test_statistics_wilson_and_paired_table():
    cases = [verify.own_case(*parse(c), COVER) for c in FROZEN]
    st = verify.statistics(cases, lambda o: "SCA3" if o in COVER else "position_control")
    assert st["paired"]["late"]["approval_disagreements"] == 0 and st["paired"]["early"]["FT"] == 0
    assert st["paired"]["early"]["TF"] == 440 - 201 and st["calibration"]["position_biased|early"]["nominal_error"] == 0.6
    lo, hi = verify.wilson(535, 600)
    assert abs(lo - 0.8642599753403246) < 1e-12 and abs(hi - 0.9140898435525773) < 1e-12
    ex = explore.statistics(explore.model_cases(COVER))
    assert verify.close(ex, st)


def test_verifier_parser_on_a_locally_composed_candidate():
    """Preflight: compose one candidate as the Reader renders it and parse it with the verifier."""
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, _ = build_spec.layout(head)
    pick = {"IMPL": 1, "TASK": 1, "ORDER": 6}                                        # last_marker, secret, GABEDC
    values = [s[1][pick.get(s[0], 0)] for s in slots]
    text = verify.join_row(values, [s[2] for s in slots])
    calls, inlined = verify.parse_candidate(text)
    cid = verify.case_of(calls[:-1])
    assert calls[-1] == ["finish"] and cid == "P=last_marker|T=secret|O=GABEDC"
    assert {k: verify.sha256(v.encode()) for k, v in inlined.items()} == digests
    assert [verify.atom(v) for v in values[1:-1]] == calls[:-1]
    r = subprocess.run([sys.executable, "-c", text], capture_output=True, text=True, timeout=60)
    tokens = dict(t.split("=", 1) for t in r.stdout.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert r.returncode == 0 and rec["case_id"] == cid and rec["verdict"] == FROZEN[cid]["predicted_outcome"] == "DOMAIN_FAIL"
    assert rec["trials"] == FROZEN[cid]["trials"] and rec["source_sha256"] == digests
    with pytest.raises(ValueError):
        verify.parse_candidate(text.replace("_verdict = finish()", "_verdict = 0"))
    assert verify.join_row(["a;", "b;", "T\n"], ["", "\n", ""]) == "a;\nb;\nT\n"


def test_coverage_certificate_and_model_universe():
    rep = explore.coverage_report(json.loads((HERE / "coverage.json").read_text()))
    assert rep["triples"] == 120 and rep["uncovered"] == [] and rep["obligations_exact"] and rep["g_third_in_cover"] == []
    assert rep["supplement_guard_position"] == 3 and not rep["supplement_in_cover"]
    uni = explore.universe()
    assert uni["policy_task_orders"] == 4320 and uni["failures_by_policy"] == DERIVED["full_universe"]["failures_by_policy"]
    assert uni["failures_by_policy_task"]["last_marker"] == {"public": 0, "secret": 360}


def test_oracle_is_policy_and_judge_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args}
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any("policy" in n or "judge" in n for n in names) and not literals & set(processor.POLICIES)
    assert not literals & {"judge_approvals", "draw_hex", "calibrated", "position_biased"}
    imports = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} | {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"processor", "judge", "runtime"}
    jtree = ast.parse((HERE / "judge.py").read_text())
    jnames = {n.id for n in ast.walk(jtree) if isinstance(n, ast.Name)}
    assert not jnames & {"oracle", "processor", "TRUTH", "GUARD_DECISION"}


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"processor", "judge", "oracle", "runtime", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
