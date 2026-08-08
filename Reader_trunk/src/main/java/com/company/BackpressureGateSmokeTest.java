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

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * STEP 34 verifier for the producer-side {@link BackpressureGate}. Proves it (a) computes depth
 * from the same plain-text {@code consumed-<id>} files the Python Executor's {@code
 * backpressure.py} writes, (b) keeps the queue bounded by the high watermark even under MANY
 * CONCURRENT producers (the real Reader emits from many virtual threads — the case a sequential
 * test misses), and (c) on cancel stops ALL producers immediately with no overshoot.
 *
 * Run:  java -cp target/classes com.company.BackpressureGateSmokeTest
 */
public final class BackpressureGateSmokeTest {
    private BackpressureGateSmokeTest() {}

    public static void main(String[] args) throws Exception {
        int f = 0;
        f += testDepthFromConsumedFiles();
        f += testConcurrentProducersStayBounded();
        f += testCancelStopsAllProducersWithNoOvershoot();
        System.out.println();
        if (f == 0) System.out.println("✅ ALL BACKPRESSURE-GATE CHECKS PASSED");
        else { System.out.println("❌ " + f + " CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── depth = produced − sum(consumed-*), reading the Python-written format ───────
    private static int testDepthFromConsumedFiles() throws IOException {
        System.out.println("\n── depth from consumed-* files (cross-language format) ──");
        Path dir = Files.createTempDirectory("bpgate-depth");
        try {
            BackpressureGate gate = new BackpressureGate(dir, 100, 50);
            for (int i = 0; i < 10; i++) gate.admit();                 // produced = 10 (well under high)
            writeCount(dir.resolve("consumed-0"), 3);                  // two "workers", like py_executor
            writeCount(dir.resolve("consumed-1"), 2);
            int f = 0;
            f += assertCond("depth == produced(10) − consumed(5) == 5", gate.depth() == 5);
            writeCount(dir.resolve("consumed-0"), 8);                  // consumed = 8 + 2 = 10
            f += assertCond("depth drains to 0 when consumed catches up", gate.depth() == 0);
            return f;
        } finally { rm(dir); }
    }

    // ─── MANY concurrent producers must not collectively overshoot the high watermark ──
    private static int testConcurrentProducersStayBounded() throws Exception {
        System.out.println("\n── concurrent producers stay bounded by high ──");
        Path dir = Files.createTempDirectory("bpgate-concur");
        try {
            int high = 20, producers = 8, perProducer = 100, total = producers * perProducer;
            BackpressureGate gate = new BackpressureGate(dir, high, high / 2);
            AtomicLong consumed = new AtomicLong(0);
            AtomicLong maxDepth = new AtomicLong(0);
            AtomicBoolean stop = new AtomicBoolean(false);
            Path consumedFile = dir.resolve("consumed-0");

            Thread consumer = new Thread(() -> {
                while (!stop.get()) {
                    try { Thread.sleep(2); } catch (InterruptedException e) { return; }
                    if (consumed.get() < gate.producedCount()) {       // drain only real in-flight items
                        try { writeCount(consumedFile, consumed.incrementAndGet()); } catch (IOException _) {}
                    }
                }
            });
            consumer.setDaemon(true); consumer.start();

            Thread[] prods = new Thread[producers];
            for (int t = 0; t < producers; t++) {
                prods[t] = new Thread(() -> {
                    for (int i = 0; i < perProducer; i++) {
                        if (!gate.admit()) return;
                        maxDepth.accumulateAndGet(gate.depth(), Math::max);
                    }
                });
                prods[t].start();
            }
            for (Thread p : prods) p.join(30000);
            for (int i = 0; i < 2000 && consumed.get() < total; i++) Thread.sleep(2);
            stop.set(true); consumer.join(2000);

            int f = 0;
            f += assertCond("all " + total + " candidates admitted", gate.producedCount() == total);
            f += assertCond("queue NEVER exceeded high under " + producers + " concurrent producers ("
                    + maxDepth.get() + " ≤ " + high + ")", maxDepth.get() <= high);
            f += assertCond("consumer drained the whole queue", consumed.get() >= total);
            // STEP 34 metrics: the gate must PUBLISH real producer_wait + max_depth (not 0).
            f += assertCond("producer_wait published > 0 (real backpressure occurred): "
                    + gate.producerWaitSeconds() + "s", gate.producerWaitSeconds() > 0.0);
            f += assertCond("max_depth published in (0, high]: " + gate.maxDepth(),
                    gate.maxDepth() > 0 && gate.maxDepth() <= high);
            f += assertCond("producer_wait + max_depth written as plain files the Executor reads",
                    Files.exists(dir.resolve("producer_wait")) && Files.exists(dir.resolve("max_depth")));
            return f;
        } finally { rm(dir); }
    }

    // ─── cancel stops ALL producers at once, with no candidate admitted past high ────
    private static int testCancelStopsAllProducersWithNoOvershoot() throws Exception {
        System.out.println("\n── cancel stops all producers (no overshoot) ──");
        Path dir = Files.createTempDirectory("bpgate-cancel");
        try {
            int high = 10, producers = 8;
            BackpressureGate gate = new BackpressureGate(dir, high, 5);
            AtomicLong admits = new AtomicLong(0);
            Thread[] prods = new Thread[producers];
            for (int t = 0; t < producers; t++) {
                // No consumer → producers admit up to `high`, then block in admit().
                prods[t] = new Thread(() -> { while (gate.admit()) admits.incrementAndGet(); });
                prods[t].start();
            }
            Thread.sleep(250);                       // let them fill to high and block
            long filledBeforeCancel = admits.get();
            gate.cancel();
            for (Thread p : prods) p.join(3000);

            boolean allDone = true;
            for (Thread p : prods) if (p.isAlive()) allDone = false;
            int f = 0;
            f += assertCond("all producers terminated promptly after cancel", allDone);
            f += assertCond("exactly high (" + high + ") admitted — no overshoot (got " + admits.get() + ")",
                    admits.get() == high);
            f += assertCond("queue was filled to high before cancel", filledBeforeCancel == high);
            f += assertCond("admit() returns false after cancel (no further candidates written)", !gate.admit());
            return f;
        } finally { rm(dir); }
    }

    // ─── helpers ────────────────────────────────────────────────────────────────────
    private static void writeCount(Path p, long n) throws IOException {
        // Atomic publish (like the Python Executor's os.replace and the gate's own writeAtomic),
        // so a concurrent reader never sees the counter file momentarily absent/partial.
        Path tmp = p.resolveSibling(p.getFileName() + ".tmp");
        Files.writeString(tmp, Long.toString(n), StandardCharsets.UTF_8);
        try {
            Files.move(tmp, p, java.nio.file.StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            Files.move(tmp, p, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static void rm(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var w = Files.walk(root)) {
            w.sorted(Comparator.reverseOrder()).forEach(p -> { try { Files.delete(p); } catch (IOException _) {} });
        }
    }
}
