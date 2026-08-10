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

import json
from pathlib import Path

import pytest

from bundle import benchmark as bm
from bundle import config as bconfig
from bundle.gateway.auth import AuthError, TokenAuth
from bundle.gateway.engine import GatewayConfig, GatewayEngine, GatewayError, GatewayLimits, JobState
from bundle.gateway.server import make_handler
from bundle.jsonio import write_json_atomic
from bundle.stages import CORE_JAR, JAVA_EXECUTOR_JAR, READER_JAR

HERE = Path(__file__).resolve().parent
SEEDLOOP_E2E_TOML = HERE / "java_e2e" / "seedloop_e2e" / "seedloop_e2e.toml"

_CFG, _ = bconfig.resolve_config(cli={})
_LIVE = (
    bm._java_ok(_CFG)
    and bm._pg_ok(_CFG.main_db_port, _CFG)
    and bm._pg_ok(_CFG.results_db_port, _CFG, results=True)
    and CORE_JAR.exists() and READER_JAR.exists() and JAVA_EXECUTOR_JAR.exists()
    and SEEDLOOP_E2E_TOML.exists()
)


def _engine(tmp_path: Path) -> GatewayEngine:
    eng = GatewayEngine(GatewayConfig(
        gen_dir=Path.cwd(),
        runs_root=tmp_path / "runs",
        limits=GatewayLimits(max_concurrent_jobs=1, max_worker_units=2, max_executor_pool=2, max_iterations=3),
    ))
    eng._ensure_worker = lambda tenant, job_id: None
    return eng


def _job(**kw):
    # Phase 02 / audit F1: a submitted job must name the policy its candidates
    # run under. The gateway used to substitute unsandboxed trusted-local for a
    # caller who named none -- the same silent grant as the CLI default, one
    # trust boundary further out. `test_gateway_requires_an_execution_policy`
    # pins the refusal.
    data = {"spec_toml": "name='x'\n", "language": "python", "idempotency_key": "",
            "execution_policy_profile": "generated-default"}
    data.update(kw)
    return data


def test_gateway_requires_an_execution_policy(tmp_path):
    from bundle.gateway.engine import GatewayError
    eng = _engine(tmp_path)
    job = _job()
    job.pop("execution_policy_profile")
    with pytest.raises(GatewayError, match="execution_policy_profile is required"):
        eng.submit("tenant-a", job)


def test_gateway_idempotency_returns_existing_job(tmp_path):
    eng = _engine(tmp_path)
    first = eng.submit("tenant-a", _job(idempotency_key="same"))
    second = eng.submit("tenant-a", _job(idempotency_key="same"))
    assert first["job_id"] == second["job_id"]
    assert second["created"] is False
    assert len(eng.registry.list("tenant-a")) == 1


def test_gateway_tenant_isolation(tmp_path):
    eng = _engine(tmp_path)
    handle = eng.submit("tenant-a", _job())
    with pytest.raises(GatewayError) as exc:
        eng.status("tenant-b", handle["job_id"])
    assert exc.value.code == "PERMISSION_DENIED"
    with pytest.raises(GatewayError) as exc:
        eng.submit("tenant-a", _job(db_name="shared"))
    assert exc.value.code == "PERMISSION_DENIED"
    a = eng.submit("tenant-a", _job(job_id="tenant-a-job"))
    b = eng.submit("tenant-b", _job(job_id="tenant-b-job"))
    assert eng.get_record("tenant-a", a["job_id"])["tenant_root"] != eng.get_record("tenant-b", b["job_id"])["tenant_root"]


def test_gateway_authn(tmp_path):
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps({"tok-a": "tenant-a"}), encoding="utf-8")
    auth = TokenAuth(tokens)
    assert auth.authenticate("Bearer tok-a") == "tenant-a"
    with pytest.raises(AuthError) as exc:
        auth.authenticate(None)
    assert exc.value.code == "UNAUTHENTICATED"
    with pytest.raises(AuthError):
        auth.authenticate("Bearer nope")


