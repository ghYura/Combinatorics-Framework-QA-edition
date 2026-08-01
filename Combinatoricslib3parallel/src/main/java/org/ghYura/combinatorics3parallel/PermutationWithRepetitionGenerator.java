// =========================================================================
// FIL 08 of 13  (CORRECTED)
// Class:   PermutationWithRepetitionGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;

/**
 * Generates all permutations <em>with repetition</em> of length {@code r}
 * chosen from a source list of size {@code n}.
 * Total count = nʳ.
 *
 * <h2>Algorithm (mixed-radix / base-n unranking)</h2>
 * <p>The index is treated as a base-{@code n} integer of {@code r} digits.
 * Digit {@code i} (most significant first, i.e., index from
 * {@code length − 1} down to {@code 0}) selects the {@code i}-th element
 * of the output permutation.  A precomputed power cache
 * ({@code powerCache[i] = n^i}) allows O(1) digit extraction, making
 * {@link #getElementByIndex(long)} run in O(r) — the fastest possible for
 * this generator type.</p>
 *
 * <h2>Enumeration order</h2>
 * <p>Elements are enumerated in <em>row-major (first-dimension-slowest)</em>
 * order, identical to the nested-loop pattern:
 * <pre>
 *   for a in src:
 *     for b in src:
 *       yield [a, b]
 * </pre>
 * For {@code src = ["a","b","c"]} and {@code length = 2}, the sequence is:
 * {@code [a,a],[a,b],[a,c],[b,a],[b,b],[b,c],[c,a],[c,b],[c,c]}.
 * <p>This matches the order produced by the paukov {@code withRepetitions(r)}
 * iterator in sequential mode.</p>
 *
 * <h2>Overflow protection</h2>
 * <p>{@link Math#multiplyExact(long, long)} is used when building the power
 * cache, so an {@link ArithmeticException} is thrown at construction time
 * if nʳ would overflow {@code long}, rather than silently wrapping to a
 * nonsensical value at runtime.</p>
 *
 * @param <T> element type
 * @author Dmitry Paukov (original concept)
 * @author Yurii Baranov (index-based access, parallel support, overflow protection)
 */
public class PermutationWithRepetitionGenerator<T> extends Generator<List<T>> {

    /**
     * The original vector of elements from which permutations are generated.
     * This list is immutable after construction.
     * Package-visible for unit tests and potential subclasses.
     */
    final List<T> originalVector;

    /**
     * The length of each permutation sequence (the exponent r in nʳ).
     * Package-visible for unit tests.
     */
    final int length;

    /**
     * Total permutation count = {@code originalVector.size()}^{@code length}.
     * Stored as long; construction throws {@link ArithmeticException} if this
     * value would overflow (detected via the power cache computation).
     */
    private final long total;

    /**
     * Precomputed mixed-radix weights: {@code powerCache[i] = n^i}
     * for i in [0, length], where n = {@code originalVector.size()}.
     *
     * <p>Usage in {@link #getElementByIndex}:
     * digit at position {@code (length − 1 − j)} = {@code (remaining / powerCache[j]) % n},
     * where the loop variable {@code j} runs from {@code length − 1} down to {@code 0}.
     * Because digits are extracted MSB→LSB and appended in that order,
     * the resulting list is already in the correct first-to-last element order.
     * <b>No reversal is needed or correct.</b></p>
     *
     * Package-visible for unit tests.
     */
    final long[] powerCache;

