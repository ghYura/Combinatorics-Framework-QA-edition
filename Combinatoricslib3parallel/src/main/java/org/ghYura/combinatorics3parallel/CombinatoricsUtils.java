// =========================================================================
// FIL 03 of 13
// Class:   CombinatoricsUtils  (final, static)
// Package: org.ghYura.combinatorics3parallel
// Role:    Математический фундамент библиотеки.
//          УЛУЧШЕНИЕ: precomputed factorial lookup table [0..20].
//          Устраняет повторные умножения в MultiPermutationGenerator, который
//          вызывает factorial() в двойном цикле O(n²) за каждый элемент.
// =========================================================================

package org.ghYura.combinatorics3parallel;

/**
 * Pure mathematical utilities shared by all combinatorial generators.
 *
 * <h2>Overflow ranges</h2>
 * <table border="1">
 * <caption>Description of the table(TO_DO)</caption>
 * <tr><th>Function</th><th>Max safe input</th><th>Max safe value</th></tr>
 * <tr><td>{@link #factorial(int)}</td><td>n ≤ 20</td><td>20! = 2,432,902,008,176,640,000</td></tr>
 * <tr><td>{@link #binomial(int,int)}</td><td>roughly n ≤ 66 for k near n/2</td><td>varies</td></tr>
 * </table>
 *
 * <h2>Performance note</h2>
 * <p>Factorials for arguments 0..20 are served from a precomputed lookup
 * table, making {@link #factorial(int)} an O(1) array access.  This
 * matters critically for {@code MultiPermutationGenerator.getElementByIndex()},
 * which calls {@code factorial} in a double-nested loop.</p>
 *
 * @author Yurii Baranov
 */
public final class CombinatoricsUtils {

    private CombinatoricsUtils() {}

    // ── Precomputed factorial table ───────────────────────────────────────

    /**
     * Precomputed values of k! for k in [0, 20].
     * 20! is the largest factorial that fits in a signed 64-bit long.
     * Access is O(1) via direct index.
     */
    private static final long[] FACTORIAL_TABLE;

    static {
        FACTORIAL_TABLE = new long[21];
        FACTORIAL_TABLE[0] = 1L;
        for (int i = 1; i <= 20; i++) {
            // Safe: 20! = 2_432_902_008_176_640_000L < Long.MAX_VALUE.
            FACTORIAL_TABLE[i] = FACTORIAL_TABLE[i - 1] * i;
        }
    }

    // ── Public API ────────────────────────────────────────────────────────

    /**
     * Returns {@code n!} (n factorial) as a {@code long}.
     *
     * <p>Values are served from a precomputed lookup table for arguments
     * 0 through 20.  This makes the method O(1) regardless of {@code n}.</p>
     *
     * @param n non-negative integer; must satisfy 0 ≤ n ≤ 20
     * @return n!
     * @throws IllegalArgumentException if {@code n < 0}
     * @throws ArithmeticException      if {@code n > 20} (would overflow long)
     */
    public static long factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("factorial requires n >= 0, got: " + n);
        }
        if (n > 20) {
            //<Y24042026> Compute actual value locally using BigInteger
            java.math.BigInteger bigFact = java.math.BigInteger.valueOf(FACTORIAL_TABLE[20]);
            for (int i = 21; i <= n; i++) {
                bigFact = bigFact.multiply(java.math.BigInteger.valueOf(i));
            }
            // Format result properly to scientific notation (e.g., 1.23456E+100)
            java.math.BigDecimal bdFact = new java.math.BigDecimal(bigFact);
            String formattedResult = String.format(java.util.Locale.US, "%.5E", bdFact);

            System.out.println("[Y WARNING] Actual factorial in 'ghYura.combinatorics3parallel.CombinatoricsUtils.java' is: " + formattedResult);
            //</Y24042026>
            throw new ArithmeticException(
                "factorial(" + n + ") overflows long; max safe argument is 20. "
                + "Use BigInteger arithmetic for larger values.");
        }
        return FACTORIAL_TABLE[n];
    }

    /**
     * Returns the binomial coefficient C(n, k) = n! / (k! × (n − k)!).
     *
     * <p>The computation uses the multiplicative formula:
     * <pre>  C(n,k) = ∏_{i=1}^{k} (n − i + 1) / i</pre>
     * <p>which keeps intermediate values small and avoids direct factorial calls
     * for large {@code n}.  The product and quotient interleave, maintaining
     * integer exactness at each step.</p>
     *
     * @param n total elements (n ≥ 0)
     * @param k chosen elements (0 ≤ k ≤ n)
     * @return C(n, k), or {@code 0} if k &lt; 0 or k &gt; n
     * @throws ArithmeticException if an intermediate or final value overflows long
     */
    public static long binomial(int n, int k) {
        if (k < 0 || k > n) return 0;
        if (k == 0 || k == n) return 1;
        // Symmetry: C(n,k) == C(n, n-k); use the smaller k for fewer iterations.
        if (k > n / 2) k = n - k;
        long res = 1;
        for (int i = 1; i <= k; i++) {
            // The division is always exact because C(n,k) is always an integer.
            // Math.multiplyExact guards against the intermediate product overflowing.
            res = Math.multiplyExact(res, n - i + 1) / i;
        }
        return res;
    }
}
