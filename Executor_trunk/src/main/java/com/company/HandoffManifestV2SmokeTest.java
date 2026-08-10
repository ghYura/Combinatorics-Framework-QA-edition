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

/**
 * Narrow STEP 19 smoke test for {@link HandoffManifestV2} (the Java-Executor-side
 * manifest parser/model -- see its javadoc and bundle-handoff-v2.schema.json):
 * one tiny "java" v2 manifest loads + validates against a synthetic one-candidate
 * source dir, and one manifest with a wrong major protocol version is rejected with
 * {@link HandoffManifestV2.ManifestError} (acceptance: "Invalid major protocol fail
 * closed"). Mirrors HandoffManifestWriterSmokeTest's narrow, no-DB, no-pipeline style
 * on the Reader side.
 *
 * Run:  java -cp ... com.company.HandoffManifestV2SmokeTest
 */
public final class HandoffManifestV2SmokeTest {
    private HandoffManifestV2SmokeTest() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testValidJavaManifestLoads();
        failures += testWrongMajorProtocolFailsClosed();
        System.out.println(failures == 0 ? "HandoffManifestV2SmokeTest: ALL OK" : "HandoffManifestV2SmokeTest: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static int testValidJavaManifestLoads() throws IOException {
        Path root = Files.createTempDirectory("handoff-v2-smoke");
        try {
            Path candidatesDir = root.resolve("candidates");
            Files.createDirectories(candidatesDir);
            Files.writeString(candidatesDir.resolve("100000_0_0.java"), "class C { public static int FW_VAR = 0; }");

            Path manifestPath = root.resolve("manifest.json");
            Files.writeString(manifestPath, "{"
                    + "\"protocol\":\"bundle.handoff/v2\","
                    + "\"run_id\":\"smoke-run-1\","
                    + "\"language\":\"java\","
                    + "\"candidate_transport\":\"loose-files\","
                    + "\"candidate_count\":1,"
                    + "\"id_format\":\"<combi_id>_0_0\","
                    + "\"sources\":[{\"kind\":\"dir\",\"path\":" + jsonString(candidatesDir.toString()) + "}],"
                    + "\"result_target\":{\"host\":\"localhost\",\"port\":5432,\"database\":\"results\",\"user\":\"postgres\"},"
                    + "\"result_schema_mode\":\"placeholders=9\","
                    + "\"verdict_mode\":\"FW_VAR\","
                    + "\"arguments\":[\"--foo\",\"bar\"],"
                    + "\"shift\":1,"
                    + "\"preprocess\":null"
                    + "}", StandardCharsets.UTF_8);

            HandoffManifestV2 m = HandoffManifestV2.load(manifestPath);

            int failures = 0;
            failures += check("protocol", HandoffManifestV2.EXPECTED_PROTOCOL, m.protocol);
            failures += check("language", "java", m.language);
            failures += check("candidate_transport", "loose-files", m.candidateTransport);
            failures += check("candidate_count", "1", Long.toString(m.candidateCount));
            failures += check("verdict_mode", "FW_VAR", m.verdictMode);
            failures += check("shift", "1", Integer.toString(m.shift));
            failures += check("source.path", candidatesDir.toString(), m.sources.get(0).path);
            failures += check("arguments", "[--foo, bar]", m.arguments.toString());
            if (failures == 0) System.out.println("testValidJavaManifestLoads: OK (run_id=" + m.runId + ")");
            return failures;
        } finally {
            deleteRecursively(root);
        }
    }

    private static int testWrongMajorProtocolFailsClosed() throws IOException {
        Path root = Files.createTempDirectory("handoff-v2-smoke-badproto");
        try {
            Path manifestPath = root.resolve("manifest.json");
            Files.writeString(manifestPath, "{"
                    + "\"protocol\":\"bundle.handoff/v3\","
                    + "\"run_id\":\"smoke-run-2\","
                    + "\"language\":\"java\","
                    + "\"candidate_transport\":\"loose-files\","
                    + "\"candidate_count\":0,"
                    + "\"id_format\":\"<combi_id>_0_0\","
                    + "\"sources\":[{\"kind\":\"dir\",\"path\":\"/tmp\"}],"
                    + "\"result_target\":{\"host\":\"localhost\",\"port\":5432,\"database\":\"results\"},"
                    + "\"result_schema_mode\":\"placeholders=9\","
                    + "\"verdict_mode\":\"FW_VAR\""
                    + "}", StandardCharsets.UTF_8);

            try {
                HandoffManifestV2 m = HandoffManifestV2.load(manifestPath);
                System.out.println("testWrongMajorProtocolFailsClosed: FAIL -- loaded a v3 manifest as v2 (protocol=" + m.protocol + ")");
                return 1;
            } catch (HandoffManifestV2.ManifestError e) {
                System.out.println("testWrongMajorProtocolFailsClosed: OK -- rejected (" + e.getMessage() + ")");
                return 0;
            }
        } finally {
            deleteRecursively(root);
        }
    }

    private static int check(String label, String expected, String actual) {
        if (expected.equals(actual)) return 0;
        System.out.println("MISMATCH " + label + ": expected " + expected + ", got " + actual);
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
