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

"""STEP 27 propagation tests: the execution policy (id + sha256) the launcher
writes -- into the Handoff v2 manifest's ``execution_policy_ref`` and the sibling
``execution_policy.json`` -- flows through the Executor into every ``results_v2``
row. This is *actual* Reader->Executor->result propagation, not model round-trip:

  * ``_load_execution_policy`` / ``read_manifest`` extract the policy from the
    on-disk manifest+sidecar (the "Reader -> Executor" carrier);
  * an end-to-end ``py_executor`` subprocess reads them and logs the policy it
    will record (real process, real files);
  * ``write_results_v2_batch`` -- the exact writer the Executor calls -- persists
    ``policy_id``/``policy_hash``, confirmed by reading the row back (Executor ->
    result);
  * ``ensure_results_v2_schema`` backfills the two columns onto a table created
    before STEP 27.

Run: ``python3 -m pytest test_results_v2_policy.py``. The DB-backed tests need a
reachable local Postgres (BUNDLE_RESULTS_DB_PASSWORD); they SKIP (not fail) when
it is absent, exactly like the other results_v2 DB harnesses.
"""
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pg8000.dbapi
import pytest

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"
_spec = importlib.util.spec_from_file_location("py_executor_policy", PY_EXECUTOR)
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)

POLICY_ID = "ep-0123456789ab"
POLICY_HASH = "0123456789abcdef" * 4          # 64 hex chars, like a real sha256
INSERT_SQL = "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);"   # 9 '?' -> placeholders=9 (FW_VAR mode)


def _policy_view():
    # trusted-local (trusted=True): STEP 28's sandbox.build_sandbox returns no
    # backend for it, so the Executor runs the candidate unsandboxed exactly as
    # before -- this STEP 27 propagation test stays about the policy id/hash
    # reaching results_v2, not about sandboxing.
    return {"id": POLICY_ID, "sha256": POLICY_HASH,
            "policy": {"schema": "bundle.execution-policy/v1", "profile": "trusted-local",
                       "backend": "local", "network": "unrestricted", "trusted": True}}


def _manifest(run_id, srcdir, database="testdb", policy_ref=POLICY_ID):
    m = {
        "protocol": "bundle.handoff/v2", "run_id": run_id, "language": "python",
        "candidate_transport": "loose-files", "candidate_count": 1,
        "id_format": "<combi_id>_0_0", "sources": [{"kind": "dir", "path": str(srcdir)}],
        "result_target": {"host": "127.0.0.1", "port": 5432, "database": database, "user": "postgres"},
        "result_schema_mode": "placeholders=9", "verdict_mode": "FW_VAR", "arguments": [], "shift": 1,
    }
    if policy_ref is not None:
        m["execution_policy_ref"] = policy_ref
    return m


def _layout(tmp, run_id="run-policy", database="testdb", policy_ref=POLICY_ID, write_sidecar=True):
    """Build the on-disk manifest + sidecar + candidate + insert.sql the way the
    launcher lays them out (execution_policy.json next to manifest.json)."""
    srcdir = tmp / "candidates"; srcdir.mkdir(parents=True, exist_ok=True)
    (srcdir / "1_0_0.py").write_text("FW_VAR = 0\n", encoding="utf-8")
    sqldir = tmp / "sqlTemplate"; sqldir.mkdir(parents=True, exist_ok=True)
    (sqldir / "insert.sql").write_text(INSERT_SQL, encoding="utf-8")
    hoff = tmp / "handoff"; hoff.mkdir(parents=True, exist_ok=True)
    manifest = hoff / "manifest.json"
    manifest.write_text(json.dumps(_manifest(run_id, srcdir, database, policy_ref)), encoding="utf-8")
    if write_sidecar:
        (hoff / "execution_policy.json").write_text(json.dumps(_policy_view()), encoding="utf-8")
    return srcdir, sqldir, manifest


# --------------------------- extraction (Reader -> Executor) ------------------ #
def test_load_execution_policy_present_absent_malformed(tmp_path):
    # STEP 28 widened the return to (id, hash, policy) -- the third element is the
    # full policy dict the sandbox backend consumes.
    policy = _policy_view()["policy"]
    (tmp_path / "execution_policy.json").write_text(json.dumps(_policy_view()), encoding="utf-8")
    assert py_executor._load_execution_policy(tmp_path) == (POLICY_ID, POLICY_HASH, policy)
    missing = tmp_path / "missing"; missing.mkdir()
    assert py_executor._load_execution_policy(missing) == (None, None, None)
    bad = tmp_path / "bad"; bad.mkdir()
    (bad / "execution_policy.json").write_text("{ not json", encoding="utf-8")
    assert py_executor._load_execution_policy(bad) == (None, None, None)
    # first dir that has the sidecar wins (search-order honored)
    assert py_executor._load_execution_policy(missing, tmp_path) == (POLICY_ID, POLICY_HASH, policy)


def test_read_manifest_extracts_policy_id_and_hash(tmp_path, monkeypatch):
    monkeypatch.setenv(py_executor.DB_PASSWORD_ENV_VAR, "unused-by-this-test")
    srcdir, sqldir, manifest = _layout(tmp_path)
    hs = py_executor.read_manifest(manifest, {"dirSqlTemplate": str(sqldir)})
    assert hs["policy_id"] == POLICY_ID       # from the manifest's execution_policy_ref
    assert hs["policy_hash"] == POLICY_HASH    # from the sibling execution_policy.json


