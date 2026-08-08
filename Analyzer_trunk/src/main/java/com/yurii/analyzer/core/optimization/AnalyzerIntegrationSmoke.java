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

import java.util.ArrayList;
import java.util.List;

/**
 * End-to-end check that the analyser actually invokes the optimisation toolkit:
 *   • Brent's method runs once per goal that supplies an objective expression.
 *   • Pareto-frontier extraction is reported via the listener after scoring.
 *   • Simpson AUC over the score curve is reported.
 *   • RK4 verification of the confidence ODE is reported.
 *
 * Run with:  java -cp target/classes com.yurii.analyzer.core.optimization.AnalyzerIntegrationSmoke
 */
public final class AnalyzerIntegrationSmoke {
    private AnalyzerIntegrationSmoke() {}

    public static void main(String[] args) throws Exception {
        // Manual config carries one objective-bearing goal: f(x) = (x - 7)^2  → argmin at x=7.
        // The "cost" key value will be parsed from each input line.
        String manualJson = """
            {
              "optimizations": [
                { "key": "cost", "mode": "target", "objective": "(x - 7)^2",
                  "search_lo": -20, "search_hi": 20, "weight": 30 }
              ]
            }
            """;
        JsonNode manual = AnalyzerCore.parseManualConfig(manualJson);

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual,
                /*minSupport*/ 1, /*topK*/ 5,
                /*optThreshold*/ 30.0, /*watchThreshold*/ 10.0,
                /*executeCommands*/ false, /*commandTimeout*/ 0.0,
                /*dynamicPython*/ false);

        // Confirm the Brent-derived argmin is exactly 7.0 to high precision.
        OptimizationGoal goal = analyzer.goals().get(0);
        if (!goal.optimumValid) { System.out.println("✗ goal optimum invalid"); System.exit(1); }
        if (Math.abs(goal.computedArgmin - 7.0) > 1e-6) {
            System.out.printf("✗ Brent argmin: got %.6f want 7.0%n", goal.computedArgmin);
            System.exit(1);
        }
        System.out.printf("✓ Brent argmin computed at construction: x*=%.6f f*=%.6g%n",
                goal.computedArgmin, goal.computedOptimum);

        // Build a small corpus with a known cost gradient.
        List<String> corpus = List.of(
                "operation=alpha cost=2 latency=8 status=ok",
                "operation=beta  cost=4 latency=6 status=ok",
                "operation=gamma cost=6 latency=4 status=ok",
                "operation=delta cost=7 latency=3 status=ok",       // best — matches argmin
                "operation=epsi  cost=8 latency=2 status=ok",
                "operation=zeta  cost=12 latency=12 status=err",
                "# comment line",
                "",
                "operation=eta   cost=15 latency=20 status=err"
        );

        Capture cap = new Capture();
        analyzer.analyzeLines(corpus, cap);

        // Verify diagnostics were emitted.
        boolean sawBrent  = cap.logs.stream().anyMatch(s -> s.contains("Brent-minimised objective"));
        boolean sawSimp   = cap.logs.stream().anyMatch(s -> s.contains("Simpson AUC"));
        boolean sawPareto = cap.logs.stream().anyMatch(s -> s.contains("Pareto-optimal frontier"));
        boolean sawOde    = cap.logs.stream().anyMatch(s -> s.contains("Confidence ODE"));

        int fail = 0;
        fail += assertTrue("listener saw Brent log line", sawBrent);
        fail += assertTrue("listener saw Simpson AUC line", sawSimp);
        fail += assertTrue("listener saw Pareto frontier line", sawPareto);
        fail += assertTrue("listener saw RK4 ODE verification line", sawOde);

        // The line with cost=7 should be the optimum (argmin) match.
        LineResult best = AnalyzerCore.findOptimalResult(cap.results);
        System.out.printf("Best line: #%d  score=%.2f  text=%s%n",
                best.lineNo, best.score, best.originalLine);

        // Show abridged diagnostic log.
        System.out.println();
        System.out.println("--- relevant log lines ---");
        cap.logs.stream()
                .filter(s -> s.contains("Brent") || s.contains("Simpson") || s.contains("Pareto") || s.contains("ODE"))
                .forEach(s -> System.out.println("  " + s));

        if (fail == 0) System.out.println("\nINTEGRATION CHECKS PASSED");
        else { System.out.println("\n" + fail + " INTEGRATION CHECK(S) FAILED"); System.exit(1); }
    }

    private static int assertTrue(String name, boolean cond) {
        System.out.printf("%s %s%n", cond ? "✓" : "✗", name);
        return cond ? 0 : 1;
    }

    private static final class Capture implements AnalysisListener {
        final List<String> logs = new ArrayList<>();
        final List<LineResult> results = new ArrayList<>();
        @Override public void onLog(String message) { logs.add(message); }
        @Override public void onResult(LineResult result) { results.add(result); }
        @Override public void onProfileReady(CorpusProfile p, SynthesizedRules r) {}
        @Override public void onFinished(AnalysisContext ctx) {}
        @Override public void onError(String message, Throwable error) {
            logs.add("ERROR: " + message + (error == null ? "" : " | " + error.getMessage()));
        }
    }
}
