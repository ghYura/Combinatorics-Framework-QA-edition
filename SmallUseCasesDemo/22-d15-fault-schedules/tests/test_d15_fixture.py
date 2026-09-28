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

"""D15 fixture checks with real local worker processes: ACK before/after fsync; killed-worker pending loss
versus durable reload; double replay with unique WAL keys; partial quorum and stable versus fresh retry; an
all-node crash; partition without restart; cut 0 and cut 3; convergence masking a uniform wrong state; merge
deduplication; malformed IPC; ownership and exit guards; tampered traces; the renderer/parser on a locally
composed candidate; a stratified sample of full cases against the frozen predictions; policy blindness;
verifier independence; the builder.

Run: python -m pytest -q -p no:cacheprovider tests
"""
import ast
import base64
import contextlib
import copy
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import build_spec  # noqa: E402
import harness  # noqa: E402
import oracle  # noqa: E402
import runtime  # noqa: E402
import verify  # noqa: E402

DERIVED = json.loads((HERE / "architect-derived.json").read_text())
FROZEN = {c["id"]: c for c in DERIVED["cases"]}
SEMANTIC = ("attempts", "trace", "acknowledged", "checks")


def parse(cid):
    f = dict(p.split("=", 1) for p in cid.split("|"))
    return f["P"], [int(n) for n in f["F"]], int(f["C"]), f["K"], f["R"]


def run_case(cid, monkeypatch=None):
    p, failed, c, k, r = parse(cid)
    runtime._state.clear()
    runtime.begin()
    runtime.impl(p)
    for n in failed:
        runtime.fail(n)
    runtime.cut(c), runtime.fault(k), runtime.retry(r)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fw = runtime.finish()
    tokens = dict(t.split("=", 1) for t in out.getvalue().split() if "=" in t)
    return fw, json.loads(base64.urlsafe_b64decode(tokens["rec"]))


@pytest.fixture
def cluster(tmp_path):
    made = []

    def make(policy):
        src, digest = runtime.worker_source()
        workdir = tmp_path / f"{policy}-{len(made)}"
        workdir.mkdir()
        cl = harness.Cluster(policy, str(workdir), src, digest)
        made.append(cl)
        for i in range(3):
            cl.start(i, 0)
        return cl
    yield make
    for cl in made:
        cl.reap_all()


def test_ack_before_or_after_fsync(cluster):
    dur, vol = cluster("durable"), cluster("volatile_ack")
    for cl in (dur, vol):
        assert cl.attempt("o1", "o1:a1", "prefix")["status"] == "ACK"
    assert [r["key"] for r in dur.wal_records(0)] == ["o1:a1"]                       # on disk before the reply
    assert vol.wal_records(0) == [] and vol.request(0, {"op": "snapshot"})["pending"] == ["o1:a1"]
    vol.flush_all()
    assert [r["key"] for r in vol.wal_records(0)] == ["o1:a1"] and vol.request(0, {"op": "snapshot"})["effects"] == ["o1"]   # no new effect


def test_killed_worker_loses_pending_memory_but_durable_reloads(cluster):
    dur, vol = cluster("durable"), cluster("volatile_ack")
    for cl in (dur, vol):
        cl.attempt("o1", "o1:a1", "prefix")
        cl.kill(0)
        cl.reopen([0])
    assert dur.snapshot("x")["nodes"][0]["accepted"] == ["o1:a1"] and dur.nodes[0].generation == 1
    assert vol.snapshot("x")["nodes"][0]["accepted"] == [] and vol.snapshot("x")["nodes"][0]["value"] == 0
    assert [e["returncode"] for e in vol.events if e["event"] == "kill"] == [-signal.SIGKILL]


