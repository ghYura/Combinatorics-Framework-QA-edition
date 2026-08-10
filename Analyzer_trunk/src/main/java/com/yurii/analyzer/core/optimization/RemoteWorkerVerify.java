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

package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Tier-4.2 verifier: {@link LineExecutor.RemoteWorker} talks to a stub
 * {@code ResultPoller} so we can exercise the file-drop + poll loop without
 * a live Postgres / legacy-Executor pair.
 *
 * <p>What's covered:</p>
 * <ul>
 *   <li>Atomic file write into {@code srcDir} with the candidate id +
 *       configured extension.</li>
 *   <li>Stub poller returning {@code null} a few times then a result row →
 *       {@code execute} returns the row as {@code remote_id=… k=v k=v …}.</li>
 *   <li>Timeout path emits {@code remote_status=timeout}.</li>
 *   <li>{@code writeFile=false} bridge mode (Reader already wrote the file):
 *       RemoteWorker is pure poller, no file IO.</li>
 *   <li>Composition with {@link LineExecutor.Caching}: second {@code execute}
 *       on identical raw hits the cache, poller is NOT re-called.</li>
 *   <li>End-to-end through {@link OptimizationAnalyzer#analyzeStream}: the
 *       remote K=V payload is auto-discovered by the analyzer and
 *       {@code fw_var} appears in the snapshot's per-key stats.</li>
 *   <li>{@code idExtractorRegex} pulls the {@code combi_id} out of a
 *       Reader-style row.</li>
 * </ul>
 *
 *   Run:  java -cp ... RemoteWorkerVerify
 */
public final class RemoteWorkerVerify {
    private RemoteWorkerVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testFileWriteAndPollResult();
        failures += testTimeoutPath();
        failures += testWriteDisabledMode();
        failures += testCachingComposition();
        failures += testIdExtractorRegex();
        failures += testEndToEndThroughAnalyzer();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL REMOTE-WORKER CHECKS PASSED");
        else { System.out.println("❌ " + failures + " REMOTE-WORKER CHECK(S) FAILED"); System.exit(1); }
    }

    /** Stub that returns a result after {@code readyAfterCalls} polls.  Records
     *  every (candidateId, callNumber) for assertions. */
    private static final class StubPoller implements LineExecutor.RemoteWorker.ResultPoller {
        final AtomicInteger calls = new AtomicInteger();
        final List<String> seenIds = new ArrayList<>();
        final int readyAfterCalls;
        final Map<String, String> resultRow;
        StubPoller(int readyAfterCalls, Map<String, String> row) {
            this.readyAfterCalls = readyAfterCalls;
            this.resultRow = row;
        }
        @Override public synchronized Map<String, String> pollOnce(String candidateId) {
            int n = calls.incrementAndGet();
            seenIds.add(candidateId);
            return (n >= readyAfterCalls) ? resultRow : null;
        }
    }

    private static int testFileWriteAndPollResult() throws Exception {
        System.out.println("── file-write + result-poll round-trip ──");
        Path srcDir = Files.createTempDirectory("rw_smoke_");

        Map<String, String> row = new LinkedHashMap<>();
        row.put("fw_var",  "0");
        row.put("status",  "true");
        row.put("combi_id_final", "42");
        StubPoller stub = new StubPoller(3, row);

        LineExecutor.RemoteWorker rw = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir)
                .fileExtension(".java")
                .poller(stub)
                .pollIntervalMs(20)
                .timeoutSeconds(5.0)
                .build();

        String body = "public class C42 { public static int FW_VAR = 0;"
                    + " public static void main(String[] a){} }";
        String out = rw.execute(42, body);

        Path written = srcDir.resolve("42.java");
        int f = 0;
        f += assertCond("candidate file written at srcDir/42.java", Files.exists(written));
        f += assertCond("written file contents == raw payload",
                Files.readString(written).equals(body));
        f += assertCond("execute returned 'remote_id=42'", out.contains("remote_id=42"));
        f += assertCond("execute returned 'fw_var=0'",     out.contains("fw_var=0"));
        f += assertCond("execute returned 'status=true'",  out.contains("status=true"));
        f += assertCond("poller saw exactly 3 calls (1 null, 1 null, 1 result)",
                stub.calls.get() == 3);
        f += assertCond("every poll asked for id=42",
                stub.seenIds.stream().allMatch("42"::equals));

        cleanup(srcDir);
        return f;
    }

    private static int testTimeoutPath() throws Exception {
        System.out.println("\n── timeout path ──");
        Path srcDir = Files.createTempDirectory("rw_timeout_");
        LineExecutor.RemoteWorker.ResultPoller alwaysEmpty = id -> null;
        LineExecutor.RemoteWorker rw = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir)
                .poller(alwaysEmpty)
                .pollIntervalMs(20)
                .timeoutSeconds(0.15)
                .build();
        long t0 = System.nanoTime();
        String out = rw.execute(99, "anything");
        long elapsedMs = (System.nanoTime() - t0) / 1_000_000L;
        int f = 0;
        f += assertCond("execute returned 'remote_status=timeout'", out.contains("remote_status=timeout"));
        f += assertCond("execute returned 'remote_id=99'",         out.contains("remote_id=99"));
        f += assertCond("elapsed roughly matches timeoutSeconds (≥ 100 ms, ≤ 1500 ms)",
                elapsedMs >= 100 && elapsedMs <= 1500);
        cleanup(srcDir);
        return f;
    }

    /** Reader-bridge mode: file is presumed already on disk; RemoteWorker is
     *  pure poller.  Verify that no file is written. */
    private static int testWriteDisabledMode() throws Exception {
        System.out.println("\n── writeFile=false (Reader-bridge) ──");
        Path srcDir = Files.createTempDirectory("rw_bridge_");
        Map<String, String> row = new LinkedHashMap<>();
        row.put("fw_var", "7");
        StubPoller stub = new StubPoller(1, row);
        LineExecutor.RemoteWorker rw = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir)
                .poller(stub)
                .pollIntervalMs(10)
                .timeoutSeconds(2.0)
                .writeFile(false)
                .build();
        String out = rw.execute(7, "class C { public static int FW_VAR = 7; }");
        int f = 0;
        f += assertCond("no candidate file written when writeFile=false",
                Files.list(srcDir).count() == 0L);
        f += assertCond("poll-only mode still returns the row",
                out.contains("fw_var=7"));
        cleanup(srcDir);
        return f;
    }

    /** Caching decorator wraps RemoteWorker; second call with same raw must
     *  hit cache instead of re-polling. */
    private static int testCachingComposition() throws Exception {
        System.out.println("\n── Caching ∘ RemoteWorker composition ──");
        Path srcDir = Files.createTempDirectory("rw_cache_");
        Map<String, String> row = new LinkedHashMap<>();
        row.put("fw_var", "0");
        row.put("score",  "0.91");
        StubPoller stub = new StubPoller(1, row);
        LineExecutor inner = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir).poller(stub).pollIntervalMs(10).timeoutSeconds(2.0).build();
        LineExecutor cached = new LineExecutor.Caching(inner, 64);

        String body = "class C1 { static int FW_VAR=0; }";
        String first  = cached.execute(1, body);
        String second = cached.execute(1, body);   // same raw → cache hit
        int f = 0;
        f += assertCond("first call returned the result",        first.contains("fw_var=0"));
        f += assertCond("second call returned identical payload", first.equals(second));
        f += assertCond("poller invoked exactly once (cached hit on 2nd call)",
                stub.calls.get() == 1);
        f += assertCond("CacheStats: hits >= 1 after the hit",
                cached.cacheStats().hits() >= 1);
        cleanup(srcDir);
        return f;
    }

    /** Builder.idExtractorRegex pulls the leading combi_id from a Reader-style
     *  row, falling back to lineNo on a non-match. */
    private static int testIdExtractorRegex() throws Exception {
        System.out.println("\n── idExtractorRegex pulls combi_id from row ──");
        Path srcDir = Files.createTempDirectory("rw_idx_");
        StubPoller stub = new StubPoller(1, Map.of("fw_var", "0"));
        LineExecutor.RemoteWorker rw = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir)
                .poller(stub)
                .pollIntervalMs(10)
                .timeoutSeconds(2.0)
                // Reader replaces FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE
                // with "<combi_id>_<opt>_<j>" — pull the leading number.
                .idExtractorRegex("\\b(\\d+)_\\d+_\\d+\\b")
                .build();
        String row = "// candidate 314_0_0 below\npublic class C { static int FW_VAR=0; }";
        String out = rw.execute(1, row);  // lineNo=1 should be ignored
        int f = 0;
        f += assertCond("execute used regex-extracted id 314, not lineNo 1",
                out.contains("remote_id=314"));
        f += assertCond("candidate file written as 314.java",
                Files.exists(srcDir.resolve("314.java")));

        // Fallback case: no match → lineNo.
        Path srcDir2 = Files.createTempDirectory("rw_idx_fb_");
        StubPoller stub2 = new StubPoller(1, Map.of("fw_var", "0"));
        LineExecutor.RemoteWorker rw2 = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir2)
                .poller(stub2)
                .pollIntervalMs(10)
                .timeoutSeconds(2.0)
                .idExtractorRegex("\\b(\\d+)_\\d+_\\d+\\b")
                .build();
        String out2 = rw2.execute(77, "no marker here");
        f += assertCond("idExtractor fell back to lineNo when regex missed",
                out2.contains("remote_id=77"));
        cleanup(srcDir);
        cleanup(srcDir2);
        return f;
    }

    /** Plug RemoteWorker into the full streaming pipeline and confirm the
     *  remote K=V flows into NSGA-II / per-key stats just like any other
     *  agnostic metric. */
    private static int testEndToEndThroughAnalyzer() throws Exception {
        System.out.println("\n── end-to-end: RemoteWorker → OptimizationAnalyzer ──");
        Path srcDir = Files.createTempDirectory("rw_e2e_");

        // Per-id result rows: id=1 fails, id=2 passes with a better score.
        Map<String, Map<String, String>> resultByCandidateId = new java.util.HashMap<>();
        Map<String, String> row1 = new LinkedHashMap<>();
        row1.put("fw_var", "1");  row1.put("score", "0.30");
        Map<String, String> row2 = new LinkedHashMap<>();
        row2.put("fw_var", "0");  row2.put("score", "0.95");
        Map<String, String> row3 = new LinkedHashMap<>();
        row3.put("fw_var", "0");  row3.put("score", "0.60");
        resultByCandidateId.put("1", row1);
        resultByCandidateId.put("2", row2);
        resultByCandidateId.put("3", row3);

        LineExecutor.RemoteWorker.ResultPoller dispatcher = id -> resultByCandidateId.get(id);
        LineExecutor remoteExec = new LineExecutor.RemoteWorker.Builder()
                .srcDir(srcDir).poller(dispatcher).pollIntervalMs(5).timeoutSeconds(2.0).build();

        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"fw_var\",\"mode\":\"minimize\",\"weight\":50},"
                    + "{\"key\":\"score\",\"mode\":\"maximize\",\"weight\":50}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false);

        List<String> corpus = List.of(
                "candidate 1",
                "candidate 2",
                "candidate 3");
        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStream(
                corpus.iterator(),
                remoteExec,
                /*topK*/ 3,
                analyzer.goals().stream().map(g ->
                        ("maximize".equals(g.mode))
                                ? GoalSpec.max(g.key, g.weight)
                                : GoalSpec.min(g.key, g.weight)).toList(),
                DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});

        int f = 0;
        f += assertCond("3 candidates processed", snap.updates() == 3);
        f += assertCond("fw_var stream discovered through RemoteWorker payload",
                snap.perKeyStats().containsKey("fw_var"));
        f += assertCond("score stream discovered through RemoteWorker payload",
                snap.perKeyStats().containsKey("score"));
        OnlineMetricAggregator.KeyStats fwStats = snap.perKeyStats().get("fw_var");
        f += assertCond("fw_var min == 0 (candidates 2 and 3 passed)",
                fwStats != null && Math.abs(fwStats.min) < 1e-9);
        f += assertCond("fw_var max == 1 (candidate 1 failed)",
                fwStats != null && Math.abs(fwStats.max - 1.0) < 1e-9);
        f += assertCond("Pareto front non-empty",
                snap.paretoFront() != null && !snap.paretoFront().isEmpty());

        // Best-by-score candidate should be the one with score=0.95 (id 2).
        List<LineResult> top = snap.topByScore();
        f += assertCond("topByScore non-empty", top != null && !top.isEmpty());

        cleanup(srcDir);
        return f;
    }

    private static void cleanup(Path dir) {
        try {
            if (dir == null || !Files.exists(dir)) return;
            try (var s = Files.walk(dir)) {
                s.sorted(java.util.Comparator.reverseOrder())
                        .forEach(p -> { try { Files.deleteIfExists(p); } catch (Exception ignored) {} });
            }
        } catch (Exception ignored) {}
    }

    @SuppressWarnings("unused")
    private static String dump(String label, Object o) {
        return String.format(Locale.ROOT, "%s=%s", label, o);
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
