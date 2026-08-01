package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.function.ToDoubleFunction;

/**
 * Verifies Win-2: the single {@link Dominance} algorithm now serves both
 * the batch path ({@link Optimizers#paretoFront}) and the streaming path
 * ({@link OnlineMetricAggregator.OnlinePareto#dominates}).
 *
 * Concrete claim: feed the SAME corpus into both paths; the resulting
 * Pareto front (as a SET of line numbers) must be IDENTICAL.  Tests with
 * MIN/MAX axes (the only case the legacy batch API supported) — the
 * unification doesn't regress that behaviour.
 *
 * Also tests the new {@link Optimizers#paretoFrontWithGoals} overload
 * with TARGET-mode goals — a capability the batch API previously
 * didn't have and the unification adds for free.
 */
public final class DominanceUnificationVerify {
    private DominanceUnificationVerify() {}

    public static void main(String[] args) throws Exception {
        int f = 0;

        // ─── Corpus: known per-line metric vectors ─────────────────────
        double[][] tuples = {
            // cost  throughput  latency  error_rate
            {0.95,    400,        12.5,    0.50},
            {0.80,    600,        10.0,    0.40},
            {0.65,    900,         8.5,    0.30},
            {0.50,   1300,         6.5,    0.20},
            {0.40,   1700,         5.5,    0.15},
            {0.30,   2200,         5.0,    0.10},
            {0.25,   2600,         5.1,    0.09},
            {0.20,   3000,         4.6,    0.08},
            {0.15,   3400,         4.2,    0.06},
            {0.12,   3800,         3.5,    0.04},
            {0.10,   4200,         3.0,    0.03},
            {0.08,   4500,         2.5,    0.02},
        };
        List<String> corpus = new ArrayList<>();
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=row_%02d cost=%.4f throughput=%.0f latency=%.2f error_rate=%.4f",
                    i + 1, tuples[i][0], tuples[i][1], tuples[i][2], tuples[i][3]));
        }

        // ─── Path A: BATCH via analyzeLines + AnalyzerCore.paretoOptimal ──
        OptimizationAnalyzer batchAnalyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{\"optimizations\":["
                        + "{\"key\":\"cost\",\"mode\":\"minimize\"},"
                        + "{\"key\":\"throughput\",\"mode\":\"maximize\"},"
                        + "{\"key\":\"latency\",\"mode\":\"minimize\"},"
                        + "{\"key\":\"error_rate\",\"mode\":\"minimize\"}"
                        + "]}"),
                1, 5, 30.0, 10.0, false, 0.0, false);
        List<LineResult> batchResults = new ArrayList<>();
        batchAnalyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { batchResults.add(r); }
        });
        List<LineResult> batchFront = AnalyzerCore.paretoOptimal(batchResults, batchAnalyzer.goals());
        Set<Integer> batchLineNos = new HashSet<>();
        for (LineResult r : batchFront) batchLineNos.add(r.lineNo);

        // ─── Path B: STREAMING via analyzeStream + OnlinePareto ──────────
        // Same goals, same corpus.  DiscoveryPolicy.DECLARED_ONLY so auto-keys
        // (the framework adds none here, but be explicit) don't shift the front.
        List<GoalSpec> streamGoals = List.of(
                GoalSpec.min("cost"),
                GoalSpec.max("throughput"),
                GoalSpec.min("latency"),
                GoalSpec.min("error_rate"));
        OptimizationAnalyzer streamAnalyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);
        OnlineMetricAggregator.Snapshot snap = streamAnalyzer.analyzeStream(
                corpus.iterator(),
                new LineExecutor.Inline(),
                /*topK*/ 5, streamGoals, DiscoveryPolicy.DECLARED_ONLY,
                new AnalyzerCore.AnalysisListener() {});
        Set<Integer> streamLineNos = new HashSet<>();
        for (LineResult r : snap.paretoFront()) streamLineNos.add(r.lineNo);

        // ─── Path C: BATCH via the NEW Optimizers.paretoFrontWithGoals ────
        //          (uses GoalSpec directly, supports TARGET — exercise here too)
        List<ToDoubleFunction<LineResult>> extractors = List.of(
                r -> parse(r, "cost"),
                r -> parse(r, "throughput"),
                r -> parse(r, "latency"),
                r -> parse(r, "error_rate"));
        List<LineResult> newApiFront = Optimizers.paretoFrontWithGoals(
                batchResults, extractors, streamGoals);
        Set<Integer> newApiLineNos = new HashSet<>();
        for (LineResult r : newApiFront) newApiLineNos.add(r.lineNo);

        // ─── Assertions ───────────────────────────────────────────────
        System.out.println("Batch front:       " + batchLineNos);
        System.out.println("Streaming front:   " + streamLineNos);
        System.out.println("paretoFrontWGoals: " + newApiLineNos);

        f += assertCond("batch and streaming produce identical front (line-no sets equal)",
                batchLineNos.equals(streamLineNos));
        f += assertCond("paretoFrontWithGoals matches legacy batch front",
                batchLineNos.equals(newApiLineNos));
        f += assertCond("front non-empty",  !batchLineNos.isEmpty());

        // ─── TARGET-mode goal in batch — only possible after unification ──
        // latency target = 5.0 → row #6 (lat=5.0) should win on latency axis.
        List<GoalSpec> withTarget = List.of(
                GoalSpec.min("cost"),
                GoalSpec.max("throughput"),
                GoalSpec.target("latency", 5.0, 1.0),  // ← target — was impossible in legacy batch API
                GoalSpec.min("error_rate"));
        List<LineResult> targetFront = Optimizers.paretoFrontWithGoals(
                batchResults, extractors, withTarget);
        Set<Integer> targetLineNos = new HashSet<>();
        for (LineResult r : targetFront) targetLineNos.add(r.lineNo);
        System.out.println("TARGET-mode front: " + targetLineNos);
        f += assertCond("TARGET-mode batch front non-empty (capability unlocked by unification)",
                !targetLineNos.isEmpty());

        // Sanity: row #6 (latency=5.0 exactly at target) should be on the front
        // — its target-axis deviation is 0, which strictly beats all others on
        // that axis.  Other rows can survive only by winning on cost/throughput.
        f += assertCond("row #6 (latency=5.0 at target) is on TARGET-mode front",
                targetLineNos.contains(6));

        // ─── Dominance.dominates direct API check ──────────────────────
        GoalSpec[] gs = {GoalSpec.min("a"), GoalSpec.max("b")};
        f += assertCond("Dominance: (1,9) dominates (2,5) under (min a, max b)",
                Dominance.dominates(new double[]{1, 9}, new double[]{2, 5}, gs));
        f += assertCond("Dominance: (2,5) does NOT dominate (1,9)",
                !Dominance.dominates(new double[]{2, 5}, new double[]{1, 9}, gs));
        f += assertCond("Dominance: identical points → no domination",
                !Dominance.dominates(new double[]{1, 1}, new double[]{1, 1}, gs));
        // NaN handling
        f += assertCond("Dominance: NaN axis is skipped (still strict on the other)",
                Dominance.dominates(new double[]{1, Double.NaN}, new double[]{2, 999}, gs));
        // null goal axis = skipped
        GoalSpec[] gsWithNull = {GoalSpec.min("a"), null};
        f += assertCond("Dominance: null goal axis is skipped",
                Dominance.dominates(new double[]{1, 999}, new double[]{2, 1}, gsWithNull));
        // TARGET dominance
        GoalSpec[] gtarget = {GoalSpec.target("a", 5.0, 1.0)};
        f += assertCond("Dominance: target=5 → 5 beats 10",
                Dominance.dominates(new double[]{5}, new double[]{10}, gtarget));
        f += assertCond("Dominance: target=5 → 4 dominates 1 (deviation 1 < 4)",
                Dominance.dominates(new double[]{4}, new double[]{1}, gtarget));

        System.out.println();
        if (f == 0) System.out.println("✅ ALL DOMINANCE-UNIFICATION CHECKS PASSED");
        else { System.out.println("❌ " + f + " CHECK(S) FAILED"); System.exit(1); }
    }

    private static double parse(LineResult r, String key) {
        return AnalyzerCore.tryParseNumeric(r.features.kvPairs.get(key)).orElse(Double.NaN);
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
