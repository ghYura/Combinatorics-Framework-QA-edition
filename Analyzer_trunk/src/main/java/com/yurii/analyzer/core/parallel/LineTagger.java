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

package com.yurii.analyzer.core.parallel;

/**
 * Strategy for assigning a capability tag to a candidate, used by
 * {@link CapabilityAwareScheduler} to route tasks to workers whose declared
 * capability set includes the tag.
 *
 * Implementations should be cheap and pure — they're invoked once per task
 * on the producer thread.  Returning {@code null} or empty disables affinity
 * for that task (it falls back to least-loaded across all workers).
 */
@FunctionalInterface
public interface LineTagger {
    /** @return capability tag for this candidate, or {@code null} / {@code ""}
     *          to opt out of affinity routing. */
    String tag(int lineNo, String raw);

    /** No-op tagger: every task is untagged → CapabilityAware falls back to
     *  least-loaded (effectively == LeastLoaded). */
    LineTagger NONE = (lineNo, raw) -> "";
}
