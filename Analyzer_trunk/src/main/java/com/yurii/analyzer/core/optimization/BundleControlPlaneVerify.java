package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.optimization.BundleControlPlane.Candidate;
import com.yurii.analyzer.core.optimization.BundleControlPlane.Config;
import com.yurii.analyzer.core.optimization.BundleControlPlane.MetricSensitivity;
import com.yurii.analyzer.core.optimization.BundleControlPlane.Outcome;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RepeatPolicy;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RunResult;
import com.yurii.analyzer.core.optimization.BundleControlPlane.UnitExecutor;
import com.yurii.analyzer.core.optimization.BundleControlPlane.UnitResult;
import com.yurii.analyzer.core.optimization.BundleControlPlane.WorkUnit;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Plan-2 verifier: drives {@link BundleControlPlane} the way
 * {@link RemoteWorkerVerify} drives RemoteWorker — no live Postgres / Executor
 * pool needed.  Covers the acceptance gates of Plan-2 §P2.5 that are provable on
 * a single host with stub executors:
 *
 * <ul>
 *   <li><b>Assignment</b> (disperse / local / nested): correct unit counts,
 *       balanced env multisets, and unique {@code (candidate, repeat_idx,
 *       env_id)} identity per unit.</li>
 *   <li><b>Parity</b>: K=1 / local / single-env through the control plane yields
 *       the same per-candidate corpus as a sequential RemoteWorker loop.</li>
 *   <li><b>Backpressure</b>: observed max in-flight never exceeds, and saturates,
 *       {@code maxInFlight}.</li>
 *   <li><b>Per-host serialization</b>: with {@code serializePerHost}, max
 *       concurrency per env is 1, while distinct envs still run in parallel.</li>
 *   <li><b>Budget / cancel</b>: a deadline (and an explicit {@code cancel()})
 *       stops dispatch and interrupts in-flight units promptly, with a complete
 *       result corpus.</li>
 * </ul>
 *
 * The genuine multi-environment SCALE / no-JDBC-pinning gates need a real
 * multi-instance Executor pool + JFR run; see the ADR (doc 25).  Those are infra,
 * not code — this verifier exercises the orchestration machinery itself.
 *
 *   Run:  java -cp ... com.yurii.analyzer.core.optimization.BundleControlPlaneVerify
 */
