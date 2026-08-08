// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

/** STEP 22: additive Results DB schema v2.
 *
 *  Introduces a normalized {@code results_v2} table that records the canonical
 *  per-candidate {@link MainWatch.Outcome} (PASS/DOMAIN_FAIL/BROKEN/TIMEOUT/
 *  INFRA_FAIL/SKIPPED/CANCELLED -- mirrors py_executor.Outcome, STEP 21) plus
 *  provenance the legacy positional table has no room for: attempt, duration,
 *  exit/signal, worker, source hash, stdout/stderr refs, created timestamp.
 *
 *  Strictly additive: lives beside the legacy table that
 *  Reader_trunk.ResultsDbProvisioner creates and MainWatch.SqlRecord/insert.sql
 *  populate. Never alters, drops, or reads from it -- legacy consumers keep
 *  working unchanged (boolean `status` stays their compatibility projection).
 *
 *  The migration is just `CREATE ... IF NOT EXISTS` -- repeatable, a no-op once
 *  applied, safe to run on every (re)connect. STEP 23 writes canonical outcomes
 *  through ResultsV2Writer after candidate classifications finalize. */
public final class ResultsV2SchemaMigrator {
    private ResultsV2SchemaMigrator() {}

    /** Sample uniqueness key (run_id, candidate_id, attempt, repeat_idx, env_id) backs STEP 23's
     *  idempotent-write policy: "one row per sample, no uncontrolled
     *  duplicates on retry/replay" -- a repeat insert for the same sample is a
     *  conflict to handle explicitly, not a silent duplicate (see
     *  {@link #CREATE_SAMPLE_INDEX_SQL}). candidate_id is
     *  the canonical composite identity string (legacy SqlRecord.resRepl shape:
     *  combi_id_final_combi_id_optional_fw_optJ) kept as text so the v2 schema
     *  stays backend-neutral across Java/Python executors and future identity
     *  shapes. */
    public static final String CREATE_TABLE_SQL =
            "CREATE TABLE IF NOT EXISTS public.results_v2 (\n" +
            "    id              bigserial PRIMARY KEY,\n" +
            "    run_id          text NOT NULL,\n" +
            "    candidate_id    text NOT NULL,\n" +
            "    attempt         integer NOT NULL DEFAULT 1,\n" +
            "    outcome         text NOT NULL,\n" +
            "    verdict_code    integer,\n" +
            "    verdict_message text,\n" +
            "    duration_ms     bigint,\n" +
            "    exit_code       integer,\n" +
            "    signal          text,\n" +
            "    worker          text,\n" +
            "    source_hash     text,\n" +
            "    stdout_ref      text,\n" +
            "    stderr_ref      text,\n" +
            "    policy_id       text,\n" +
            "    policy_hash     text,\n" +
            "    repeat_idx      integer NOT NULL DEFAULT 0,\n" +
            "    env_id          text NOT NULL DEFAULT '',\n" +
            "    created_at      timestamptz NOT NULL DEFAULT now()\n" +
            ")";

    /** Plan-1 Phase 3b (docs/24 §1.4/§1.6/§1.7): the SAMPLE-identity unique index. Identity is the
     *  5-column sample key {@code (run_id, candidate_id, attempt, repeat_idx, env_id)} -- {@code
     *  attempt} (external retry) is nested INSIDE the {@code (candidate_id, repeat_idx, env_id)}
     *  sample, so two repeats of one candidate are distinct rows, NOT a uniqueness conflict. At K=1
     *  every row carries the defaults {@code repeat_idx=0, env_id=''}, so 5-column uniqueness is
     *  identical to the retired 3-column key and K=1 idempotency is behavior-preserving. Mirrors
     *  py_executor.RESULTS_V2_CREATE_SAMPLE_INDEX_SQL. */
    public static final String CREATE_SAMPLE_INDEX_SQL =
            "CREATE UNIQUE INDEX IF NOT EXISTS results_v2_sample_uk " +
            "ON public.results_v2 (run_id, candidate_id, attempt, repeat_idx, env_id)";

