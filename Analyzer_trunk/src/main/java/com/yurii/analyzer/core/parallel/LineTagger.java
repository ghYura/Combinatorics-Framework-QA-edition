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
