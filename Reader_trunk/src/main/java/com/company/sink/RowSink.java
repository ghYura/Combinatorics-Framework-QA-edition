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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

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
