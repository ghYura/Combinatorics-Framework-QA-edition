#!/usr/bin/env python3
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
# (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
# Ukraine
#
# See LICENSE and NOTICE.md for the binding terms.

"""STEP 40 — stage-specific benchmark harness.

Every stage runs for REAL when its backend is available (no hardcoded skips):
generator/sieve in-process, analyzer via AnalyzeKv, and Core/Reader/Executor via
the real bundle stages on temp DBs. A stage records SKIPPED only when its infra
is genuinely absent (with a precise reason). 100M/1B are never auto-run; no
"end-to-end billion executions" claim.

Run: `python3 -m pytest test_bundle_benchmark.py -q`. The pipeline/sandbox tests
self-skip when PostgreSQL / the jars / Docker are unavailable.
"""
import dataclasses
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bundle import benchmark as bm, config

_CFG, _ = config.resolve_config(cli={})
_JAVA = bm._java_ok(_CFG)
_PG = bm._pg_ok(_CFG.main_db_port, _CFG) and bm._pg_ok(_CFG.results_db_port, _CFG, results=True)
_READER = (Path(_CFG.reader_jar) if _CFG.reader_jar else bm.stages.READER_JAR).exists()
_CORE = (Path(_CFG.core_jar) if _CFG.core_jar else bm.stages.CORE_JAR).exists()
_PYEXEC = (Path(_CFG.py_executor) if _CFG.py_executor else bm.stages.PY_EXECUTOR).exists()
_ANALYZER = (bm.SRC / "Analyzer_trunk/target/analyzekv/AnalyzeKv.class").exists() and \
            (bm.SRC / "Analyzer_trunk/analyzer_cp.txt").exists()
_PIPELINE = _JAVA and _PG and _READER and _CORE and _PYEXEC
_DOCKER = bm._docker_ok()


# ---- structural / guard tests (no infra) ---------------------------------- #
def test_resolve_profile_and_huge_guard():
    assert bm.resolve_profile("10K") == 10_000
    assert bm.resolve_profile("1M") == 1_000_000 and bm.resolve_profile("10M") == 10_000_000
    with pytest.raises(bm.BenchmarkError, match="never started automatically|ceiling"):
        bm.resolve_profile("100000000")
    with pytest.raises(bm.BenchmarkError):
        bm.resolve_profile("1000000000")
    assert bm.resolve_profile("100000000", allow_huge=True) == 100_000_000   # resolve only, no run
    with pytest.raises(bm.BenchmarkError, match="unknown profile"):
        bm.resolve_profile("banana")


def test_10k_infra_free_stages_measured_separately(tmp_path):
    rep = bm.run_benchmark("10K", ["generator", "sieve"], scratch=tmp_path, cfg=_CFG)
    bm.validate_report(rep)
    assert rep["candidates"] == 10_000
    stages = {s["stage"]: s for s in rep["stages"]}
    assert set(stages) == {"generator", "sieve"}                  # boundaries measured separately
    for s in stages.values():
        assert not s["skipped"] and s["throughput_per_s"] > 0 and s["peak_memory_bytes"] > 0
    assert stages["generator"]["rows"] == 10_000


@pytest.mark.parametrize("n", [12, 97, 256, 10000])     # non-square, prime, square, profile
def test_input_is_exactly_n_and_throughput_uses_actual_count(n, tmp_path):
    """Heavy-stage input is sized to EXACTLY n (a×b == n), and throughput is
    computed against the actual processed rows, not the requested profile size."""
    a, b = bm._factor_pair(n)
    assert a * b == n                                    # exact factorization
    rep = bm.run_benchmark(str(n), ["generator", "sieve"], scratch=tmp_path, cfg=_CFG)
    for s in rep["stages"]:
        assert s["rows"] == n                            # exactly n, not (isqrt(n)+1)²
        # throughput is sourced from the actual rows/wall (relative tolerance covers
        # the report's wall(6dp)/throughput(2dp) rounding)
        if s["wall_seconds"] > 0 and s["throughput_per_s"] > 0:
            expected = s["rows"] / s["wall_seconds"]
            assert abs(s["throughput_per_s"] - expected) <= 0.01 * expected + 1


def test_report_environment_and_component_hashes(tmp_path):
    env = bm.run_benchmark("10K", ["generator"], scratch=tmp_path, cfg=_CFG)["environment"]
    for key in ("hardware", "os_kernel", "toolchain", "component_hashes", "db_settings"):
        assert key in env
    assert env["hardware"]["cpu_count"] and env["toolchain"]["python"]
    assert "fwgen.py" in env["component_hashes"] and "sieve.py" in env["component_hashes"]