    /**
     * Constructs a permutation-with-repetition generator.
     *
     * @param originalVector the source collection (must not be {@code null})
     * @param length         the length of each permutation (must be ≥ 0)
     * @throws NullPointerException     if {@code originalVector} is {@code null}
     * @throws IllegalArgumentException if {@code length} is negative
     * @throws ArithmeticException      if {@code originalVector.size()}^{@code length}
     *                                  overflows {@code long}
     */
    public PermutationWithRepetitionGenerator(Collection<T> originalVector, int length) {
        Objects.requireNonNull(originalVector, "originalVector must not be null");
        if (length < 0) {
            throw new IllegalArgumentException("length must be >= 0, got: " + length);
        }
        this.originalVector = List.copyOf(originalVector);
        this.length         = length;
        // Build power cache first; this throws ArithmeticException on overflow,
        // which also prevents a nonsensical total value.
        this.powerCache = precomputePowers(this.originalVector.size(), length);
        this.total      = powerCache[length];  // n^length, safely computed above
    }

    /**
     * Returns the permutation-with-repetition at the given index.
     *
     * <p>Interpretation: view {@code index} as a base-{@code n} number of
     * {@code r} digits (zero-padded on the left).  The loop extracts digits
     * from the most-significant position ({@code length − 1}) down to the
     * least-significant ({@code 0}) using the precomputed power cache, and
     * appends the corresponding source element at each step.  Because digits
     * are extracted and appended in MSB-to-LSB order, the resulting list is
     * already in the natural (first-element-first) order.
     * <b>No reversal is applied.</b></p>
     *
     * <p>Example: {@code src = [a,b,c]}, {@code length = 2}, {@code index = 5}:
     * <ul>
     *   <li>Base-3 representation of 5 = 1 × 3¹ + 2 × 3⁰ → digits [1, 2].</li>
     *   <li>Iteration i=1: pos = 5 / 3 = 1, remaining = 2 → append src[1] = b.</li>
     *   <li>Iteration i=0: pos = 2 / 1 = 2, remaining = 0 → append src[2] = c.</li>
     *   <li>Result: [b, c] ✓ (matches row-major order: index 5 = [b,c]).</li>
     * </ul>
     *
     * @param index zero-based index in [0, nʳ)
     * @return a fresh {@link ArrayList} containing the permutation in
     *         first-dimension-slowest (row-major) order; never {@code null}
     * @throws IndexOutOfBoundsException if {@code index} is out of range
     */
    @Override
    protected List<T> getElementByIndex(long index) {
        if (index < 0 || index >= total) {
            throw new IndexOutOfBoundsException(
                "Index " + index + " out of [0, " + total + ")");
        }
        List<T> permutation = new ArrayList<>(length);
        long    remaining   = index;

        // Extract digits from most-significant (powerCache[length-1] = n^(length-1))
        // down to least-significant (powerCache[0] = 1), appending in MSB→LSB order.
        // The resulting list is in the correct first-to-last element order.
        // *** DO NOT reverse: reversing would invert the enumeration order. ***
        for (int i = length - 1; i >= 0; i--) {
            int pos = (int) (remaining / powerCache[i]);
            remaining %= powerCache[i];
            permutation.add(originalVector.get(pos));
        }

        return permutation;
    }

    /** @return nʳ where n = source size and r = length */
    @Override
    public long getNumberOfGeneratedElements() { return total; }

    /**
     * Precomputes {@code powers[i] = base^i} for i in [0, exponent].
     *
     * <p>Uses {@link Math#multiplyExact(long, long)} to detect overflow eagerly
     * at construction time rather than silently wrapping at access time.
     * {@code powers[exponent]} equals nʳ and is stored as {@link #total}.</p>
     *
     * @param base     the radix n (size of original vector); 0 and 1 are valid
     * @param exponent the permutation length r; must be ≥ 0
     * @return array of length {@code exponent + 1} with {@code powers[i] = base^i}
     * @throws ArithmeticException if any intermediate {@code base^i} overflows long
     */
    private static long[] precomputePowers(int base, int exponent) {
        long[] powers = new long[exponent + 1];
        powers[0] = 1L;
        for (int i = 1; i <= exponent; i++) {
            // ArithmeticException here is intentional — surfaces overflow at
            // construction time, not silently at a later access.
            powers[i] = Math.multiplyExact(powers[i - 1], base);
        }
        return powers;
    }
}
