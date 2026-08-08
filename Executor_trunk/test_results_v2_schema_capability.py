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

"""Plan-1 Phase 3b launcher-side schema safety (docs/24 §1.6): the ``results_v2_schema_meta`` stamp
and the writer's connect-time capability validation that fails CLOSED
(``RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH``) when the live results_v2 identity is not the 5-column
sample key this writer upserts against.

Structural (always run): the capability document advertises the 5-col schema writer; the meta DDL
shape. DB-gated (skip without ``BUNDLE_RESULTS_DB_PASSWORD``): fresh install stamps + validates;
legacy 3a migration stamps + validates; compatible reconnect re-stamps idempotently; and validation
fails closed on a missing stamp, a wrong version, a missing/wrong 5-col index, and a resurrected
legacy 3-col index.
Run: python3 -m pytest test_results_v2_schema_capability.py -q
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

_spec = importlib.util.spec_from_file_location("py_executor_cap", PY_EXECUTOR)
pyx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pyx)


def _norm(s):
    return " ".join(s.split()).lower()


# ------------------------------ structural (no DB) -------------------------- #
def test_capability_document_advertises_5col_schema_writer():
    rs = pyx.capability_document()["results_v2_schema"]
    assert rs == {"version": 2, "unique_index": "results_v2_sample_uk", "sample_identity_writer": True}
    assert pyx.RESULTS_V2_SCHEMA_VERSION == 2
    assert pyx.RESULTS_V2_SAMPLE_INDEX_NAME == "results_v2_sample_uk"


def test_schema_meta_ddl_is_singleton_and_stamp_upserts():
    ddl = _norm(pyx.RESULTS_V2_CREATE_SCHEMA_META_SQL)
    assert "create table if not exists public.results_v2_schema_meta" in ddl
    assert "id integer primary key" in ddl and "check (id = 1)" in ddl
    assert "version integer not null" in ddl and "unique_index text not null" in ddl
    stamp = _norm(pyx.RESULTS_V2_STAMP_SCHEMA_META_SQL)
    assert "insert into public.results_v2_schema_meta" in stamp
    assert "on conflict (id) do update" in stamp


# ----------------- DB-gated assertions (run only with PostgreSQL) ----------- #
def _db_admin_or_skip():
    password = os.environ.get("BUNDLE_RESULTS_DB_PASSWORD")
    if not password or _pg is None:
        pytest.skip("BUNDLE_RESULTS_DB_PASSWORD/pg8000 unavailable; skipping live-DB capability assertions")
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
    name = f"bundle_phase3b_{os.getpid()}_{uuid.uuid4().hex[:10]}"
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


def _meta(cur):
    cur.execute("SELECT version, unique_index FROM public.results_v2_schema_meta WHERE id=1")
    return cur.fetchone()


def test_db_fresh_install_stamps_meta_and_validates():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        assert tuple(_meta(cur)) == (2, "results_v2_sample_uk")
        pyx.validate_results_v2_schema_capability(conn)   # compatible -> no raise
        cur.close()


def test_db_legacy_3col_migration_stamps_meta_and_validates():
    with _temp_db() as conn:
        cur = conn.cursor()
        # a DB already on the legacy 3-col index, no meta stamp (pre-3b).
        cur.execute(pyx.RESULTS_V2_CREATE_TABLE_SQL)
        cur.execute("CREATE UNIQUE INDEX results_v2_run_candidate_attempt_uk "
                    "ON public.results_v2 (run_id, candidate_id, attempt)")
        conn.commit()
        pyx.ensure_results_v2_schema(conn)                # 3b cutover: drops 3-col, stamps meta
        assert tuple(_meta(cur)) == (2, "results_v2_sample_uk")
        pyx.validate_results_v2_schema_capability(conn)
        cur.close()


def test_db_compatible_reconnect_restamps_idempotently():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        pyx.ensure_results_v2_schema(conn)               # a second connect re-stamps the singleton
        cur.execute("SELECT count(*) FROM public.results_v2_schema_meta")
        assert cur.fetchone()[0] == 1                    # still exactly one stamp row
        pyx.validate_results_v2_schema_capability(conn)
        cur.close()


def test_db_missing_meta_fails_closed():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        cur.execute("DELETE FROM public.results_v2_schema_meta")
        conn.commit()
        with pytest.raises(pyx.ResultsV2SchemaCapabilityMismatch) as ei:
            pyx.validate_results_v2_schema_capability(conn)
        assert pyx.RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH in str(ei.value)
        cur.close()


def test_db_wrong_version_fails_closed():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        cur.execute("UPDATE public.results_v2_schema_meta SET version=99 WHERE id=1")
        conn.commit()
        with pytest.raises(pyx.ResultsV2SchemaCapabilityMismatch) as ei:
            pyx.validate_results_v2_schema_capability(conn)
        assert pyx.RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH in str(ei.value)
        cur.close()


def test_db_missing_or_wrong_index_fails_closed():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        # drop the real 5-col index but leave the (now stale) meta stamp -> a stamp without the
        # backing index must fail closed.
        cur.execute("DROP INDEX public.results_v2_sample_uk")
        conn.commit()
        with pytest.raises(pyx.ResultsV2SchemaCapabilityMismatch) as ei:
            pyx.validate_results_v2_schema_capability(conn)
        assert pyx.RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH in str(ei.value)
        cur.close()


def test_db_resurrected_legacy_3col_index_fails_closed():
    with _temp_db() as conn:
        cur = conn.cursor()
        pyx.ensure_results_v2_schema(conn)
        # simulate an old binary re-creating the 3-col index after cutover -> must fail closed
        # (the two unique keys cannot coexist for K>1).
        cur.execute("CREATE UNIQUE INDEX results_v2_run_candidate_attempt_uk "
                    "ON public.results_v2 (run_id, candidate_id, attempt)")
        conn.commit()
        with pytest.raises(pyx.ResultsV2SchemaCapabilityMismatch) as ei:
            pyx.validate_results_v2_schema_capability(conn)
        assert pyx.RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH in str(ei.value)
        cur.close()


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except BaseException as exc:  # noqa: BLE001 - also catch pytest.skip's Skipped
            if "Skipped" in type(exc).__name__:
                print(f"  skip {fn.__name__}: {exc}")
            else:
                failures += 1
                print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
