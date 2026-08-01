#!/usr/bin/env python3
"""Plan-1 schema-delta tests (docs/24 §1.4/§1.6/§1.7): the results_v2 ``repeat_idx``/``env_id``
columns AND the Phase-3b cutover that makes the 5-column sample key
``(run_id, candidate_id, attempt, repeat_idx, env_id)`` the unique identity + ``ON CONFLICT``
target, retiring the legacy 3-column key. Java/Python parity throughout. Non-DB-gated: DDL-string
parity + a recording-cursor migration-order check (create sample index, then drop legacy index).
DB-gated (skip without ``BUNDLE_RESULTS_DB_PASSWORD``): live migration contract (5-col index
present, 3-col gone, columns backfilled), K=1 default-filled insert, idempotent duplicate/upsert,
K>1 sample identity (two rows differing only in repeat_idx coexist), and resume idempotency.
Run: python3 -m pytest test_results_v2_repeat_schema.py -q
"""
import contextlib
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

try:
    import pg8000.dbapi as _pg
except Exception:  # pragma: no cover - pg8000 is vendored in this repo
    _pg = None

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"
JAVA_MIGRATOR = HERE / "src" / "main" / "java" / "com" / "company" / "ResultsV2SchemaMigrator.java"

_spec = importlib.util.spec_from_file_location("py_executor_phase3", PY_EXECUTOR)
pyx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pyx)


def _norm(s):
    return " ".join(s.split()).lower()


# ------------------------------ Python DDL delta ---------------------------- #
def test_python_create_table_has_repeat_columns_with_k1_defaults():
    ddl = _norm(pyx.RESULTS_V2_CREATE_TABLE_SQL)
    assert "repeat_idx integer not null default 0" in ddl
    assert "env_id text not null default ''" in ddl


def test_python_repeat_backfill_is_additive_if_not_exists():
    sql = _norm(pyx.RESULTS_V2_ADD_REPEAT_COLUMNS_SQL)
    assert "alter table public.results_v2" in sql
    assert "add column if not exists repeat_idx integer not null default 0" in sql
    assert "add column if not exists env_id text not null default ''" in sql


def test_python_unique_index_and_on_conflict_are_5col_sample_key():
    # Phase 3b: identity is the 5-column sample key; the legacy 3-col index is dropped.
    idx = _norm(pyx.RESULTS_V2_CREATE_SAMPLE_INDEX_SQL)
    assert "results_v2_sample_uk" in idx
    assert "(run_id, candidate_id, attempt, repeat_idx, env_id)" in idx
    drop = _norm(pyx.RESULTS_V2_DROP_LEGACY_INDEX_SQL)
    assert "drop index if exists" in drop and "results_v2_run_candidate_attempt_uk" in drop
    # the old 3-col create constant is gone (no stale 3-col key left to resurrect here).
    assert not hasattr(pyx, "RESULTS_V2_CREATE_UNIQUE_INDEX_SQL")
    ins = _norm(pyx.RESULTS_V2_IDEMPOTENT_INSERT_SQL)
    assert "on conflict (run_id, candidate_id, attempt, repeat_idx, env_id) do nothing" in ins
    # the writer now lists repeat_idx/env_id explicitly (K=1 binds the 0/'' defaults).
    assert "repeat_idx, env_id)" in ins


# ------------------------------ Java/Python parity -------------------------- #
def test_java_migrator_parity():
    java = _norm(JAVA_MIGRATOR.read_text(encoding="utf-8"))
    assert "repeat_idx integer not null default 0" in java
    assert "env_id text not null default ''" in java
    assert "add column if not exists repeat_idx integer not null default 0" in java
    assert "add column if not exists env_id text not null default ''" in java
    # Phase 3b: Java cuts over to the same 5-col sample index and drops the legacy 3-col key.
    assert "results_v2_sample_uk" in java
    assert "(run_id, candidate_id, attempt, repeat_idx, env_id)" in java
    assert "drop index if exists public.results_v2_run_candidate_attempt_uk" in java


# ------------------------- migration applies it, in order ------------------- #
class _RecordingCursor:
    def __init__(self):
        self.sql = []

    def execute(self, s):
        self.sql.append(s)

    def close(self):
        pass


