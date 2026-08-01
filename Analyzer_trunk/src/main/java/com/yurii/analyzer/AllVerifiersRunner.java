package com.yurii.analyzer;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * Single entry point that runs every existing verification driver and
 * aggregates pass/fail counts.  Bound to {@code mvn test} via
 * {@code exec-maven-plugin} in the POM, so {@code mvn test} becomes the
 * canonical regression check across both code paths and feature areas.
 *
 * Offline-friendly: doesn't rely on JUnit / Surefire / TestNG (their
 * providers may not be cached in {@code ~/.m2}).  Forks each driver as a
 * subprocess on the test JVM's classpath, captures stdout/stderr, asserts
 * exit code 0.  Total runtime ~10 s for the whole suite.
 *
 * The drivers themselves keep their {@code main()} entries untouched — they
 * remain runnable ad-hoc from the command line for individual investigation.
 *
 * Optional drivers (those that need on-disk inputs) are skipped quietly when
 * the input is missing, so the runner works on any developer machine.
 */
public final class AllVerifiersRunner {
    private AllVerifiersRunner() {}

    /** One row in the verifier table. */
    private record Verifier(String className, String description, String[] args,
                            String[] requiredFiles, boolean optional) {
        static Verifier req(String c, String d, String... args) {
            return new Verifier(c, d, args, new String[0], false);
        }
        static Verifier opt(String c, String d, String[] needed, String... args) {
            return new Verifier(c, d, args, needed, true);
        }
    }

    private static final List<Verifier> VERIFIERS = List.of(
        Verifier.req("com.yurii.analyzer.core.optimization.OptimizersSmokeTest",
                "Brent / Newton / NM / SA / RK4 / Simpson primitives"),
        Verifier.req("com.yurii.analyzer.core.optimization.OptimizationVerification",
                "12 adversarial numerical claims (KKT, Pareto domination, ODE)"),
        Verifier.req("com.yurii.analyzer.core.optimization.AnalyzerIntegrationSmoke",
                "Brent + Pareto + Simpson + RK4 end-to-end via OptimizationAnalyzer"),
        Verifier.req("com.yurii.analyzer.core.optimization.ExecutableLineE2E",
                "executable lines + agnostic metrics + every workflow fires"),
        Verifier.req("com.yurii.analyzer.core.optimization.GuiOptionsVerify",
                "Multi-Target table + Python eval round-trip"),
        Verifier.req("com.yurii.analyzer.core.optimization.AutoAnalysisVerify",
                "Auto-Analysis planner: discover + infer modes + dispatch"),
        Verifier.req("com.yurii.analyzer.core.optimization.AnalysisModeVerify",
                "Formal vs exploratory modes (declared-only vs auto-discovery; no implicit objective change)"),
        Verifier.req("com.yurii.analyzer.core.optimization.ProvenanceExplanationVerify",
                "Provenance + non-dominance explanation (traceable, deterministic, versioned JSON, formal policy)"),
        Verifier.req("com.yurii.analyzer.core.optimization.BestLinesReporterVerify",
                "Calibrated best-lines report sections (top / Pareto / champions / robustness)"),
        Verifier.req("com.yurii.analyzer.core.optimization.LineParserVerify",
                "LineParser plug-in: Kv + Json + Multi + end-to-end JSON ingestion"),
        Verifier.req("com.yurii.analyzer.core.optimization.RepeatAggregatorVerify",
                "Plan-1 repeat-aware aggregation: per-candidate median + order-statistic CI + TARGET + non-transitive ties"),
        Verifier.req("com.yurii.analyzer.core.optimization.RepeatGoalConsistencyVerify",
                "Plan-1 declared-goal-set parity: K=1 raw and K>1 aggregated paths rank only declared goals (no auto-discovery)"),
        Verifier.req("com.yurii.analyzer.core.optimization.SnapshotJsonVerify",
                "Snapshot.toJson() machine-readable report + round-trip"),
        Verifier.req("com.yurii.analyzer.core.optimization.ReservoirDeepAnalysisVerify",
                "Bounded reservoir + full MetricStreamAnalyzer toolkit on streaming auto-keys"),
        Verifier.req("com.yurii.analyzer.core.optimization.DominanceUnificationVerify",
                "Single Dominance algorithm — batch & streaming produce identical fronts + TARGET unlocked"),
        Verifier.req("com.yurii.analyzer.core.optimization.NsgaIIVerify",
                "Tier-2.3: NSGA-II fast non-dominated sort + crowding distance (default front algorithm)"),
        Verifier.req("com.yurii.analyzer.core.optimization.NsgaIIIVerify",
                "Tier-5.1: NSGA-III reference-point niching (Das-Dennis + perp distance) parallel to NSGA-II"),
        Verifier.req("com.yurii.analyzer.core.optimization.Spea2Verify",
                "Tier-5.1: SPEA2 strength + raw fitness + k-NN density (Zitzler 2001) parallel to NSGA family"),
        Verifier.req("com.yurii.analyzer.core.optimization.MoeaDVerify",
                "Tier-5.1: MOEA/D decomposition (Tchebycheff over Das-Dennis weights) parallel to NSGA + SPEA2"),
        Verifier.req("com.yurii.analyzer.core.optimization.RemoteWorkerVerify",
                "Tier-4.2: RemoteWorker LineExecutor (file-drop + DB-poll closes the loop with the legacy Executor)"),
        Verifier.req("com.yurii.analyzer.core.optimization.BundleControlPlaneVerify",
                "Plan-2: Loom control plane — disperse/local/nested assignment + backpressure + per-host serialization + budget/cancel + K=1 parity"),
        Verifier.req("com.yurii.analyzer.core.optimization.Tier35SeedFeedbackVerify",
                "Tier-3.5: BundleSeed closed-loop feedback artifact (Snapshot → JSON → readback round-trip)"),
        Verifier.req("com.yurii.analyzer.core.optimization.ParallelStreamingVerify",
                "analyzeStreamParallel: numerical equivalence to sequential + speedup at N=50k"),
        Verifier.req("com.yurii.analyzer.core.optimization.CachingExecutorVerify",
                "Tier-1.5: LineExecutor.Caching decorator + CacheStats on Snapshot (sequential + parallel + legacy invariant)"),
        Verifier.req("com.yurii.analyzer.core.optimization.CoverageProbeVerify",
                "Tier-2.1: CoverageProbe shelf (JaCoCo XML / coverage.py JSON / gcov text) + decorator + cache composition"),
        Verifier.req("com.yurii.analyzer.core.parallel.SchedulerVerify",
                "Tier-3.3: pluggable Scheduler shelf — WorkStealing / LeastLoaded / CapabilityAware (numerical equivalence + balance + routing)"),
        Verifier.opt("com.yurii.analyzer.core.optimization.SortMockupRun",
                "Real executable-line corpus (SortAlgoPyMockup3.py)",
                new String[]{System.getenv().getOrDefault("ANALYZER_SORT_CORPUS", "")}),
        // Pass a smaller N for `mvn test` so the suite stays fast; the 1M-scale
        // stress is run ad-hoc via `java ... StreamingVerify 1000000`.
        Verifier.req("com.yurii.analyzer.core.optimization.StreamingVerify",
                "Streaming pipeline + online aggregator + bounded memory (N=10k)",
                "10000")
    );

