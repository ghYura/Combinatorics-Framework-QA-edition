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

r"""py_executor — a Python Executor analog for the Combinatorics Bundle.

The Bundle's real Executor (Executor_trunk, com.company.MainWatch) compiles & runs
ONLY Java candidates (Janino/JDK in-JVM). This is its Python counterpart: it consumes
the SAME Reader->Executor file-watch handshake, runs each reassembled .py candidate in
isolation, extracts the FW_VAR / FW_CUSTOM_VAR verdict, and writes a verdict row into
the same Results DB -- replicating MainWatch.SqlRecord.bind() EXACTLY (positional NULL
encoding of the combos* boolean columns; FW_VAR vs FW_CUSTOM_VAR mode chosen by the
'?' count of insert.sql, == 6 -> custom).

Differences from the Java Executor, all deliberate hardening:
  * clean per-run flush in ONE transaction at the end (no %200 tail-loss, no idle-flush
    race -- the Java side's known-fragile plumbing);
  * candidates run as isolated subprocesses with a timeout;
  * cold-start by design (scan everything present), with an optional idle-watch tail.

Handshake (same dirs/files the Reader writes; MainWatch flag names mirrored):
  -srcDirList DIR        dir of <combi_id>_0_0.py candidates to run
  -dirResultsDbURL DIR   contains resultsDbURL.properties (jdbc:postgresql://h:p/db?user=&password=)
  -dirSqlTemplate DIR    contains insert.sql (INSERT ... VALUES (?,?,...)); '?' count -> mode
  -dirArguments DIR      contains args (argv for the candidate) and fwVar.shift (int)
  -dirRunFirstOnce DIR   optional; runmefirstonce.first (Java RunMeFirstOnce -- ignored for Python)
  -out2 DIR              optional; also write the flushed tuples as <n>.sql (parity with Java)
  --writeToDB true|false (default true)   --failOnly true|false (default true)
  --passSource true|false (default false) also store source for PASSES (success-is-result runs)
  --watchSeconds N       after the cold scan, keep watching for new files until N s idle (default 0)
  --python PATH          interpreter for candidates (default: this interpreter)

Handoff v2 (STEP 18, optional, preferred once the Reader writes it -- STEP 17):
  --manifest PATH        bundle.handoff/v2 manifest.json (see generator_trunk's
                         bundle-handoff-v2.schema.json / bundle.handoff.HandoffV2).
                         When given, it -- not '?' inference, -srcDirList, or the
                         legacy resultsDbURL/arguments/runFirstOnce dirs -- is the
                         SOLE source of truth for the candidate dir to run from,
                         run identity, candidate accounting, verdict mode, DB
                         host/port/database/user, argv, shift and the RunMeFirstOnce
                         preprocessor path (Java stub ignored; host execution
                         refused by secure profiles): only its declared "loose-files"
                         source is scanned/executed (-srcDirList becomes optional --
                         a redundant cross-check that must agree if present, never
                         an independent path). py_executor only runs language=
                         "python" manifests (it is the Python Executor analog --
                         a "java" manifest would reconcile *.java counts yet leave
                         it scanning 0 *.py files, silently producing processed=0).
                         The manifest NEVER carries the SQL template text or the DB
                         password (P3/P14): -dirSqlTemplate is still read for
                         insert.sql, and the password comes from
                         BUNDLE_RESULTS_DB_PASSWORD in the environment.
                         -dirResultsDbURL/-dirArguments/-dirRunFirstOnce are
                         ignored once a manifest validates.
  --runId ID             optional; if given, must equal the manifest's run_id
  --resultFile PATH      optional; on completion, also write a JSON result
                         (processed/pass/fail/broken/inserted/outcomes/
                         duration_seconds/manifest_protocol/
                         candidate_count_reconciliation) next to the existing
                         text completion summary. `outcomes` is the canonical
                         PASS/DOMAIN_FAIL/BROKEN/TIMEOUT/INFRA_FAIL/SKIPPED/
                         CANCELLED breakdown (STEP 21); pass/fail/broken stay
                         as the legacy boolean-status projection.
  Without --manifest, the legacy directory handshake is used as a fallback
  (with a warning) -- both paths must keep working until the Reader/launcher
  finish migrating (STEP 17/20).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pg8000.dbapi

# STEP 28: the sandbox backend layer lives in the sibling module `sandbox.py`.
# Import it by path so this works both when py_executor is run as a script and
# when it is loaded via importlib in tests (where Executor_trunk is not on
# sys.path). A failed import leaves _sandbox=None: legacy/no-policy runs do not
# need it, and a secure policy that DOES require it fails closed in main().
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import sandbox as _sandbox
except Exception:                          # pragma: no cover - sandbox optional for legacy runs
    _sandbox = None

# STEP 32: streaming reader for the "sharded" candidate transport (ShardSink). Sibling
# module, stdlib-only; loaded the same path-relative way as `sandbox`.
import shard_reader
# STEP 33: deterministic sharding + local worker pool (sibling module, stdlib-only).
import worker_pool
# STEP 34: cross-process backpressure / bounded-queue coordinator (sibling module, stdlib-only).
import backpressure

HANDOFF_PROTOCOL = "bundle.handoff/v2"
DB_PASSWORD_ENV_VAR = "BUNDLE_RESULTS_DB_PASSWORD"
CAPABILITY_SCHEMA = "py_executor.capabilities/v1"


def capability_document() -> dict:
    """Machine-readable, side-effect-free launcher preflight contract."""
    return {
        "schema": CAPABILITY_SCHEMA,
        "repeat": {
            "local_metrics": True,
            "local_all": True,
            "max_k": 1024,
            "raw_sample_identity": True,
            "runtime_accounting": True,
        },
        # Plan-1 Phase 3b: the results_v2 identity this binary writes. The launcher reads this BEFORE
        # the executor connects and fences out any artifact that does not advertise the 5-column
        # sample-identity writer (docs/24 §1.6) -- a genuinely-old binary cannot report it, so it is
        # rejected before its ensureSchema could resurrect the legacy 3-column index.
        "results_v2_schema": {
            "version": RESULTS_V2_SCHEMA_VERSION,
            "unique_index": RESULTS_V2_SAMPLE_INDEX_NAME,
            "sample_identity_writer": True,
        },
    }


# ------------------------- canonical outcome model (STEP 21) ----------------- #
# Mirrors generator_trunk.bundle.models.Outcome; kept as a plain str enum here
# (no generator_trunk import, see _write_json_atomic) so this script stays
# standalone. Separates the DOMAIN verdict (PASS/DOMAIN_FAIL -- a property of
# the candidate under test) from INFRASTRUCTURE outcomes (BROKEN/TIMEOUT/
# INFRA_FAIL/SKIPPED/CANCELLED -- properties of the run itself): a candidate
# that times out is not "the same kind of failure" as one that legitimately
# fails its domain check, and conflating them under one "broken" bucket hid
# that distinction from the launcher and the Results consumers.
class Outcome:
    PASS = "PASS"
    DOMAIN_FAIL = "DOMAIN_FAIL"
    BROKEN = "BROKEN"
    TIMEOUT = "TIMEOUT"
    INFRA_FAIL = "INFRA_FAIL"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"

    ALL = (PASS, DOMAIN_FAIL, BROKEN, TIMEOUT, INFRA_FAIL, SKIPPED, CANCELLED)


# ------------------- additive Results DB schema v2 (STEP 22) ----------------- #
# Mirrors Executor_trunk.com.company.ResultsV2SchemaMigrator (Java side) --
# both Executors connect to the same Postgres Results DB, so both must apply
# the identical additive DDL. `results_v2` records the canonical per-candidate
# Outcome above plus provenance the legacy positional table (created by
# Reader_trunk.ResultsDbProvisioner, populated via the `insert.sql` handshake
# template) has no room for: attempt, duration, exit/signal, worker, source
# hash, stdout/stderr refs, created timestamp. Strictly additive -- never
# alters or drops the legacy table; legacy consumers (boolean `status`) keep
# working unchanged. STEP 23 persists canonical rows after legacy outcomes
# have reached their final classification.
#
# `CREATE ... IF NOT EXISTS` makes this a repeatable migration: idempotent, a
# no-op once applied, safe on every connect. The (run_id, candidate_id,
# attempt) unique index backs STEP 23's idempotent-write policy ("one row per
# attempt, no uncontrolled duplicates on retry/replay" -- a repeat insert for
# the same attempt is an explicit conflict to handle, not a silent duplicate).
# candidate_id is the canonical composite identity string (legacy resRepl
# shape: combi_id_final_combi_id_optional_fw_optJ) kept as text so the schema
# stays backend-neutral. STEP 23 writes canonical outcomes through the
# idempotent batch writer after legacy classifications finalize.
RESULTS_V2_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.results_v2 (
    id              bigserial PRIMARY KEY,
    run_id          text NOT NULL,
    candidate_id    text NOT NULL,
    attempt         integer NOT NULL DEFAULT 1,
    outcome         text NOT NULL,
    verdict_code    integer,
    verdict_message text,
    duration_ms     bigint,
    exit_code       integer,
    signal          text,
    worker          text,
    source_hash     text,
    stdout_ref      text,
    stderr_ref      text,
    policy_id       text,
    policy_hash     text,
    repeat_idx      integer NOT NULL DEFAULT 0,
    env_id          text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now()
)
"""

# Plan-1 Phase 3b (docs/24 §1.4/§1.6/§1.7): the SAMPLE-identity unique index. Identity is the
# 5-column sample key (run_id, candidate_id, attempt, repeat_idx, env_id) -- `attempt` (external
# retry) is nested INSIDE the (candidate_id, repeat_idx, env_id) sample, so two repeats of one
# candidate are distinct rows, NOT a uniqueness conflict. At K=1 every row carries the defaults
# repeat_idx=0, env_id='', so 5-column uniqueness is identical to the retired 3-column key: the same
# rows are accepted and the same replays dedupe, i.e. K=1 idempotency is behavior-preserving.
# Mirrors Java ResultsV2SchemaMigrator.CREATE_SAMPLE_INDEX_SQL.
RESULTS_V2_CREATE_SAMPLE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS results_v2_sample_uk
    ON public.results_v2 (run_id, candidate_id, attempt, repeat_idx, env_id)
