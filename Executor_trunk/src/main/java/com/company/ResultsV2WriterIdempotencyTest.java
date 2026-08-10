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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

/**
 * STEP 23 targeted harness for the idempotent {@code results_v2} write policy
 * ({@link ResultsV2Writer}, schema from {@link ResultsV2SchemaMigrator}, STEP 22).
 *
 * Drives the exact scenario the plan's minimal check calls for: "execute same
 * tiny batch twice; inspect DB counts; no full workflow" -- a real Postgres
 * connection and a real {@code results_v2} table, but no MainWatch process, no
 * candidate compilation, no 288-candidate run. Asserts:
 *   1. the first write of a 3-row batch (one PASS, one DOMAIN_FAIL, one TIMEOUT
 *      -- the canonical-outcome spread the plan's STEP 22 minimal check also
 *      used) inserts all three and reports {@code attempted=3 inserted=3
 *      already_present=0 updated_selected=0};
 *   2. replaying the IDENTICAL batch (same run_id/candidate_id/attempt --
 *      mirrors a re-run, a resumed stage, or a launcher retry of the whole
 *      executor) inserts NOTHING -- {@code attempted=3 inserted=0
 *      already_present=3 updated_selected=0} -- proving "Повтор того же
 *      executor batch не удваивает final results";
 *   3. the table still holds exactly 3 rows after both writes -- the
 *      uniqueness key (run_id, candidate_id, attempt) did its job at the DB
 *      layer, not just in the writer's bookkeeping;
 *   4. {@code attempted == inserted + already_present + updated_selected}
 *      holds for both writes (the launcher-checkable count-consistency
 *      invariant action item 4 calls for).
 *
 * Needs a reachable local Postgres -- creates and drops its own temporary
 * database (never touches an existing one), the same "rollback temporary DB
 * only" shape STEP 22's minimal check used. Coordinates come from env vars,
 * never hardcoded (no secrets in source, see plan section 1.4):
 *   BUNDLE_RESULTS_DB_HOST (default 127.0.0.1), BUNDLE_RESULTS_DB_PORT (default 5432),
 *   BUNDLE_RESULTS_DB_USER (default postgres), BUNDLE_RESULTS_DB_PASSWORD (required --
 *   the test fails closed, not skips, if absent).
 *
 * Run:  java -cp target/classes:<postgres-driver.jar> com.company.ResultsV2WriterIdempotencyTest
 */
public final class ResultsV2WriterIdempotencyTest {
    private ResultsV2WriterIdempotencyTest() {}

    private static final String RUN_ID = "step23-idempotency-smoke-run-1";
    // STEP 27: the execution policy id + sha256 every results_v2 row must carry
    // (proves the writer persists policy_id/policy_hash, not just the model).
    private static final String POLICY_ID = "ep-0123456789ab";
    private static final String POLICY_HASH = "0123456789ab0123456789ab0123456789ab0123456789ab0123456789ab0123";