def test_double_replay_keeps_unique_wal_keys(cluster):
    cl = cluster("replay_twice")
    cl.attempt("o1", "o1:a1", "prefix")
    cl.kill(1)
    cl.reopen([1])
    node = cl.snapshot("x")["nodes"][1]
    assert node["effects"] == ["o1", "o1"] and node["value"] == 2 and node["wal"] == ["o1:a1"] and node["accepted"] == ["o1:a1"]


@pytest.mark.parametrize("cid,verdict,dup", [("P=durable|F=01|C=1|K=partition|R=stable", "PASS", False),
                                              ("P=durable|F=01|C=1|K=partition|R=fresh", "DOMAIN_FAIL", True),
                                              ("P=durable|F=01|C=1|K=crash|R=fresh", "DOMAIN_FAIL", True)])
def test_partial_quorum_and_retry_keys(cid, verdict, dup):
    _, rec = run_case(cid)
    window = [a for a in rec["attempts"] if a["phase"] == "window"][0]
    assert window == {"op": "o2", "key": "o2:a1", "phase": "window", "targets": [2], "status": "TIMEOUT"}
    assert rec["verdict"] == verdict and (rec["trace"][-1]["nodes"][0]["counts"]["o2"] == 2) == dup
    assert (not rec["checks"]["accepted_logical_ops_once"]) == dup


def test_all_node_crash_loses_volatile_acknowledged_work():
    _, rec = run_case("P=volatile_ack|F=012|C=2|K=crash|R=stable")
    assert [a["status"] for a in rec["attempts"]] == ["ACK", "ACK", "TIMEOUT", "ACK"]
    assert rec["checks"]["acknowledged_survive_repair"] is False and rec["trace"][-1]["nodes"][0]["counts"] == {"o1": 0, "o2": 0, "o3": 1}
    assert rec["provenance"]["injected_kills"] == 3 and rec["provenance"]["worker_starts"] == 6


def test_partition_without_restart():
    _, rec = run_case("P=replay_twice|F=12|C=1|K=partition|R=stable")
    assert rec["provenance"]["injected_kills"] == 0 and rec["provenance"]["worker_starts"] == 3
    faulted = [t for t in rec["trace"] if t["checkpoint"] == "faulted"][0]["nodes"]
    assert [(s["running"], s["reachable"], s["generation"]) for s in faulted] == [(True, True, 0), (True, False, 0), (True, False, 0)]
    assert rec["verdict"] == "PASS"                                                  # no restart, no double replay


def test_cut_zero_and_cut_three():
    _, c0 = run_case("P=replay_twice|F=0|C=0|K=crash|R=stable")
    assert [t["checkpoint"] for t in c0["trace"]] == ["initial", "prefix", "faulted", "window", "reopened", "repaired", "final"]
    assert c0["verdict"] == "PASS"                                                   # empty WAL: double replay is harmless
    _, c3 = run_case("P=durable|F=01|C=3|K=partition|R=fresh")
    assert "window" not in [t["checkpoint"] for t in c3["trace"]] and c3["verdict"] == "PASS"   # control: nothing in the window


def test_convergence_masks_a_uniform_wrong_state():
    _, rec = run_case("P=replay_twice|F=012|C=3|K=crash|R=stable")
    final = rec["trace"][-1]["nodes"]
    assert all(s["counts"] == {"o1": 2, "o2": 2, "o3": 2} and s["value"] == 222 for s in final)
    assert rec["checks"]["replicas_agree"] and not rec["checks"]["matches_fault_free_reference"] and rec["verdict"] == "DOMAIN_FAIL"


def test_merge_deduplicates(cluster):
    cl = cluster("durable")
    cl.attempt("o1", "o1:a1", "prefix")
    rec = {"key": "o1:a1", "op": "o1", "delta": 1}
    assert cl.request(0, {"op": "merge", "records": [rec]}) == {"ok": True, "added": 0, "flushed": 0}
    assert cl.snapshot("x")["nodes"][0]["effects"] == ["o1"]


