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

"""STEP 22 migration tests.

The unit test verifies rollback on a partial DDL failure. The DB-backed smoke
creates and drops an isolated temporary PostgreSQL database, applies the real
migration twice, inserts PASS/DOMAIN_FAIL/TIMEOUT rows, and confirms the
unmodified legacy boolean-status query still works.
"""
import importlib.util
import os
import uuid
from pathlib import Path

import pg8000.dbapi
import pytest

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"

_spec = importlib.util.spec_from_file_location("py_executor_results_v2", PY_EXECUTOR)
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)


class _FailingCursor:
    def __init__(self):
        self.execute_count = 0

    def execute(self, _sql):
        self.execute_count += 1
        if self.execute_count == 2:
            raise RuntimeError("simulated unique-index DDL failure")

    def close(self):
        pass


class _FailingConnection:
    def __init__(self):
        self.cursor_instance = _FailingCursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_partial_migration_rolls_back_before_error_is_rethrown():
    conn = _FailingConnection()

    with pytest.raises(RuntimeError, match="unique-index DDL failure"):
        py_executor.ensure_results_v2_schema(conn)

    assert conn.commits == 0
    assert conn.rollbacks == 1


def _db_config():
    password = os.environ.get("BUNDLE_RESULTS_DB_PASSWORD")
    if not password:
        pytest.skip("BUNDLE_RESULTS_DB_PASSWORD is not set; skipping PostgreSQL migration smoke")
    return {
        "host": os.environ.get("BUNDLE_RESULTS_DB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("BUNDLE_RESULTS_DB_PORT", "5432")),
        "user": os.environ.get("BUNDLE_RESULTS_DB_USER", "postgres"),
        "password": password,
        "database": os.environ.get("BUNDLE_RESULTS_DB_NAME", "postgres"),
    }


def _connect_or_skip(config):
    try:
        return pg8000.dbapi.connect(**config)
    except Exception as exc:
        pytest.skip(f"PostgreSQL credentials are unavailable: {exc}")


def test_results_v2_repeatable_migration_and_legacy_compatibility():
    config = _db_config()
    admin = _connect_or_skip(config)
    temp_db = f"bundle_step22_{os.getpid()}_{uuid.uuid4().hex[:10]}"
    created = False
    try:
        admin.autocommit = True
        admin_cur = admin.cursor()
        try:
            try:
                admin_cur.execute(f'CREATE DATABASE "{temp_db}"')
                created = True
            except Exception as exc:
                pytest.skip(f"PostgreSQL role cannot create a temporary database: {exc}")
        finally:
            admin_cur.close()

        test_config = dict(config)
        test_config["database"] = temp_db
        conn = pg8000.dbapi.connect(**test_config)
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    "CREATE TABLE public.legacy_results "
                    "(status boolean NOT NULL, candidate_id text NOT NULL)"
                )
                cur.execute(
                    "INSERT INTO public.legacy_results(status, candidate_id) "
                    "VALUES (true, 'legacy-pass'), (false, 'legacy-fail')"
                )
                conn.commit()

                py_executor.ensure_results_v2_schema(conn)
                py_executor.ensure_results_v2_schema(conn)

                cur.execute(
                    "INSERT INTO public.results_v2 "
                    "(run_id, candidate_id, attempt, outcome, verdict_code) "
                    "VALUES "
                    "('step22-smoke', 'pass', 1, 'PASS', 0), "
                    "('step22-smoke', 'domain-fail', 1, 'DOMAIN_FAIL', 1), "
                    "('step22-smoke', 'timeout', 1, 'TIMEOUT', NULL)"
                )
                conn.commit()

                cur.execute(
                    "SELECT outcome, count(*) FROM public.results_v2 "
                    "WHERE run_id = 'step22-smoke' GROUP BY outcome ORDER BY outcome"
                )
                assert [tuple(row) for row in cur.fetchall()] == [
                    ("DOMAIN_FAIL", 1),
                    ("PASS", 1),
                    ("TIMEOUT", 1),
                ]

                cur.execute(
                    "SELECT count(*), count(*) FILTER (WHERE status), "
                    "count(*) FILTER (WHERE NOT status) FROM public.legacy_results"
                )
                assert tuple(cur.fetchone()) == (2, 1, 1)

                duplicate_rejected = False
                try:
                    cur.execute(
                        "INSERT INTO public.results_v2 "
                        "(run_id, candidate_id, attempt, outcome) "
                        "VALUES ('step22-smoke', 'pass', 1, 'PASS')"
                    )
                    conn.commit()
                except Exception:
                    duplicate_rejected = True
                    conn.rollback()
                assert duplicate_rejected

                cur.execute(
                    "SELECT count(*) FROM public.results_v2 "
                    "WHERE run_id = 'step22-smoke'"
                )
                assert cur.fetchone()[0] == 3
            finally:
                cur.close()
        finally:
            conn.close()
    finally:
        if created:
            try:
                admin_cur = admin.cursor()
                try:
                    admin_cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (temp_db,),
                    )
                    admin_cur.execute(f'DROP DATABASE IF EXISTS "{temp_db}"')
                finally:
                    admin_cur.close()
            finally:
                admin.close()
        else:
            admin.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