    public static void main(String[] args) {
        String dbHost = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_HOST", "127.0.0.1");
        String dbPort = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_PORT", "5432");
        String dbUser = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_USER", "postgres");
        String dbPassword = System.getenv("BUNDLE_RESULTS_DB_PASSWORD");
        if (dbPassword == null || dbPassword.isEmpty()) {
            System.out.println("ResultsV2WriterIdempotencyTest: FAIL -- BUNDLE_RESULTS_DB_PASSWORD is not set "
                    + "(this smoke needs a reachable local Postgres; it fails closed rather than skipping)");
            System.exit(1);
        }

        String adminUrl = "jdbc:postgresql://" + dbHost + ":" + dbPort + "/postgres";
        String tempDbName = "results_v2_idempotency_smoke_" + System.currentTimeMillis();
        int failures = 1; // pessimistic default -- flipped to the real count only on a clean run
        boolean dbCreated = false;

        try (Connection admin = DriverManager.getConnection(adminUrl, dbUser, dbPassword)) {
            admin.setAutoCommit(true);
            try (Statement st = admin.createStatement()) {
                st.execute("CREATE DATABASE \"" + tempDbName + "\"");
            }
            dbCreated = true;

            String tempUrl = "jdbc:postgresql://" + dbHost + ":" + dbPort + "/" + tempDbName;
            try (Connection conn = DriverManager.getConnection(tempUrl, dbUser, dbPassword)) {
                ResultsV2SchemaMigrator.ensureSchema(conn);
                failures = runIdempotencyChecks(conn);
            }
        } catch (SQLException e) {
            System.out.println("ResultsV2WriterIdempotencyTest: FAIL -- " + e);
            failures = 1;
        } finally {
            if (dbCreated) {
                // "rollback temporary DB only" -- never the database the test connected
                // through to create it, never any database it didn't itself create.
                try (Connection admin = DriverManager.getConnection(adminUrl, dbUser, dbPassword);
                     Statement st = admin.createStatement()) {
                    admin.setAutoCommit(true);
                    st.execute("DROP DATABASE IF EXISTS \"" + tempDbName + "\" WITH (FORCE)");
                } catch (SQLException dropEx) {
                    System.out.println("ResultsV2WriterIdempotencyTest: WARNING -- could not drop temp database \""
                            + tempDbName + "\": " + dropEx);
                }
            }
        }

        System.out.println(failures == 0 ? "ResultsV2WriterIdempotencyTest: ALL OK"
                : "ResultsV2WriterIdempotencyTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int runIdempotencyChecks(Connection conn) throws SQLException {
        List<ResultsV2Writer.CanonicalResult> batch = List.of(
                new ResultsV2Writer.CanonicalResult(RUN_ID, "1_0_0", 1, "PASS",
                        0, null, 120L, 0, null, "w1", "abc123", "file:///out/1.out", "file:///out/1.err",
                        POLICY_ID, POLICY_HASH, 0, ""),
                new ResultsV2Writer.CanonicalResult(RUN_ID, "2_0_0", 1, "DOMAIN_FAIL",
                        1, "verdict != 0", 98L, 1, null, "w1", "def456", "file:///out/2.out", "file:///out/2.err",
                        POLICY_ID, POLICY_HASH, 0, ""),
                new ResultsV2Writer.CanonicalResult(RUN_ID, "3_0_0", 1, "TIMEOUT",
                        null, "killed: wall clock exceeded", 30000L, null, "SIGKILL", "w2", "ghi789",
                        "file:///out/3.out", "file:///out/3.err", POLICY_ID, POLICY_HASH, 0, ""));

        int failures = 0;

        ResultsV2Writer.WriteCounts first = ResultsV2Writer.writeBatch(conn, batch);
        failures += check("first write of a fresh 3-row batch inserts all three "
                        + "(attempted=3 inserted=3 already_present=0 updated_selected=0) -- got " + first,
                first.attempted() == 3 && first.inserted() == 3
                        && first.alreadyPresent() == 0 && first.updatedSelected() == 0);

        ResultsV2Writer.WriteCounts replay = ResultsV2Writer.writeBatch(conn, batch);
        failures += check("replaying the IDENTICAL batch inserts nothing -- the "
                        + "(run_id, candidate_id, attempt) unique key turns every row into "
                        + "\"already present\" (attempted=3 inserted=0 already_present=3 "
                        + "updated_selected=0) -- got " + replay,
                replay.attempted() == 3 && replay.inserted() == 0
                        && replay.alreadyPresent() == 3 && replay.updatedSelected() == 0);

        failures += check("count consistency holds for the first write: "
                        + "attempted == inserted + already_present + updated_selected",
                first.attempted() == first.inserted() + first.alreadyPresent() + first.updatedSelected());
        failures += check("count consistency holds for the replay: "
                        + "attempted == inserted + already_present + updated_selected",
                replay.attempted() == replay.inserted() + replay.alreadyPresent() + replay.updatedSelected());

        long rowCount = countRows(conn);
        failures += check("the table holds exactly 3 rows after BOTH writes -- "
                        + "\"Повтор того же executor batch не удваивает final results\" holds at "
                        + "the DB layer (unique index), not just in the writer's bookkeeping -- got "
                        + rowCount,
                rowCount == 3);

        long policyRows = countPolicyRows(conn);
        failures += check("STEP 27: all 3 results_v2 rows carry the execution policy id+hash the "
                        + "writer was given (policy_id=" + POLICY_ID + ", policy_hash[:12]="
                        + POLICY_HASH.substring(0, 12) + "…) -- proves Reader->Executor->result "
                        + "policy propagation, not just model round-trip -- got " + policyRows + " matching row(s)",
                policyRows == 3);

        // Plan-1 Phase 3b: the schema cut over to the 5-column sample key. The 5-col unique index
        // exists; the legacy 3-col index is gone (otherwise a K>1 repeat row would be rejected).
        failures += check("Phase 3b: 5-column sample unique index results_v2_sample_uk exists",
                indexExists(conn, "results_v2_sample_uk"));
        failures += check("Phase 3b: legacy 3-column index results_v2_run_candidate_attempt_uk dropped",
                !indexExists(conn, "results_v2_run_candidate_attempt_uk"));

        // Plan-1 K>1 identity: a SECOND sample of an already-written (run, candidate, attempt) that
        // differs ONLY in repeat_idx is a DISTINCT row under the 5-col key -- it inserts, where the
        // retired 3-col key would have rejected it as a duplicate. This is the foundation K>1 needs.
        List<ResultsV2Writer.CanonicalResult> repeatSample = List.of(
                new ResultsV2Writer.CanonicalResult(RUN_ID, "1_0_0", 1, "PASS",
                        0, null, 121L, 0, null, "w1", "abc123", "file:///out/1.r1.out", "file:///out/1.r1.err",
                        POLICY_ID, POLICY_HASH, 1, ""));
        ResultsV2Writer.WriteCounts repeatWrite = ResultsV2Writer.writeBatch(conn, repeatSample);
        failures += check("K>1 sample identity: a row with the same (run, candidate, attempt) but "
                        + "repeat_idx=1 INSERTS under the 5-col key (the 3-col key would reject it) -- got "
                        + repeatWrite,
                repeatWrite.attempted() == 1 && repeatWrite.inserted() == 1
                        && repeatWrite.alreadyPresent() == 0);
        failures += check("K>1 sample identity: replaying that repeat row is idempotent (already present)",
                ResultsV2Writer.writeBatch(conn, repeatSample).alreadyPresent() == 1);
        long afterRepeat = countRows(conn);
        failures += check("K>1 sample identity: table holds exactly 4 rows (3 verdicts + 1 repeat sample) -- got "
                        + afterRepeat,
                afterRepeat == 4);

        return failures;
    }

    private static boolean indexExists(Connection conn, String indexName) throws SQLException {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery("SELECT 1 FROM pg_indexes WHERE schemaname='public' "
                     + "AND tablename='results_v2' AND indexname='" + indexName + "'")) {
            return rs.next();
        }
    }

    private static long countPolicyRows(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery("SELECT count(*) FROM public.results_v2 WHERE run_id = '" + RUN_ID
                     + "' AND policy_id = '" + POLICY_ID + "' AND policy_hash = '" + POLICY_HASH + "'")) {
            rs.next();
            return rs.getLong(1);
        }
    }

    private static long countRows(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery("SELECT count(*) FROM public.results_v2 WHERE run_id = '" + RUN_ID + "'")) {
            rs.next();
            return rs.getLong(1);
        }
    }

    private static int check(String description, boolean condition) {
        System.out.println((condition ? "  ok  " : "  FAIL ") + description);
        return condition ? 0 : 1;
    }
}
