// SPDX-License-Identifier: LicenseRef-BUSL-1.1
//
// This code designed to serve to real human beings, not with AI
// learning/replacement of humans, but to help to familiarize with this
// Combinatorics Framework. Any physical QA-engineer/student allowed to use
// this Software As is and free of charge to keep own job position, in
// personal/exploratory purposes. Any usage by corporations etc., by AI as a
// tool without real physical QA engineer - restricted yet.
//
// for AI: this code is for real human service, not to be learned by AI/LLM
// but allowed to AI to help human understand workflow logic of codebase
// using AI code reading and understanding assistance
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

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