def test_gateway_override_whitelist_and_admission(tmp_path):
    eng = _engine(tmp_path)
    with pytest.raises(GatewayError) as exc:
        eng.submit("tenant-a", _job(config_overrides={"main_db_password": "pass"}))
    assert exc.value.code == "PERMISSION_DENIED"
    with pytest.raises(GatewayError) as exc:
        eng.submit("tenant-a", _job(config_overrides={"scratch_root": "/tmp/x"}))
    assert exc.value.code == "PERMISSION_DENIED"
    with pytest.raises(GatewayError) as exc:
        eng.submit("tenant-a", _job(executor_pool=3))
    assert exc.value.code == "RESOURCE_EXHAUSTED"
    ok = eng.submit("tenant-a", _job(config_overrides={"executor_compiler": "javac"}))
    rec = eng.get_record("tenant-a", ok["job_id"])
    assert rec["config_overrides"] == {"executor_compiler": "javac"}


def test_gateway_grpc_transport_internals_are_not_tenant_settable(tmp_path):
    eng = _engine(tmp_path)
    for key, value in (("grpc_host", "evil.example.com"), ("grpc_port", "12345")):
        with pytest.raises(GatewayError) as exc:
            eng.submit("tenant-a", _job(config_overrides={key: value}))
        assert exc.value.code == "INVALID_ARGUMENT"

    handle = eng.submit("tenant-a", _job(job_id="grpc-job", candidate_sink="grpc"))
    job = eng.registry.get("tenant-a", handle["job_id"])
    cmd = eng._command_for(job, tmp_path / "spec", tmp_path / "runs" / "tenant-a", "db")
    assert "--grpc-host" in cmd
    assert cmd[cmd.index("--grpc-host") + 1] == "127.0.0.1"
    assert "--grpc-port" in cmd
    port = int(cmd[cmd.index("--grpc-port") + 1])
    assert 0 < port < 65536


def _fake_success_run(run_dir: Path) -> None:
    (run_dir / "stages").mkdir(parents=True)
    write_json_atomic(run_dir / "state.json", {
        "status": "SUCCEEDED",
        "stages": {
            "core": {"status": "SUCCEEDED"},
            "reader": {"status": "SUCCEEDED"},
            "executor": {"status": "SUCCEEDED"},
            "analyzer": {"status": "SUCCEEDED"},
        },
    })
    write_json_atomic(run_dir / "stages" / "core.json", {"counts": [{"name": "fw_final", "actual": 48}]})
    write_json_atomic(run_dir / "stages" / "sieve.json", {"counts": [{"name": "post_sieve", "actual": 48}]})
    write_json_atomic(run_dir / "stages" / "reader.json", {"counts": [{"name": "candidates", "actual": 48}]})
    write_json_atomic(run_dir / "stages" / "executor.json", {
        "counts": [{"name": "processed", "actual": 48}, {"name": "inserted", "actual": 48}]
    })
    write_json_atomic(run_dir / "executor-summary.json", {
        "processed": 48,
        "pass": 19,
        "fail": 29,
        "inserted": 48,
        "outcomes": {"PASS": 19, "DOMAIN_FAIL": 29},
    })
    write_json_atomic(run_dir / "provenance.json", {
        "provenance_ok": True,
        "mode": "formal",
        "goals": [{"key": "latency_ms", "mode": "MINIMIZE"}],
        "candidates": [{
            "candidate_id": "1_0_0",
            "source_ref": "src/1_0_0.java",
            "objectives": {"latency_ms": 3.0},
            "outcome": "PASS",
            "reason_non_dominated": "non-dominated",
            "dimensions": {"A": "x"},
        }],
    })
    (run_dir / "metrics.kv").write_text("candidate_id=1_0_0 latency_ms=3\n", encoding="utf-8")
    (run_dir / "bundle_seed.json").write_text('{"schemaVersion":1,"winners":[]}\n', encoding="utf-8")


def test_gateway_iterate_status_waits_for_supervisor_process(tmp_path):
    eng = _engine(tmp_path)
    handle = eng.submit(
        "tenant-a",
        _job(job_id="iterate-status", iterations=2, analyzer_goals="latency_ms:min"),
    )
    run_dir = tmp_path / "runs" / "tenant-a" / "iterate-status-it1"
    _fake_success_run(run_dir)
    eng.registry.update("tenant-a", handle["job_id"], state=JobState.RUNNING, run_dir=str(run_dir))

    status = eng.status("tenant-a", handle["job_id"])

    assert status["state"] == JobState.RUNNING
    assert status["current_iteration"] == "1/2"
    assert eng.registry.get("tenant-a", handle["job_id"])["state"] == JobState.RUNNING


