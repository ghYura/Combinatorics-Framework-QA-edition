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

package com.company.bundle;

import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Trivial passthrough strategy.  Useful for:
 * <ul>
 *   <li>The first iteration of a Master-mode run, when no BundleSeed exists
 *       yet (orchestrator unconditionally invokes {@link WorkbookMutator}
 *       and gets back the input unchanged).</li>
 *   <li>Disabling mutation entirely via a property switch without ripping out
 *       the orchestrator plumbing.</li>
 *   <li>Sanity baselines in regression tests.</li>
 * </ul>
 */
public final class NoopStrategy implements WorkbookMutationStrategy {
    @Override public String mutate(ObjectNode workbookRoot, BundleSeedAdapter seed) {
        return "Noop: input passed through unchanged";
    }
    @Override public String name() { return "Noop"; }
}
