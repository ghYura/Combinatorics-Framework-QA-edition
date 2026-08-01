// =========================================================================
// FIL 05 of 13
// Class:   MultiCombinationGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    C(n+k-1,k) мультисет-комбинации (с повторениями).
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates all multiset combinations (combinations <em>with</em> repetition)
 * of {@code k} elements chosen from a source list.
 * Total count = C(n + k − 1, k), also written C(n+k-1, n-1).
 *
 * <h2>Algorithm</h2>
 * <p>Index unranking via the <em>multiset combinatorial number system</em>:
 * each position is resolved greedily using the recurrence for stars-and-bars.
 * Once an element at position {@code p} is chosen, subsequent elements may
 * repeat that same position (unlike plain combinations, where {@code lastIdx}
 * advances).  Cost is O(k²) per element.</p>
 *
 * @param <T> element type
 * @author Yurii Baranov
 */
public class MultiCombinationGenerator<T> extends Generator<List<T>> {

    /** Immutable source list. */
    private final List<T> src;

    /** Multiset combination size. */
    private final int k;

    /** C(src.size() + k − 1, k), computed in the constructor. */
    private final long total;

    /**
     * Creates a new {@code MultiCombinationGenerator} for multiset combinations of size {@code k}.
     *
     * @param src source collection; must not be {@code null}
     * @param k   combination size; must be ≥ 0
     * @throws NullPointerException     if {@code src} is {@code null}
     * @throws IllegalArgumentException if {@code k < 0}
     */
    public MultiCombinationGenerator(Collection<T> src, int k) {
        Objects.requireNonNull(src, "src must not be null");
        if (k < 0) {
            throw new IllegalArgumentException("k must be >= 0, got: " + k);
        }
        this.src   = List.copyOf(src);
        this.k     = k;
        this.total = CombinatoricsUtils.binomial(this.src.size() + k - 1, k);
    }

    /**
     * {@inheritDoc}
     *
     * @param index zero-based index in [0, {@link #getNumberOfGeneratedElements()})
     * @throws IndexOutOfBoundsException if {@code index} is out of range
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        if (index < 0 || index >= total) {
            throw new IndexOutOfBoundsException(
                "Index " + index + " out of [0, " + total + ")");
        }
        List<T> res     = new ArrayList<>(k);
        int     n       = src.size();
        long    left    = index;
        int     lastIdx = 0;   // repetition allowed: lastIdx does NOT advance past chosen element

        for (int i = 0; i < k; i++) {
            int nextIdx = lastIdx;
            while (nextIdx < n) {
                // Number of multiset combinations of length (k-i-1) from elements ≥ nextIdx.
                long count = CombinatoricsUtils.binomial(n - nextIdx + k - i - 2, k - i - 1);
                if (left < count) {
                    res.add(src.get(nextIdx));
                    lastIdx = nextIdx;   // <-- same index may be chosen again
                    break;
                }
                left -= count;
                nextIdx++;
            }
        }
        return res;
    }

    /** @return C(n + k − 1, k) */
    @Override
    public long getNumberOfGeneratedElements() { return total; }
}