    /** Retire the legacy 3-column key once the 5-column sample index exists. The two CANNOT coexist
     *  for K>1 (the 3-col index would reject two repeats differing only in repeat_idx/env_id), and
     *  the writer's {@code ON CONFLICT} target is co-versioned with the live index. {@code DROP
     *  INDEX IF EXISTS} makes the cutover idempotent and a no-op on an already-migrated DB. Mirrors
     *  py_executor.RESULTS_V2_DROP_LEGACY_INDEX_SQL. */
    public static final String DROP_LEGACY_INDEX_SQL =
            "DROP INDEX IF EXISTS public.results_v2_run_candidate_attempt_uk";

    /** Plan-1 Phase 3b launcher-side schema safety (docs/24 §1.6). The schema_meta stamp records
     *  WHICH unique identity the live results_v2 is on, so a writer can fail closed at connect when
     *  its {@code ON CONFLICT} arity != the live index ({@link #SCHEMA_CAPABILITY_MISMATCH}) instead
     *  of risking a silent duplicate or a raw crash. Version 2 == the 5-column sample identity
     *  (version 1 was the retired 3-column key; no DB ever carried a meta stamp under it). Mirrors
     *  py_executor.RESULTS_V2_SCHEMA_VERSION / RESULTS_V2_CREATE_SCHEMA_META_SQL. */
    public static final int SCHEMA_VERSION = 2;
    public static final String SAMPLE_INDEX_NAME = "results_v2_sample_uk";
    public static final String LEGACY_INDEX_NAME = "results_v2_run_candidate_attempt_uk";
    public static final String SCHEMA_CAPABILITY_MISMATCH = "RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH";

    public static final String CREATE_SCHEMA_META_SQL =
            "CREATE TABLE IF NOT EXISTS public.results_v2_schema_meta (" +
            " id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1)," +
            " version integer NOT NULL," +
            " unique_index text NOT NULL," +
            " updated_at timestamptz NOT NULL DEFAULT now())";

    /** Singleton (id=1) upsert; values are code constants (safe to inline). Mirrors
     *  py_executor.RESULTS_V2_STAMP_SCHEMA_META_SQL. */
    public static final String STAMP_SCHEMA_META_SQL =
            "INSERT INTO public.results_v2_schema_meta (id, version, unique_index, updated_at) " +
            "VALUES (1, " + SCHEMA_VERSION + ", '" + SAMPLE_INDEX_NAME + "', now()) " +
            "ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, " +
            "unique_index = EXCLUDED.unique_index, updated_at = now()";

    /** The live results_v2 schema does not match this writer's 5-column sample-identity contract.
     *  Message is prefixed {@link #SCHEMA_CAPABILITY_MISMATCH} so the launcher and logs can detect it
     *  unambiguously; the writer fails closed (no write, no silent dup) rather than risk a duplicate
     *  or a raw crash. Mirrors py_executor.ResultsV2SchemaCapabilityMismatch. */
    public static final class SchemaCapabilityMismatch extends RuntimeException {
        public SchemaCapabilityMismatch(String message) { super(message); }
    }

    /** STEP 27: the execution policy (bundle/policy.py) each candidate ran under.
     *  Additive + repeatable like the table itself -- {@code ADD COLUMN IF NOT
     *  EXISTS} is a no-op on a fresh table (the columns are already in
     *  CREATE_TABLE_SQL) and backfills them onto a results_v2 created by a
     *  pre-STEP-27 executor. Mirrors py_executor.RESULTS_V2_ADD_POLICY_COLUMNS_SQL. */
    public static final String ADD_POLICY_COLUMNS_SQL =
            "ALTER TABLE public.results_v2 " +
            "ADD COLUMN IF NOT EXISTS policy_id text, " +
            "ADD COLUMN IF NOT EXISTS policy_hash text";

