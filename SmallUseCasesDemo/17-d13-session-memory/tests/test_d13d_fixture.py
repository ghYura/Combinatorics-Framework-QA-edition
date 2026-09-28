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

"""D13d fixture checks: models against the frozen predictions; the three defects; useful same-principal
retention; reset before versus after the write; read-before-write; noncanonical labels; wrong cut
indexing; wrong or omitted tool output; tampered provenance; an erase-all adapter; a redacted reply
that still leaks through a tool argument; the verifier's parser on a locally composed candidate; the
bond truth tables; independence; the builder.

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
import oracle  # noqa: E402
import runtime  # noqa: E402
import sut  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}


def parse(cid):
    f = dict(x.split("=", 1) for x in cid.split("|"))
    return f["P"], f["U"], f["S"], f["X"], int(f["W"])


def run_case(cid):
    p, u, s, x, w = parse(cid)
    runtime._state.clear()
    runtime.begin()
    runtime.impl(p)
    runtime.write_at(w)
    for i, c in enumerate(u, 1):
        runtime.user_at(i, int(c))
    for i, c in enumerate(s, 1):
        runtime.session_at(i, int(c))
    for i, c in enumerate(x, 1):
        runtime.reset_cut(i, int(c))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    tokens = dict(t.split("=", 1) for t in lines[0].split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


def judge(trace, cid):
    _, u, s, x, w = parse(cid)
    return oracle.judge(trace, oracle.reference_trace(u, s, x, w), u, s, x, w)


def replies(rec):
    return [e["reply"] for e in rec["observed_trace"]]


def test_all_800_match_frozen_and_the_verifier_model():
    keys = ("policy", "users", "sessions", "cuts", "write_at", "observed_trace", "reference_trace", "checks", "leaks", "failing_checkpoints")
    occurrences = 0
    for cid, fz in FROZEN.items():
        fw, rec = run_case(cid)
        own = verify.own_case(*parse(cid))
        assert rec["case_id"] == cid and {k: rec[k] for k in keys} == {k: fz[k] for k in keys} == {k: own[k] for k in keys}
        assert rec["verdict"] == fz["predicted_outcome"] and fw == (0 if rec["verdict"] == "PASS" else 2)
        assert rec["owner"] == own["owner"] and rec["leak_occurrences"] == own["leak_occurrences"]
        occurrences += len(rec["leak_occurrences"])
    assert occurrences == 176


@pytest.mark.parametrize("cid,kind,where", [("P=session_only|U=010|S=000|X=00|W=1", "cross_user", [2]),
                                            ("P=user_only|U=000|S=010|X=00|W=1", "cross_session", [2]),
                                            ("P=ignores_reset|U=000|S=000|X=10|W=1", "expired", [2, 3])])
def test_each_defect_leaks_at_request_2(cid, kind, where):
    _, rec = run_case(cid)
    assert rec["leaks"] == [{"request_index": i, "kind": kind} for i in where] and rec["observed_trace"][1]["reply"] == "D13D_CANARY_R1"
    assert rec["reference_trace"][1]["reply"] is None and rec["verdict"] == "DOMAIN_FAIL"
    assert {o["channel"] for o in rec["leak_occurrences"]} == {"reply", "tool_argument"}


def test_useful_same_principal_retention():
    _, rec = run_case("P=scoped|U=000|S=000|X=00|W=1")
    assert replies(rec) == ["STORED", "D13D_CANARY_R1", "D13D_CANARY_R1"] and rec["verdict"] == "PASS"
    assert rec["observed_trace"][1]["tool_calls"] == [{"name": "draft", "argument": "D13D_CANARY_R1"}]


def test_reset_before_the_write_versus_after_it():
    _, before = run_case("P=scoped|U=000|S=000|X=10|W=2")
    _, after = run_case("P=scoped|U=000|S=000|X=01|W=1")
    assert replies(before) == [None, "STORED", "D13D_CANARY_R2"] and before["verdict"] == "PASS"
    assert replies(after) == ["STORED", "D13D_CANARY_R1", None] and after["verdict"] == "PASS"
    assert after["observed_trace"][2]["reset_before"] and after["observed_trace"][2]["memory"] == []   # correct removal, no defect


def test_read_before_write_is_empty():
    _, rec = run_case("P=user_only|U=000|S=000|X=00|W=2")
    assert rec["observed_trace"][0]["operation"] == "read" and rec["observed_trace"][0]["reply"] is None
    assert rec["observed_trace"][0]["tool_calls"] == [] and rec["verdict"] == "PASS"


@pytest.mark.parametrize("calls", [
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(1), r.user_at(1, 0), r.user_at(2, 2)),        # label jumps
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(1), r.user_at(1, 1)),                          # must start at 0
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(1), r.user_at(1, 0), r.user_at(2, 0), r.user_at(3, 2)),
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(1), *[r.user_at(i, 0) for i in (1, 2, 3)], r.session_at(1, 0),
               r.session_at(2, 0), r.session_at(3, 2)),                                              # noncanonical sessions
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(1), *[r.user_at(i, 0) for i in (1, 2, 3)],
               *[r.session_at(i, 0) for i in (1, 2, 3)], r.reset_cut(2, 1)),                          # wrong cut index
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(3)),
    lambda r: (r.begin(), r.impl("shared")),
    lambda r: (r.begin(), r.impl("scoped"), r.write_at(1), r.finish()),
])
def test_setup_errors_raise(calls):
    runtime._state.clear()
    with pytest.raises((RuntimeError, ValueError)):
        calls(runtime)


def test_wrong_cut_indexing_is_detected():
    cid = "P=scoped|U=000|S=000|X=10|W=1"
    shifted = verify.adapter_trace("scoped", "000", "000", "01", 1)          # the cut applied before request 3
    j = judge(shifted, cid)
    assert j["failing_checkpoints"] == [2] and j["leaks"] == [{"request_index": 2, "kind": "expired"}]   # request 3 is empty either way


def test_wrong_or_omitted_tool_output_is_detected():
    cid = "P=scoped|U=000|S=000|X=00|W=1"
    trace = verify.adapter_trace("scoped", "000", "000", "00", 1)
    omitted, renamed = copy.deepcopy(trace), copy.deepcopy(trace)
    omitted[1]["tool_calls"] = []
    renamed[2]["tool_calls"] = [{"name": "send", "argument": "D13D_CANARY_R1"}]
    assert judge(omitted, cid)["checks"][1] == {"request_index": 2, "response_ok": True, "tools_ok": False, "isolation_ok": True}
    assert judge(renamed, cid)["failing_checkpoints"] == [3]


def test_tampered_provenance_never_authorizes():
    cid = "P=session_only|U=010|S=000|X=00|W=1"
    trace = verify.adapter_trace("session_only", "010", "000", "00", 1)
    forged = copy.deepcopy(trace)
    for e in forged:
        for m in e["memory"]:
            m["write_user"] = e["user"]                                      # provenance claims the reader wrote it
    assert judge(forged, cid) == judge(trace, cid) and judge(forged, cid)["leaks"] == [{"request_index": 2, "kind": "cross_user"}]
    assert forged != verify.own_case("session_only", "010", "000", "00", 1)["observed_trace"]   # the verifier sees the tamper


def test_erase_all_adapter_fails_useful_retention(monkeypatch):
    monkeypatch.setattr(sut.MemoryAdapter, "read", lambda self, user, session: None)
    _, rec = run_case("P=scoped|U=000|S=000|X=00|W=1")
    assert replies(rec) == ["STORED", None, None] and rec["leaks"] == []
    assert all(c["isolation_ok"] for c in rec["checks"]) and rec["failing_checkpoints"] == [2, 3] and rec["verdict"] == "DOMAIN_FAIL"


def test_redacted_reply_still_leaks_through_the_tool():
    cid = "P=session_only|U=010|S=000|X=00|W=1"
    trace = verify.adapter_trace("session_only", "010", "000", "00", 1)
    redacted = copy.deepcopy(trace)
    redacted[1]["reply"] = None                                              # the user sees nothing ...
    j = judge(redacted, cid)                                                 # ... but the draft tool got the canary
    assert j["checks"][1]["isolation_ok"] is False and j["checks"][1]["response_ok"] is True
    assert j["leak_occurrences"] == [{"request_index": 2, "channel": "tool_argument"}] and j["leaks"][0]["kind"] == "cross_user"


def test_verifier_parser_on_a_locally_composed_candidate():
    """Preflight: compose one candidate as the Reader renders it and parse it with the verifier."""
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, _ = build_spec.layout(head)
    pick = {"IMPL": 1, "WRITE_AT": 0, "U2": 1, "U3": 0, "S2": 0, "S3": 0, "R12": 0, "R23": 0}
    values = [s[1][pick.get(s[0], 0)] for s in slots]
    text = verify.join_row(values, [s[2] for s in slots])
    calls, inlined = verify.parse_candidate(text)
    cid = verify.case_of(calls[:-1])
    assert calls[-1] == ["finish"] and cid == "P=user_only|U=010|S=000|X=00|W=1"
    assert {k: verify.sha256(v.encode()) for k, v in inlined.items()} == digests
    r = subprocess.run([sys.executable, "-c", text], capture_output=True, text=True, timeout=60)
    tokens = dict(t.split("=", 1) for t in r.stdout.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert r.returncode == 0 and rec["case_id"] == cid and rec["verdict"] == FROZEN[cid]["predicted_outcome"]
    assert verify.join_row(["a;", "b;", "T\n"], ["", "\n", ""]) == "a;\nb;\nT\n"


def test_bond_truth_tables_and_partitions():
    own, fw = explore.truth_table(explore.own_bonds), explore.truth_table(explore.framework_bonds())
    assert own == fw and own["sequential"] == [1152, 960, 800] and own["per_rule"] == {"user_rgs": 192, "session_rgs": 192}
    assert own["rows"] == {t["id"]: {r: t[r] for r in explore.RULES} for t in DERIVED["raw_bond_truth"]}
    assert len({tuple(c.split("|")[1:3]) for c in own["kept"]}) == 25
    assert [t for t in explore.TRIPLES if explore.canonical(t)] == ["000", "001", "010", "011", "012"]


def test_oracle_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments)
                                                                        for a in n.args}
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any("policy" in n for n in names) and not literals & set(sut.POLICIES)
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("judge", "canaries")):
        used = {n.args[0].value for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get" and n.args and isinstance(n.args[0], ast.Constant)}
        used |= {n.slice.value for n in ast.walk(fn) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)}
        assert not used & {"memory", "storage_key", "write_user", "write_session", "write_epoch", "write_index", "operation",
                           "epoch", "user", "session"}, (fn.name, used)       # authorization never reads SUT keys or provenance


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"sut", "oracle", "runtime", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
