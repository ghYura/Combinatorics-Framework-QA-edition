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

package com.company;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * STEP 34 verifier for {@link ProducerCancellation} — the component the Reader pipeline uses to
 * make a cancelled run terminate EARLY. It registers the same kind of virtual-thread pool the
 * pipeline submits candidate tasks to, fills it with long-running tasks, then cancels and proves
 * the watcher {@code shutdownNow()}s the pool so it terminates promptly (interrupting in-flight
 * tasks) instead of waiting for every task to finish.
 *
 * Run:  java -cp target/classes com.company.ProducerCancellationSmokeTest
 */
public final class ProducerCancellationSmokeTest {
    private ProducerCancellationSmokeTest() {}

    public static void main(String[] args) throws Exception {
        int f = 0;
        f += testCancelShutsDownPoolsEarly();
        f += testRegisterAfterCancelShutsDownImmediately();
        System.out.println();
        if (f == 0) System.out.println("✅ ALL PRODUCER-CANCELLATION CHECKS PASSED");
        else { System.out.println("❌ " + f + " CHECK(S) FAILED"); System.exit(1); }
    }

    private static int testCancelShutsDownPoolsEarly() throws Exception {
        System.out.println("\n── cancel shuts the producer pools down EARLY (interrupts in-flight tasks) ──");
        Path dir = Files.createTempDirectory("prodcancel");
        try {
            BackpressureGate gate = new BackpressureGate(dir, 1000, 500);
            ProducerCancellation pc = new ProducerCancellation(gate);
            ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor();   // like the pipeline's `executor`
            pc.register(pool);

            int n = 2000;
            AtomicInteger started = new AtomicInteger(0), completed = new AtomicInteger(0), interrupted = new AtomicInteger(0);
            for (int i = 0; i < n; i++) {
                pool.submit(() -> {
                    started.incrementAndGet();
                    try { Thread.sleep(2000); completed.incrementAndGet(); }     // a "long candidate computation"
                    catch (InterruptedException e) { interrupted.incrementAndGet(); }
                });
            }
            Thread.sleep(150);                       // let tasks start running
            long t0 = System.nanoTime();
            gate.cancel();                           // watcher → shutdownNow(pool)
            boolean terminated = pool.awaitTermination(10, TimeUnit.SECONDS);
            long ms = (System.nanoTime() - t0) / 1_000_000;
            pc.close();

            int f = 0;
            f += assertCond("pool terminated after cancel", terminated);
            f += assertCond("terminated EARLY — " + ms + "ms (< the 2000ms a single task needs)", ms < 2000);
            f += assertCond("ProducerCancellation fired", pc.fired());
            f += assertCond("NOT all tasks completed (the run was cut short)", completed.get() < n);
            f += assertCond("in-flight tasks were interrupted", interrupted.get() > 0);
            return f;
        } finally { rm(dir); }
    }

    private static int testRegisterAfterCancelShutsDownImmediately() throws Exception {
        System.out.println("\n── a pool registered AFTER cancel is shut down at once ──");
        Path dir = Files.createTempDirectory("prodcancel2");
        try {
            BackpressureGate gate = new BackpressureGate(dir, 10, 5);
            gate.cancel();
            ProducerCancellation pc = new ProducerCancellation(gate);
            Thread.sleep(120);                       // let the watcher observe the cancel
            ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor();
            pc.register(pool);                       // registered after cancel → shut down immediately
            int f = assertCond("late-registered pool is shut down", pool.isShutdown());
            pc.close();
            return f;
        } finally { rm(dir); }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static void rm(Path root) throws java.io.IOException {
        if (!Files.exists(root)) return;
        try (var w = Files.walk(root)) {
            w.sorted(Comparator.reverseOrder()).forEach(p -> { try { Files.delete(p); } catch (java.io.IOException _) {} });
        }
    }
}
