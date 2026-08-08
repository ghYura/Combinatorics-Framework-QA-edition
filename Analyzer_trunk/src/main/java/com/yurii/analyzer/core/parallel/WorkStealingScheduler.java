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

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

/**
 * Shared-queue, free-worker-takes-first scheduler.  Byte-for-byte equivalent
 * of the legacy hard-coded parallel path in {@code analyzeStreamParallel}:
 *   • Single bounded queue, default capacity {@code max(1024, parallelism * 256)}.
 *   • All workers race on {@code take()}.
 *   • Single POISON published on {@link #close}; cascaded by workers so each
 *     sibling sees it without the producer needing to publish N copies.
 *
 * This is the right default for streaming workloads where per-candidate cost
 * is roughly uniform — the implicit work-stealing naturally absorbs minor
 * skew.  Switch to {@link LeastLoadedScheduler} when execution cost varies
 * by orders of magnitude across candidates.
 */
public final class WorkStealingScheduler implements Scheduler {

    private final BlockingQueue<Task> queue;

    public WorkStealingScheduler(int parallelism) {
        this(parallelism, Math.max(1024, parallelism * 256));
    }
    public WorkStealingScheduler(int parallelism, int capacity) {
        if (parallelism <= 0) throw new IllegalArgumentException("parallelism must be > 0");
        if (capacity <= 0)    throw new IllegalArgumentException("capacity must be > 0");
        this.queue = new ArrayBlockingQueue<>(capacity);
    }

    @Override public void submit(int lineNo, String raw) throws InterruptedException {
        queue.put(new Task(lineNo, raw));
    }

    @Override public Task take(int workerId) throws InterruptedException {
        Task t = queue.take();
        if (t == Task.POISON) {
            // Cascade so siblings exit too.  One POISON keeps circulating
            // until every worker has consumed-and-republished it once.
            queue.put(Task.POISON);
            return Task.POISON;
        }
        return t;
    }

    @Override public void close() throws InterruptedException {
        queue.put(Task.POISON);
    }
}
