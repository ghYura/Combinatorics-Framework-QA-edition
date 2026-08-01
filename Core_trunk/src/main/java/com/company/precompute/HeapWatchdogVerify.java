package com.company.precompute;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Iter4.4 verification harness — confirms the heap watchdog actually fires
 * level crossings under synthetic heap pressure.
 *
 * <p>Run with a small heap to make crossings observable, e.g.:
 * {@code java -Xmx256m -cp target/classes com.company.precompute.HeapWatchdogVerify}</p>
 *
 * <p>Allocates byte[] chunks into a List in a loop, sleeping briefly to give the
 * watchdog sample loop time to fire.  Stops automatically when CRITICAL is
 * reached OR after a hard cap (so it doesn't actually OOM the test harness).</p>
 */
public final class HeapWatchdogVerify {

    public static void main(String[] args) throws Exception {
        AtomicBoolean criticalSeen = new AtomicBoolean(false);
        AtomicBoolean highSeen = new AtomicBoolean(false);

        HeapWatchdog watchdog = new HeapWatchdog(
                HeapWatchdog.Mode.DRAIN_ON_CRITICAL,
                evt -> {
                    highSeen.set(true);
                    System.out.printf("[test] ABORT callback fired at level=%s used=%.1f%%%n",
                            evt.level, evt.fractionUsed * 100);
                },
                evt -> {
                    criticalSeen.set(true);
                    System.out.printf("[test] DRAIN callback fired at level=%s used=%.1f%%%n",
                            evt.level, evt.fractionUsed * 100);
                });

        watchdog.start();
        watchdog.setStage("synthetic-allocation-loop");

        long maxHeap = Runtime.getRuntime().maxMemory();
        System.out.printf("-Xmx = %d MB%n", maxHeap / (1024 * 1024));
        System.out.println("Allocating byte[] chunks until CRITICAL or hard cap reached…");

        List<byte[]> retain = new ArrayList<>();
        int chunkBytes = (int) Math.min(8 * 1024 * 1024, maxHeap / 64);  // ~8 MB / chunk, scaled down for tiny heaps
        long hardCap = (long) (maxHeap * 0.97);  // stop before OOM

        try {
            int allocated = 0;
            while (!criticalSeen.get()) {
                retain.add(new byte[chunkBytes]);
                allocated++;
                long used = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
                if (allocated % 4 == 0) {
                    System.out.printf("  allocated %d chunks (~%d MB heap used so far)%n",
                            allocated, used / (1024 * 1024));
                }
                if (used > hardCap) {
                    System.out.println("[test] hard cap reached — pausing 4s to let watchdog sample HIGH/CRITICAL");
                    Thread.sleep(4000);  // give watchdog at least one sample interval at the high mark
                    break;
                }
                // Sleep so the watchdog's 2.5 s sample loop catches the pressure rise.
                Thread.sleep(300);
            }
        } finally {
            // Release before stop() so log output isn't itself starved.
            retain.clear();
            System.gc();
            Thread.sleep(500);
            watchdog.stop();
        }

        System.out.println();
        System.out.printf("Summary: HIGH callback fired = %s,  CRITICAL callback fired = %s%n",
                highSeen.get(), criticalSeen.get());
        if (!criticalSeen.get() && !highSeen.get()) {
            System.out.println("WARN: neither callback fired — was -Xmx large enough vs chunk size?");
            System.exit(1);
        }
        System.out.println("OK");
    }
}
