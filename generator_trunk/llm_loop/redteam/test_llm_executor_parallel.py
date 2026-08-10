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

"""Acceptance tests for the parallel, resumable red-team Executor (spec section 15).

Runs WITHOUT PostgreSQL and WITHOUT Ollama. The DB integration test is gated/skipped
when no local results cluster is reachable. No real external network is used.
"""
from __future__ import annotations

import http.server
import json
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))                 # generator_trunk/
sys.path.insert(0, str(HERE.parents[2] / "Executor_trunk"))  # worker_pool

import llm_executor as X  # noqa: E402
import worker_pool  # noqa: E402


# ------------------------------- helpers ------------------------------------ #
def base_args(tmp_path, **over):
    a = {"provider": "mock", "workers": 1, "db_mode": "off", "run_id": "t",
         "state_dir": tmp_path / "state", "metrics_file": tmp_path / "m.kv",
         "result_file": tmp_path / "r.json"}
    a.update(over)
    out = ["--provider", a["provider"], "--workers", str(a["workers"]),
           "--db-mode", a["db_mode"], "--run-id", a["run_id"],
           "--state-dir", str(a["state_dir"]), "--metrics-file", str(a["metrics_file"]),
           "--result-file", str(a["result_file"])]
    if "mock_delay_ms" in over:
        out += ["--mock-delay-ms", str(over["mock_delay_ms"])]
    if "attempt" in over:
        out += ["--attempt", str(over["attempt"])]
    if "ollama_host" in over:
        out += ["--ollama-host", over["ollama_host"]]
    if over.get("resume"):
        out += ["--resume"]
    return out


def semantic(path):
    """candidate_id -> verdict fields, dropping run/worker identity (cross-config compare)."""
    rows = {}
    for ln in Path(path).read_text().splitlines():
        if not ln:
            continue
        f = dict(t.split("=", 1) for t in ln.split() if "=" in t)
        rows[f["candidate_id"]] = {k: v for k, v in f.items()
                                   if k not in ("run_id", "worker_index", "model", "provider")}
    return rows


# --------------------------- 15.1 partition correctness --------------------- #
def test_matrix_is_exactly_288():
    import redteam_matrix as M
    assert M.count() == 288
    assert sum(1 for _ in M.reassemble()) == 288


@pytest.mark.parametrize("n", [1, 2, 3, 4, 7, 8])
def test_partitions_disjoint_union_stable(n):
    fp = X.compute_fingerprint(n)
    assert fp["total"] == 288
    assert sum(s["count"] for s in fp["shards"]) == 288
    # every candidate maps to exactly one worker, deterministically
    assign = {}
    for combo, cid, _ln in X._candidate_lines():
        w = worker_pool.assign(cid, n)
        assert cid not in assign
        assign[cid] = w
        assert cid == X.candidate_id_for(combo)        # stable id independent of worker count
    assert len(assign) == 288
    # rerun is identical (deterministic)
    assert X.compute_fingerprint(n)["space_sha256"] == fp["space_sha256"]


def test_candidate_space_hash_is_worker_count_independent():
    hashes = {X.compute_fingerprint(n)["space_sha256"] for n in (1, 4, 8)}
    assert len(hashes) == 1


# ---------------------- 15.2 one vs N worker equivalence -------------------- #
def test_one_vs_n_worker_equivalence(tmp_path):
    sems = {}
    for n in (1, 2, 4, 8):
        d = tmp_path / f"w{n}"
        rc = X.main(base_args(d, workers=n, run_id=f"eq{n}"))
        assert rc == 0, n
        sems[n] = semantic(d / "m.kv")
        assert len(sems[n]) == 288
    assert sems[1] == sems[2] == sems[4] == sems[8]    # identical attributable verdicts


def test_same_config_rerun_is_byte_identical(tmp_path):
    a = X.main(base_args(tmp_path / "A", workers=2, run_id="det"))
    b = X.main(base_args(tmp_path / "B", workers=2, run_id="det"))
    assert a == b == 0
    assert (tmp_path / "A" / "m.kv").read_bytes() == (tmp_path / "B" / "m.kv").read_bytes()


