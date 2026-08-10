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

package com.company.precompute;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Iter4 Layer 3 — runtime heap watchdog.
 *
 * <p>Background daemon thread that samples {@code Runtime.totalMemory() -
 * Runtime.freeMemory()} every {@code samplingIntervalMs} (default 2.5 s) and
 * escalates as pressure crosses configurable thresholds.  Safety net for cases
 * where Layer 1's pessimistic estimate wasn't pessimistic enough — typically
 * because compositional FW_Seq complexity (Group/ReplaceRE/brace fanout) made
 * the actual peak diverge from the static upper bound.</p>
 *
 * <p>Pressure levels (defaults):</p>
 * <ul>
 *   <li>{@link Level#NORMAL}   — usage ≤ 80% of {@code maxMemory}.</li>
 *   <li>{@link Level#WARN}     — usage > 80%, ≤ 90%.</li>
 *   <li>{@link Level#HIGH}     — usage > 90%, ≤ 95%.</li>
 *   <li>{@link Level#CRITICAL} — usage > 95%.</li>
 * </ul>
 *
 * <p>Logging fires once per level CROSSING (not every sample) to avoid log
 * spam.  Each crossing logs the current pipeline stage label so the user can
 * correlate which workload section was active when pressure rose.</p>
 *
 * <p>Mode behaviour (chosen at construction):</p>
 * <ul>
 *   <li>{@link Mode#PASSIVE} — log only.  Used in {@code precompute=db} mode
 *       and as the default for any diagnostic deployment.</li>
 *   <li>{@link Mode#ABORT_ON_HIGH} — fires {@code abortCallback} at the HIGH
 *       crossing.  Used in FORCED-JAVA mode: pipeline interrupts itself with
 *       a clear "exceeded -Xmx" error rather than waiting for a JVM crash.</li>
 *   <li>{@link Mode#DRAIN_ON_CRITICAL} — fires {@code drainCallback} at the
 *       CRITICAL crossing.  Used in AUTO-resolved JAVA mode: pipeline can
 *       attempt to flush in-memory state to PG and continue.  The drain
 *       mechanism itself is future work (Iter4.5+); as of Iter4.4 the callback
 *       only logs a clear escalation message and recommendation to bump
 *       {@code -Xmx}.</li>
 * </ul>
 *
 * <p>Thread-safety: {@code start()}/{@code stop()} are idempotent and
 * synchronized.  {@code setStage} is lock-free via {@link AtomicReference}.
 * The sampling thread is a daemon (JVM exit doesn't block on it).</p>
 */
public final class HeapWatchdog implements AutoCloseable {

    private static final Logger log = LogManager.getLogger(HeapWatchdog.class);

    public enum Mode { PASSIVE, ABORT_ON_HIGH, DRAIN_ON_CRITICAL }
    public enum Level { NORMAL, WARN, HIGH, CRITICAL }

    /** Snapshot of one heap-pressure crossing, passed to callbacks for logging. */
    public static final class HeapPressureEvent {
        public final Level level;
        public final long usedBytes;
        public final long maxBytes;
        public final double fractionUsed;
        public final String stage;
        HeapPressureEvent(Level level, long usedBytes, long maxBytes,
                          double fractionUsed, String stage) {
            this.level = level;
            this.usedBytes = usedBytes;
            this.maxBytes = maxBytes;
            this.fractionUsed = fractionUsed;
            this.stage = stage;
        }
    }

    // ── tunables (defaults; configurable via constructor variant if needed) ──
    private final double WARN_FRAC     = 0.80;
    private final double HIGH_FRAC     = 0.90;
    private final double CRITICAL_FRAC = 0.95;
    private final long   SAMPLE_INTERVAL_MS = 2500L;

    private final Mode mode;
    private final Consumer<HeapPressureEvent> abortCallback;
    private final Consumer<HeapPressureEvent> drainCallback;

    private final ScheduledExecutorService scheduler;
    private final AtomicReference<String> currentStage = new AtomicReference<>("init");
    private volatile Level lastLevel = Level.NORMAL;
    private ScheduledFuture<?> sampleFuture;
    private volatile boolean started = false;
    private volatile boolean stopped = false;

    public HeapWatchdog(Mode mode,
                        Consumer<HeapPressureEvent> abortCallback,
                        Consumer<HeapPressureEvent> drainCallback) {
        this.mode = (mode == null) ? Mode.PASSIVE : mode;
        this.abortCallback = (abortCallback == null) ? e -> {} : abortCallback;
        this.drainCallback = (drainCallback == null) ? e -> {} : drainCallback;
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "heap-watchdog");
            t.setDaemon(true);
            return t;
        });
    }

    public synchronized void start() {
        if (started || stopped) return;
        started = true;
        log.info("[Iter4.4 HeapWatchdog] starting (mode={}, thresholds: WARN={}%, HIGH={}%, CRITICAL={}%, interval={}ms)",
                mode, (int)(WARN_FRAC * 100), (int)(HIGH_FRAC * 100),
                (int)(CRITICAL_FRAC * 100), SAMPLE_INTERVAL_MS);
        sampleFuture = scheduler.scheduleAtFixedRate(
                this::sampleOnce,
                SAMPLE_INTERVAL_MS, SAMPLE_INTERVAL_MS, TimeUnit.MILLISECONDS);
    }

    @Override
    public synchronized void close() { stop(); }

    public synchronized void stop() {
        if (stopped) return;
        stopped = true;
        if (sampleFuture != null) sampleFuture.cancel(false);
        scheduler.shutdown();
        try {
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        log.info("[Iter4.4 HeapWatchdog] stopped (last level: {})", lastLevel);
    }

    /** Pipeline calls this at major stage transitions so heap-pressure logs
     *  show which stage was active when pressure rose.  Cheap (single CAS). */
    public void setStage(String stage) {
        currentStage.set(stage == null ? "(unknown)" : stage);
    }

    public Level lastLevel() { return lastLevel; }

    /** One sample.  Updates {@link #lastLevel} and fires callbacks on level
     *  CROSSING only — not every sample. */
    private void sampleOnce() {
        if (stopped) return;
        long max = Runtime.getRuntime().maxMemory();
        long total = Runtime.getRuntime().totalMemory();
        long free = Runtime.getRuntime().freeMemory();
        long used = total - free;
        double frac = (double) used / Math.max(1L, max);

        Level newLevel;
        if      (frac >= CRITICAL_FRAC) newLevel = Level.CRITICAL;
        else if (frac >= HIGH_FRAC)     newLevel = Level.HIGH;
        else if (frac >= WARN_FRAC)     newLevel = Level.WARN;
        else                            newLevel = Level.NORMAL;

        if (newLevel == lastLevel) return;

        String pct = String.format("%.1f%%", frac * 100.0);
        HeapPressureEvent event = new HeapPressureEvent(
                newLevel, used, max, frac, currentStage.get());

        switch (newLevel) {
            case NORMAL:
                log.info("[Iter4.4 HeapWatchdog] heap pressure released → NORMAL ({} of {} = {}); stage='{}'",
                        formatBytes(used), formatBytes(max), pct, event.stage);
                break;
            case WARN:
                log.warn("[Iter4.4 HeapWatchdog] WARN → heap at {} of {} ({}); stage='{}'",
                        formatBytes(used), formatBytes(max), pct, event.stage);
                break;
            case HIGH:
                log.warn("[Iter4.4 HeapWatchdog] HIGH → heap at {} of {} ({}); stage='{}'",
                        formatBytes(used), formatBytes(max), pct, event.stage);
                if (mode == Mode.ABORT_ON_HIGH) {
                    log.error("[Iter4.4 HeapWatchdog] ABORT signal (forced-JAVA mode): "
                            + "heap crossed HIGH threshold; pipeline will abort at next checkpoint. "
                            + "Re-run with larger -Xmx or use core.precompute=auto.");
                    safelyInvoke(abortCallback, event, "abortCallback");
                }
                break;
            case CRITICAL:
                log.error("[Iter4.4 HeapWatchdog] CRITICAL → heap at {} of {} ({}); stage='{}'",
                        formatBytes(used), formatBytes(max), pct, event.stage);
                if (mode == Mode.DRAIN_ON_CRITICAL) {
                    log.error("[Iter4.4 HeapWatchdog] EMERGENCY DRAIN signal (AUTO-JAVA mode): "
                            + "would flush in-JVM intermediates to PG and switch remaining stages "
                            + "to DB mode.  Drain mechanism: not yet implemented as of Iter4.4 — "
                            + "bumping -Xmx is recommended.");
                    safelyInvoke(drainCallback, event, "drainCallback");
                } else if (mode == Mode.ABORT_ON_HIGH) {
                    // [Iter4.4 fix] If heap jumps directly from WARN/NORMAL to
                    // CRITICAL within one sample, we skipped over the HIGH bucket.
                    // Fire abort callback now — CRITICAL implies HIGH.
                    if (lastLevel != Level.HIGH) {
                        log.error("[Iter4.4 HeapWatchdog] ABORT signal (forced-JAVA mode): "
                                + "heap jumped past HIGH into CRITICAL; pipeline will abort at next checkpoint. "
                                + "Re-run with larger -Xmx or use core.precompute=auto.");
                        safelyInvoke(abortCallback, event, "abortCallback");
                    }
                }
                break;
        }
        lastLevel = newLevel;
    }

    private static void safelyInvoke(Consumer<HeapPressureEvent> cb,
                                     HeapPressureEvent event, String name) {
        try {
            cb.accept(event);
        } catch (Throwable t) {
            log.error("[Iter4.4 HeapWatchdog] {} threw: {}", name, t.toString(), t);
        }
    }

    private static String formatBytes(long b) {
        if (b < 0) return "n/a";
        if (b < 1024L) return b + " B";
        if (b < 1024L * 1024) return String.format("%.1f KB", b / 1024.0);
        if (b < 1024L * 1024 * 1024) return String.format("%.1f MB", b / (1024.0 * 1024));
        return String.format("%.2f GB", b / (1024.0 * 1024 * 1024));
    }
}