class _RecordingConn:
    def __init__(self):
        self.cur = _RecordingCursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def test_ensure_schema_applies_repeat_backfill_in_order():
    conn = _RecordingConn()
    pyx.ensure_results_v2_schema(conn)
    stmts = [_norm(s) for s in conn.cur.sql]
    assert conn.committed is True
    table_i = next(i for i, s in enumerate(stmts) if "create table if not exists public.results_v2" in s)
    policy_i = next(i for i, s in enumerate(stmts) if "add column if not exists policy_id" in s)
    repeat_i = next(i for i, s in enumerate(stmts) if "add column if not exists repeat_idx" in s)
    sample_i = next(i for i, s in enumerate(stmts) if "create unique index" in s and "results_v2_sample_uk" in s)
    drop_i = next(i for i, s in enumerate(stmts) if "drop index if exists" in s)
    meta_i = next(i for i, s in enumerate(stmts) if "create table if not exists public.results_v2_schema_meta" in s)
    stamp_i = next(i for i, s in enumerate(stmts) if "insert into public.results_v2_schema_meta" in s)
    # backfill columns first, then create the 5-col sample index, then drop the legacy 3-col index
    # (create-before-drop so the table is never left without a unique key), then stamp the meta.
    assert table_i < policy_i < repeat_i < sample_i < drop_i < meta_i < stamp_i
    # no statement re-creates the legacy 3-col key.
    assert not any("results_v2_run_candidate_attempt_uk" in s and "create" in s for s in stmts)


# ----------------- DB-gated assertions (run only with PostgreSQL) ----------- #
# Structural tests above run everywhere; these assert the live migration shapes
# (column type/NOT NULL/default, backfilled row values, unchanged 3-col index, and a
# default-filled K=1 insert) and SKIP without BUNDLE_RESULTS_DB_PASSWORD.
def _db_admin_or_skip():
    password = os.environ.get("BUNDLE_RESULTS_DB_PASSWORD")
    if not password or _pg is None:
        pytest.skip("BUNDLE_RESULTS_DB_PASSWORD/pg8000 unavailable; skipping live-DB repeat-schema assertions")
    cfg = {
        "host": os.environ.get("BUNDLE_RESULTS_DB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("BUNDLE_RESULTS_DB_PORT", "5432")),
        "user": os.environ.get("BUNDLE_RESULTS_DB_USER", "postgres"),
        "password": password,
        "database": os.environ.get("BUNDLE_RESULTS_DB_NAME", "postgres"),
    }
    try:
        return _pg.connect(**cfg), cfg
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")


@contextlib.contextmanager
def _temp_db():
    admin, cfg = _db_admin_or_skip()
    name = f"bundle_phase3a_{os.getpid()}_{uuid.uuid4().hex[:10]}"
    created = False
    try:
        admin.autocommit = True
        cur = admin.cursor()
        try:
            cur.execute(f'CREATE DATABASE "{name}"')
            created = True
        except Exception as exc:
            pytest.skip(f"role cannot create a temporary database: {exc}")
        finally:
            cur.close()
        conn = _pg.connect(**dict(cfg, database=name))
        try:
            yield conn
        finally:
            conn.close()
    finally:
        if created:
            cur = admin.cursor()
            try:
                cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
                cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
            finally:
                cur.close()
        admin.close()


def _assert_live_repeat_contract(cur):
    cur.execute("SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='results_v2' "
                "AND column_name IN ('repeat_idx','env_id')")
    meta = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    assert "repeat_idx" in meta and "env_id" in meta, meta
    rtype, rnull, rdef = meta["repeat_idx"]
    assert rtype == "integer" and rnull == "NO" and rdef is not None and rdef.startswith("0"), meta["repeat_idx"]
    etype, enull, edef = meta["env_id"]
    assert etype == "text" and enull == "NO" and edef is not None and "''" in edef, meta["env_id"]
    # Phase 3b: the 5-col sample index is live and the legacy 3-col index is gone.
    cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                "AND tablename='results_v2' AND indexname='results_v2_sample_uk'")
    row = cur.fetchone()
    assert row is not None, "5-col sample unique index missing"
    idxdef = " ".join(row[0].split()).lower()
    assert "unique index" in idxdef
    assert "(run_id, candidate_id, attempt, repeat_idx, env_id)" in idxdef
    cur.execute("SELECT 1 FROM pg_indexes WHERE schemaname='public' "
                "AND tablename='results_v2' AND indexname='results_v2_run_candidate_attempt_uk'")
    assert cur.fetchone() is None, "legacy 3-col unique index should be dropped after Phase 3b cutover"


