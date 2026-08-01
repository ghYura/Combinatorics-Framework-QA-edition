package com.yurii.analyzer.core.parallel;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

/**
 * Per-worker-queue scheduler that routes each new task to the worker with the
 * shortest pending queue — minimising tail-latency under heavy per-candidate
 * cost skew (e.g. a mix of cheap {@code Inline} and expensive {@code Shell}
 * executions, or candidates that sometimes hit the {@code Caching} layer and
 * sometimes don't).
 *
 * Trade-off vs {@link WorkStealingScheduler}: per-worker queues prevent any
 * one slow task from blocking the head of a shared queue, but introduce a
 * routing cost (O(P) scan per submit) and lose stealing — a worker that
 * happens to be empty won't pull from a busy neighbour.  Acceptable up to a
 * few dozen workers; beyond that, the shared-queue variant tends to win.
 *
 * close() publishes one POISON per worker queue (no cascade needed).
 */
public final class LeastLoadedScheduler implements Scheduler {

    private final BlockingQueue<Task>[] queues;
    private final int parallelism;

    public LeastLoadedScheduler(int parallelism) {
        this(parallelism, Math.max(64, 256));
    }

    @SuppressWarnings("unchecked")
    public LeastLoadedScheduler(int parallelism, int perWorkerCapacity) {
        if (parallelism <= 0) throw new IllegalArgumentException("parallelism must be > 0");
        if (perWorkerCapacity <= 0) throw new IllegalArgumentException("perWorkerCapacity must be > 0");
        this.parallelism = parallelism;
        // Reserve 1 extra slot for the POISON sentinel so close() never blocks.
        this.queues = (BlockingQueue<Task>[]) new BlockingQueue[parallelism];
        for (int i = 0; i < parallelism; i++) {
            queues[i] = new ArrayBlockingQueue<>(perWorkerCapacity + 1);
        }
    }

    @Override public void submit(int lineNo, String raw) throws InterruptedException {
        int chosen = pickLeastLoaded();
        queues[chosen].put(new Task(lineNo, raw));
    }

    @Override public Task take(int workerId) throws InterruptedException {
        return queues[workerId].take();
    }

    @Override public void close() throws InterruptedException {
        for (int i = 0; i < parallelism; i++) queues[i].put(Task.POISON);
    }

    /** Read-only snapshot of current per-worker pending counts.  Stale by the
     *  time the caller sees it, but useful for diagnostics and verifiers. */
    public int[] pendingCounts() {
        int[] out = new int[parallelism];
        for (int i = 0; i < parallelism; i++) out[i] = queues[i].size();
        return out;
    }

    private int pickLeastLoaded() {
        int best = 0;
        int bestSize = queues[0].size();
        for (int i = 1; i < parallelism; i++) {
            int s = queues[i].size();
            if (s < bestSize) { bestSize = s; best = i; }
        }
        return best;
    }
}