@pytest.mark.parametrize("msg", [{"op": "put", "record": {"key": "o1:a1", "op": "o2", "delta": 10}},
                                 {"op": "put", "record": {"key": "o1:a1", "op": "o1", "delta": 2}},
                                 {"op": "put", "record": {"key": "o9:a1", "op": "o9", "delta": 1}},
                                 {"op": "merge", "records": [{"key": "o2:a1", "op": "o2", "delta": 10}, {"key": "o1:a1", "op": "o1", "delta": 1}]},
                                 {"op": "teleport"}, {"op": "merge", "records": "o1"}])
def test_malformed_ipc_is_an_infrastructure_error(cluster, msg):
    cl = cluster("durable")
    with pytest.raises(harness.InfraError):
        cl.request(0, msg)


def test_conflicting_payload_for_a_known_key(cluster):
    cl = cluster("durable")
    cl.attempt("o1", "o1:a1", "prefix")
    with pytest.raises(harness.InfraError):
        cl.request(0, {"op": "put", "record": {"key": "o1:a1", "op": "o1", "delta": 1, "extra": 1}})


def test_ownership_and_exit_guards(cluster):
    cl = cluster("durable")
    cl.kill(2)
    with pytest.raises(harness.InfraError):
        cl.kill(2)                                                                  # already dead: never signal again
    cl.owned_pids.discard(cl.nodes[1].proc.pid)
    with pytest.raises(harness.InfraError):
        cl.kill(1)                                                                  # not in the owned set
    cl.owned_pids.add(cl.nodes[1].proc.pid)                                         # restore, so cleanup reaps it
    os.kill(cl.nodes[0].proc.pid, signal.SIGTERM)                                   # an unexpected exit
    cl.nodes[0].proc.wait(timeout=5)
    with pytest.raises(harness.InfraError):
        cl.request(0, {"op": "snapshot"})
    with pytest.raises(harness.InfraError):
        harness.Cluster("durable", str(Path(cl.workdir)), "print(1)\n", "0" * 64)   # worker source hash mismatch


def test_tampered_traces_are_detected():
    cid = "P=volatile_ack|F=012|C=2|K=crash|R=stable"
    _, rec = run_case(cid)
    own = verify.transitions(*parse(cid))
    assert [n for n, g, w in verify.record_problems(rec, own) if g != w] == []
    for mutate in (lambda r: r["attempts"][2].update(status="ACK"), lambda r: r["trace"][-1]["nodes"][1].update(value=111),
                   lambda r: r["wal_evidence"]["n0"]["lines"].append(r["wal_evidence"]["n0"]["lines"][0]),
                   lambda r: r["provenance"]["events"][3].update(returncode=0), lambda r: r["checks"].update(replicas_agree=False),
                   lambda r: r["final_payloads"][2]["wal"].pop()):
        t = copy.deepcopy(rec)
        mutate(t)
        assert [n for n, g, w in verify.record_problems(t, own) if g != w]


def test_oracle_payload_check_and_missing_checkpoint():
    _, rec = run_case("P=durable|F=0|C=1|K=crash|R=stable")
    bad = copy.deepcopy(rec["final_payloads"])
    bad[0]["wal"][0] = dict(bad[0]["wal"][0], delta=5)
    assert oracle.checks(rec["attempts"], rec["trace"], bad)[1]["final_wal_matches_accepted"] is False
    with pytest.raises(ValueError):
        oracle.checks(rec["attempts"], rec["trace"][:-1], rec["final_payloads"])