public final class BundleControlPlaneVerify {
    private BundleControlPlaneVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testLocalAssignment();
        failures += testDisperseAssignmentBalanced();
        failures += testNestedAssignment();
        failures += testIdentityUniqueAllPolicies();
        failures += testK1ParityVsSequentialRemoteWorker();
        failures += testBackpressureCap();
        failures += testPerHostSerialization();
        failures += testBudgetDeadlineCancels();
        failures += testExplicitCancel();
        failures += testDispatchToAggregationJoin();
        failures += testMetricSensitivitySerialization();
        failures += testRepeatEnvJdbcPollerSql();
        failures += testPlanJsonRoundTrip();
        failures += testNestedCrossEnvDecomposition();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL CONTROL-PLANE CHECKS PASSED");
        else { System.out.println("❌ " + failures + " CONTROL-PLANE CHECK(S) FAILED"); System.exit(1); }
    }

    // ---------------------------------------------------------- assignment

    private static int testLocalAssignment() {
        System.out.println("── local: K repeats per candidate pinned to one env ──");
        Config cfg = new Config(RepeatPolicy.LOCAL, 2, List.of("a", "b"), 64, false, 0);
        BundleControlPlane cp = new BundleControlPlane(cfg);
        List<WorkUnit> u = cp.planUnits(cands(3));
        int f = 0;
        f += assertCond("local: 3 candidates × K2 = 6 units", u.size() == 6);
        f += assertCond("local: candidate 1's two repeats share one env",
                envsOf(u, "1").size() == 1);
        f += assertCond("local: candidates round-robin across the pool (a,b,a)",
                envOf(u, "1").equals("a") && envOf(u, "2").equals("b") && envOf(u, "3").equals("a"));
        f += assertCond("local: repeat_idx is 0..K-1 within the candidate",
                repeatIdxsOf(u, "1").equals(Set.of(0, 1)));
        return f;
    }

    private static int testDisperseAssignmentBalanced() {
        System.out.println("\n── disperse: K repeats scattered, balanced across envs ──");
        // K == E: every candidate must see each env exactly once.
        Config cfgKE = new Config(RepeatPolicy.DISPERSE, 2, List.of("a", "b"), 64, false, 0);
        List<WorkUnit> u = new BundleControlPlane(cfgKE).planUnits(cands(4));
        int f = 0;
        f += assertCond("disperse: 4 candidates × K2 = 8 units", u.size() == 8);
        boolean eachSeesAll = true;
        for (int c = 1; c <= 4; c++) if (!envMultiset(u, String.valueOf(c)).keySet().equals(Set.of("a", "b"))) eachSeesAll = false;
        f += assertCond("disperse(K==E): every candidate sees each env exactly once", eachSeesAll);
        f += assertCond("disperse: global env load balanced (a:4, b:4)",
                count(u, "a") == 4 && count(u, "b") == 4);

        // K = 2·E: every candidate must see each env exactly K/E = 2 times.
        Config cfg2 = new Config(RepeatPolicy.DISPERSE, 4, List.of("a", "b"), 64, false, 0);
        List<WorkUnit> u2 = new BundleControlPlane(cfg2).planUnits(cands(2));
        boolean balanced = true;
        for (int c = 1; c <= 2; c++) {
            Map<String, Integer> m = envMultiset(u2, String.valueOf(c));
            if (!(Integer.valueOf(2).equals(m.get("a")) && Integer.valueOf(2).equals(m.get("b")))) balanced = false;
        }
        f += assertCond("disperse(K=2E): every candidate sees each env exactly K/E=2 times", balanced);
        return f;
    }

    private static int testNestedAssignment() {
        System.out.println("\n── nested: K repeats on EACH of E envs ──");
        Config cfg = new Config(RepeatPolicy.NESTED, 3, List.of("a", "b"), 64, false, 0);
        List<WorkUnit> u = new BundleControlPlane(cfg).planUnits(cands(2));
        int f = 0;
        f += assertCond("nested: 2 cand × E2 × K3 = 12 units", u.size() == 12);
        f += assertCond("nested: candidate 1 runs on both envs",
                envsOf(u, "1").equals(Set.of("a", "b")));
        f += assertCond("nested: candidate 1 has K=3 samples on env 'a'",
                Integer.valueOf(3).equals(envMultiset(u, "1").get("a")));
        return f;
    }

    private static int testIdentityUniqueAllPolicies() {
        System.out.println("\n── identity: (candidate, repeat_idx, env) unique per unit (Plan-1 5-col key) ──");
        int f = 0;
        for (RepeatPolicy p : RepeatPolicy.values()) {
            Config cfg = new Config(p, 3, List.of("a", "b", "c"), 64, false, 0);
            List<WorkUnit> u = new BundleControlPlane(cfg).planUnits(cands(5));
            Set<String> ids = new HashSet<>();
            boolean unique = true;
            for (WorkUnit w : u) if (!ids.add(w.candidateId() + "#" + w.repeatIdx() + "#" + w.envId())) unique = false;
            f += assertCond(p + ": all " + u.size() + " units have a unique (cand,repeat,env) identity", unique);
        }
        return f;
    }

    // ------------------------------------------------------------- parity

    private static int testK1ParityVsSequentialRemoteWorker() throws Exception {
        System.out.println("\n── parity: control plane (K=1/local/1-env) == sequential RemoteWorker ──");
        Map<String, Map<String, String>> rows = new HashMap<>();
        for (int i = 1; i <= 6; i++) {
            Map<String, String> r = new LinkedHashMap<>();
            r.put("fw_var", String.valueOf(i % 2));
            r.put("score", String.format(java.util.Locale.ROOT, "0.%02d", i));
            rows.put(String.valueOf(i), r);
        }
        LineExecutor.RemoteWorker.ResultPoller poller = id -> rows.get(id);
        List<Candidate> candidates = cands(6);

        // Reference: a single sequential RemoteWorker loop (today's behaviour).
        Path seqDir = Files.createTempDirectory("cp_seq_");
        LineExecutor.RemoteWorker seq = new LineExecutor.RemoteWorker.Builder()
                .srcDir(seqDir).poller(poller).pollIntervalMs(10).timeoutSeconds(2.0).build();
        Map<String, String> sequential = new LinkedHashMap<>();
        for (Candidate c : candidates) sequential.put(c.candidateId(), seq.execute(c.lineNo(), c.raw()));

        // Control plane: K=1, local, one env — should reproduce it exactly.
        Path cpDir = Files.createTempDirectory("cp_par_");
        UnitExecutor exec = BundleControlPlane.remoteWorkerExecutor(
                Map.of("", cpDir), poller, 10, 2.0);
        Config cfg = new Config(RepeatPolicy.LOCAL, 1, List.of(""), 32, false, 0);
        RunResult rr = new BundleControlPlane(cfg).run(candidates, exec);
        Map<String, String> viaPlane = new LinkedHashMap<>();
        for (UnitResult u : rr.results()) viaPlane.put(u.unit().candidateId(), u.output());

        int f = 0;
        f += assertCond("parity: same candidate set", viaPlane.keySet().equals(sequential.keySet()));
        f += assertCond("parity: every candidate's metric text is byte-identical",
                viaPlane.equals(sequential));
        f += assertCond("parity: all 6 units COMPLETED", rr.stats().completed() == 6);
        cleanup(seqDir); cleanup(cpDir);
        return f;
    }

    // -------------------------------------------------------- backpressure

    private static int testBackpressureCap() {
        System.out.println("\n── backpressure: observed in-flight ≤ and saturates maxInFlight ──");
        int maxInFlight = 4;
        Config cfg = new Config(RepeatPolicy.LOCAL, 1, List.of(""), maxInFlight, false, 0);
        UnitExecutor sleeper = u -> { Thread.sleep(40); return "remote_id=" + u.candidateId() + " ok=1"; };
        RunResult rr = new BundleControlPlane(cfg).run(cands(20), sleeper);
        int f = 0;
        f += assertCond("backpressure: maxInFlightObserved ≤ cap (" + maxInFlight + ")",
                rr.stats().maxInFlightObserved() <= maxInFlight);
        f += assertCond("backpressure: cap is actually saturated (== " + maxInFlight + ")",
                rr.stats().maxInFlightObserved() == maxInFlight);
        f += assertCond("backpressure: all 20 units completed", rr.stats().completed() == 20);
        f += assertCond("backpressure: throttling stretched wall-clock (≥150 ms for 20×40ms/4)",
                rr.stats().elapsedMillis() >= 150);
        return f;
    }

    // -------------------------------------------------- per-host serialization

    private static int testPerHostSerialization() {
        System.out.println("\n── per-host serialization: 1 candidate/host at a time, hosts parallel ──");
        UnitExecutor sleeper = u -> { Thread.sleep(30); return "remote_id=" + u.candidateId() + " ok=1"; };
        // nested: 2 cand × 2 env × K3 = 12 units, 6 per env.
        Config serial = new Config(RepeatPolicy.NESTED, 3, List.of("h1", "h2"), 12, true, 0);
        RunResult rs = new BundleControlPlane(serial).run(cands(2), sleeper);
        int f = 0;
        f += assertCond("serialized: max concurrency on h1 == 1",
                Integer.valueOf(1).equals(rs.stats().maxPerEnvObserved().get("h1")));
        f += assertCond("serialized: max concurrency on h2 == 1",
                Integer.valueOf(1).equals(rs.stats().maxPerEnvObserved().get("h2")));
        f += assertCond("serialized: the two hosts still ran in parallel (global in-flight == 2)",
                rs.stats().maxInFlightObserved() == 2);
        f += assertCond("serialized: all 12 units completed", rs.stats().completed() == 12);

        // Contrast: without per-host serialization, a host runs many at once.
        Config wide = new Config(RepeatPolicy.NESTED, 3, List.of("h1", "h2"), 12, false, 0);
        RunResult rw = new BundleControlPlane(wide).run(cands(2), sleeper);
        int maxAnyEnv = Math.max(rw.stats().maxPerEnvObserved().get("h1"),
                                 rw.stats().maxPerEnvObserved().get("h2"));
        f += assertCond("contrast: without serialization a host overlaps (>1 concurrent)", maxAnyEnv > 1);
        return f;
    }

    // ------------------------------------------------------- budget / cancel

    private static int testBudgetDeadlineCancels() {
        System.out.println("\n── budget: deadline interrupts in-flight units, corpus stays complete ──");
        // 5 s per unit, but a 150 ms budget — the deadline must cut it short.
        Config cfg = new Config(RepeatPolicy.LOCAL, 1, List.of(""), 10, false, 150);
        UnitExecutor slow = u -> { Thread.sleep(5000); return "remote_id=" + u.candidateId() + " ok=1"; };
        long t0 = System.nanoTime();
        RunResult rr = new BundleControlPlane(cfg).run(cands(10), slow);
        long elapsed = (System.nanoTime() - t0) / 1_000_000L;
        int f = 0;
        f += assertCond("budget: returned well before the 5 s unit work (≤ 3 s)", elapsed <= 3000);
        f += assertCond("budget: no unit completed within the 150 ms budget", rr.stats().completed() == 0);
        f += assertCond("budget: every unit accounted for (10 results)", rr.results().size() == 10);
        f += assertCond("budget: all 10 units cancelled/timed-out",
                rr.stats().cancelled() + rr.stats().timedOut() == 10);
        return f;
    }

    private static int testExplicitCancel() {
        System.out.println("\n── cancel(): external stop interrupts in-flight units promptly ──");
        Config cfg = new Config(RepeatPolicy.LOCAL, 1, List.of(""), 10, false, 0);
        UnitExecutor slow = u -> { Thread.sleep(5000); return "remote_id=" + u.candidateId() + " ok=1"; };
        BundleControlPlane cp = new BundleControlPlane(cfg);
        Thread.ofVirtual().name("canceller").start(() -> {
            try { Thread.sleep(120); } catch (InterruptedException ignored) {}
            cp.cancel();
        });
        long t0 = System.nanoTime();
        RunResult rr = cp.run(cands(10), slow);
        long elapsed = (System.nanoTime() - t0) / 1_000_000L;
        int f = 0;
        f += assertCond("cancel: returned promptly after cancel() (≤ 3 s)", elapsed <= 3000);
        f += assertCond("cancel: nothing completed", rr.stats().completed() == 0);
        f += assertCond("cancel: complete corpus of 10 results", rr.results().size() == 10);
        f += assertCond("cancel: units recorded as cancelled",
                rr.stats().cancelled() + rr.stats().timedOut() == 10);
        return f;
    }

    // -------------------------------------------------- dispatch → aggregation

    private static int testDispatchToAggregationJoin() {
        System.out.println("\n── join: fanned-out K-repeat campaign → repeat-aware aggregate ──");
        final int K = 3;
        Config cfg = new Config(RepeatPolicy.LOCAL, K, List.of("e1"), 32, false, 0);
        // lat = candidateId*100 + repeat_idx*10  → cand 1: {100,110,120} median 110, etc.
        UnitExecutor exec = u -> "remote_id=" + u.candidateId() + " lat="
                + (Integer.parseInt(u.candidateId()) * 100 + u.repeatIdx() * 10);
        RunResult rr = new BundleControlPlane(cfg).run(cands(4), exec);

        List<String> cpCorpus = BundleControlPlane.toAggregatorCorpus(rr);
        Set<String> expectedCorpus = new HashSet<>();
        for (int c = 1; c <= 4; c++)
            for (int r = 0; r < K; r++)
                expectedCorpus.add("candidate_id=" + c + " repeat_idx=" + r + " env_id=e1 lat=" + (c * 100 + r * 10));

        int f = 0;
        f += assertCond("join: corpus has C·K = 12 lines", cpCorpus.size() == 12);
        f += assertCond("join: no RemoteWorker envelope token leaked into the corpus",
                cpCorpus.stream().noneMatch(l -> l.contains("remote_id=") || l.contains("remote_status=")));
        f += assertCond("join: control-plane corpus == expected (candidate,repeat,env,metric)",
                new HashSet<>(cpCorpus).equals(expectedCorpus));

        List<GoalSpec> goals = List.of(GoalSpec.min("lat", 1.0));
        Map<String, RepeatAggregator.CandidateAggregate> viaPlane = BundleControlPlane.aggregate(rr, goals);
        Map<String, RepeatAggregator.CandidateAggregate> direct =
                RepeatAggregator.aggregate(new ArrayList<>(expectedCorpus), goals);
        f += assertCond("join: aggregated candidate set matches direct aggregation",
                viaPlane.keySet().equals(direct.keySet()));
        boolean statsMatch = true, counts = true;
        for (String c : direct.keySet()) {
            RepeatAggregator.MetricStat a = viaPlane.get(c).objective().get("lat");
            RepeatAggregator.MetricStat b = direct.get(c).objective().get("lat");
            if (a == null || b == null || a.median() != b.median()
                    || a.ciLow() != b.ciLow() || a.ciHigh() != b.ciHigh()) statsMatch = false;
            if (viaPlane.get(c).sampleCount() != K) counts = false;
        }
        f += assertCond("join: per-candidate median + order-statistic CI match direct aggregation", statsMatch);
        f += assertCond("join: every candidate aggregated K=3 samples", counts);
        RepeatAggregator.MetricStat c1 = viaPlane.get("1").objective().get("lat");
        f += assertCond("join: candidate 1 median 110, order-statistic CI [100,120]",
                c1.median() == 110.0 && c1.ciLow() == 100.0 && c1.ciHigh() == 120.0);
        return f;
    }

    private static int testMetricSensitivitySerialization() {
        System.out.println("\n── metric type drives per-host serialization ──");
        int f = 0;
        f += assertCond("noisy ⇒ serialize per host",
                BundleControlPlane.serializePerHostFor(MetricSensitivity.NOISY));
        f += assertCond("deterministic ⇒ fan out (no per-host serialization)",
                !BundleControlPlane.serializePerHostFor(MetricSensitivity.DETERMINISTIC));
        f += assertCond("Config.forMetric(NOISY) sets serializePerHost",
                Config.forMetric(RepeatPolicy.LOCAL, 2, List.of("h1"), 8, MetricSensitivity.NOISY, 0).serializePerHost());
        f += assertCond("Config.forMetric(DETERMINISTIC) leaves it off",
                !Config.forMetric(RepeatPolicy.LOCAL, 2, List.of("h1"), 8, MetricSensitivity.DETERMINISTIC, 0).serializePerHost());
        f += assertCond("fromProperties: metricSensitivity=noisy ⇒ serialize",
                Config.fromProperties(Map.of("fw.controlplane.metricSensitivity", "noisy")).serializePerHost());
        f += assertCond("fromProperties: explicit serializePerHost=false overrides metricSensitivity=noisy",
                !Config.fromProperties(Map.of("fw.controlplane.metricSensitivity", "noisy",
                        "fw.controlplane.serializePerHost", "false")).serializePerHost());
        f += assertCond("metricSensitivityFrom aliases (latency⇒NOISY, verdict⇒DETERMINISTIC)",
                BundleControlPlane.metricSensitivityFrom("latency") == MetricSensitivity.NOISY
                        && BundleControlPlane.metricSensitivityFrom("verdict") == MetricSensitivity.DETERMINISTIC);
        return f;
    }

    // ----------------------------------------------- repeat/env JDBC + plan JSON

    private static int testRepeatEnvJdbcPollerSql() {
        System.out.println("\n── repeat/env-aware JDBC poll: SQL keyed by (candidate_id, repeat_idx, env_id) ──");
        int f = 0;
        String sql = BundleControlPlane.RepeatEnvJdbcPoller.buildSelectSql(
                "results_v2", "candidate_id", "repeat_idx", "env_id", List.of("fw_var", "lat"));
        f += assertCond("SQL: quoted cols + 3-key WHERE + LIMIT 1",
                sql.equals("SELECT \"fw_var\", \"lat\" FROM \"results_v2\" "
                        + "WHERE \"candidate_id\" = ? AND \"repeat_idx\" = ? AND \"env_id\" = ? LIMIT 1"));
        String sql2 = BundleControlPlane.RepeatEnvJdbcPoller.buildSelectSql(
                "\"results_v2\"", "candidate_id", "repeat_idx", "env_id", List.of("\"fw_optJ\""));
        f += assertCond("SQL: already-quoted identifiers are not double-quoted (preserves mixed-case fw_optJ)",
                sql2.equals("SELECT \"fw_optJ\" FROM \"results_v2\" "
                        + "WHERE \"candidate_id\" = ? AND \"repeat_idx\" = ? AND \"env_id\" = ? LIMIT 1"));
        return f;
    }

    private static int testPlanJsonRoundTrip() throws Exception {
        System.out.println("\n── plan JSON: Python→Java ingest + expanded-plan emit ──");
        String json = "{\"policy\":\"nested\",\"repeatK\":2,\"envs\":[\"a\",\"b\"],"
                + "\"maxInFlight\":16,\"metricSensitivity\":\"noisy\","
                + "\"candidates\":[{\"lineNo\":1,\"candidateId\":\"1\",\"raw\":\"x\"},"
                + "{\"lineNo\":2,\"candidateId\":\"2\",\"raw\":\"y\"}]}";
        BundleControlPlane.Plan plan = BundleControlPlane.Plan.fromJson(json);
        int f = 0;
        f += assertCond("ingest: policy=nested, K=2, envs=[a,b], maxInFlight=16",
                plan.config().policy() == RepeatPolicy.NESTED && plan.config().repeatK() == 2
                        && plan.config().envs().equals(List.of("a", "b")) && plan.config().maxInFlight() == 16);
        f += assertCond("ingest: metricSensitivity=noisy ⇒ serializePerHost", plan.config().serializePerHost());
        f += assertCond("ingest: 2 candidates parsed", plan.candidates().size() == 2);

        List<WorkUnit> units = new BundleControlPlane(plan.config()).planUnits(plan.candidates());
        f += assertCond("plan expands to C·E·K = 2·2·2 = 8 units (nested)", units.size() == 8);

        String emitted = BundleControlPlane.unitsToJson(plan.config(), units);
        var back = new com.fasterxml.jackson.databind.ObjectMapper().readTree(emitted);
        f += assertCond("emit: plannedUnits/executions = 8, units array has 8 entries",
                back.get("plannedUnits").asInt() == 8 && back.get("executions").asInt() == 8
                        && back.get("units").size() == 8);
        f += assertCond("ingest: empty/partial plan is tolerated (no candidates)",
                BundleControlPlane.Plan.fromJson("{\"candidates\":[]}").candidates().isEmpty());
        return f;
    }

    // -------------------------------------------------- cross-env (§12)

    private static int testNestedCrossEnvDecomposition() {
        System.out.println("\n── cross-env (§12): nested between-env vs within-env decomposition ──");
        Config cfg = new Config(RepeatPolicy.NESTED, 4, List.of("a", "b", "c"), 16, false, 0);
        // candidate 1 is env-sensitive (per-env base differs); candidate 2 is not.
        UnitExecutor exec = u -> {
            int cand = Integer.parseInt(u.candidateId());
            double base;
            if (cand == 1) {
                base = switch (u.envId()) { case "a" -> 100; case "b" -> 200; case "c" -> 150; default -> 0; };
            } else {
                base = 100;
            }
            return "remote_id=" + u.candidateId() + " lat=" + (base + u.repeatIdx());
        };
        var nested = BundleControlPlane.aggregateNested(
                new BundleControlPlane(cfg).run(cands(2), exec), List.of(GoalSpec.min("lat", 1.0)));
        int f = 0;
        f += assertCond("nested: both candidates aggregated", nested.keySet().equals(Set.of("1", "2")));
        var c1 = nested.get("1");
        f += assertCond("nested: candidate 1 across E=3 envs, E·K=12 samples",
                c1.envCount() == 3 && c1.totalSamples() == 12);
        var s1 = c1.objective().get("lat");
        f += assertCond("nested: grandMedian = median of per-env medians = 151.5", s1.grandMedian() == 151.5);
        f += assertCond("nested: between-env range = 201.5−101.5 = 100.0", s1.betweenEnvRange() == 100.0);
        f += assertCond("nested: within-env median range = 3.0 (each env spans 4 reps)",
                s1.withinEnvMedianRange() == 3.0);
        f += assertCond("nested: candidate 1 is env-sensitive (between ≫ within)", s1.envSensitive());
        f += assertCond("nested: 3 per-env medians recorded", s1.perEnvMedians().size() == 3);
        var s2 = nested.get("2").objective().get("lat");
        f += assertCond("nested: candidate 2 (env-insensitive) between-env range == 0", s2.betweenEnvRange() == 0.0);
        f += assertCond("nested: candidate 2 NOT env-sensitive", !s2.envSensitive());
        return f;
    }

    // ---------------------------------------------------------------- helpers

    private static List<Candidate> cands(int n) {
        List<Candidate> out = new ArrayList<>();
        for (int i = 1; i <= n; i++) out.add(new Candidate(i, String.valueOf(i), "candidate " + i));
        return out;
    }

    private static Set<String> envsOf(List<WorkUnit> u, String cand) {
        Set<String> s = new HashSet<>();
        for (WorkUnit w : u) if (w.candidateId().equals(cand)) s.add(w.envId());
        return s;
    }
    private static String envOf(List<WorkUnit> u, String cand) {
        for (WorkUnit w : u) if (w.candidateId().equals(cand)) return w.envId();
        return null;
    }
    private static Set<Integer> repeatIdxsOf(List<WorkUnit> u, String cand) {
        Set<Integer> s = new HashSet<>();
        for (WorkUnit w : u) if (w.candidateId().equals(cand)) s.add(w.repeatIdx());
        return s;
    }
    private static Map<String, Integer> envMultiset(List<WorkUnit> u, String cand) {
        Map<String, Integer> m = new LinkedHashMap<>();
        for (WorkUnit w : u) if (w.candidateId().equals(cand)) m.merge(w.envId(), 1, Integer::sum);
        return m;
    }
    private static long count(List<WorkUnit> u, String env) {
        return u.stream().filter(w -> w.envId().equals(env)).count();
    }

    private static void cleanup(Path dir) {
        try {
            if (dir == null || !Files.exists(dir)) return;
            try (var s = Files.walk(dir)) {
                s.sorted(java.util.Comparator.reverseOrder())
                        .forEach(p -> { try { Files.deleteIfExists(p); } catch (Exception ignored) {} });
            }
        } catch (Exception ignored) {}
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
