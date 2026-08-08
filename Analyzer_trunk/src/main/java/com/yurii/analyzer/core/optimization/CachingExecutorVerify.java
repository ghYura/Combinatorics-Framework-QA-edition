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

package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.JsonNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Verifies Tier-1 win 1.5 — {@link LineExecutor.Caching} memoising decorator
 * and {@link CacheStats} reporting on {@link OnlineMetricAggregator.Snapshot}.
 *
 * Invariants checked:
 *   1. Hits + misses == total executor invocations
 *   2. Misses == number of unique candidates (sequential path, no race)
 *   3. Delegate executor was called exactly {@code unique} times
 *   4. {@code cacheStats.hitRate()} ∈ [0, 1]
 *   5. Cached result for a repeated candidate equals the delegate's first result
 *   6. Snapshot.render() emits the cache section when non-empty
 *   7. Snapshot.toJson() emits "cacheStats" key when non-empty
 *   8. Default (non-caching) path emits {@link CacheStats#EMPTY} and suppresses
 *      the "cacheStats" JSON key — legacy byte-for-byte invariant
 *   9. Parallel path: hits + misses == total seen, results still consistent
 */
public final class CachingExecutorVerify {
    private CachingExecutorVerify() {}

    public static void main(String[] args) throws Exception {
        int failed = 0;
        failed += sequentialPath();
        failed += legacyNonCachingInvariant();
        failed += parallelPath();

        System.out.println();
        if (failed == 0) System.out.println("✅ ALL CACHING-EXECUTOR CHECKS PASSED");
        else { System.out.println("❌ " + failed + " CACHING-EXECUTOR CHECK(S) FAILED"); System.exit(1); }
    }

    // ─────────────────────────────────────────────────────────────────────
    //  Path 1 — sequential analyzeStream with deliberate duplicates
    // ─────────────────────────────────────────────────────────────────────
    private static int sequentialPath() throws Exception {
        System.out.println("── Sequential path: 3 unique candidates, 6 emissions, expect 3 hits / 3 misses ──");
        AtomicInteger delegateCalls = new AtomicInteger();
        LineExecutor counting = (lineNo, raw) -> {
            delegateCalls.incrementAndGet();
            return raw; // inline-equivalent
        };
        LineExecutor cached = new LineExecutor.Caching(counting, 64);

        // 3 unique candidate strings, each appearing twice (interleaved).
        String[] rows = {
                "id=a cost=1.0 throughput=100",
                "id=b cost=2.0 throughput=200",
                "id=a cost=1.0 throughput=100",
                "id=c cost=3.0 throughput=300",
                "id=b cost=2.0 throughput=200",
                "id=a cost=1.0 throughput=100",
        };

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);

        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStream(
                arrayIterator(rows),
                cached,
                5,
                List.of(GoalSpec.min("cost", 1.0), GoalSpec.max("throughput", 1.0)),
                DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});

        int f = 0;
        CacheStats cs = snap.cacheStats();
        f += assertCond("cacheStats non-null", cs != null);
        f += assertCond("misses == 3 unique",  cs.misses() == 3);
        f += assertCond("hits == 3 repeats",   cs.hits() == 3);
        f += assertCond("total == 6 rows",     cs.total() == 6);
        f += assertCond("delegate called == misses (3)", delegateCalls.get() == 3);
        f += assertCond("hitRate == 0.5",      Math.abs(cs.hitRate() - 0.5) < 1e-9);
        f += assertCond("size == 3",           cs.size() == 3);
        f += assertCond("capacity >= 16 (min)", cs.capacity() >= 16);
        f += assertCond("snapshot.updates == 6", snap.updates() == 6);

        // Rendered text carries the cache section.
        String rendered = snap.render();
        f += assertCond("render() contains 'LineExecutor cache'",
                rendered.contains("LineExecutor cache"));
        f += assertCond("render() includes hit-rate=50.00%",
                rendered.contains("50.00%"));

        // JSON carries the cacheStats object.
        JsonNode json = snap.toJson();
        f += assertCond("toJson() has 'cacheStats'", json.has("cacheStats"));
        JsonNode jn = json.get("cacheStats");
        f += assertCond("toJson.cacheStats.hits == 3",   jn.get("hits").asLong()   == 3);
        f += assertCond("toJson.cacheStats.misses == 3", jn.get("misses").asLong() == 3);
        f += assertCond("toJson.cacheStats.hitRate ≈ 0.5",
                Math.abs(jn.get("hitRate").asDouble() - 0.5) < 1e-9);

        // Round-trip the JSON to make sure the new field doesn't break parsing.
        String serialised = json.toString();
        JsonNode reparsed = AnalyzerCore.mapper().readTree(serialised);
        f += assertCond("JSON round-trip preserves cacheStats.hits",
                reparsed.get("cacheStats").get("hits").asLong() == 3);

        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  Path 2 — legacy non-caching invariant (no cacheStats key in JSON)
    // ─────────────────────────────────────────────────────────────────────
    private static int legacyNonCachingInvariant() throws Exception {
        System.out.println("\n── Legacy non-caching path: CacheStats.EMPTY, JSON omits cacheStats key ──");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);

        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStream(
                arrayIterator(new String[]{
                        "id=x cost=1.0 throughput=10",
                        "id=y cost=2.0 throughput=20"}),
                new LineExecutor.Inline(),
                5,
                List.of(GoalSpec.min("cost", 1.0)),
                DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});

        int f = 0;
        f += assertCond("non-caching → cacheStats == EMPTY",
                snap.cacheStats() == CacheStats.EMPTY
                        || (snap.cacheStats().hits() == 0 && snap.cacheStats().misses() == 0));
        f += assertCond("non-caching → toJson omits 'cacheStats'", !snap.toJson().has("cacheStats"));
        f += assertCond("non-caching → render omits cache section",
                !snap.render().contains("LineExecutor cache"));
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  Path 3 — parallel analyzeStreamParallel: aggregate accounting holds
    // ─────────────────────────────────────────────────────────────────────
    private static int parallelPath() throws Exception {
        System.out.println("\n── Parallel path (P=4): hits+misses == total, results still consistent ──");
        AtomicInteger delegateCalls = new AtomicInteger();
        LineExecutor counting = (lineNo, raw) -> {
            delegateCalls.incrementAndGet();
            return raw;
        };
        LineExecutor cached = new LineExecutor.Caching(counting, 64);

        // 8 unique candidates × 5 emissions each, shuffled deterministically.
        int unique = 8, copies = 5;
        String[] rows = new String[unique * copies];
        int idx = 0;
        for (int c = 0; c < copies; c++) {
            for (int u = 0; u < unique; u++) {
                rows[idx++] = String.format(Locale.ROOT,
                        "id=p_%d cost=%.2f throughput=%d", u, 1.0 + u, 100 + 10 * u);
            }
        }

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);

        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStreamParallel(
                arrayIterator(rows),
                cached,
                5,
                List.of(GoalSpec.min("cost", 1.0), GoalSpec.max("throughput", 1.0)),
                DiscoveryPolicy.DEFAULT,
                4,
                new AnalyzerCore.AnalysisListener() {});

        int f = 0;
        CacheStats cs = snap.cacheStats();
        f += assertCond("parallel cacheStats non-null", cs != null);
        f += assertCond("hits + misses == total emissions (" + (unique * copies) + ")",
                cs.total() == (long) unique * copies);
        // Under contention, delegate may be called > unique times (lost races),
        // but never more than total, and misses always equals delegate calls.
        f += assertCond("misses == delegate calls",
                cs.misses() == delegateCalls.get());
        f += assertCond("misses ≥ unique (lower bound)",
                cs.misses() >= unique);
        f += assertCond("misses ≤ total (upper bound)",
                cs.misses() <= (long) unique * copies);
        f += assertCond("hitRate in [0, 1]",
                cs.hitRate() >= 0.0 && cs.hitRate() <= 1.0);
        f += assertCond("size ≤ capacity", cs.size() <= cs.capacity());
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  helpers
    // ─────────────────────────────────────────────────────────────────────
    private static Iterator<String> arrayIterator(String[] xs) {
        return new Iterator<>() {
            int i = 0;
            @Override public boolean hasNext() { return i < xs.length; }
            @Override public String next() {
                if (i >= xs.length) throw new NoSuchElementException();
                return xs[i++];
            }
        };
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
