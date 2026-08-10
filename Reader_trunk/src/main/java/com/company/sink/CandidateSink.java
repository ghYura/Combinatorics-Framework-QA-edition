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
 * STEP 31 — candidate output abstraction.
 *
 * <p>Decouples the combinatorial generator pipeline from the concrete "one loose
 * file per candidate" persistence. The pipeline calls {@link #write} with a stable
 * candidate id and the already-assembled candidate body; the sink decides <em>where</em>
 * and <em>how</em> those bytes land (filename, directory placement, atomicity) and
 * keeps the {@link Summary authoritative tally}.
 *
 * <p>The only implementation today is {@link LooseFileSink} (transport
 * {@code "loose-files"}), which preserves the framework's historical byte-for-byte
 * loose-file output. A future {@code ShardSink} (STEP 32 — compressed shards) will
 * implement this same interface, so the pipeline never needs to learn a second
 * write path; the loose-file mode stays available for debugging.
 *
 * <p>Note: this is a distinct concept from {@link RowSink}. {@code RowSink} is a
 * row-content <em>tee</em> for the Analyzer (it observes row text alongside the
 * real writer); {@code CandidateSink} <em>is</em> the real writer of candidate
 * artifacts.
 *
 * <p>Implementations MUST be thread-safe: {@link #write} is called concurrently from
 * many virtual-thread writers in both the FINAL-only and CARTESIAN passes.
 */
public sealed interface CandidateSink permits LooseFileSink, ShardSink, GrpcCandidateSink {

    /**
     * Persist exactly one candidate.
     *
     * @param candidateId stable candidate identity (e.g. {@code <final>_0_0} or
     *                    {@code <final>_<opt>_<optSuffix>}); used to derive the
     *                    artifact name and the authoritative index.
     * @param content     buffer holding the candidate body; only
     *                    {@code [off, off+len)} is the payload (the caller has already
     *                    applied any FW_REPLACE_ME substitution and computed the trim).
     * @param off         start offset of the payload within {@code content}.
     * @param len         payload length in bytes (already trimmed; never negative).
     */
    void write(String candidateId, byte[] content, int off, int len);

    /** Transport descriptor for the Handoff v2 manifest, e.g. {@code "loose-files"}. */
    String transport();

    /** Authoritative, point-in-time tally of what this sink has persisted so far. */
    Summary summary();

    /** Flush/finalise. Idempotent; safe to call once after the last {@link #write}. */
    void close();

    /**
     * Authoritative summary of a sink's output. The {@link #candidateCount} is the
     * count of candidates the sink actually persisted (not a config guess, not a
     * post-hoc directory listing) — see the STEP 31 acceptance criterion
     * "Count summary authoritative".
     */
    record Summary(String transport, long candidateCount, long bytes, long errors, String index) {

        @Override
        public String toString() {
            return transport + " count=" + candidateCount + " bytes=" + bytes
                    + " errors=" + errors + " index=" + index;
        }
    }
}
