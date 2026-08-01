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