def test_db_prior_state_table_backfills_repeat_columns():
    with _temp_db() as conn:
        cur = conn.cursor()
        # a PRE-Phase-3 results_v2 (no repeat_idx/env_id/policy columns), with a row.
        cur.execute("CREATE TABLE public.results_v2 ("
                    " id bigserial PRIMARY KEY, run_id text NOT NULL, candidate_id text NOT NULL,"
                    " attempt integer NOT NULL DEFAULT 1, outcome text NOT NULL,"
                    " created_at timestamptz NOT NULL DEFAULT now())")
        cur.execute("INSERT INTO public.results_v2(run_id, candidate_id, attempt, outcome) "
                    "VALUES ('prior', 'c1', 1, 'PASS')")
        conn.commit()
        pyx.ensure_results_v2_schema(conn)   # adds policy + repeat columns + the index
        pyx.ensure_results_v2_schema(conn)   # idempotent re-run changes nothing
        _assert_live_repeat_contract(cur)
        cur.execute("SELECT repeat_idx, env_id FROM public.results_v2 WHERE candidate_id='c1'")
        assert tuple(cur.fetchone()) == (0, "")   # prior row backfilled with K=1 defaults
        cur.close()


def test_db_fresh_migration_contract_and_default_filled_insert():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        _assert_live_repeat_contract(cur)
        # a K=1 insert that does NOT list repeat_idx/env_id gets the defaults.
        cur.execute("INSERT INTO public.results_v2(run_id, candidate_id, attempt, outcome) "
                    "VALUES ('fresh', 'c2', 1, 'PASS')")
        conn.commit()
        cur.execute("SELECT repeat_idx, env_id FROM public.results_v2 WHERE candidate_id='c2'")
        assert tuple(cur.fetchone()) == (0, "")
        cur.close()


def test_db_cutover_from_legacy_3col_index_drops_it_and_unblocks_repeats():
    # The real 3a->3b path: a DB already on the LEGACY 3-col unique index with a K=1 row. The
    # migration must create the 5-col sample index, drop the 3-col index, preserve the row, and
    # thereby unblock a K>1 repeat sample the 3-col key would have rejected as a duplicate.
    with _temp_db() as conn:
        cur = conn.cursor()
        cur.execute(pyx.RESULTS_V2_CREATE_TABLE_SQL)
        cur.execute("CREATE UNIQUE INDEX results_v2_run_candidate_attempt_uk "
                    "ON public.results_v2 (run_id, candidate_id, attempt)")
        cur.execute("INSERT INTO public.results_v2(run_id, candidate_id, attempt, outcome) "
                    "VALUES ('legacy', 'c1', 1, 'PASS')")
        conn.commit()
        cur.execute("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND tablename='results_v2' "
                    "AND indexname='results_v2_run_candidate_attempt_uk'")
        assert cur.fetchone() is not None, "precondition: legacy 3-col index present"
        pyx.ensure_results_v2_schema(conn)        # the Phase 3b cutover
        _assert_live_repeat_contract(cur)         # 5-col present, 3-col gone
        cur.execute("SELECT repeat_idx, env_id FROM public.results_v2 WHERE candidate_id='c1'")
        assert tuple(cur.fetchone()) == (0, "")   # the legacy row survived with K=1 defaults
        # a repeat sample (same run/candidate/attempt, repeat_idx=1) now inserts -- the 3-col key
        # would have rejected it as a duplicate.
        assert pyx.write_results_v2_batch(conn, [
            {"run_id": "legacy", "candidate_id": "c1", "attempt": 1, "outcome": "PASS",
             "repeat_idx": 1, "env_id": ""}])["inserted"] == 1
        cur.close()


