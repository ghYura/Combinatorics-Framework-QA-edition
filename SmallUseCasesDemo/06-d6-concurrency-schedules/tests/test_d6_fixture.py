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

"""D6 fixture checks: SUT, reference and verify.py's model against the frozen cases; runtime records;
malformed, over-cap and disabled schedules rejected as setup errors (BROKEN, never a verdict);
reference blindness; offline-tool independence; the exploration precheck; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import importlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import explore  # noqa: E402
import oracle  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())


def fresh_runtime():
    import runtime
    return importlib.reload(runtime)


def run_case(policy, schedule, cap=None, campaign=None):
    rt = fresh_runtime()
    rt.begin()
    rt.impl(policy)
    if cap is not None:
        rt.cap(cap)
    for i, t in enumerate(schedule, start=1):
        rt.set_step(i, t)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fw = rt.finish(campaign or ("counter" if cap is not None else "queue"))
    tokens = dict(t.split("=", 1) for t in buf.getvalue().split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def test_models_match_frozen():
    for c in DERIVED["counter_cases"]:
        m = sut.Counter(c["policy"])
        assert [m.step(t) for t in c["schedule"]] == c["predicted_trace"]
        assert oracle.counter_expected(c["schedule"]) == [x["counter"] for x in c["reference_trace"]]
        assert verify.counter_model(c["schedule"], c["policy"]) == (c["predicted_trace"], oracle.counter_expected(c["schedule"]))
    for c in DERIVED["queue_cases"]:
        m = sut.Queue(c["policy"])
        tr = [m.step(t) for t in c["schedule"]]
        ref, disabled = oracle.queue_reference(c["schedule"])
        assert tr == c["predicted_trace"] and disabled is None
        assert verify.queue_model(c["schedule"], c["policy"]) == (tr, ref, None)


def test_preemption_examples_and_all_words():
    assert [(oracle.context_switches(w), oracle.preemptions(w)) for w in ("AABB", "ABBA", "ABAB")] == [(1, 0), (2, 1), (3, 2)]
    for w in explore.words("counter"):
        assert oracle.preemptions(w) == explore.prefix_preemptions(w) == explore.expression(w) == verify.preemptions(w)


def test_counter_records():
    fw, rec = run_case("split_rw", "ABAB", cap=2)
    assert fw == 2 and rec["case_id"] == "counter|split_rw|CAP=2|SEQ=ABAB" and rec["failing_checkpoints"] == [4]
    assert rec["observed_trace"][-1]["counter"] == 1 and rec["reference_counters"] == [0, 0, 1, 2]
    fw, rec = run_case("split_rw", "AABB", cap=0)
    assert fw == 0 and rec["verdict"] == "PASS" and rec["preemptions"] == 0 and rec["context_switches"] == 1


def test_queue_records():
    fw, rec = run_case("stale_empty", "PCCP")
    assert fw == 2 and rec["failing_checkpoints"] == [3, 4] and rec["observed_trace"][2]["pop_result"] == "EMPTY"
    assert rec["observed_trace"][2]["items"] == ["item"]
    fw, rec = run_case("actual_queue", "PCCP")
    assert fw == 0 and rec["observed_trace"][2]["pop_result"] == "item"


@pytest.mark.parametrize("policy,schedule,cap,campaign", [
    ("split_rw", "AAAB", 2, "counter"),          # not two each
    ("split_rw", "ABAB", 1, "counter"),          # above its cap
    ("split_rw", "ABAB", None, "counter"),       # no cap
    ("actual_queue", "CPPC", None, "queue"),     # C1 disabled on the reference state
    ("actual_queue", "PPCC", 1, "queue"),        # cap in a queue case
    ("split_rw", "PPCC", None, "queue"),         # a counter policy in the queue campaign
    ("actual_queue", "PPCX", None, "queue"),     # unknown thread
])
def test_setup_errors_raise(policy, schedule, cap, campaign):
    with pytest.raises((RuntimeError, ValueError)):
        run_case(policy, schedule, cap=cap, campaign=campaign)


def test_steps_out_of_order_raise():
    rt = fresh_runtime()
    rt.begin()
    rt.impl("split_rw")
    rt.cap(2)
    with pytest.raises(ValueError):
        rt.set_step(2, "A")


def test_reference_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(tree) if isinstance(a, ast.arg)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert "policy" not in names and not imports


@pytest.mark.parametrize("tool", ["verify.py", "explore.py"])
def test_offline_tools_import_no_sut_reference_or_runtime(tool):
    tree = ast.parse((HERE / tool).read_text())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imports & {"sut", "oracle", "runtime"}


def test_exploration_precheck():
    c, q = explore.precheck("counter"), explore.precheck("queue")
    assert c["truth_table"]["sequential"] == [96, 36, 24] and c["expression_equals_prefix_count_on_all_16"]
    assert {k: len(v) for k, v in c["schedules_by_cap"].items()} == {0: 2, 1: 4, 2: 6}
    assert q["truth_table"]["sequential"] == [32, 12, 6] and q["feasible"] == ["PCCP", "PCPC", "PPCC"]
    assert q["feasible_equals_first_letter_P"] and q["bonds_retain_exactly_feasible"]
    assert c["framework_sieve_offline_agrees"] and q["framework_sieve_offline_agrees"]


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True, cwd=HERE)
    assert r.returncode == 0, r.stdout + r.stderr
