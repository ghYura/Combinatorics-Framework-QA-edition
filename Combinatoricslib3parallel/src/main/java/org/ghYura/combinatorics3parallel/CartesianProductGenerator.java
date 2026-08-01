// =========================================================================
// FIL 10 of 13
// Class:   CartesianProductGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    N-way декартово произведение через mixed-radix (row-major order).
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates the N-way Cartesian product of ordered lists.
 * Total count = |v₁| × |v₂| × … × |vₙ|.
 *
 * <h2>Row-major enumeration</h2>
 * <p>Elements are enumerated in <em>row-major (last-index-fastest)</em> order,
 * identical to a nested for-loop where the last list's index increments first.
 * Index unranking treats the index as a mixed-radix number whose digit bases
 * are the sizes of the input lists (from right to left).  Cost is O(N) per
 * element.</p>
 *
 * @param <T> element type; all input lists share the same type parameter
 * @author Yurii Baranov
 */
public class CartesianProductGenerator<T> extends Generator<List<T>> {

    /** Immutable copies of all input vectors. */
    private final List<List<T>> vectors;

    /** Product of all vector sizes; 0 if any vector is empty. */
    private final long total;

    /**
     * Creates a new {@code CartesianProductGenerator} from the given collection of input lists.
     *
     * @param src collection of ordered input lists; must not be {@code null};
     *            each inner list must not be {@code null}; empty inner lists
     *            result in a total of 0 (generator produces nothing)
     * @throws NullPointerException if {@code src} or any inner list is {@code null}
     * @throws ArithmeticException  if the product of sizes overflows {@code long}
     */
    public CartesianProductGenerator(Collection<? extends Collection<T>> src) {
        Objects.requireNonNull(src, "src must not be null");
        this.vectors = src.stream()
            .map(v -> {
                Objects.requireNonNull(v, "inner collection must not be null");
                return List.copyOf(v);
            })
            .toList();

        long t = 1;
        for (var v : vectors) {
            if (v.isEmpty()) {
                t = 0;
                break;  // empty vector → product is 0; avoid overflow check
            }
            t = Math.multiplyExact(t, v.size());
        }
        this.total = t;
    }

    /**
     * {@inheritDoc}
     *
     * <p>Decodes the index as a mixed-radix number:
     * last vector contributes the least-significant digit.</p>
     *
     * @param index row-major index in [0, |v₁|×…×|vₙ|)
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        List<T> res  = new ArrayList<>(vectors.size());
        long    left = index;
        // Iterate from last vector to first to extract digits LSB→MSB.
        for (int i = vectors.size() - 1; i >= 0; i--) {
            var v = vectors.get(i);
            res.add(0, v.get((int) (left % v.size())));
            left /= v.size();
        }
        return res;
    }

    /** @return |v₁| × |v₂| × … × |vₙ|; 0 if any input list is empty */
    @Override
    public long getNumberOfGeneratedElements() { return total; }
}
