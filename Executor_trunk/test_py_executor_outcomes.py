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

"""Targeted harness for the canonical outcome model (STEP 21).

Exercises every outcome py_executor can produce on the candidate-execution
path -- PASS / DOMAIN_FAIL / BROKEN / TIMEOUT / INFRA_FAIL -- plus the two
infrastructure boundaries flagged in review as able to bypass classification
and exit without a completion summary: Results-DB connect() and the
per-candidate cur.execute() (run: `python3 test_py_executor_outcomes.py`).

SKIPPED/CANCELLED are not exercised here: py_executor's cold-start/watch loop
never produces them (they belong to the resume/cancel paths of STEP 24/25).
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"

_spec = importlib.util.spec_from_file_location("py_executor_outcomes", PY_EXECUTOR)
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)

Outcome = py_executor.Outcome

INSERT_SQL = "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);"  # 9 '?' -> FW_VAR mode


def test_secure_python_preprocess_boundary(tmp_path):
    java_stub = tmp_path / "runmefirstonce.first"
    java_stub.write_text(
        "class RunMeFirstOnce { public static void main(String[] args){} }",
        encoding="utf-8",
    )
    resolved, note = py_executor.resolve_preprocess_for_policy(
        java_stub,
        {"trusted": False, "backend": "container"},
    )
    assert resolved is None
    assert "ignored Java" in note

    python_preprocess = tmp_path / "patch.py"
    python_preprocess.write_text("print('trusted-only preprocessor')\n")
    with pytest.raises(ValueError, match="refuses host-side"):
        py_executor.resolve_preprocess_for_policy(
            python_preprocess,
            {"trusted": False, "backend": "container"},
        )
    with pytest.raises(ValueError, match="refuses host-side"):
        py_executor.resolve_preprocess_for_policy(python_preprocess, {})
    resolved, note = py_executor.resolve_preprocess_for_policy(
        python_preprocess,
        {"trusted": True, "backend": "local"},
    )
    assert resolved == python_preprocess and note is None


def _manifest(run_id: str, srcdir: Path, candidate_count: int, port: int = 5432) -> dict:
    return {
        "protocol": "bundle.handoff/v2",
        "run_id": run_id,
        "language": "python",
        "candidate_transport": "loose-files",
        "candidate_count": candidate_count,
        "id_format": "<combi_id>_0_0",
        "sources": [{"kind": "dir", "path": str(srcdir)}],
        "result_target": {"host": "127.0.0.1", "port": port, "database": "testdb", "user": "postgres"},
        "result_schema_mode": "placeholders=9",
        "verdict_mode": "FW_VAR",
        "arguments": [],
        "shift": 1,
    }


def _write_sql_template(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "insert.sql").write_text(INSERT_SQL, encoding="utf-8")
    return d


def _run(args, env_extra=None):
    env = dict(os.environ)
    env["BUNDLE_RESULTS_DB_PASSWORD"] = "test-secret"
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(PY_EXECUTOR)] + args,
                          capture_output=True, text=True, env=env)


# --------------------- direct run_candidate classification ------------------- #
# run_candidate is the single point where py_executor turns a subprocess result
# into an outcome (Outcome.BROKEN / Outcome.TIMEOUT / Outcome.INFRA_FAIL, or
# `(None, fw, fwc)` for the caller to derive PASS/DOMAIN_FAIL from the verdict).
# Exercised directly -- one candidate per outcome -- rather than via a full run.
def test_run_candidate_pass_and_domain_fail():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        passed = td / "1_0_0.py"; passed.write_text("FW_VAR = 0\n", encoding="utf-8")
        failed = td / "2_0_0.py"; failed.write_text("FW_VAR = 1\n", encoding="utf-8")

        infra_outcome, fw, fwc = py_executor.run_candidate(sys.executable, passed, [])
        assert infra_outcome is None and fw == 0   # caller derives PASS from verdict==0

        infra_outcome, fw, fwc = py_executor.run_candidate(sys.executable, failed, [])
        assert infra_outcome is None and fw == 1   # caller derives DOMAIN_FAIL from verdict!=0


def test_run_candidate_broken_on_empty_file_and_missing_marker():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        empty = td / "1_0_0.py"; empty.write_text("", encoding="utf-8")
        crashes = td / "2_0_0.py"; crashes.write_text("raise RuntimeError('boom')\n", encoding="utf-8")

        assert py_executor.run_candidate(sys.executable, empty, []) == (Outcome.BROKEN, None, None)
        assert py_executor.run_candidate(sys.executable, crashes, []) == (Outcome.BROKEN, None, None)


def test_run_candidate_timeout_and_infra_fail_on_subprocess_errors():
    """The 20s per-candidate timeout and OS-level spawn failures are not
    practical to trigger for real in a narrow harness -- substitute the exact
    exceptions `subprocess.run` raises for them (TimeoutExpired / OSError) and
    verify run_candidate maps each to its canonical outcome, not to BROKEN."""
    import subprocess as sp
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        target = td / "1_0_0.py"; target.write_text("FW_VAR = 0\n", encoding="utf-8")

        orig_run = py_executor.subprocess.run

        def raise_timeout(cmd, **kw):
            raise sp.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout"))

        def raise_oserror(cmd, **kw):
            raise OSError("spawn failed (simulated ENOMEM)")

        py_executor.subprocess.run = raise_timeout
        try:
            assert py_executor.run_candidate(sys.executable, target, []) == (Outcome.TIMEOUT, None, None)
        finally:
            py_executor.subprocess.run = orig_run

        py_executor.subprocess.run = raise_oserror
        try:
            assert py_executor.run_candidate(sys.executable, target, []) == (Outcome.INFRA_FAIL, None, None)
        finally:
            py_executor.subprocess.run = orig_run


# ------------------ end-to-end: DB infrastructure boundaries ----------------- #
# Review finding: connect()/execute()/commit() bypassed classification and could
# end the process without an INFRA_FAIL count or a completion summary at all.
# These run the real script as a subprocess against a port nothing listens on,
# so pg8000.dbapi.connect raises for real -- no DB, no mocking required.
_DEAD_PORT = 1  # privileged/unassigned; "connection refused" practically guaranteed

def test_db_connect_failure_is_fatal_with_zero_processed_and_still_emits_summary():
    """A connect failure happens before any candidate is attempted -- it is not
    a per-candidate INFRA_FAIL outcome (there is no candidate to classify), it
    is a FATAL precondition failure: processed stays 0, every outcome bucket
    stays 0 (so processed == sum(outcomes) still holds, see executor_processed_
    eq_sum), and the always-CRITICAL/untolerable executor_processed_positive
    invariant is what fails the run -- not a tolerable INFRA_FAIL count (review
    finding: counting it as INFRA_FAIL produced processed=0 != sum(outcomes)=1
    and let `--executor-tolerate-outcomes=INFRA_FAIL` paper over "nothing ran")."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        srcdir.mkdir(parents=True)
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-infra-1", srcdir, 0, port=_DEAD_PORT)), encoding="utf-8")
        result_file = td / "result.json"

        r = _run(["--manifest", str(manifest),
                  "-dirSqlTemplate", str(sqldir), "--writeToDB", "true",
                  "--failOnly", "false", "--resultFile", str(result_file)])

        out = r.stdout + r.stderr
        assert r.returncode != 0, out
        assert "FATAL -- could not connect to Results DB" in out
        assert "0 candidates attempted" in out
        # the process must still report -- not vanish mid-stream (review finding)
        assert "py_executor DONE: processed=0 pass=0 fail=0 broken=0 inserted=0" in out
        assert "py_executor OUTCOMES:" in out and "infra_fail=0" in out
        result = json.loads(result_file.read_text(encoding="utf-8"))
        assert result["outcomes"]["INFRA_FAIL"] == 0
        assert result["processed"] == 0