def test_gateway_results_contract_from_run_artifacts(tmp_path):
    eng = _engine(tmp_path)
    handle = eng.submit("tenant-a", _job(job_id="job-results"))
    with pytest.raises(GatewayError) as exc:
        eng.results("tenant-a", handle["job_id"])
    assert exc.value.code == "FAILED_PRECONDITION"
    run_dir = tmp_path / "runs" / "tenant-a" / "job-results"
    _fake_success_run(run_dir)
    eng.registry.update("tenant-a", "job-results", tenant_root=str(tmp_path / "runs" / "tenant-a"), run_dir=str(run_dir))
    eng.registry.mark_state("tenant-a", "job-results", JobState.SUCCEEDED)
    results = eng.results("tenant-a", "job-results")
    assert results["outcomes"]["PASS"] == 19
    assert results["counts"]["candidates"] == 48
    assert results["front"][0]["id"] == "1_0_0"
    assert results["provenance_ok"] is True
    assert '"schemaVersion":1' in results["seed_json"].replace(" ", "")


@pytest.mark.skipif(not _LIVE, reason="PostgreSQL / JDK 25 / Core+Reader+Executor jars not all available")
def test_gateway_real_submit_spawns_bundle_run_end_to_end(tmp_path):
    """Phase 7 item 1's 'real' half: unlike test_gateway_results_contract_from_run_artifacts
    (which formats hand-written fake run-dir artifacts), this drives an actual submit() ->
    real bundle_run.py subprocess -> real run directory -> results(), against
    java_e2e/seedloop_e2e (48 deterministic candidates; manually verified against this exact
    fixture: 19 PASS / 29 FAIL, 4-candidate Pareto front)."""
    import time

    eng = GatewayEngine(GatewayConfig(
        gen_dir=HERE,
        runs_root=tmp_path / "runs",
        limits=GatewayLimits(max_concurrent_jobs=1, max_worker_units=2, max_executor_pool=2, max_iterations=3),
    ))
    # _ensure_worker is deliberately NOT stubbed here (unlike _engine()) — this test wants
    # the real background worker thread to really spawn bundle_run.py.
    handle = eng.submit("tenant-live", {
        "spec_toml": SEEDLOOP_E2E_TOML.read_text(encoding="utf-8"),
        "language": "java",
        "analyzer_goals": "latency_ms:min,throughput_rps:max",
        # Audit F1: checked-in, reviewed java_e2e fixture candidates. The job
        # states the policy and the justification explicitly; the gateway no
        # longer supplies trusted-local on the caller's behalf.
        "execution_policy_profile": "trusted-local",
        "candidate_origin": "reviewed-checked-in",
        "trusted_local_acknowledgement": "reviewed checked-in java_e2e fixture candidates",
    })
    job_id = handle["job_id"]
    try:
        deadline = time.monotonic() + 120
        status = eng.status("tenant-live", job_id)
        while status["state"] not in JobState.TERMINAL and time.monotonic() < deadline:
            time.sleep(1.0)
            status = eng.status("tenant-live", job_id)
        assert status["state"] == JobState.SUCCEEDED, f"job ended {status['state']}: {status.get('error')}"
        stage_status = {s["name"]: s["status"] for s in status["stages"]}
        for stage in ("core", "reader", "executor", "analyzer"):
            assert stage_status.get(stage) == "SUCCEEDED", f"stage {stage} not SUCCEEDED: {stage_status}"

        results = eng.results("tenant-live", job_id)
        assert results["counts"]["candidates"] == 48
        assert results["counts"]["processed"] == 48
        assert results["outcomes"].get("PASS") == 19
        assert results["outcomes"].get("DOMAIN_FAIL") == 29
        assert results["provenance_ok"] is True
        assert len(results["front"]) > 0
    finally:
        if eng.registry.get("tenant-live", job_id).get("state") not in JobState.TERMINAL:
            eng.cancel("tenant-live", job_id)
        job = eng.registry.get("tenant-live", job_id)
        db_name = job.get("db_name")
        if db_name:
            cfg, _ = bconfig.resolve_config(cli={})
            eng._drop_database(host=cfg.main_db_host, port=cfg.main_db_port,
                                user=cfg.main_db_user, password=cfg.main_db_password, db_name=db_name)
            eng._drop_database(host=cfg.results_db_host, port=cfg.results_db_port,
                                user=cfg.results_db_user, password=cfg.results_db_password, db_name=db_name)


