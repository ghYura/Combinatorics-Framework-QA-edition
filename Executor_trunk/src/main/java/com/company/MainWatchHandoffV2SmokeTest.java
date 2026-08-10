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

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.time.Duration;
import java.time.Instant;

/**
 * STEP 19 end-to-end smoke: unlike {@link HandoffManifestV2SmokeTest} (which only exercises
 * {@link HandoffManifestV2#load}), this one actually launches {@link MainWatch} as a real
 * subprocess with a {@code -manifest} pointing at one tiny "java" v2 candidate, lets it
 * compile+run that candidate end to end in Bundle full-verdict mode, lets the finite
 * manifest corpus auto-complete, and asserts both {@code executor-summary.json} and the
 * canonical {@code results_v2} row. The smoke creates and drops an isolated temporary DB.
 *
 * Needs a reachable local Postgres -- MainWatch only starts watching candidates after its
 * resultsDbURL handshake succeeds (dbMgr.init()), even with --writeToDB false. Coordinates
 * come from env vars, never hardcoded (no secrets in source, see plan section 1.4):
 *   BUNDLE_RESULTS_DB_HOST (default 127.0.0.1), BUNDLE_RESULTS_DB_PORT (default 5432),
 *   BUNDLE_RESULTS_DB_USER (default postgres), BUNDLE_RESULTS_DB_NAME (default postgres),
 *   BUNDLE_RESULTS_DB_PASSWORD (required -- the test fails closed, not skips, if absent).
 *
 * Run:  java -cp ... com.company.MainWatchHandoffV2SmokeTest
 */
public final class MainWatchHandoffV2SmokeTest {
    private MainWatchHandoffV2SmokeTest() {}

    private static final String CANDIDATE_NAME = "100000_0_0";
    private static final String CANDIDATE_SOURCE =
            "public class C { public static int FW_VAR = 0; public static void main(String[] args) {} }";
    private static final String INSERT_SQL = "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);"; // 9 '?' -> placeholders=9 -> FW_VAR mode
    private static final String RUN_ID = "smoke-mainwatch-run-1";