"""

# Retire the legacy 3-column key once the 5-column sample index exists. The two CANNOT coexist for
# K>1 (the 3-col index would reject two repeats differing only in repeat_idx/env_id), and the
# writer's ON CONFLICT target is co-versioned with the live index. `DROP INDEX IF EXISTS` makes the
# cutover idempotent and a no-op on a DB already migrated. Mirrors Java
# ResultsV2SchemaMigrator.DROP_LEGACY_INDEX_SQL.
RESULTS_V2_DROP_LEGACY_INDEX_SQL = """
DROP INDEX IF EXISTS public.results_v2_run_candidate_attempt_uk
"""

# Plan-1 Phase 3b launcher-side schema safety (docs/24 §1.6). The schema_meta stamp records WHICH
# unique-identity the live results_v2 is on, so a writer can fail closed at connect when its
# ON CONFLICT arity != the live index (RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH) instead of risking a
# silent duplicate or a raw crash. Version 2 == the 5-column sample identity (version 1 was the
# retired 3-column key; no DB ever carried a meta stamp under it -- the table is introduced with 3b).
RESULTS_V2_SCHEMA_VERSION = 2
RESULTS_V2_SAMPLE_INDEX_NAME = "results_v2_sample_uk"
RESULTS_V2_LEGACY_INDEX_NAME = "results_v2_run_candidate_attempt_uk"
RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH = "RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH"

RESULTS_V2_CREATE_SCHEMA_META_SQL = """
CREATE TABLE IF NOT EXISTS public.results_v2_schema_meta (
    id           integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    version      integer NOT NULL,
    unique_index text NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
)
"""

# Singleton (id=1) upsert: re-stamping an already-migrated DB just refreshes version/unique_index/ts.
# Values are code constants (int + a safe identifier literal), inlined so ensure_results_v2_schema
# applies it with a single-arg execute like the rest of its DDL (mirrors the Java STAMP_SCHEMA_META_SQL).
RESULTS_V2_STAMP_SCHEMA_META_SQL = f"""
INSERT INTO public.results_v2_schema_meta (id, version, unique_index, updated_at)
VALUES (1, {RESULTS_V2_SCHEMA_VERSION}, '{RESULTS_V2_SAMPLE_INDEX_NAME}', now())
ON CONFLICT (id) DO UPDATE
    SET version = EXCLUDED.version, unique_index = EXCLUDED.unique_index, updated_at = now()
"""

# STEP 27: the execution policy (bundle/policy.py) each candidate ran under.
# Additive + repeatable like the table itself -- `ADD COLUMN IF NOT EXISTS` makes
# this a no-op on a fresh table (the columns are already in CREATE_TABLE above)
# AND backfills the two columns onto a results_v2 created by an older executor,
# so a DB migrated before STEP 27 gains them on the next connect. Mirrors the
# Java ResultsV2SchemaMigrator.ADD_POLICY_COLUMNS_SQL.
RESULTS_V2_ADD_POLICY_COLUMNS_SQL = """
ALTER TABLE public.results_v2
    ADD COLUMN IF NOT EXISTS policy_id   text,
    ADD COLUMN IF NOT EXISTS policy_hash text
"""

# Plan-1 Phase 3a/3b (docs/24 §1.6/§1.7): the per-candidate repeat SAMPLE identity. `repeat_idx`
# (0..K-1) is the intentional repeat; `env_id` is the assignment-time executor environment.
# Additive + repeatable like the policy columns above: a no-op on a fresh table and a backfill
# onto a pre-Phase-3 table (existing rows get the K=1 defaults repeat_idx=0, env_id=''). Phase 3b
# promotes these from carried-but-unindexed columns to part of the unique identity: the index is the
# 5-column sample key and the INSERT's ON CONFLICT target matches it (see
# RESULTS_V2_CREATE_SAMPLE_INDEX_SQL). The defaults keep K=1 behavior-preserving -- a run with K
# forced to 1 writes repeat_idx=0/env_id='' on every row, so the 5-col key dedupes exactly as the
# old 3-col key did. Mirrors Java ResultsV2SchemaMigrator.ADD_REPEAT_COLUMNS_SQL.
RESULTS_V2_ADD_REPEAT_COLUMNS_SQL = """
ALTER TABLE public.results_v2
    ADD COLUMN IF NOT EXISTS repeat_idx integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS env_id     text    NOT NULL DEFAULT ''
"""


def ensure_results_v2_schema(conn) -> None:
    """Repeatable migration entry point -- applies the additive DDL above.
    Idempotent: a second call against an already-migrated DB runs the same
    `IF NOT EXISTS` statements and changes nothing. Raises on genuine DB
    errors so callers can decide how to react. This function owns its short
    migration transaction: it commits only after both statements succeed and
    rolls back before re-raising on any failure. The rollback is required
    because the connect-time caller treats migration failure as non-fatal and
    continues using the same connection for the legacy insert flow."""
    cur = conn.cursor()
    try:
        cur.execute(RESULTS_V2_CREATE_TABLE_SQL)
        cur.execute(RESULTS_V2_ADD_POLICY_COLUMNS_SQL)   # STEP 27: backfill on pre-existing tables
        cur.execute(RESULTS_V2_ADD_REPEAT_COLUMNS_SQL)   # Plan-1 Phase 3a: repeat_idx/env_id backfill
        # Plan-1 Phase 3b: cut the unique identity over to the 5-column sample key, THEN retire the
        # legacy 3-column key. Create-before-drop (both in this one transaction) so the table is
        # never left without a unique key; idempotent (IF [NOT] EXISTS) and safe on existing tables
        # because every backfilled row carries repeat_idx=0/env_id='' (the 5-col index can't find a
        # collision the 3-col index didn't already forbid).
        cur.execute(RESULTS_V2_CREATE_SAMPLE_INDEX_SQL)
        cur.execute(RESULTS_V2_DROP_LEGACY_INDEX_SQL)
        # Plan-1 Phase 3b: stamp the schema-capability meta so a writer can validate the live
        # identity at connect and fail closed on a mismatch (docs/24 §1.6).
        cur.execute(RESULTS_V2_CREATE_SCHEMA_META_SQL)
        cur.execute(RESULTS_V2_STAMP_SCHEMA_META_SQL)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()


class ResultsV2SchemaCapabilityMismatch(Exception):
    """The live results_v2 schema does not match this writer's 5-column sample-identity contract.

    Plan-1 Phase 3b (docs/24 §1.6): a writer probes the live schema at connect and fails CLOSED on a
    mismatch instead of risking a silent duplicate (its ``ON CONFLICT`` arity != the live unique
    index) or a raw crash. The message is prefixed ``RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH`` so the
    launcher and logs can detect it unambiguously. Mirrors the Java
    ResultsV2SchemaMigrator.SchemaCapabilityMismatch."""


def validate_results_v2_schema_capability(conn) -> None:
    """Fail closed unless the live results_v2 schema is on the 5-column sample identity this writer
    upserts against (docs/24 §1.6). Checks, in order: (1) the schema_meta stamp is present and on
    this writer's version + sample-index identity; (2) the live unique index named
    ``results_v2_sample_uk`` exists on exactly the 5 sample columns; (3) the retired 3-column index
    was not resurrected (an old binary's ``ensureSchema`` re-creates it, and the two cannot coexist
    for K>1). Raises :class:`ResultsV2SchemaCapabilityMismatch` on any failure; returns None when the
    live schema matches. Read-only -- never mutates the schema."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT version, unique_index FROM public.results_v2_schema_meta WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            raise ResultsV2SchemaCapabilityMismatch(
                f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: results_v2_schema_meta stamp is missing -- "
                f"the DB has not been migrated to the version {RESULTS_V2_SCHEMA_VERSION} "
                f"sample-identity schema")
        version, unique_index = int(row[0]), str(row[1])
        if version != RESULTS_V2_SCHEMA_VERSION or unique_index != RESULTS_V2_SAMPLE_INDEX_NAME:
            raise ResultsV2SchemaCapabilityMismatch(
                f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: live schema version={version} "
                f"unique_index={unique_index!r} != this writer's version={RESULTS_V2_SCHEMA_VERSION} "
                f"unique_index={RESULTS_V2_SAMPLE_INDEX_NAME!r}")
        cur.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND tablename='results_v2' AND indexname = %s", (RESULTS_V2_SAMPLE_INDEX_NAME,))
        idx = cur.fetchone()
        idxdef = " ".join(idx[0].split()).lower() if idx else ""
        if "unique index" not in idxdef or "(run_id, candidate_id, attempt, repeat_idx, env_id)" not in idxdef:
            raise ResultsV2SchemaCapabilityMismatch(
                f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: the live unique index "
                f"{RESULTS_V2_SAMPLE_INDEX_NAME!r} is missing or is not the 5-column sample key "
                f"(found: {idxdef or 'none'})")
        cur.execute("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND tablename='results_v2' "
                    "AND indexname = %s", (RESULTS_V2_LEGACY_INDEX_NAME,))
        if cur.fetchone() is not None:
            raise ResultsV2SchemaCapabilityMismatch(
                f"{RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH}: the legacy 3-column index "
                f"{RESULTS_V2_LEGACY_INDEX_NAME!r} was resurrected (an old executor binary); it "
                f"conflicts with the 5-column sample key and must not coexist")
    finally:
        cur.close()


# --------------------- idempotent results_v2 writes (STEP 23) ---------------- #
# Mirrors Executor_trunk.com.company.ResultsV2Writer (Java side) -- both
# Executors connect to the same Postgres Results DB and must apply the
# identical write policy, or a mixed-language run could duplicate or silently
# overwrite rows depending on which Executor touched a candidate first.
#
# Policy (acceptance: "Count semantics документированы в schema comments/code"):
#   * Immutable samples: a (run_id, candidate_id, attempt, repeat_idx, env_id)
#     row, once written, is never modified. `INSERT ... ON CONFLICT (run_id,
#     candidate_id, attempt, repeat_idx, env_id) DO NOTHING` -- never `DO
#     UPDATE` -- so replaying a batch (resume, retry, re-run) cannot overwrite
#     or duplicate a landed row. This is what "Повтор того же executor batch не
#     удваивает final results" and "no silent overwrite" require.
#   * Sample identity (Plan-1 Phase 3b): backed by the results_v2_sample_uk
#     index (RESULTS_V2_CREATE_SAMPLE_INDEX_SQL) -- identity is the 5-column
#     (run, candidate, attempt, repeat_idx, env_id) sample key. `attempt`
#     (external retry) is nested INSIDE the (candidate, repeat_idx, env_id)
#     sample, so one candidate legitimately produces one row per attempt AND one
#     sample per repeat/env. At K=1 every row carries repeat_idx=0/env_id='', so
#     this dedupes exactly as the retired 3-column key did.
#   * One selected/final result is a READ-time concern: the row with the
#     highest attempt number is final (ORDER BY attempt DESC LIMIT 1 per
#     run/candidate). This writer never UPDATEs or deletes a row to "select"
#     it -- doing so would break immutability and could race a concurrently-
#     inserted later attempt. `updated_selected` in the returned counts
#     therefore
#     stays 0 by design -- carried explicitly (not omitted) so the policy is
#     visible in the count tuple's shape, not silently absent.
#   * Attempts traceable: every attempt -- including ones a retry later
#     supersedes -- keeps its own immutable row; the full attempt history for
#     a candidate is always reconstructable from results_v2 alone.
#   * Retry creates a new attempt, not a new candidate (a CONTRACT for callers
#     -- not enforced here; retry mechanics live in the launcher/resume
#     machinery). On retry after BROKEN/TIMEOUT/INFRA_FAIL, callers MUST keep
#     candidate_id stable and pass attempt+1; minting a fresh candidate_id for
#     the same underlying candidate would defeat both the unique key and
#     "Attempts traceable".
#
# Transaction shape: one transaction per bounded batch (mirrors the legacy
# flush-on-batch commit), explicit per-row conflict handling (ON CONFLICT ...
# DO NOTHING, not a whole-batch catch) so one candidate's replay does not block
# its batch-mates from landing.
RESULTS_V2_IDEMPOTENT_INSERT_SQL = """
INSERT INTO public.results_v2
    (run_id, candidate_id, attempt, outcome, verdict_code, verdict_message,
     duration_ms, exit_code, signal, worker, source_hash, stdout_ref, stderr_ref,
     policy_id, policy_hash, repeat_idx, env_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (run_id, candidate_id, attempt, repeat_idx, env_id) DO NOTHING
"""
# ON CONFLICT (columns) -- column-list inference, not ON CONFLICT ON
# CONSTRAINT <name> -- because RESULTS_V2_CREATE_SAMPLE_INDEX_SQL provisions a
# plain CREATE UNIQUE INDEX, not a named UNIQUE table constraint, and Postgres
# only accepts ON CONFLICT ON CONSTRAINT for the latter (mirrors the Java
# writer's identical reasoning -- see ResultsV2Writer.IDEMPOTENT_INSERT_SQL).
# The arity here (5 columns) is co-versioned with the live unique index: it must
# match results_v2_sample_uk, never the retired 3-column key.


