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
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisContext;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.CorpusProfile;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationGoal;
import com.yurii.analyzer.core.AnalyzerCore.SynthesizedRules;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner.GoalRecommendation;
import com.yurii.analyzer.core.optimization.AutoAnalysisPlanner.Plan;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Headless verification of the Auto-Analysis flow.  Reproduces exactly what
 * the GUI button does on the planner side, then dispatches the plan through
 * the same {@link OptimizationAnalyzer} pipeline that {@code startAnalysis()}
 * would invoke, and asserts the chosen modes / weights / target values are
 * sensible and that every downstream optimisation workflow fires.
 *
 * Run:  java -cp target/classes:&lt;deps&gt;
 *             com.yurii.analyzer.core.optimization.AutoAnalysisVerify
 */
public final class AutoAnalysisVerify {
    private AutoAnalysisVerify() {}

    public static void main(String[] args) throws Exception {
        // ─── Synthetic corpus that exercises the planner heuristic ──────
        // 12 telemetry lines with five numeric metrics (cost, latency, throughput,
        // accuracy, error_rate) and one categorical (status), plus a handful of
        // shell-like and python-eval-eligible lines so the planner triggers
        // BOTH 'recommend executeCommands' AND 'recommend dynamic Python eval'.
        List<String> corpus = new ArrayList<>();
        double[] cost = {0.95, 0.80, 0.65, 0.50, 0.40, 0.30, 0.25, 0.20, 0.15, 0.12, 0.10, 0.08};
        double[] lat  = {12.5, 10.0,  8.5,  6.5,  5.5,  5.0,  5.1,  4.6,  4.2,  3.5,  3.0,  2.5};
        double[] thr  = { 400,  600,  900, 1300, 1700, 2200, 2600, 3000, 3400, 3800, 4200, 4500};
        double[] acc  = {0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.91, 0.92, 0.94, 0.96, 0.97, 0.98};
        double[] err  = {0.50, 0.40, 0.30, 0.20, 0.15, 0.10, 0.09, 0.08, 0.06, 0.04, 0.03, 0.02};
        for (int i = 0; i < cost.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "operation=run%02d cost=%.3f latency=%.2f throughput=%.0f "
                  + "accuracy=%.3f error_rate=%.3f status=ok",
                    i, cost[i], lat[i], thr[i], acc[i], err[i]));
        }
        // 8 lines that look like shell commands → 8/22 ≈ 36%, clears the
        // planner's 30% threshold for recommendExecuteCommands.
        corpus.add("echo \"hello world\"");
        corpus.add("ls -la /tmp");
        corpus.add("python3 -c 'print(42)'");
        corpus.add("grep -E '^cost=' /var/log/syslog");
        corpus.add("curl -s https://example.com/health");
        corpus.add("awk '{print $1}' /etc/passwd");
        corpus.add("./run_one.sh --probe");
        corpus.add("docker ps --format '{{.Names}}'");
        // 2 python-eval-eligible lines
        corpus.add("objective = lambda x: (x[0]-1.5)**2 + 0.05; params = {'start_point': [0.0]}");
        corpus.add("objective = lambda x: (x[0]+2.0)**2 + 0.10; params = {'start_point': [0.0]}");

        int failures = 0;

        // ═══════════════════════════════════════════════════════════════
        //  Phase 1 — Planner produces a sane plan from sample alone.
        // ═══════════════════════════════════════════════════════════════
        boolean scipy = AutoAnalysisPlanner.detectScipyAvailable();
        Plan plan = AutoAnalysisPlanner.plan(corpus, scipy);
        System.out.println(plan.renderSummary());

        // Did planner discover the five numeric metrics?
        Set<String> discoveredKeys = new HashSet<>();
        for (GoalRecommendation g : plan.goals()) discoveredKeys.add(g.key());
        for (String k : List.of("cost", "latency", "throughput", "accuracy", "error_rate")) {
            failures += assertCond("planner discovered '" + k + "'", discoveredKeys.contains(k));
        }

        // Mode inference verdict per metric.
        failures += assertMode(plan, "cost",       "minimize");
        failures += assertMode(plan, "latency",    "minimize");
        failures += assertMode(plan, "throughput", "maximize");
        failures += assertMode(plan, "accuracy",   "maximize");
        failures += assertMode(plan, "error_rate", "minimize");

        // Weights distribute the 100-pt budget evenly across the 5 goals.
        double sumW = 0;
        for (GoalRecommendation g : plan.goals()) sumW += g.weight();
        failures += assertCond(String.format(Locale.ROOT,
                "weight budget ≈ %.1f (sum of %d weights)", sumW, plan.goals().size()),
                Math.abs(sumW - AutoAnalysisPlanner.WEIGHT_BUDGET) <= 1.0);

        // Target value defaults to the metric's median.
        for (GoalRecommendation g : plan.goals()) {
            failures += assertCond(String.format(Locale.ROOT,
                    "%s target = median (%g)", g.key(), g.median()),
                    Math.abs(g.targetValue() - g.median()) < 1e-9);
        }

        // Recommend-execute / recommend-python should both fire.
        failures += assertCond("recommendExecuteCommands == true (8/22 shell-like ≥ 30% threshold)",
                plan.recommendExecuteCommands());
        failures += assertCond("recommendDynamicPython matches scipy availability",
                plan.recommendDynamicPython() == scipy);

        // ═══════════════════════════════════════════════════════════════
        //  Phase 2 — Apply the plan as the GUI would and run analysis.
        //  This proves the populated optTable + checkboxes drive the
        //  pipeline correctly end-to-end.
        // ═══════════════════════════════════════════════════════════════
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig("{}");
        ArrayNode opts = manual.putArray("optimizations");
        for (GoalRecommendation g : plan.goals()) {
            opts.addObject().put("key", g.key()).put("mode", g.mode())
                    .put("target_value", g.targetValue()).put("weight", g.weight());
        }
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual,
                /*minSupport*/ 1, /*topK*/ 5,
                /*optThreshold*/ 30.0, /*watchThreshold*/ 10.0,
                /*executeCommands*/ false,                // skip real shelling out
                /*commandTimeout*/ 5.0,
                /*dynamicPythonEnabled*/ plan.recommendDynamicPython());

        // Goals were parsed back identically.
        List<OptimizationGoal> goals = analyzer.goals();
        failures += assertCond("analyzer received same goal count", goals.size() == plan.goals().size());
        for (int i = 0; i < goals.size(); i++) {
            OptimizationGoal og = goals.get(i);
            GoalRecommendation gr = plan.goals().get(i);
            failures += assertCond(String.format("goal[%d] round-trip key/mode/target/weight", i),
                    og.key.equals(gr.key()) && og.mode.equals(gr.mode())
                            && Math.abs(og.targetValue - gr.targetValue()) < 1e-9
                            && Math.abs(og.weight - gr.weight()) < 1e-9);
        }

        Capture cap = new Capture();
        analyzer.analyzeLines(corpus, cap);

        // Each per-mode breakdown tag must appear.
        boolean sawMin = false, sawMax = false;
        for (LineResult r : cap.results) {
            for (String tag : r.breakdown.keySet()) {
                if (tag.startsWith("OptTarget[cost]") || tag.startsWith("OptTarget[error_rate]")) sawMin = true;
                if (tag.startsWith("OptTarget[throughput]") || tag.startsWith("OptTarget[accuracy]")) sawMax = true;
            }
        }
        failures += assertCond("minimize-mode bonus tag fired", sawMin);
        failures += assertCond("maximize-mode bonus tag fired", sawMax);

        // Every workflow log line we already audited must show up.
        boolean[] seen = new boolean[8];
        for (String l : cap.logs) {
            if (l.contains("Pareto-optimal frontier")) seen[0] = true;
            if (l.contains("Simpson AUC"))             seen[1] = true;
            if (l.contains("Confidence ODE"))          seen[2] = true;
            if (l.contains("Auto-discovered"))         seen[3] = true;
            if (l.contains("Brent argmin@line"))       seen[4] = true;
            if (l.contains("Nelder-Mead exp-fit"))     seen[5] = true;
            if (l.contains("SA min="))                 seen[6] = true;
            if (l.contains("RK4 τ="))                  seen[7] = true;
        }
        String[] names = {"declared-goal Pareto", "Simpson AUC", "RK4 confidence ODE",
                "Auto-discovered metric streams", "Brent argmin/argmax",
                "Nelder-Mead exp-fit", "Simulated annealing", "RK4 relaxation smoothing"};
        for (int i = 0; i < seen.length; i++)
            failures += assertCond("workflow fired: " + names[i], seen[i]);

        // Pareto frontier across the 5 declared goals must be non-empty.
        List<LineResult> front = AnalyzerCore.paretoOptimal(cap.results, goals);
        failures += assertCond("declared-goal Pareto front non-empty (got "
                + front.size() + " of " + cap.results.size() + ")", !front.isEmpty());

        // Auto-Pareto across discovered metrics likewise non-empty.
        List<LineResult> autoFront = MetricStreamAnalyzer.autoPareto(cap.results, 5);
        failures += assertCond("auto-Pareto front non-empty (got " + autoFront.size() + ")",
                !autoFront.isEmpty());

        // Python-eval lines were processed (their python_opt_val must
        // therefore appear as an auto-discovered metric).
        if (plan.recommendDynamicPython()) {
            List<String> autoKeys = MetricStreamAnalyzer.discoveredKeys(cap.results, 1);
            failures += assertCond("python_opt_val auto-discovered after Python eval ran",
                    autoKeys.contains("python_opt_val"));
        }

        // ═══════════════════════════════════════════════════════════════
        //  Wrap-up
        // ═══════════════════════════════════════════════════════════════
        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Selected listener log lines (proof of workflow firing)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (String l : cap.logs) {
            if (l.contains("Pareto") || l.contains("Simpson") || l.contains("Brent")
                    || l.contains("Confidence ODE") || l.contains("Auto-discovered")
                    || l.contains("Auto-Pareto") || l.contains("Nelder-Mead")
                    || l.contains("Newton")) {
                System.out.println("  " + l);
            }
        }

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL AUTO-ANALYSIS CHECKS PASSED");
        else { System.out.println("❌ " + failures + " AUTO-ANALYSIS CHECK(S) FAILED"); System.exit(1); }
    }

    private static int assertMode(Plan plan, String key, String wantMode) {
        for (GoalRecommendation g : plan.goals()) {
            if (g.key().equals(key)) {
                boolean ok = g.mode().equals(wantMode);
                System.out.println((ok ? "  ✓ " : "  ✗ ") + "mode('" + key + "') = "
                        + g.mode() + " (expected " + wantMode + ")  ← " + g.reason());
                return ok ? 0 : 1;
            }
        }
        System.out.println("  ✗ key '" + key + "' missing from plan");
        return 1;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
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
