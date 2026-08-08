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

"""STEP 23 targeted harness for the idempotent results_v2 write policy --
the Python mirror of Executor_trunk.com.company.ResultsV2WriterIdempotencyTest
(Java side; schema from ResultsV2SchemaMigrator / ResultsV2Writer, STEP 22/23).

Drives the exact scenario the plan's minimal check calls for: "execute same
tiny batch twice; inspect DB counts; no full workflow" -- a real Postgres
connection and a real results_v2 table, but no py_executor process, no
candidate execution, no full run. Asserts:
  1. the first write of a 3-row batch (one PASS, one DOMAIN_FAIL, one TIMEOUT
     -- the same canonical-outcome spread the Java mirror and STEP 22's
     minimal check used) inserts all three: attempted=3 inserted=3
     already_present=0 updated_selected=0;
  2. replaying the IDENTICAL batch (same run_id/candidate_id/attempt --
     mirrors a re-run, a resumed stage, or a launcher retry of the whole
     executor) inserts NOTHING: attempted=3 inserted=0 already_present=3
     updated_selected=0 -- proving "Повтор того же executor batch не
     удваивает final results";
  3. the table still holds exactly 3 rows after both writes -- the
     (run_id, candidate_id, attempt) unique index did its job at the DB
     layer, not just in the writer's bookkeeping;
  4. attempted == inserted + already_present + updated_selected holds for
     both writes (the launcher-checkable count-consistency invariant action
     item 4 calls for).

Needs a reachable local Postgres -- creates and drops its own temporary
database (never touches an existing one), the same "rollback temporary DB
only" shape STEP 22's minimal check used. Coordinates come from env vars,
never hardcoded (no secrets in source, see plan section 1.4):
  BUNDLE_RESULTS_DB_HOST (default 127.0.0.1), BUNDLE_RESULTS_DB_PORT (default 5432),
  BUNDLE_RESULTS_DB_USER (default postgres), BUNDLE_RESULTS_DB_PASSWORD (required --
  this harness fails closed, not skips, if absent).

Run:  python3 test_results_v2_idempotency.py
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

import pg8000.dbapi

HERE = Path(__file__).resolve().parent
PY_EXECUTOR = HERE / "py_executor.py"

_spec = importlib.util.spec_from_file_location("py_executor_results_v2", PY_EXECUTOR)
py_executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(py_executor)

RUN_ID = "step23-idempotency-smoke-run-1-py"


def _row(candidate_id, attempt, outcome, **extra):
    base = {"run_id": RUN_ID, "candidate_id": candidate_id, "attempt": attempt, "outcome": outcome}
    base.update(extra)
    return base


BATCH = [
    _row("1_0_0", 1, "PASS", verdict_code=0, duration_ms=120, exit_code=0,
         worker="w1", source_hash="abc123", stdout_ref="file:///out/1.out", stderr_ref="file:///out/1.err"),
    _row("2_0_0", 1, "DOMAIN_FAIL", verdict_code=1, verdict_message="verdict != 0", duration_ms=98, exit_code=1,
         worker="w1", source_hash="def456", stdout_ref="file:///out/2.out", stderr_ref="file:///out/2.err"),
    _row("3_0_0", 1, "TIMEOUT", verdict_message="killed: wall clock exceeded", duration_ms=30000, signal="SIGKILL",
         worker="w2", source_hash="ghi789", stdout_ref="file:///out/3.out", stderr_ref="file:///out/3.err"),
]


def check(description, condition):
    print(("  ok  " if condition else "  FAIL ") + description)
    return 0 if condition else 1


def count_rows(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM public.results_v2 WHERE run_id = %s", (RUN_ID,))
        return cur.fetchone()[0]
    finally:
        cur.close()


def main() -> int:
    db_host = os.environ.get("BUNDLE_RESULTS_DB_HOST", "127.0.0.1")
    db_port = int(os.environ.get("BUNDLE_RESULTS_DB_PORT", "5432"))
    db_user = os.environ.get("BUNDLE_RESULTS_DB_USER", "postgres")
    db_password = os.environ.get("BUNDLE_RESULTS_DB_PASSWORD")
    if not db_password:
        print("test_results_v2_idempotency: FAIL -- BUNDLE_RESULTS_DB_PASSWORD is not set "
              "(this harness needs a reachable local Postgres; it fails closed rather than skipping)")
        return 1

    temp_db = f"results_v2_idempotency_smoke_py_{int(time.time() * 1000)}"
    db_created = False
    failures = 1  # pessimistic default -- flipped to the real count only on a clean run

    try:
        admin = pg8000.dbapi.connect(host=db_host, port=db_port, database="postgres",
                                     user=db_user, password=db_password)
        admin.autocommit = True
        try:
            cur = admin.cursor()
            try:
                cur.execute(f'CREATE DATABASE "{temp_db}"')
            finally:
                cur.close()
            db_created = True
        finally:
            admin.close()

        conn = pg8000.dbapi.connect(host=db_host, port=db_port, database=temp_db,
                                    user=db_user, password=db_password)
        try:
            py_executor.ensure_results_v2_schema(conn)
            failures = run_idempotency_checks(conn)
        finally:
            conn.close()
    except Exception as exc:
        print(f"test_results_v2_idempotency: FAIL -- {exc!r}")
        failures = 1
    finally:
        if db_created:
            # "rollback temporary DB only" -- never the database this harness connected
            # through to create it, never any database it didn't itself create.
            try:
                admin = pg8000.dbapi.connect(host=db_host, port=db_port, database="postgres",
                                             user=db_user, password=db_password)
                admin.autocommit = True
                try:
                    cur = admin.cursor()
                    try:
                        cur.execute(f'DROP DATABASE IF EXISTS "{temp_db}" WITH (FORCE)')
                    finally:
                        cur.close()
                finally:
                    admin.close()
            except Exception as drop_exc:
                print(f"test_results_v2_idempotency: WARNING -- could not drop temp database "
                      f"{temp_db!r}: {drop_exc!r}")

    print("test_results_v2_idempotency: ALL OK" if failures == 0
          else f"test_results_v2_idempotency: {failures} FAILURE(S)")
    return 0 if failures == 0 else 1


def run_idempotency_checks(conn) -> int:
    failures = 0

    first = py_executor.write_results_v2_batch(conn, BATCH)
    failures += check(
        "first write of a fresh 3-row batch inserts all three "
        f"(attempted=3 inserted=3 already_present=0 updated_selected=0) -- got {first}",
        first == {"attempted": 3, "inserted": 3, "already_present": 0, "updated_selected": 0})

    replay = py_executor.write_results_v2_batch(conn, BATCH)
    failures += check(
        "replaying the IDENTICAL batch inserts nothing -- the (run_id, candidate_id, "
        "attempt) unique key turns every row into \"already present\" "
        f"(attempted=3 inserted=0 already_present=3 updated_selected=0) -- got {replay}",
        replay == {"attempted": 3, "inserted": 0, "already_present": 3, "updated_selected": 0})

    failures += check(
        "count consistency holds for the first write: "
        "attempted == inserted + already_present + updated_selected",
        first["attempted"] == first["inserted"] + first["already_present"] + first["updated_selected"])
    failures += check(
        "count consistency holds for the replay: "
        "attempted == inserted + already_present + updated_selected",
        replay["attempted"] == replay["inserted"] + replay["already_present"] + replay["updated_selected"])

    row_count = count_rows(conn)
    failures += check(
        "the table holds exactly 3 rows after BOTH writes -- \"Повтор того же executor "
        "batch не удваивает final results\" holds at the DB layer (unique index), not "
        f"just in the writer's bookkeeping -- got {row_count}",
        row_count == 3)

    return failures


if __name__ == "__main__":
    sys.exit(main())
