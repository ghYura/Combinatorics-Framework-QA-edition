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
import java.sql.SQLException;
import java.util.HashMap;
import java.util.Map;

/**
 * Narrow STEP 17 smoke test: exercises {@link HandoffManifestWriter#writeManifestV2()}
 * against a synthetic legacy-handshake fixture (no DB, no candidate generation pipeline)
 * and checks the emitted manifest.json is atomic, well-formed, and count-consistent.
 * Schema-shape validation against bundle-handoff-v2.schema.json is done separately
 * (Python side owns that validator — see generator_trunk/bundle/handoff.py).
 *
 * Run:  java -cp ... com.company.HandoffManifestWriterSmokeTest
 */
public final class HandoffManifestWriterSmokeTest {
    private HandoffManifestWriterSmokeTest() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testDualWriteProducesValidManifest();
        failures += testCandidateCountFromSinkRegistry();   // STEP 31
        failures += testFailClosedOnCountMismatch();         // STEP 31
        failures += testFailClosedOnSinkErrors();            // STEP 31
        System.out.println(failures == 0 ? "HandoffManifestWriterSmokeTest: ALL OK" : "HandoffManifestWriterSmokeTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int testDualWriteProducesValidManifest() throws IOException, SQLException {
        Path root = Files.createTempDirectory("handoff-manifest-smoke");
        try {
            com.company.sink.CandidateSinkRegistry.reset(); // STEP 31: exercise the disk-fallback path (no sink ran)
            Path candidatesDir = root.resolve("candidates");
            Files.createDirectories(candidatesDir);
            int n = 5;
            for (int i = 1; i <= n; i++) Files.writeString(candidatesDir.resolve(i + "00000_0_0.java"), "// candidate " + i);
            Files.writeString(candidatesDir.resolve("ignored.txt"), "not a candidate");

            Path argsFile = root.resolve("arguments/args");
            Files.createDirectories(argsFile.getParent());
            Files.writeString(argsFile, " --foo bar --baz");
            Files.writeString(root.resolve("arguments/fwVar.shift"), "1");

            Path runOnce = root.resolve("runFirstOnce/runmefirstonce.first");
            Files.createDirectories(runOnce.getParent());
            Files.writeString(runOnce, "String FW_PATH_FILES_TO = \"/tmp/x\";");

            Path insertSql = root.resolve("sqlTemplate/insert.sql");
            Files.createDirectories(insertSql.getParent());
            Files.writeString(insertSql, "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);");

            Path manifestPath = root.resolve("handoff/manifest.json");

            installFixtureConfig(candidatesDir, insertSql, argsFile, runOnce, manifestPath);

            HandoffManifestWriter.writeManifestV2();

            if (!Files.exists(manifestPath)) return fail("manifest.json was not written to " + manifestPath);
            String json = Files.readString(manifestPath, StandardCharsets.UTF_8);

            int failures = 0;
            failures += expectContains(json, "\"protocol\":\"bundle.handoff/v2\"");
            failures += expectContains(json, "\"run_id\":\"smoketest-run-0001\"");
            failures += expectContains(json, "\"language\":\"java\"");
            failures += expectContains(json, "\"candidate_transport\":\"loose-files\"");
            failures += expectContains(json, "\"candidate_count\":" + n);
            failures += expectContains(json, "\"id_format\":\"<combi_id>_0_0\"");
            failures += expectContains(json, "\"kind\":\"dir\"");
            failures += expectContains(json, "\"host\":\"127.0.0.1\"");
            failures += expectContains(json, "\"database\":\"smoketest_db\"");
            failures += expectContains(json, "\"result_schema_mode\":\"placeholders=9\"");
            failures += expectContains(json, "\"verdict_mode\":\"FW_VAR\"");
            failures += expectContains(json, "\"custom_verdicts\":[]");
            failures += expectContains(json, "\"arguments\":[\"--foo\",\"bar\",\"--baz\"]");
            failures += expectContains(json, "\"shift\":1");
            failures += expectContains(json, "\"execution_policy_ref\":null");
            failures += expectBalancedJsonBraces(json);
            failures += validateAgainstV2Schema(manifestPath);

            // Re-run: must overwrite atomically (no partial/duplicated content, no leftover .tmp files).
            HandoffManifestWriter.writeManifestV2();
            long tmpLeftovers;
            try (var s = Files.list(manifestPath.getParent())) {
                tmpLeftovers = s.filter(p -> p.getFileName().toString().endsWith(".tmp")).count();
            }
            if (tmpLeftovers != 0) failures += fail("atomic write left " + tmpLeftovers + " .tmp file(s) behind");
            String json2 = Files.readString(manifestPath, StandardCharsets.UTF_8);
            if (!json2.equals(json)) failures += fail("re-run produced a different manifest for identical inputs (non-deterministic write)");

            return failures;
        } finally {
            deleteRecursively(root);
        }
    }

