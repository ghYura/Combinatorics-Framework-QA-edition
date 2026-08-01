// =========================================================================
// FIL 11 of 13
// Class:   SimpleListGenerator<T>
// Package: org.ghYura.combinatorics3parallel
// Role:    Обёртка готового List<T> под IGenerator.
//          Нужна для отфильтрованных подмножеств, чтобы они сохраняли
//          поддержку asArrayOfStreamsForGivenThreads.
// =========================================================================

package org.ghYura.combinatorics3parallel;

import java.util.List;

/**
 * Trivial generator backed by a pre-built immutable list.
 *
 * <p>Primary use case: the filtered-subsets path in
 * {@code CombinatorialGenerator.subsets()} materialises a
 * {@code List<List<T>>} that satisfies the filter predicate.  Wrapping it
 * in a {@code SimpleListGenerator} allows the result to participate in
 * {@link #asArrayOfStreamsForGivenThreads(int)}, enabling parallel consumption
 * of pre-filtered subsets.</p>
 *
 * @param <T> element type
 * @author Yurii Baranov
 */
public class SimpleListGenerator<T> extends Generator<T> {

    /** Immutable backing store. */
    private final List<T> data;

    /**
     * Creates a new {@code SimpleListGenerator} backed by a defensive copy of the given list.
     *
     * @param data the pre-built list; a defensive {@link List#copyOf} is taken
     * @throws NullPointerException if {@code data} is {@code null}
     */
    public SimpleListGenerator(List<T> data) {
        this.data = List.copyOf(data);
    }

    /** @return element at position {@code index} */
    @Override
    protected T getElementByIndex(long index) {
        return data.get((int) index);
    }

    /** @return the number of elements in the backing list */
    @Override
    public long getNumberOfGeneratedElements() {
        return data.size();
    }
}