class _FakeCursor:
    def __init__(self, fail_on_execute, fail_on_commit_conn=None):
        self.fail_on_execute = fail_on_execute
        self.executed = 0
        # results_v2's idempotent insert reads cur.rowcount (0 => already-present,
        # 1 => written) -- expose it so the commit path exercises the real code
        # instead of tripping over a missing attribute.
        self.rowcount = 1

    def execute(self, sql, params):
        self.executed += 1
        if self.fail_on_execute:
            raise RuntimeError("simulated: connection lost mid-insert")

    def close(self):
        pass


class _FakeConn:
    def __init__(self, fail_on_execute=False, fail_on_commit=False):
        self._cur = _FakeCursor(fail_on_execute)
        self.fail_on_commit = fail_on_commit
        self.committed = False

    def cursor(self):
        return self._cur

    def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("simulated: commit failed (connection reset)")
        self.committed = True

    def close(self):
        pass


def _run_main_with_fake_db(argv, fake_conn):
    """Run py_executor.main() in-process (not subprocess) with
    pg8000.dbapi.connect replaced by a stub that hands back `fake_conn` --
    the only way to reach the per-row cur.execute()/conn.commit() boundaries
    deterministically without a live Results DB. Returns (exit_code, stdout)."""
    orig_argv, orig_connect = sys.argv, py_executor.pg8000.dbapi.connect
    password_key = "BUNDLE_RESULTS_DB_PASSWORD"
    orig_password = os.environ.get(password_key)
    sys.argv = ["py_executor.py"] + argv
    py_executor.pg8000.dbapi.connect = lambda **kw: fake_conn
    os.environ[password_key] = "test-secret"
    buf = io.StringIO()
    try:
        try:
            with contextlib.redirect_stdout(buf):
                py_executor.main()
            exited = 0
        except SystemExit as exc:
            exited = exc.code or 0
        return exited, buf.getvalue()
    finally:
        sys.argv = orig_argv
        py_executor.pg8000.dbapi.connect = orig_connect
        if orig_password is None:
            os.environ.pop(password_key, None)
        else:
            os.environ[password_key] = orig_password


