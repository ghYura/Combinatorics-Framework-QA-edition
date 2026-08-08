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

package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.optimization.BundleControlPlane.Candidate;
import com.yurii.analyzer.core.optimization.BundleControlPlane.Config;
import com.yurii.analyzer.core.optimization.BundleControlPlane.NestedAggregate;
import com.yurii.analyzer.core.optimization.BundleControlPlane.NestedMetricStat;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RepeatEnvJdbcPoller;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RepeatPolicy;
import com.yurii.analyzer.core.optimization.BundleControlPlane.RunResult;
import com.yurii.analyzer.core.optimization.BundleControlPlane.UnitExecutor;
import com.yurii.analyzer.core.optimization.BundleControlPlane.WorkUnit;

import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Plan-2 <b>end-to-end scale demonstration</b>: the real control-plane code drives
 * N real, core-pinned worker processes ({@code cp_demo_worker.py}) that do genuine
 * CPU work and write real {@code results_v2} rows, then collects them back through
 * {@link RepeatEnvJdbcPoller} + {@link BundleControlPlane#run} and decomposes them
 * with {@link BundleControlPlane#aggregateNested}. Closes the §P2.5 <b>Scale</b>
 * gate at small E with a real throughput-vs-N curve, and shows the §12 between-env
 * / within-env decomposition over real measured latencies.
 *
 * <p>The "environments" are real OS processes pinned to distinct cores via
 * {@code taskset} (Plan-1 §4.4 perf isolation). The candidate scatter uses the
 * control plane's own {@link BundleControlPlane#planUnits} assignment — the same
 * balanced round-robin Reader's {@code LooseFileSink} performs in the real data
 * plane.</p>
 *
 * <p>Run (against an isolated throwaway DB):
 * {@code java -cp ... BundleControlPlaneScaleDemo <jdbcUrl> <worker.py> <host> <port> <db> <user> <pass>}</p>
 */
public final class BundleControlPlaneScaleDemo {
    private BundleControlPlaneScaleDemo() {}

    private static final String DDL =
            "CREATE TABLE IF NOT EXISTS public.results_v2 (" +
            " run_id text NOT NULL DEFAULT 'demo', candidate_id text NOT NULL," +
            " attempt int NOT NULL DEFAULT 0, repeat_idx int NOT NULL DEFAULT 0," +
            " env_id text NOT NULL DEFAULT '', fw_var int, lat double precision," +
            " PRIMARY KEY (run_id, candidate_id, attempt, repeat_idx, env_id))";

    private static String jdbcUrl, workerPy, host, port, db, user, pass;

    public static void main(String[] args) throws Exception {
        if (args.length < 7) {
            System.err.println("usage: BundleControlPlaneScaleDemo <jdbcUrl> <worker.py> <host> <port> <db> <user> <pass>");
            System.exit(2);
        }
        jdbcUrl = args[0]; workerPy = args[1]; host = args[2]; port = args[3];
        db = args[4]; user = args[5]; pass = args[6];
        try (Connection c = DriverManager.getConnection(jdbcUrl); Statement st = c.createStatement()) {
            st.execute(DDL);
        }

        scaleTest(new int[]{1, 2, 3}, /*candidates*/ 8, /*K*/ 3, /*iters*/ 250_000);
        nestedDecomposition(/*candidates*/ 3, /*envs*/ 3, /*K*/ 4, /*iters*/ 250_000);

        System.out.println("\n✅ SCALE DEMO COMPLETE");
    }

    /** Fixed workload (C·K disperse units) processed by N pinned workers; report
     *  wall-clock + throughput + speedup as N grows. */
    private static void scaleTest(int[] ns, int candidates, int k, int iters) throws Exception {
        System.out.println("══ Scale: " + candidates + " candidates × K" + k + " = "
                + (candidates * k) + " units (disperse), processed by N core-pinned workers ══");
        System.out.printf(Locale.ROOT, "  %-4s %-8s %-12s %-14s %-9s%n",
                "N", "units", "completed", "wall(ms)", "speedup");
        double baseWall = -1;
        for (int n : ns) {
            truncate();
            Config cfg = new Config(RepeatPolicy.DISPERSE, k, envNames(n), 256, false, 0);
            List<Candidate> cands = candidates(candidates);
            List<WorkUnit> units = new BundleControlPlane(cfg).planUnits(cands);
            writeUnitFiles(units, iters);

            List<Process> workers = launchWorkers(n);
            long t0 = System.nanoTime();
            RunResult rr = new BundleControlPlane(cfg).run(cands,
                    BundleControlPlane.jdbcUnitExecutor(poller(), 50L, 60.0));
            long wallMs = (System.nanoTime() - t0) / 1_000_000L;
            for (Process w : workers) w.waitFor();

            if (baseWall < 0) baseWall = wallMs;
            System.out.printf(Locale.ROOT, "  %-4d %-8d %-12d %-14d %-9s%n",
                    n, units.size(), rr.stats().completed(), wallMs,
                    String.format(Locale.ROOT, "%.2fx", baseWall / Math.max(1, wallMs)));
        }
        System.out.println("  (fixed C·K work; more pinned workers ⇒ lower wall-clock ⇒ the FW_VAR-style"
                + " verdict path scales with Executors — §P2.5 Scale.)");
    }

    /** Nested run: each candidate on each of E real environments; decompose
     *  between-env vs within-env over the workers' real measured latencies. */
    private static void nestedDecomposition(int candidates, int envs, int k, int iters) throws Exception {
        System.out.println("\n══ Cross-env (§12): nested " + candidates + " cand × E" + envs + " × K" + k
                + " on real pinned envs — between-env vs within-env over real latencies ══");
        truncate();
        Config cfg = new Config(RepeatPolicy.NESTED, k, envNames(envs), 256, false, 0);
        List<Candidate> cands = candidates(candidates);
        writeUnitFiles(new BundleControlPlane(cfg).planUnits(cands), iters);
        List<Process> workers = launchWorkers(envs);
        RunResult rr = new BundleControlPlane(cfg).run(cands,
                BundleControlPlane.jdbcUnitExecutor(poller(), 50L, 60.0));
        for (Process w : workers) w.waitFor();

        Map<String, NestedAggregate> nested = BundleControlPlane.aggregateNested(rr, List.of(GoalSpec.min("lat", 1.0)));
        System.out.printf(Locale.ROOT, "  %-5s %-7s %-12s %-12s %-12s %-11s%n",
                "cand", "envs", "grandMed", "betweenEnv", "withinEnv", "envSens?");
        for (Map.Entry<String, NestedAggregate> e : nested.entrySet()) {
            NestedMetricStat s = e.getValue().objective().get("lat");
            if (s == null) continue;
            System.out.printf(Locale.ROOT, "  %-5s %-7d %-12.3f %-12.3f %-12.3f %-11s%n",
                    e.getKey(), s.envCount(), s.grandMedian(), s.betweenEnvRange(),
                    s.withinEnvMedianRange(), s.envSensitive());
        }
        System.out.println("  (latency in ms; between-env = range of per-env medians, within-env = median"
                + " per-env range. Real numbers from real pinned compute.)");
    }

    // ---------------------------------------------------------------- helpers

    private static RepeatEnvJdbcPoller poller() {
        return new RepeatEnvJdbcPoller(jdbcUrl, "results_v2",
                "candidate_id", "repeat_idx", "env_id", List.of("fw_var", "lat"));
    }

    private static List<String> envNames(int n) {
        List<String> envs = new ArrayList<>();
        for (int i = 0; i < n; i++) envs.add("env-" + i);
        return envs;
    }

    private static List<Candidate> candidates(int n) {
        List<Candidate> out = new ArrayList<>();
        for (int i = 1; i <= n; i++) out.add(new Candidate(i, String.valueOf(i), "cand " + i));
        return out;
    }

    /** Write each env's units (candidate_id repeat_idx iters) to a file the worker reads. */
    private static void writeUnitFiles(List<WorkUnit> units, int iters) throws Exception {
        Path dir = Files.createDirectories(Path.of(System.getProperty("java.io.tmpdir"), "cp_demo"));
        Map<String, BufferedWriter> w = new LinkedHashMap<>();
        try {
            for (WorkUnit u : units) {
                BufferedWriter bw = w.computeIfAbsent(u.envId(), env -> openUnitFile(dir, env));
                bw.write(u.candidateId() + " " + u.repeatIdx() + " " + iters);
                bw.newLine();
            }
        } finally {
            for (BufferedWriter bw : w.values()) bw.close();
        }
    }

    private static BufferedWriter openUnitFile(Path dir, String env) {
        try { return Files.newBufferedWriter(dir.resolve("units_" + env + ".txt"), StandardCharsets.UTF_8); }
        catch (Exception e) { throw new RuntimeException(e); }
    }

    private static List<Process> launchWorkers(int n) throws Exception {
        Path dir = Path.of(System.getProperty("java.io.tmpdir"), "cp_demo");
        int cores = Runtime.getRuntime().availableProcessors();
        List<Process> procs = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            String env = "env-" + i;
            String unitsFile = dir.resolve("units_" + env + ".txt").toString();
            List<String> cmd = new ArrayList<>(List.of(
                    "taskset", "-c", String.valueOf(i % cores),
                    "python3", workerPy, env, unitsFile, host, port, db, user, pass));
            procs.add(new ProcessBuilder(cmd).redirectErrorStream(false).inheritIO().start());
        }
        return procs;
    }

    private static void truncate() throws Exception {
        try (Connection c = DriverManager.getConnection(jdbcUrl); Statement st = c.createStatement()) {
            st.execute("TRUNCATE public.results_v2");
        }
    }
}
