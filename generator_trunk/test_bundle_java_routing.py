#!/usr/bin/env python3
"""Focused tests for manifest-driven Java Executor routing in the Bundle."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bundle import stages
from bundle.config import BundleConfig
from bundle.errors import PreflightError, StageError
from bundle.process import CommandResult


@pytest.fixture(autouse=True)
def _stub_schema_capability_probe(monkeypatch):
    # Plan-1 Phase 3b pre-connect fencing runs at the start of stage_executor; these tests stub the
    # executor run with a dummy jar, so stub the capability probe too (the fencing itself is covered
    # in test_bundle_schema_capability.py).
    monkeypatch.setattr(stages, "verify_executor_schema_capability",
                        lambda cfg, language=None: {"results_v2_schema": {"version": 2}})


def _manifest(path: Path, src: Path, language="java") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "protocol": "bundle.handoff/v2",
        "run_id": "java-route-test",
        "language": language,
        "candidate_transport": "loose-files",
        "candidate_count": 2,
        "id_format": "<combi_id>_0_0",
        "sources": [{"kind": "dir", "path": str(src)}],
        "result_target": {
            "host": "127.0.0.1", "port": 5432,
            "database": "java_route_test", "user": "postgres",
        },
        "result_schema_mode": "placeholders=9",
        "verdict_mode": "FW_VAR",
        "custom_verdicts": [],
        "arguments": [],
        "shift": 1,
        "preprocess": None,
    }), encoding="utf-8")
    return path


def _result(returncode=0):
    return CommandResult(
        argv=(), display="", returncode=returncode,
        stdout="MainWatch: manifest corpus complete\n", stderr="",
        start=0.0, end=0.0, duration=0.0, timed_out=False,
    )


def test_java_manifest_routes_to_mainwatch_with_dependency_jars_and_full_verdict_mode(tmp_path):
    src = tmp_path / "src"
    hs = tmp_path / "handshake"
    jars = tmp_path / "jars"
    src.mkdir()
    jars.mkdir()
    for name in ("resultsDbURL", "sqlTemplate", "arguments", "runFirstOnce"):
        (hs / name).mkdir(parents=True)
    executor_jar = tmp_path / "Executor-fat.jar"
    executor_jar.write_bytes(b"jar")
    manifest = _manifest(hs / "handoff" / "manifest.json", src)
    summary = tmp_path / "executor-summary.json"
    captured = {}

    def fake_java(cmd, summary_path, timeout_seconds):
        captured["cmd"] = cmd
        captured["timeout"] = timeout_seconds
        Path(summary_path).write_text(json.dumps({
            "schema": "bundle.executor-summary/v1",
            "language": "java",
            "processed_count": 2,
            "sandbox_backend": None,
            "outcomes": {
                "PASS": 1, "DOMAIN_FAIL": 1, "BROKEN": 0,
                "TIMEOUT": 0, "INFRA_FAIL": 0, "SKIPPED": 0, "CANCELLED": 0,
            },
            "results_v2_write_counts": {
                "attempted": 2, "inserted": 2,
                "already_present": 0, "updated_selected": 0,
            },
        }), encoding="utf-8")
        return _result()

    cfg = BundleConfig(
        java_cmd="java-test", java_executor_jar=str(executor_jar),
        java_jars_dir=str(jars), executor_timeout_seconds=123.0,
    )
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 1 / fail 1", 0)):
        result = stages.stage_executor(
            src, hs, "java_route_test", 5432, cfg=cfg,
            manifest_path=manifest, run_id="java-route-test",
            summary_path=summary, language="java",
        )

    assert result == (2, 1, 1, 0, 2, 2, 0, 0, {
        "attempted": 2, "inserted": 2,
        "already_present": 0, "updated_selected": 0,
    })
    cmd = captured["cmd"]
    assert cmd[:3] == ["java-test", "-jar", str(executor_jar)]
    assert cmd[cmd.index("-dirJars") + 1] == str(jars)
    assert cmd[cmd.index("-manifest") + 1] == str(manifest)
    assert cmd[cmd.index("-out2") + 1] == str(tmp_path)
    assert cmd[cmd.index("-failOnly") + 1] == "false"
    assert cmd[cmd.index("-exitWhenComplete") + 1] == "true"
    assert captured["timeout"] == 123.0


def test_java_summary_is_read_from_out2_fixed_name_not_summary_path_basename(tmp_path):
    """Seam fix: MainWatch writes the FIXED name executor-summary.json into -out2.
    The launcher must read THAT file, derived from out2 (= summary_path's parent),
    not summary_path's basename -- otherwise a differently-named summary_path makes
    the launcher look for a file MainWatch never wrote."""
    src = tmp_path / "src"; src.mkdir()
    hs = tmp_path / "handshake"
    for name in ("resultsDbURL", "sqlTemplate", "arguments", "runFirstOnce"):
        (hs / name).mkdir(parents=True)
    jars = tmp_path / "jars"; jars.mkdir()
    executor_jar = tmp_path / "Executor-fat.jar"; executor_jar.write_bytes(b"jar")
    manifest = _manifest(hs / "handoff" / "manifest.json", src)
    odd_summary = tmp_path / "out" / "caller-chose-this-name.json"  # NOT executor-summary.json

    def fake_java(cmd, summary_path, timeout_seconds):
        # the launcher must hand us out2/executor-summary.json regardless of the basename above
        assert Path(summary_path).name == "executor-summary.json", summary_path
        assert cmd[cmd.index("-out2") + 1] == str(Path(summary_path).parent)
        Path(summary_path).write_text(json.dumps({
            "schema": "bundle.executor-summary/v1", "processed_count": 2,
            "outcomes": {"PASS": 2, "DOMAIN_FAIL": 0, "BROKEN": 0, "TIMEOUT": 0,
                          "INFRA_FAIL": 0, "SKIPPED": 0, "CANCELLED": 0},
            "results_v2_write_counts": {"attempted": 2, "inserted": 2,
                                         "already_present": 0, "updated_selected": 0},
        }), encoding="utf-8")
        return _result()

    cfg = BundleConfig(java_executor_jar=str(executor_jar), java_jars_dir=str(jars))
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 2 / fail 0", 0)):
        result = stages.stage_executor(
            src, hs, "db", 5432, cfg=cfg, manifest_path=manifest,
            run_id="java-route-test", summary_path=odd_summary, language="java")
    assert result[0] == 2 and result[1] == 2   # processed, pass


def test_manifest_language_is_authoritative_and_mismatch_fails_before_launch(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    manifest = _manifest(tmp_path / "handoff" / "manifest.json", src, language="java")
    try:
        stages._executor_language(manifest, "python")
        assert False, "expected a language mismatch to fail closed"
    except StageError as exc:
        assert "language mismatch" in str(exc)


def test_java_without_handoff_manifest_is_rejected(tmp_path):
    try:
        stages.stage_executor(
            tmp_path / "src", tmp_path / "handshake", "db", 5432,
            cfg=BundleConfig(), language="java",
        )
        assert False, "expected Java legacy handoff to be rejected"
    except StageError as exc:
        assert "requires a validated Handoff v2 manifest" in str(exc)


def test_java_stress_and_legacy_handoff_are_rejected_in_preflight(tmp_path):
    core = tmp_path / "core.jar"
    reader = tmp_path / "reader.jar"
    core.write_bytes(b"jar")
    reader.write_bytes(b"jar")
    cfg = BundleConfig(core_jar=str(core), reader_jar=str(reader))

    for mode, legacy, expected in (
        ("stress", False, "Python-specific"),
        ("verdict", True, "require Handoff v2"),
    ):
        args = SimpleNamespace(lang="java", mode=mode, legacy_handoff=legacy)
        try:
            stages.preflight(args, cfg)
            assert False, "expected an unsupported Java routing combination to fail in preflight"
        except PreflightError as exc:
            assert expected in str(exc)


def test_executor_compiler_pins_backend_via_jvm_property(tmp_path):
    """--executor-compiler / cfg.executor_compiler must inject -Dfw.exec.compiler=<x>
    BEFORE -jar so MainWatch pins the backend; an invalid value fails closed."""
    src = tmp_path / "src"; src.mkdir()
    hs = tmp_path / "handshake"
    for name in ("resultsDbURL", "sqlTemplate", "arguments", "runFirstOnce"):
        (hs / name).mkdir(parents=True)
    jars = tmp_path / "jars"; jars.mkdir()
    executor_jar = tmp_path / "Executor-fat.jar"; executor_jar.write_bytes(b"jar")
    manifest = _manifest(hs / "handoff" / "manifest.json", src)
    summary = tmp_path / "executor-summary.json"
    captured = {}

    def fake_java(cmd, summary_path, timeout_seconds):
        captured["cmd"] = cmd
        Path(summary_path).write_text(json.dumps({
            "schema": "bundle.executor-summary/v1", "processed_count": 2,
            "outcomes": {"PASS": 2, "DOMAIN_FAIL": 0, "BROKEN": 0, "TIMEOUT": 0,
                          "INFRA_FAIL": 0, "SKIPPED": 0, "CANCELLED": 0},
            "results_v2_write_counts": {"attempted": 2, "inserted": 2,
                                         "already_present": 0, "updated_selected": 0},
        }), encoding="utf-8")
        return _result()

    cfg = BundleConfig(java_executor_jar=str(executor_jar), java_jars_dir=str(jars),
                       executor_compiler="janino")
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 2 / fail 0", 0)):
        stages.stage_executor(src, hs, "db", 5432, cfg=cfg, manifest_path=manifest,
                              run_id="java-route-test", summary_path=summary, language="java")
    cmd = captured["cmd"]
    assert "-Dfw.exec.compiler=janino" in cmd, cmd
    assert cmd.index("-Dfw.exec.compiler=janino") < cmd.index("-jar"), cmd  # before -jar

    bad = BundleConfig(java_executor_jar=str(executor_jar), java_jars_dir=str(jars),
                       executor_compiler="gcj")
    try:
        stages.stage_executor(src, hs, "db", 5432, cfg=bad, manifest_path=manifest,
                              run_id="x", summary_path=summary, language="java")
        assert False, "expected an invalid executor_compiler to fail closed"
    except StageError as exc:
        assert "invalid executor_compiler" in str(exc)


def test_java_with_analyzer_is_supported_in_preflight(tmp_path):
    """Plan-1 3c: Java + --analyzer is now SUPPORTED. MainWatch harvests the Analyzer K=V corpus
    in-sandbox (-metricsFile: the candidate's TAIL emits its app= line, MainWatch writes the corpus
    in the same _write_metrics_corpus format), so preflight must NO LONGER fail closed on an
    analyzer block for a Java run. (Later preflight checks -- e.g. a missing Java jar -- may still
    fire; this test asserts only that the analyzer-specific refusal is gone.)"""
    core = tmp_path / "core.jar"; core.write_bytes(b"jar")
    reader = tmp_path / "reader.jar"; reader.write_bytes(b"jar")
    cfg = BundleConfig(core_jar=str(core), reader_jar=str(reader))
    args = SimpleNamespace(lang="java", mode="verdict", legacy_handoff=False,
                           analyzer="bugs_found:max")
    try:
        stages.preflight(args, cfg)
    except PreflightError as exc:
        # any remaining failure must NOT be the lifted analyzer refusal
        assert "support the Analyzer" not in str(exc), exc
        assert "metrics-harvest transport" not in str(exc), exc


def test_java_executor_threads_metrics_file_when_corpus_requested(tmp_path):
    """Plan-1 3c: when the launcher passes metrics_path, the Java branch must thread it to MainWatch
    as `-metricsFile <path>` (mirrors the Python --metricsFile wiring), so MainWatch harvests the
    corpus from THIS sandboxed run instead of a host re-run. When metrics_path is None, the flag is
    absent (verdict-only run)."""
    src = tmp_path / "src"; src.mkdir()
    hs = tmp_path / "handshake"
    for name in ("resultsDbURL", "sqlTemplate", "arguments", "runFirstOnce"):
        (hs / name).mkdir(parents=True)
    jars = tmp_path / "jars"; jars.mkdir()
    executor_jar = tmp_path / "Executor-fat.jar"; executor_jar.write_bytes(b"jar")
    manifest = _manifest(hs / "handoff" / "manifest.json", src)
    summary = tmp_path / "executor-summary.json"
    corpus = tmp_path / "metrics.kv"
    captured = {}

    def fake_java(cmd, summary_path, timeout_seconds):
        captured["cmd"] = cmd
        Path(summary_path).write_text(json.dumps({
            "schema": "bundle.executor-summary/v1", "processed_count": 2,
            "outcomes": {"PASS": 2, "DOMAIN_FAIL": 0, "BROKEN": 0, "TIMEOUT": 0,
                          "INFRA_FAIL": 0, "SKIPPED": 0, "CANCELLED": 0},
            "results_v2_write_counts": {"attempted": 2, "inserted": 2,
                                         "already_present": 0, "updated_selected": 0},
        }), encoding="utf-8")
        return _result()

    cfg = BundleConfig(java_executor_jar=str(executor_jar), java_jars_dir=str(jars))
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 2 / fail 0", 0)):
        stages.stage_executor(src, hs, "db", 5432, cfg=cfg, manifest_path=manifest,
                              run_id="java-route-test", summary_path=summary,
                              metrics_path=corpus, language="java")
    cmd = captured["cmd"]
    assert "-metricsFile" in cmd, cmd
    assert cmd[cmd.index("-metricsFile") + 1] == str(corpus), cmd

    # metrics_path=None (verdict-only) -> no -metricsFile flag
    captured.clear()
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 2 / fail 0", 0)):
        stages.stage_executor(src, hs, "db", 5432, cfg=cfg, manifest_path=manifest,
                              run_id="java-route-test", summary_path=summary,
                              metrics_path=None, language="java")
    assert "-metricsFile" not in captured["cmd"], captured["cmd"]


def test_java_executor_threads_repeat_flags_for_local_metrics_kgt1(tmp_path):
    """Plan-1 3c sub-increment 2: the Java branch threads the MainWatch repeat flags
    (-repeat/-repeatPolicy/-repeatScope/-envId) for a local/metrics K>1 cfg, mirroring the Python
    --repeat wiring. K=1 emits no repeat flags (the unchanged single-shot path). The launcher gate
    (cli._check_budgets) still fences Java K>1 upstream -- this asserts only the executor-side wiring."""
    src = tmp_path / "src"; src.mkdir()
    hs = tmp_path / "handshake"
    for name in ("resultsDbURL", "sqlTemplate", "arguments", "runFirstOnce"):
        (hs / name).mkdir(parents=True)
    jars = tmp_path / "jars"; jars.mkdir()
    executor_jar = tmp_path / "Executor-fat.jar"; executor_jar.write_bytes(b"jar")
    manifest = _manifest(hs / "handoff" / "manifest.json", src)
    summary = tmp_path / "executor-summary.json"
    corpus = tmp_path / "metrics.kv"
    captured = {}

    def fake_java(cmd, summary_path, timeout_seconds):
        captured["cmd"] = cmd
        Path(summary_path).write_text(json.dumps({
            "schema": "bundle.executor-summary/v1", "processed_count": 2,
            "outcomes": {"PASS": 2, "DOMAIN_FAIL": 0, "BROKEN": 0, "TIMEOUT": 0,
                          "INFRA_FAIL": 0, "SKIPPED": 0, "CANCELLED": 0},
            "results_v2_write_counts": {"attempted": 2, "inserted": 2,
                                         "already_present": 0, "updated_selected": 0},
        }), encoding="utf-8")
        return _result()

    k3 = BundleConfig(java_executor_jar=str(executor_jar), java_jars_dir=str(jars),
                      repeat_each_candidate=3, repeat_policy="local", repeat_scope="metrics")
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 2 / fail 0", 0)):
        stages.stage_executor(src, hs, "db", 5432, cfg=k3, manifest_path=manifest,
                              run_id="rr", summary_path=summary, metrics_path=corpus, language="java")
    cmd = captured["cmd"]
    assert cmd[cmd.index("-repeat") + 1] == "3", cmd
    assert cmd[cmd.index("-repeatPolicy") + 1] == "local", cmd
    assert cmd[cmd.index("-repeatScope") + 1] == "metrics", cmd
    assert cmd[cmd.index("-envId") + 1] == "local:rr", cmd

    # K=1 -> no repeat flags
    captured.clear()
    k1 = BundleConfig(java_executor_jar=str(executor_jar), java_jars_dir=str(jars))
    with patch.object(stages, "_run_java_executor", fake_java), \
         patch.object(stages, "psql", lambda *a, **k: ("2 / pass 2 / fail 0", 0)):
        stages.stage_executor(src, hs, "db", 5432, cfg=k1, manifest_path=manifest,
                              run_id="rr", summary_path=summary, metrics_path=corpus, language="java")
    assert "-repeat" not in captured["cmd"], captured["cmd"]