    /** Plan-1 Phase 3a (docs/24 §1.6/§1.7): the per-candidate repeat SAMPLE identity.
     *  {@code repeat_idx} (0..K-1) is the intentional repeat; {@code env_id} is the
     *  assignment-time executor environment. Additive + repeatable exactly like
     *  {@link #ADD_POLICY_COLUMNS_SQL}: a no-op on a fresh table (already in
     *  CREATE_TABLE_SQL) and a backfill onto a pre-Phase-3 table -- existing rows get the
     *  K=1 defaults {@code repeat_idx=0, env_id=''}. The unique index stays the 3-column
     *  {@code (run_id, candidate_id, attempt)} key and the writer's {@code ON CONFLICT}
     *  target is UNCHANGED: with K forced to 1 every row carries the defaults, so 3-column
     *  uniqueness is still correct and K=1 idempotency is byte-identical. Promoting the
     *  index to the 5-column {@code (run_id, candidate_id, attempt, repeat_idx, env_id)}
     *  sample key (and writing non-default repeat_idx/env_id) is the version-gated cutover
     *  that lands with the executor phase that actually runs K>1 -- NOT here. Mirrors
     *  py_executor.RESULTS_V2_ADD_REPEAT_COLUMNS_SQL. */
    public static final String ADD_REPEAT_COLUMNS_SQL =
            "ALTER TABLE public.results_v2 " +
            "ADD COLUMN IF NOT EXISTS repeat_idx integer NOT NULL DEFAULT 0, " +
            "ADD COLUMN IF NOT EXISTS env_id text NOT NULL DEFAULT ''";

    /** Repeatable migration entry point: applies the additive DDL above.
     *  Idempotent -- a second call against an already-migrated DB executes the
     *  same `IF NOT EXISTS` statements and changes nothing. This method owns a
     *  short transaction and restores the connection's prior auto-commit mode:
     *  both statements commit together, or the transaction is rolled back
     *  before the error is rethrown. Callers that must not let a v2-schema
     *  hiccup disturb the legacy flow should catch {@link SQLException}
     *  around this call (see MainWatch). */
    public static void ensureSchema(Connection conn) throws SQLException {
        boolean previousAutoCommit = conn.getAutoCommit();
        SQLException failure = null;
        try {
            conn.setAutoCommit(false);
            try (Statement st = conn.createStatement()) {
                st.execute(CREATE_TABLE_SQL);
                st.execute(ADD_POLICY_COLUMNS_SQL);   // STEP 27: backfill on pre-existing tables
                st.execute(ADD_REPEAT_COLUMNS_SQL);   // Plan-1 Phase 3a: repeat_idx/env_id backfill
                // Plan-1 Phase 3b: cut the unique identity over to the 5-column sample key, THEN
                // retire the legacy 3-column key. Create-before-drop (one transaction) so the table
                // is never left without a unique key; idempotent and safe on existing tables because
                // every backfilled row carries repeat_idx=0/env_id='' (no collision the 3-col index
                // did not already forbid).
                st.execute(CREATE_SAMPLE_INDEX_SQL);
                st.execute(DROP_LEGACY_INDEX_SQL);
                // Plan-1 Phase 3b: stamp the schema-capability meta so a writer can validate the
                // live identity at connect and fail closed on a mismatch (docs/24 §1.6).
                st.execute(CREATE_SCHEMA_META_SQL);
                st.execute(STAMP_SCHEMA_META_SQL);
            }
            conn.commit();
        } catch (SQLException ex) {
            failure = ex;
            try {
                conn.rollback();
            } catch (SQLException rollbackEx) {
                ex.addSuppressed(rollbackEx);
            }
            throw ex;
        } finally {
            try {
                conn.setAutoCommit(previousAutoCommit);
            } catch (SQLException restoreEx) {
                if (failure != null) {
                    failure.addSuppressed(restoreEx);
                } else {
                    throw restoreEx;
                }
            }
        }
    }