def write_results_v2_batch(conn, rows, do_commit=True):
    """Idempotent batched write -- the Python mirror of
    ResultsV2Writer.writeBatch(Connection, List<CanonicalResult>).

    STEP 33: pass ``do_commit=False`` to accumulate the rows in the CALLER's open
    transaction (the legacy Results inserts) without committing/rolling back here, so a
    single combined commit persists legacy + results_v2 atomically -- a results_v2 failure
    then rolls the legacy inserts back too, leaving nothing for a resume to duplicate.

    `rows` is an iterable of dicts with keys matching the INSERT column list
    (run_id, candidate_id, attempt, outcome, verdict_code, verdict_message,
    duration_ms, exit_code, signal, worker, source_hash, stdout_ref,
    stderr_ref, policy_id, policy_hash, repeat_idx, env_id); any nullable column
    whose key is absent or `None` is written as SQL NULL. The two sample-identity
    columns are NOT NULL, so an absent/None `repeat_idx`/`env_id` is written as
    the K=1 default (0 / '') -- a caller that does not yet thread per-sample
    identity (today's K=1 writers) still produces valid, dedupe-correct rows.

    Returns a dict {"attempted", "inserted", "already_present",
    "updated_selected"} -- the four buckets the executor summary reports
    (action item 3). `attempted == inserted + already_present +
    updated_selected` always holds (the launcher-checkable count-consistency
    invariant action item 4 calls for); `updated_selected` is always 0 for
    this writer (see the "one selected/final result" policy note above).

    One transaction for the whole batch: it commits only if every row's
    conflict-or-insert succeeds, and rolls back -- leaving no partial trace,
    exactly like the legacy per-batch commit/rollback this mirrors -- on any
    failure, before re-raising. Conflict detection relies on pg8000 reporting
    `cur.rowcount == 0` for a row the `ON CONFLICT ... DO NOTHING` clause
    skipped (it changed nothing) and `cur.rowcount == 1` for a row it actually
    wrote -- so `rowcount == 0` <=> "already present"."""
    columns = ("run_id", "candidate_id", "attempt", "outcome", "verdict_code", "verdict_message",
               "duration_ms", "exit_code", "signal", "worker", "source_hash", "stdout_ref", "stderr_ref",
               "policy_id", "policy_hash", "repeat_idx", "env_id")
    # The two sample-identity columns are NOT NULL with K=1 defaults; coalesce an absent/None value
    # to the default so a K=1 writer that omits them still binds a valid, dedupe-correct row.
    def _col_value(row, c):
        v = row.get(c)
        if c == "repeat_idx":
            return 0 if v is None else int(v)
        if c == "env_id":
            return "" if v is None else str(v)
        return v
    rows = list(rows)
    attempted = len(rows)
    if attempted == 0:
        return {"attempted": 0, "inserted": 0, "already_present": 0, "updated_selected": 0}

    cur = conn.cursor()
    inserted = 0
    try:
        for row in rows:
            cur.execute(RESULTS_V2_IDEMPOTENT_INSERT_SQL, tuple(_col_value(row, c) for c in columns))
            if cur.rowcount and cur.rowcount > 0:
                inserted += 1
        if do_commit:
            conn.commit()
    except Exception:
        if do_commit:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        cur.close()

    already_present = attempted - inserted
    return {"attempted": attempted, "inserted": inserted,
            "already_present": already_present, "updated_selected": 0}


def commit_legacy_and_v2(conn, run_id, v2_rows):
    """STEP 33 (review fix): persist the legacy Results inserts (already accumulated on
    ``conn`` by the per-candidate loop) AND the results_v2 rows in ONE transaction with a
    SINGLE commit. The results_v2 rows are inserted WITHOUT their own commit, then one
    ``conn.commit()`` makes both durable together.

    Why it matters: previously the legacy commit ran first and a later results_v2 failure left
    the legacy rows committed while the worker exited non-zero (completed_successfully=False) --
    a resume then re-ran the worker and DUPLICATED the already-committed legacy inserts. With a
    single transaction, any failure (results_v2 insert OR the commit) rolls EVERYTHING back, so
    a resume re-runs against an empty slate. Returns the results_v2 write counts; raises on any
    failure (caller reclassifies to INFRA_FAIL, exits non-zero, leaves the checkpoint incomplete).
    """
    v2_counts = {"attempted": len(v2_rows), "inserted": 0, "already_present": 0, "updated_selected": 0}
    try:
        if run_id and v2_rows:
            v2_counts = write_results_v2_batch(conn, [v2_rows[k] for k in sorted(v2_rows)], do_commit=False)
        conn.commit()                       # SINGLE commit: legacy inserts + results_v2 together
        return v2_counts
    except Exception:
        try:
            conn.rollback()                 # roll BOTH back -- nothing persisted, resume-safe
        except Exception:
            pass
        raise


# ----------------------------- handshake parsing ----------------------------- #
def parse_jdbc(url: str) -> dict:
    m = re.search(r"jdbc:postgresql://([^:/]+):(\d+)/([^?]+)(\?(.*))?", url.strip())
    if not m:
        raise SystemExit(f"py_executor: cannot parse JDBC URL: {url!r}")
    host, port, db, _, qs = m.groups()
    params = dict(kv.split("=", 1) for kv in (qs or "").split("&") if "=" in kv)
    return {"host": host, "port": int(port), "database": db,
            "user": params.get("user", "postgres"), "password": params.get("password", "")}


def _first_file(d, *names):
    p = Path(d)
    for n in names:
        if (p / n).is_file():
            return p / n
    fs = [f for f in p.iterdir() if f.is_file()] if p.is_dir() else []
    return fs[0] if fs else None


def read_handshake(args: dict) -> dict:
    url_f = _first_file(args["dirResultsDbURL"], "resultsDbURL.properties")
    sql_f = _first_file(args["dirSqlTemplate"], "insert.sql")
    if not url_f or not sql_f:
        raise SystemExit("py_executor: missing resultsDbURL.properties or insert.sql in handshake dirs")
    url = url_f.read_text(encoding="utf-8").strip()
    url = next((ln for ln in url.splitlines() if ln.startswith("jdbc:")), url)
    insert_sql = sql_f.read_text(encoding="utf-8").strip().rstrip(";")
    n_q = insert_sql.count("?")
    custom_mode = (n_q == 6)                   # MainWatch: FW_CUSTOM_VARmode = (questionCharsNumber == 6)

    argv, shift = [], 0
    ad = Path(args.get("dirArguments") or "")
    if (ad / "args").is_file():
        argv = (ad / "args").read_text(encoding="utf-8").strip().split()
    if (ad / "fwVar.shift").is_file():
        t = (ad / "fwVar.shift").read_text(encoding="utf-8").strip()
        shift = int(t) if t else 0
    preprocess = None
    rfo_dir = Path(args.get("dirRunFirstOnce") or "")
    rfo_f = rfo_dir / "runmefirstonce.first" if rfo_dir.is_dir() else None
    if rfo_f and rfo_f.exists() and rfo_f.stat().st_size > 0:
        preprocess = rfo_f
    # STEP 27: best-effort policy lookup even on the legacy handshake path --
    # the launcher writes execution_policy.json under the handshake's handoff/
    # dir; absent it, (None, None) -> SQL NULLs (legacy/rollback runs).
    _roots = [Path(args[k]).parent for k in ("dirSqlTemplate", "dirArguments", "dirRunFirstOnce") if args.get(k)]
    _search = [p for r in _roots for p in (r / "handoff", r)]
    policy_id, policy_hash, policy_doc = _load_execution_policy(*_search)
    return {"db": parse_jdbc(url), "insert_sql": insert_sql, "n_q": n_q,
            "custom_mode": custom_mode, "argv": argv, "shift": shift,
            "preprocess": preprocess, "manifest": None, "srcdir": None,
            "policy_id": policy_id, "policy_hash": policy_hash, "policy": policy_doc,
            "candidate_reconciliation": None}


# ------------------------------ Handoff v2 manifest --------------------------- #
# Candidate file extension per `language` -- mirrors py_executor's own
# list_candidates() (".py") and Reader's HandoffManifestWriter.describeSourceDir,
# which lists only `*<FW_FILE_EXTENSION>` files (".py" <-> language="python").
_LANGUAGE_EXTENSION = {"python": ".py", "java": ".java"}


def _candidate_names(p: Path, ext: str) -> list:
    return sorted(f.name for f in p.iterdir() if f.is_file() and f.name.endswith(ext))


def _sources_dir_digest(names: list) -> str:
    """sha256 over the sorted candidate name list, one line at a time --
    byte-for-byte what Reader's sha256OfLines (HandoffManifestWriter.java)
    produces: ``md.update((name + "\\n").getBytes(UTF_8))`` per name, NOT a
    single "\\n".join(...) (which drops the final newline when non-empty)."""
    md = hashlib.sha256()
    for name in names:
        md.update((name + "\n").encode("utf-8"))
    return md.hexdigest()


