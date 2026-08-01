package com.company.sink;

/**
 * One-method callback fired for every fully-formed combinatorial row that the
 * framework emits.  Designed as a tee-point alongside the existing file/zip
 * writers — the sink sees the same row text that lands in the output file,
 * so downstream consumers (Analyzer, alternate aggregators, custom CLI
 * post-processing) can react row-by-row without re-reading the file.
 *
 * Implementations MUST be thread-safe.  Both code paths in {@code Main}
 * (STREAMING-DIRECT and the per-driver parallel pool) push rows here, and
 * the parallel path produces multiple rows concurrently from worker threads.
 *
 * Default behaviour is "do nothing" via {@link RowSinkRegistry#NULL}, so
 * the framework's existing functionality is preserved when no sink is
 * installed.
 */
@FunctionalInterface
public interface RowSink {

    /**
     * Called once per row.
     *
     * @param id   the combination's primary key (Long-valued; matches the
     *             {@code finalLong} that the framework otherwise prints in
     *             file names / ids)
     * @param row  the row content as it would appear in the output file,
     *             after sheet-prefix prepending, code-byte resolution, and
     *             any FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE substitution.
     *             Trailing separator (FW_B_ARR or sheet ending) IS trimmed
     *             when the framework would have trimmed it for the file —
     *             so this is the canonical "one row" representation.
     */
    void accept(long id, String row);

    /** Optional lifecycle hook.  Called when the framework finishes emitting
     *  rows.  Default no-op so simple lambdas don't have to implement it. */
    default void close() {}
}
