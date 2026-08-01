package com.company;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * Plan-1 Phase 3b launcher-side schema safety (docs/24 §1.6) -- the Java mirror of
 * {@code test_results_v2_schema_capability.py}. Drives {@link ResultsV2SchemaMigrator#validateCapability}
 * against a real Postgres on the scenarios the contract calls for:
 *   - fresh install: ensureSchema stamps results_v2_schema_meta v2 and validateCapability passes;
 *   - legacy 3-col migration: a DB on the old 3-col index is cut over, stamped, and validates;
 *   - compatible reconnect: a second ensureSchema re-stamps the singleton, still validates;
 *   - fail closed (RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH) on: missing stamp, wrong version,
 *     missing/wrong 5-col index, and a resurrected legacy 3-col index.
 *
 * Needs a reachable local Postgres -- creates and drops its own temporary database (never touches an
 * existing one). Coordinates from env vars: BUNDLE_RESULTS_DB_HOST (default 127.0.0.1),
 * BUNDLE_RESULTS_DB_PORT (default 5432), BUNDLE_RESULTS_DB_USER (default postgres),
 * BUNDLE_RESULTS_DB_PASSWORD (required -- fails closed, not skips, if absent).
 *
 * Run:  java -cp target/classes:<postgres-driver.jar> com.company.ResultsV2SchemaCapabilityTest
 */
public final class ResultsV2SchemaCapabilityTest {
    private ResultsV2SchemaCapabilityTest() {}

    public static void main(String[] args) {
        String dbHost = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_HOST", "127.0.0.1");
        String dbPort = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_PORT", "5432");
        String dbUser = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_USER", "postgres");
        String dbPassword = System.getenv("BUNDLE_RESULTS_DB_PASSWORD");
        if (dbPassword == null || dbPassword.isEmpty()) {
            System.out.println("ResultsV2SchemaCapabilityTest: FAIL -- BUNDLE_RESULTS_DB_PASSWORD is not set "
                    + "(this smoke needs a reachable local Postgres; it fails closed rather than skipping)");
            System.exit(1);
        }

        String adminUrl = "jdbc:postgresql://" + dbHost + ":" + dbPort + "/postgres";
        String tempDbName = "results_v2_capability_smoke_" + System.currentTimeMillis();
        int failures = 1;
        boolean dbCreated = false;

        try (Connection admin = DriverManager.getConnection(adminUrl, dbUser, dbPassword)) {
            admin.setAutoCommit(true);
            try (Statement st = admin.createStatement()) {
                st.execute("CREATE DATABASE \"" + tempDbName + "\"");
            }
            dbCreated = true;
            String tempUrl = "jdbc:postgresql://" + dbHost + ":" + dbPort + "/" + tempDbName;
            try (Connection conn = DriverManager.getConnection(tempUrl, dbUser, dbPassword)) {
                failures = runChecks(conn);
            }
        } catch (SQLException e) {
            System.out.println("ResultsV2SchemaCapabilityTest: FAIL -- " + e);
            failures = 1;
        } finally {
            if (dbCreated) {
                try (Connection admin = DriverManager.getConnection(adminUrl, dbUser, dbPassword);
                     Statement st = admin.createStatement()) {
                    admin.setAutoCommit(true);
                    st.execute("DROP DATABASE IF EXISTS \"" + tempDbName + "\" WITH (FORCE)");
                } catch (SQLException dropEx) {
                    System.out.println("ResultsV2SchemaCapabilityTest: WARNING -- could not drop temp database \""
                            + tempDbName + "\": " + dropEx);
                }
            }
        }

        System.out.println(failures == 0 ? "ResultsV2SchemaCapabilityTest: ALL OK"
                : "ResultsV2SchemaCapabilityTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int runChecks(Connection conn) throws SQLException {
        int failures = 0;

        // 1) fresh install: ensureSchema stamps v2 and validateCapability passes.
        ResultsV2SchemaMigrator.ensureSchema(conn);
        failures += check("fresh install stamps results_v2_schema_meta v2 + sample index",
                metaVersion(conn) == ResultsV2SchemaMigrator.SCHEMA_VERSION
                        && ResultsV2SchemaMigrator.SAMPLE_INDEX_NAME.equals(metaUniqueIndex(conn)));
        failures += check("fresh install: validateCapability passes (compatible)", validatesOk(conn));

        // 2) compatible reconnect: re-running ensureSchema re-stamps the singleton, still validates.
        ResultsV2SchemaMigrator.ensureSchema(conn);
        failures += check("compatible reconnect: exactly one meta stamp row + still validates",
                metaRowCount(conn) == 1 && validatesOk(conn));

        // 3) missing stamp -> fail closed.
        exec(conn, "DELETE FROM public.results_v2_schema_meta");
        failures += check("missing schema_meta stamp -> RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH",
                failsClosed(conn));

        // restore a clean migrated state for the remaining corruptions.
        ResultsV2SchemaMigrator.ensureSchema(conn);

        // 4) wrong version -> fail closed.
        exec(conn, "UPDATE public.results_v2_schema_meta SET version = 99 WHERE id = 1");
        failures += check("wrong schema_meta version -> RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH",
                failsClosed(conn));
        exec(conn, "UPDATE public.results_v2_schema_meta SET version = "
                + ResultsV2SchemaMigrator.SCHEMA_VERSION + " WHERE id = 1");

        // 5) missing/wrong 5-col index -> fail closed (stamp present but no backing index).
        exec(conn, "DROP INDEX public." + ResultsV2SchemaMigrator.SAMPLE_INDEX_NAME);
        failures += check("missing 5-col sample index -> RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH",
                failsClosed(conn));
        ResultsV2SchemaMigrator.ensureSchema(conn);   // re-create the sample index + stamp

        // 6) resurrected legacy 3-col index -> fail closed.
        exec(conn, "CREATE UNIQUE INDEX " + ResultsV2SchemaMigrator.LEGACY_INDEX_NAME
                + " ON public.results_v2 (run_id, candidate_id, attempt)");
        failures += check("resurrected legacy 3-col index -> RESULTS_V2_SCHEMA_CAPABILITY_MISMATCH",
                failsClosed(conn));

        // 7) the capability self-report advertises the 5-col writer (what the launcher fences on).
        String doc = ResultsV2SchemaMigrator.capabilityDocumentJson();
        failures += check("capability doc advertises the 5-col sample-identity writer -- got " + doc,
                doc.contains("\"version\":2")
                        && doc.contains("\"unique_index\":\"results_v2_sample_uk\"")
                        && doc.contains("\"sample_identity_writer\":true"));

        return failures;
    }

    private static boolean validatesOk(Connection conn) throws SQLException {
        try {
            ResultsV2SchemaMigrator.validateCapability(conn);
            return true;
        } catch (ResultsV2SchemaMigrator.SchemaCapabilityMismatch m) {
            System.out.println("    (unexpected mismatch: " + m.getMessage() + ")");
            return false;
        }
    }

    private static boolean failsClosed(Connection conn) throws SQLException {
        try {
            ResultsV2SchemaMigrator.validateCapability(conn);
            return false;   // should have thrown
        } catch (ResultsV2SchemaMigrator.SchemaCapabilityMismatch m) {
            return m.getMessage() != null
                    && m.getMessage().startsWith(ResultsV2SchemaMigrator.SCHEMA_CAPABILITY_MISMATCH);
        }
    }

    private static int metaVersion(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             var rs = st.executeQuery("SELECT version FROM public.results_v2_schema_meta WHERE id=1")) {
            return rs.next() ? rs.getInt(1) : -1;
        }
    }

    private static String metaUniqueIndex(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             var rs = st.executeQuery("SELECT unique_index FROM public.results_v2_schema_meta WHERE id=1")) {
            return rs.next() ? rs.getString(1) : null;
        }
    }

    private static long metaRowCount(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             var rs = st.executeQuery("SELECT count(*) FROM public.results_v2_schema_meta")) {
            rs.next();
            return rs.getLong(1);
        }
    }

    private static void exec(Connection conn, String sql) throws SQLException {
        try (Statement st = conn.createStatement()) {
            st.execute(sql);
        }
    }

    private static int check(String description, boolean condition) {
        System.out.println((condition ? "  ok  " : "  FAIL ") + description);
        return condition ? 0 : 1;
    }
}
