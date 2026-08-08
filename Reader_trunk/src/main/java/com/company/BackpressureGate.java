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
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.concurrent.atomic.AtomicLong;

/**
 * STEP 34 — producer-side bounded-queue gate for the Reader.
 *
 * <p>The legacy Reader paces candidate emission with an OPEN-LOOP time ramp
 * ({@code FILE_GENERATION_DELAY}/{@code rampUp*} in {@code ComboGenerationPipeline} — it just
 * sleeps a shrinking delay between candidates). That is a gentle-start guess, not a bound: a
 * slow (directory-watching) Executor still lets the eventually-fast Reader run ahead without
 * limit, growing on-disk candidate artifacts unboundedly.
 *
 * <p>This is the CLOSED-LOOP bound that complements the ramp: before emitting a candidate the
 * Reader calls {@link #awaitCapacity}, which PAUSES while the in-flight depth
 * ({@code produced - consumed}) is at/above the high watermark and resumes at the low watermark.
 * {@code produced} is this JVM's monotonic counter; {@code consumed} is the sum of the
 * {@code consumed-<id>} plain-text files the Python Executor's {@code backpressure.py} publishes
 * as it processes candidates — the same cross-process state dir, no broker (action 6).
 *
 * <p>Inactive (constructed only) when no backpressure state dir is configured, so the default
 * Reader run is unchanged (ramp-only). Thread-safe: {@link #awaitCapacity}/{@link #noteProduced}
 * are called concurrently from many virtual-thread writers; {@code produced} is an
 * {@link AtomicLong} and the on-disk publish is a last-writer-wins atomic replace of a monotonic
 * value (a slightly stale on-disk {@code produced} only affects metrics, never the gate's own
 * in-memory depth).
 */
public final class BackpressureGate {

    private final Path dir;
    private final Path producedFile;
    private final Path cancelFile;
    private final Path waitFile;         // STEP 34: cumulative producer wait (seconds) — metrics
    private final Path maxDepthFile;     // STEP 34: peak in-flight depth — metrics
    private final int high;
    private final int low;
    private final AtomicLong produced = new AtomicLong(0);
    private volatile long lastFlushed = -1;
    private boolean paused = false;      // hysteresis state (guarded by `this`)

    public BackpressureGate(Path stateDir, int high, int low) throws IOException {
        Files.createDirectories(stateDir);
        this.dir = stateDir;
        this.producedFile = stateDir.resolve("produced");
        this.cancelFile = stateDir.resolve("cancel");
        this.waitFile = stateDir.resolve("producer_wait");
        this.maxDepthFile = stateDir.resolve("max_depth");
        this.high = Math.max(1, high);
        this.low = Math.max(0, Math.min(low, this.high - 1));
        Path started = stateDir.resolve("started");
        if (!Files.exists(started)) {
            writeAtomic(started, Double.toString(System.currentTimeMillis() / 1000.0));
        }
    }

    /**
     * Atomically admit ONE candidate into the bounded queue. This is the single critical section
     * that makes the bound hold under CONCURRENCY: the depth check and the {@code produced}
     * reservation happen under one monitor, so two (of the many virtual-thread) writers can never
     * both observe "depth &lt; high" and then both write — overshooting the watermark. It blocks
     * while the in-flight depth ≥ high (re-polling the cross-process {@code consumed-*} every
     * 50&nbsp;ms, or woken immediately by {@link #cancel}).
     *
     * @return {@code true} once a slot is reserved (the caller MUST then write the candidate);
     *         {@code false} if the run was cancelled — the caller MUST NOT write the candidate.
     */
    public synchronized boolean admit() {
        long waitedNanos = 0;
        try {
            while (!isCancelled()) {
                long d = depth();
                bumpMaxDepth(d);                          // record peak even while blocked
                if (paused) {
                    if (d <= low) {
                        paused = false;                  // hysteresis: drained to LOW → resume
                    }
                } else if (d >= high) {
                    paused = true;                       // hit HIGH → pause until it drains to low
                } else {
                    long p = produced.incrementAndGet(); // reserve the slot, atomic with the check
                    bumpMaxDepth(p - consumed());         // peak right after reserving
                    if (p <= 1 || p - lastFlushed >= 32) {
                        lastFlushed = p;
                        try { writeAtomic(producedFile, Long.toString(p)); } catch (IOException _) { }
                    }
                    return true;
                }
                long t0 = System.nanoTime();
                wait(50);                                // releases the monitor; re-checks consumed on wake
                waitedNanos += System.nanoTime() - t0;
            }
            return false;                                // cancelled → do NOT reserve / write
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        } finally {
            if (waitedNanos > 0) {
                addProducerWait(waitedNanos / 1_000_000_000.0);   // publish cumulative producer wait
            }
        }
    }

    /** Atomically bump the published peak in-flight depth (metrics). Caller holds {@code this}. */
    private void bumpMaxDepth(long d) {
        if (d > readLong(maxDepthFile)) {
            try { writeAtomic(maxDepthFile, Long.toString(d)); } catch (IOException _) { }
        }
    }

    /** Atomically add to the published cumulative producer-wait seconds. Caller holds {@code this}. */
    private void addProducerWait(double seconds) {
        try { writeAtomic(waitFile, Double.toString(readDouble(waitFile) + seconds)); } catch (IOException _) { }
    }

    /** Published cumulative producer-wait seconds (the metric the Executor/launcher reads). */
    public double producerWaitSeconds() {
        return readDouble(waitFile);
    }

    /** Published peak in-flight depth. */
    public long maxDepth() {
        return readLong(maxDepthFile);
    }

    /** In-flight candidates: produced (in-memory) minus consumed (on-disk, from the Executor). */
    public long depth() {
        return Math.max(0, produced.get() - consumed());
    }

    /** This JVM's monotonic produced count (accurate; the on-disk file is flushed only periodically). */
    public long producedCount() {
        return produced.get();
    }

    public boolean isCancelled() {
        return Files.exists(cancelFile);
    }

    /** Signal cancellation to BOTH sides (producer gate + the Executor's consumers poll this).
     *  Wakes any producer blocked in {@link #admit} immediately (in-process); a cross-process
     *  canceller is picked up by admit's 50&nbsp;ms re-poll. */
    public synchronized void cancel() {
        try {
            writeAtomic(cancelFile, "1");
        } catch (IOException _) {
        }
        notifyAll();
    }

    /** Final flush of {@code produced} (e.g. at end-of-run). Idempotent. */
    public void close() {
        try {
            writeAtomic(producedFile, Long.toString(produced.get()));
        } catch (IOException _) {
        }
    }

    private long consumed() {
        long total = 0;
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "consumed-*")) {
            for (Path p : stream) {
                if (p.getFileName().toString().contains(".tmp")) continue;   // skip transient writes
                total += readLong(p);
            }
        } catch (IOException _) {
        }
        return total;
    }

    private static long readLong(Path p) {
        try {
            return Long.parseLong(Files.readString(p, StandardCharsets.UTF_8).trim());
        } catch (IOException | NumberFormatException e) {
            return 0;
        }
    }

    private static double readDouble(Path p) {
        try {
            return Double.parseDouble(Files.readString(p, StandardCharsets.UTF_8).trim());
        } catch (IOException | NumberFormatException e) {
            return 0.0;
        }
    }

    private static void writeAtomic(Path p, String text) throws IOException {
        Path tmp = p.resolveSibling(p.getFileName() + ".tmp." + Thread.currentThread().threadId());
        Files.writeString(tmp, text, StandardCharsets.UTF_8);
        try {
            Files.move(tmp, p, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            Files.move(tmp, p, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
