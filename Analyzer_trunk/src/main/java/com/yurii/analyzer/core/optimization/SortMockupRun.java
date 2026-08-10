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

package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisContext;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.CorpusProfile;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.AnalyzerCore.SynthesizedRules;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner.GoalRecommendation;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner.Plan;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Driver that runs the analyser end-to-end on a corpus of sort workloads — a
 * file where every line is a self-contained `python3 -c "…"` command that
 * prints agnostic timing / memory metrics on stdout (Wall, CPU, Blocks, Peak
 * Mem, GC, Correct).  This is the most realistic "executable lines emitting
 * agnostic metrics" workload in the project, and a strong test of the full
 * pipeline (executeCommands=true → stdout capture → KV parsing → numeric
 * extraction → MetricStreamAnalyzer → BestLinesReporter).
 *
 * The corpus is runtime output and is therefore not committed:
 * {@code Analyzer_trunk/samples/make_sort_corpus.py} generates it
 * deterministically, and {@code run-tests.sh} writes it to a temporary
 * directory, exports {@code ANALYZER_SORT_CORPUS}, and deletes it afterwards.
 * Nothing here asserts on measured values — only that the metric keys are
 * discovered and the reports are non-empty.
 *
 * Run:  java -cp target/classes:&lt;deps&gt;
 *             com.yurii.analyzer.core.optimization.SortMockupRun [path]
 */
public final class SortMockupRun {
    private SortMockupRun() {}

    public static void main(String[] args) throws Exception {
        String corpusArg = args.length > 0 ? args[0] : System.getenv("ANALYZER_SORT_CORPUS");
        if (corpusArg == null || corpusArg.isBlank()) {
            System.out.println("SKIP: pass a corpus path or set ANALYZER_SORT_CORPUS");
            return;
        }
        Path corpus = Path.of(corpusArg);
        List<String> lines = Files.readAllLines(corpus, StandardCharsets.UTF_8);
        System.out.println("Input file: " + corpus + "  (" + lines.size() + " lines)");

        // ─── Plan via Auto-Analysis (peek lines without executing) ──────
        Plan plan = AutoAnalysisPlanner.plan(lines, AutoAnalysisPlanner.detectScipyAvailable());
        System.out.println();
        System.out.println(plan.renderSummary());

        // ─── Build manual config from plan + run with executeCommands=true ──
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig("{}");
        ArrayNode opts = manual.putArray("optimizations");
        for (GoalRecommendation g : plan.goals()) {
            opts.addObject().put("key", g.key()).put("mode", g.mode())
                    .put("target_value", g.targetValue()).put("weight", g.weight());
        }
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, /*minSupport*/1, /*topK*/10, /*optThreshold*/30.0,
                /*watchThreshold*/10.0, /*executeCommands*/true,
                /*commandTimeout*/30.0, /*dynamicPython*/false);

        Capture cap = new Capture();
        long t0 = System.nanoTime();
        analyzer.analyzeLines(lines, cap);
        long elapsedMs = (System.nanoTime() - t0) / 1_000_000;

        // ─── Per-line: what kvPairs were captured? ───────────────────────
        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Per-line kvPairs (after stdout capture)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (LineResult r : cap.results) {
            System.out.printf(Locale.ROOT, "  line #%-2d  type=%-10s  score=%6.2f%n",
                    r.lineNo, r.features.lineType, r.score);
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                System.out.printf("              %-20s → %s%n", e.getKey(), e.getValue());
            }
        }

        // ─── Auto-discovered metric streams ───────────────────────────────
        List<String> discoveredKeys = MetricStreamAnalyzer.discoveredKeys(cap.results, 2);
        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Auto-discovered numeric metric streams (≥2 occurrences)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println("  " + discoveredKeys);

        // ─── Per-stream optimisation-theory sweep ─────────────────────────
        List<MetricStreamAnalyzer.MetricAnalysis> streams =
                MetricStreamAnalyzer.analyzeAll(cap.results, 2);
        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Per-metric optimisation-theory results");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (var ma : streams) {
            System.out.printf(Locale.ROOT, "  %-20s n=%-2d μ=%-12.4g σ=%-12.4g  Brent[min=%-12.4g @x≈%-5.2f, max=%-12.4g @x≈%-5.2f]%n",
                    ma.key(), ma.n(), ma.mean(), ma.stdev(),
                    ma.brentMin(), ma.brentArgmin(), ma.brentMax(), ma.brentArgmax());
        }

        // ─── Calibrated best-lines report ─────────────────────────────────
        BestLinesReporter.Report report = BestLinesReporter.build(
                cap.profile, cap.results, analyzer.goals());
        System.out.println(report.render());

        // ─── Pipeline coverage assertions ─────────────────────────────────
        int failures = 0;
        failures += assertCond("every line had its stdout captured (≥1 kvPair)",
                cap.results.stream().allMatch(r -> !r.features.kvPairs.isEmpty()));
        failures += assertCond("at least one numeric metric auto-discovered",
                !discoveredKeys.isEmpty());
        // extractFeatures lowercases the K/V keys before storing them in
        // kvPairs, so we look for the lowercase form. (Stdout had "Wall:",
        // "CPU:", "Blocks:", "Peak Mem:".)
        failures += assertCond("'wall' (timing, unit-suffixed) auto-discovered",
                discoveredKeys.contains("wall"));
        failures += assertCond("'cpu'  (timing, unit-suffixed) auto-discovered",
                discoveredKeys.contains("cpu"));
        failures += assertCond("'blocks' (clean integer) auto-discovered",
                discoveredKeys.contains("blocks"));
        failures += assertCond("'mem' (memory, unit-suffixed) auto-discovered",
                discoveredKeys.contains("mem"));
        failures += assertCond("'gc' (truncated tuple) auto-discovered",
                discoveredKeys.contains("gc"));
        boolean sawSimpson = cap.logs.stream().anyMatch(s -> s.contains("Simpson AUC"));
        boolean sawAuto    = cap.logs.stream().anyMatch(s -> s.contains("Auto-discovered"));
        failures += assertCond("listener saw Simpson AUC log",        sawSimpson);
        failures += assertCond("listener saw Auto-discovered log",    sawAuto);
        failures += assertCond("BestLinesReporter Section 4 non-empty",
                !report.metricChampions().isEmpty());
        failures += assertCond("BestLinesReporter robustness ranking non-empty",
                !report.robustness().isEmpty());

        System.out.printf(Locale.ROOT, "%nElapsed: %d ms%n", elapsedMs);
        if (failures == 0) System.out.println("\n✅ ALL SORT-MOCKUP CHECKS PASSED");
        else { System.out.println("\n❌ " + failures + " SORT-MOCKUP CHECK(S) FAILED"); System.exit(1); }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static final class Capture implements AnalysisListener {
        final List<String> logs = new ArrayList<>();
        final List<LineResult> results = new ArrayList<>();
        CorpusProfile profile;
        @Override public void onLog(String message) { logs.add(message); }
        @Override public void onResult(LineResult result) { results.add(result); }
        @Override public void onProfileReady(CorpusProfile p, SynthesizedRules r) { profile = p; }
        @Override public void onFinished(AnalysisContext ctx) {}
        @Override public void onError(String message, Throwable error) {
            logs.add("ERROR: " + message + (error == null ? "" : " | " + error.getMessage()));
        }
    }
}