def test_renderer_and_parser_on_a_locally_composed_candidate():
    """Preflight: compose one candidate as the Reader renders it (FAIL row = its values back to back) and run it."""
    sources = {m: (HERE / f"{m}.py").read_text(encoding="utf-8") for m in build_spec.MODULES}
    head, digests = build_spec.head_value(sources)
    slots, extra = build_spec.layout(head)
    pick = {"IMPL": [2], "FAIL": [0, 1, 2], "CUT": [3], "KIND": [0], "RETRY": [0]}   # replay_twice, 012, 3, crash, stable
    cells = [[s[1][i] for i in pick.get(s[0], [0])] for s in slots]
    text = verify.join_cells(cells, [s[2] for s in slots])
    assert "fail(0);fail(1);fail(2);\n" in text
    calls, inlined = verify.parse_candidate(text)
    cid = verify.case_of(calls[:-1])
    assert calls[-1] == ["finish"] and cid == "P=replay_twice|F=012|C=3|K=crash|R=stable"
    assert {k: verify.sha256(v.encode()) for k, v in inlined.items()} == digests and inlined["worker"] == sources["worker"]
    assert dict((r[0], r[1:]) for r in extra)["FAIL"] == ["FW_Subsets", "FW_Combi(size)"]
    env = dict(os.environ, TMPDIR=str(Path(tempfile.gettempdir())))
    r = subprocess.run([sys.executable, "-c", text], capture_output=True, text=True, timeout=120, env=env)
    tokens = dict(t.split("=", 1) for t in r.stdout.split() if "=" in t)
    rec = json.loads(base64.urlsafe_b64decode(tokens["rec"]))
    assert r.returncode == 0 and rec["id"] == cid and rec["verdict"] == FROZEN[cid]["predicted_outcome"] == "DOMAIN_FAIL"
    assert all(rec[k] == FROZEN[cid][k] for k in SEMANTIC) and rec["source_sha256"] == digests
    with pytest.raises(ValueError):
        verify.case_of([["impl", "durable"], ["fail", 1], ["fail", 0], ["cut", 0], ["fault", "crash"], ["retry", "stable"]])
    with pytest.raises(ValueError):
        verify.parse_candidate(text.replace("_verdict = finish()", "_verdict = 0"))


@pytest.mark.parametrize("fails", [[0, 0], [3], [], ["0"]])
def test_lost_or_duplicated_fail_atoms(fails):
    runtime._state.clear()
    runtime.begin(), runtime.impl("durable")
    with pytest.raises((ValueError, RuntimeError)):
        for n in fails:
            runtime.fail(n)
        runtime.cut(0)


def test_stratified_sample_matches_the_frozen_predictions():
    sample = [c for c in DERIVED["cases"] if (c["cut"] + len(c["failed"]) + (c["kind"] == "crash")) % 5 == 0]
    assert len(sample) >= 50
    for c in sample:
        _, rec = run_case(c["id"])
        assert all(rec[k] == c[k] for k in SEMANTIC) and rec["verdict"] == c["predicted_outcome"], c["id"]


def test_verifier_model_equals_frozen_on_all_312():
    for c in DERIVED["cases"]:
        o = verify.transitions(c["policy"], c["failed"], c["cut"], c["kind"], c["retry"])
        assert all(o[k] == c[k] for k in SEMANTIC) and o["verdict"] == c["predicted_outcome"]


def test_oracle_is_policy_blind():
    tree = ast.parse((HERE / "oracle.py").read_text())
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {a.arg for n in ast.walk(tree) if isinstance(n, ast.arguments) for a in n.args}
    assert not literals & set(runtime.IMPLEMENTATIONS) and not any("policy" in n or "impl" in n for n in names)


def test_verifier_and_explorer_import_nothing_from_the_implementation():
    for f in ("verify.py", "explore.py"):
        mods = {n.names[0].name.split(".")[0] if isinstance(n, ast.Import) else (n.module or "").split(".")[0]
                for n in ast.walk(ast.parse((HERE / f).read_text())) if isinstance(n, (ast.Import, ast.ImportFrom))}
        assert not mods & {"worker", "harness", "oracle", "runtime", "preflight", "derive"}, (f, mods)


def test_spec_matches_fresh_build():
    r = subprocess.run([sys.executable, str(HERE / "build_spec.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
