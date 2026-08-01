package com.yurii.analyzer.core.optimization;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * NSGA-II (Deb et al., 2002) primitives — <em>fast non-dominated sort</em> +
 * <em>crowding distance</em> — implemented as a side-by-side alternative to
 * the legacy {@link Dominance#paretoFront} batch path.  The two stay byte-for-
 * byte compatible on rank-1 membership: NSGA-II's first front is the Pareto
 * front, by definition.  What NSGA-II adds is:
 *
 *   1. A <strong>full rank assignment</strong> over every candidate (rank 1 =
 *      Pareto front, rank 2 = front after the rank-1 set is removed, …) —
 *      callers that previously discarded the dominated tail can now consume it
 *      in dominance-order.
 *
 *   2. A <strong>crowding distance</strong> per candidate (per its own front),
 *      a scale-invariant density estimate that the original paper uses to
 *      diversify selection inside one front.  Larger crowding ⇒ this candidate
 *      sits in a sparser neighbourhood ⇒ keep it.  We surface this number all
 *      the way up to {@code BestLinesReporter.LineMention.crowdingDistance} so
 *      reports can rank front members not just by score but by "how distinct
 *      this objective vector is from its peers".
 *
 * <p>Complexity is the same {@code O(M·N²)} as the legacy Pareto front (M =
 * objectives, N = candidates).  The original paper claims a tighter bound by
 * exploiting cached domination counts during sort; this implementation keeps
 * the simpler quadratic style of {@link Dominance#paretoFront} for parity with
 * the rest of the codebase — the win here is diversity, not speed.</p>
 *
 * <p>Like {@link Dominance}, this class is stateless and thread-safe.
 * {@link GoalSpec#deviation(double)} is the single canonical "lower is better"
 * mapping, so MIN/MAX/TARGET modes and NaN-skipping behave identically across
 * batch / streaming / NSGA-II.</p>
 */
public final class NsgaII {
    private NsgaII() {}

    /** One candidate with its non-dominated-sort rank and crowding distance.
     *  Rank starts at 1 (Pareto front) and grows for successively dominated
     *  layers.  {@code crowdingDistance} is {@link Double#POSITIVE_INFINITY}
     *  for boundary members of any front (per the NSGA-II convention — these
     *  are anchors that selection must always keep). */
    public record Ranked<T>(T item, int rank, double crowdingDistance) {}

    /**
     * Fast non-dominated sort: partition the candidate set into fronts F₁, F₂,
     * … such that F₁ contains exactly the non-dominated candidates of the full
     * set, F₂ contains the non-dominated candidates of (set \ F₁), and so on.
     * Returns the fronts as a list of lists of indices into {@code vectors}.
     *
     * <p>Inside each returned front the index order is whatever the input
     * order was — callers that want a tie-break should apply
     * {@link #crowdingDistance} and sort by it.</p>
     */
    public static List<List<Integer>> fastNonDominatedSort(double[][] vectors, GoalSpec[] goals) {
        int n = vectors == null ? 0 : vectors.length;
        if (n == 0) return List.of();

        // dominationCount[i] = how many candidates strictly dominate i
        // dominatedBy[i]     = indices that i strictly dominates
        int[] dominationCount = new int[n];
        List<List<Integer>> dominatedBy = new ArrayList<>(n);
        for (int i = 0; i < n; i++) dominatedBy.add(new ArrayList<>());

        List<List<Integer>> fronts = new ArrayList<>();
        List<Integer> currentFront = new ArrayList<>();

        for (int p = 0; p < n; p++) {
            for (int q = 0; q < n; q++) {
                if (p == q) continue;
                if (Dominance.dominates(vectors[p], vectors[q], goals)) {
                    dominatedBy.get(p).add(q);
                } else if (Dominance.dominates(vectors[q], vectors[p], goals)) {
                    dominationCount[p]++;
                }
            }
            if (dominationCount[p] == 0) currentFront.add(p);
        }

        // Peel layers until every index has been placed.
        int placed = 0;
        while (!currentFront.isEmpty()) {
            fronts.add(currentFront);
            placed += currentFront.size();
            if (placed >= n) break;

            List<Integer> next = new ArrayList<>();
            for (int p : currentFront) {
                for (int q : dominatedBy.get(p)) {
                    if (--dominationCount[q] == 0) next.add(q);
                }
            }
            currentFront = next;
        }
        return fronts;
    }

    /**
     * Crowding distance for one front.  Each axis is min-max normalised over
     * the front; the boundary members on every axis are assigned
     * {@link Double#POSITIVE_INFINITY} so selection always keeps them; interior
     * members get the sum-over-axes of (right-neighbour − left-neighbour) in
     * normalised coordinates.  Axes that collapse to a single value
     * (all-equal across the front) contribute zero.
     *
     * <p>The returned array is parallel to {@code frontIdx}: {@code result[k]}
     * is the crowding distance for {@code vectors[frontIdx.get(k)]}.</p>
     */
    public static double[] crowdingDistance(List<Integer> frontIdx, double[][] vectors, GoalSpec[] goals) {
        int m = frontIdx.size();
        double[] dist = new double[m];
        if (m == 0) return dist;
        if (m <= 2) {                                  // boundaries dominate
            java.util.Arrays.fill(dist, Double.POSITIVE_INFINITY);
            return dist;
        }
        int axes = goals == null ? 0 : goals.length;
        for (int a = 0; a < axes; a++) {
            final GoalSpec g = goals[a];
            if (g == null) continue;                   // skipped axis (policy)
            final int axis = a;

            // Sort the front by deviation on this axis (ascending = better).
            Integer[] sorted = frontIdx.toArray(new Integer[0]);
            java.util.Arrays.sort(sorted, Comparator.comparingDouble(i -> {
                double v = (axis < vectors[i].length) ? vectors[i][axis] : Double.NaN;
                return Double.isNaN(v) ? Double.POSITIVE_INFINITY : g.deviation(v);
            }));
            double vMin = vectors[sorted[0]][axis];
            double vMax = vectors[sorted[m - 1]][axis];
            double vMinDev = Double.isNaN(vMin) ? Double.NaN : g.deviation(vMin);
            double vMaxDev = Double.isNaN(vMax) ? Double.NaN : g.deviation(vMax);
            double range = (Double.isNaN(vMinDev) || Double.isNaN(vMaxDev))
                    ? 0.0 : (vMaxDev - vMinDev);

            // Map sorted-position → position in original frontIdx.  This lets
            // us write back into dist[] in the right slot.
            int[] origPos = new int[m];
            for (int k = 0; k < m; k++) {
                int orig = frontIdx.indexOf(sorted[k]);
                origPos[k] = orig;
            }

            // Boundary members on this axis pin to +∞.
            dist[origPos[0]]      = Double.POSITIVE_INFINITY;
            dist[origPos[m - 1]]  = Double.POSITIVE_INFINITY;
            if (range <= 0) continue;                  // collapsed axis

            for (int k = 1; k < m - 1; k++) {
                if (Double.isInfinite(dist[origPos[k]])) continue;
                double prev = vectors[sorted[k - 1]][axis];
                double next = vectors[sorted[k + 1]][axis];
                if (Double.isNaN(prev) || Double.isNaN(next)) continue;
                dist[origPos[k]] += (g.deviation(next) - g.deviation(prev)) / range;
            }
        }
        return dist;
    }

    /** Convenience: sort one front so the densest members (smallest crowding
     *  distance) come last.  Useful for survivor-selection in a generational
     *  GA where the population must be trimmed back to a fixed size.  Items in
     *  the returned list are parallel to the input {@code frontIdx} after
     *  re-ordering. */
    public static List<Integer> sortByCrowdingDescending(List<Integer> frontIdx, double[] crowding) {
        if (frontIdx.size() != crowding.length)
            throw new IllegalArgumentException("frontIdx and crowding lengths must match");
        Integer[] order = new Integer[frontIdx.size()];
        for (int i = 0; i < order.length; i++) order[i] = i;
        java.util.Arrays.sort(order, (a, b) -> Double.compare(crowding[b], crowding[a]));
        List<Integer> out = new ArrayList<>(frontIdx.size());
        for (int idx : order) out.add(frontIdx.get(idx));
        return out;
    }

    /**
     * Full NSGA-II pass: every candidate gets its rank and (per-front) crowding
     * distance.  Drop-in replacement when callers want both the membership
     * verdict AND the diversity-aware tie-break in one shot.
     *
     * <p>The returned list is parallel to {@code items} / {@code vectors}: the
     * k-th {@link Ranked} corresponds to the k-th input candidate.  This keeps
     * the API simple — callers that want "rank-1 only" filter on
     * {@code r.rank() == 1}, callers that want layered fronts group by
     * {@code r.rank()}.</p>
     */
    public static <T> List<Ranked<T>> nonDominatedSortWithCrowding(List<T> items,
                                                                     double[][] vectors,
                                                                     GoalSpec[] goals) {
        int n = items == null ? 0 : items.size();
        if (n == 0) return List.of();
        if (vectors == null || vectors.length != n)
            throw new IllegalArgumentException("vectors must align with items");

        List<List<Integer>> fronts = fastNonDominatedSort(vectors, goals);
        int[]    rankOf  = new int[n];
        double[] crowdOf = new double[n];
        java.util.Arrays.fill(rankOf, fronts.size() + 1);     // sentinel for unplaced
        for (int r = 0; r < fronts.size(); r++) {
            List<Integer> front = fronts.get(r);
            double[] cd = crowdingDistance(front, vectors, goals);
            for (int k = 0; k < front.size(); k++) {
                rankOf[front.get(k)]  = r + 1;                 // 1-based
                crowdOf[front.get(k)] = cd[k];
            }
        }

        List<Ranked<T>> out = new ArrayList<>(n);
        for (int i = 0; i < n; i++)
            out.add(new Ranked<>(items.get(i), rankOf[i], crowdOf[i]));
        return out;
    }

    /**
     * Convenience: the Pareto front (rank 1) as a {@code List<T>}, in the same
     * order the input items were supplied.  Mirrors the signature of
     * {@link Dominance#paretoFront} so it can be swapped in directly.
     * Callers that need the crowding-distance values per member should use
     * {@link #firstFrontWithCrowding} instead — this overload throws them
     * away.
     */
    public static <T> List<T> firstFront(List<T> items, double[][] vectors, GoalSpec[] goals) {
        List<T> out = new ArrayList<>();
        for (Ranked<T> r : nonDominatedSortWithCrowding(items, vectors, goals))
            if (r.rank() == 1) out.add(r.item());
        return out;
    }

    /** As {@link #firstFront} but exposes the crowding distance for every
     *  rank-1 member.  Indices in the returned list are parallel — same item
     *  ordering as the input, then filtered to rank-1. */
    public static <T> List<Ranked<T>> firstFrontWithCrowding(List<T> items,
                                                              double[][] vectors,
                                                              GoalSpec[] goals) {
        List<Ranked<T>> out = new ArrayList<>();
        for (Ranked<T> r : nonDominatedSortWithCrowding(items, vectors, goals))
            if (r.rank() == 1) out.add(r);
        return out;
    }
}