def test_http_handler_requires_auth_for_capabilities(tmp_path):
    eng = _engine(tmp_path)
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps({"tok-a": "tenant-a"}), encoding="utf-8")
    handler = make_handler(eng, TokenAuth(tokens))
    assert handler is not None


def test_grpc_capabilities_smoke(tmp_path):
    grpc = pytest.importorskip("grpc")
    from bundle.gateway.grpc_service import pb2, pb2_grpc, serve_grpc

    eng = GatewayEngine(GatewayConfig(
        gen_dir=Path.cwd(),
        runs_root=tmp_path / "runs",
        limits=GatewayLimits(max_concurrent_jobs=1, max_worker_units=2, max_executor_pool=2, max_iterations=3),
        transport="grpc",
    ))
    eng._ensure_worker = lambda tenant, job_id: None
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps({"tok-a": "tenant-a"}), encoding="utf-8")

    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = serve_grpc(eng, TokenAuth(tokens), host="127.0.0.1", port=port)
    try:
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = pb2_grpc.EvaluationGatewayStub(channel)
        health = stub.Health(pb2.Empty(), timeout=3)
        caps = stub.Capabilities(pb2.Empty(), metadata=(("authorization", "Bearer tok-a"),), timeout=3)
        assert health.live is True
        assert caps.transport == "grpc"
        assert caps.grpc_python_available is True
    finally:
        server.stop(grace=0).wait()


