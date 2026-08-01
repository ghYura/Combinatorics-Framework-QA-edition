package com.company.sink;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * Runs every existing verifier on the CombinatoricsReader side as
 * subprocesses, aggregates pass/fail.  Mirrors {@code AllVerifiersRunner}
 * on the Analyzer side.  Invoked by {@code ./run-tests.sh} at the project
 * root.  Currently the only verifier is {@link SinkSmokeTest}.
 */
public final class AllSinkVerifiersRunner {
    private AllSinkVerifiersRunner() {}

    private record Verifier(String className, String description) {}

    private static final List<Verifier> VERIFIERS = List.of(
        new Verifier("com.company.sink.SinkSmokeTest",
                "RowSink + RowSinkOutputStream + AnalyzerBridge + DiscoveryPolicy"),
        new Verifier("com.company.sink.CandidateSinkSmokeTest",
                "CandidateSink + LooseFileSink + CandidateSinkRegistry (STEP 31)"),
        new Verifier("com.company.sink.ShardSinkSmokeTest",
                "ShardSink + ShardReader compressed-shard sink (STEP 32)")
    );

    public static void main(String[] args) {
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Running " + VERIFIERS.size() + " sink verifier(s)");
        System.out.println("════════════════════════════════════════════════════════════════════");

        int passed = 0, failed = 0;
        long t0 = System.nanoTime();
        for (Verifier v : VERIFIERS) {
            String shortName = v.className.substring(v.className.lastIndexOf('.') + 1);
            long s = System.nanoTime();
            Result r = runOne(v);
            long ms = (System.nanoTime() - s) / 1_000_000;
            if (r.exitCode == 0) {
                System.out.printf(Locale.ROOT, "  ✓ PASS  %-30s  (%4d ms)  %s%n",
                        shortName, ms, v.description);
                passed++;
            } else {
                System.out.printf(Locale.ROOT, "  ✗ FAIL  %-30s  exit=%d (%4d ms)  %s%n",
                        shortName, r.exitCode, ms, v.description);
                System.out.println("    ── tail of output (last 30 lines) ──");
                tail(r.output, 30).forEach(line -> System.out.println("    " + line));
                System.out.println("    ── end ──");
                failed++;
            }
        }
        long totalMs = (System.nanoTime() - t0) / 1_000_000;
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.printf(Locale.ROOT, " Summary: %d passed, %d failed — total %d ms%n",
                passed, failed, totalMs);
        System.out.println("════════════════════════════════════════════════════════════════════");
        if (failed > 0) { System.out.println("❌ TEST RUN FAILED"); System.exit(1); }
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
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            pb.directory(new File(System.getProperty("user.dir")));
            Process p = pb.start();
            StringBuilder out = new StringBuilder();
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) out.append(line).append('\n');
            }
            boolean finished = p.waitFor(180, TimeUnit.SECONDS);
            if (!finished) {
                p.destroyForcibly();
                return new Result(124, out + "\n[timeout 180s]");
            }
            return new Result(p.exitValue(), out.toString());
        } catch (Exception e) {
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