def test_no_billion_claim(tmp_path):
    rep = bm.run_benchmark("10K", ["generator", "sieve"], scratch=tmp_path, cfg=_CFG)
    assert "billion" in rep["claims"]["disclaimer"].lower()
    assert "never run automatically" in rep["claims"]["disclaimer"].lower()
    assert "fused end-to-end" in rep["claims"]["scope"]


def test_structurally_reproducible(tmp_path):
    a = bm.run_benchmark("10K", ["generator", "sieve"], scratch=tmp_path / "a", cfg=_CFG)
    b = bm.run_benchmark("10K", ["generator", "sieve"], scratch=tmp_path / "b", cfg=_CFG)
    assert a["candidates"] == b["candidates"]
    assert [s["stage"] for s in a["stages"]] == [s["stage"] for s in b["stages"]]
    assert [s["rows"] for s in a["stages"]] == [s["rows"] for s in b["stages"]]
    assert a["environment"]["component_hashes"] == b["environment"]["component_hashes"]


def test_validate_report_rejects_defects(tmp_path):
    with pytest.raises(bm.BenchmarkError):
        bm.validate_report({"schema": "wrong"})
    good = bm.run_benchmark("10K", ["generator"], scratch=tmp_path, cfg=_CFG)
    good["claims"]["disclaimer"] = "no caveat"
    with pytest.raises(bm.BenchmarkError, match="billion"):
        bm.validate_report(good)


def test_stage_skips_with_precise_reason_when_infra_absent(tmp_path, monkeypatch):
    """A stage records SKIPPED (with a reason) only when its backend is missing —
    here a deliberately-unreachable main DB port — never a hardcoded skip.

    This is an infra-detection unit test, so make the earlier Java/JAR checks
    deterministic instead of depending on generated build artifacts.
    """
    import dataclasses
    core_jar = tmp_path / "Core-test.jar"
    core_jar.touch()
    monkeypatch.setattr(bm, "_java_ok", lambda cfg: True)
    monkeypatch.setattr(bm, "_pg_ok", lambda port, cfg, *, results=False: False)
    bad = dataclasses.replace(_CFG, main_db_port=1, core_jar=str(core_jar))
    rep = bm.run_benchmark("100", ["core"], scratch=tmp_path, cfg=bad, main_port=1)
    s = rep["stages"][0]
    assert s["skipped"]
    assert s["skip_reason"] == "main PostgreSQL :1 not reachable"


def test_reference_wrapper_uses_unique_database_and_cleanup_tracks_both_clusters(
        tmp_path, monkeypatch):
    """The overhead harness must never run a launcher against its fixed default
    database: Core preEraseDB would overwrite it and the benchmark used to leave
    that side effect behind."""
    core_jar = tmp_path / "core.jar"
    reader_jar = tmp_path / "reader.jar"
    core_jar.touch()
    reader_jar.touch()
    cfg = dataclasses.replace(
        _CFG,
        core_jar=str(core_jar),
        reader_jar=str(reader_jar),
        main_db_password="test-only",
        results_db_password="test-only",
    )
    commands = []
    dropped = []

    def fake_run_wall(command, env):
        commands.append(command)
        return (2.0 if "run_direct_engine_smoke.py" in command[1] else 1.0, 0)

    monkeypatch.setattr(bm, "_java_ok", lambda _cfg: True)
    monkeypatch.setattr(bm, "_pg_ok", lambda *args, **kwargs: True)
    monkeypatch.setattr(bm, "_run_wall", fake_run_wall)
    monkeypatch.setattr(bm, "_stage_durations", lambda _run_dir: {"engine.core": 0.5})
    monkeypatch.setattr(bm, "_candidate_count", lambda _run_dir: 8)
    monkeypatch.setattr(bm, "_drop_db", lambda port, name, _cfg, *, results=False:
                        dropped.append((port, name, results)))
    monkeypatch.setattr(bm, "capture_environment", lambda **kwargs: {
        "hardware": {}, "os_kernel": {}, "toolchain": {},
        "component_hashes": {}, "db_settings": {}})

    report = bm.run_benchmark(
        "100", ["reference_overhead[engine-demo]"], scratch=tmp_path, cfg=cfg)
    stage = report["stages"][0]
    assert stage["candidates"] == stage["rows"] == 8  # actual workload, not profile=100

    direct = next(command for command in commands
                  if command[1].endswith("bundle_run.py") and "plan" not in command)
    wrapper = next(command for command in commands
                   if command[1].endswith("run_direct_engine_smoke.py"))
    direct_db = direct[direct.index("--db") + 1]
    wrapper_db = wrapper[wrapper.index("--db") + 1]
    wrapper_run_id = wrapper[wrapper.index("--run-id") + 1]
    assert direct_db.startswith("refovh_direct_engine_demo_")
    assert wrapper_db.startswith("refovh_app_engine_demo_")
    assert direct_db != wrapper_db
    assert wrapper_run_id.startswith("refovh-app-engine_demo-")
    assert {(name, results) for _port, name, results in dropped} == {
        (direct_db, False), (direct_db, True),
        (wrapper_db, False), (wrapper_db, True),
    }


