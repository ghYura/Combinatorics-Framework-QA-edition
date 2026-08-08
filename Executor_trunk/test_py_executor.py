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

"""Targeted tests for py_executor's Handoff v2 manifest path (STEP 18):
one mocked v2 candidate, one legacy-handshake fallback case, and one
candidate-count mismatch that must block execution before any DB I/O
(run: `python3 test_py_executor.py`).

All cases run with --writeToDB false so no live Results DB is required --
read_manifest/read_handshake validate and resolve connection coordinates,
but `main` only calls `pg8000.dbapi.connect` when write_db is true.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"

_spec = importlib.util.spec_from_file_location("py_executor", PY_EXECUTOR)
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)

_wp_spec = importlib.util.spec_from_file_location("worker_pool", HERE / "worker_pool.py")
worker_pool = importlib.util.module_from_spec(_wp_spec)
_wp_spec.loader.exec_module(worker_pool)

_bp_spec = importlib.util.spec_from_file_location("backpressure", HERE / "backpressure.py")
backpressure = importlib.util.module_from_spec(_bp_spec)
_bp_spec.loader.exec_module(backpressure)


def _reader_sha256_of_lines(names):
    """Byte-for-byte reimplementation of Reader's HandoffManifestWriter.sha256OfLines
    (``for (String l : lines) md.update((l + "\\n").getBytes(UTF_8))``) -- the
    independent reference _sources_dir_digest must agree with."""
    md = hashlib.sha256()
    for n in names:
        md.update((n + "\n").encode("utf-8"))
    return md.hexdigest()


CANDIDATE_SOURCE = "FW_VAR = 0\n"
INSERT_SQL = "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);"  # 9 '?' -> placeholders=9 -> FW_VAR mode


class _FakeCursor:
    """Minimal pg8000-shaped cursor that records executes and (optionally) fails them."""
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.conn.executed.append(sql)
        if self.conn.fail_v2:
            raise RuntimeError("simulated results_v2 insert failure")
        self.rowcount = 1

    def close(self):
        pass


class _FakeConn:
    """Records commit/rollback so a test can prove the legacy+results_v2 transaction is atomic."""
    def __init__(self, fail_v2=False, fail_commit=False):
        self.executed, self.commits, self.rollbacks = [], 0, 0
        self.fail_v2, self.fail_commit = fail_v2, fail_commit

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("simulated commit failure")
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _write_candidate(srcdir: Path, name: str = "1_0_0.py") -> None:
    srcdir.mkdir(parents=True, exist_ok=True)
    (srcdir / name).write_text(CANDIDATE_SOURCE, encoding="utf-8")


def _write_sql_template(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "insert.sql").write_text(INSERT_SQL, encoding="utf-8")
    return d


def _manifest(run_id: str, srcdir: Path, candidate_count: int) -> dict:
    return {
        "protocol": "bundle.handoff/v2",
        "run_id": run_id,
        "language": "python",
        "candidate_transport": "loose-files",
        "candidate_count": candidate_count,
        "id_format": "<combi_id>_0_0",
        "sources": [{"kind": "dir", "path": str(srcdir)}],
        "result_target": {"host": "127.0.0.1", "port": 5432, "database": "testdb", "user": "postgres"},
        "result_schema_mode": "placeholders=9",
        "verdict_mode": "FW_VAR",
        "arguments": [],
        "shift": 1,
    }


def _run(args, env_extra=None):
    env = dict(os.environ)
    env["BUNDLE_RESULTS_DB_PASSWORD"] = "test-secret"
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(PY_EXECUTOR)] + args,
                          capture_output=True, text=True, env=env)


def test_manifest_v2_path_runs_one_mocked_candidate():
    # Deliberately omit -srcDirList: the manifest's single declared source is
    # the sole source of truth for the candidate dir to scan/execute -- this
    # must succeed without it (it's a redundant cross-check, not a dependency).
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_candidate(srcdir)
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-v2-1", srcdir, 1)), encoding="utf-8")
        result_file = td / "result.json"

        r = _run(["--manifest", str(manifest),
                  "-dirSqlTemplate", str(sqldir), "--writeToDB", "false",
                  "--failOnly", "false", "--resultFile", str(result_file)])

        assert r.returncode == 0, r.stdout + r.stderr
        assert "Handoff v2 manifest" in r.stdout
        assert "py_executor DONE: processed=1 pass=1 fail=0 broken=0 inserted=0" in r.stdout
        result = json.loads(result_file.read_text(encoding="utf-8"))
        assert result["processed"] == 1 and result["pass"] == 1
        assert result["manifest_protocol"] == "bundle.handoff/v2"
        assert result["candidate_count_reconciliation"] == {"declared": 1, "actual": 1}


def test_legacy_handshake_path_still_works_with_a_warning():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir = td / "candidates"
        _write_candidate(srcdir)
        url_dir = td / "resultsDbURL"; url_dir.mkdir()
        (url_dir / "resultsDbURL.properties").write_text(
            "jdbc:postgresql://127.0.0.1:5432/testdb?user=postgres&password=x\n", encoding="utf-8")
        sqldir = _write_sql_template(td / "sqlTemplate")
        argdir = td / "arguments"; argdir.mkdir()
        (argdir / "fwVar.shift").write_text("1\n", encoding="utf-8")

        r = _run(["-srcDirList", str(srcdir), "-dirResultsDbURL", str(url_dir),
                  "-dirSqlTemplate", str(sqldir), "-dirArguments", str(argdir),
                  "--writeToDB", "false", "--failOnly", "false"])

        assert r.returncode == 0, r.stdout + r.stderr
        assert "WARNING: no --manifest given" in r.stdout
        assert "py_executor DONE: processed=1 pass=1 fail=0 broken=0 inserted=0" in r.stdout


def test_manifest_candidate_count_mismatch_blocks_execution():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_candidate(srcdir)               # one file on disk ...
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-v2-2", srcdir, 2)), encoding="utf-8")  # ... manifest says 2

        r = _run(["--manifest", str(manifest), "-srcDirList", str(srcdir),
                  "-dirSqlTemplate", str(sqldir), "--writeToDB", "false", "--failOnly", "false"])

        assert r.returncode != 0
        assert "candidate_count=2" in (r.stdout + r.stderr)
        assert "found 1 *.py candidate file(s)" in (r.stdout + r.stderr)
        assert "py_executor DONE" not in r.stdout    # blocked before any candidate ran


def test_source_digest_matches_readers_sha256_of_lines():
    # _sources_dir_digest must be byte-for-byte compatible with Reader's
    # HandoffManifestWriter.sha256OfLines, or every real dual-written manifest
    # checksum is rejected. "\n".join(names) (no trailing "\n") would NOT match.
    names = ["1_0_0.py", "2_0_0.py", "10_0_0.py"]
    assert py_executor._sources_dir_digest(names) == _reader_sha256_of_lines(names)
    assert py_executor._sources_dir_digest(names) != hashlib.sha256(
        "\n".join(names).encode("utf-8")).hexdigest()


def test_manifest_checksum_mismatch_blocks_execution():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_candidate(srcdir)
        _write_sql_template(sqldir)
        m = _manifest("run-v2-3", srcdir, 1)
        m["sources"][0]["sha256"] = "0" * 64   # deliberately wrong digest
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(m), encoding="utf-8")

        r = _run(["--manifest", str(manifest), "-srcDirList", str(srcdir),
                  "-dirSqlTemplate", str(sqldir), "--writeToDB", "false", "--failOnly", "false"])

        assert r.returncode != 0
        assert "checksum mismatch" in (r.stdout + r.stderr)
        assert "py_executor DONE" not in r.stdout


def test_manifest_source_path_must_match_srcdirlist():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, other_dir, sqldir = td / "candidates", td / "elsewhere", td / "sqlTemplate"
        _write_candidate(srcdir)
        _write_candidate(other_dir)             # same content under a different path
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-v2-4", srcdir, 1)), encoding="utf-8")

        r = _run(["--manifest", str(manifest), "-srcDirList", str(other_dir),
                  "-dirSqlTemplate", str(sqldir), "--writeToDB", "false", "--failOnly", "false"])

        assert r.returncode != 0
        assert "does not match the manifest's source path" in (r.stdout + r.stderr)
        assert "py_executor DONE" not in r.stdout


def test_manifest_rejects_non_python_language():
    # py_executor only ever lists/runs `*.py` candidates (list_candidates).
    # A language="java" manifest could pass count/checksum reconciliation
    # against *.java files yet leave the run scanning 0 *.py files -- silently
    # producing processed=0 rather than failing loudly. Must be rejected up front.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        srcdir.mkdir(parents=True)
        (srcdir / "1_0_0.java").write_text("class C {}\n", encoding="utf-8")
        _write_sql_template(sqldir)
        m = _manifest("run-v2-5", srcdir, 1)
        m["language"] = "java"
        m["sources"][0]["path"] = str(srcdir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(m), encoding="utf-8")

        r = _run(["--manifest", str(manifest),
                  "-dirSqlTemplate", str(sqldir), "--writeToDB", "false", "--failOnly", "false"])

        assert r.returncode != 0
        assert "manifest language 'java'" in (r.stdout + r.stderr)
        assert "py_executor only runs" in (r.stdout + r.stderr)
        assert "py_executor DONE" not in r.stdout


def _write_corpus(srcdir, n):
    srcdir.mkdir(parents=True, exist_ok=True)
    for i in range(n):                                  # even → PASS, odd → DOMAIN_FAIL
        (srcdir / f"{100000 + i}_0_0.py").write_text(f"FW_VAR = {i % 2}\n", encoding="utf-8")


def test_worker_pool_dispatcher_matches_single_worker():
    """STEP 33: a 2-worker dispatched run yields the SAME aggregated outcome set as a single
    worker over the same corpus (deterministic id-hash partitioning; no duplicate/lost candidate)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_corpus(srcdir, 12)                       # 6 PASS + 6 DOMAIN_FAIL
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-wp", srcdir, 12)), encoding="utf-8")

        def run_with(workers, rf):
            return _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                         "--writeToDB", "false", "--failOnly", "false",
                         "--workers", str(workers), "--resultFile", str(rf)])

        rf1, rf2 = td / "r1.json", td / "r2.json"
        r1, r2 = run_with(1, rf1), run_with(2, rf2)
        assert r1.returncode == 0, r1.stdout + r1.stderr
        assert r2.returncode == 0, r2.stdout + r2.stderr
        a1, a2 = json.loads(rf1.read_text()), json.loads(rf2.read_text())
        assert a1["processed"] == 12 and a2["processed"] == 12
        assert a1["pass"] == a2["pass"] == 6 and a1["fail"] == a2["fail"] == 6
        assert a1["outcomes"] == a2["outcomes"]         # identical outcome set, 1 vs 2 workers
        assert a2.get("workers") == 2 and a2.get("crashed_workers") == []
        # the dispatcher still emits the scrapable DONE line the launcher reads
        assert "py_executor DONE: processed=12 pass=6 fail=6 broken=0 inserted=0" in r2.stdout


