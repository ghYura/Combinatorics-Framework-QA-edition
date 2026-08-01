// =========================================================================
// FIL 02 of 13
// Class:   Generator<T>  (abstract)
// Package: org.ghYura.combinatorics3parallel
// Role:    Абстрактная база — iterator/stream/chunking из одного
//          getElementByIndex(long).  Subclass-ы реализуют только
//          getElementByIndex() и getNumberOfGeneratedElements().
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.*;
import java.util.stream.*;

/**
 * Abstract base class for all index-addressable generators.
 *
 * <h2>Extension contract</h2>
 * <p>Subclasses implement exactly two methods:
 * <ol>
 *   <li>{@link #getElementByIndex(long)} — must be a pure, side-effect-free,
 *       thread-safe function from index to element.</li>
 *   <li>{@link #getNumberOfGeneratedElements()} — must return a non-negative
 *       long computed by closed-form formula without any heap allocation.</li>
 * </ol>
 * <p>All iteration, streaming, and parallel chunking are derived from these two
 * primitives automatically.<!--/p-->
 *
 * <h2>Thread safety</h2>
 * <p>As long as subclasses fulfil the pure-function contract above, all
 * methods of this class are thread-safe.  In particular, multiple threads
 * may call {@link #getElementByIndex(long)} concurrently on the same
 * generator instance without external synchronisation.</p>
 *
 * @param <T> the type of element produced
 * @author Yurii Baranov
 */
public abstract class Generator<T> implements IGenerator<T> {
    /** Default constructor for use by subclasses. Y */
    protected Generator() {}//Y
    /**
     * Returns the element at the given zero-based index.
     *
     * <p><b>Implementation requirements:</b>
     * <ul>
     *   <li>Must be a pure function: same index always yields the same element.</li>
     *   <li>Must be thread-safe: called concurrently by multiple virtual threads
     *       during parallel chunk processing.</li>
     *   <li>Must not allocate shared mutable state.</li>
     * </ul>
     *
     * @param index zero-based element index in [0, {@link #getNumberOfGeneratedElements()})
     * @return the element at {@code index}; never {@code null}
     */
    protected abstract T getElementByIndex(long index);

    /** {@inheritDoc} */
    @Override
    public abstract long getNumberOfGeneratedElements();

    /**
     * {@inheritDoc}
     *
     * <p>The returned iterator walks indices from 0 to
     * {@link #getNumberOfGeneratedElements()} − 1 inclusive.  It is
     * <em>not</em> thread-safe; do not share across threads.</p>
     */
    @Override
    public Iterator<T> iterator() {
        return new Iterator<>() {
            private long cur = 0;

            @Override
            public boolean hasNext() {
                return cur < getNumberOfGeneratedElements();
            }

            @Override
            public T next() {
                if (!hasNext()) throw new NoSuchElementException();
                return getElementByIndex(cur++);
            }
        };
    }

    /**
     * {@inheritDoc}
     *
     * <p>The stream is sequential and lazy: elements are produced by
     * {@link #getElementByIndex(long)} only as the terminal operation
     * demands them.  No elements are buffered.</p>
     */
    @Override
    public Stream<T> stream() {
        return LongStream.range(0, getNumberOfGeneratedElements())
                         .mapToObj(this::getElementByIndex);
    }

    /**
     * {@inheritDoc}
     *
     * <p>Distribution algorithm: the total {@code N} elements are distributed
     * across {@code min(threads, N)} chunks.  The first {@code N % threads}
     * chunks receive {@code ⌈N/threads⌉} elements; the remaining chunks
     * receive {@code ⌊N/threads⌋} elements.  This balanced distribution
     * minimises the maximum chunk size.</p>
     *
     * <p>Each returned stream is backed by a {@link LongStream#range} over its
     * sub-range, so no elements are computed until a terminal operation is
     * applied to the stream.</p>
     */
    @Override
    public List<Stream<T>> asArrayOfStreamsForGivenThreads(int threads) {
        if (threads <= 0) {
            throw new IllegalArgumentException("threads must be > 0, got: " + threads);
        }
        long total = getNumberOfGeneratedElements();
        if (total <= 0) return Collections.emptyList();

        // Cap chunk count to actual element count — no empty chunks.
        int  n         = (int) Math.min((long) threads, total);
        long chunkSize = total / n;
        long remainder = total % n;   // first `remainder` chunks get one extra element

        List<Stream<T>> streams = new ArrayList<>(n);
        long start = 0;
        for (int i = 0; i < n; i++) {
            long end    = start + chunkSize + (i < remainder ? 1 : 0);
            final long fStart = start;
            final long fEnd   = end;
            streams.add(
                LongStream.range(fStart, fEnd).mapToObj(this::getElementByIndex)
            );
            start = end;
        }
        return streams;
    }
}
