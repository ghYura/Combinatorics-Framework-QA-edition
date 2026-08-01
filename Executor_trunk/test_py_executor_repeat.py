#!/usr/bin/env python3
"""Repeat executor tests: fail-closed options, raw identity, and real K-loop behavior."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("py_executor_repeat", HERE / "py_executor.py")
pyx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pyx)


def test_repeat_options_fail_closed_and_preserve_k1_topology():
    assert pyx.resolve_repeat_options({
        "repeat": "1", "repeatPolicy": "nested", "repeatScope": "all"
    }) == (1, "nested", "all")
    # local/metrics K>1 (the verified path) and local/all K>1 (every sample a full verdict) are accepted.
    assert pyx.resolve_repeat_options({
        "repeat": "3", "repeatPolicy": "local", "repeatScope": "metrics", "metricsFile": "m.kv"
    }) == (3, "local", "metrics")
    assert pyx.resolve_repeat_options({
        "repeat": "3", "repeatPolicy": "local", "repeatScope": "all"
    }) == (3, "local", "all")            # all-scope does NOT require --metricsFile (verdicts are the output)
    with pytest.raises(SystemExit, match="only"):
        pyx.resolve_repeat_options({
            "repeat": "2", "repeatPolicy": "disperse", "repeatScope": "metrics",
            "metricsFile": "metrics.kv",
        })
    with pytest.raises(SystemExit, match="metricsFile"):
        pyx.resolve_repeat_options({"repeat": "2"})
    with pytest.raises(SystemExit, match="1024"):
        pyx.resolve_repeat_options({"repeat": "1025", "metricsFile": "metrics.kv"})
    with pytest.raises(SystemExit, match="integer"):
        pyx.resolve_repeat_options({"repeat": "1.5"})


_SYNTH_CANDIDATE = (
    "import os\n"
    "_cf = os.environ['FW_COUNTER_FILE']\n"
    "try:\n"
    "    n = int(open(_cf).read() or '0')\n"
    "except OSError:\n"
    "    n = 0\n"
    "n += 1\n"
    "open(_cf, 'w').write(str(n))\n"
    "FW_VAR = 0\n"
    "FW_CUSTOM_VAR = 0\n"
    "print(f'app=synth FW_VAR=0 latency_ms={n * 10}')\n"
)


def _measure(tmp_path, candidate_text, k, name="counter.txt"):
    candidate = tmp_path / "1_0_0.py"
    candidate.write_text(candidate_text)
    counter = tmp_path / name
    old = os.environ.get("FW_COUNTER_FILE")
    os.environ["FW_COUNTER_FILE"] = str(counter)
    try:
        result = pyx.measure_metric_repeated(
            sys.executable, candidate, [], None, None, k)
    finally:
        if old is None:
            os.environ.pop("FW_COUNTER_FILE", None)
        else:
            os.environ["FW_COUNTER_FILE"] = old
    return result, counter


def test_measure_metric_repeated_retains_five_raw_samples(tmp_path):
    (outcome, fw, _fwc, measurements), counter = _measure(
        tmp_path, _SYNTH_CANDIDATE, 5)
    assert outcome is None and fw == 0
    assert int(counter.read_text()) == 5
    assert [m["repeat_idx"] for m in measurements] == [0, 1, 2, 3, 4]
    assert [m["metric_line"].split("latency_ms=")[1] for m in measurements] == [
        "10", "20", "30", "40", "50"]
    assert all(m["outcome"] is None and m["duration_ms"] >= 0 for m in measurements)


def test_measure_metric_repeated_k1_is_single_measurement(tmp_path):
    (outcome, _fw, _fwc, measurements), counter = _measure(
        tmp_path, _SYNTH_CANDIDATE, 1, "counter-k1.txt")
    assert outcome is None and len(measurements) == 1
    assert int(counter.read_text()) == 1


def test_metric_only_failure_is_retained_and_later_repeats_continue(tmp_path):
    candidate = _SYNTH_CANDIDATE.replace(
        "FW_VAR = 0\n",
        "if n == 2:\n    raise SystemExit(7)\nFW_VAR = 0\n")
    (outcome, _fw, _fwc, measurements), counter = _measure(
        tmp_path, candidate, 3, "counter-failure.txt")
    assert outcome is None and int(counter.read_text()) == 3
    assert [m["outcome"] for m in measurements] == [None, pyx.Outcome.BROKEN, None]
    assert [m["metric_line"] is not None for m in measurements] == [True, False, True]


def test_canonical_failure_stops_further_side_effecting_invocations(tmp_path):
    candidate = (
        "import os\n"
        "p = os.environ['FW_COUNTER_FILE']\n"
        "open(p, 'w').write('1')\n"
        "raise SystemExit(9)\n"
    )
    (outcome, _fw, _fwc, measurements), counter = _measure(
        tmp_path, candidate, 5, "counter-canonical-failure.txt")
    assert outcome == pyx.Outcome.BROKEN
    assert counter.read_text() == "1"
    assert len(measurements) == 1 and measurements[0]["metric_line"] is None


def test_repeat_corpus_preserves_raw_identity_and_values(tmp_path):
    out = tmp_path / "metrics.kv"
    observations = {
        ("7_0_0", 0, "host-a"): ("7_0_0.py", "app=x FW_VAR=0 latency_ms=10"),
        ("7_0_0", 1, "host-a"): ("7_0_0.py", "app=x FW_VAR=0 latency_ms=90"),
    }
    assert pyx._write_metrics_corpus(out, observations, "run-r") == 2
    assert out.read_text().splitlines() == [
        "candidate_id=7_0_0 source_ref=7_0_0.py run_id=run-r repeat_idx=0 env_id=host-a "
        "app=x FW_VAR=0 latency_ms=10",
        "candidate_id=7_0_0 source_ref=7_0_0.py run_id=run-r repeat_idx=1 env_id=host-a "
        "app=x FW_VAR=0 latency_ms=90",
    ]


def test_k1_corpus_byte_parity_with_java_mainwatch(tmp_path):
    """Plan-1 3c: the K=1 (string-key) corpus py_executor._write_metrics_corpus emits is byte-for-byte
    what the Java MainWatch harvest writer produces -- the Java harness
    Executor_trunk/src/main/java/com/company/MetricsHarvestCorpusTest.java asserts the SAME golden
    bytes for the SAME inputs. So a Java and a Python run feed the Analyzer interchangeable corpora.
    Pins: per-line provenance prefix, run_id token, deterministic code-point sort by candidate_id
    ('_' (0x5F) sorts AFTER digits -> "10_0_0" < "1_0_0" < "9_0_0"), and the trailing newline."""
    out = tmp_path / "metrics.kv"
    observations = {                                  # K=1 => string keys (not repeat-aware tuples)
        "9_0_0": ("9_0_0.java", "app=perf_opt_java algo=simd threads=8 batch=256 cache=large "
                                "latency_ms=4.648 throughput_rps=1548.9 memory_mb=244.0 FW_VAR=0"),
        "10_0_0": ("10_0_0.java", "app=perf_opt_java algo=naive threads=2 batch=64 cache=large "
                                  "latency_ms=33.024 throughput_rps=54.5 memory_mb=114.0 FW_VAR=0"),
        "1_0_0": ("1_0_0.java", "app=perf_opt_java algo=naive threads=1 batch=16 cache=small "
                                "latency_ms=100.000 throughput_rps=9.0 memory_mb=18.5 FW_VAR=0"),
    }
    assert pyx._write_metrics_corpus(out, observations, "run-XYZ") == 3
    golden = (
        "candidate_id=10_0_0 source_ref=10_0_0.java run_id=run-XYZ app=perf_opt_java algo=naive "
        "threads=2 batch=64 cache=large latency_ms=33.024 throughput_rps=54.5 memory_mb=114.0 FW_VAR=0\n"
        "candidate_id=1_0_0 source_ref=1_0_0.java run_id=run-XYZ app=perf_opt_java algo=naive "
        "threads=1 batch=16 cache=small latency_ms=100.000 throughput_rps=9.0 memory_mb=18.5 FW_VAR=0\n"
        "candidate_id=9_0_0 source_ref=9_0_0.java run_id=run-XYZ app=perf_opt_java algo=simd "
        "threads=8 batch=256 cache=large latency_ms=4.648 throughput_rps=1548.9 memory_mb=244.0 FW_VAR=0\n"
    )
    assert out.read_text(encoding="utf-8") == golden


def test_repeat_cli_writes_three_raw_samples_and_runtime_accounting(tmp_path):
    source_dir = tmp_path / "candidates"
    sql_dir = tmp_path / "sql"
    source_dir.mkdir()
    sql_dir.mkdir()
    candidate = source_dir / "1_0_0.py"
    candidate.write_text(_SYNTH_CANDIDATE)
    (sql_dir / "insert.sql").write_text(
        "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "protocol": "bundle.handoff/v2",
        "run_id": "repeat-cli",
        "language": "python",
        "candidate_transport": "loose-files",
        "candidate_count": 1,
        "id_format": "<combi_id>_0_0",
        "sources": [{"kind": "dir", "path": str(source_dir)}],
        "result_target": {
            "host": "127.0.0.1", "port": 5432,
            "database": "unused", "user": "postgres"},
        "result_schema_mode": "placeholders=9",
        "verdict_mode": "FW_VAR",
        "arguments": [],
        "shift": 1,
    }))
    metrics = tmp_path / "metrics.kv"
    result_file = tmp_path / "result.json"
    counter = tmp_path / "cli-counter.txt"
    env = dict(os.environ)
    env.update({
        "BUNDLE_RESULTS_DB_PASSWORD": "unused",
        "FW_COUNTER_FILE": str(counter),
    })
    completed = subprocess.run([
        sys.executable, str(HERE / "py_executor.py"),
        "--manifest", str(manifest),
        "-dirSqlTemplate", str(sql_dir),
        "--writeToDB", "false",
        "--failOnly", "false",
        "--metricsFile", str(metrics),
        "--resultFile", str(result_file),
        "--repeat", "3",
        "--repeatPolicy", "local",
        "--repeatScope", "metrics",
        "--envId", "host-z",
    ], capture_output=True, text=True, env=env)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "wrote 3 raw sample line(s)" in completed.stdout
    lines = metrics.read_text().splitlines()
    assert len(lines) == 3
    assert [f"repeat_idx={idx}" in lines[idx] for idx in range(3)] == [True] * 3
    assert all("env_id=host-z" in line for line in lines)
    result = json.loads(result_file.read_text())
    assert result["processed"] == 1
    assert result["repeat_measurements"] == {
        "opportunities": 3,
        "invocations": 3,
        "metric_rows": 3,
        "missing_measurements": 0,
        "failed_invocations": 0,
        "unattempted_after_canonical_failure": 0,
    }


def test_worker_merge_keys_by_full_repeat_identity(tmp_path):
    part0 = tmp_path / "metrics-0.kv"
    part1 = tmp_path / "metrics-1.kv"
    part0.write_text(
        "candidate_id=c repeat_idx=0 env_id=e app=x FW_VAR=0 latency_ms=10\n"
        "candidate_id=c repeat_idx=1 env_id=e app=x FW_VAR=0 latency_ms=20\n")
    part1.write_text(
        "candidate_id=d repeat_idx=0 env_id=e app=x FW_VAR=0 latency_ms=30\n")
    out = tmp_path / "merged.kv"
    assert pyx.merge_worker_metrics([part0, part1], out) == 3
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    assert "candidate_id=c repeat_idx=0" in lines[0]
    assert "candidate_id=c repeat_idx=1" in lines[1]


def test_worker_summary_aggregates_repeat_runtime_tallies():
    aggregate = pyx.worker_pool.aggregate_summaries([
        {"processed": 1, "repeat_measurements": {
            "opportunities": 3, "invocations": 3, "metric_rows": 2,
            "missing_measurements": 1, "failed_invocations": 1,
            "unattempted_after_canonical_failure": 0}},
        {"processed": 1, "repeat_measurements": {
            "opportunities": 3, "invocations": 1, "metric_rows": 0,
            "missing_measurements": 3, "failed_invocations": 1,
            "unattempted_after_canonical_failure": 2}},
    ])
    assert aggregate["repeat_measurements"] == {
        "opportunities": 6, "invocations": 4, "metric_rows": 2,
        "missing_measurements": 4, "failed_invocations": 2,
        "unattempted_after_canonical_failure": 2,
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