    /** Plan-1 Phase 3b (docs/24 §1.6): fail closed unless the live results_v2 schema is on the
     *  5-column sample identity this writer upserts against. Checks, in order: (1) the schema_meta
     *  stamp is present and on this writer's version + sample-index identity; (2) the live unique
     *  index named {@link #SAMPLE_INDEX_NAME} exists on exactly the 5 sample columns; (3) the retired
     *  3-column index was not resurrected (an old binary's {@link #ensureSchema} re-creates it, and
     *  the two cannot coexist for K&gt;1). Throws {@link SchemaCapabilityMismatch} on any failure;
     *  returns normally when the live schema matches. Read-only -- never mutates the schema.
     *  Mirrors py_executor.validate_results_v2_schema_capability. */
    public static void validateCapability(Connection conn) throws SQLException {
        int version;
        String uniqueIndex;
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(
                     "SELECT version, unique_index FROM public.results_v2_schema_meta WHERE id = 1")) {
            if (!rs.next()) {
                throw new SchemaCapabilityMismatch(SCHEMA_CAPABILITY_MISMATCH
                        + ": results_v2_schema_meta stamp is missing -- the DB has not been migrated "
                        + "to the version " + SCHEMA_VERSION + " sample-identity schema");
            }
            version = rs.getInt(1);
            uniqueIndex = rs.getString(2);
        }
        if (version != SCHEMA_VERSION || !SAMPLE_INDEX_NAME.equals(uniqueIndex)) {
            throw new SchemaCapabilityMismatch(SCHEMA_CAPABILITY_MISMATCH + ": live schema version="
                    + version + " unique_index=" + uniqueIndex + " != this writer's version="
                    + SCHEMA_VERSION + " unique_index=" + SAMPLE_INDEX_NAME);
        }
        String idxdef = indexDef(conn, SAMPLE_INDEX_NAME);
        if (idxdef == null || !idxdef.contains("unique index")
                || !idxdef.contains("(run_id, candidate_id, attempt, repeat_idx, env_id)")) {
            throw new SchemaCapabilityMismatch(SCHEMA_CAPABILITY_MISMATCH + ": the live unique index "
                    + SAMPLE_INDEX_NAME + " is missing or is not the 5-column sample key (found: "
                    + (idxdef == null ? "none" : idxdef) + ")");
        }
        if (indexDef(conn, LEGACY_INDEX_NAME) != null) {
            throw new SchemaCapabilityMismatch(SCHEMA_CAPABILITY_MISMATCH + ": the legacy 3-column "
                    + "index " + LEGACY_INDEX_NAME + " was resurrected (an old executor binary); it "
                    + "conflicts with the 5-column sample key and must not coexist");
        }
    }

    /** The whitespace-normalized, lower-cased {@code indexdef} of a results_v2 index, or null when
     *  no such index exists. */
    private static String indexDef(Connection conn, String indexName) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='results_v2' "
                + "AND indexname = ?")) {
            ps.setString(1, indexName);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) return null;
                return rs.getString(1).replaceAll("\\s+", " ").toLowerCase();
            }
        }
    }

    /** Plan-1 Phase 3b/3c: the machine-readable capability self-report the launcher reads BEFORE this
     *  binary connects -- to fence out genuinely-old artifacts that cannot advertise the 5-column
     *  sample-identity writer (docs/24 §1.6), AND (3c) to gate Java K>1 only when this binary
     *  advertises the local/metrics repeat fan-out. Hand-built JSON (no JSON dependency on this path);
     *  mirrors the {@code repeat} + {@code results_v2_schema} blocks of py_executor.capability_document
     *  (same keys/values, so probe_*_executor_repeat_capability accept either executor). */
    public static String capabilityDocumentJson() {
        return "{\"schema\":\"java_executor.capabilities/v1\","
                + "\"repeat\":{\"local_metrics\":true,\"local_all\":true,\"max_k\":1024"
                + ",\"raw_sample_identity\":true,\"runtime_accounting\":true},"
                + "\"results_v2_schema\":{\"version\":" + SCHEMA_VERSION
                + ",\"unique_index\":\"" + SAMPLE_INDEX_NAME + "\""
                + ",\"sample_identity_writer\":true}}";
    }
}
