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
 * Tier-3 win 3.3 — pluggable work-distribution strategy for the parallel
 * streaming path.  The producer (a single thread iterating the candidate
 * source) calls {@link #submit} for each task; N worker threads each call
 * {@link #take} in a loop until the {@link Task#POISON} sentinel is returned.
 *
 * Three built-in implementations, each fitting a different workload shape:
 *   • {@link WorkStealingScheduler} — single shared queue, free-worker-takes-first;
 *     identical semantics to the legacy hard-coded parallel path.  Default.
 *   • {@link LeastLoadedScheduler}  — per-worker queues, producer routes new
 *     tasks to the worker with the shortest queue.  Better balance when
 *     per-candidate execution cost is highly variable (e.g. mixed
 *     shell-out + cheap inline).
 *   • {@link CapabilityAwareScheduler} — per-worker queues + tag affinity;
 *     tasks are routed to workers whose declared capability set contains
 *     the task's tag, falling back to least-loaded across all workers when
 *     no eligible worker exists.  Useful when some workers are specialised
 *     (e.g. dedicated GPU host vs CPU pool).
 *
 * Lifecycle contract:
 *   <ol>
 *     <li>Producer thread calls {@link #submit} per task.</li>
 *     <li>Producer signals end of input with {@link #close}; the scheduler
 *         must propagate {@link Task#POISON} to every worker.</li>
 *     <li>Each worker calls {@link #take} in a loop; on receiving POISON,
 *         the worker exits.  Schedulers MAY require workers to re-publish
 *         POISON for sibling cascade (the shared-queue variant does); the
 *         per-worker-queue variants handle this internally.</li>
 *   </ol>
 *
 * Thread-safety: a {@code Scheduler} is shared by ONE producer and N workers.
 * Implementations must be safe for that pattern.
 */
public interface Scheduler extends AutoCloseable {

    /** Producer-side: enqueue a candidate for execution. */
    void submit(int lineNo, String raw) throws InterruptedException;

    /** Worker-side: pull the next task assigned to {@code workerId}.  Returns
     *  {@link Task#POISON} when no more tasks will arrive for this worker. */
    Task take(int workerId) throws InterruptedException;

    /** Producer-side: signal end-of-input.  Must guarantee that every worker
     *  eventually sees {@link Task#POISON} from {@link #take}. */
    @Override void close() throws InterruptedException;

    /** Optional load-tracking hook called by the worker after each completed
     *  task.  Default no-op; the {@link LeastLoadedScheduler} subclass can
     *  override to refine load estimates from wall-time. */
    default void taskCompleted(int workerId, long elapsedNanos) {}

    /** Numbered candidate flowing through the scheduler. */
    record Task(int lineNo, String raw) {
        /** Sentinel signaling end-of-input to a worker.  Compared by
         *  reference identity — never construct a fresh "poison" record. */
        public static final Task POISON = new Task(-1, null);
    }
}