    // ───────────────────────────── STEP 31 ─────────────────────────────
    // candidate_count is the sink's authoritative tally (CandidateSinkRegistry),
    // and the manifest fails closed when that tally disagrees with the filesystem
    // or reports write errors.

    /** candidate_count is taken from the recorded sink summary, reconciled against disk. */
    private static int testCandidateCountFromSinkRegistry() throws IOException, SQLException {
        System.out.println("[STEP 31] candidate_count sourced from CandidateSinkRegistry");
        Path root = Files.createTempDirectory("handoff-step31-count");
        try {
            com.company.sink.CandidateSinkRegistry.reset();
            Path manifestPath = wireFixture(root, 5);
            // sink wrote 5 candidates, no errors — matches the 5 files on disk
            com.company.sink.CandidateSinkRegistry.record(
                    new com.company.sink.CandidateSink.Summary("loose-files", 5, 1234, 0, "abc123abc123abc1"));
            HandoffManifestWriter.writeManifestV2();
            String json = Files.readString(manifestPath, StandardCharsets.UTF_8);
            int f = 0;
            f += expectContains(json, "\"candidate_count\":5");
            f += expectContains(json, "\"candidate_transport\":\"loose-files\"");
            return f;
        } finally {
            com.company.sink.CandidateSinkRegistry.reset();
            deleteRecursively(root);
        }
    }

    /** sink count != files on disk ⇒ refuse to write a handoff (fail-closed). */
    private static int testFailClosedOnCountMismatch() throws IOException, SQLException {
        System.out.println("[STEP 31] fail-closed on sink/disk count mismatch");
        Path root = Files.createTempDirectory("handoff-step31-mismatch");
        try {
            com.company.sink.CandidateSinkRegistry.reset();
            Path manifestPath = wireFixture(root, 5);   // 5 candidate files on disk
            com.company.sink.CandidateSinkRegistry.record(
                    new com.company.sink.CandidateSink.Summary("loose-files", 7, 0, 0, "deadbeefdeadbeef")); // claims 7
            int f = 0;
            boolean threw = false;
            try {
                HandoffManifestWriter.writeManifestV2();
            } catch (IOException expected) {
                threw = true;
                f += expectContains(expected.getMessage(), "fail-closed");
            }
            f += assertTrue("count mismatch throws (fail-closed)", threw);
            f += assertTrue("no manifest written on fail-closed", !Files.exists(manifestPath));
            return f;
        } finally {
            com.company.sink.CandidateSinkRegistry.reset();
            deleteRecursively(root);
        }
    }