def test_worker_pool_workers_write_unique_output_files():
    """STEP 33 review fix #1: parallel workers must NOT overwrite one shared SQL dump --
    each worker writes py_executor_<workerIndex>.sql for its disjoint partition."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir, out2 = td / "candidates", td / "sqlTemplate", td / "out2"
        _write_corpus(srcdir, 12)
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-wp-files", srcdir, 12)), encoding="utf-8")

        r = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                  "--writeToDB", "false", "--failOnly", "false", "--writeFile", "true",
                  "-out2", str(out2), "--workers", "2", "--resultFile", str(td / "r.json")])
        assert r.returncode == 0, r.stdout + r.stderr
        f0, f1 = out2 / "py_executor_0.sql", out2 / "py_executor_1.sql"
        assert f0.is_file() and f1.is_file(), f"expected one file per worker, got {list(out2.iterdir())}"
        rows0 = [x for x in f0.read_text(encoding="utf-8").strip().split(",\n") if x]
        rows1 = [x for x in f1.read_text(encoding="utf-8").strip().split(",\n") if x]
        assert len(rows0) > 0 and len(rows1) > 0          # both workers contributed
        assert len(rows0) + len(rows1) == 12              # disjoint union == whole corpus, no overwrite


def test_worker_pool_resume_skips_completed_workers():
    """STEP 33 review fix #2: after a crash, re-running --workers N resumes ONLY the crashed
    workers -- a worker that already finished (checkpoint present) is NOT reprocessed, so the
    non-idempotent legacy Results are never duplicated."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_corpus(srcdir, 12)
        _write_sql_template(sqldir)
        run_id = "run-resume-skip"
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest(run_id, srcdir, 12)), encoding="utf-8")

        # Pre-seed worker 0's checkpoint with a SENTINEL, as if it had already completed.
        state_dir = manifest.resolve().parent / f".fw-workers-{run_id}-2"
        state_dir.mkdir(parents=True, exist_ok=True)
        sentinel = {"processed": 777, "pass": 700, "fail": 77, "broken": 0, "inserted": 777,
                    "timeout": 0, "infra_fail": 0, "completed_successfully": True,
                    "outcomes": {"PASS": 700, "DOMAIN_FAIL": 77},
                    "results_v2_write_counts": {"attempted": 777, "inserted": 777,
                                                "already_present": 0, "updated_selected": 0}}
        (state_dir / "worker-0.json").write_text(json.dumps(sentinel), encoding="utf-8")

        rf = td / "r.json"
        r = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                  "--writeToDB", "false", "--failOnly", "false", "--workers", "2", "--resultFile", str(rf)])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "resume" in r.stdout and "already complete" in r.stdout, r.stdout
        # worker 0 was NOT re-run: its checkpoint still holds the sentinel (not the real ~6).
        assert json.loads((state_dir / "worker-0.json").read_text())["processed"] == 777
        # aggregate == sentinel (worker 0, reused) + worker 1's real partition.
        n1 = sum(1 for i in range(12) if worker_pool.assign(f"{100000 + i}_0_0", 2) == 1)
        agg = json.loads(rf.read_text())
        assert agg["processed"] == 777 + n1, (agg["processed"], n1)