def test_fresh_coordinator_enumerates_candidate_space_once(tmp_path, monkeypatch):
    original = X._candidate_lines
    calls = []

    def counted():
        calls.append(1)
        yield from original()

    monkeypatch.setattr(X, "_candidate_lines", counted)
    assert X.main(base_args(tmp_path, workers=2, run_id="once")) == 0
    assert len(calls) == 1


def test_non_resume_run_is_fresh_not_implicit_reuse(tmp_path):
    args = base_args(tmp_path, workers=2, run_id="fresh")
    assert X.main(args) == 0
    assert X.main(args) == 0
    summary = json.loads((tmp_path / "r.json").read_text())
    assert summary["reused_workers"] == []
    assert summary["rerun_workers"] == [0, 1]


# ------------------------- 15.3 real concurrency proof ---------------------- #
def test_delayed_mock_proves_concurrency(tmp_path):
    delay = 5
    t0 = time.monotonic()
    assert X.main(base_args(tmp_path / "s1", workers=1, run_id="c1", mock_delay_ms=delay)) == 0
    serial = time.monotonic() - t0
    t0 = time.monotonic()
    assert X.main(base_args(tmp_path / "s4", workers=4, run_id="c4", mock_delay_ms=delay)) == 0
    parallel = time.monotonic() - t0
    # 288 candidates x 5ms sleeps overlap across 4 workers — require >= 2x on this PC.
    assert serial >= 2.0 * parallel, f"serial={serial:.2f}s parallel={parallel:.2f}s"


# --------------------------- 15.4 crash and resume -------------------------- #
def test_crash_then_resume_reruns_only_failed_worker(tmp_path, monkeypatch):
    args = base_args(tmp_path, workers=4, run_id="crash")
    monkeypatch.setenv("LLM_REDTEAM_TEST_FAIL_WORKER", "1")
    assert X.main(args) != 0                                   # one worker crashes -> nonzero
    assert not (tmp_path / "m.kv").exists()                    # failed run published no final corpus
    monkeypatch.delenv("LLM_REDTEAM_TEST_FAIL_WORKER", raising=False)
    assert X.main(base_args(tmp_path, workers=4, run_id="crash", resume=True)) == 0
    summary = json.loads((tmp_path / "r.json").read_text())
    assert summary["rerun_workers"] == [1]
    assert summary["reused_workers"] == [0, 2, 3]
    assert summary["processed"] == 288
    ids = [dict(t.split("=", 1) for t in ln.split() if "=" in t)["candidate_id"]
           for ln in (tmp_path / "m.kv").read_text().splitlines() if ln]
    assert len(ids) == len(set(ids)) == 288                    # complete, duplicate-free


# ----------------------- 15.5 resume mismatch refusal ----------------------- #
def test_resume_requires_manifest(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="r", resume=True)) == 2


def test_resume_changed_worker_count_fails_closed(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="r")) == 0
    assert X.main(base_args(tmp_path, workers=4, run_id="r", resume=True)) == 2


def test_resume_changed_attempt_fails_closed(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="r")) == 0
    assert X.main(base_args(tmp_path, workers=2, run_id="r", attempt=2, resume=True)) == 2


def test_resume_changed_provider_runtime_fails_closed(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="r", mock_delay_ms=0)) == 0
    assert X.main(base_args(tmp_path, workers=2, run_id="r", mock_delay_ms=10,
                            resume=True)) == 2


def test_resume_tampered_identity_fails_closed(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="r")) == 0
    man = tmp_path / "state" / "manifest.json"
    m = json.loads(man.read_text())
    m["model"] = "someone-elses-model"
    man.write_text(json.dumps(m))
    assert X.main(base_args(tmp_path, workers=2, run_id="r", resume=True)) == 2


def test_checkpoint_invalid_on_malformed_or_missing_partition(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="r")) == 0
    manifest = json.loads((tmp_path / "state" / "manifest.json").read_text())
    assert X.checkpoint_valid(tmp_path / "state", 0, manifest)
    # corrupt the metrics partition -> checkpoint must be rejected (worker would be rerun)
    X.worker_metrics_path(tmp_path / "state", 0).write_text("garbage\n")
    assert not X.checkpoint_valid(tmp_path / "state", 0, manifest)
    # malformed summary -> rejected
    X.worker_summary_path(tmp_path / "state", 1).write_text("{not json")
    assert not X.checkpoint_valid(tmp_path / "state", 1, manifest)


