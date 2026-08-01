package com.yurii.analyzer.core.optimization;

/**
 * Immutable cumulative statistics for a memoising {@link LineExecutor}.
 *
 * Exposed on {@link OnlineMetricAggregator.Snapshot} so downstream tools (CI
 * dashboards, Combinatorics-engine feedback loop, GP outer-loop) can see how
 * much work the Analyzer skipped versus how much it actually executed.
 *
 * Non-caching executors return {@link #EMPTY}; the Snapshot renders the cache
 * section only when {@code total() > 0}, keeping legacy output byte-for-byte
 * identical when caching is off.
 */
public record CacheStats(long hits, long misses, int size, int capacity) {

    /** Zero-value sentinel returned by non-caching executors. */
    public static final CacheStats EMPTY = new CacheStats(0L, 0L, 0, 0);

    /** Total cache lookups (hits + misses). */
    public long total() { return hits + misses; }

    /** Fraction of lookups satisfied from cache, in [0, 1]; 0 when {@link #total()} is 0. */
    public double hitRate() {
        long t = total();
        return t == 0L ? 0.0 : (double) hits / (double) t;
    }
}
