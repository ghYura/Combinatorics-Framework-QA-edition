// =========================================================================
// FIL 07 of 13
// Class:   MultiPermutationGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    n!/(c1!·c2!·…) мультисет-перестановки.
//          КЛЮЧЕВЫЕ ИСПРАВЛЕНИЯ:
//            • Precomputed unique[] + baseCounts[] — нет TreeMap, нет
//              скрытого Comparable-constraint.
//            • Использует CombinatoricsUtils.factorial() (lookup table) —
//              быстрее в двойном цикле getElementByIndex().
//            • Fast-path для src.size() == 1.
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates all <em>distinct</em> permutations of a multiset (a collection
 * that may contain repeated elements).
 * Total count = n! / (c₁! · c₂! · … · cₘ!), where cᵢ are the repetition
 * counts of each distinct element.
 *
 * <h2>Algorithm</h2>
 * <p>Index unranking proceeds position by position.  At each position {@code i},
 * the algorithm tries each unique element {@code e_j} in first-occurrence order:
 * it temporarily decrements {@code counts[j]} and computes the multinomial
 * coefficient for the remaining positions.  If {@code left < subTotal}, element
 * {@code e_j} is placed at position {@code i} and we move to position {@code i+1};
 * otherwise {@code left -= subTotal} and we try the next element.  Cost is
 * O(n × m) per element, where m is the number of distinct elements.</p>
 *
 * <h2>No Comparable requirement</h2>
 * <p>Unlike a {@link TreeMap}-based implementation, this class enumerates
 * unique elements in <em>first-occurrence order</em> using
 * {@link Objects#equals}.  This means {@code T} requires only a correct
 * {@link Object#equals(Object)} implementation, which all standard Java
 * types provide.  In particular, {@code Short} (used throughout
 * {@code SheetWorker}) is supported without any cast or wrapper.</p>
 *
 * @param <T> element type; must implement {@link Object#equals} correctly
 * @author Yurii Baranov
 */
public class MultiPermutationGenerator<T> extends Generator<List<T>> {

    /** Original source list, immutable after construction. */
    private final List<T> src;

    /**
     * Unique elements in first-occurrence order.
     * Size m = number of distinct values in {@code src}.
     */
    private final List<T> unique;

    /**
     * Repetition count for each unique element.
     * {@code baseCounts[j]} = number of times {@code unique.get(j)} appears in {@code src}.
     * Index-parallel to {@code unique}.  Sum of all counts = {@code src.size()}.
     */
    private final int[] baseCounts;

    /**
     * Precomputed total = n! / (c₁! · c₂! · … · cₘ!).
     * Computed in the constructor; never changes.
     */
    private final long total;

    /**
     * Creates a new {@code MultiPermutationGenerator} for all distinct permutations of the given multiset.
     *
     * @param src source collection; may contain duplicates; must not be {@code null};
     *            max 20 elements (21! overflows long)
     * @throws NullPointerException if {@code src} is {@code null}
     * @throws ArithmeticException  if {@code src.size() > 20}
     */
    public MultiPermutationGenerator(Collection<T> src) {
        Objects.requireNonNull(src, "src must not be null");
        this.src    = List.copyOf(src);
        this.unique = new ArrayList<>();

        // Build unique-element list and counts without TreeMap.
        // We iterate once (O(n)) and use Objects.equals for comparison.
        List<Integer> countList = new ArrayList<>();
        for (T t : this.src) {
            int idx = indexOfEqual(unique, t);
            if (idx < 0) {
                unique.add(t);
                countList.add(1);
            } else {
                countList.set(idx, countList.get(idx) + 1);
            }
        }

        this.baseCounts = countList.stream().mapToInt(Integer::intValue).toArray();
        this.total      = computeTotal();
    }

    /**
     * Computes the multinomial coefficient n! / (c₁! · c₂! · … · cₘ!).
     * Uses the factorial lookup table (O(1) per call).
     */
    private long computeTotal() {
        long res = CombinatoricsUtils.factorial(src.size());
        for (int c : baseCounts) {
            res /= CombinatoricsUtils.factorial(c);
        }
        return res;
    }

    /**
     * Linear scan for the first occurrence of {@code target} in {@code list}
     * using {@link Objects#equals}.  Null-safe.
     *
     * @param list   list to search
     * @param target value to find
     * @return index of first match, or -1 if not found
     */
    private static <T> int indexOfEqual(List<T> list, T target) {
        for (int i = 0; i < list.size(); i++) {
            if (Objects.equals(list.get(i), target)) return i;
        }
        return -1;
    }

    /**
     * {@inheritDoc}
     *
     * <p>Uses a per-call clone of {@code baseCounts} so that concurrent calls
     * to this method on the same generator instance are independent and
     * thread-safe.</p>
     *
     * @param index zero-based permutation index in [0, {@link #getNumberOfGeneratedElements()})
     * @throws IndexOutOfBoundsException if {@code index} is out of range
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        if (index < 0 || index >= total) {
            throw new IndexOutOfBoundsException(
                "Index " + index + " out of [0, " + total + ")");
        }

        // Fast-path: only one distinct element → every permutation is identical.
        if (unique.size() == 1) {
            List<T> res = new ArrayList<>(src.size());
            for (int i = 0; i < src.size(); i++) res.add(unique.get(0));
            return res;
        }

        // Per-call mutable count array; does not affect the generator's state.
        int[]   counts = baseCounts.clone();
        List<T> res    = new ArrayList<>(src.size());
        long    left   = index;
        int     n      = src.size();

        for (int i = 0; i < n; i++) {
            for (int j = 0; j < unique.size(); j++) {
                if (counts[j] == 0) continue;

                // Temporarily place unique[j] at position i.
                counts[j]--;

                // Compute the number of distinct permutations of the remaining n-1-i elements.
                // Uses lookup table O(1) per call — hot path.
                long subTotal = CombinatoricsUtils.factorial(n - 1 - i);
                for (int c : counts) subTotal /= CombinatoricsUtils.factorial(c);

                if (left < subTotal) {
                    res.add(unique.get(j));
                    break;   // move to next position
                }

                // Not this element: restore and try the next unique element.
                left -= subTotal;
                counts[j]++;
            }
        }
        return res;
    }

    /** @return n! / (c₁! · … · cₘ!) */
    @Override
    public long getNumberOfGeneratedElements() { return total; }
}