def test_checkpoint_invalid_on_tampered_runtime_fields(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="cp")) == 0
    manifest = json.loads((tmp_path / "state" / "manifest.json").read_text())
    sp = X.worker_summary_path(tmp_path / "state", 0)
    summary = json.loads(sp.read_text())
    summary["provider"] = "tampered-provider"
    sp.write_text(json.dumps(summary))
    assert not X.checkpoint_valid(tmp_path / "state", 0, manifest)
    assert X.main(base_args(tmp_path, workers=2, run_id="cp", resume=True)) == 0
    final = json.loads((tmp_path / "r.json").read_text())
    assert final["rerun_workers"] == [0]
    assert final["reused_workers"] == [1]


def test_checkpoint_invalid_when_summary_disagrees_with_metrics(tmp_path):
    assert X.main(base_args(tmp_path, workers=2, run_id="counts")) == 0
    manifest = json.loads((tmp_path / "state" / "manifest.json").read_text())
    sp = X.worker_summary_path(tmp_path / "state", 0)
    summary = json.loads(sp.read_text())
    summary["outcomes"]["breach"] -= 1
    summary["outcomes"]["refused"] += 1
    sp.write_text(json.dumps(summary))
    assert not X.checkpoint_valid(tmp_path / "state", 0, manifest)


# --------------------------- 15.6 provider failure -------------------------- #
def test_unavailable_ollama_fails_no_mock_fallback(tmp_path):
    # nothing listening on this port -> preflight fails closed, NOT a mock run
    rc = X.main(base_args(tmp_path, workers=1, provider="ollama",
                          ollama_host="http://127.0.0.1:9", run_id="o"))
    assert rc == 2
    assert not (tmp_path / "m.kv").exists()


class _FlakyOllama(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # /api/tags -> reachable (preflight passes)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"models":[]}')

    def do_POST(self):  # /api/chat -> transport failure
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"boom")


