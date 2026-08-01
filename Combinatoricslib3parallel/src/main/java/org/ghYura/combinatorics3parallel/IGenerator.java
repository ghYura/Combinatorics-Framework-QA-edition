// =========================================================================
// FIL 01 of 13
// Class:   IGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    Контракт всей параллельной библиотеки.
//          Каждый генератор должен реализовать этот интерфейс, чтобы
//          SheetWorker мог использовать его через CombinatorialGenerator-фасад.
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

/**
 * Core contract for all index-addressable combinatorial generators in the
 * {@code org.ghYura.combinatorics3parallel} library.
 *
 * <h2>Design philosophy</h2>
 * <p>Each generator maps a zero-based integer index to a combinatorial object
 * via {@link Generator#getElementByIndex(long)}.  All other capabilities —
 * iteration, streaming, and parallel chunking — are derived from that single
 * primitive without pre-materialisation.  This means the memory footprint of
 * a generator is O(1) regardless of how many elements it produces.</p>
 *
 * <h2>Parallel chunking</h2>
 * <p>{@link #asArrayOfStreamsForGivenThreads(int)} splits the index range
 * {@code [0, N)} into at most {@code threads} contiguous sub-ranges and
 * returns one lazy {@link Stream} per sub-range.  Sub-range streams are
 * independent: they can be consumed concurrently without any additional
 * synchronisation inside the generator itself.</p>
 *
 * @param <T> the type of element produced by this generator
 * @author Yurii Baranov
 * @see Generator
 */
public interface IGenerator<T> extends Iterable<T> {

    /**
     * Returns a lazy sequential {@link Stream} that produces all elements
     * in ascending index order.
     *
     * <p>The stream is <em>not</em> parallel; elements are computed on demand
     * via {@link Generator#getElementByIndex(long)}.  Closing the stream has
     * no effect.</p>
     *
     * @return sequential stream of all elements; never {@code null}
     */
    Stream<T> stream();

    /**
     * Partitions the generation space {@code [0, N)} into at most
     * {@code threads} non-overlapping contiguous index ranges and returns
     * one lazy {@link Stream} per range.
     *
     * <p>If {@code N < threads}, fewer streams are returned (one per element).
     * If {@code N == 0}, an empty list is returned.  The streams in the
     * returned list are independent and may be consumed concurrently by
     * separate virtual threads.</p>
     *
     * <p>Typical usage with a virtual-thread executor:
     * <pre>{@code
     * try (var exec = Executors.newVirtualThreadPerTaskExecutor()) {
     *     generator.asArrayOfStreamsForGivenThreads(8)
     *              .forEach(chunk -> exec.submit(() -> chunk.forEach(process)));
     * }
     * }</pre>
     *
     * @param threads desired parallelism level; must be &gt; 0
     * @return list of independent, non-overlapping chunk-streams;
     *         empty list if {@link #getNumberOfGeneratedElements()} is 0
     */
    List<Stream<T>> asArrayOfStreamsForGivenThreads(int threads);

    /**
     * Returns the total number of elements this generator will produce.
     *
     * <p>This value is computed by closed-form combinatorial formulae in O(1)
     * — no elements are generated and no memory is allocated beyond a few
     * local variables.  Callers may safely invoke this method before deciding
     * whether to apply parallelism.</p>
     *
     * @return total element count; always ≥ 0
     */
    long getNumberOfGeneratedElements();

    /**
     * Returns {@code true} if this generator produces no elements.
     *
     * <p>Default implementation delegates to
     * {@link #getNumberOfGeneratedElements()}.</p>
     *
     * @return {@code true} iff the total element count is zero
     */
    default boolean isEmpty() {
        return getNumberOfGeneratedElements() == 0;
    }

    /**
     * Returns an {@link Optional} containing the first element (index 0),
     * or {@link Optional#empty()} if this generator is empty.
     *
     * <p>Default implementation uses {@link #stream()} so it works for all
     * generators regardless of whether they support direct index access from
     * the interface alone.</p>
     *
     * @return optional first element
     */
    default Optional<T> first() {
        return stream().findFirst();
    }
}