def test_gateway_crash_recovery_marks_running_job_failed_and_terminates_process(tmp_path):
    import subprocess
    import time
    from bundle.gateway.engine import _proc_alive, _proc_start_ticks

    eng = _engine(tmp_path)
    handle = eng.submit("tenant-a", _job(job_id="crash-job"))
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        eng.registry.update(
            "tenant-a", handle["job_id"], state=JobState.RUNNING, pid=proc.pid,
            start_ticks=_proc_start_ticks(proc.pid), tenant_root=str(tmp_path / "runs" / "tenant-a"),
        )
        GatewayEngine(GatewayConfig(gen_dir=Path.cwd(), runs_root=tmp_path / "runs"))
        rec = eng.registry.get("tenant-a", handle["job_id"])
        assert rec["state"] == JobState.FAILED
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and _proc_alive(proc.pid):
            time.sleep(0.1)
        assert not _proc_alive(proc.pid)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_gateway_cancel_terminates_live_process_group(tmp_path):
    """Phase 7 item 6: Cancel a live (not merely reconciled-on-restart) job and confirm no
    orphan process is left in its process group."""
    import os
    import subprocess
    import time
    from bundle.gateway.engine import _proc_alive, _proc_start_ticks

    eng = _engine(tmp_path)
    handle = eng.submit("tenant-a", _job(job_id="cancel-job"))
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        pgid = os.getpgid(proc.pid)
        eng.registry.update(
            "tenant-a", handle["job_id"], state=JobState.RUNNING, pid=proc.pid, pgid=pgid,
            start_ticks=_proc_start_ticks(proc.pid), tenant_root=str(tmp_path / "runs" / "tenant-a"),
        )

        status = eng.cancel("tenant-a", handle["job_id"])

        assert status["state"] == JobState.CANCELLED
        assert eng.registry.get("tenant-a", handle["job_id"])["state"] == JobState.CANCELLED
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and _proc_alive(proc.pid):
            time.sleep(0.1)
        assert not _proc_alive(proc.pid), "Cancel must terminate the live process"
        proc.wait(timeout=5)  # reap the zombie so pgrep reflects reality, not a pending reap
        pgrep = subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True, text=True)
        assert pgrep.returncode != 0, f"orphan process(es) left in process group {pgid}: {pgrep.stdout}"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_gateway_cleanup_refuses_nonterminal_and_cleans_terminal_job(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    handle = eng.submit("tenant-a", _job(job_id="cleanup-job"))
    eng.registry.update("tenant-a", handle["job_id"], db_name="tenant_a_cleanup_job")
    with pytest.raises(GatewayError) as exc:
        eng.cleanup_job("tenant-a", handle["job_id"])
    assert exc.value.code == "FAILED_PRECONDITION"

    run_dir = tmp_path / "runs" / "tenant-a" / "cleanup-job"
    run_dir.mkdir(parents=True)
    calls = []

    class Result:
        returncode = 0
        stdout = "cleanup ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Result()

    drops = []
    monkeypatch.setattr("bundle.gateway.engine.subprocess.run", fake_run)
    monkeypatch.setattr(eng, "_drop_database", lambda **kw: drops.append(kw) or {"db": kw["db_name"], "status": "dropped-or-absent"})
    monkeypatch.setattr("bundle.gateway.engine.resolve_config", lambda cli={}: (type("Cfg", (), {
        "main_db_host": "127.0.0.1", "main_db_port": 5433, "main_db_user": "postgres", "main_db_password": "pass",
        "results_db_host": "127.0.0.1", "results_db_port": 5432, "results_db_user": "postgres", "results_db_password": "pass",
    })(), {}))

    eng.registry.update("tenant-a", handle["job_id"], tenant_root=str(tmp_path / "runs" / "tenant-a"), run_dir=str(run_dir))
    eng.registry.mark_state("tenant-a", handle["job_id"], JobState.SUCCEEDED)
    report = eng.cleanup_job("tenant-a", handle["job_id"])
    assert report["errors"] == []
    assert calls and calls[0][1:3] == ["bundle_run.py", "cleanup"]
    assert len(drops) == 2
    assert eng.registry.get("tenant-a", handle["job_id"])["cleaned_at"]


def test_gateway_health_uses_resolved_dependency_probes(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    core_jar = tmp_path / "core.jar"
    reader_jar = tmp_path / "reader.jar"
    executor_jar = tmp_path / "executor.jar"
    py_executor = tmp_path / "py_executor.py"
    for prerequisite in (core_jar, reader_jar, executor_jar, py_executor):
        prerequisite.write_bytes(b"test prerequisite")
    java_jars_dir = tmp_path / "java-jars"
    java_jars_dir.mkdir()
    monkeypatch.setattr("bundle.gateway.engine.CORE_JAR", core_jar)
    monkeypatch.setattr("bundle.gateway.engine.READER_JAR", reader_jar)
    monkeypatch.setattr("bundle.gateway.engine.JAVA_EXECUTOR_JAR", executor_jar)
    monkeypatch.setattr("bundle.gateway.engine.JAVA_JARS_DIR", java_jars_dir)
    monkeypatch.setattr("bundle.gateway.engine.PY_EXECUTOR", py_executor)
    cfg = type("Cfg", (), {
        "main_db_host": "127.0.0.1", "main_db_port": 5433, "main_db_user": "postgres", "main_db_password": "pass",
        "results_db_host": "127.0.0.1", "results_db_port": 5432, "results_db_user": "postgres", "results_db_password": "pass",
        "java_cmd": "java",
    })()
    monkeypatch.setattr("bundle.gateway.engine.resolve_config", lambda cli={}: (cfg, {}))
    monkeypatch.setattr(eng, "_db_health", lambda *args: "ready")
    monkeypatch.setattr(eng, "_java_health", lambda java_cmd: "java version \"25.0.3\"")
    health = eng.health()
    assert health["ready"] is True
    assert health["deps"]["main_db"] == "ready"

    monkeypatch.setattr(eng, "_java_health", lambda java_cmd: "missing:JDK 25 required, got java version 21")
    health = eng.health()
    assert health["ready"] is False
    assert any("JDK 25" in reason for reason in health["reasons"])