def test_db_insert_failure_reclassifies_candidate_as_infra_fail():
    """A candidate that ran fine and produced a DOMAIN_FAIL verdict, but whose
    insert failed because the DB connection was lost mid-run, must end up
    counted as INFRA_FAIL -- not silently recorded as a domain verdict that
    was never actually persisted (review finding: cur.execute() bypassed
    classification)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        srcdir.mkdir(parents=True)
        (srcdir / "1_0_0.py").write_text("FW_VAR = 1\n", encoding="utf-8")  # DOMAIN_FAIL -> always inserted
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-insert-fail", srcdir, 1)), encoding="utf-8")
        result_file = td / "result.json"

        fake_conn = _FakeConn(fail_on_execute=True)
        exited, out = _run_main_with_fake_db(
            ["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
             "--writeToDB", "true", "--failOnly", "false", "--resultFile", str(result_file)],
            fake_conn)

        assert "INFRA_FAIL -- DB insert failed for 1_0_0.py" in out
        # reclassified: NOT counted as a domain verdict, NOT inserted
        assert "py_executor DONE: processed=1 pass=0 fail=0 broken=0 inserted=0" in out
        assert "py_executor OUTCOMES:" in out and "domain_fail=0" in out and "infra_fail=1" in out
        result = json.loads(result_file.read_text(encoding="utf-8"))
        assert result["outcomes"]["DOMAIN_FAIL"] == 0
        assert result["outcomes"]["INFRA_FAIL"] == 1
        assert result["inserted"] == 0


def test_db_commit_failure_is_infra_fail_and_still_emits_summary():
    """A commit failure after successful inserts leaves every just-inserted row
    in an unknown persisted state -- it must be surfaced as INFRA_FAIL (in
    aggregate, since no single candidate can be blamed) rather than reported
    as a clean `inserted=N` the DB cannot actually back up (review finding:
    conn.commit() bypassed classification and could end the run silently)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        srcdir, sqldir = td / "candidates", td / "sqlTemplate"
        srcdir.mkdir(parents=True)
        (srcdir / "1_0_0.py").write_text("FW_VAR = 1\n", encoding="utf-8")  # DOMAIN_FAIL -> always inserted
        _write_sql_template(sqldir)
        manifest = td / "manifest.json"
        manifest.write_text(json.dumps(_manifest("run-commit-fail", srcdir, 1)), encoding="utf-8")
        result_file = td / "result.json"

        fake_conn = _FakeConn(fail_on_execute=False, fail_on_commit=True)
        exited, out = _run_main_with_fake_db(
            ["--manifest", str(manifest), "-dirSqlTemplate", str(sqldir),
             "--writeToDB", "true", "--failOnly", "false", "--resultFile", str(result_file)],
            fake_conn)

        assert exited != 0
        # stable message prefix (the combined legacy+results_v2 single-commit path, STEP 23/33);
        # the exact exception tail is incidental.
        assert "INFRA_FAIL -- combined legacy+results_v2 commit failed" in out
        assert "NOTHING persisted (1 candidate(s) reclassified)" in out
        # the process must still report -- not vanish mid-stream (review finding)
        assert "py_executor DONE: processed=1 pass=0 fail=0 broken=0 inserted=0" in out
        assert "py_executor OUTCOMES:" in out and "domain_fail=0" in out and "infra_fail=1" in out
        result = json.loads(result_file.read_text(encoding="utf-8"))
        assert result["outcomes"]["DOMAIN_FAIL"] == 0
        assert result["outcomes"]["INFRA_FAIL"] == 1
        assert result["inserted"] == 0


