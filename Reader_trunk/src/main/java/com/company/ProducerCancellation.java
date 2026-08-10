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

package com.company;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;

/**
 * STEP 34 — propagates a shared {@link BackpressureGate} cancel to the Reader's PRODUCER
 * pipeline so a cancelled run terminates EARLY instead of computing every remaining candidate.
 *
 * <p>Per-task and per-row cancel checks alone don't help much: the candidate tasks are submitted
 * to a virtual-thread {@code executor} from driver-pool tasks streaming the Core DB, and the
 * launcher then {@code awaitTermination}s the pool. Without an active cancellation, every queued
 * task still runs (its body may early-return, but the scheduling + remaining driver reads
 * continue). This watcher polls the gate and, on cancel, calls {@link ExecutorService#shutdownNow}
 * on EVERY registered pool — interrupting the running candidate tasks and draining the queues — so
 * {@code awaitTermination} returns promptly. Producers also stop SUBMITTING (the streaming
 * callbacks check {@link BackpressureGate#isCancelled} before enqueuing the next candidate).
 *
 * <p>Register each producer pool ({@code executor}, the FINAL/CARTESIAN driver pools) as it is
 * created; a pool registered after the cancel was already seen is shut down immediately. {@link
 * #close} stops the watcher at end-of-run.
 */
public final class ProducerCancellation {

    private final BackpressureGate gate;
    private final List<ExecutorService> pools = new CopyOnWriteArrayList<>();
    private final Thread watcher;
    private volatile boolean fired = false;

    public ProducerCancellation(BackpressureGate gate) {
        this.gate = gate;
        this.watcher = new Thread(this::watch, "bp-cancel-watcher");
        this.watcher.setDaemon(true);
        this.watcher.start();
    }

    /** Register a producer pool to be {@code shutdownNow()}'d on cancel (idempotent). */
    public void register(ExecutorService pool) {
        if (pool == null) return;
        pools.add(pool);
        if (fired || gate.isCancelled()) {
            pool.shutdownNow();          // cancel already seen → don't let it start running
        }
    }

    private void watch() {
        while (!Thread.currentThread().isInterrupted()) {
            if (gate.isCancelled()) {
                fired = true;
                System.out.println("  [backpressure] CANCEL observed — shutting down "
                        + pools.size() + " producer pool(s) (interrupting in-flight candidate tasks)");
                for (ExecutorService p : pools) {
                    p.shutdownNow();
                }
                return;
            }
            try {
                Thread.sleep(50);
            } catch (InterruptedException e) {
                return;
            }
        }
    }

    /** True once the cancel was observed and the registered pools were shut down. */
    public boolean fired() {
        return fired;
    }

    /** Stop the watcher (end-of-run). Idempotent. */
    public void close() {
        watcher.interrupt();
    }
}
