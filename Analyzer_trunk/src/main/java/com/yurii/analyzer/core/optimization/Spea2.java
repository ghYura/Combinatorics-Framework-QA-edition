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
import java.util.Arrays;
import java.util.List;

/**
 * SPEA2 (Zitzler, Laumanns &amp; Thiele, 2001) — Strength Pareto Evolutionary
 * Algorithm 2 primitives, sitting on the same {@code FrontAlgorithm} shelf as
 * {@link NsgaII} and {@link NsgaIII}.
 *
 * <p>Three pieces of SPEA2 are surfaced per candidate:</p>
 * <ol>
 *   <li><strong>Strength</strong> {@code S(i)} = how many other candidates
 *       {@code i} dominates.</li>
 *   <li><strong>Raw fitness</strong> {@code R(i)} = Σ {@code S(j)} over every
 *       {@code j} that dominates {@code i}.  {@code R(i) == 0} iff {@code i}
 *       is non-dominated (rank-1 set in NSGA terms).</li>
 *   <li><strong>k-NN density</strong> {@code D(i) = 1 / (σ_k + 2)} where
 *       {@code σ_k} is the distance to the {@code k}-th nearest neighbour
 *       in deviation-space; {@code k = √N} per the SPEA2 standard.</li>
 * </ol>
 *
 * <p>Final fitness {@code F(i) = R(i) + D(i)} — used by SPEA2's environmental
 * truncation when the non-dominated set is too large for the archive cap.
 * The Analyzer uses these values for reporting only (we score all candidates
 * we see; we don't run a population-cap truncation step).  The exposed
 * {@code kNearestDistance} doubles as the per-front "diversity metric"
 * suitable for the polymorphic {@code LineMention.crowdingDistance} slot
 * (bigger = more isolated = more diverse).</p>
 *
 * <p>Front membership ({@code rank == 1}) is mathematically identical to
 * PARETO / NSGA-II / NSGA-III on the same input — all four use the same
 * dominance predicate.  What differs is the per-front diversification
 * score.  This is verified end-to-end in {@code Spea2Verify}.</p>
 *
 * <p>Complexity: {@code O(N²)} for strength + raw fitness, {@code O(N² log N)}
 * for k-NN via per-row sort.  Same order as NSGA-II/III for typical N.</p>
 *
 * <p>Stateless and thread-safe.</p>
 */
public final class Spea2 {
    private Spea2() {}

    /** One candidate with SPEA2's full fitness breakdown.
     *  {@code rank} is the NSGA-II-equivalent front index (1 = non-dominated).
     *  {@code rawFitness == 0} ⇔ {@code rank == 1}. */
    public record Ranked<T>(
            T item,
            int rank,
            int strength,
            double rawFitness,
            double kNearestDistance,
            double density,
            double finalFitness) {}