    public static void main(String[] args) throws Exception {
        int failures = runOneCandidateAndCheckSummary();
        System.out.println(failures == 0 ? "MainWatchHandoffV2SmokeTest: ALL OK" : "MainWatchHandoffV2SmokeTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int runOneCandidateAndCheckSummary() throws Exception {
        // The assembly JAR contains both JDBC implementations but only one service entry;
        // load the PostgreSQL driver explicitly for this standalone smoke's DriverManager calls.
        Class.forName("org.postgresql.Driver");
        String dbHost = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_HOST", "127.0.0.1");
        String dbPort = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_PORT", "5432");
        String dbUser = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_USER", "postgres");
        String adminDb = System.getenv().getOrDefault("BUNDLE_RESULTS_DB_NAME", "postgres");
        String dbPassword = System.getenv("BUNDLE_RESULTS_DB_PASSWORD");
        if (dbPassword == null || dbPassword.isEmpty()) {
            System.out.println("MainWatchHandoffV2SmokeTest: FAIL -- BUNDLE_RESULTS_DB_PASSWORD is not set "
                    + "(this smoke needs a reachable local Postgres; it fails closed rather than skipping)");
            return 1;
        }

        String dbName = "mainwatch_handoff_v2_smoke_" + System.currentTimeMillis();
        boolean dbCreated = false;
        Path root = Files.createTempDirectory("mainwatch-handoff-v2-smoke");
        Process process = null;
        try {
            createDatabase(dbHost, dbPort, adminDb, dbUser, dbPassword, dbName);
            dbCreated = true;
            createLegacyResultsTable(dbHost, dbPort, dbName, dbUser, dbPassword);
            Path candidatesDir = mkdir(root, "candidates");
            Path jarsDir = mkdir(root, "jars");
            Path argumentsDir = mkdir(root, "arguments");
            Path runFirstOnceDir = mkdir(root, "runFirstOnce");
            Path sqlTemplateDir = mkdir(root, "sqlTemplate");
            Path resultsDbUrlDir = mkdir(root, "resultsDbURL");
            Path out2Dir = mkdir(root, "out2");

            Path candidateFile = candidatesDir.resolve(CANDIDATE_NAME + ".java");
            Files.writeString(candidateFile, CANDIDATE_SOURCE, StandardCharsets.UTF_8);

            Path manifestPath = root.resolve("manifest.json");
            Files.writeString(manifestPath, "{"
                    + "\"protocol\":\"bundle.handoff/v2\","
                    + "\"run_id\":" + jsonString(RUN_ID) + ","
                    + "\"language\":\"java\","
                    + "\"candidate_transport\":\"loose-files\","
                    + "\"candidate_count\":1,"
                    + "\"id_format\":\"<combi_id>_0_0\","
                    + "\"sources\":[{\"kind\":\"dir\",\"path\":" + jsonString(candidatesDir.toString()) + "}],"
                    + "\"result_target\":{\"host\":" + jsonString(dbHost) + ",\"port\":" + dbPort
                    + ",\"database\":" + jsonString(dbName) + ",\"user\":" + jsonString(dbUser) + "},"
                    + "\"result_schema_mode\":\"placeholders=9\","
                    + "\"verdict_mode\":\"FW_VAR\","
                    + "\"arguments\":[],"
                    + "\"shift\":1,"
                    + "\"preprocess\":null,"
                    + "\"execution_policy_ref\":\"trusted-local\""
                    + "}", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("execution_policy.json"), "{"
                    + "\"id\":\"trusted-local\","
                    + "\"sha256\":\"smoke-test\","
                    + "\"policy\":{"
                    + "\"backend\":\"local\","
                    + "\"trusted\":true,"
                    + "\"allowed_interpreters\":[\"java\",\"javac\"]"
                    + "}}", StandardCharsets.UTF_8);

            Path stdout = root.resolve("mainwatch.stdout.log");
            Path stderr = root.resolve("mainwatch.stderr.log");
            process = launchMainWatch(manifestPath, candidatesDir, jarsDir, argumentsDir, runFirstOnceDir,
                    sqlTemplateDir, resultsDbUrlDir, out2Dir, stdout, stderr);

            // Give the directory watchers (resultsDbURL / insert.sql / srcDirList) time to register
            // before we drop the handshake files that drive them -- a watcher only sees events that
            // occur AFTER it registers, so pre-existing-at-launch files would never be noticed.
            Thread.sleep(3000);
            if (!process.isAlive()) {
                System.out.println("MainWatchHandoffV2SmokeTest: FAIL -- MainWatch exited early (code="
                        + process.exitValue() + "); see " + stdout + " / " + stderr);
                return 1;
            }

            String jdbcUrl = "jdbc:postgresql://" + dbHost + ":" + dbPort + "/" + dbName
                    + "?user=" + dbUser + "&password=" + dbPassword;
            writeHandshakeFile(resultsDbUrlDir.resolve("resultsDbURL.properties"), jdbcUrl);
            Thread.sleep(1000);
            writeHandshakeFile(sqlTemplateDir.resolve("insert.sql"), INSERT_SQL);

            boolean processed = waitUntil(Duration.ofSeconds(90), () -> !Files.exists(candidateFile));
            if (!processed) {
                System.out.println("MainWatchHandoffV2SmokeTest: FAIL -- candidate " + candidateFile
                        + " was not picked up/processed within the timeout; see " + stdout + " / " + stderr);
                return 1;
            }

            // Bundle mode is a finite manifest corpus. MainWatch must exit itself after the
            // declared candidate count completes, then its shutdown hook flushes both result
            // stores and writes executor-summary.json. No launcher-side guess/sleep/SIGTERM.
            boolean exited = process.waitFor(30, java.util.concurrent.TimeUnit.SECONDS);
            if (!exited) {
                process.destroyForcibly();
                System.out.println("MainWatchHandoffV2SmokeTest: FAIL -- MainWatch did not auto-exit "
                        + "after the manifest corpus completed; see " + stdout + " / " + stderr);
                return 1;
            }

            Path summaryPath = out2Dir.resolve("executor-summary.json");
            boolean summaryWritten = waitUntil(Duration.ofSeconds(15), () -> Files.exists(summaryPath));
            if (!summaryWritten) {
                System.out.println("MainWatchHandoffV2SmokeTest: FAIL -- " + summaryPath
                        + " was never written; see " + stdout + " / " + stderr);
                return 1;
            }
            String summary = Files.readString(summaryPath, StandardCharsets.UTF_8);

            int failures = 0;
            failures += check(summary, "\"schema\":\"bundle.executor-summary/v1\"");
            failures += check(summary, "\"language\":\"java\"");
            failures += check(summary, "\"processed_count\":1");
            failures += check(summary, "\"manifest_protocol\":\"bundle.handoff/v2\"");
            failures += check(summary, "\"manifest_run_id\":" + jsonString(RUN_ID));
            failures += check(summary, "\"manifest_candidate_count\":1");
            failures += check(summary, "\"results_v2_write_counts\":{\"attempted\":1,\"inserted\":1,"
                    + "\"already_present\":0,\"updated_selected\":0}");
            failures += checkResultRow(dbHost, dbPort, dbName, dbUser, dbPassword);
            if (failures == 0) {
                System.out.println("runOneCandidateAndCheckSummary: OK -- " + summaryPath + " = " + summary);
            }
            return failures;
        } finally {
            if (process != null && process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(10, java.util.concurrent.TimeUnit.SECONDS);
            }
            if (dbCreated) {
                dropDatabase(dbHost, dbPort, adminDb, dbUser, dbPassword, dbName);
            }
            deleteRecursively(root);
        }
    }

    private static Process launchMainWatch(Path manifestPath, Path candidatesDir, Path jarsDir, Path argumentsDir,
                                            Path runFirstOnceDir, Path sqlTemplateDir, Path resultsDbUrlDir,
                                            Path out2Dir, Path stdout, Path stderr) throws IOException {
        String javaBin = System.getProperty("java.home") + java.io.File.separator + "bin" + java.io.File.separator + "java";
        java.util.List<String> cmd = java.util.List.of(
                javaBin, "-cp", System.getProperty("java.class.path"), "com.company.MainWatch",
                "-manifest", manifestPath.toString(),
                "-srcDirList", candidatesDir.toString(),
                "-dirJars", jarsDir.toString(),
                "-dirArguments", argumentsDir.toString(),
                "-dirRunFirstOnce", runFirstOnceDir.toString(),
                "-dirSqlTemplate", sqlTemplateDir.toString(),
                "-dirResultsDbURL", resultsDbUrlDir.toString(),
                "-out2", out2Dir.toString(),
                "-failOnly", "false",
                "-exitWhenComplete", "true",
                "--writeToDB", "true");
        ProcessBuilder pb = new ProcessBuilder(cmd)
                .redirectOutput(stdout.toFile())
                .redirectError(stderr.toFile());
        return pb.start();
    }

    private static void createDatabase(String host, String port, String adminDb, String user,
                                       String password, String dbName) throws Exception {
        try (Connection con = DriverManager.getConnection(
                "jdbc:postgresql://" + host + ":" + port + "/" + adminDb, user, password);
             Statement st = con.createStatement()) {
            con.setAutoCommit(true);
            st.execute("CREATE DATABASE \"" + dbName + "\"");
        }
    }

    private static void createLegacyResultsTable(String host, String port, String dbName,
                                                 String user, String password) throws Exception {
        try (Connection con = DriverManager.getConnection(
                "jdbc:postgresql://" + host + ":" + port + "/" + dbName, user, password);
             Statement st = con.createStatement()) {
            st.execute("CREATE TABLE results (status boolean, attachment text, fw_var integer, "
                    + "combi_id integer, optional_id integer, sequence_id integer, "
                    + "check_1 boolean, check_2 boolean, check_3 boolean)");
        }
    }

    private static void dropDatabase(String host, String port, String adminDb, String user,
                                     String password, String dbName) {
        try (Connection con = DriverManager.getConnection(
                "jdbc:postgresql://" + host + ":" + port + "/" + adminDb, user, password);
             Statement st = con.createStatement()) {
            con.setAutoCommit(true);
            st.execute("DROP DATABASE IF EXISTS \"" + dbName + "\" WITH (FORCE)");
        } catch (Exception e) {
            System.out.println("MainWatchHandoffV2SmokeTest: WARNING -- could not drop temp DB "
                    + dbName + ": " + e);
        }
    }

    private static int checkResultRow(String host, String port, String dbName, String user,
                                      String password) throws Exception {
        try (Connection con = DriverManager.getConnection(
                "jdbc:postgresql://" + host + ":" + port + "/" + dbName, user, password);
             Statement st = con.createStatement();
             ResultSet rs = st.executeQuery("SELECT count(*), min(outcome), max(attempt) "
                     + "FROM public.results_v2 WHERE run_id='" + RUN_ID + "'")) {
            rs.next();
            boolean ok = rs.getLong(1) == 1 && "PASS".equals(rs.getString(2)) && rs.getInt(3) == 1;
            if (!ok) {
                System.out.println("MISMATCH: expected one PASS attempt=1 in results_v2, got count="
                        + rs.getLong(1) + " outcome=" + rs.getString(2) + " attempt=" + rs.getInt(3));
            }
            return ok ? 0 : 1;
        }
    }

    private static Path mkdir(Path root, String name) throws IOException {
        return Files.createDirectories(root.resolve(name));
    }

    /** Writes via create-then-write so the watcher (registered earlier) observes a fresh
     *  ENTRY_CREATE followed by the ENTRY_MODIFY it actually keys off of. */
    private static void writeHandshakeFile(Path path, String content) throws IOException {
        Files.writeString(path, "", StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        Files.writeString(path, content, StandardCharsets.UTF_8, StandardOpenOption.WRITE);
    }

    private static boolean waitUntil(Duration timeout, java.util.function.BooleanSupplier condition) throws InterruptedException {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline)) {
            if (condition.getAsBoolean()) return true;
            Thread.sleep(500);
        }
        return condition.getAsBoolean();
    }

    private static int check(String haystack, String expectedFragment) {
        if (haystack.contains(expectedFragment)) return 0;
        System.out.println("MISMATCH: expected to find " + expectedFragment + " in " + haystack);
        return 1;
    }

    private static String jsonString(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var stream = Files.walk(root)) {
            stream.sorted(java.util.Comparator.reverseOrder()).forEach(p -> {
                try { Files.delete(p); } catch (IOException ignored) {}
            });
        }
    }
}
