// =========================================================================
// FIL 06 of 13
// Class:   PermutationGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    n! перестановок через декодирование факторадического числа.
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates all permutations of a source list (all elements treated as
 * positionally distinct, even if equal by value).  Total count = n!.
 *
 * <h2>Algorithm (Lehmer code / factoradic unranking)</h2>
 * <p>The index is interpreted as a mixed-radix number in the factorial
 * number system.  The most-significant digit (base n) selects the first
 * element; successive digits (bases n-1, n-2, …) select subsequent elements
 * from the remaining pool.  Cost is O(n²) per element due to the list
 * {@link List#remove(int)} shift.</p>
 *
 * <p>No {@link Comparable} constraint is imposed on {@code T}: elements are
 * distinguished by position, not value.</p>
 *
 * @param <T> element type
 * @author Yurii Baranov
 */
public class PermutationGenerator<T> extends Generator<List<T>> {

    /** Immutable source list; all positions are treated as distinct. */
    private final List<T> src;

    /** n! where n = src.size().  Valid only for n ≤ 20. */
    private final long total;

    /**
     * Creates a new {@code PermutationGenerator} for all permutations of the given collection.
     *
     * @param src source collection; must not be {@code null}; max 20 elements
     *            (21! overflows long)
     * @throws NullPointerException if {@code src} is {@code null}
     * @throws ArithmeticException  if {@code src.size() > 20}
     */
    public PermutationGenerator(Collection<T> src) {
        Objects.requireNonNull(src, "src must not be null");
        this.src   = List.copyOf(src);
        this.total = CombinatoricsUtils.factorial(this.src.size());
    }

    /**
     * {@inheritDoc}
     *
     * @param index zero-based permutation index in [0, n!)
     * @throws IndexOutOfBoundsException if {@code index} is out of range
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        if (index < 0 || index >= total) {
            throw new IndexOutOfBoundsException(
                "Index " + index + " out of [0, " + total + ")");
        }
        // Working copy; elements are removed as they are placed.
        List<T> items = new ArrayList<>(src);
        List<T> res   = new ArrayList<>(src.size());
        long    left  = index;
        int     n     = src.size();

        for (int i = n; i > 0; i--) {
            long f   = CombinatoricsUtils.factorial(i - 1);  // O(1) lookup
            int  idx = (int) (left / f);
            res.add(items.remove(idx));
            left %= f;
        }
        return res;
    }

    /** @return n! where n = source size */
    @Override
    public long getNumberOfGeneratedElements() { return total; }
}
