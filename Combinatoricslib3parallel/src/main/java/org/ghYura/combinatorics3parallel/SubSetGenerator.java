// =========================================================================
// FIL 09 of 13
// Class:   SubSetGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    Все 2^n подмножеств через битмаску.
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates all subsets (power set) of a source list in bitmask order.
 * Total count = 2ⁿ.
 *
 * <h2>Bitmask encoding</h2>
 * <p>Subset at index {@code i} contains {@code src.get(k)} iff bit {@code k}
 * is set in {@code i} (i.e., {@code (i >>> k) & 1 == 1}).  This gives a
 * natural correspondence: index 0 = empty set, index 2ⁿ − 1 = full set.
 * Cost per element is O(n).</p>
 *
 * <h2>Size limitation</h2>
 * <p>Java {@code long} is 64-bit signed, so bit {@code 63} is the sign bit.
 * To keep {@code 1L << n} positive and {@code total = 2ⁿ} representable,
 * {@code n} is capped at 62 elements.  An {@link IllegalArgumentException} is
 * thrown at construction time for larger inputs.</p>
 *
 * @param <T> element type
 * @author Yurii Baranov
 */
public class SubSetGenerator<T> extends Generator<List<T>> {

    /** Maximum supported source size (exclusive upper bound = 63). */
    private static final int MAX_ELEMENTS = 62;

    /** Immutable source list. */
    private final List<T> src;

    /** Total subset count = 2^src.size(). */
    private final long total;

    /**
     * Creates a new {@code SubSetGenerator} for all subsets of the given collection.
     *
     * @param src source collection; must not be {@code null}; at most 62 elements
     * @throws NullPointerException     if {@code src} is {@code null}
     * @throws IllegalArgumentException if {@code src.size() > 62}
     */
    public SubSetGenerator(Collection<T> src) {
        Objects.requireNonNull(src, "src must not be null");
        if (src.size() > MAX_ELEMENTS) {
            throw new IllegalArgumentException(
                "SubSetGenerator supports at most " + MAX_ELEMENTS
                + " elements to prevent long overflow; got: " + src.size());
        }
        this.src   = List.copyOf(src);
        this.total = 1L << src.size();  // 2^n; safe because n <= 62
    }

    /**
     * {@inheritDoc}
     *
     * @param index bitmask index in [0, 2ⁿ); bit {@code k} set → include {@code src.get(k)}
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        List<T> res = new ArrayList<>();
        for (int i = 0; i < src.size(); i++) {
            if ((index & (1L << i)) != 0) res.add(src.get(i));
        }
        return res;
    }

    /** @return 2^n where n = source size */
    @Override
    public long getNumberOfGeneratedElements() { return total; }
}