def test_per_request_failure_becomes_infra_outcome(tmp_path):
    srv = http.server.HTTPServer(("127.0.0.1", 0), _FlakyOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        rc = X.main(base_args(tmp_path, workers=2, provider="ollama",
                              ollama_host=host, run_id="flaky"))
    finally:
        srv.shutdown()
    assert rc != 0                                            # infra failures -> nonzero
    summary = json.loads((tmp_path / "r.json").read_text())
    assert summary["status"] == "FAILED"
    assert summary["outcomes"]["infra_fail"] == 288
    assert summary["outcomes"]["breach"] == 0                 # never substituted with a mock breach


# ----------------------------- 15.7 database -------------------------------- #
def test_db_sql_is_parameterized_and_idempotent_by_identity():
    assert X.INSERT_SQL.count("%s") == 21
    assert "ON CONFLICT (run_id,candidate_id,attempt) DO NOTHING" in X.INSERT_SQL
    assert "PRIMARY KEY (run_id, candidate_id, attempt)" in X.DDL


def test_row_for_db_shape():
    cand = next(({"candidate_id": X.candidate_id_for(c), "combo_id": c, "labels": lab, "prompt": p}
                 for c, lab, p in __import__("redteam_matrix").reassemble()))
    rec = X.score(X.MockVictim(), cand)

    class A:
        run_id, attempt, provider, ollama_model = "rid", 1, "mock", "llama3.1"
    row = X.row_for_db(A, 0, rec)
    assert len(row) == 21
    assert row[0:3] == ("rid", cand["candidate_id"], 1)       # PK identity first


def test_db_mode_off_runs_without_postgres(tmp_path):
    rc = X.main(base_args(tmp_path, workers=2, run_id="nodb", db_mode="off"))
    assert rc == 0
    assert json.loads((tmp_path / "r.json").read_text())["db"]["attempted"] == 0


def test_unsafe_database_name_is_rejected():
    with pytest.raises(SystemExit):
        X.main(["--db-name", 'bad\";DROP DATABASE postgres;--'])


def test_optional_db_setup_failure_is_recorded(tmp_path, monkeypatch):
    def fail(_args):
        raise RuntimeError("synthetic DB outage")

    monkeypatch.setattr(X, "db_setup_schema", fail)
    rc = X.main(base_args(tmp_path, workers=2, run_id="dbwarn", db_mode="optional"))
    assert rc == 0
    summary = json.loads((tmp_path / "r.json").read_text())
    assert summary["status"] == "SUCCEEDED_WITH_WARNINGS"
    assert summary["db"]["requested_mode"] == "optional"
    assert summary["db"]["effective_mode"] == "off"
    assert summary["db"]["warnings"]


def test_db_integration_idempotent_if_local_postgres(tmp_path):
    name = "redteam_test_v2"
    args0 = base_args(tmp_path, workers=2, run_id="dbi", db_mode="required")
    args0 += ["--db-name", name]
    try:
        rc = X.main(args0)
    except SystemExit:
        pytest.skip("local results PostgreSQL not available")
    if rc != 0:
        pytest.skip("local results PostgreSQL not available")
    # query inserted count
    import importlib
    params = X.db_params(type("A", (), {"db_name": name})())
    try:
        cx = X.db_connect(params)
    except Exception:
        pytest.skip("cannot reconnect to verify")
    cu = cx.cursor()
    cu.execute("SELECT count(*) FROM redteam_findings_v2 WHERE run_id=%s", ("dbi",))
    first = cu.fetchone()[0]
    cu.close(); cx.close()
    assert first == 288
    # Fresh replay executes every candidate again; ON CONFLICT, not checkpoint skipping,
    # must preserve uniqueness.
    replay_args = base_args(tmp_path, workers=2, run_id="dbi", db_mode="required") + ["--db-name", name]
    assert X.main(replay_args) == 0
    replay_summary = json.loads((tmp_path / "r.json").read_text())
    assert replay_summary["db"]["attempted"] == 288
    assert replay_summary["db"]["already_present"] == 288
    cx = X.db_connect(params); cu = cx.cursor()
    cu.execute("SELECT count(*) FROM redteam_findings_v2 WHERE run_id=%s", ("dbi",))
    assert cu.fetchone()[0] == 288
    cu.execute('DROP TABLE redteam_findings_v2')
    cx.commit(); cu.close(); cx.close()
    importlib.invalidate_caches()


# --------------------------- 15.8 atomic artifacts -------------------------- #
def test_failed_run_does_not_overwrite_prior_success(tmp_path, monkeypatch):
    ok = base_args(tmp_path, workers=2, run_id="ok")
    assert X.main(ok) == 0
    good = (tmp_path / "m.kv").read_bytes()
    # a separate failing run targeting the SAME metrics file must not clobber it
    state2 = tmp_path / "state2"
    fail = ["--provider", "mock", "--workers", "2", "--db-mode", "off", "--run-id", "bad",
            "--state-dir", str(state2), "--metrics-file", str(tmp_path / "m.kv"),
            "--result-file", str(tmp_path / "bad.json")]
    monkeypatch.setenv("LLM_REDTEAM_TEST_FAIL_WORKER", "0")
    assert X.main(fail) != 0
    monkeypatch.delenv("LLM_REDTEAM_TEST_FAIL_WORKER", raising=False)
    assert (tmp_path / "m.kv").read_bytes() == good           # untouched


def test_merge_detects_duplicate_and_missing(tmp_path):
    state = tmp_path / "state"
    (state / "partitions").mkdir(parents=True)
    manifest = {"workers": 1, "candidate_count": 2}
    mp = X.worker_metrics_path(state, 0)
    mp.write_text("candidate_id=redteam:1 combo_id=1 x=1\ncandidate_id=redteam:1 combo_id=1 x=1\n")
    with pytest.raises(SystemExit):
        X.merge_metrics(state, manifest)                      # duplicate
    mp.write_text("candidate_id=redteam:1 combo_id=1 x=1\n")
    with pytest.raises(SystemExit):
        X.merge_metrics(state, manifest)                      # missing (1 != 2)


# ------------------------- 15.9 backward compatibility ---------------------- #
def test_legacy_positional_invocation(tmp_path):
    out = tmp_path / "legacy.kv"
    assert X.main(["mock", str(out)]) == 0
    lines = [ln for ln in out.read_text().splitlines() if ln]
    assert len(lines) == 288
    assert all(ln.startswith("app=llm_redteam ") for ln in lines)