def test_worker_pool_failed_worker_with_json_is_rerun_on_resume():
    """STEP 33 review fix: a worker that WROTE a result JSON but exited NON-ZERO (here: a real
    FATAL Results-DB connect failure) leaves completed_successfully=False, so a later resume must
    RE-RUN it — never skip it as finished. A bare valid JSON is NOT proof of completion."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_corpus(srcdir, 12)
        _write_sql_template(sqldir)
        run_id = "run-failed-worker"
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest(run_id, srcdir, 12)), encoding="utf-8")

        # 1) A real worker pointed at an UNREACHABLE Results DB writes its result JSON and exits
        #    non-zero — the faithful "left a JSON but failed" case. Its checkpoint is NOT complete.
        state_dir = manifest.resolve().parent / f".fw-workers-{run_id}-2"
        state_dir.mkdir(parents=True, exist_ok=True)
        w0 = state_dir / "worker-0.json"
        m_bad = _manifest(run_id, srcdir, 12)
        m_bad["result_target"] = {"host": "127.0.0.1", "port": 1, "database": "x", "user": "postgres"}
        bad_manifest = td / "bad_manifest.json"
        bad_manifest.write_text(json.dumps(m_bad), encoding="utf-8")
        rfail = _run(["--manifest", str(bad_manifest), "-dirSqlTemplate", str(sqldir),
                      "--writeToDB", "true", "--failOnly", "false",
                      "--workerCount", "2", "--workerIndex", "0", "--resultFile", str(w0)])
        assert rfail.returncode != 0, rfail.stdout + rfail.stderr          # FATAL DB connect → non-zero
        assert w0.is_file(), "the failed worker must still have written its result JSON"
        assert json.loads(w0.read_text()).get("completed_successfully") is not True

        # 2) Resume via the dispatcher (--writeToDB false): worker 0's incomplete checkpoint must be
        #    REJECTED → worker 0 re-runs and overwrites it with a clean (completed) checkpoint.
        rf = td / "r.json"
        r = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                  "--writeToDB", "false", "--failOnly", "false", "--workers", "2", "--resultFile", str(rf)])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "already complete" not in r.stdout                          # the failed worker was NOT skipped
        w0_after = json.loads(w0.read_text())
        assert w0_after.get("completed_successfully") is True              # re-run produced a CLEAN checkpoint
        n0 = sum(1 for i in range(12) if worker_pool.assign(f"{100000 + i}_0_0", 2) == 0)
        assert w0_after["processed"] == n0                                 # real partition, not the failed leftover
        assert json.loads(rf.read_text())["processed"] == 12               # both partitions processed


def test_legacy_and_results_v2_commit_atomically():
    """STEP 33 review fix (partial-commit): legacy Results + results_v2 are persisted in ONE
    transaction with a SINGLE commit. A results_v2 failure (or the commit itself failing) rolls
    BOTH back -- the legacy inserts are NEVER committed separately, so a resume that re-runs the
    worker cannot duplicate already-committed legacy rows."""
    v2_rows = {"1_0_0": {"run_id": "r", "candidate_id": "1_0_0", "attempt": 1, "outcome": "PASS"},
               "2_0_0": {"run_id": "r", "candidate_id": "2_0_0", "attempt": 1, "outcome": "DOMAIN_FAIL"}}

    # results_v2 insert fails → nothing is committed (the legacy inserts are NOT left durable),
    # only a rollback. (The old code committed the legacy rows FIRST → this asserts the bug is gone.)
    bad = _FakeConn(fail_v2=True)
    try:
        py_executor.commit_legacy_and_v2(bad, "r", v2_rows)
        raised = False
    except Exception:
        raised = True
    assert raised
    assert bad.commits == 0, "a results_v2 failure must NOT leave the legacy inserts committed"
    assert bad.rollbacks >= 1

    # the combined commit itself fails → rollback, nothing persisted.
    bad2 = _FakeConn(fail_commit=True)
    try:
        py_executor.commit_legacy_and_v2(bad2, "r", v2_rows)
        committed = True
    except Exception:
        committed = False
    assert committed is False and bad2.commits == 0 and bad2.rollbacks >= 1

    # success → EXACTLY ONE commit covering legacy + results_v2, no rollback.
    good = _FakeConn()
    counts = py_executor.commit_legacy_and_v2(good, "r", v2_rows)
    assert good.commits == 1 and good.rollbacks == 0
    assert counts["attempted"] == 2 and counts["inserted"] == 2

    # no results_v2 (legacy-only run) → still exactly one commit, no v2 inserts.
    legacy_only = _FakeConn()
    py_executor.commit_legacy_and_v2(legacy_only, None, {})
    assert legacy_only.commits == 1 and legacy_only.executed == []


def test_executor_publishes_consumer_progress_to_backpressure():
    """STEP 34: with --backpressureDir the Executor publishes CONSUMER progress (note_consumed
    per candidate) so a producer (Reader) can bound how far ahead it runs. Works single-process
    and across dispatched workers (each writes its own consumed-<index>, summed by metrics)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        _write_corpus(srcdir, 12)
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-bp", srcdir, 12)), encoding="utf-8")

        bp1 = td / "bp1"
        r1 = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                   "--writeToDB", "false", "--failOnly", "false", "--backpressureDir", str(bp1)])
        assert r1.returncode == 0, r1.stdout + r1.stderr
        assert backpressure.Backpressure(bp1).metrics()["consumed"] == 12

        # 2 workers: the dispatcher passes --backpressureDir through; each worker writes its own
        # consumed-<index> counter, summed across workers by metrics().
        bp2 = td / "bp2"
        r2 = _run(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                   "--writeToDB", "false", "--failOnly", "false", "--workers", "2",
                   "--backpressureDir", str(bp2), "--resultFile", str(td / "r.json")])
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert backpressure.Backpressure(bp2).metrics()["consumed"] == 12


