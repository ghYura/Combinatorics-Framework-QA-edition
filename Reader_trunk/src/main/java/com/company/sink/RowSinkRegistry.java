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
 * Process-global, thread-safe handle to the active {@link RowSink}.
 *
 * The framework's {@code Main} class is highly procedural with many static
 * fields already (FW_B_ARR, cfg().pathFwOutFile(), etc.); this
 * registry follows the same idiom rather than threading a sink reference
 * through every internal helper.  Cost: one {@code volatile} read on the
 * hot row-emission path — negligible relative to the actual byte work.
 *
 * Usage:
 *   • At startup (after properties are loaded) call {@link #install} once
 *     with whatever sink the user chose (e.g. {@link AnalyzerBridge} when
 *     {@code fw.analyzer.enabled=true}, or a custom one).
 *   • Both row-emission paths in {@code Main} guard their sink call with
 *     {@link #isActive()} so the no-sink configuration pays nothing beyond
 *     a single boolean check per row.
 *   • At shutdown (after the framework finishes its main run) call
 *     {@link #closeActive()} so the sink can flush any buffered state.
 */
public final class RowSinkRegistry {
    private RowSinkRegistry() {}

    /** No-op sink — installed by default so {@code current().accept(...)}
     *  is always safe to call without a null check. */
    public static final RowSink NULL = (id, row) -> {};

    private static volatile RowSink active = NULL;

    /** Install a sink.  Passing {@code null} restores the no-op default. */
    public static void install(RowSink sink) {
        active = (sink == null) ? NULL : sink;
    }

    /** Currently installed sink (never null). */
    public static RowSink current() {
        return active;
    }

    /** {@code true} iff a non-noop sink is installed.  Hot-path callers
     *  can short-circuit row-construction work for the sink when this is
     *  false. */
    public static boolean isActive() {
        return active != NULL;
    }

    /** Close + reset — call once when the framework's main loop exits so
     *  the sink can finalise its aggregation. */
    public static void closeActive() {
        RowSink s = active;
        active = NULL;
        if (s != null && s != NULL) {
            try { s.close(); } catch (Exception _) {}
        }
    }
}
