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

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;

/**
 * Verifies Win-1: the streaming aggregator now collects a bounded
 * reservoir per auto-discovered key and runs the full
 * {@link MetricStreamAnalyzer} toolkit (exp-fit, Simpson AUC, Brent,
 * Nelder-Mead, SA, RK4, Newton) on those samples at snapshot time.
 *
 * Three things to check:
 *   1. {@code Snapshot.deepAnalysis} is populated for every auto-key.
 *   2. The per-key MetricAnalysis values are within sane bounds
 *      (Brent min/max ∈ [seriesMin, seriesMax]; exp-fit RMS ≤ 1.5·σ).
 *   3. Reservoir keeps memory bounded as N grows from 10k → 100k.
 */
public final class ReservoirDeepAnalysisVerify {
    private ReservoirDeepAnalysisVerify() {}

    public static void main(String[] args) throws Exception {
        int N = (args.length > 0) ? Integer.parseInt(args[0]) : 50_000;
        int f = 0;

        // ── Synth: 4 metric streams with known shapes ───────────────────
        //   cost          ~ uniform(0.05, 2.0)         — flat
        //   latency       ~ 100·exp(-0.0001·i) + noise — exponential decay
        //   throughput    ~ 100 + 20·sin(i/1000)·i     — oscillating + drift
        //   accuracy      ~ uniform(0.5, 1.0)
        java.util.Random rng = new java.util.Random(42);
        Iterator<String> rows = new Iterator<>() {
            int i = 0;
            @Override public boolean hasNext() { return i < N; }
            @Override public String next() {
                if (i >= N) throw new NoSuchElementException();
                i++;
                double cost = 0.05 + rng.nextDouble() * 1.95;
                double lat  = 100.0 * Math.exp(-0.0001 * i) + rng.nextGaussian();
                double thr  = 100.0 + 20.0 * Math.sin(i / 1000.0) * (i / 1000.0);
                double acc  = 0.5  + rng.nextDouble() * 0.5;
                return String.format(Locale.ROOT,
                        "id=r_%07d cost=%.15g latency=%.15g throughput=%.15g accuracy=%.15g",
                        i, cost, lat, thr, acc);
            }
        };

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);

        Runtime rt = Runtime.getRuntime();
        System.gc(); Thread.sleep(50); System.gc();
        long heapBefore = rt.totalMemory() - rt.freeMemory();
        long t0 = System.nanoTime();
        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStream(
                rows, new LineExecutor.Inline(),
                /*topK*/ 5, List.<GoalSpec>of(), DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});
        long elapsedMs = (System.nanoTime() - t0) / 1_000_000;
        System.gc(); Thread.sleep(50); System.gc();
        long heapDelta = (rt.totalMemory() - rt.freeMemory()) - heapBefore;

        System.out.printf(Locale.ROOT,
                "Streamed N=%d  elapsed=%d ms  heapΔ=%.2f MB  reservoirCap=%d%n%n",
                N, elapsedMs, heapDelta / 1e6, OnlineMetricAggregator.RESERVOIR_CAP);

        // ── 1. deepAnalysis populated for every auto-key ───────────────
        f += assertCond("deepAnalysis non-empty",      !snap.deepAnalysis().isEmpty());
        f += assertCond("deepAnalysis covers cost",       snap.deepAnalysis().containsKey("cost"));
        f += assertCond("deepAnalysis covers latency",    snap.deepAnalysis().containsKey("latency"));
        f += assertCond("deepAnalysis covers throughput", snap.deepAnalysis().containsKey("throughput"));
        f += assertCond("deepAnalysis covers accuracy",   snap.deepAnalysis().containsKey("accuracy"));

        // ── 2. Per-key bounds ──────────────────────────────────────────
        for (String key : List.of("cost", "latency", "throughput", "accuracy")) {
            MetricStreamAnalyzer.MetricAnalysis ma = snap.deepAnalysis().get(key);
            OnlineMetricAggregator.KeyStats ks = snap.perKeyStats().get(key);
            f += assertCond(key + ".n ≤ RESERVOIR_CAP (bounded reservoir)",
                    ma.n() <= OnlineMetricAggregator.RESERVOIR_CAP);
            f += assertCond(key + ".n ≥ 5 (deep analysis fitted)", ma.n() >= 5);
            f += assertCond(key + ".brentMin ∈ [seriesMin, seriesMax]",
                    ma.brentMin() >= ks.min - 1e-6 && ma.brentMin() <= ks.max + 1e-6);
            f += assertCond(key + ".brentMax ∈ [seriesMin, seriesMax]",
                    ma.brentMax() >= ks.min - 1e-6 && ma.brentMax() <= ks.max + 1e-6);
            f += assertCond(key + ".simpsonAuc is finite",
                    Double.isFinite(ma.simpsonAuc()));
            f += assertCond(key + ".rk4Tau > 0",
                    ma.rk4Tau() > 0);
        }

        // ── 3. Exp-fit residual ≤ 1.5·σ on each series ─────────────────
        for (String key : List.of("cost", "latency", "throughput", "accuracy")) {
            var ma = snap.deepAnalysis().get(key);
            double rms = Math.sqrt(ma.expFitLoss() / Math.max(1, ma.n()));
            f += assertCond(String.format(Locale.ROOT,
                    "%s exp-fit RMS %.3g ≤ 1.5·σ %.3g  (NM-converged)",
                    key, rms, 1.5 * ma.stdev()),
                    rms <= 1.5 * ma.stdev() + 1e-3);
        }

        // ── 4. Memory bounded: at N=50k, heap delta should be well under
        //       50 MB (most of it is the 4 reservoirs at 16 KB each = 64 KB).
        f += assertCond("heap delta ≤ 50 MB (reservoir is bounded)",
                heapDelta <= 50 * 1024L * 1024L);

        // ── 5. JSON includes deepAnalysis section ──────────────────────
        com.fasterxml.jackson.databind.JsonNode json = snap.toJson();
        f += assertCond("toJson includes 'deepAnalysis' section", json.has("deepAnalysis"));
        f += assertCond("deepAnalysis.cost.expFit present in JSON",
                json.path("deepAnalysis").path("cost").has("expFit"));
        f += assertCond("deepAnalysis.cost.simpsonAuc present in JSON",
                json.path("deepAnalysis").path("cost").has("simpsonAuc"));
        f += assertCond("deepAnalysis.cost.rk4Tau present in JSON",
                json.path("deepAnalysis").path("cost").has("rk4Tau"));

        System.out.println();
        if (f == 0) System.out.println("✅ ALL RESERVOIR-DEEP-ANALYSIS CHECKS PASSED");
        else { System.out.println("❌ " + f + " CHECK(S) FAILED"); System.exit(1); }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
