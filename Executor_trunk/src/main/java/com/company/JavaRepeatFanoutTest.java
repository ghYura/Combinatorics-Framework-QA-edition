package com.company;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Plan-1 3c sub-increment 2 -- the Java mirror of the {@code measure_metric_repeated} scenarios in
 * {@code Executor_trunk/test_py_executor_repeat.py}. Drives {@link MainWatch#processCandidateFileRepeated}
 * with REAL compiled candidates (fresh child classloader per repeat) and checks the contract:
 *   - success: K isolated invocations -> K raw metric rows, ONE canonical verdict row (sample 0,
 *     repeat_idx 0), correct repeat_runtime accounting, repeat-aware corpus;
 *   - canonical failure: sample 0 throws -> stop-on-canonical-failure (1 invocation), the remaining
 *     K-1 accounted as unattempted_after_canonical_failure (and missing), exactly one BROKEN verdict row;
 *   - partial/total metric loss: a candidate that produces its FW_VAR verdict but emits no metric line
 *     -> every repeat is a missing_measurement, the verdict still lands (V=C).
 *
 * Runs against the FAT JAR (needs the Janino/ECJ compiler + deps to compile candidates):
 *   java -cp target/Executor-1.0-jar-with-dependencies.jar com.company.JavaRepeatFanoutTest
 */
public class JavaRepeatFanoutTest {

    private static final String SUCCESS_EMIT =
            "public class FwCand {\n" +
            "    public static int FW_VAR;\n" +
            "    public static void main(String[] a) {\n" +
            "        FW_VAR = 0;\n" +
            "        String mp = System.getProperty(\"fw.metrics.out\");\n" +
            "        if (mp != null) {\n" +
            "            try { java.nio.file.Files.writeString(java.nio.file.Paths.get(mp), \"app=t key=1 FW_VAR=0\"); }\n" +
            "            catch (Exception e) { }\n" +
            "        }\n" +
            "    }\n" +
            "}\n";

    private static final String THROWS_BEFORE_EMIT =
            "public class FwCand {\n" +
            "    public static int FW_VAR;\n" +
            "    public static void main(String[] a) { throw new RuntimeException(\"boom\"); }\n" +
            "}\n";

    private static final String VERDICT_NO_EMIT =
            "public class FwCand {\n" +
            "    public static int FW_VAR;\n" +
            "    public static void main(String[] a) { FW_VAR = 0; }\n" +
            "}\n";

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testSuccessKSamples();
        failures += testCanonicalFailureStops();
        failures += testMetricLossAccountedMissing();
        failures += testLocalAllKVerdictRows();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL JAVA REPEAT-FANOUT CHECKS PASSED");
        else System.out.println("❌ " + failures + " JAVA REPEAT-FANOUT CHECK(S) FAILED");
        System.exit(failures == 0 ? 0 : 1);
    }

    // ── success: K=3 isolated invocations -> 3 samples + 1 canonical PASS row ─────────
    private static int testSuccessKSamples() throws Exception {
        System.out.println("\n── success: K=3 -> 3 raw samples, 1 canonical verdict row, corpus ──");
        Path work = Files.createTempDirectory("repeat-fanout-success");
        int f = 0;
        try {
            Path corpus = work.resolve("metrics.kv");
            setUp(work, corpus, 3, "1_0_0", SUCCESS_EMIT);
            Path cand = work.resolve("1_0_0.java");

            MainWatch.processCandidateFileRepeated(cand.toString());

            f += assertEq("opportunities", 3, MainWatch.repeatOpportunities.get());
            f += assertEq("invocations", 3, MainWatch.repeatInvocations.get());
            f += assertEq("metric_rows", 3, MainWatch.repeatMetricRows.get());
            f += assertEq("missing_measurements", 0, MainWatch.repeatMissingMeasurements.get());
            f += assertEq("failed_invocations", 0, MainWatch.repeatFailedInvocations.get());
            f += assertEq("unattempted_after_canonical_failure", 0, MainWatch.repeatUnattemptedAfterCanonicalFailure.get());
            f += assertEq("processed", 1, MainWatch.atomicInteger.get());
            f += assertEq("PASS outcomes", 1, MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get());
            f += assertEq("ONE canonical verdict row (never K)", 1, MainWatch.resultsV2ByCandidate.size());
            ResultsV2Writer.CanonicalResult row = MainWatch.resultsV2ByCandidate.get("1_0_0");
            f += assertCond("canonical outcome PASS", row != null && "PASS".equals(row.outcome()));
            f += assertCond("canonical repeat_idx == 0", row != null && row.repeatIdx() == 0);
            f += assertCond("canonical env_id == local:run-r", row != null && "local:run-r".equals(row.envId()));

            MainWatch.flushMetricsCorpusOnShutdown();
            String got = Files.readString(corpus, StandardCharsets.UTF_8);
            String expected =
                    "candidate_id=1_0_0 source_ref=1_0_0.java run_id=run-r repeat_idx=0 env_id=local:run-r app=t key=1 FW_VAR=0\n"
                  + "candidate_id=1_0_0 source_ref=1_0_0.java run_id=run-r repeat_idx=1 env_id=local:run-r app=t key=1 FW_VAR=0\n"
                  + "candidate_id=1_0_0 source_ref=1_0_0.java run_id=run-r repeat_idx=2 env_id=local:run-r app=t key=1 FW_VAR=0\n";
            f += assertCond("corpus has 3 repeat-aware lines (sorted by repeat_idx)", expected.equals(got));
            if (!expected.equals(got)) System.out.println("  --- expected ---\n" + expected + "  --- got ---\n" + got);
        } finally {
            tearDown(work);
        }
        return f;
    }

    // ── canonical failure: sample 0 throws -> 1 invocation, K-1 unattempted ───────────
    private static int testCanonicalFailureStops() throws Exception {
        System.out.println("\n── canonical failure: stop-on-failure, K-1 unattempted ──");
        Path work = Files.createTempDirectory("repeat-fanout-failure");
        int f = 0;
        try {
            Path corpus = work.resolve("metrics.kv");
            setUp(work, corpus, 3, "2_0_0", THROWS_BEFORE_EMIT);
            Path cand = work.resolve("2_0_0.java");

            MainWatch.processCandidateFileRepeated(cand.toString());

            f += assertEq("opportunities", 3, MainWatch.repeatOpportunities.get());
            f += assertEq("invocations (stopped after sample 0)", 1, MainWatch.repeatInvocations.get());
            f += assertEq("metric_rows", 0, MainWatch.repeatMetricRows.get());
            f += assertEq("missing_measurements (1 no-emit + 2 unattempted)", 3, MainWatch.repeatMissingMeasurements.get());
            f += assertEq("failed_invocations", 1, MainWatch.repeatFailedInvocations.get());
            f += assertEq("unattempted_after_canonical_failure", 2, MainWatch.repeatUnattemptedAfterCanonicalFailure.get());
            f += assertEq("processed", 1, MainWatch.atomicInteger.get());
            f += assertEq("BROKEN outcomes", 1, MainWatch.outcomeCounts.get(MainWatch.Outcome.BROKEN).get());
            f += assertEq("ONE canonical verdict row", 1, MainWatch.resultsV2ByCandidate.size());
            ResultsV2Writer.CanonicalResult row = MainWatch.resultsV2ByCandidate.get("2_0_0");
            f += assertCond("canonical outcome BROKEN", row != null && "BROKEN".equals(row.outcome()));
        } finally {
            tearDown(work);
        }
        return f;
    }

    // ── metric loss: verdict produced but no metric line -> all repeats missing ───────
    private static int testMetricLossAccountedMissing() throws Exception {
        System.out.println("\n── metric loss: verdict OK but no app= line -> missing_measurements ──");
        Path work = Files.createTempDirectory("repeat-fanout-missing");
        int f = 0;
        try {
            Path corpus = work.resolve("metrics.kv");
            setUp(work, corpus, 3, "3_0_0", VERDICT_NO_EMIT);
            Path cand = work.resolve("3_0_0.java");

            MainWatch.processCandidateFileRepeated(cand.toString());

            f += assertEq("opportunities", 3, MainWatch.repeatOpportunities.get());
            f += assertEq("invocations (no stop -- verdict produced)", 3, MainWatch.repeatInvocations.get());
            f += assertEq("metric_rows", 0, MainWatch.repeatMetricRows.get());
            f += assertEq("missing_measurements", 3, MainWatch.repeatMissingMeasurements.get());
            f += assertEq("failed_invocations", 0, MainWatch.repeatFailedInvocations.get());
            f += assertEq("unattempted_after_canonical_failure", 0, MainWatch.repeatUnattemptedAfterCanonicalFailure.get());
            f += assertEq("PASS outcomes (verdict still lands, V=C)", 1, MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get());
            f += assertEq("ONE canonical verdict row", 1, MainWatch.resultsV2ByCandidate.size());

            MainWatch.flushMetricsCorpusOnShutdown();
            String got = Files.readString(corpus, StandardCharsets.UTF_8);
            f += assertCond("empty corpus (no metric harvested)", got.isEmpty());
        } finally {
            tearDown(work);
        }
        return f;
    }

    // ── local/all: every sample is a full verdict -> K verdict rows per candidate (V=C·K) ──
    private static int testLocalAllKVerdictRows() throws Exception {
        System.out.println("\n── local/all: K=3 -> 3 verdict rows (repeat_idx 0..2), V=C·K ──");
        Path work = Files.createTempDirectory("repeat-fanout-all");
        int f = 0;
        try {
            Path corpus = work.resolve("metrics.kv");
            setUp(work, corpus, 3, "5_0_0", SUCCESS_EMIT);
            MainWatch.repeatScope = "all";          // every sample a full verdict (not metrics scope)
            Path cand = work.resolve("5_0_0.java");

            MainWatch.processCandidateFileRepeated(cand.toString());

            f += assertEq("opportunities", 3, MainWatch.repeatOpportunities.get());
            f += assertEq("invocations (no stop -- all independent verdicts)", 3, MainWatch.repeatInvocations.get());
            f += assertEq("metric_rows", 3, MainWatch.repeatMetricRows.get());
            f += assertEq("missing_measurements", 0, MainWatch.repeatMissingMeasurements.get());
            f += assertEq("unattempted_after_canonical_failure", 0, MainWatch.repeatUnattemptedAfterCanonicalFailure.get());
            f += assertEq("processed = K verdicts (V=C·K)", 3, MainWatch.atomicInteger.get());
            f += assertEq("PASS outcomes = K", 3, MainWatch.outcomeCounts.get(MainWatch.Outcome.PASS).get());
            f += assertEq("K verdict rows (one per repeat_idx, never 1)", 3, MainWatch.resultsV2ByCandidate.size());
            // index the K rows by their repeat_idx field (independent of the internal map-key format)
            java.util.Map<Integer, String> byIdx = new java.util.HashMap<>();
            MainWatch.resultsV2ByCandidate.values().forEach(v -> byIdx.put(v.repeatIdx(), v.outcome()));
            f += assertCond("verdict rows at repeat_idx 0,1,2 all PASS, all candidate 5_0_0",
                    "PASS".equals(byIdx.get(0)) && "PASS".equals(byIdx.get(1)) && "PASS".equals(byIdx.get(2))
                 && MainWatch.resultsV2ByCandidate.values().stream().allMatch(v -> "5_0_0".equals(v.candidateId())));
        } finally {
            tearDown(work);
        }
        return f;
    }

    // ── helpers ──────────────────────────────────────────────────────────────────────
    private static void setUp(Path work, Path corpus, int k, String candidateId, String source) throws Exception {
        reset();
        MainWatch.FW_CUSTOM_VARmode = false;   // FW_VAR verdict mode (the perf_opt_java campaign mode)
        MainWatch.repeatK = k;
        MainWatch.repeatPolicy = "local";
        MainWatch.repeatScope = "metrics";
        MainWatch.repeatEnvId = "local:run-r";
        MainWatch.resultsV2RunId = "run-r";
        MainWatch.resultsV2Attempt = 1;
        MainWatch.metricsCorpusFile = corpus.toString();
        MainWatch.metricsScratchDir = Files.createDirectories(work.resolve("sinks"));
        Files.writeString(work.resolve(candidateId + ".java"), source, StandardCharsets.UTF_8);
    }

    private static void reset() {
        MainWatch.harvestedMetrics.clear();
        MainWatch.resultsV2ByCandidate.clear();
        MainWatch.repeatOpportunities.set(0);
        MainWatch.repeatInvocations.set(0);
        MainWatch.repeatMetricRows.set(0);
        MainWatch.repeatMissingMeasurements.set(0);
        MainWatch.repeatFailedInvocations.set(0);
        MainWatch.repeatUnattemptedAfterCanonicalFailure.set(0);
        MainWatch.atomicInteger.set(0);
        for (MainWatch.Outcome o : MainWatch.Outcome.values()) MainWatch.outcomeCounts.get(o).set(0);
        MainWatch.repeatK = 1;
        MainWatch.metricsCorpusFile = null;
        MainWatch.metricsScratchDir = null;
        MainWatch.resultsV2RunId = null;
    }

    private static void tearDown(Path work) {
        reset();
        try (java.util.stream.Stream<Path> s = Files.walk(work)) {
            s.sorted(java.util.Comparator.reverseOrder()).forEach(p -> {
                try { Files.deleteIfExists(p); } catch (Exception ignore) { }
            });
        } catch (Exception ignore) { }
    }

    private static int assertEq(String label, int expected, int actual) {
        boolean ok = expected == actual;
        System.out.println((ok ? "  ✅ " : "  ❌ ") + label + " = " + actual + (ok ? "" : " (expected " + expected + ")"));
        return ok ? 0 : 1;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✅ " : "  ❌ ") + label);
        return cond ? 0 : 1;
    }
}
