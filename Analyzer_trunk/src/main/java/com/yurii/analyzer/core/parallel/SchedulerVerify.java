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

package com.yurii.analyzer.core.parallel;

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.optimization.DiscoveryPolicy;
import com.yurii.analyzer.core.optimization.GoalSpec;
import com.yurii.analyzer.core.optimization.LineExecutor;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator;

import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Verifies Tier-3 win 3.3 — pluggable {@link Scheduler} shelf.
 *
 * Three sub-tests:
 *   1. Numerical equivalence across all three schedulers — same input, same
 *      per-key stats (Welford μ/σ/n/min/max), same Pareto-front size.
 *   2. {@link LeastLoadedScheduler} balance — under cost skew (every 4th task
 *      sleeps), every worker still receives a fair share (max-min ≤ N/P + P).
 *   3. {@link CapabilityAwareScheduler} routing — tagged tasks reach only
 *      workers whose declared capability set contains the tag.  Verified via
 *      per-worker thread-name introspection.
 */
public final class SchedulerVerify {
    private SchedulerVerify() {}

    public static void main(String[] args) throws Exception {
        int failed = 0;
        failed += numericalEquivalence();
        failed += leastLoadedBalance();
        failed += capabilityRouting();

        System.out.println();
        if (failed == 0) System.out.println("✅ ALL SCHEDULER CHECKS PASSED");
        else { System.out.println("❌ " + failed + " SCHEDULER CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── 1. Numerical equivalence ───────────────────────────────────────
    private static int numericalEquivalence() throws Exception {
        System.out.println("── 1. Numerical equivalence across schedulers ──");
        int N = 2000, parallelism = 4;
        OptimizationAnalyzer analyzer = newAnalyzer();
        List<GoalSpec> goals = List.of(
                GoalSpec.min("cost", 1.0),
                GoalSpec.max("throughput", 1.0));

        OnlineMetricAggregator.Snapshot ws = analyzer.analyzeStreamParallel(
                kvStream(N), new LineExecutor.Inline(), 10, goals,
                DiscoveryPolicy.DEFAULT, parallelism,
                new WorkStealingScheduler(parallelism),
                new AnalyzerCore.AnalysisListener() {});
        OnlineMetricAggregator.Snapshot ll = analyzer.analyzeStreamParallel(
                kvStream(N), new LineExecutor.Inline(), 10, goals,
                DiscoveryPolicy.DEFAULT, parallelism,
                new LeastLoadedScheduler(parallelism, 64),
                new AnalyzerCore.AnalysisListener() {});
        OnlineMetricAggregator.Snapshot ca = analyzer.analyzeStreamParallel(
                kvStream(N), new LineExecutor.Inline(), 10, goals,
                DiscoveryPolicy.DEFAULT, parallelism,
                new CapabilityAwareScheduler(parallelism, Map.of(), LineTagger.NONE),
                new AnalyzerCore.AnalysisListener() {});

        int f = 0;
        f += assertCond("WorkStealing.updates == N", ws.updates() == N);
        f += assertCond("LeastLoaded.updates  == N", ll.updates() == N);
        f += assertCond("CapabilityAware.updates == N", ca.updates() == N);

        for (String key : List.of("cost", "throughput")) {
            var ksWs = ws.perKeyStats().get(key);
            var ksLl = ll.perKeyStats().get(key);
            var ksCa = ca.perKeyStats().get(key);
            f += assertCond(key + ".n consistent (WS vs LL)",     ksWs.n == ksLl.n);
            f += assertCond(key + ".n consistent (WS vs CA)",     ksWs.n == ksCa.n);
            f += assertCond(key + ".mean ≈ across schedulers",
                    Math.abs(ksWs.mean - ksLl.mean) < 1e-9
                            && Math.abs(ksWs.mean - ksCa.mean) < 1e-9);
            f += assertCond(key + ".stdev ≈ across schedulers",
                    Math.abs(ksWs.stdev() - ksLl.stdev()) < 1e-9
                            && Math.abs(ksWs.stdev() - ksCa.stdev()) < 1e-9);
            f += assertCond(key + ".min equal", ksWs.min == ksLl.min && ksWs.min == ksCa.min);
            f += assertCond(key + ".max equal", ksWs.max == ksLl.max && ksWs.max == ksCa.max);
        }
        f += assertCond("Pareto front size equal (WS vs LL vs CA)",
                ws.paretoFront().size() == ll.paretoFront().size()
                        && ws.paretoFront().size() == ca.paretoFront().size());
        return f;
    }

    // ─── 2. LeastLoadedScheduler balance under skew ─────────────────────
    private static int leastLoadedBalance() throws Exception {
        System.out.println("\n── 2. LeastLoaded balance under cost skew ──");
        int N = 800, parallelism = 4;
        AtomicInteger[] perWorker = new AtomicInteger[parallelism];
        for (int i = 0; i < parallelism; i++) perWorker[i] = new AtomicInteger();

        LineExecutor instrumented = (lineNo, raw) -> {
            int w = workerIdFromThreadName();
            if (w >= 0 && w < parallelism) perWorker[w].incrementAndGet();
            // Every 8th task is "slow" (small sleep) — without active routing
            // this creates head-of-line blocking on the shared queue.
            if ((lineNo & 7) == 0) {
                try { Thread.sleep(2); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
            }
            return raw;
        };
        OptimizationAnalyzer analyzer = newAnalyzer();
        analyzer.analyzeStreamParallel(
                kvStream(N), instrumented, 5, List.of(GoalSpec.min("cost", 1.0)),
                DiscoveryPolicy.DEFAULT, parallelism,
                new LeastLoadedScheduler(parallelism, 32),
                new AnalyzerCore.AnalysisListener() {});

        int total = 0, min = Integer.MAX_VALUE, max = 0;
        for (AtomicInteger ai : perWorker) {
            int v = ai.get();
            total += v;
            if (v < min) min = v;
            if (v > max) max = v;
        }
        System.out.println("  per-worker counts: " + describe(perWorker));

        int f = 0;
        f += assertCond("LL: all tasks accounted for (" + total + " == " + N + ")", total == N);
        f += assertCond("LL: every worker received at least one task", min > 0);
        // Tolerant bound: max-min ≤ N/P + P  (a few-task slack under contention).
        int bound = N / parallelism + parallelism;
        f += assertCond("LL: max-min worker count ≤ N/P + P  (" + (max - min) + " ≤ " + bound + ")",
                (max - min) <= bound);
        return f;
    }

    // ─── 3. CapabilityAware routing ─────────────────────────────────────
    private static int capabilityRouting() throws Exception {
        System.out.println("\n── 3. CapabilityAware routes by tag ──");
        int N = 400, parallelism = 4;
        // Workers 0,1 → "py"; workers 2,3 → "sh".
        Map<Integer, Set<String>> caps = Map.of(
                0, Set.of("py"),
                1, Set.of("py"),
                2, Set.of("sh"),
                3, Set.of("sh"));
        LineTagger tagger = (lineNo, raw) ->
                raw.startsWith("py ") ? "py" : raw.startsWith("sh ") ? "sh" : "";
        Scheduler sched = new CapabilityAwareScheduler(parallelism, caps, tagger, 32);

        ConcurrentHashMap<Integer, Integer> pyCount = new ConcurrentHashMap<>();
        ConcurrentHashMap<Integer, Integer> shCount = new ConcurrentHashMap<>();

        LineExecutor recorder = (lineNo, raw) -> {
            int w = workerIdFromThreadName();
            (raw.startsWith("py ") ? pyCount : shCount)
                    .merge(w, 1, Integer::sum);
            return raw;
        };

        OptimizationAnalyzer analyzer = newAnalyzer();
        analyzer.analyzeStreamParallel(
                taggedStream(N), recorder, 5, List.of(),
                DiscoveryPolicy.DEFAULT, parallelism,
                sched, new AnalyzerCore.AnalysisListener() {});

        System.out.println("  py-task counts per worker: " + pyCount);
        System.out.println("  sh-task counts per worker: " + shCount);

        int f = 0;
        // py tasks must land only on workers 0,1; sh tasks only on 2,3.
        for (Map.Entry<Integer, Integer> e : pyCount.entrySet()) {
            f += assertCond("py task on worker " + e.getKey() + " is in {0,1}",
                    e.getKey() == 0 || e.getKey() == 1);
        }
        for (Map.Entry<Integer, Integer> e : shCount.entrySet()) {
            f += assertCond("sh task on worker " + e.getKey() + " is in {2,3}",
                    e.getKey() == 2 || e.getKey() == 3);
        }
        int pyTotal = pyCount.values().stream().mapToInt(Integer::intValue).sum();
        int shTotal = shCount.values().stream().mapToInt(Integer::intValue).sum();
        f += assertCond("py total + sh total == N (" + (pyTotal + shTotal) + " vs " + N + ")",
                pyTotal + shTotal == N);
        f += assertCond("py total == N/2 (" + pyTotal + ")", pyTotal == N / 2);
        f += assertCond("sh total == N/2 (" + shTotal + ")", shTotal == N / 2);
        return f;
    }

    // ─── helpers ────────────────────────────────────────────────────────

    private static OptimizationAnalyzer newAnalyzer() throws Exception {
        return new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 10, 30.0, 10.0, false, 0.0, false);
    }

    private static Iterator<String> kvStream(int n) {
        return new Iterator<>() {
            int i = 0;
            @Override public boolean hasNext() { return i < n; }
            @Override public String next() {
                if (i >= n) throw new NoSuchElementException();
                int id = i++;
                // Deterministic pseudo-random metrics for reproducibility.
                double cost = (id * 31 % 100) / 100.0 + 0.01;
                double tp   = ((id * 17 + 13) % 1000);
                return String.format(Locale.ROOT,
                        "id=k_%d cost=%.4f throughput=%.0f", id, cost, tp);
            }
        };
    }

    private static Iterator<String> taggedStream(int n) {
        return new Iterator<>() {
            int i = 0;
            @Override public boolean hasNext() { return i < n; }
            @Override public String next() {
                if (i >= n) throw new NoSuchElementException();
                int id = i++;
                String prefix = (id % 2 == 0) ? "py" : "sh";
                return prefix + " id=" + id + " cost=" + (id % 17) + " throughput=" + (id % 7);
            }
        };
    }

    private static int workerIdFromThreadName() {
        String n = Thread.currentThread().getName();
        int dash = n.lastIndexOf('-');
        if (dash < 0 || dash == n.length() - 1) return -1;
        try { return Integer.parseInt(n.substring(dash + 1)); }
        catch (NumberFormatException e) { return -1; }
    }

    private static String describe(AtomicInteger[] arr) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < arr.length; i++) {
            if (i > 0) sb.append(", ");
            sb.append('w').append(i).append('=').append(arr[i].get());
        }
        return sb.append(']').toString();
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
