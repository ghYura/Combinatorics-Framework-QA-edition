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
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.KeyStats;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;

/**
 * Stress-tests the streaming pipeline that the Combinatorics Framework will
 * drive in production:
 *
 *   • {@code analyzeStream(Iterator<String>, LineExecutor, …)} on 100K
 *     synthetic candidates,
 *   • {@code OnlineMetricAggregator} producing Welford stats + per-metric
 *     champions + online Pareto front,
 *   • bounded memory regardless of N (we measure heap before/after and assert
 *     it doesn't blow up linearly with the candidate count).
 *
 * Synthetic corpus is built via an {@code Iterator} that lazily emits one
 * candidate at a time — never materialised as a List.  Each candidate is
 * {@code "id=N cost=X latency=Yms throughput=Z accuracy=W"} with values
 * sampled from known distributions, so we can independently compute the
 * expected min/max/mean/argmin and assert the aggregator matches.
 *
 * Run:  java -cp target/classes:&lt;deps&gt; -Xmx512m
 *             com.yurii.analyzer.core.optimization.StreamingVerify [N]
 */
public final class StreamingVerify {
    private StreamingVerify() {}

    public static void main(String[] args) throws Exception {
        int N = args.length > 0 ? Integer.parseInt(args[0]) : 100_000;
        long seed = 1337L;
        System.out.println("Streaming " + N + " synthetic candidates (seed=" + seed + ")");

        // ─── Compute reference values offline (for correctness assertions) ─
        Random rng = new Random(seed);
        double[] cost = new double[N], latency = new double[N], throughput = new double[N], accuracy = new double[N];
        for (int i = 0; i < N; i++) {
            cost[i]       = 0.05 + rng.nextDouble() * 1.95;     // [0.05, 2.0]
            latency[i]    = 1.0  + rng.nextDouble() * 99.0;     // [1, 100] ms
            throughput[i] = 100.0 + rng.nextDouble() * 9900.0;  // [100, 10000]
            accuracy[i]   = 0.5  + rng.nextDouble() * 0.5;      // [0.5, 1.0]
        }
        // expected min/max + indices
        // Latency is emitted with "ms" suffix; aggregator canonicalises to
        // seconds (1ms = 1e-3 s).  Use seconds-scaled reference for assertions.
        double[] latencySec = new double[N];
        for (int i = 0; i < N; i++) latencySec[i] = latency[i] * 1e-3;
        Stat refCost = stat(cost), refLat = stat(latencySec), refThr = stat(throughput), refAcc = stat(accuracy);

        // ─── Stream the pipeline ──────────────────────────────────────────
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);

        // Memory probe BEFORE
        Runtime rt = Runtime.getRuntime();
        System.gc(); Thread.sleep(50); System.gc();
        long heapBefore = rt.totalMemory() - rt.freeMemory();

        Capture cap = new Capture();
        long t0 = System.nanoTime();
        Snapshot snap = analyzer.analyzeStream(
                new SyntheticIterator(N, seed),
                new LineExecutor.Inline(),
                /*topK*/ 10,
                /*maximize*/ java.util.Set.of("throughput", "accuracy"),
                cap);
        long elapsedMs = (System.nanoTime() - t0) / 1_000_000;

        // Memory probe AFTER
        System.gc(); Thread.sleep(50); System.gc();
        long heapAfter = rt.totalMemory() - rt.freeMemory();
        long heapDelta = heapAfter - heapBefore;

        System.out.println();
        System.out.println(snap.render());
        System.out.printf(Locale.ROOT, "%nElapsed: %d ms (%.0f cand/sec)%n",
                elapsedMs, 1000.0 * N / Math.max(1, elapsedMs));
        System.out.printf(Locale.ROOT, "Heap before=%.1fMB  after=%.1fMB  Δ=%.1fMB (~%d bytes/candidate)%n",
                heapBefore / 1e6, heapAfter / 1e6, heapDelta / 1e6, heapDelta / Math.max(1, N));

        // ─── Assertions ───────────────────────────────────────────────────
        int failures = 0;
        failures += assertCond("snapshot updates == N",  snap.updates() == N);
        failures += assertCond("4 metric streams discovered (cost, latency, throughput, accuracy)",
                snap.perKeyStats().size() == 4);

        KeyStats kc = snap.perKeyStats().get("cost");
        KeyStats kl = snap.perKeyStats().get("latency");
        KeyStats kt = snap.perKeyStats().get("throughput");
        KeyStats ka = snap.perKeyStats().get("accuracy");

        failures += assertCond("cost.n == N",        kc.n == N);
        failures += assertCond("cost.min ≈ ref",     near(kc.min, refCost.min, 1e-9));
        failures += assertCond("cost.max ≈ ref",     near(kc.max, refCost.max, 1e-9));
        failures += assertCond("cost.mean ≈ ref",    near(kc.mean, refCost.mean, 1e-6));
        failures += assertCond("cost.argmin line == ref",  kc.argminLineNo == refCost.argmin + 1);
        failures += assertCond("cost.argmax line == ref",  kc.argmaxLineNo == refCost.argmax + 1);