    /** sink reported write errors ⇒ refuse to write a handoff (fail-closed). */
    private static int testFailClosedOnSinkErrors() throws IOException, SQLException {
        System.out.println("[STEP 31] fail-closed on sink write errors");
        Path root = Files.createTempDirectory("handoff-step31-errors");
        try {
            com.company.sink.CandidateSinkRegistry.reset();
            Path manifestPath = wireFixture(root, 5);
            com.company.sink.CandidateSinkRegistry.record(
                    new com.company.sink.CandidateSink.Summary("loose-files", 5, 0, 2, "deadbeefdeadbeef")); // 2 errors
            int f = 0;
            boolean threw = false;
            try {
                HandoffManifestWriter.writeManifestV2();
            } catch (IOException expected) {
                threw = true;
                f += expectContains(expected.getMessage(), "error");
            }
            f += assertTrue("errors>0 throws (fail-closed)", threw);
            f += assertTrue("no manifest written on fail-closed", !Files.exists(manifestPath));
            return f;
        } finally {
            com.company.sink.CandidateSinkRegistry.reset();
            deleteRecursively(root);
        }
    }

    /** Minimal fixture: {@code n} candidate files + the legacy-handshake helper files,
     *  with an immutable test config snapshot installed for them. 9 insert.sql placeholders ⇒ FW_VAR mode
     *  (no results-DB lookup), so this needs neither a DB nor a generation pipeline. */
    private static Path wireFixture(Path root, int n) throws IOException {
        Path candidatesDir = root.resolve("candidates");
        Files.createDirectories(candidatesDir);
        for (int i = 1; i <= n; i++) Files.writeString(candidatesDir.resolve(i + "00000_0_0.java"), "// candidate " + i);

        Path argsFile = root.resolve("arguments/args");
        Files.createDirectories(argsFile.getParent());
        Files.writeString(argsFile, " --foo bar");
        Files.writeString(root.resolve("arguments/fwVar.shift"), "1");

        Path runOnce = root.resolve("runFirstOnce/runmefirstonce.first");
        Files.createDirectories(runOnce.getParent());
        Files.writeString(runOnce, "String FW_PATH_FILES_TO = \"/tmp/x\";");

        Path insertSql = root.resolve("sqlTemplate/insert.sql");
        Files.createDirectories(insertSql.getParent());
        Files.writeString(insertSql, "INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?);");

        Path manifestPath = root.resolve("handoff/manifest.json");
        installFixtureConfig(candidatesDir, insertSql, argsFile, runOnce, manifestPath);
        return manifestPath;
    }

    private static void installFixtureConfig(Path candidatesDir, Path insertSql, Path argsFile,
            Path runOnce, Path manifestPath) {
        Map<String, Object> overrides = new HashMap<>();
        overrides.put("fwFileExtension", ".java");
        overrides.put("pathFwOutZipDirList", java.util.List.of(candidatesDir.toString() + "/"));
        overrides.put("fwPathFilesTo", candidatesDir.toString() + "/");
        overrides.put("pathFwResultsDbSqlInsertTemplateFileResults", insertSql.toString());
        overrides.put("pathFwResultsArgumentsResults", argsFile.toString());
        overrides.put("pathFwResultsFirstRunOnceResults", runOnce.toString());
        overrides.put("pathFwResultsHandoffManifestResults", manifestPath.toString());
        overrides.put("handoffRunId", "smoketest-run-0001");
        overrides.put("handoffDualWrite", true);
        overrides.put("dbHostResults", "127.0.0.1");
        overrides.put("dbPortResults", 5432);
        overrides.put("dbName", "smoketest_db");
        overrides.put("dbUserResults", "smoketest_user");
        overrides.put("dbPasswordResults", "");
        ReaderConfig.installForTest(configWithOverrides(ReaderConfig.cfg(), overrides));
    }

    private static ReaderConfig.ReaderConfiguration configWithOverrides(
            ReaderConfig.ReaderConfiguration base, Map<String, Object> overrides) {
        try {
            var components = ReaderConfig.ReaderConfiguration.class.getRecordComponents();
            Class<?>[] parameterTypes = new Class<?>[components.length];
            Object[] values = new Object[components.length];
            for (int i = 0; i < components.length; i++) {
                var component = components[i];
                String name = component.getName();
                parameterTypes[i] = component.getType();
                values[i] = overrides.containsKey(name)
                        ? overrides.get(name)
                        : component.getAccessor().invoke(base);
            }
            return ReaderConfig.ReaderConfiguration.class
                    .getDeclaredConstructor(parameterTypes)
                    .newInstance(values);
        } catch (ReflectiveOperationException e) {
            throw new AssertionError("could not build ReaderConfiguration test fixture", e);
        }
    }

