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

import com.fasterxml.jackson.databind.JsonNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Verifies Tier-2 win 2.1 — {@link CoverageProbe} adapter shelf.
 *
 * What's checked:
 *   1. {@link CoverageProbe.JaCoCoXml}      parses {@code <counter type="LINE" .../>} pairs into
 *                                           fractional + count K=V pairs.
 *   2. {@link CoverageProbe.CoveragePyJson} parses {@code totals.percent_covered} etc.
 *   3. {@link CoverageProbe.GcovText}       extracts last-emitted "Lines/Branches/Calls executed:N%"
 *      from gcov / gcovr summary text.
 *   4. {@link LineExecutor.CoverageProbing} concatenates probe suffix to delegate output.
 *   5. Missing report → "" (probe never throws — candidate survives).
 *   6. End-to-end {@code analyzeStream} run picks up {@code coverage_*} axes,
 *      and {@code DiscoveryPolicy.DEFAULT} infers them as MAXIMIZE
 *      (via {@code AutoAnalysisPlanner.MAX_HINTS} containing "coverage").
 *   7. Composition with {@link LineExecutor.Caching}: probe outputs are
 *      cached too — repeated raw lines hit cache and do NOT re-read the
 *      report file (verified via on-disk delete-then-call).
 */
public final class CoverageProbeVerify {
    private CoverageProbeVerify() {}

    public static void main(String[] args) throws Exception {
        int failed = 0;
        Path tmp = Files.createTempDirectory("cov_probe_verify_");
        try {
            failed += jacocoParse(tmp);
            failed += coveragePyParse(tmp);
            failed += gcovParse(tmp);
            failed += probingDecoratorAndMissingReport(tmp);
            failed += endToEndAnalyzerInference(tmp);
            failed += cacheComposition(tmp);
        } finally {
            cleanup(tmp);
        }

        System.out.println();
        if (failed == 0) System.out.println("✅ ALL COVERAGE-PROBE CHECKS PASSED");
        else { System.out.println("❌ " + failed + " COVERAGE-PROBE CHECK(S) FAILED"); System.exit(1); }
    }