    public static void main(String[] args) {
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Running " + VERIFIERS.size() + " verification drivers");
        System.out.println("════════════════════════════════════════════════════════════════════");

        int passed = 0, failed = 0, skipped = 0;
        long t0 = System.nanoTime();
        for (Verifier v : VERIFIERS) {
            String shortName = v.className.substring(v.className.lastIndexOf('.') + 1);
            // Skip optional drivers whose inputs are missing
            if (v.optional) {
                boolean missing = false;
                for (String f : v.requiredFiles) {
                    if (!Files.isRegularFile(Path.of(f))) { missing = true; break; }
                }
                if (missing) {
                    System.out.printf(Locale.ROOT, "  ◌ SKIP  %-32s  (input file not present)%n", shortName);
                    skipped++;
                    continue;
                }
            }
            long s = System.nanoTime();
            Result r = runOne(v);
            long ms = (System.nanoTime() - s) / 1_000_000;
            if (r.exitCode == 0) {
                System.out.printf(Locale.ROOT, "  ✓ PASS  %-32s  (%4d ms)  %s%n",
                        shortName, ms, v.description);
                passed++;
            } else {
                System.out.printf(Locale.ROOT, "  ✗ FAIL  %-32s  exit=%d (%4d ms)  %s%n",
                        shortName, r.exitCode, ms, v.description);
                System.out.println("    ── tail of output (last 30 lines) ──");
                tail(r.output, 30).forEach(line -> System.out.println("    " + line));
                System.out.println("    ── end ──");
                failed++;
            }
        }
        long totalMs = (System.nanoTime() - t0) / 1_000_000;

        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.printf(Locale.ROOT,
                " Summary: %d passed, %d failed, %d skipped — total %d ms%n",
                passed, failed, skipped, totalMs);
        System.out.println("════════════════════════════════════════════════════════════════════");
        if (failed > 0) {
            System.out.println("❌ TEST RUN FAILED");
            System.exit(1);
        }
        System.out.println("✅ TEST RUN PASSED");
    }

    private record Result(int exitCode, String output) {}

    private static Result runOne(Verifier v) {
        try {
            String javaBin = System.getProperty("java.home") + "/bin/java";
            String classpath = System.getProperty("java.class.path");
            List<String> cmd = new ArrayList<>();
            cmd.add(javaBin);
            cmd.add("-cp");
            cmd.add(classpath);
            cmd.add(v.className);
            for (String a : v.args) cmd.add(a);

            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            pb.directory(new File(System.getProperty("user.dir")));
            Process p = pb.start();

            StringBuilder out = new StringBuilder();
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    out.append(line).append('\n');
                }
            }
            boolean finished = p.waitFor(180, TimeUnit.SECONDS);
            if (!finished) {
                p.destroyForcibly();
                return new Result(124, out + "\n[timeout after 180s]");
            }
            return new Result(p.exitValue(), out.toString());
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) Thread.currentThread().interrupt();
            return new Result(125, "[runner failure: " + e + "]");
        }
    }

    private static List<String> tail(String text, int n) {
        String[] lines = text.split("\n", -1);
        int start = Math.max(0, lines.length - n);
        List<String> out = new ArrayList<>(Math.min(n, lines.length));
        for (int i = start; i < lines.length; i++) out.add(lines[i]);
        return out;
    }
}