    private static int assertTrue(String label, boolean cond) {
        if (cond) return 0;
        return fail(label);
    }

    /** The acceptance criterion is "schema validate emitted manifest" — and the real
     *  bundle.handoff/v2 schema document plus its validator (validate_against_json_schema +
     *  HandoffV2/validate_handoff) live on the Python side (STEP 16, generator_trunk/bundle).
     *  Re-implementing that validator in Java would drift from the source of truth, so this
     *  shells out to python3 and runs the Java-emitted manifest.json through the actual
     *  schema document and the actual HandoffV2 parser/validator — a real cross-language
     *  contract check, not a string-fragment proxy for one. */
    private static int validateAgainstV2Schema(Path manifestPath) {
        Path generatorTrunk = Path.of(System.getProperty("user.dir")).resolve("../generator_trunk").normalize();
        Path schemaPath = generatorTrunk.resolve("bundle-handoff-v2.schema.json");
        if (!Files.isDirectory(generatorTrunk) || !Files.isRegularFile(schemaPath)) {
            return fail("cannot locate generator_trunk/bundle-handoff-v2.schema.json next to "
                    + generatorTrunk + " — schema validation skipped, treating as failure");
        }
        String script = String.join("\n",
                "import sys, json",
                "sys.path.insert(0, " + pyStr(generatorTrunk.toString()) + ")",
                "from bundle import handoff as h",
                "with open(" + pyStr(manifestPath.toString()) + ") as f:",
                "    data = json.load(f)",
                "with open(" + pyStr(schemaPath.toString()) + ") as f:",
                "    schema = json.load(f)",
                "h.validate_against_json_schema(data, schema)",
                "ho = h.handoff_from_dict(data)",
                "h.validate_handoff(ho)",
                "print('schema+HandoffV2 OK: run_id=' + ho.run_id + ' candidate_count=' + str(ho.candidate_count) + ' verdict_mode=' + ho.verdict_mode.value)"
        );
        try {
            Process p = new ProcessBuilder("python3", "-c", script).redirectErrorStream(true).start();
            String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            int code = p.waitFor();
            System.out.println("  [schema validation] " + out.strip().replace("\n", "\n  [schema validation] "));
            if (code != 0) return fail("manifest failed bundle-handoff-v2.schema.json / HandoffV2 validation (exit=" + code + ")");
            return 0;
        } catch (IOException | InterruptedException e) {
            return fail("could not run schema validation via python3: " + e);
        }
    }

    private static String pyStr(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static int expectContains(String haystack, String needle) {
        if (haystack.contains(needle)) return 0;
        return fail("manifest missing expected fragment: " + needle);
    }

    private static int expectBalancedJsonBraces(String json) {
        int depth = 0;
        boolean inString = false, escape = false;
        for (char c : json.toCharArray()) {
            if (escape) { escape = false; continue; }
            if (c == '\\' && inString) { escape = true; continue; }
            if (c == '"') { inString = !inString; continue; }
            if (inString) continue;
            if (c == '{' || c == '[') depth++;
            else if (c == '}' || c == ']') depth--;
            if (depth < 0) return fail("manifest JSON has unbalanced/closing-before-opening brackets");
        }
        return depth == 0 ? 0 : fail("manifest JSON has unbalanced brackets (end depth=" + depth + ")");
    }

    private static int fail(String msg) {
        System.out.println("  FAIL: " + msg);
        return 1;
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var walk = Files.walk(root)) {
            walk.sorted(java.util.Comparator.reverseOrder()).forEach(p -> { try { Files.delete(p); } catch (IOException _) {} });
        }
    }
}