    /** Compute SPEA2 fitness components for every input candidate.  Output
     *  parallels {@code items} / {@code vectors}: the k-th {@link Ranked}
     *  corresponds to the k-th input candidate. */
    public static <T> List<Ranked<T>> rank(List<T> items, double[][] vectors, GoalSpec[] goals) {
        int n = items == null ? 0 : items.size();
        if (n == 0) return List.of();
        if (vectors == null || vectors.length != n)
            throw new IllegalArgumentException("vectors must align with items");

        // 1. Strength S(i) and per-candidate dominator list.
        int[] strength = new int[n];
        List<List<Integer>> dominators = new ArrayList<>(n);
        for (int i = 0; i < n; i++) dominators.add(new ArrayList<>());
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                if (i == j) continue;
                if (Dominance.dominates(vectors[i], vectors[j], goals)) {
                    strength[i]++;
                }
                if (Dominance.dominates(vectors[j], vectors[i], goals)) {
                    dominators.get(i).add(j);
                }
            }
        }

        // 2. Raw fitness R(i) = Σ S(j) for every j dominating i.
        double[] raw = new double[n];
        for (int i = 0; i < n; i++) {
            double sum = 0;
            for (int j : dominators.get(i)) sum += strength[j];
            raw[i] = sum;
        }

        // 3. k-NN density.  k = √N per SPEA2 standard; k ≥ 1 for any
        //    non-empty population.
        int k = Math.max(1, (int) Math.sqrt(n));
        double[] kNN = new double[n];
        if (n == 1) {
            kNN[0] = 0;   // singleton: no neighbours; degenerate but valid
        } else {
            for (int i = 0; i < n; i++) {
                double[] dists = new double[n - 1];
                int idx = 0;
                for (int j = 0; j < n; j++) {
                    if (i == j) continue;
                    dists[idx++] = euclideanDeviation(vectors[i], vectors[j], goals);
                }
                Arrays.sort(dists);
                // k-th nearest (0-based index k-1); fall back to last when N is tiny
                int kIdx = Math.min(k - 1, dists.length - 1);
                if (kIdx < 0) kIdx = 0;
                kNN[i] = dists[kIdx];
            }
        }

        // 4. Density D(i) and final fitness F(i) = R(i) + D(i).
        double[] density = new double[n];
        double[] finalFitness = new double[n];
        for (int i = 0; i < n; i++) {
            density[i] = 1.0 / (kNN[i] + 2.0);
            finalFitness[i] = raw[i] + density[i];
        }

        // 5. NSGA-II-equivalent rank for reporting (rank 1 ⇔ raw == 0).
        List<List<Integer>> fronts = NsgaII.fastNonDominatedSort(vectors, goals);
        int[] rankOf = new int[n];
        Arrays.fill(rankOf, fronts.size() + 1);
        for (int r = 0; r < fronts.size(); r++) {
            for (int idx : fronts.get(r)) rankOf[idx] = r + 1;
        }

        List<Ranked<T>> out = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            out.add(new Ranked<>(items.get(i), rankOf[i],
                    strength[i], raw[i], kNN[i], density[i], finalFitness[i]));
        }
        return out;
    }

    /** Euclidean distance in deviation-space (goals' {@code deviation(v)}
     *  applied per axis).  NaN-safe (skip axis), {@code null}-goal-safe
     *  (skip axis). */
    static double euclideanDeviation(double[] a, double[] b, GoalSpec[] goals) {
        if (a == null || b == null || goals == null) return 0;
        double sum = 0;
        int len = Math.min(Math.min(a.length, b.length), goals.length);
        for (int i = 0; i < len; i++) {
            if (goals[i] == null) continue;
            double va = a[i], vb = b[i];
            if (Double.isNaN(va) || Double.isNaN(vb)) continue;
            double diff = goals[i].deviation(va) - goals[i].deviation(vb);
            sum += diff * diff;
        }
        return Math.sqrt(sum);
    }

    /** Front (rank 1 / non-dominated set), in input order.  Mirrors
     *  {@link Dominance#paretoFront}'s shape. */
    public static <T> List<T> firstFront(List<T> items, double[][] vectors, GoalSpec[] goals) {
        List<T> out = new ArrayList<>();
        for (Ranked<T> r : rank(items, vectors, goals))
            if (r.rank() == 1) out.add(r.item());
        return out;
    }

    /** Front with full SPEA2 fitness breakdown per member.  Used by
     *  {@code BestLinesReporter} to surface {@code kNearestDistance} on each
     *  {@code LineMention} (kNN-distance as the diversity metric: bigger =
     *  more isolated = better preserved in environmental truncation). */
    public static <T> List<Ranked<T>> firstFrontWithFitness(List<T> items,
                                                              double[][] vectors,
                                                              GoalSpec[] goals) {
        List<Ranked<T>> out = new ArrayList<>();
        for (Ranked<T> r : rank(items, vectors, goals))
            if (r.rank() == 1) out.add(r);
        return out;
    }
}
