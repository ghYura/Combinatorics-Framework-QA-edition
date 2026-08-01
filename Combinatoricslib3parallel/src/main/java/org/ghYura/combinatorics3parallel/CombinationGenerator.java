// =========================================================================
// FIL 04 of 13
// Class:   CombinationGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    C(n,k) без повторений.
//          УЛУЧШЕНИЕ: три fast-path случая (k=0, k=1, k=n).
//          SheetWorker типично вызывает combinations(list, 1) — O(1) fast-path
//          критичен для производительности.
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates all combinations of {@code k} elements chosen from a source list
 * without repetition, in lexicographic order.  Total count = C(n, k).
 *
 * <h2>Algorithm</h2>
 * <p>Index unranking via the <em>combinatorial number system</em>:
 * given an index {@code i}, the method finds the unique combination whose
 * rank in co-lexicographic order equals {@code i}.  Each position is resolved
 * greedily using the recurrence
 * <pre>  C(n − pos − 1, k − j − 1) = number of combinations starting with elements ≤ pos</pre>
 * <p>This gives O(k) iterations of a loop that calls {@link CombinatoricsUtils#binomial}
 * (itself O(k) per call), for a total of O(k²) per element.</p>
 *
 * <h2>Fast paths</h2>
 * <ul>
 *   <li>{@code k == 0} → always returns the empty list in O(1).</li>
 *   <li>{@code k == 1} → returns the element at position {@code index} in O(1).</li>
 *   <li>{@code k == n} → always returns the full source list in O(n).</li>
 * </ul>
 * The {@code k == 1} case is particularly important because
 * {@code SheetWorker} frequently calls {@code combinations(list, 1)}.
 *
 * @param <T> element type
 * @author Yurii Baranov
 */
public class CombinationGenerator<T> extends Generator<List<T>> {

    /**
     * Immutable copy of the source collection, preserved in insertion order.
     * Package-visible for potential use by subclasses (e.g., a filtered variant).
     */
    protected final List<T> src;

    /**
     * The combination size (number of elements in each output list).
     * Package-visible for subclasses.
     */
    protected final int k;

    /**
     * Precomputed total = C(src.size(), k).
     * Computed once in the constructor via {@link CombinatoricsUtils#binomial}.
     */
    private final long total;

    /**
     * Constructs a combination generator.
     *
     * @param src source collection; order is preserved via {@link List#copyOf};
     *            must not be {@code null}
     * @param k   combination size; must satisfy 0 ≤ k ≤ src.size()
     * @throws NullPointerException     if {@code src} is {@code null}
     * @throws IllegalArgumentException if {@code k < 0} or {@code k > src.size()}
     */
    public CombinationGenerator(Collection<T> src, int k) {
        Objects.requireNonNull(src, "src must not be null");
        if (k < 0 || k > src.size()) {
            throw new IllegalArgumentException(
                "k must satisfy 0 <= k <= src.size() (src.size()="
                + src.size() + ", k=" + k + ")");
        }
        this.src   = List.copyOf(src);
        this.k     = k;
        this.total = CombinatoricsUtils.binomial(this.src.size(), k);
    }

    /**
     * {@inheritDoc}
     *
     * <p>Applies fast-path optimisations for {@code k == 0}, {@code k == 1},
     * and {@code k == n} before falling through to the general unranking
     * algorithm.</p>
     *
     * @param index zero-based combination index in [0, {@link #getNumberOfGeneratedElements()})
     * @return the combination at the given index; a fresh {@link ArrayList}
     * @throws IndexOutOfBoundsException if {@code index} is out of range
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        if (index < 0 || index >= total) {
            throw new IndexOutOfBoundsException(
                "Index " + index + " out of [0, " + total + ")");
        }

        // ── Fast path: k == 0 ──────────────────────────────────────────────
        // There is exactly one empty combination (index 0).
        if (k == 0) {
            return Collections.emptyList();
        }

        int n = src.size();

        // ── Fast path: k == n ──────────────────────────────────────────────
        // There is exactly one combination containing all elements (index 0).
        if (k == n) {
            return new ArrayList<>(src);
        }

        // ── Fast path: k == 1 ──────────────────────────────────────────────
        // Each single-element combination is uniquely identified by its index.
        // Avoids the full unranking loop; critical for combinations(list, 1).
        if (k == 1) {
            return Collections.singletonList(src.get((int) index));
        }

        // ── General unranking via combinatorial number system ───────────────
        List<T> res     = new ArrayList<>(k);
        long    left    = index;
        int     lastIdx = 0;

        for (int i = 0; i < k; i++) {
            int nextIdx = lastIdx;
            // Invariant: nextIdx < n at each iteration because index < C(n,k)
            // guarantees there always exists a valid position.
            while (nextIdx < n) {
                long count = CombinatoricsUtils.binomial(n - nextIdx - 1, k - i - 1);
                if (left < count) {
                    res.add(src.get(nextIdx));
                    lastIdx = nextIdx + 1;
                    break;
                }
                left -= count;
                nextIdx++;
            }
        }
        return res;
    }

    /** @return C(src.size(), k), computed in the constructor */
    @Override
    public long getNumberOfGeneratedElements() { return total; }
}