def _write_slow_corpus(srcdir, n, delay=0.05):
    srcdir.mkdir(parents=True, exist_ok=True)
    for i in range(n):                                  # slow enough that a mid-run cancel is observable
        (srcdir / f"{100000 + i}_0_0.py").write_text(
            f"import time\ntime.sleep({delay})\nFW_VAR = 0\n", encoding="utf-8")


def _popen(args, env_extra=None):
    env = dict(os.environ)
    env["BUNDLE_RESULTS_DB_PASSWORD"] = "test-secret"
    if env_extra:
        env.update(env_extra)
    return subprocess.Popen([sys.executable, str(PY_EXECUTOR)] + args,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)


def test_executor_stops_early_on_cancel():
    """STEP 34: the Executor must POLL the shared cancel and stop its candidate loop early — not
    process the whole corpus after cancel."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir, bpdir = td / "candidates", td / "sqlTemplate", td / "bp"
        _write_slow_corpus(srcdir, 20)
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-cancel", srcdir, 20)), encoding="utf-8")
        rf = td / "r.json"

        proc = _popen(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                       "--writeToDB", "false", "--failOnly", "false",
                       "--backpressureDir", str(bpdir), "--resultFile", str(rf)])
        time.sleep(0.35)                                       # let it process a few
        backpressure.Backpressure(bpdir).cancel()             # cancel mid-run
        out = proc.communicate(timeout=60)[0]
        assert proc.returncode == 0, out
        assert "CANCELLED" in out, out
        processed = json.loads(rf.read_text())["processed"]
        assert 1 <= processed < 20, f"expected early stop (1..19), processed={processed}\n{out}"


def test_cancel_stops_both_producer_and_executor():
    """STEP 34 integration smoke: a producer (synthetic, standing in for the Reader, using the same
    Backpressure coordinator) and the REAL Executor both watch one shared cancel flag and BOTH stop
    early when it is set."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir, bpdir = td / "candidates", td / "sqlTemplate", td / "bp"
        _write_slow_corpus(srcdir, 20)
        _write_sql_template(sqldir)
        bpdir.mkdir(parents=True, exist_ok=True)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-both", srcdir, 20)), encoding="utf-8")
        rf = td / "r.json"

        # Producer: admits against the Executor's published consumption (writer_id=0), bounded by
        # high=8, until cancelled. Runs in this test process, like the Reader would in its own.
        prod = backpressure.Backpressure(bpdir, high=8, writer_id="prod")
        produced = [0]
        stop_flag = [False]

        def producer():
            while not stop_flag[0] and produced[0] < 100000:
                if not prod.admit():                          # returns False on cancel
                    return
                produced[0] += 1

        tp = threading.Thread(target=producer); tp.start()
        proc = _popen(["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
                       "--writeToDB", "false", "--failOnly", "false",
                       "--backpressureDir", str(bpdir), "--resultFile", str(rf)])
        time.sleep(0.35)
        prod.cancel()                                          # ONE shared cancel for both sides
        out = proc.communicate(timeout=60)[0]
        stop_flag[0] = True
        tp.join(10)

        assert proc.returncode == 0, out
        # Executor stopped early:
        processed = json.loads(rf.read_text())["processed"]
        assert 1 <= processed < 20, f"Executor did not stop early, processed={processed}\n{out}"
        # Producer stopped early (was bounded by the slow Executor and then halted on cancel):
        assert not tp.is_alive(), "producer thread did not terminate on cancel"
        assert produced[0] < 100000, "producer ran away instead of stopping on cancel"
        assert prod.admit() is False, "admit() must keep returning False after cancel"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} tests passed")
