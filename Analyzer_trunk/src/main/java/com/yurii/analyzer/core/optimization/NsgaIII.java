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
 * NSGA-III (Deb &amp; Jain, 2014) primitives — same {@code fast non-dominated
 * sort} backbone as {@link NsgaII}, but the diversification metric is
 * <strong>reference-point-based niching</strong> instead of crowding distance.
 *
 * <p>Why this matters for the bundle.  Crowding distance loses discriminative
 * power once the objective count exceeds 3-4 (most front members get +∞
 * because they're boundary on at least one axis).  NSGA-III replaces
 * crowding with a structured set of reference directions and associates
 * every individual with its nearest direction.  The result scales cleanly to
 * many-objective scoring — which is exactly where the bundle ends up when
 * an Analyzer corpus has auto-discovered 5-10 numeric metrics
 * ({@code cost / latency / throughput / coverage_line / coverage_branch /
 * accuracy / loss / token_cost / …}).</p>
 *
 * <p>Architectural placement: side-by-side with {@link NsgaII} on the
 * {@code FrontAlgorithm} shelf, gated by {@code FrontAlgorithm.NSGA_III}.
 * Default front algorithm stays NSGA-II so existing call-sites are
 * byte-for-byte unchanged.  Rank-1 membership is mathematically identical
 * across PARETO / NSGA-II / NSGA-III (all three use the same dominance
 * predicate); only the per-front diversity scoring differs.</p>
 *
 * <p>The five steps of NSGA-III's selection phase:</p>
 * <ol>
 *   <li><strong>Fast non-dominated sort</strong> — shared with {@link NsgaII}.</li>
 *   <li><strong>Normalize objectives</strong> — translate by the ideal point
 *       (per-axis minimum deviation), find {@code M} extreme points via the
 *       Achievement Scalarising Function (ASF), solve a {@code M×M} linear
 *       system for the hyperplane intercepts, divide by intercepts.</li>
 *   <li><strong>Generate reference points</strong> — Das-Dennis structured
 *       set on the unit simplex with {@code p} divisions per axis.  Total
 *       point count is {@code C(M+p-1, p)} which grows fast; pick {@code p}
 *       per {@link #defaultDivisions} for sensible counts.</li>
 *   <li><strong>Associate</strong> — for every individual, find the
 *       reference direction whose line (through origin) is closest in
 *       perpendicular distance.</li>
 *   <li><strong>Niche preservation</strong> — when selecting from a
 *       partially-included front, prefer under-occupied reference points.
 *       (Our public API doesn't perform niche selection — callers usually
 *       want the whole rank-1 set — but the {@code referencePointIndex} +
 *       {@code perpendicularDistance} on every {@link Ranked} let downstream
 *       reporters do their own niche-balance sorting.)</li>
 * </ol>
 *
 * <p>Complexity: {@code O(M·N²)} dominance pass + {@code O(N·R + N·M³)}
 * for normalize + associate, where {@code R} is the reference-point count
 * (a small constant for the typical M ≤ 6).  Same big-O as NSGA-II for the
 * dominant term.</p>
 *
 * <p>Stateless and thread-safe.</p>
 */
public final class NsgaIII {
    private NsgaIII() {}

    /** One candidate with its rank + reference-point association.
     *  Parallel to {@link NsgaII.Ranked}, but the diversity metric is
     *  {@link #perpendicularDistance} to the nearest reference direction
     *  rather than crowding distance.  Smaller perp-distance = more
     *  axis-aligned with that reference direction. */
    public record Ranked<T>(T item, int rank, int referencePointIndex,
                              double perpendicularDistance) {}

    /** Lightweight (refIdx, perpDist) pair returned by
     *  {@link #associate(double[][], double[][])}. */
    public record Association(int referencePointIndex, double perpendicularDistance) {}

    /**
     * Heuristic for the {@code p} parameter of Das-Dennis given the objective
     * count {@code M}.  Picks values that keep the reference-point count
     * tractable (a few dozen to a few hundred, never thousands).
     */
    public static int defaultDivisions(int objectives) {
        if (objectives <= 2) return 12;   //  13 ref pts
        if (objectives == 3) return 7;    //  36 ref pts
        if (objectives == 4) return 5;    //  56 ref pts
        if (objectives == 5) return 4;    //  70 ref pts
        if (objectives == 6) return 3;    //  56 ref pts
        return 3;                          // sparse for M >= 7
    }

    /**
     * Generate Das-Dennis structured reference points on the unit
     * {@code M}-simplex with {@code divisions} per axis.  Every point has
     * non-negative coordinates summing to 1; point count is the binomial
     * coefficient {@code C(M+divisions-1, divisions)}.
     */
    public static double[][] referencePoints(int objectives, int divisions) {
        if (objectives < 1) throw new IllegalArgumentException("objectives must be >= 1");
        if (divisions < 1)  throw new IllegalArgumentException("divisions must be >= 1");
        List<double[]> out = new ArrayList<>();
        generate(new int[objectives], 0, divisions, divisions, out);
        return out.toArray(new double[0][]);
    }

    private static void generate(int[] state, int axis, int remaining,
                                  int divisions, List<double[]> out) {
        if (axis == state.length - 1) {
            state[axis] = remaining;
            double[] pt = new double[state.length];
            double denom = (double) divisions;
            for (int i = 0; i < state.length; i++) pt[i] = state[i] / denom;
            out.add(pt);
            return;
        }
        for (int v = 0; v <= remaining; v++) {
            state[axis] = v;
            generate(state, axis + 1, remaining - v, divisions, out);
        }
    }

    /**
     * Normalize the objective-space vectors via NSGA-III's standard pipeline:
     * translate by ideal point, find {@code M} extreme points via ASF, solve
     * the hyperplane intercept linear system, divide by intercepts.  Falls
     * back to max-on-axis when the extreme-point matrix is singular (a
     * common degenerate case on tiny corpora).
     *
     * @return per-candidate {@code M}-vector of normalized deviations
     */
    public static double[][] normalize(double[][] vectors, GoalSpec[] goals) {
        if (vectors == null || vectors.length == 0)
            return new double[0][];
        if (goals == null || goals.length == 0)
            throw new IllegalArgumentException("goals must be non-empty");
        int n = vectors.length;
        int m = goals.length;

        // 1. Deviation per axis — NaN-safe; null goal contributes 0.
        double[][] dev = new double[n][m];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                if (goals[j] == null) { dev[i][j] = 0; continue; }
                double v = (j < vectors[i].length) ? vectors[i][j] : Double.NaN;
                dev[i][j] = Double.isNaN(v) ? 0 : goals[j].deviation(v);
            }
        }

        // 2. Ideal point: per-axis minimum.
        double[] ideal = new double[m];
        for (int j = 0; j < m; j++) {
            double mn = Double.POSITIVE_INFINITY;
            for (int i = 0; i < n; i++) if (dev[i][j] < mn) mn = dev[i][j];
            ideal[j] = Double.isFinite(mn) ? mn : 0;
        }

        // 3. Translate (subtract ideal so the population's best on every
        //    axis sits at 0).
        double[][] tr = new double[n][m];
        for (int i = 0; i < n; i++)
            for (int j = 0; j < m; j++) tr[i][j] = dev[i][j] - ideal[j];

        // 4. Extreme points via ASF — for axis k, the extreme is the
        //    individual with min-over-axes max(f_j / w_j) where w has 1 on k
        //    and a small epsilon elsewhere.
        int[] extreme = new int[m];
        for (int axis = 0; axis < m; axis++) {
            double bestAsf = Double.POSITIVE_INFINITY;
            int bestIdx = -1;
            for (int i = 0; i < n; i++) {
                double asf = asf(tr[i], axis);
                if (asf < bestAsf) { bestAsf = asf; bestIdx = i; }
            }
            extreme[axis] = (bestIdx < 0) ? 0 : bestIdx;
        }

        // 5. Hyperplane intercepts (1 / x where Ax = b, b = 1-vector,
        //    A row k = extreme[k]'s translated objective vector).
        double[] intercepts = computeIntercepts(tr, extreme, m);

        // 6. Normalize each candidate by the intercept of its axis.
        double[][] norm = new double[n][m];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < m; j++) {
                double denom = Math.abs(intercepts[j]) < 1e-12 ? 1e-12 : intercepts[j];
                norm[i][j] = tr[i][j] / denom;
            }
        }
        return norm;
    }

    /** Achievement Scalarising Function with weight = unit vector on
     *  {@code axis} (eps elsewhere). */
    private static double asf(double[] translated, int axis) {
        double eps = 1e-6;
        double maxRatio = Double.NEGATIVE_INFINITY;
        for (int j = 0; j < translated.length; j++) {
            double w = (j == axis) ? 1.0 : eps;
            double ratio = translated[j] / w;
            if (ratio > maxRatio) maxRatio = ratio;
        }
        return maxRatio;
    }

    /** Compute the M intercepts of the hyperplane through the M extreme
     *  points.  Falls back to per-axis max when the system is singular
     *  (degenerate fronts on tiny corpora). */
    private static double[] computeIntercepts(double[][] tr, int[] extreme, int m) {
        double[][] A = new double[m][m];
        for (int k = 0; k < m; k++) {
            int idx = extreme[k];
            for (int j = 0; j < m; j++) A[k][j] = tr[idx][j];
        }
        double[] b = new double[m];
        Arrays.fill(b, 1.0);
        double[] x = gaussianSolve(A, b);

        double[] intercepts = new double[m];
        if (x == null) {
            // Singular — fall back to per-axis max as the intercept estimate.
            for (int j = 0; j < m; j++) {
                double mx = 0;
                for (int i = 0; i < tr.length; i++)
                    if (tr[i][j] > mx) mx = tr[i][j];
                intercepts[j] = (mx > 1e-12) ? mx : 1.0;
            }
        } else {
            for (int j = 0; j < m; j++) {
                if (Math.abs(x[j]) < 1e-12) intercepts[j] = 1.0;
                else intercepts[j] = 1.0 / x[j];
                if (intercepts[j] < 1e-12) intercepts[j] = 1.0;
            }
        }
        return intercepts;
    }

    /** Gaussian elimination with partial pivoting; returns {@code null} on
     *  singular matrices.  Allocates a working augmented copy so the caller's
     *  matrix is left untouched. */
    private static double[] gaussianSolve(double[][] A, double[] b) {
        int n = b.length;
        double[][] aug = new double[n][n + 1];
        for (int i = 0; i < n; i++) {
            System.arraycopy(A[i], 0, aug[i], 0, n);
            aug[i][n] = b[i];
        }
        for (int col = 0; col < n; col++) {
            int pivot = col;
            double maxVal = Math.abs(aug[col][col]);
            for (int r = col + 1; r < n; r++) {
                double v = Math.abs(aug[r][col]);
                if (v > maxVal) { pivot = r; maxVal = v; }
            }
            if (maxVal < 1e-12) return null;
            if (pivot != col) {
                double[] tmp = aug[col]; aug[col] = aug[pivot]; aug[pivot] = tmp;
            }
            for (int r = col + 1; r < n; r++) {
                double factor = aug[r][col] / aug[col][col];
                for (int c = col; c <= n; c++) aug[r][c] -= factor * aug[col][c];
            }
        }
        double[] x = new double[n];
        for (int r = n - 1; r >= 0; r--) {
            double sum = aug[r][n];
            for (int c = r + 1; c < n; c++) sum -= aug[r][c] * x[c];
            x[r] = sum / aug[r][r];
        }
        return x;
    }

    /**
     * Associate each normalized individual with its nearest reference
     * direction.  Distance is perpendicular to the line through origin
     * along the reference vector.
     */
    public static Association[] associate(double[][] normalized, double[][] refPoints) {
        int n = normalized.length;
        int r = refPoints.length;
        Association[] out = new Association[n];
        for (int i = 0; i < n; i++) {
            int bestR = 0;
            double bestDist = Double.POSITIVE_INFINITY;
            for (int k = 0; k < r; k++) {
                double d = perpendicularDistance(normalized[i], refPoints[k]);
                if (d < bestDist) { bestDist = d; bestR = k; }
            }
            out[i] = new Association(bestR, bestDist);
        }
        return out;
    }

    /** Perpendicular distance from {@code point} to the line through the
     *  origin along {@code ref}.  Standard projection: t = (p·r)/(r·r),
     *  closest point on line is t·r, distance = ||p − t·r||. */
    static double perpendicularDistance(double[] point, double[] ref) {
        double dot = 0, refNormSq = 0;
        int len = Math.min(point.length, ref.length);
        for (int i = 0; i < len; i++) {
            dot += point[i] * ref[i];
            refNormSq += ref[i] * ref[i];
        }
        if (refNormSq < 1e-12) {
            // Reference vector is zero (origin) — distance is ||point||.
            double d2 = 0;
            for (int i = 0; i < len; i++) d2 += point[i] * point[i];
            return Math.sqrt(d2);
        }
        double t = dot / refNormSq;
        double dist2 = 0;
        for (int i = 0; i < len; i++) {
            double diff = point[i] - t * ref[i];
            dist2 += diff * diff;
        }
        return Math.sqrt(dist2);
    }

    /**
     * Full NSGA-III pass: every candidate gets its rank, nearest reference-
     * point index, and perpendicular distance.  Uses {@link #defaultDivisions}
     * to pick the Das-Dennis parameter from the objective count.
     *
     * <p>Output is parallel to {@code items} / {@code vectors}: the k-th
     * {@link Ranked} corresponds to the k-th input candidate.  Rank-1
     * filter ({@code r.rank() == 1}) yields the Pareto front.</p>
     */
    public static <T> List<Ranked<T>> nonDominatedSortWithReference(List<T> items,
                                                                       double[][] vectors,
                                                                       GoalSpec[] goals) {
        if (goals == null) throw new IllegalArgumentException("goals must be non-null");
        return nonDominatedSortWithReference(items, vectors, goals, defaultDivisions(goals.length));
    }

    /** Explicit-divisions overload for callers that want a non-default
     *  reference-point granularity. */
    public static <T> List<Ranked<T>> nonDominatedSortWithReference(List<T> items,
                                                                       double[][] vectors,
                                                                       GoalSpec[] goals,
                                                                       int divisions) {
        int n = items == null ? 0 : items.size();
        if (n == 0) return List.of();
        if (vectors == null || vectors.length != n)
            throw new IllegalArgumentException("vectors must align with items");

        // 1. Fast non-dominated sort — same predicate / same fronts as NSGA-II.
        List<List<Integer>> fronts = NsgaII.fastNonDominatedSort(vectors, goals);
        int[] rankOf = new int[n];
        Arrays.fill(rankOf, fronts.size() + 1);
        for (int r = 0; r < fronts.size(); r++) {
            for (int idx : fronts.get(r)) rankOf[idx] = r + 1;
        }

        // 2. Normalize the objective space.
        double[][] norm = normalize(vectors, goals);

        // 3. Reference points.
        double[][] refs = referencePoints(goals.length, divisions);

        // 4. Associate every candidate with its nearest reference direction.
        Association[] assoc = associate(norm, refs);

        // 5. Pack the output.
        List<Ranked<T>> out = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            out.add(new Ranked<>(items.get(i),
                    rankOf[i],
                    assoc[i].referencePointIndex(),
                    assoc[i].perpendicularDistance()));
        }
        return out;
    }

    /** Pareto front (rank 1) only, as a {@code List<T>}; mirrors
     *  {@link Dominance#paretoFront} / {@link NsgaII#firstFront}. */
    public static <T> List<T> firstFront(List<T> items, double[][] vectors, GoalSpec[] goals) {
        List<T> out = new ArrayList<>();
        for (Ranked<T> r : nonDominatedSortWithReference(items, vectors, goals))
            if (r.rank() == 1) out.add(r.item());
        return out;
    }

    /** As {@link #firstFront} but exposes reference-point association +
     *  perpendicular distance per member.  Used by {@code BestLinesReporter}
     *  to surface the diversity metric on each {@code LineMention}. */
    public static <T> List<Ranked<T>> firstFrontWithReference(List<T> items,
                                                                 double[][] vectors,
                                                                 GoalSpec[] goals) {
        List<Ranked<T>> out = new ArrayList<>();
        for (Ranked<T> r : nonDominatedSortWithReference(items, vectors, goals))
            if (r.rank() == 1) out.add(r);
        return out;
    }
}