def test_read_manifest_falls_back_to_sidecar_id_when_ref_absent(tmp_path, monkeypatch):
    monkeypatch.setenv(py_executor.DB_PASSWORD_ENV_VAR, "unused-by-this-test")
    srcdir, sqldir, manifest = _layout(tmp_path, policy_ref=None)   # no ref in manifest
    hs = py_executor.read_manifest(manifest, {"dirSqlTemplate": str(sqldir)})
    assert hs["policy_id"] == POLICY_ID and hs["policy_hash"] == POLICY_HASH


# ------------------- end-to-end subprocess (real Executor reads it) ----------- #
def test_executor_subprocess_reads_policy_from_manifest_and_sidecar(tmp_path):
    """A real py_executor process, given the manifest + sibling sidecar, logs the
    exact policy id/hash it will stamp onto results_v2 -- proving the Executor
    (not just an in-process call) reads the launcher's on-disk policy. writeToDB
    is off, so this needs no database."""
    srcdir, sqldir, manifest = _layout(tmp_path, run_id="run-e2e-policy")
    env = dict(os.environ); env["BUNDLE_RESULTS_DB_PASSWORD"] = "unused"
    r = subprocess.run([sys.executable, str(PY_EXECUTOR), "--manifest", str(manifest),
                        "-dirSqlTemplate", str(sqldir), "--writeToDB", "false", "--failOnly", "false"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"execution policy → id={POLICY_ID}" in r.stdout
    assert POLICY_HASH[:12] in r.stdout
    assert "processed=1 pass=1" in r.stdout


# ----------------------- persistence (Executor -> result) -------------------- #
@pytest.fixture
def results_db():
    host = os.environ.get("BUNDLE_RESULTS_DB_HOST", "127.0.0.1")
    port = int(os.environ.get("BUNDLE_RESULTS_DB_PORT", "5432"))
    user = os.environ.get("BUNDLE_RESULTS_DB_USER", "postgres")
    password = os.environ.get("BUNDLE_RESULTS_DB_PASSWORD")
    if not password:
        pytest.skip("BUNDLE_RESULTS_DB_PASSWORD not set -- DB-backed propagation test skipped")
    name = f"results_v2_policy_smoke_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

    def _admin():
        c = pg8000.dbapi.connect(host=host, port=port, database="postgres", user=user, password=password)
        c.autocommit = True
        return c

    # A set password says the operator INTENDED a DB run; it does not prove the
    # server is up. Without this guard an unreachable endpoint raises inside the
    # fixture and pytest reports ERROR, contradicting this module's docstring and
    # diverging from the sibling results_v2 harnesses, which skip. Absent
    # infrastructure is a skip; only a reachable-but-wrong server is a failure.
    try:
        admin = _admin()
    except Exception as exc:
        pytest.skip(f"results PostgreSQL unavailable at {host}:{port}: {exc}")
    try:
        cur = admin.cursor(); cur.execute(f'CREATE DATABASE "{name}"'); cur.close()
    finally:
        admin.close()
    conn = pg8000.dbapi.connect(host=host, port=port, database=name, user=user, password=password)
    try:
        yield conn
    finally:
        conn.close()
        try:
            admin = _admin()
            cur = admin.cursor(); cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'); cur.close()
            admin.close()
        except Exception:
            pass


def test_writer_persists_policy_columns(results_db):
    py_executor.ensure_results_v2_schema(results_db)
    row = {"run_id": "step27-writer", "candidate_id": "1_0_0", "attempt": 1, "outcome": "PASS",
           "policy_id": POLICY_ID, "policy_hash": POLICY_HASH}
    counts = py_executor.write_results_v2_batch(results_db, [row])
    assert counts["attempted"] == 1 and counts["inserted"] == 1
    cur = results_db.cursor()
    cur.execute("SELECT policy_id, policy_hash FROM public.results_v2 "
                "WHERE run_id='step27-writer' AND candidate_id='1_0_0'")
    got = cur.fetchone(); cur.close()
    assert got == [POLICY_ID, POLICY_HASH]


def test_schema_migration_backfills_policy_columns_on_pre_step27_table(results_db):
    # Simulate a results_v2 created before STEP 27: the full STEP-22 schema MINUS
    # the two policy columns. ensure_results_v2_schema must ADD them (repeatable
    # migration) without disturbing the existing columns.
    cur = results_db.cursor()
    cur.execute("CREATE TABLE public.results_v2 ("
                "id bigserial PRIMARY KEY, run_id text NOT NULL, candidate_id text NOT NULL, "
                "attempt integer NOT NULL DEFAULT 1, outcome text NOT NULL, verdict_code integer, "
                "verdict_message text, duration_ms bigint, exit_code integer, signal text, worker text, "
                "source_hash text, stdout_ref text, stderr_ref text, "
                "created_at timestamptz NOT NULL DEFAULT now())")
    results_db.commit(); cur.close()
    py_executor.ensure_results_v2_schema(results_db)   # must not fail; must add the columns
    cur = results_db.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name='results_v2' AND column_name IN ('policy_id','policy_hash') ORDER BY 1")
    cols = [r[0] for r in cur.fetchall()]; cur.close()
    assert cols == ["policy_hash", "policy_id"]
    # and a write of the full row now succeeds end-to-end
    py_executor.write_results_v2_batch(results_db, [{"run_id": "m", "candidate_id": "c", "attempt": 1,
                                                     "outcome": "PASS", "policy_id": POLICY_ID,
                                                     "policy_hash": POLICY_HASH}])