    // ─────────────────────────────────────────────────────────────────────
    //  1. JaCoCo XML
    // ─────────────────────────────────────────────────────────────────────
    private static int jacocoParse(Path tmp) throws Exception {
        System.out.println("── JaCoCo XML parse ──");
        Path xml = tmp.resolve("jacoco.xml");
        String body = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
                + "<report name=\"demo\">\n"
                + "  <package name=\"a/b\">\n"
                + "    <counter type=\"LINE\" missed=\"5\" covered=\"15\"/>\n"
                + "  </package>\n"
                // Report-level totals — these are what the probe should report.
                + "  <counter type=\"INSTRUCTION\" missed=\"40\" covered=\"160\"/>\n"
                + "  <counter type=\"BRANCH\" missed=\"3\" covered=\"7\"/>\n"
                + "  <counter type=\"LINE\" missed=\"2\" covered=\"18\"/>\n"
                + "  <counter type=\"METHOD\" missed=\"1\" covered=\"9\"/>\n"
                + "  <counter type=\"CLASS\" missed=\"0\" covered=\"3\"/>\n"
                + "</report>\n";
        Files.writeString(xml, body, StandardCharsets.UTF_8);

        CoverageProbe probe = new CoverageProbe.JaCoCoXml(xml.toString());
        String out = probe.collect(1, "raw", "");
        System.out.println("  output: " + out);

        int f = 0;
        // Last <counter type="LINE"> in the file: missed=2 covered=18 → 18/20 = 0.9.
        f += assertCond("JaCoCo coverage_line=0.900000", out.contains("coverage_line=0.900000"));
        f += assertCond("JaCoCo coverage_line_covered=18", out.contains("coverage_line_covered=18"));
        f += assertCond("JaCoCo coverage_line_total=20", out.contains("coverage_line_total=20"));
        f += assertCond("JaCoCo coverage_branch=0.700000", out.contains("coverage_branch=0.700000"));
        f += assertCond("JaCoCo coverage_method=0.900000", out.contains("coverage_method=0.900000"));
        f += assertCond("JaCoCo coverage_class=1.000000",  out.contains("coverage_class=1.000000"));
        f += assertCond("JaCoCo coverage_instruction=0.800000",
                out.contains("coverage_instruction=0.800000"));
        f += assertCond("JaCoCo output is space-prefixed", out.startsWith(" "));
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  2. coverage.py JSON
    // ─────────────────────────────────────────────────────────────────────
    private static int coveragePyParse(Path tmp) throws Exception {
        System.out.println("\n── coverage.py JSON parse ──");
        Path json = tmp.resolve("coverage.json");
        String body = "{ \"meta\": {}, \"totals\": {"
                + "  \"covered_lines\": 85,"
                + "  \"num_statements\": 100,"
                + "  \"missing_lines\": 15,"
                + "  \"percent_covered\": 85.0,"
                + "  \"covered_branches\": 18,"
                + "  \"num_branches\": 20"
                + "} }";
        Files.writeString(json, body, StandardCharsets.UTF_8);

        CoverageProbe probe = new CoverageProbe.CoveragePyJson(json.toString());
        String out = probe.collect(1, "raw", "");
        System.out.println("  output: " + out);

        int f = 0;
        f += assertCond("coverage.py coverage_line=0.850000", out.contains("coverage_line=0.850000"));
        f += assertCond("coverage.py coverage_line_covered=85", out.contains("coverage_line_covered=85"));
        f += assertCond("coverage.py coverage_line_total=100", out.contains("coverage_line_total=100"));
        f += assertCond("coverage.py coverage_line_missed=15", out.contains("coverage_line_missed=15"));
        f += assertCond("coverage.py coverage_branch=0.900000", out.contains("coverage_branch=0.900000"));
        f += assertCond("coverage.py coverage_branch_covered=18",
                out.contains("coverage_branch_covered=18"));
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  3. gcov / gcovr text
    // ─────────────────────────────────────────────────────────────────────
    private static int gcovParse(Path tmp) throws Exception {
        System.out.println("\n── gcov / gcovr text parse ──");
        Path txt = tmp.resolve("gcov.txt");
        String body = ""
                + "File 'src/foo.c'\n"
                + "Lines executed:60.00% of 30\n"
                + "Branches executed:50.00% of 10\n"
                + "Calls executed:75.00% of 4\n"
                // Aggregate (last) — what the probe should report.
                + "File 'src/bar.c'\n"
                + "Lines executed:80.00% of 50\n"
                + "Branches executed:65.00% of 20\n"
                + "Calls executed:90.00% of 10\n";
        Files.writeString(txt, body, StandardCharsets.UTF_8);

        CoverageProbe probe = new CoverageProbe.GcovText(txt.toString());
        String out = probe.collect(1, "raw", "");
        System.out.println("  output: " + out);

        int f = 0;
        f += assertCond("gcov coverage_line=0.800000 (last match wins)",
                out.contains("coverage_line=0.800000"));
        f += assertCond("gcov coverage_line_total=50", out.contains("coverage_line_total=50"));
        f += assertCond("gcov coverage_branch=0.650000", out.contains("coverage_branch=0.650000"));
        f += assertCond("gcov coverage_call=0.900000", out.contains("coverage_call=0.900000"));
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  4. CoverageProbing decorator + 5. missing report tolerance
    // ─────────────────────────────────────────────────────────────────────
    private static int probingDecoratorAndMissingReport(Path tmp) throws Exception {
        System.out.println("\n── CoverageProbing decorator + missing-report tolerance ──");
        Path xml = tmp.resolve("decorator_jacoco.xml");
        Files.writeString(xml,
                "<report><counter type=\"LINE\" missed=\"1\" covered=\"9\"/></report>",
                StandardCharsets.UTF_8);

        LineExecutor base = (lineNo, raw) -> "id=" + lineNo + " cost=" + raw;
        LineExecutor wrapped = new LineExecutor.CoverageProbing(
                base, new CoverageProbe.JaCoCoXml(xml.toString()));

        String out = wrapped.execute(7, "1.5");
        System.out.println("  wrapped output: " + out);

        int f = 0;
        f += assertCond("decorator preserves delegate output",
                out.startsWith("id=7 cost=1.5"));
        f += assertCond("decorator appends coverage_line=0.900000",
                out.contains("coverage_line=0.900000"));

        // Missing report → "" (no exception).
        LineExecutor wrappedMissing = new LineExecutor.CoverageProbing(
                base, new CoverageProbe.JaCoCoXml(tmp.resolve("does_not_exist.xml").toString()));
        String outMissing = wrappedMissing.execute(8, "2.0");
        f += assertCond("missing report → no suffix appended",
                outMissing.equals("id=8 cost=2.0"));
        f += assertCond("missing report does not throw", true);

        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  6. End-to-end through analyzeStream: coverage axes are auto-discovered
    //     and inferred as MAXIMIZE
    // ─────────────────────────────────────────────────────────────────────
    private static int endToEndAnalyzerInference(Path tmp) throws Exception {
        System.out.println("\n── End-to-end: analyzeStream picks up coverage_* axes as MAXIMIZE ──");
        // Write a different JaCoCo XML per candidate so the Pareto front sees
        // variation along the coverage axis (otherwise OnlinePareto sees a
        // constant axis and trims it from selection).
        for (int i = 1; i <= 3; i++) {
            Path xml = tmp.resolve("e2e_jacoco_" + i + ".xml");
            int covered = 10 * i;        // 10, 20, 30
            int missed  = 30 - 10 * i;   // 20, 10, 0
            Files.writeString(xml,
                    "<report><counter type=\"LINE\" missed=\"" + missed
                            + "\" covered=\"" + covered + "\"/></report>",
                    StandardCharsets.UTF_8);
        }

        LineExecutor base = (lineNo, raw) -> raw;
        LineExecutor wrapped = new LineExecutor.CoverageProbing(
                base, new CoverageProbe.JaCoCoXml(
                        tmp.resolve("e2e_jacoco_{lineNo}.xml").toString()));

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);
        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStream(
                arrayIterator(new String[]{
                        "id=a cost=3.0",
                        "id=b cost=2.0",
                        "id=c cost=1.0"}),
                wrapped, 5,
                List.of(GoalSpec.min("cost", 1.0)),
                DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});

        int f = 0;
        f += assertCond("Snapshot.perKeyStats includes 'coverage_line'",
                snap.perKeyStats().containsKey("coverage_line"));
        f += assertCond("coverage_line.n == 3", snap.perKeyStats().get("coverage_line").n == 3);
        // Effective goals: declared 'cost' + auto-discovered 'coverage_line' inferred MAX.
        List<GoalSpec> eff = snap.effectiveGoals();
        GoalSpec covGoal = null;
        for (GoalSpec g : eff) if ("coverage_line".equals(g.key())) covGoal = g;
        f += assertCond("effectiveGoals includes coverage_line", covGoal != null);
        if (covGoal != null) {
            f += assertCond("coverage_line inferred as MAXIMIZE",
                    covGoal.mode() == GoalSpec.Mode.MAXIMIZE);
        }
        // JSON also surfaces it under autoDiscoveredAxes.
        JsonNode json = snap.toJson();
        boolean covAuto = false;
        for (JsonNode a : json.get("autoDiscoveredAxes")) {
            if ("coverage_line".equals(a.get("key").asText())) {
                covAuto = true;
                f += assertCond("toJson coverage_line.mode == MAXIMIZE",
                        "MAXIMIZE".equals(a.get("mode").asText()));
            }
        }
        f += assertCond("autoDiscoveredAxes contains coverage_line", covAuto);
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  7. Composition with Caching — probe is INSIDE the cache.
    //     Repeated raw line → cache hit → no probe call → still works
    //     even after the report file is removed.
    // ─────────────────────────────────────────────────────────────────────
    private static int cacheComposition(Path tmp) throws Exception {
        System.out.println("\n── Composition: Caching outside CoverageProbing ──");
        Path xml = tmp.resolve("compose_jacoco.xml");
        Files.writeString(xml,
                "<report><counter type=\"LINE\" missed=\"2\" covered=\"8\"/></report>",
                StandardCharsets.UTF_8);

        AtomicInteger delegateCalls = new AtomicInteger();
        LineExecutor base = (lineNo, raw) -> {
            delegateCalls.incrementAndGet();
            return raw;
        };
        LineExecutor probing = new LineExecutor.CoverageProbing(
                base, new CoverageProbe.JaCoCoXml(xml.toString()));
        LineExecutor cached = new LineExecutor.Caching(probing, 64);

        String first  = cached.execute(1, "id=q cost=1.0");
        // Delete the report — a cache hit must NOT need it.
        Files.deleteIfExists(xml);
        String second = cached.execute(2, "id=q cost=1.0");

        int f = 0;
        f += assertCond("first call includes coverage_line=0.800000",
                first.contains("coverage_line=0.800000"));
        f += assertCond("second call (cache hit) equals first call output",
                second.equals(first));
        f += assertCond("delegate called exactly once (cache hit on repeat)",
                delegateCalls.get() == 1);
        CacheStats cs = cached.cacheStats();
        f += assertCond("cacheStats.hits == 1", cs.hits() == 1);
        f += assertCond("cacheStats.misses == 1", cs.misses() == 1);
        return f;
    }

    // ─────────────────────────────────────────────────────────────────────
    //  helpers
    // ─────────────────────────────────────────────────────────────────────
    private static void cleanup(Path dir) {
        try {
            if (dir == null) return;
            if (Files.isDirectory(dir)) {
                try (var stream = Files.list(dir)) {
                    stream.forEach(p -> { try { Files.deleteIfExists(p); } catch (IOException ignored) {} });
                }
                Files.deleteIfExists(dir);
            }
        } catch (Exception ignored) {}
    }

    private static Iterator<String> arrayIterator(String[] xs) {
        return new Iterator<>() {
            int i = 0;
            @Override public boolean hasNext() { return i < xs.length; }
            @Override public String next() {
                if (i >= xs.length) throw new NoSuchElementException();
                return xs[i++];
            }
        };
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    // Suppress an unused-import lint when Locale isn't directly referenced.
    @SuppressWarnings("unused") private static final Locale ROOT = Locale.ROOT;
}