        failures += assertCond("latency.argmin line == ref",     kl.argminLineNo == refLat.argmin + 1);
        // Aggregator value is in seconds (canonicalised from "ms" suffix).
        failures += assertCond("latency unit-suffix canonicalised to seconds (mean ≈ 0.050)",
                near(kl.mean, refLat.mean, 1e-6));

        failures += assertCond("throughput.argmax line == ref",  kt.argmaxLineNo == refThr.argmax + 1);
        failures += assertCond("accuracy.argmax line == ref",    ka.argmaxLineNo == refAcc.argmax + 1);

        // Online Pareto sanity: every member should be on the offline Pareto.
        // We don't recompute the full offline Pareto (O(N²) at N=100K); instead
        // we check pairwise non-domination AMONG front members — necessary
        // condition for correctness.
        List<LineResult> front = snap.paretoFront();
        boolean pairwiseOk = true;
        for (int i = 0; i < front.size() && pairwiseOk; i++)
            for (int j = i + 1; j < front.size() && pairwiseOk; j++)
                if (offlineDominates(front.get(i), front.get(j))
                        || offlineDominates(front.get(j), front.get(i))) {
                    System.out.println("    ✗ front members " + i + " and " + j + " dominance-related");
                    pairwiseOk = false;
                }
        failures += assertCond("Pareto front pairwise non-dominated (size=" + front.size() + ")", pairwiseOk);

        // Memory bound: even at 100K candidates, heap delta should be modest.
        // Bound: 1KB/candidate is generous (real value ~50–200 bytes).  If
        // this fails, we're accidentally buffering all candidates.
        long bytesPerCand = heapDelta / Math.max(1, N);
        failures += assertCond("memory bounded (≤1KB/candidate, got " + bytesPerCand + " B)",
                bytesPerCand <= 1024);

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL STREAMING CHECKS PASSED");
        else { System.out.println("❌ " + failures + " STREAMING CHECK(S) FAILED"); System.exit(1); }
    }

    /** Lazy iterator — never materialises the full corpus. */
    private static final class SyntheticIterator implements Iterator<String> {
        private final int N;
        private final Random rng;
        private int i = 0;
        SyntheticIterator(int N, long seed) { this.N = N; this.rng = new Random(seed); }
        @Override public boolean hasNext() { return i < N; }
        @Override public String next() {
            if (i >= N) throw new java.util.NoSuchElementException();
            i++;
            double cost = 0.05 + rng.nextDouble() * 1.95;
            double lat  = 1.0  + rng.nextDouble() * 99.0;
            double thr  = 100.0 + rng.nextDouble() * 9900.0;
            double acc  = 0.5  + rng.nextDouble() * 0.5;
            // High precision so the rounded text round-trips losslessly back to
            // the same double values. Lower precision (%.4f) caused argmin/argmax
            // ties between rounded values, breaking the offline-vs-online check.
            return String.format(Locale.ROOT,
                    "id=cand_%07d cost=%.15g latency=%.15gms throughput=%.15g accuracy=%.15g",
                    i, cost, lat, thr, acc);
        }
    }

    private record Stat(double min, double max, double mean, int argmin, int argmax) {}
    private static Stat stat(double[] a) {
        double mn = Double.POSITIVE_INFINITY, mx = Double.NEGATIVE_INFINITY, sum = 0;
        int amn = -1, amx = -1;
        for (int i = 0; i < a.length; i++) {
            sum += a[i];
            if (a[i] < mn) { mn = a[i]; amn = i; }
            if (a[i] > mx) { mx = a[i]; amx = i; }
        }
        return new Stat(mn, mx, sum / a.length, amn, amx);
    }

    private static boolean near(double a, double b, double tol) {
        return Math.abs(a - b) <= tol * Math.max(1, Math.abs(b));
    }

    /** Offline domination check using the same maximize set as the online Pareto.
     *  cost/latency are minimised; throughput/accuracy maximised. */
    private static boolean offlineDominates(LineResult a, LineResult b) {
        double ac = parse(a, "cost"),    bc = parse(b, "cost");
        double al = parse(a, "latency"), bl = parse(b, "latency");
        double at = parse(a, "throughput"), bt = parse(b, "throughput");
        double aa = parse(a, "accuracy"),   ba = parse(b, "accuracy");
        boolean strict = false;
        // minimise: cost
        if (ac > bc) return false; if (ac < bc) strict = true;
        // minimise: latency
        if (al > bl) return false; if (al < bl) strict = true;
        // maximise: throughput
        if (at < bt) return false; if (at > bt) strict = true;
        // maximise: accuracy
        if (aa < ba) return false; if (aa > ba) strict = true;
        return strict;
    }

    private static double parse(LineResult r, String key) {
        return AnalyzerCore.tryParseNumeric(r.features.kvPairs.get(key)).orElse(Double.NaN);
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static final class Capture implements AnalysisListener {
        @Override public void onLog(String message) { /* silenced for 100K */ }
        @Override public void onResult(LineResult r) { /* dropped — proves streaming */ }
        @Override public void onProgress(int processed, int totalHint, String message) {
            if (processed % 25_000 == 0) System.out.println("  " + message);
        }
        @Override public void onError(String message, Throwable error) {
            System.out.println("  err: " + message);
        }
    }
}
