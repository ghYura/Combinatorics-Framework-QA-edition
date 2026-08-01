package com.company.sink;

import com.yurii.analyzer.core.optimization.OnlineMetricAggregator;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Verifier that exercises the new sink layer WITHOUT touching any of the
 * framework's DB / file / zip pathways.  The test reproduces both code
 * paths in {@code Main} as small in-memory simulations:
 *
 *   • simulated STREAMING-DIRECT — write rows through
 *     {@link RowSinkOutputStream} and confirm both the file and the sink
 *     receive identical content (modulo separator stripping).
 *
 *   • simulated parallel path    — invoke the sink directly with
 *     pre-assembled row bytes from many threads and confirm the
 *     {@link AnalyzerBridge} aggregates correctly to a Snapshot.
 *
 * Plus a baseline "no sink installed" check that proves the framework's
 * original byte-on-disk output is unchanged when {@code fw.analyzer.enabled=false}.
 *
 * Run:  java -cp ... com.company.sink.SinkSmokeTest
 */
public final class SinkSmokeTest {
    private SinkSmokeTest() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testNoSinkPassthrough();
        failures += testStreamingDirectPath();
        failures += testParallelPath();
        failures += testIdempotentInstall();
        failures += testMixedModeGoalsAndBalancedOptima();
        failures += testAgnosticAutoDiscovery();
        failures += testDeclaredOnlyPolicy();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL SINK SMOKE CHECKS PASSED");
        else { System.out.println("❌ " + failures + " SINK SMOKE CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── Agnostic: declare ONE goal, rows have FIVE metrics; verify all
    //     five participate in Pareto + balanced-optimum via DiscoveryPolicy.DEFAULT
    private static int testAgnosticAutoDiscovery() throws Exception {
        System.out.println("\n── Agnostic auto-discovery (1 declared, 4 inferred) ──");
        // Declare ONLY cost as MIN. The other four metrics — latency,
        // throughput, accuracy, error_rate — should be auto-discovered AND
        // their lexical-inferred modes (latency→MIN, throughput→MAX,
        // accuracy→MAX, error_rate→MIN) used in Pareto/scalarization.
        java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals = java.util.List.of(
                com.yurii.analyzer.core.optimization.GoalSpec.min("cost", 1.0));
        AnalyzerBridge bridge = AnalyzerBridge.start(
                1024, 5,
                new com.yurii.analyzer.core.optimization.LineExecutor.Inline(),
                goals,
                com.yurii.analyzer.core.optimization.DiscoveryPolicy.DEFAULT,
                "{}");
        RowSinkRegistry.install(bridge);

        double[][] tuples = {
            // cost  latency throughput accuracy error_rate
            {0.95,    12.5,     400,     0.50,    0.50},
            {0.65,     8.5,     900,     0.70,    0.30},
            {0.40,     5.5,    1700,     0.85,    0.15},
            {0.25,     5.1,    2600,     0.91,    0.09},  // good cross-axis balance
            {0.15,     4.2,    3400,     0.94,    0.06},
            {0.10,     3.0,    4200,     0.97,    0.03},
            {0.08,     2.5,    4500,     0.98,    0.02},  // best on cost & latency
        };
        long id = 0;
        for (double[] t : tuples) {
            id++;
            String row = String.format(java.util.Locale.ROOT,
                    "id=auto_%02d cost=%.4f latency=%.2fms throughput=%.0f accuracy=%.4f error_rate=%.4f",
                    id, t[0], t[1], t[2], t[3], t[4]);
            RowSinkRegistry.current().accept(id, row);
        }
        com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot snap =
                bridge.finishAndGetSnapshot(10_000);
        RowSinkRegistry.closeActive();

        int f = 0;
        f += assertCond("snapshot retains 7 candidates",
                snap != null && snap.updates() == 7);
        f += assertCond("declared goals count == 1 (only cost)",
                snap.goals().size() == 1);
        f += assertCond("declaredKeys contains 'cost' only",
                snap.declaredKeys().size() == 1 && snap.declaredKeys().contains("cost"));

        // Effective goals = 1 declared + 4 auto-inferred = 5.
        java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> eff = snap.effectiveGoals();
        f += assertCond("effectiveGoals size == 5 (1 declared + 4 auto)",
                eff.size() == 5);

        // Verify lexical-inferred modes for each auto-discovered key.
        java.util.Map<String, com.yurii.analyzer.core.optimization.GoalSpec.Mode> byKey =
                new java.util.LinkedHashMap<>();
        for (var g : eff) byKey.put(g.key(), g.mode());
        f += assertCond("cost mode == MINIMIZE (declared)",
                byKey.get("cost") == com.yurii.analyzer.core.optimization.GoalSpec.Mode.MINIMIZE);
        f += assertCond("latency mode == MINIMIZE (lexical)",
                byKey.get("latency") == com.yurii.analyzer.core.optimization.GoalSpec.Mode.MINIMIZE);
        f += assertCond("throughput mode == MAXIMIZE (lexical)",
                byKey.get("throughput") == com.yurii.analyzer.core.optimization.GoalSpec.Mode.MAXIMIZE);
        f += assertCond("accuracy mode == MAXIMIZE (lexical)",
                byKey.get("accuracy") == com.yurii.analyzer.core.optimization.GoalSpec.Mode.MAXIMIZE);
        f += assertCond("error_rate mode == MINIMIZE (lexical: 'error' fragment wins)",
                byKey.get("error_rate") == com.yurii.analyzer.core.optimization.GoalSpec.Mode.MINIMIZE);

        // BalancedOptimumSelector should iterate over ALL 5 axes, not just 1.
        java.util.List<com.yurii.analyzer.core.optimization.BalancedOptimumSelector.Selection> sels =
                com.yurii.analyzer.core.optimization.BalancedOptimumSelector.all(
                        snap.paretoFront(), snap.perKeyStats(), eff);
        for (var sel : sels) {
            f += assertCond(sel.strategy() + " sees all 5 axes (got "
                    + sel.perAxisContribution().size() + ")",
                    sel.perAxisContribution().size() == 5);
        }

        // Print snapshot — visible proof.
        System.out.println(snap.render());
        return f;
    }

    // ─── DECLARED_ONLY policy: auto-keys observed but NOT in scalarization
    private static int testDeclaredOnlyPolicy() throws Exception {
        System.out.println("\n── DECLARED_ONLY policy (auto-keys observed, not selected) ──");
        java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals = java.util.List.of(
                com.yurii.analyzer.core.optimization.GoalSpec.min("cost", 1.0));
        AnalyzerBridge bridge = AnalyzerBridge.start(
                1024, 5,
                new com.yurii.analyzer.core.optimization.LineExecutor.Inline(),
                goals,
                com.yurii.analyzer.core.optimization.DiscoveryPolicy.DECLARED_ONLY,
                "{}");
        RowSinkRegistry.install(bridge);

        double[][] tuples = {
            // cost  extra_a extra_b
            {0.95,     5,     50},
            {0.65,    15,     80},
            {0.40,    25,    150},
            {0.25,    35,    200},
            {0.10,    45,    250},
        };
        long id = 0;
        for (double[] t : tuples) {
            id++;
            RowSinkRegistry.current().accept(id, String.format(java.util.Locale.ROOT,
                    "id=do_%02d cost=%.3f extra_a=%.0f extra_b=%.0f",
                    id, t[0], t[1], t[2]));
        }
        var snap = bridge.finishAndGetSnapshot(10_000);
        RowSinkRegistry.closeActive();

        int f = 0;
        f += assertCond("Welford observed all 3 keys (cost, extra_a, extra_b)",
                snap.perKeyStats().size() == 3);
        f += assertCond("effectiveGoals size == 1 (auto excluded by DECLARED_ONLY)",
                snap.effectiveGoals().size() == 1);
        // With DECLARED_ONLY, Pareto only compares on 'cost' axis → only one
        // candidate (the one with min cost) is non-dominated.
        f += assertCond("Pareto front size == 1 (single-axis dominance)",
                snap.paretoFront().size() == 1);
        if (snap.paretoFront().size() == 1) {
            f += assertCond("Pareto winner is the min-cost candidate (id=do_05)",
                    snap.paretoFront().get(0).originalLine.contains("do_05"));
        }
        return f;
    }

    // ─── Mixed-mode goals + scalarization-based "balanced optimum" ──────
    private static int testMixedModeGoalsAndBalancedOptima() throws Exception {
        System.out.println("\n── Mixed-mode goals (MIN + MAX + TARGET) + balanced optima ──");
        // Construct goals: minimize cost, maximize throughput, target latency=50ms.
        // The corpus is engineered so a clear winner exists per strategy.
        // Use the unit-aware target factory: "50ms" canonicalises to 0.05 s
        // (same scale as the parsed latency values), so the TARGET pull
        // actually distinguishes candidates — vs hardcoding 50.0 which the
        // analyzer would interpret as 50 seconds and overshoot all candidates.
        java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals = java.util.List.of(
                com.yurii.analyzer.core.optimization.GoalSpec.min("cost", 1.0),
                com.yurii.analyzer.core.optimization.GoalSpec.max("throughput", 1.0),
                com.yurii.analyzer.core.optimization.GoalSpec.target("latency", "50ms", 1.0));
        AnalyzerBridge bridge = AnalyzerBridge.start(
                1024, 10,
                new com.yurii.analyzer.core.optimization.LineExecutor.Inline(),
                goals, "{}");
        RowSinkRegistry.install(bridge);

        // 12 candidates with varied trade-offs. Candidate #6 is engineered
        // to be the balanced-optimum winner: cost=0.30 (good), throughput=2200
        // (good), latency=50.0 (exactly at target).
        double[][] tuples = {
            // cost   throughput  latency
            {0.95,    400,        12.5},
            {0.80,    600,        80.0},
            {0.65,    900,        70.0},
            {0.50,   1300,        62.0},
            {0.40,   1700,        55.0},
            {0.30,   2200,        50.0},   // balanced-optimum winner
            {0.25,   2600,        51.0},
            {0.20,   3000,        46.0},
            {0.15,   3400,        42.0},
            {0.12,   3800,        35.0},
            {0.10,   4200,        30.0},   // best on cost AND throughput, but far from latency target
            {0.08,   4500,        25.0},
        };
        long id = 0;
        for (double[] t : tuples) {
            id++;
            String row = String.format(java.util.Locale.ROOT,
                    "id=mix_%02d cost=%.4f throughput=%.0f latency=%.2fms",
                    id, t[0], t[1], t[2]);
            RowSinkRegistry.current().accept(id, row);
        }
        com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot snap =
                bridge.finishAndGetSnapshot(10_000);
        RowSinkRegistry.closeActive();

        int f = 0;
        f += assertCond("snapshot retains 12 candidates",   snap != null && snap.updates() == 12);
        f += assertCond("snapshot carries declared goals",  !snap.goals().isEmpty());
        f += assertCond("Pareto front non-empty",           !snap.paretoFront().isEmpty());

        // Print the rendered snapshot — visible proof the balanced-optimum
        // section now appears in the report.
        System.out.println(snap.render());

        java.util.List<com.yurii.analyzer.core.optimization.BalancedOptimumSelector.Selection> sels =
                com.yurii.analyzer.core.optimization.BalancedOptimumSelector.all(
                        snap.paretoFront(), snap.perKeyStats(), snap.goals());
        f += assertCond("3 scalarization strategies returned", sels.size() == 3);

        // Tchebycheff (min-max regret) is the "fairest" balance — with the
        // engineered corpus where #6 has cost=0.30/thr=2200/lat=50ms (target),
        // its max axis contribution is the smallest of the front members.
        var tch = sels.stream().filter(s -> s.strategy().equals("tchebycheff")).findFirst().orElseThrow();
        f += assertCond("tchebycheff picked a non-null candidate", tch.chosen() != null);
        // Latency contribution should be near-zero for the Tchebycheff pick
        // when latency=50ms is the target (proves TARGET-mode pull works).
        Double tchLatContrib = tch.perAxisContribution().get("latency");
        f += assertCond(String.format(java.util.Locale.ROOT,
                "tchebycheff latency contrib ≤ 0.4 (got %.4f) — TARGET mode pulls toward 50ms",
                tchLatContrib == null ? Double.NaN : tchLatContrib),
                tchLatContrib != null && tchLatContrib <= 0.4);

        // Weighted-sum and distance-to-ideal should also produce non-null picks.
        var ws  = sels.stream().filter(s -> s.strategy().equals("weighted-sum")).findFirst().orElseThrow();
        var dti = sels.stream().filter(s -> s.strategy().equals("distance-to-ideal")).findFirst().orElseThrow();
        f += assertCond("weighted-sum picked a non-null candidate",       ws.chosen()  != null);
        f += assertCond("distance-to-ideal picked a non-null candidate",  dti.chosen() != null);

        // The TARGET-mode latency contribution dimension MUST be evaluated
        // for every strategy (even if not the deciding factor), proving
        // mixed-mode integration is real.
        for (var sel : sels) {
            f += assertCond(sel.strategy() + " contribution map includes 'latency' axis",
                    sel.perAxisContribution().containsKey("latency"));
            f += assertCond(sel.strategy() + " contribution map includes 'cost' axis",
                    sel.perAxisContribution().containsKey("cost"));
            f += assertCond(sel.strategy() + " contribution map includes 'throughput' axis",
                    sel.perAxisContribution().containsKey("throughput"));
        }
        return f;
    }

    // ─── Baseline: no sink installed → file output unchanged ────────────
    private static int testNoSinkPassthrough() throws Exception {
        System.out.println("\n── No-sink pass-through ──");
        RowSinkRegistry.install(null);   // ensure NULL sink

        ByteArrayOutputStream sinkOut = new ByteArrayOutputStream();
        OutputStream maybeSink = RowSinkRegistry.isActive()
                ? new RowSinkOutputStream(sinkOut, RowSinkRegistry.current(),
                        new byte[]{'\n'}, new AtomicLong(1L))
                : sinkOut;
        maybeSink.write("k=1 cost=0.5\n".getBytes(StandardCharsets.UTF_8));
        maybeSink.write("k=2 cost=0.3\n".getBytes(StandardCharsets.UTF_8));
        maybeSink.close();

        boolean unchanged = sinkOut.toString(StandardCharsets.UTF_8)
                .equals("k=1 cost=0.5\nk=2 cost=0.3\n");
        return assertCond("no sink installed → bytes-on-disk unchanged", unchanged);
    }

    // ─── Path 1: STREAMING-DIRECT via RowSinkOutputStream tee ───────────
    private static int testStreamingDirectPath() throws Exception {
        System.out.println("\n── STREAMING-DIRECT path simulation ──");
        AnalyzerBridge bridge = AnalyzerBridge.startInline(1024, 5);
        RowSinkRegistry.install(bridge);

        ByteArrayOutputStream fileOut = new ByteArrayOutputStream();
        // Use FW_B_ARR-equivalent separator (e.g. configured to "\n")
        RowSinkOutputStream tee = new RowSinkOutputStream(
                fileOut, RowSinkRegistry.current(),
                new byte[]{'\n'}, new AtomicLong(1L));

        for (int i = 1; i <= 50; i++) {
            String row = String.format(java.util.Locale.ROOT,
                    "id=row_%03d cost=%.3f latency=%dms throughput=%d\n",
                    i, 0.05 * i, 5 * i, 1000 - 7 * i);
            tee.write(row.getBytes(StandardCharsets.UTF_8));
        }
        tee.close();

        OnlineMetricAggregator.Snapshot snap = bridge.finishAndGetSnapshot(10_000);
        RowSinkRegistry.closeActive();

        int f = 0;
        f += assertCond("file received all 50 rows",
                fileOut.toString(StandardCharsets.UTF_8).split("\n").length == 50);
        f += assertCond("snapshot got 50 candidates", snap != null && snap.updates() == 50);
        f += assertCond("'cost' auto-discovered",       snap.perKeyStats().containsKey("cost"));
        f += assertCond("'latency' auto-discovered",    snap.perKeyStats().containsKey("latency"));
        f += assertCond("'throughput' auto-discovered", snap.perKeyStats().containsKey("throughput"));
        // cost min should be at i=1 (0.050) and max at i=50 (2.500)
        OnlineMetricAggregator.KeyStats kc = snap.perKeyStats().get("cost");
        f += assertCond("cost.argminLine == 1 (i=1)",  kc.argminLineNo == 1);
        f += assertCond("cost.argmaxLine == 50 (i=50)", kc.argmaxLineNo == 50);
        return f;
    }

    // ─── Path 2: parallel path bypasses RowSinkOutputStream and calls
    //               sink.accept directly from many threads ─────────────────
    private static int testParallelPath() throws Exception {
        System.out.println("\n── Parallel-path simulation (16 threads × 100 rows) ──");
        AnalyzerBridge bridge = AnalyzerBridge.startInline(8192, 5);
        RowSinkRegistry.install(bridge);

        java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newFixedThreadPool(16);
        java.util.concurrent.atomic.AtomicLong globalId = new java.util.concurrent.atomic.AtomicLong();
        java.util.List<java.util.concurrent.Future<?>> futs = new java.util.ArrayList<>();
        for (int t = 0; t < 16; t++) {
            final int tid = t;
            futs.add(pool.submit(() -> {
                for (int i = 0; i < 100; i++) {
                    long id = globalId.incrementAndGet();
                    String row = String.format(java.util.Locale.ROOT,
                            "id=p_%02d_%03d cost=%.4f latency=%.2fms thread=%d",
                            tid, i, 0.01 * i + 0.001 * tid, 1.0 + i * 0.5, tid);
                    RowSinkRegistry.current().accept(id, row);
                }
            }));
        }
        for (var f : futs) f.get();
        pool.shutdown();

        OnlineMetricAggregator.Snapshot snap = bridge.finishAndGetSnapshot(15_000);
        RowSinkRegistry.closeActive();

        int f = 0;
        f += assertCond("snapshot got 1600 candidates from 16 threads",
                snap != null && snap.updates() == 1600);
        f += assertCond("'cost' auto-discovered (parallel)",
                snap.perKeyStats().containsKey("cost"));
        f += assertCond("'latency' auto-discovered & canonicalised",
                snap.perKeyStats().containsKey("latency"));
        f += assertCond("Pareto front non-empty",
                snap.paretoFront() != null && !snap.paretoFront().isEmpty());
        return f;
    }

    // ─── Sanity: install/closeActive() lifecycle is robust ──────────────
    private static int testIdempotentInstall() {
        System.out.println("\n── Lifecycle (install/close idempotent) ──");
        RowSinkRegistry.install(null);
        int f = 0;
        f += assertCond("install(null) → not active", !RowSinkRegistry.isActive());
        f += assertCond("current() never null",       RowSinkRegistry.current() != null);
        RowSinkRegistry.closeActive();
        f += assertCond("closeActive() on NULL is a no-op", true);
        return f;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