# ---- in-sandbox Analyzer-metrics harvest (no host re-run of candidates) ---- #
# Regression for the STEP 44 finding: collect_kv re-EXECUTED every candidate on
# the host to build the Analyzer corpus -- a sandbox bypass for a secure policy
# and a double-execution that re-fires stateful sudden actions, producing a wrong,
# truncated corpus. The corpus is now harvested from each candidate's REAL run
# (run_candidate metrics_out -> --metricsFile), never a second run.
def test_run_candidate_harvests_metrics_line_in_a_single_execution():
    """run_candidate with metrics_out captures the candidate's own 'app=...FW_VAR='
    line FROM the one real execution -- proven single-run by a side-effect counter
    the candidate increments each time it runs (must be exactly 1)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        counter = td / "runs.count"
        cand = td / "7_0_0.py"
        cand.write_text(
            "from pathlib import Path\n"
            f"p = Path(r'{counter}')\n"
            "p.write_text(str((int(p.read_text()) if p.exists() else 0) + 1))\n"
            "print('app=demo metric_x=42 FW_VAR=0')\n"
            "FW_VAR = 0\n", encoding="utf-8")
        metrics = []
        infra_outcome, fw, fwc = py_executor.run_candidate(sys.executable, cand, [], metrics_out=metrics)
        assert infra_outcome is None and fw == 0          # classification unchanged
        assert metrics == ["app=demo metric_x=42 FW_VAR=0"]  # harvested from the real run
        assert counter.read_text() == "1"                 # executed EXACTLY once (no re-run)


def test_run_candidate_metrics_out_default_is_unchanged():
    """Omitting metrics_out keeps the legacy 3-tuple behaviour byte-for-byte
    (backward compatible: every existing caller/test passes nothing)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ok = td / "1_0_0.py"; ok.write_text("print('app=x FW_VAR=0')\nFW_VAR = 0\n", encoding="utf-8")
        assert py_executor.run_candidate(sys.executable, ok, []) == (None, 0, -999)
        # a BROKEN candidate appends nothing (no metrics line emitted)
        broke = td / "2_0_0.py"; broke.write_text("raise SystemExit(3)\n", encoding="utf-8")
        cap = []
        assert py_executor.run_candidate(sys.executable, broke, [], metrics_out=cap) == (Outcome.BROKEN, None, None)
        assert cap == []


def test_write_metrics_corpus_matches_collect_kv_format_and_is_ordered():
    """_write_metrics_corpus emits one '<candidate_id> <source_ref> <run_id> <K=V>'
    line per candidate, sorted by candidate_id -- byte-compatible with collect_kv's
    provenance prefix so AnalyzeKv's formal provenance/corpus-count checks consume it
    unchanged, and deterministic regardless of execution order."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "metrics.kv"
        by_id = {
            "10_0_0": ("10_0_0.py", "app=demo sev=1 FW_VAR=2"),
            "2_0_0": ("2_0_0.py", "app=demo sev=0 FW_VAR=0"),
        }
        n = py_executor._write_metrics_corpus(out, by_id, "run-xyz")
        assert n == 2
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines == [
            "candidate_id=10_0_0 source_ref=10_0_0.py run_id=run-xyz app=demo sev=1 FW_VAR=2",
            "candidate_id=2_0_0 source_ref=2_0_0.py run_id=run-xyz app=demo sev=0 FW_VAR=0",
        ]


def test_merge_worker_metrics_is_sorted_dedup_and_crash_tolerant():
    """The worker-pool metrics merge (BUG-1 dispatcher path) must yield a corpus
    keyed+sorted by candidate_id so 1-worker and N-worker runs produce the IDENTICAL
    corpus, skip a crashed worker's missing partition, and write deterministically."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "metrics-0.kv").write_text(
            "candidate_id=2_0_0 run_id=r app=x v=2 FW_VAR=0\n"
            "candidate_id=10_0_0 run_id=r app=x v=10 FW_VAR=1\n", encoding="utf-8")
        (d / "metrics-1.kv").write_text(
            "candidate_id=1_0_0 run_id=r app=x v=1 FW_VAR=0\n", encoding="utf-8")
        out = d / "metrics.kv"
        # metrics-2.kv is intentionally absent -> a crashed worker's partition is skipped
        n = py_executor.merge_worker_metrics(
            [d / "metrics-0.kv", d / "metrics-1.kv", d / "metrics-2.kv"], out)
        assert n == 3, n
        lines = out.read_text(encoding="utf-8").splitlines()
        assert [l.split()[0] for l in lines] == [
            "candidate_id=10_0_0", "candidate_id=1_0_0", "candidate_id=2_0_0"], lines
        # deterministic: re-merging the same inputs yields identical bytes
        out2 = d / "metrics2.kv"
        py_executor.merge_worker_metrics([d / "metrics-0.kv", d / "metrics-1.kv"], out2)
        assert out2.read_text(encoding="utf-8") == out.read_text(encoding="utf-8")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} tests passed")