def test_ai_campaign_honors_single_scenario_database_override(tmp_path):
    from AI_combi_testing_platform import run_campaign

    args = SimpleNamespace(
        db="isolated_benchmark_db", runs_root=tmp_path,
        main_port=5433, results_port=5432, repeat=1,
        budget_requests=None, budget_monetary_cost=None, cost_per_candidate=None,
    )
    command = run_campaign._run_command("00_smoke", "run-id", args)
    assert command[command.index("--db") + 1] == "isolated_benchmark_db"


# ---- REAL execution of every stage (infra-gated) -------------------------- #
@pytest.mark.skipif(not _ANALYZER, reason="Analyzer build not present")
def test_analyzer_runs_for_real(tmp_path):
    rep = bm.run_benchmark("10K", ["analyzer"], scratch=tmp_path, cfg=_CFG)
    s = rep["stages"][0]
    assert not s["skipped"] and s["rows"] == 10_000 and s["throughput_per_s"] > 0
    assert "AnalyzeKv" in s["notes"]


@pytest.mark.skipif(not _PIPELINE, reason="PostgreSQL / Core jar / Reader jar / py_executor not all available")
def test_core_reader_executor_execute_for_real(tmp_path):
    """Core, Reader (loose+shard) and Executor (local+workers) are MEASURED, not
    skipped, when the infrastructure exists (the reviewer's blocking gap)."""
    rep = bm.run_benchmark("6", ["core", "reader_loose", "reader_shard",
                                  "executor_local", "executor_workers"],
                           scratch=tmp_path, cfg=_CFG)    # 6 -> 2×3 spec -> EXACTLY 6 candidates
    bm.validate_report(rep)
    stages = {s["stage"]: s for s in rep["stages"]}
    for name in ("core", "reader_loose", "reader_shard", "executor_local", "executor_workers"):
        s = stages[name]
        assert not s["skipped"], f"{name} was skipped: {s['skip_reason']}"
        assert s["rows"] == 6 and s["wall_seconds"] > 0 and s["throughput_per_s"] > 0   # exactly n
    assert stages["core"]["rows"] == stages["reader_loose"]["rows"]    # Reader reassembled all Core rows
    assert rep["claims"]["measured_stages"] == ["core", "reader_loose", "reader_shard",
                                                "executor_local", "executor_workers"]


@pytest.mark.skipif(not (_PIPELINE and _DOCKER), reason="Docker container backend / pipeline infra not available")
def test_executor_sandbox_uses_container_backend(tmp_path):
    rep = bm.run_benchmark("6", ["executor_sandbox"], scratch=tmp_path, cfg=_CFG)
    s = rep["stages"][0]
    assert not s["skipped"], f"sandbox skipped: {s['skip_reason']}"
    assert s["rows"] == 6 and s["wall_seconds"] > 0    # 6 -> 2×3 spec -> exactly 6 candidates, each in a container


# ---- CLI ------------------------------------------------------------------- #
def test_cli_bench_10k_writes_report(tmp_path):
    out = tmp_path / "bench.json"
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "bench",
                        "--profile", "10K", "--stages", "generator,sieve",
                        "--scratch", str(tmp_path), "--out", str(out)],
                       cwd=str(HERE), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["schema"] == bm.SCHEMA and rep["candidates"] == 10_000
    assert {s["stage"] for s in rep["stages"]} == {"generator", "sieve"}


def test_cli_bench_refuses_1b_without_allow_huge(tmp_path):
    r = subprocess.run([sys.executable, str(HERE / "bundle_run.py"), "bench",
                        "--profile", "1000000000", "--stages", "sieve", "--scratch", str(tmp_path)],
                       cwd=str(HERE), capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "never started automatically" in (r.stdout + r.stderr) or "ceiling" in (r.stdout + r.stderr)
    assert not (tmp_path / "benchmark.json").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
