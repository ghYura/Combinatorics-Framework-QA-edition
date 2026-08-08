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

import java.util.ArrayList;
import java.util.List;
import java.util.function.ToDoubleFunction;

/**
 * Single source of truth for Pareto dominance comparisons across the
 * entire project.  Previously the same algorithm was duplicated in three
 * places:
 *
 *   • {@link Optimizers#paretoFront} — batch path (MIN/MAX via boolean flags)
 *   • {@link OnlineMetricAggregator.OnlinePareto#dominates} — streaming path
 *     (MIN/MAX/TARGET via {@link GoalSpec} per axis, with NaN handling)
 *   • Test-side dominance helpers in several verifiers
 *
 * The streaming version was the most general — it handles {@code TARGET}
 * mode (closer-to-target wins) and {@code NaN} (axis skipped as
 * incomparable).  This class promotes that semantics to a single
 * canonical implementation and refactors the older sites to delegate
 * here.
 *
 * The dominance rule, in one sentence: <em>{@code a} dominates {@code b}
 * iff {@code a} is no-worse than {@code b} on every comparable axis AND
 * strictly better on at least one</em>, where "better" is encoded by
 * {@link GoalSpec#deviation(double)} (lower = better, uniformly across
 * MIN/MAX/TARGET).
 *
 * Stateless, thread-safe, allocation-free per call (no boxing, no array
 * growth).
 */
public final class Dominance {
    private Dominance() {}

    /**
     * @param a      metric vector of candidate A (length n)
     * @param b      metric vector of candidate B (length n)
     * @param goals  per-axis goals (length n).  {@code null} entry =
     *               axis excluded from comparison (e.g. policy-skipped
     *               auto-discovered key).  Length mismatch with the
     *               vectors is allowed: comparisons run up to
     *               {@code min(a.length, b.length, goals.length)}.
     * @return       {@code true} iff a dominates b under the rule above
     */
    public static boolean dominates(double[] a, double[] b, GoalSpec[] goals) {
        if (a == null || b == null || goals == null) return false;
        boolean strict = false;
        int len = Math.min(Math.min(a.length, b.length), goals.length);
        for (int i = 0; i < len; i++) {
            GoalSpec g = goals[i];
            if (g == null) continue;                         // axis skipped
            double va = a[i], vb = b[i];
            if (Double.isNaN(va) || Double.isNaN(vb)) continue;
            double da = g.deviation(va);
            double db = g.deviation(vb);
            double diff = da - db;
            if (diff > 0) return false;
            if (diff < 0) strict = true;
        }
        return strict;
    }

    /** Same predicate, but with {@code GoalSpec} supplied as a {@link List}.
     *  Convenience wrapper for callers that already keep goals in lists. */
    public static boolean dominates(double[] a, double[] b, List<GoalSpec> goals) {
        if (goals == null) return false;
        return dominates(a, b, goals.toArray(new GoalSpec[0]));
    }

    /**
     * Batch O(N²) Pareto-front extraction using the unified dominance
     * predicate.  This is the algorithm that {@link Optimizers#paretoFront}
     * delegates to internally.  Exposed publicly so callers with
     * pre-computed metric vectors can skip the {@code ToDoubleFunction}
     * machinery.
     *
     * @param items  candidates (returned slice is a sublist of these)
     * @param vectors  metric vectors, one per item (must align with items)
     * @param goals  per-axis goals
     * @return  the sublist of items that are non-dominated
     */
    public static <T> List<T> paretoFront(List<T> items, double[][] vectors, GoalSpec[] goals) {
        int n = items.size();
        if (n == 0) return List.of();
        boolean[] dominated = new boolean[n];
        for (int i = 0; i < n; i++) {
            if (dominated[i]) continue;
            for (int j = 0; j < n; j++) {
                if (i == j || dominated[j]) continue;
                if (dominates(vectors[j], vectors[i], goals)) {
                    dominated[i] = true;
                    break;
                }
            }
        }
        List<T> front = new ArrayList<>();
        for (int i = 0; i < n; i++) if (!dominated[i]) front.add(items.get(i));
        return front;
    }

    /**
     * NSGA-II flavoured front extraction — semantically identical rank-1 set
     * to {@link #paretoFront}, but the algorithm under the hood is the
     * "fast non-dominated sort" of {@link NsgaII} which simultaneously
     * computes layered fronts and per-candidate crowding distances.  Use this
     * overload when the caller wants the diversification metric or the
     * dominated-tail layering; both are available via the more general
     * {@link NsgaII#nonDominatedSortWithCrowding} API.
     */
    public static <T> List<T> paretoFrontNsgaII(List<T> items, double[][] vectors, GoalSpec[] goals) {
        return NsgaII.firstFront(items, vectors, goals);
    }

    /**
     * Tier-5.1 — NSGA-III flavoured front extraction.  Rank-1 membership is
     * identical to {@link #paretoFront} and {@link #paretoFrontNsgaII} (all
     * three use the same dominance predicate); what differs is the per-front
     * diversity metric.  NSGA-III computes a structured set of reference
     * directions (Das-Dennis) and associates every candidate with its
     * perpendicular distance to the nearest direction — better-behaved than
     * crowding distance for many-objective fronts ({@code M} ≥ 4).  Both
     * the front membership and the reference-point + perpendicular-distance
     * payload are available via {@link NsgaIII#firstFrontWithReference}.
     */
    public static <T> List<T> paretoFrontNsgaIII(List<T> items, double[][] vectors, GoalSpec[] goals) {
        return NsgaIII.firstFront(items, vectors, goals);
    }

    /**
     * Tier-5.1 — SPEA2 (Zitzler et al., 2001) flavoured front extraction.
     * Rank-1 membership is identical to {@link #paretoFront} (same dominance
     * predicate); what differs is the per-candidate strength / raw-fitness /
     * k-NN-density breakdown surfaced via {@link Spea2#firstFrontWithFitness}.
     */
    public static <T> List<T> paretoFrontSpea2(List<T> items, double[][] vectors, GoalSpec[] goals) {
        return Spea2.firstFront(items, vectors, goals);
    }

    /**
     * Tier-5.1 — MOEA/D (Zhang &amp; Li, 2007) flavoured front extraction.
     * Same rank-1 set; what differs is the per-candidate Tchebycheff
     * decomposition surfaced via {@link MoeaD#firstFrontWithDecomposition}.
     */
    public static <T> List<T> paretoFrontMoeaD(List<T> items, double[][] vectors, GoalSpec[] goals) {
        return MoeaD.firstFront(items, vectors, goals);
    }

    /**
     * Materialise the metric vectors of a list of items using a parallel
     * list of {@code ToDoubleFunction} extractors.  Convenience for the
     * batch path, which historically passed extractor lambdas.
     */
    public static <T> double[][] extractVectors(List<T> items,
                                                 List<ToDoubleFunction<T>> extractors) {
        double[][] vectors = new double[items.size()][];
        int k = extractors.size();
        for (int i = 0; i < items.size(); i++) {
            T item = items.get(i);
            double[] v = new double[k];
            for (int j = 0; j < k; j++) v[j] = extractors.get(j).applyAsDouble(item);
            vectors[i] = v;
        }
        return vectors;
    }
}