def _load_execution_policy(*search_dirs) -> tuple:
    """STEP 27/28: read the ``(id, sha256, policy)`` of the execution policy
    (bundle/policy.py) this run's candidates execute under, from the secret-free
    ``execution_policy.json`` the launcher writes next to the handoff manifest.

    Returns ``(policy_id, policy_hash, policy)`` where ``policy`` is the full
    policy dict STEP 28's sandbox backend needs (``backend``, the resource/fs/
    network/env limits); ``(None, None, None)`` when no such file is found (older
    runs / a pure-legacy handshake) so the executor records SQL NULLs into
    ``results_v2.policy_id/policy_hash`` and runs the legacy unsandboxed path
    rather than failing."""
    for d in search_dirs:
        if not d:
            continue
        try:
            ep = json.loads((Path(d) / "execution_policy.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid, phash = ep.get("id"), ep.get("sha256")
        policy = ep.get("policy") if isinstance(ep.get("policy"), dict) else None
        return ((pid if isinstance(pid, str) else None),
                (phash if isinstance(phash, str) else None), policy)
    return None, None, None


def read_manifest(manifest_path: Path, args: dict) -> dict:
    """Load + validate a ``bundle.handoff/v2`` manifest (STEP 16/17) and adapt
    it into the same shape ``read_handshake`` returns, so ``main`` need not
    care which contract produced it.

    The manifest is the source of truth for run identity, candidate counts,
    verdict mode, DB host/port/database/user, argv, shift and the RunMeFirstOnce
    preprocessor -- but it deliberately never carries the SQL template text
    (P14: "result_schema_mode ... Never the SQL text itself") or the DB
    password (P3/P14: "result_target ... NEVER carries a password"), so those
    two still come from -dirSqlTemplate and the environment respectively.
    """
    try:
        raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"py_executor: cannot read manifest {manifest_path!r}: {exc}")

    protocol = raw.get("protocol")
    if protocol != HANDOFF_PROTOCOL:
        raise SystemExit(f"py_executor: manifest protocol {protocol!r} != expected {HANDOFF_PROTOCOL!r}")

    run_id = raw.get("run_id") or ""
    if not run_id.strip():
        raise SystemExit("py_executor: manifest run_id is empty")
    expected_run_id = args.get("runId")
    if expected_run_id and expected_run_id != run_id:
        raise SystemExit(f"py_executor: manifest run_id {run_id!r} != expected --runId {expected_run_id!r}")

    language = raw.get("language")
    if language != "python":
        # py_executor is the *Python* Executor analog -- it only ever compiles/
        # runs `*.py` candidates (see module docstring / list_candidates). A
        # language="java" manifest would still pass count reconciliation against
        # `*.java` files yet leave list_candidates() scanning 0 `*.py` files,
        # silently producing processed=0 instead of failing loudly.
        raise SystemExit(f"py_executor: manifest language {language!r} -- "
                         f"py_executor only runs \"python\" candidates (use the Java Executor for \"java\")")
    ext = _LANGUAGE_EXTENSION[language]
    transport = raw.get("candidate_transport")
    if transport not in ("loose-files", "sharded"):
        raise SystemExit(f"py_executor: manifest candidate_transport {transport!r} "
                         f"is not supported (only \"loose-files\"/\"sharded\")")

    sources = raw.get("sources") or []
    if len(sources) != 1:
        raise SystemExit(f"py_executor: a {transport!r} manifest must declare exactly one "
                         f"source, got {len(sources)}")
    src = sources[0]
    sp = Path(src["path"])
    if not sp.is_dir():
        raise SystemExit(f"py_executor: manifest source path does not exist: {src['path']!r}")

    # The manifest's declared source IS the candidate dir to run from --
    # source of truth, not -srcDirList (legacy flag, optional once a manifest
    # validates). If both are given and disagree, the two contracts have
    # silently diverged and execution would read from the wrong place.
    declared_srcdir = args.get("srcDirList")
    if declared_srcdir and Path(declared_srcdir).resolve() != sp.resolve():
        raise SystemExit(f"py_executor: -srcDirList {declared_srcdir!r} does not match "
                         f"the manifest's source path {src['path']!r}")

    declared_count = raw["candidate_count"]
    sha = src.get("sha256")
    if transport == "sharded":
        # STEP 32: candidates live inside *.fwshard containers; the count is the sum of
        # records across VALID finalized shards, and the source digest is sha256 over the
        # sorted *.fwshard name list (symmetric with Reader's describeShardDir). A corrupt
        # / partial shard contributes 0 records -> count shortfall -> fail closed.
        shard_names = sorted(p.name for p in shard_reader.list_finalized_shards(sp))
        actual_count = shard_reader.corpus_count(sp)
        found_desc = f"{actual_count} candidate(s) across {len(shard_names)} *{shard_reader.SHARD_EXT} shard(s)"
        if sha and _sources_dir_digest(shard_names) != sha:
            raise SystemExit(f"py_executor: manifest source checksum mismatch for {src['path']!r} "
                             f"(over the sorted *{shard_reader.SHARD_EXT} name list)")
    else:
        names = _candidate_names(sp, ext)
        actual_count = len(names)
        found_desc = f"{actual_count} *{ext} candidate file(s)"
        if sha and _sources_dir_digest(names) != sha:
            raise SystemExit(f"py_executor: manifest source checksum mismatch for {src['path']!r} "
                             f"(over the sorted *{ext} name list)")
    if actual_count != declared_count:
        raise SystemExit(f"py_executor: manifest candidate_count={declared_count} "
                         f"but found {found_desc} in {src['path']!r}")

    # The manifest never carries the SQL text itself -- read it from the
    # legacy -dirSqlTemplate dir and cross-check result_schema_mode against it.
    sql_f = _first_file(args.get("dirSqlTemplate") or "", "insert.sql")
    if not sql_f:
        raise SystemExit("py_executor: --manifest given but -dirSqlTemplate has no insert.sql "
                         "(the manifest never carries the SQL text -- P14)")
    insert_sql = sql_f.read_text(encoding="utf-8").strip().rstrip(";")
    n_q = insert_sql.count("?")
    expected_schema_mode = f"placeholders={n_q}"
    if raw["result_schema_mode"] != expected_schema_mode:
        raise SystemExit(f"py_executor: manifest result_schema_mode {raw['result_schema_mode']!r} "
                         f"!= actual {expected_schema_mode!r} ({n_q} '?' in insert.sql)")

    verdict_mode = raw["verdict_mode"]
    if verdict_mode not in ("FW_VAR", "FW_CUSTOM_VAR"):
        raise SystemExit(f"py_executor: manifest verdict_mode {verdict_mode!r} is not FW_VAR/FW_CUSTOM_VAR")
    custom_mode = (verdict_mode == "FW_CUSTOM_VAR")          # explicit -- NOT inferred from '?' count (P2)

    rt = raw["result_target"]
    password = os.environ.get(DB_PASSWORD_ENV_VAR)
    if not password:
        raise SystemExit(f"py_executor: manifest mode needs the Results DB password in "
                         f"${DB_PASSWORD_ENV_VAR} -- the v2 manifest never carries one (P3/P14)")
    db = {"host": rt["host"], "port": rt["port"], "database": rt["database"],
          "user": rt.get("user") or "postgres", "password": password}

    preprocess = None
    if raw.get("preprocess"):
        pp = Path(raw["preprocess"])
        if pp.exists() and pp.stat().st_size > 0:
            preprocess = pp

    # STEP 27: the execution policy id/hash this run's candidates run under,
    # recorded into every results_v2 row. The manifest's execution_policy_ref is
    # the authoritative id (the launcher stamps it in); the sidecar
    # execution_policy.json next to the manifest carries the full sha256.
    policy_id, policy_hash, policy_doc = _load_execution_policy(Path(manifest_path).parent)
    ref = raw.get("execution_policy_ref")
    if isinstance(ref, str) and ref:
        policy_id = ref

    return {"db": db, "insert_sql": insert_sql, "n_q": n_q, "custom_mode": custom_mode,
            "argv": list(raw.get("arguments") or []), "shift": raw.get("shift", 1),
            "preprocess": preprocess, "manifest": raw, "srcdir": sp,
            "transport": transport, "ext": ext,
            "policy_id": policy_id, "policy_hash": policy_hash, "policy": policy_doc,
            "candidate_reconciliation": {"declared": declared_count, "actual": actual_count}}


# ----------------------------- run one candidate ----------------------------- #
_RUNNER = ("import runpy,sys\n"
           "ns = runpy.run_path(sys.argv[1], run_name='__main__')\n"
           "print('__FWV__ %d %d' % (int(ns.get('FW_VAR', -999)), int(ns.get('FW_CUSTOM_VAR', -999))))\n")
_FWV = re.compile(r"__FWV__ (-?\d+) (-?\d+)")


def resolve_preprocess_for_policy(
    preprocess: Path | None,
    policy_doc: dict | None,
) -> tuple[Path | None, str | None]:
    """Keep host preprocessing outside every secure Python execution path.

    Reader historically attaches the Java ``RunMeFirstOnce`` stub to Python
    handoffs too. Running that text through Python is useless host work, so it
    is ignored for all profiles. An actual Python preprocessor remains a
    trusted-local compatibility feature; a non-trusted policy rejects it
    because executing or mutating generated source on the host would bypass the
    candidate sandbox.
    """
    if preprocess is None:
        return None, None
    secure_policy = policy_doc is not None and not policy_doc.get("trusted", False)
    try:
        source = preprocess.read_text(encoding="utf-8")
    except OSError as exc:
        if secure_policy:
            raise ValueError("secure policy cannot validate its host preprocessor") from exc
        return preprocess, None
    if re.search(r"\bclass\s+RunMeFirstOnce\b", source) and "public static" in source:
        return None, "ignored Java RunMeFirstOnce stub for Python candidates"
    if secure_policy:
        raise ValueError(
            "secure execution policy refuses host-side Python preprocessing"
        )
    return preprocess, None


def run_candidate(py: str, path: Path, argv: list,
                  preprocess: Path | None = None, sandbox=None,
                  metrics_out: "list | None" = None) -> tuple:
    """Run one candidate and classify it under the canonical outcome model (STEP 21).

    Returns ``(outcome, fw_var, fw_custom_var)``:
      * ``(Outcome.BROKEN, None, None)``     -- empty file or no FW_VAR/FW_CUSTOM_VAR
                                                 marker emitted (unrunnable / crashed
                                                 before printing it);
      * ``(Outcome.TIMEOUT, None, None)``    -- candidate exceeded the per-run timeout;
      * ``(Outcome.INFRA_FAIL, None, None)`` -- the subprocess itself could not be
                                                 spawned (OS-level error, not the
                                                 candidate's fault);
      * ``(None, fw, fwc)``                  -- ran to completion and printed a verdict;
                                                 the caller derives PASS/DOMAIN_FAIL from it.

    If `sandbox` is given (a sandbox.SandboxBackend, STEP 28), the candidate runs
    inside it (rootless-Docker container / bubblewrap namespace) instead of as a
    bare host subprocess; `sandbox=None` keeps the legacy unsandboxed behaviour
    (trusted-local / no-policy runs). Classification is identical either way.

    If the caller approved a trusted-local `preprocess` path, it is run as:
        python <preprocess> <candidate_path>
    before the candidate itself.  This implements the RunMeFirstOnce
    "patch-before-launch" contract: each Executor instance has its own
    runmefirstonce.first that rewrites TARGET_BASE_URL (or any slot) in the
    incoming \\d_\\d_\\d.py to point to that instance's application server. Secure
    policies resolve this argument to `None` or fail before this function.
    """
    if path.stat().st_size == 0:
        return Outcome.BROKEN, None, None
    if preprocess is not None:
        try:
            subprocess.run([py, str(preprocess), str(path)],
                           capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            pass   # non-fatal; run the (unpatched) candidate anyway
        except OSError:
            pass   # non-fatal; preprocessor spawn failure does not doom the candidate
    if sandbox is None:
        # Legacy / trusted-local unsandboxed path -- behaviour unchanged.
        try:
            r = subprocess.run([py, "-c", _RUNNER, str(path)] + argv,
                               capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return Outcome.TIMEOUT, None, None
        except OSError:
            # spawn-level failure (e.g. interpreter missing, ENOMEM, EMFILE) -- an
            # infrastructure problem, not a verdict on the candidate itself.
            return Outcome.INFRA_FAIL, None, None
        stdout = r.stdout
    else:
        # STEP 28: run inside the policy's sandbox backend. The backend maps a
        # wall-clock/CPU timeout to `timed_out` and a spawn-level failure (the
        # sandbox itself could not start the candidate) to `spawn_error` -- the
        # same two infrastructure outcomes the unsandboxed path derives from
        # TimeoutExpired / OSError, so classification stays identical.
        res = sandbox.run(path, argv)
        if res.spawn_error is not None:
            return Outcome.INFRA_FAIL, None, None
        if res.timed_out:
            return Outcome.TIMEOUT, None, None
        stdout = res.stdout
    m = _FWV.search(stdout)
    if m is None:
        return Outcome.BROKEN, None, None
    if metrics_out is not None:
        # Harvest the candidate's own K=V metrics line FROM THIS (already-sandboxed)
        # execution. The Analyzer corpus must come from here, never from a SECOND,
        # local re-run of the candidate (collect_kv's legacy behaviour): re-running
        # generated code on the host is a sandbox bypass for a secure policy, and
        # re-firing a STATEFUL candidate (e.g. an FW_Optional rotate-key/poison-cache
        # sudden action) against a live SUT produces a different, wrong verdict. Same
        # selection rule as collect_kv ("app=" prefix + "FW_VAR=" token); empty string
        # when the candidate emitted no metrics line (still has a __FWV__ verdict).
        metrics_out.append(next((ln.strip() for ln in stdout.splitlines()
                                 if ln.startswith("app=") and "FW_VAR=" in ln), ""))
    return None, int(m.group(1)), int(m.group(2))


# --------------- Plan-1 repeatScope=metrics: K-sample measurement ------------- #
# The executor is the observation layer, not the statistics layer. It retains every
# valid raw sample with (candidate_id, repeat_idx, env_id) identity; the Analyzer owns
# median/CI/TARGET transforms. Prematurely collapsing here destroys the order statistics
# and makes missing measurements impossible to account for honestly.


def resolve_repeat_options(args: dict) -> tuple:
    """Validate the standalone executor's currently implemented repeat capability.

    K=1 keeps the legacy path regardless of policy/scope tokens because the topology is
    inactive. K>1 fails closed unless this executor can actually honor the request: the
    `local` policy with scope `metrics` (verdict once, K metric samples) or `all` (every
    sample a full verdict ⇒ K results_v2 rows), K within the exact-reservoir contract.
    `disperse`/`nested` need multi-instance / multi-environment dispatch and stay refused.
    """
    raw_k = args.get("repeat", "1")
    try:
        k = int(raw_k)
    except (TypeError, ValueError):
        raise SystemExit(f"py_executor: --repeat must be an integer >= 1, got {raw_k!r}")
    if k < 1:
        raise SystemExit("py_executor: --repeat must be >= 1")
    if k > 1024:
        raise SystemExit("py_executor: --repeat must be <= 1024 (exact raw-sample contract)")
    policy = args.get("repeatPolicy", "local")
    scope = args.get("repeatScope", "metrics")
    if k > 1:
        if policy != "local" or scope not in ("metrics", "all"):
            raise SystemExit("py_executor: K>1 currently supports only --repeatPolicy local "
                             "with --repeatScope metrics or all")
        if scope == "metrics" and not args.get("metricsFile"):
            raise SystemExit("py_executor: K>1 local/metrics requires --metricsFile; "
                             "raw repeat observations must not be discarded")
    return k, policy, scope

def measure_metric_repeated(py: str, path: Path, argv: list, preprocess, sandbox, k: int) -> tuple:
    """Run up to K measurements through the identical sandbox/oracle path.

    The first invocation owns the canonical verdict. Each returned measurement retains
    its repeat index, raw metric line (or None), infrastructure outcome, and duration.
    Metric-only failures are therefore observable instead of silently discarded. If the
    canonical invocation fails, no further side-effecting invocations are attempted.
    """
    measurements = []
    canonical = (None, None, None)
    for repeat_idx in range(k):
        captured = []
        started = time.monotonic()
        outcome, fw, fwc = run_candidate(
            py, path, argv, preprocess, sandbox, metrics_out=captured)
        measurements.append({
            "repeat_idx": repeat_idx,
            "metric_line": captured[0] if captured and captured[0] else None,
            "outcome": outcome,
            "duration_ms": round((time.monotonic() - started) * 1000),
        })
        if repeat_idx == 0:
            canonical = (outcome, fw, fwc)
            if outcome is not None:
                break
    return canonical[0], canonical[1], canonical[2], measurements


# ------------------- replicate MainWatch.SqlRecord.bind() -------------------- #
def build_params(status: bool, source: str, verdict_code: int, ids: list,
                 n_total: int, shift: int, custom_mode: bool) -> list:
    # col1 status; col2 attachment; col3 fwVarOrCustom; then 3 id ints; then combos* booleans
    # attachment: the Java Executor saves source for FAILS only; the caller may also pass the
    # source for PASSES (--passSource) so use-cases where success IS the result (e.g. the
    # superoptimizer: a correct program == a pass) keep the winning artifact in the Results DB.
    col3 = 0 if status else (verdict_code if custom_mode else -1)
    params = [status, source, col3] + ids
    if not custom_mode:
        n_bool = n_total - 6
        if status:
            params += [None] * n_bool
        else:
            null1 = verdict_code - shift                       # leading NULL combos columns
            null2 = n_total - verdict_code - 6 + (shift - 1)   # trailing NULL combos columns
            if null1 < 0 or null2 < 0:
                raise ValueError(f"verdict code {verdict_code} overflows {n_bool} combos columns "
                                 f"(shift={shift}); use a code <= #combos columns")
            params += [None] * null1 + [False] + [None] * null2
    if len(params) != n_total:
        raise ValueError(f"bound {len(params)} params but template has {n_total} '?'")
    return params


def _write_json_atomic(path: Path, data: dict) -> None:
    """Write *data* as JSON without ever exposing a partial file: temp file in
    the same directory, flush+fsync, then ``os.replace`` (atomic on POSIX) --
    mirrors ``generator_trunk.bundle.jsonio.write_json_atomic`` (STEP 3) without
    making this standalone script depend on the generator_trunk package."""
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _metric_identity(key) -> tuple:
    """Normalize a legacy candidate key or a repeat-aware composite key."""
    if isinstance(key, tuple):
        candidate_id, repeat_idx, env_id = key
        return str(candidate_id), int(repeat_idx), str(env_id), True
    return str(key), 0, "", False


def _write_metrics_corpus(path: Path, metrics_by_id: dict, run_id: "str | None") -> int:
    """Write raw in-sandbox observations in deterministic sample-identity order.

    Legacy K=1 string keys retain the byte-compatible provenance prefix. Repeat-aware
    tuple keys add repeat_idx/env_id and preserve every valid raw line for Analyzer-side
    median/CI computation.
    """
    lines = []
    for key in sorted(metrics_by_id, key=lambda k: _metric_identity(k)[:3]):
        cid, repeat_idx, env_id, repeat_aware = _metric_identity(key)
        name, kv = metrics_by_id[key]
        prov = [f"candidate_id={cid.replace(' ', '_')}",
                f"source_ref={name.replace(' ', '_')}"]
        if run_id:
            prov.append(f"run_id={str(run_id).replace(' ', '_')}")
        if repeat_aware:
            prov.extend((f"repeat_idx={repeat_idx}",
                         f"env_id={env_id.replace(' ', '_')}"))
        lines.append(" ".join(prov) + " " + kv)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ("\n".join(lines) + "\n") if lines else ""
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return len(lines)


def _metric_identity_from_line(line: str) -> tuple:
    tokens = {}
    for token in line.split():
        if "=" in token:
            key, value = token.split("=", 1)
            tokens.setdefault(key, value)
    candidate_id = tokens.get("candidate_id", line)
    try:
        repeat_idx = int(tokens.get("repeat_idx", "0"))
    except ValueError:
        repeat_idx = 0
    return candidate_id, repeat_idx, tokens.get("env_id", "")


def merge_worker_metrics(part_paths, out_path: Path) -> int:
    """Merge worker partitions by full repeat identity, never by candidate alone."""
    merged = {}
    for part in part_paths:
        part = Path(part)
        if not part.is_file():
            continue
        for line in part.read_text(encoding="utf-8").splitlines():
            if line.strip():
                merged[_metric_identity_from_line(line)] = line
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = ("\n".join(merged[key] for key in sorted(merged)) + "\n") if merged else ""
    tmp = out_path.with_name(f".{out_path.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out_path)
    return len(merged)


def to_sql_tuple(params: list) -> str:
    def cell(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        return "$$" + str(v) + "$$"
    return "(" + ",".join(cell(p) for p in params) + ")"


# ----------------------------------- main ----------------------------------- #
def parse_args(argv):
    a, i = {}, 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            a[tok[2:]] = argv[i + 1]; i += 2
        elif tok.startswith("-"):
            a[tok[1:]] = argv[i + 1]; i += 2
        else:
            i += 1
    return a


def list_candidates(srcdir: Path):
    return sorted(p for p in srcdir.iterdir() if p.is_file() and p.suffix == ".py")


def _strip_arg(argv, name):
    """Remove every ``--name value`` / ``-name value`` pair from a parsed-style argv list."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] in ("--" + name, "-" + name):
            i += 2                                    # drop the flag and its value
            continue
        out.append(argv[i]); i += 1
    return out


def _worker_run_id(a):
    """Stable identity for this run's worker state dir: the manifest run_id (so a `bundle
    resume` of the SAME run resumes its workers, while a fresh run — fresh run_id — starts
    clean). Legacy/no-manifest runs get no cross-invocation identity."""
    mp = a.get("manifest")
    if not mp:
        return None
    try:
        return json.loads(Path(mp).read_text(encoding="utf-8")).get("run_id")
    except (OSError, json.JSONDecodeError):
        return None


def _workers_state_dir(a, workers):
    """Per-run directory holding one ``worker-<w>.json`` checkpoint per COMPLETED worker.
    Keyed by run_id + worker count next to the manifest, so a re-run skips the workers that
    already finished and re-runs only the crashed/missing ones. Legacy runs use a private
    temp dir (no resume)."""
    run_id = _worker_run_id(a)
    if run_id is not None and a.get("manifest"):
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(run_id))
        return Path(a["manifest"]).resolve().parent / f".fw-workers-{safe}-{workers}", False
    import tempfile
    return Path(tempfile.mkdtemp(prefix="fw-workers-")), True


def _valid_worker_summary(path):
    """A worker counts as COMPLETE only if its checkpoint carries ``completed_successfully:true``
    -- which py_executor writes ONLY after ALL its commit + results_v2 writes succeeded. A
    worker that wrote a result JSON but then exited non-zero (a commit / results_v2 failure, or
    any early FATAL) leaves the flag False, so it is NOT treated as complete and IS re-run on the
    next resume (review fix: a valid-JSON-but-failed worker must not be skipped)."""
    try:
        summ = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return summ if summ.get("completed_successfully") is True else None


def _dispatch_workers(a, workers):
    """STEP 33 dispatcher: run ``workers`` local py_executor workers over disjoint,
    deterministically id-hash-assigned candidate partitions and aggregate their summaries.

    Reuses the WHOLE per-candidate path (manifest validation, execution policy / sandbox,
    classification, idempotent results_v2 writes) by re-invoking this script with
    ``--workerCount N --workerIndex w``. Each worker writes its structured result JSON to a
    per-run state dir ONLY after its single end-of-run commit; the dispatcher aggregates
    those. On a re-run it SKIPS workers that already have a valid checkpoint and re-runs only
    the crashed/missing ones — so a crash followed by a plain re-run never reprocesses (and so
    never duplicates the non-idempotent legacy Results of) a worker that already finished."""
    started = time.monotonic()
    # no recursion / own result + metrics file per worker (the dispatcher merges them)
    base = _strip_arg(_strip_arg(_strip_arg(sys.argv[1:], "workers"), "resultFile"), "metricsFile")
    state_dir, ephemeral = _workers_state_dir(a, workers)
    state_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = a.get("metricsFile")

    done, specs = {}, []
    for w in range(workers):
        rp = state_dir / f"worker-{w}.json"
        prior = None if ephemeral else _valid_worker_summary(rp)
        if prior is not None:
            done[w] = prior
            continue
        cmd = [sys.executable, str(Path(__file__).resolve())] + base + [
            "--workerCount", str(workers), "--workerIndex", str(w), "--resultFile", str(rp)]
        if metrics_file:
            # each worker harvests its partition's metrics into the state dir; merged below
            cmd += ["--metricsFile", str(state_dir / f"metrics-{w}.kv")]
        specs.append({"index": w, "cmd": cmd, "result_path": str(rp)})

    if done:
        print(f"py_executor: resume -- {len(done)} worker(s) already complete {sorted(done)} "
              f"(skipped, not reprocessed); re-running only {[s['index'] for s in specs]}")
    print(f"py_executor: dispatching {len(specs)} local worker(s) over deterministic id-hash "
          f"partitions (workers={workers}, state={state_dir})")

    def _hb(alive):
        print(f"py_executor: heartbeat -- {len(alive)} worker(s) still running: {alive}")

    fresh, crashed = worker_pool.run_workers(specs, heartbeat_interval=10.0, on_progress=_hb)
    all_results = {**done, **fresh}
    agg = worker_pool.aggregate_summaries([all_results[i] for i in sorted(all_results)])
    duration = time.monotonic() - started

    # Re-emit the SAME summary lines the launcher scrapes (stages.stage_executor), aggregated.
    print(f"py_executor DONE: processed={agg['processed']} pass={agg['pass']} fail={agg['fail']} "
          f"broken={agg['broken']} inserted={agg['inserted']} (workers={workers})")
    print("py_executor OUTCOMES: " +
          " ".join(f"{o.lower()}={agg['outcomes'].get(o, 0)}" for o in Outcome.ALL))
    print("py_executor RESULTS_V2: " +
          " ".join(f"{k}={agg['results_v2_write_counts'].get(k, 0)}"
                   for k in ("attempted", "inserted", "already_present", "updated_selected")))
    if crashed:
        print(f"py_executor: WORKER CRASH -- worker(s) {crashed} did not complete; their candidate "
              f"partition(s) were NOT processed and committed nothing. The completed workers are "
              f"checkpointed; re-run the SAME command to resume ONLY the crashed worker(s) -- already-"
              f"finished workers are skipped, so legacy Results are not duplicated.")

    result_file = a.get("resultFile")
    if result_file:
        out = dict(agg)
        out.update({"workers": workers, "crashed_workers": crashed, "duration_seconds": round(duration, 3)})
        _write_json_atomic(Path(result_file), out)
        print(f"py_executor: aggregated result written → {result_file}")

    # Merge the per-worker metrics partitions into the single corpus the launcher
    # asked for, sorted by candidate_id so the result is deterministic regardless of
    # worker count (1-worker and N-worker runs yield the same corpus). Only complete
    # (non-crashed) workers contribute; a crashed partition's candidates are absent,
    # which formal mode then catches as a corpus-count shortfall (fail closed).
    if metrics_file:
        parts = [state_dir / f"metrics-{w}.kv" for w in range(workers)]
        n_merged = merge_worker_metrics(parts, Path(metrics_file))
        print(f"py_executor METRICS: merged {n_merged} candidate K=V line(s) "
              f"from {workers} worker partition(s) → {metrics_file}")

    if ephemeral:                       # legacy/no-manifest: nothing to resume from, tidy up
        for w in range(workers):
            for fname in (f"worker-{w}.json", f"metrics-{w}.kv"):
                try:
                    (state_dir / fname).unlink()
                except OSError:
                    pass
        try:
            state_dir.rmdir()
        except OSError:
            pass
    # NOTE (manifest mode): the per-run checkpoints are intentionally KEPT so a re-run resumes
    # only the crashed workers; `bundle cleanup` (STEP 25) removes them with the run.
    raise SystemExit(1 if crashed else 0)


def main():
    a = parse_args(sys.argv[1:])
    if a.get("capabilities", "").lower() == "true":
        print(json.dumps(capability_document(), sort_keys=True))
        return
    py = a.get("python", sys.executable)
    fail_only = a.get("failOnly", "true").lower() != "false"
    save_pass_source = a.get("passSource", "false").lower() == "true"
    write_db = a.get("writeToDB", "true").lower() != "false"
    write_file = a.get("writeFile", "false").lower() == "true"
    watch_seconds = float(a.get("watchSeconds", "0"))
    attempt = int(a.get("attempt", "1"))
    if attempt < 1:
        raise SystemExit("py_executor: --attempt must be >= 1")
    # Standalone capability: K>1 is deliberately narrow and fails closed unless raw
    # observations can be persisted for later Analyzer-side statistics.
    repeat_k, repeat_policy, repeat_scope = resolve_repeat_options(a)
    repeat_env_id = a.get("envId", "")
    repeat_runtime = {
        "opportunities": 0,
        "invocations": 0,
        "metric_rows": 0,
        "missing_measurements": 0,
        "failed_invocations": 0,
        "unattempted_after_canonical_failure": 0,
    }
    # STEP 33: deterministic sharding + local worker pool. `--workers N` (N>1) runs as a
    # DISPATCHER: it spawns N local worker py_executors over disjoint, id-hash-assigned
    # candidate partitions and aggregates their summaries (no remote orchestration). A worker
    # invocation carries `--workerCount N --workerIndex w` and filters its candidates with
    # worker_pool.assign(); the default (1 worker, no worker coords) is the unchanged single
    # process path. `_mine()` below is a no-op when workerCount == 1.
    workers = int(a.get("workers", "1"))
    worker_count = int(a.get("workerCount", "1"))
    worker_index = int(a.get("workerIndex", "0"))
    if workers > 1 and a.get("workerCount") is None:
        _dispatch_workers(a, workers)            # spawns workers, aggregates, raises SystemExit
        return

    def _mine(candidate_id):                     # this worker owns this candidate?
        return worker_pool.assign(candidate_id, worker_count) == worker_index

    # STEP 34: when a backpressure state dir is configured, publish CONSUMER progress so the
    # Reader (producer) can bound how far ahead it runs (depth = produced - consumed). Opt-in:
    # absent → no-op, behaviour unchanged. Each worker owns its own consumed-<index> counter.
    bp = (backpressure.Backpressure(a["backpressureDir"], writer_id=worker_index)
          if a.get("backpressureDir") else None)

    def _consumed(t0):
        if bp:
            bp.note_consumed(1, busy_seconds=time.monotonic() - t0)

    start = time.monotonic()

    manifest_path = a.get("manifest")
    if manifest_path:
        hs = read_manifest(Path(manifest_path), a)
        srcdir = hs["srcdir"]                    # manifest source IS the source of truth, not -srcDirList
        print(f"py_executor: Handoff v2 manifest → {manifest_path} "
              f"(run_id={hs['manifest']['run_id']}, candidates "
              f"declared={hs['candidate_reconciliation']['declared']} "
              f"actual={hs['candidate_reconciliation']['actual']})")
    else:
        print("py_executor: WARNING: no --manifest given -- falling back to the "
              "legacy directory handshake (Handoff v2 not in effect, see STEP 17/20)")
        hs = read_handshake(a)
        srcdir = Path(a["srcDirList"])

    run_id = (hs["manifest"] or {}).get("run_id") or a.get("runId")
    if write_db and not run_id:
        print("py_executor: WARNING: results_v2 disabled because legacy mode has no stable --runId")
    # STEP 27: execution policy id/hash recorded into every results_v2 row.
    policy_id = hs.get("policy_id")
    policy_hash = hs.get("policy_hash")
    if run_id:
        print(f"py_executor: execution policy → id={policy_id or '(none)'} "
              f"hash={(policy_hash[:12] + '…') if policy_hash else '(none)'}")
    # STEP 28: the sandbox backend every candidate executes under. `None` means
    # run unsandboxed -- ONLY for a trusted-local policy (explicit opt-in) or a
    # legacy/no-policy run. The backend itself is built after emit_summary is
    # defined (so a fail-closed exit can still print a summary); see below.
    policy_doc = hs.get("policy")
    sandbox = None

    # Candidate preprocessor reference from the handshake/manifest. Before any
    # candidate runs, the policy boundary below ignores a Java stub, refuses a
    # real host Python preprocessor for secure profiles, and retains it only for
    # explicitly trusted-local compatibility.
    preprocess = hs["preprocess"]
    print(f"py_executor: mode={'FW_CUSTOM_VAR' if hs['custom_mode'] else 'FW_VAR'} "
          f"(insert has {hs['n_q']} '?'), shift={hs['shift']}, failOnly={fail_only}, "
          f"db={hs['db']['host']}:{hs['db']['port']}/{hs['db']['database']}")
    sql = re.sub(r"\?", "%s", hs["insert_sql"])

    rows_sql, n_pass, n_fail, n_broken, n_inserted = [], 0, 0, 0, 0
    # `processed` counts full-verdict invocations (V), not candidate files: == len(seen) for
    # metrics/K=1 (one verdict per candidate), == C·K for local/all (K verdict rows per candidate).
    # Keeps `processed == sum(outcomes) == attempted == V` (docs/24 §2) for every scope.
    n_processed = 0
    outcomes = {o: 0 for o in Outcome.ALL}
    # (outcome, status) for every row `cur.execute`d but not yet committed --
    # needed so a commit failure can reclassify them to INFRA_FAIL too (the
    # outcome model is meant to be mutually-exclusive-per-candidate: a row
    # that was never durably persisted is not a recorded domain verdict,
    # mirroring the per-row `cur.execute` reclassification below).
    pending_commits = []
    seen = set()
    v2_rows = {}
    v2_counts = {"attempted": 0, "inserted": 0, "already_present": 0, "updated_selected": 0}
    # Analyzer metrics corpus harvested DURING this sandboxed run. K=1 is keyed by
    # candidate_id; repeats use (candidate_id, repeat_idx, env_id), so raw samples
    # survive without a second host-side re-run of the candidates (see run_candidate's
    # metrics_out and the --metricsFile writer below). Empty when --metricsFile is absent.
    metrics_file = a.get("metricsFile")
    metrics_by_id = {}

    def record_v2(candidate_id, outcome, verdict_code, duration_ms, source_hash, repeat_idx=0):
        if not run_id:
            return
        v2_rows[(candidate_id, repeat_idx)] = {
            "run_id": run_id,
            "candidate_id": candidate_id,
            "attempt": attempt,
            "outcome": outcome,
            "verdict_code": verdict_code,
            "verdict_message": None,
            "duration_ms": duration_ms,
            "exit_code": None,
            "signal": None,
            "worker": f"python:{os.getpid()}",
            "source_hash": source_hash,
            "stdout_ref": None,
            "stderr_ref": None,
            "policy_id": policy_id,
            "policy_hash": policy_hash,
            # Plan-1 sample identity: the verdict is metric sample 0 (docs/24 §3.0); env_id is the
            # assignment-time environment ('' for the single-env standalone executor). repeat_idx is
            # 0 for metrics/K=1 (one verdict row per candidate, V=C); for local/all it is the sample
            # ordinal 0..K-1 (K verdict rows per candidate, V=C·K).
            "repeat_idx": repeat_idx,
            "env_id": repeat_env_id,
        }

    def reclassify_v2(candidate_id, outcome, repeat_idx=0):
        row = v2_rows.get((candidate_id, repeat_idx))
        if row is not None:
            row["outcome"] = outcome

    def emit_summary(completed=False):
        """Print the legacy + canonical-outcome completion summaries and (optionally)
        the JSON result file. Factored out so EVERY exit path -- clean completion,
        a DB-connect INFRA_FAIL, a commit INFRA_FAIL -- reports the same shape; a
        run that dies before reaching the bottom of `main` must never vanish
        without a summary (STEP 21 review finding).

        STEP 33: ``completed`` is written into the result JSON as ``completed_successfully``
        and is True ONLY on the fully-clean exit (after every commit + results_v2 write
        succeeded). Every failure/early-exit path leaves it False, so the worker-pool
        dispatcher never mistakes a worker that wrote a result file but then exited
        non-zero for a finished one (it re-runs it)."""
        duration = time.monotonic() - start
        # Legacy line kept byte-for-byte (stages.stage_executor scrapes it with a
        # fixed regex, STEP 6/20): pass/fail here are the boolean-status projection
        # (PASS/DOMAIN_FAIL), broken is the canonical BROKEN count -- both already
        # matched the STEP 21 mapping before this step, so the line needs no change.
        print(f"py_executor DONE: processed={n_processed} pass={n_pass} fail={n_fail} "
              f"broken={n_broken} inserted={n_inserted} (failOnly={fail_only})")
        # New: canonical outcome breakdown (STEP 21 action item 5) -- separates
        # domain verdicts (PASS/DOMAIN_FAIL) from infrastructure outcomes
        # (BROKEN/TIMEOUT/INFRA_FAIL/SKIPPED/CANCELLED) the legacy line conflates.
        print("py_executor OUTCOMES: " +
              " ".join(f"{o.lower()}={outcomes[o]}" for o in Outcome.ALL))
        print("py_executor RESULTS_V2: " +
              " ".join(f"{key}={v2_counts[key]}" for key in
                       ("attempted", "inserted", "already_present", "updated_selected")))

        result_file = a.get("resultFile")
        if result_file:
            result = {
                "processed": n_processed, "pass": n_pass, "fail": n_fail,
                "broken": n_broken, "inserted": n_inserted,
                # STEP 33: the authoritative "this worker finished cleanly" flag the dispatcher's
                # resume checks -- True only after all commit/results_v2 writes succeeded.
                "completed_successfully": completed,
                "outcomes": dict(outcomes),
                "results_v2_write_counts": dict(v2_counts),
                "duration_seconds": round(duration, 3),
                "manifest_protocol": (hs["manifest"] or {}).get("protocol"),
                "candidate_count_reconciliation": hs["candidate_reconciliation"],
                # STEP 28: which sandbox backend candidates actually ran under
                # (None = unsandboxed trusted-local/legacy). STEP 30 cross-checks
                # "sandbox backend recorded".
                "sandbox_backend": sandbox.describe() if sandbox is not None else None,
            }
            if repeat_k > 1:
                result["repeat_measurements"] = dict(repeat_runtime)
            _write_json_atomic(Path(result_file), result)
            print(f"py_executor: result written → {result_file}")

    try:
        preprocess, preprocess_note = resolve_preprocess_for_policy(
            preprocess,
            policy_doc,
        )
    except ValueError as exc:
        print(f"py_executor: FATAL -- {exc}")
        emit_summary()
        sys.exit(1)
    if preprocess_note:
        print(f"py_executor: {preprocess_note}")
    elif preprocess is not None:
        print(f"py_executor: trusted RunMeFirstOnce preprocessor → {preprocess}")

    # STEP 28: resolve the sandbox backend BEFORE connecting/processing, so a
    # secure policy whose backend is unavailable fails closed up front and never
    # runs a single generated candidate unsandboxed (acceptance / STEP 30:
    # "Secure mode не использует local fallback"). `build_sandbox` returns None
    # for a trusted-local policy (explicit opt-in) and for a legacy/no-policy run.
    backend_name = (policy_doc or {}).get("backend", "local")
    if policy_doc and backend_name != "local" and _sandbox is None:
        print(f"py_executor: FATAL -- execution policy requires sandbox backend "
              f"{backend_name!r} but the sandbox module failed to import; refusing "
              f"to run generated candidates unsandboxed")
        emit_summary()
        sys.exit(1)
    if policy_doc and _sandbox is not None:
        try:
            sandbox = _sandbox.build_sandbox(
                policy_doc, runner=_RUNNER, host_python=py,
                image=os.environ.get("BUNDLE_SANDBOX_IMAGE"))
        except _sandbox.SandboxUnavailable as exc:
            print(f"py_executor: FATAL -- {exc}")
            emit_summary()
            sys.exit(1)
    if sandbox is not None:
        print(f"py_executor: sandbox → {sandbox.describe()}")
        # STEP 28: production wiring of the network allowlist -- the backend
        # attaches each allowlisted target (driven by the policy's
        # network_allowlist, validated against it) to the candidate's dedicated
        # internal network. No-op for non-allowlist policies / non-container
        # backends. This is the real api-probe path, not a test-only call.
        provisioned = sandbox.provision()
        if provisioned:
            print(f"py_executor: sandbox allowlist → attached {provisioned} "
                  f"target(s) to the dedicated internal network")
    else:
        print(f"py_executor: sandbox → none (backend={backend_name}; "
              f"{'trusted opt-in' if (policy_doc or {}).get('trusted') else 'unsandboxed legacy/local'})")

    # A bare `pg8000.dbapi.connect()` raising here used to crash the whole process
    # before a single line of completion summary was printed -- the launcher saw a
    # bare non-zero exit / parse failure (STEP 21 review finding). Still emit the
    # summary and exit non-zero so the launcher always gets a parseable report.
    #
    # NOTE this is *not* counted into `outcomes[INFRA_FAIL]`: the Outcome enum
    # classifies the result of an attempted *candidate* (P21 mapping: "spawn/DB
    # infrastructure error -> INFRA_FAIL" refers to a per-candidate insert/commit
    # failure inside `process`, see below). A connect failure here happens before
    # any candidate is attempted -- nothing was processed (`processed=len(seen)==0`,
    # all outcome buckets stay 0, so `processed == sum(outcomes)` still holds) and
    # there is nothing to classify. The run still fails, unconditionally and not
    # subject to --executor-tolerate-outcomes: `executor_processed_positive` is an
    # untolerable CRITICAL invariant precisely because "zero candidates could even
    # be attempted" is not a degraded-but-acceptable state to wave through.
    schema_ready = False
    try:
        conn = pg8000.dbapi.connect(**hs["db"]) if write_db else None
        cur = conn.cursor() if conn else None
        if conn is not None:
            # STEP 22: ensure the additive results_v2 schema exists alongside
            # the legacy table on every connect. Purely additive/idempotent --
            # a failure here must never block the legacy flow this script
            # already depends on, so it is logged and swallowed, not raised.
            # STEP 23 writes the canonical batch after legacy outcomes finalize.
            try:
                ensure_results_v2_schema(conn)
                schema_ready = True
            except Exception as schema_exc:
                print(f"py_executor: results_v2 schema ensure failed (non-fatal, "
                      f"legacy Results flow unaffected): {schema_exc}")
    except Exception as exc:
        print(f"py_executor: FATAL -- could not connect to Results DB "
              f"{hs['db']['host']}:{hs['db']['port']}/{hs['db']['database']} "
              f"-- 0 candidates attempted: {exc}")
        if sandbox is not None:
            sandbox.close()
        emit_summary()
        sys.exit(1)

    # Plan-1 Phase 3b (docs/24 §1.6): when the schema migration succeeded AND we will write canonical
    # results_v2 rows, validate the live schema is on the 5-column sample identity this writer upserts
    # against, and FAIL CLOSED on a mismatch (wrong/missing index, wrong meta version, or a
    # resurrected legacy 3-col index) -- a silent duplicate or a raw crash is not acceptable. Gated on
    # `schema_ready` so a swallowed ensure failure keeps the legacy-only flow's prior behavior (the
    # write path's ON CONFLICT against a missing 5-col index is the structural backstop), and on
    # run_id because that is when canonical rows are actually written.
    if conn is not None and write_db and run_id and schema_ready:
        try:
            validate_results_v2_schema_capability(conn)
        except ResultsV2SchemaCapabilityMismatch as mismatch:
            print(f"py_executor: FATAL -- {mismatch} -- 0 candidates attempted")
            if sandbox is not None:
                sandbox.close()
            emit_summary()
            sys.exit(1)

    def _record_full_verdict(path, candidate_id, repeat_idx, infra_outcome, fw, fwc,
                             duration_ms, source_hash):
        """Record ONE full verdict sample (results_v2 row + legacy row + outcome/processed counts)
        at repeat_idx. Called once per candidate (repeat_idx 0) on the metrics/single path, and K
        times (repeat_idx 0..K-1) on the local/all path — where each sample is an independent full
        verdict (no stop-on-canonical-failure). Mutates the run counters."""
        nonlocal n_pass, n_fail, n_broken, n_inserted, n_processed
        n_processed += 1
        if infra_outcome is not None:
            outcomes[infra_outcome] += 1
            if infra_outcome == Outcome.BROKEN:
                n_broken += 1   # legacy counter: "no verdict marker" only (P21 mapping)
            record_v2(candidate_id, infra_outcome, None, duration_ms, source_hash, repeat_idx)
            return
        verdict = fwc if hs["custom_mode"] else fw
        # `status` is the boolean compatibility projection the Results DB schema and existing
        # consumers expect (STEP 21 action item 4): PASS -> True, DOMAIN_FAIL -> False.
        status = (verdict == 0)
        outcome = Outcome.PASS if status else Outcome.DOMAIN_FAIL
        outcomes[outcome] += 1
        if status:
            n_pass += 1
        else:
            n_fail += 1
        record_v2(candidate_id, outcome, verdict, duration_ms, source_hash, repeat_idx)
        if fail_only and status:
            return
        ids = [int(x) for x in path.stem.split("_")]          # <final>_<opt>_<j>
        # save source for fails always; for passes only when --passSource (success-is-result runs)
        src = path.read_text(encoding="utf-8") if (not status or save_pass_source) else None
        try:
            params = build_params(status, src, verdict, ids, hs["n_q"], hs["shift"], hs["custom_mode"])
        except ValueError as exc:
            # An unencodable verdict (e.g. a verdict code outside the #combos-columns range) is a
            # single BROKEN candidate, not a run-killer: undo the PASS/DOMAIN_FAIL tentatively
            # recorded above, reclassify THIS candidate as BROKEN with the clear reason, and carry
            # on so the executor still emits a completion summary (an honest "N BROKEN" + the reason,
            # instead of exiting status 1 with "no completion summary / unclassified failure").
            outcomes[outcome] -= 1
            if status:
                n_pass -= 1
            else:
                n_fail -= 1
            outcomes[Outcome.BROKEN] += 1
            n_broken += 1
            reclassify_v2(candidate_id, Outcome.BROKEN, repeat_idx)
            print(f"py_executor: BROKEN -- {path.name}: {exc}", flush=True)
            return
        if write_db:
            try:
                cur.execute(sql, params)
            except Exception as exc:
                # PostgreSQL aborts the whole transaction after one failed statement. Roll it back
                # and reclassify every pending legacy row, not only the one whose execute raised.
                affected = pending_commits + [(outcome, status, candidate_id, repeat_idx)]
                try:
                    conn.rollback()
                except Exception:
                    pass
                for prior_outcome, prior_status, prior_id, prior_repeat in affected:
                    outcomes[prior_outcome] -= 1
                    outcomes[Outcome.INFRA_FAIL] += 1
                    if prior_status:
                        n_pass -= 1
                    else:
                        n_fail -= 1
                    reclassify_v2(prior_id, Outcome.INFRA_FAIL, prior_repeat)
                n_inserted -= len(pending_commits)
                pending_commits.clear()
                print(f"py_executor: INFRA_FAIL -- DB insert failed for {path.name}; "
                      f"rolled back and reclassified {len(affected)} candidate(s): {exc}")
                return
            n_inserted += 1
            pending_commits.append((outcome, status, candidate_id, repeat_idx))
        if write_file:
            rows_sql.append(to_sql_tuple(params))

    def process(path: Path):
        candidate_id = path.stem
        candidate_started = time.monotonic()
        try:
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            source_hash = None
        repeat_active = repeat_k > 1
        if repeat_active and repeat_scope == "all":
            # local/all: every sample is a full verdict (V = I = C·K). Run K INDEPENDENT invocations,
            # record EACH as its own verdict row at repeat_idx 0..K-1 (the 5-col sample index keeps
            # them distinct), and harvest each sample's metric. NO stop-on-canonical-failure: every
            # sample is an honest, independent verdict (this is the flaky-verdict measurement mode).
            repeat_runtime["opportunities"] += repeat_k
            for repeat_idx in range(repeat_k):
                sample_started = time.monotonic()
                captured = [] if metrics_file else None
                infra_outcome, fw, fwc = run_candidate(
                    py, path, hs["argv"], preprocess, sandbox, metrics_out=captured)
                sample_ms = round((time.monotonic() - sample_started) * 1000)
                repeat_runtime["invocations"] += 1
                metric_line = captured[0] if (captured and captured[0]) else None
                if metric_line:
                    metrics_by_id[(candidate_id, repeat_idx, repeat_env_id)] = (path.name, metric_line)
                    repeat_runtime["metric_rows"] += 1
                else:
                    repeat_runtime["missing_measurements"] += 1
                if infra_outcome is not None:
                    repeat_runtime["failed_invocations"] += 1
                _record_full_verdict(path, candidate_id, repeat_idx, infra_outcome, fw, fwc,
                                     sample_ms, source_hash)
            return
        # Sample 0 owns the canonical verdict. metrics/K>1 persists every valid raw metric
        # observation; median/CI computation belongs to the Analyzer.
        if repeat_active:
            infra_outcome, fw, fwc, measurements = measure_metric_repeated(
                py, path, hs["argv"], preprocess, sandbox, repeat_k)
            duration_ms = measurements[0]["duration_ms"]
            repeat_runtime["opportunities"] += repeat_k
            repeat_runtime["invocations"] += len(measurements)
            unattempted = repeat_k - len(measurements)
            repeat_runtime["unattempted_after_canonical_failure"] += unattempted
            repeat_runtime["missing_measurements"] += unattempted
            for measurement in measurements:
                metric_line = measurement["metric_line"]
                if metric_line:
                    sample_key = (candidate_id, measurement["repeat_idx"], repeat_env_id)
                    metrics_by_id[sample_key] = (path.name, metric_line)
                    repeat_runtime["metric_rows"] += 1
                else:
                    repeat_runtime["missing_measurements"] += 1
                if measurement["outcome"] is not None:
                    repeat_runtime["failed_invocations"] += 1
        else:
            metrics_capture = [] if metrics_file else None
            infra_outcome, fw, fwc = run_candidate(py, path, hs["argv"], preprocess, sandbox,
                                                   metrics_out=metrics_capture)
            duration_ms = round((time.monotonic() - candidate_started) * 1000)
            if metrics_file and metrics_capture and metrics_capture[0]:
                metrics_by_id[candidate_id] = (path.name, metrics_capture[0])
        _record_full_verdict(path, candidate_id, 0, infra_outcome, fw, fwc, duration_ms, source_hash)

    transport = hs.get("transport", "loose-files")
    if transport == "sharded":
        # STEP 32: candidates live inside *.fwshard containers. Stream them one record at a
        # time (the whole shard is never expanded to disk) and materialise each into a private
        # scratch dir as <id><ext> so the existing per-candidate path (process/run_candidate/
        # sandbox, which need a real file) is reused unchanged; the temp file is deleted right
        # after, so at most one candidate body sits on disk at a time.
        import tempfile
        ext = hs.get("ext", ".py")
        scratch = Path(tempfile.mkdtemp(prefix="fw-shard-cand-"))
        seen_shards = set()

        def process_shard_record(cid, body):
            cand = scratch / (cid + ext)
            cand.write_bytes(body)
            try:
                seen.add(cand.name)
                _t0 = time.monotonic()
                process(cand)
                _consumed(_t0)                       # STEP 34: consumer progress
            finally:
                try:
                    cand.unlink()
                except OSError:
                    pass

        def scan_new_shards():
            processed = 0
            for shard in shard_reader.list_finalized_shards(srcdir):
                if shard.name in seen_shards or not shard_reader.is_finalized(shard):
                    continue
                seen_shards.add(shard.name)
                for cid, body in shard_reader.iter_shard(shard):
                    if bp and bp.is_cancelled():  # STEP 34: stop processing on a shared cancel
                        return processed
                    if not _mine(cid):            # STEP 33: another worker owns this candidate
                        continue
                    process_shard_record(cid, body)
                    processed += 1
            return processed

        try:
            n0 = scan_new_shards()
            print(f"COLD-START: processing {n0} candidate(s) from {len(seen_shards)} shard(s) in {srcdir}")
            if watch_seconds > 0:
                last = time.time()
                while time.time() - last < watch_seconds:
                    if bp and bp.is_cancelled():          # STEP 34: stop watching on cancel
                        print("py_executor: CANCELLED -- stopping shard watch loop early"); break
                    if scan_new_shards() > 0:
                        last = time.time()
                    else:
                        time.sleep(0.5)
        finally:
            try:
                scratch.rmdir()
            except OSError:
                pass
    else:
        present = [p for p in list_candidates(srcdir) if _mine(p.stem)]   # STEP 33: this worker's partition
        print(f"COLD-START: processing {len(present)} pre-existing candidate file(s) in {srcdir}")
        for p in present:
            if bp and bp.is_cancelled():                  # STEP 34: stop processing on a shared cancel
                print("py_executor: CANCELLED -- stopping candidate processing early"); break
            seen.add(p.name); _t0 = time.monotonic(); process(p); _consumed(_t0)   # STEP 34: consumer progress

        if watch_seconds > 0:
            last = time.time()
            while time.time() - last < watch_seconds:
                if bp and bp.is_cancelled():              # STEP 34: stop watching on cancel
                    print("py_executor: CANCELLED -- stopping watch loop early"); break
                new = [p for p in list_candidates(srcdir) if p.name not in seen and _mine(p.stem)]
                if new:
                    for p in new:
                        if bp and bp.is_cancelled():
                            break
                        seen.add(p.name); _t0 = time.monotonic(); process(p); _consumed(_t0)
                    last = time.time()
                else:
                    time.sleep(0.5)

    # STEP 33 (review fix): commit the legacy Results inserts AND the results_v2 rows in ONE
    # transaction. If either the results_v2 inserts or the combined commit fails, EVERYTHING is
    # rolled back and the worker exits non-zero with completed_successfully=False -- a resume
    # then re-runs it against an empty slate, so no already-committed legacy row is duplicated.
    commit_failed = False
    v2_write_failed = False
    if conn:
        try:
            v2_counts.update(commit_legacy_and_v2(conn, run_id, v2_rows))
        except Exception as exc:
            commit_failed = True
            v2_write_failed = bool(run_id)
            for outcome, status, candidate_id, repeat_idx in pending_commits:
                outcomes[outcome] -= 1
                outcomes[Outcome.INFRA_FAIL] += 1
                if status:
                    n_pass -= 1
                else:
                    n_fail -= 1
                reclassify_v2(candidate_id, Outcome.INFRA_FAIL, repeat_idx)
            v2_counts.update({"attempted": len(v2_rows), "inserted": 0,
                              "already_present": 0, "updated_selected": 0})
            print(f"py_executor: INFRA_FAIL -- combined legacy+results_v2 commit failed; rolled "
                  f"back, NOTHING persisted ({len(pending_commits)} candidate(s) reclassified): {exc}")
            n_inserted = 0
            pending_commits.clear()
    if write_file and rows_sql and a.get("out2"):
        # STEP 33: name the dump per worker so N parallel workers never overwrite one shared
        # file (each worker owns a disjoint candidate partition → disjoint rows).
        Path(a["out2"]).mkdir(parents=True, exist_ok=True)
        (Path(a["out2"]) / f"py_executor_{worker_index}.sql").write_text(
            ",\n".join(rows_sql) + "\n", encoding="utf-8")
    if cur:
        cur.close()
    if conn:
        conn.close()
    if sandbox is not None:
        sandbox.close()          # STEP 28: guaranteed sandbox teardown (action 7)

    # Write the Analyzer metrics corpus harvested in-sandbox from this run's
    # candidate stdout (no host-side re-execution). In worker mode each worker
    # writes its own partition file; the dispatcher concatenates them.
    if metrics_file:
        n_metrics = _write_metrics_corpus(Path(metrics_file), metrics_by_id, run_id)
        if repeat_k > 1 and repeat_policy == "local" and repeat_scope in ("metrics", "all"):
            print(f"py_executor METRICS: wrote {n_metrics} raw sample line(s) over "
                  f"{repeat_runtime['invocations']}/{repeat_runtime['opportunities']} "
                  f"in-sandbox invocation(s) (repeat K={repeat_k} local/{repeat_scope}, "
                  f"missing={repeat_runtime['missing_measurements']}, "
                  f"failed={repeat_runtime['failed_invocations']}) → {metrics_file}")
        else:
            print(f"py_executor METRICS: wrote {n_metrics} candidate K=V line(s) "
                  f"(harvested in-sandbox, no re-run) → {metrics_file}")

    # STEP 33: the checkpoint is marked complete ONLY when every commit + results_v2 write
    # succeeded; a worker that reaches here with a failure exits non-zero AND leaves
    # completed_successfully=False, so a later resume re-runs it rather than skipping it.
    emit_summary(completed=not (commit_failed or v2_write_failed))
    if commit_failed or v2_write_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