# ---- Phase 3b writer behaviour over the live 5-col sample key (DB-gated) -------------------- #
def _v2_row(candidate_id, attempt, outcome, **extra):
    base = {"run_id": "r1", "candidate_id": candidate_id, "attempt": attempt, "outcome": outcome}
    base.update(extra)
    return base


def _count_rows(cur, run_id="r1"):
    cur.execute("SELECT count(*) FROM public.results_v2 WHERE run_id=%s", (run_id,))
    return cur.fetchone()[0]


def test_db_writer_5col_upsert_idempotent_and_k1_defaults():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        batch = [_v2_row("c1", 1, "PASS"), _v2_row("c2", 1, "DOMAIN_FAIL")]
        first = pyx.write_results_v2_batch(conn, batch)
        assert first == {"attempted": 2, "inserted": 2, "already_present": 0, "updated_selected": 0}
        # K=1 rows that omit repeat_idx/env_id are bound with the 0/'' defaults (writer coalesces).
        cur.execute("SELECT repeat_idx, env_id FROM public.results_v2 ORDER BY candidate_id")
        assert [tuple(r) for r in cur.fetchall()] == [(0, ""), (0, "")]
        # replay the IDENTICAL batch -> ON CONFLICT (5-col) DO NOTHING, nothing duplicated.
        replay = pyx.write_results_v2_batch(conn, batch)
        assert replay == {"attempted": 2, "inserted": 0, "already_present": 2, "updated_selected": 0}
        assert _count_rows(cur) == 2
        cur.close()


def test_db_writer_k_gt_1_sample_identity_coexists():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        # sample 0 (the verdict) and sample 1 (a repeat) of ONE candidate at ONE attempt differ ONLY
        # in repeat_idx -> DISTINCT rows under the 5-col key (the retired 3-col key would reject s1).
        s0 = _v2_row("c1", 1, "PASS", repeat_idx=0, env_id="")
        s1 = _v2_row("c1", 1, "PASS", repeat_idx=1, env_id="")
        counts = pyx.write_results_v2_batch(conn, [s0, s1])
        assert counts["inserted"] == 2 and counts["already_present"] == 0
        assert _count_rows(cur) == 2
        # a different env_id is also a distinct sample of the same (candidate, attempt, repeat_idx).
        s0e = _v2_row("c1", 1, "PASS", repeat_idx=0, env_id="envB")
        assert pyx.write_results_v2_batch(conn, [s0e])["inserted"] == 1
        assert _count_rows(cur) == 3
        # replaying every sample is idempotent (each is already present at the 5-col key).
        assert pyx.write_results_v2_batch(conn, [s0, s1, s0e]) == {
            "attempted": 3, "inserted": 0, "already_present": 3, "updated_selected": 0}
        cur.close()


def test_db_resume_replay_is_idempotent_across_remigrate():
    # "idempotent resume": a re-run that re-applies the (idempotent) schema cutover AND re-writes the
    # same sample batch lands no duplicates -- the 5-col unique key dedupes at the DB layer.
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        batch = [_v2_row("c1", 1, "PASS", repeat_idx=0, env_id=""),
                 _v2_row("c1", 1, "PASS", repeat_idx=1, env_id="")]
        assert pyx.write_results_v2_batch(conn, batch)["inserted"] == 2
        pyx.ensure_results_v2_schema(conn)          # resume re-runs the cutover: still idempotent
        _assert_live_repeat_contract(cur)           # 5-col index still the only unique key
        replay = pyx.write_results_v2_batch(conn, batch)
        assert replay == {"attempted": 2, "inserted": 0, "already_present": 2, "updated_selected": 0}
        assert _count_rows(cur) == 2
        cur.close()


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except BaseException as exc:  # noqa: BLE001 - also catch pytest.skip's Skipped (BaseException)
            if "Skipped" in type(exc).__name__:
                print(f"  skip {fn.__name__}: {exc}")
            else:
                failures += 1
                print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
