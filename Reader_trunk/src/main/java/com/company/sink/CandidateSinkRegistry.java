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

package com.company.sink;

/**
 * STEP 31 — process-global handle to the last {@link CandidateSink.Summary}.
 *
 * <p>Follows the same idiom as {@link RowSinkRegistry}: the pipeline records the
 * sink's authoritative summary when it finishes emitting candidates, and the
 * downstream {@code HandoffManifestWriter} (which runs after the pipeline, in a
 * static context) reads back the sink's transport so the Handoff v2 manifest's
 * {@code candidate_transport} reflects the sink type actually used — instead of a
 * hardcoded literal (plan action: "Handoff transport описывает sink type").
 *
 * <p>When no sink ran (e.g. ZIP or in-memory streaming output), {@link #last} is
 * {@code null} and {@link #transportOrDefault} falls back to the caller's default,
 * so behaviour is unchanged for those modes.
 */
public final class CandidateSinkRegistry {
    private CandidateSinkRegistry() {}

    private static volatile CandidateSink.Summary lastSummary;

    /** Record the authoritative summary of the just-completed candidate emission. */
    public static void record(CandidateSink.Summary summary) {
        lastSummary = summary;
    }

    /** The last recorded summary, or {@code null} if no candidate sink has run. */
    public static CandidateSink.Summary last() {
        return lastSummary;
    }

    /** Transport of the last sink, or {@code dflt} if none ran / none recorded. */
    public static String transportOrDefault(String dflt) {
        CandidateSink.Summary s = lastSummary;
        return (s != null && s.transport() != null) ? s.transport() : dflt;
    }

    /** Test/utility hook: clear the recorded summary. */
    public static void reset() {
        lastSummary = null;
    }
}
