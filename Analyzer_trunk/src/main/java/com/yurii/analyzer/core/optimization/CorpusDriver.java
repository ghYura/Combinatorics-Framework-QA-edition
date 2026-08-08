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
import com.yurii.analyzer.core.AnalyzerCore.AnalysisContext;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.CorpusProfile;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationGoal;
import com.yurii.analyzer.core.AnalyzerCore.SynthesizedRules;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Drives samples/comprehensive_input.txt through the analyser using
 * samples/comprehensive_config.json. Prints (a) every Brent-derived argmin,
 * (b) the line-type histogram, (c) the listener's optimisation diagnostics,
 * (d) the top 10 results by score.
 *
 * Run:  java -cp target/classes:<deps> com.yurii.analyzer.core.optimization.CorpusDriver
 */
public final class CorpusDriver {
    private CorpusDriver() {}

    public static void main(String[] args) throws Exception {
        Path corpusPath = Path.of(args.length > 0 ? args[0] : "samples/comprehensive_input.txt");
        Path configPath = Path.of(args.length > 1 ? args[1] : "samples/comprehensive_config.json");

        String configJson = Files.readString(configPath, StandardCharsets.UTF_8);
        JsonNode manual = AnalyzerCore.parseManualConfig(configJson);
        List<String> lines = Files.readAllLines(corpusPath, StandardCharsets.UTF_8);

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 3, 12, 75.0, 45.0, false, 30.0, false);

        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Brent-precomputed analytical optima (one per goal with 'objective')");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (OptimizationGoal g : analyzer.goals()) {
            if (g.optimumValid) {
                System.out.printf(Locale.ROOT,
                        "  goal '%s'   objective='%s'   bracket=[%g, %g]%n" +
                        "      → argmin = %.10f   fmin = %.10g   weight = %g%n",
                        g.key, g.objective, g.searchLo, g.searchHi,
                        g.computedArgmin, g.computedOptimum, g.weight);
            } else {
                System.out.printf(Locale.ROOT,
                        "  goal '%s'   mode=%s   weight=%g (no objective expression)%n",
                        g.key, g.mode, g.weight);
            }
        }
        System.out.println();

        Capture cap = new Capture();
        analyzer.analyzeLines(lines, cap);

        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Line-type histogram (kv_numeric/kv/templated/numeric/text/mixed/...)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (Map.Entry<String, Integer> e : cap.profile.lineTypeFrequency.entrySet())
            System.out.printf(Locale.ROOT, "  %-12s  %5d%n", e.getKey(), e.getValue());

        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Optimisation-theory diagnostics (the listener log)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        cap.logs.stream()
                .filter(s -> s.contains("Brent") || s.contains("Simpson") || s.contains("Pareto")
                          || s.contains("ODE")   || s.contains("Auto-discovered")
                          || s.contains("Nelder-Mead") || s.contains("Newton")
                          || s.contains("argmin@") || s.contains("Auto-Pareto"))
                .forEach(s -> System.out.println("  " + s));

        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Top 10 lines by score");
        System.out.println("════════════════════════════════════════════════════════════════════");
        cap.results.stream()
                .sorted((a, b) -> Double.compare(b.score, a.score))
                .limit(10)
                .forEach(r -> System.out.printf(Locale.ROOT,
                        "  #%-4d  score=%6.2f  decision=%-6s  type=%-10s  %s%n",
                        r.lineNo, r.score, r.decision, r.features.lineType,
                        r.originalLine.length() > 80 ? r.originalLine.substring(0, 77) + "..." : r.originalLine));

        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Decision counts");
        System.out.println("════════════════════════════════════════════════════════════════════");
        Map<String, Integer> decCounts = new LinkedHashMap<>();
        for (LineResult r : cap.results) decCounts.merge(r.decision, 1, Integer::sum);
        for (Map.Entry<String, Integer> e : decCounts.entrySet())
            System.out.printf(Locale.ROOT, "  %-8s  %5d%n", e.getKey(), e.getValue());
    }

    private static final class Capture implements AnalysisListener {
        final java.util.List<String> logs = new java.util.ArrayList<>();
        final java.util.List<LineResult> results = new java.util.ArrayList<>();
        CorpusProfile profile;
        @Override public void onLog(String message) { logs.add(message); }
        @Override public void onResult(LineResult result) { results.add(result); }
        @Override public void onProfileReady(CorpusProfile p, SynthesizedRules r) { this.profile = p; }
        @Override public void onFinished(AnalysisContext ctx) {}
        @Override public void onError(String message, Throwable error) {
            logs.add("ERROR: " + message + (error == null ? "" : " | " + error.getMessage()));
        }
    }
}
