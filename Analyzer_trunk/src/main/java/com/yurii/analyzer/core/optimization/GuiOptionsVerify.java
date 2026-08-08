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

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Headless verification that the Multi-Target Optimization GUI panel and the
 * "Enable dynamic Python eval (requires scipy)" checkbox actually drive the
 * underlying analyser correctly, end-to-end.
 *
 * The GUI does two things when the user clicks Start:
 *
 *   1. If 'Enable target optimization' is checked, every row of optTable is
 *      converted into one element of an "optimizations" JSON array placed
 *      inside the manual config:
 *
 *          { "optimizations": [
 *              { "key": <Metric Key>, "mode": <Mode>,
 *                "target_value": <Target Value>, "weight": <Weight> },
 *              ...
 *          ] }
 *
 *      That JsonNode is then handed to {@code new OptimizationAnalyzer(...)}.
 *
 *   2. The 'Enable dynamic Python eval' checkbox flips the constructor's
 *      {@code dynamicPythonEnabled} flag.  When set, every line whose text
 *      contains both '=' and ';' is evaluated by the bundled scipy script
 *      (yurii_universal_opt.py — auto-extracted to /tmp on first call); the
 *      returned key/values are merged into that line's kvPairs map.
 *
 * This class reproduces those two steps programmatically, populates the
 * table with three rows that exercise every supported mode, generates a
 * matching synthetic input file, runs the analyser, and asserts the
 * concrete observable consequences.
 *
 *   row #  Metric Key   Mode       Target Value   Weight
 *   ─────  ───────────  ────────   ────────────   ──────
 *     1    cost         minimize       0.50         40
 *     2    throughput   maximize    2000.00         30
 *     3    latency      target         5.00         25
 *
 *   Run:  java -cp target/classes:&lt;deps&gt;
 *               com.yurii.analyzer.core.optimization.GuiOptionsVerify
 */
public final class GuiOptionsVerify {
    private GuiOptionsVerify() {}

    public static void main(String[] args) throws Exception {
        // ─── Step 1: build the JSON exactly the way MainWindow.startAnalysis
        //            does when 'Enable target optimization' is ticked. ─────
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig("{}");
        ArrayNode opts = manual.putArray("optimizations");

        addRow(opts, "cost",       "minimize",   0.50,   40.0);
        addRow(opts, "throughput", "maximize", 2000.00,  30.0);
        addRow(opts, "latency",    "target",     5.00,   25.0);

        System.out.println("Manual config the GUI would produce:");
        System.out.println(AnalyzerCore.toPrettyJson(manual));

        // ─── Step 2: synthesize the corpus the user mentioned.  Each line
        //            carries values for all three goal keys plus an extra
        //            'opt_payload' field that contains a 'k=v;k=v;...'
        //            string — that's the trigger for the Python eval path
        //            (extractFeatures runs UniversalDynamicOptimizer when
        //            text contains both '=' and ';').
        List<String> corpus = generateCorpus();
        Path corpusFile = Files.createTempFile("gui_opts_verify_input_", ".txt");
        Files.write(corpusFile, corpus, StandardCharsets.UTF_8);
        System.out.println("\nSynthetic corpus written to: " + corpusFile);
        System.out.println("Sample lines:");
        for (int i = 0; i < Math.min(5, corpus.size()); i++)
            System.out.println("  " + corpus.get(i));
        System.out.println("  …(" + (corpus.size() - 5) + " more)");

        int failures = 0;

        // ─── Step 3: run the analyser with BOTH 'Enable target optimization'
        //            and 'Enable dynamic Python eval' simulated as ON. ────
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual,
                /*minSupport*/ 1, /*topK*/ 5,
                /*optThreshold*/ 30.0, /*watchThreshold*/ 10.0,
                /*executeCommands*/ false,
                /*commandTimeout*/ 5.0,
                /*dynamicPythonEnabled*/ true);   // ← Python checkbox = ON

        // ── 3a. Goals were parsed from the JSON in row order with the
        //        correct mode / target / weight fields. ──────────────────
        List<OptimizationGoal> goals = analyzer.goals();
        failures += check("3 goals parsed from optTable", goals.size() == 3);
        if (goals.size() == 3) {
            failures += check("row1 key=cost / mode=minimize / target=0.5 / weight=40",
                    goals.get(0).key.equals("cost")
                    && goals.get(0).mode.equals("minimize")
                    && Math.abs(goals.get(0).targetValue - 0.5)  < 1e-9
                    && Math.abs(goals.get(0).weight       - 40)  < 1e-9);
            failures += check("row2 key=throughput / mode=maximize / target=2000 / weight=30",
                    goals.get(1).key.equals("throughput")
                    && goals.get(1).mode.equals("maximize")
                    && Math.abs(goals.get(1).targetValue - 2000) < 1e-9
                    && Math.abs(goals.get(1).weight       - 30)  < 1e-9);
            failures += check("row3 key=latency / mode=target / target=5 / weight=25",
                    goals.get(2).key.equals("latency")
                    && goals.get(2).mode.equals("target")
                    && Math.abs(goals.get(2).targetValue - 5)    < 1e-9
                    && Math.abs(goals.get(2).weight       - 25)  < 1e-9);
        }

        Capture cap = new Capture();
        analyzer.analyzeLines(corpus, cap);

        // ── 3b. Each non-empty line gets a per-mode breakdown tag. ───────
        int minBonus = 0, maxBonus = 0, tgtBonus = 0;
        boolean anyMissTags = false;
        double sumMin = 0, sumMax = 0, sumTgt = 0;
        for (LineResult r : cap.results) {
            for (Map.Entry<String, Double> kv : r.breakdown.entrySet()) {
                String tag = kv.getKey();
                if (tag.startsWith("OptTarget[cost]"))       { minBonus++; sumMin += kv.getValue(); }
                if (tag.startsWith("OptTarget[throughput]")) { maxBonus++; sumMax += kv.getValue(); }
                if (tag.startsWith("OptTarget[latency]"))    { tgtBonus++; sumTgt += kv.getValue(); }
                if (tag.startsWith("MissOptMetric"))         anyMissTags = true;
            }
        }
        System.out.printf(Locale.ROOT,
                "%nPer-mode breakdown evidence: minimize tag×%d (Σ=%.2f)  maximize tag×%d (Σ=%.2f)  target tag×%d (Σ=%.2f)%n",
                minBonus, sumMin, maxBonus, sumMax, tgtBonus, sumTgt);
        failures += check("minimize-mode bonus tag appeared on ≥10 lines", minBonus >= 10);
        failures += check("maximize-mode bonus tag appeared on ≥10 lines", maxBonus >= 10);
        failures += check("target-mode bonus tag appeared on ≥10 lines",   tgtBonus >= 10);

        // ── 3c. Mode semantics: min-mode bonus is largest where 'cost' is
        //        smallest; max-mode bonus is largest where 'throughput' is
        //        largest; target-mode bonus is largest where |latency-5| is
        //        smallest.  This catches mode-mixups in the GUI→config wiring.
        LineResult minBest = bestBy(cap.results, r -> r.breakdown.getOrDefault("OptTarget[cost]", Double.NEGATIVE_INFINITY));
        LineResult maxBest = bestBy(cap.results, r -> r.breakdown.getOrDefault("OptTarget[throughput]", Double.NEGATIVE_INFINITY));
        LineResult tgtBest = bestBy(cap.results, r -> r.breakdown.getOrDefault("OptTarget[latency]", Double.NEGATIVE_INFINITY));
        System.out.printf(Locale.ROOT,
                "Best-bonus lines:  min(cost)=line#%d cost=%s   max(throughput)=line#%d thr=%s   target(latency≈5)=line#%d lat=%s%n",
                minBest.lineNo, minBest.features.kvPairs.get("cost"),
                maxBest.lineNo, maxBest.features.kvPairs.get("throughput"),
                tgtBest.lineNo, tgtBest.features.kvPairs.get("latency"));

        double minCost = parse(minBest.features.kvPairs.get("cost"));
        double maxThr  = parse(maxBest.features.kvPairs.get("throughput"));
        double tgtLat  = parse(tgtBest.features.kvPairs.get("latency"));
        failures += check("minimize: best-bonus cost is the corpus minimum (≤0.30)", minCost <= 0.30 + 1e-6);
        failures += check("maximize: best-bonus throughput is the corpus maximum (≥3000)", maxThr >= 3000.0 - 1e-6);
        failures += check("target=5: best-bonus latency is closest to 5 (|Δ|≤0.5)", Math.abs(tgtLat - 5.0) <= 0.5 + 1e-6);

        // ── 3d. Python eval path actually fired.  Every line in the corpus
        //        contains a 'opt_payload=' field with a ';'-separated python
        //        env statement, so UniversalDynamicOptimizer.evaluate()
        //        should have been called and either a 'python_opt_val'
        //        (scipy success) or 'python_eval_error' key should have
        //        landed in kvPairs.
        int pyTouched = 0, pyOptVal = 0, pyError = 0;
        for (LineResult r : cap.results) {
            boolean any = false;
            for (String k : r.features.kvPairs.keySet()) {
                if (k.startsWith("python_")) { any = true; if (k.equals("python_opt_val")) pyOptVal++; if (k.contains("error")) pyError++; }
            }
            if (any) pyTouched++;
        }
        System.out.printf(Locale.ROOT,
                "%nPython-eval path: %d/%d lines carry python_* keys  (python_opt_val=%d  python_eval_error=%d)%n",
                pyTouched, cap.results.size(), pyOptVal, pyError);
        // The corpus has 6 dedicated python-eval lines; each MUST come back
        // with python_opt_val from scipy.optimize.minimize. The 12 telemetry
        // lines also pass the trigger but the helper finds nothing to
        // minimise there (which is the intended pass-through behaviour).
        failures += check("scipy returned a real optimum on every dedicated python-eval line (≥6)",
                pyOptVal >= 6);
        failures += check("python_eval_error never raised", pyError == 0);

        // ── 3e. Multi-target optimisation diagnostic stream surfaced. ────
        boolean sawPareto = false, sawSimpson = false, sawAuto = false, sawConfODE = false;
        for (String l : cap.logs) {
            if (l.contains("Pareto-optimal frontier")) sawPareto = true;
            if (l.contains("Simpson AUC"))             sawSimpson = true;
            if (l.contains("Auto-discovered"))         sawAuto    = true;
            if (l.contains("Confidence ODE"))          sawConfODE = true;
        }
        failures += check("listener saw Pareto-optimal frontier line",          sawPareto);
        failures += check("listener saw Simpson AUC line",                       sawSimpson);
        failures += check("listener saw 'Auto-discovered ... metric stream(s)'", sawAuto);
        failures += check("listener saw RK4 confidence-ODE verification line",   sawConfODE);

        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Listener log lines (relevant subset)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (String l : cap.logs) {
            if (l.contains("Pareto") || l.contains("Simpson") || l.contains("Brent")
                    || l.contains("Confidence ODE") || l.contains("Auto-discovered")
                    || l.contains("Auto-Pareto") || l.contains("Nelder-Mead")
                    || l.contains("Newton") || l.contains("RK4 τ")) {
                System.out.println("  " + l);
            }
        }

        // Show what python_* keys were captured for one representative line.
        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Sample line: dynamic Python eval merge into kvPairs");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (LineResult r : cap.results) {
            boolean hasPy = r.features.kvPairs.keySet().stream().anyMatch(k -> k.startsWith("python_"));
            if (hasPy) {
                System.out.printf("  line #%d original: %s%n", r.lineNo,
                        r.originalLine.length() > 90 ? r.originalLine.substring(0, 87) + "..." : r.originalLine);
                System.out.println("  python_* keys:");
                for (Map.Entry<String, String> e : r.features.kvPairs.entrySet())
                    if (e.getKey().startsWith("python_"))
                        System.out.printf("    %s = %s%n", e.getKey(), e.getValue());
                break;
            }
        }

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL GUI-OPTIONS CHECKS PASSED");
        else { System.out.println("❌ " + failures + " GUI-OPTIONS CHECK(S) FAILED"); System.exit(1); }
    }

    private static void addRow(ArrayNode opts, String key, String mode, double target, double weight) {
        opts.addObject().put("key", key).put("mode", mode).put("target_value", target).put("weight", weight);
    }

    private static List<String> generateCorpus() {
        // 12 distinct lines exercising the cost / throughput / latency
        // trio across the value space; values are chosen so the per-mode
        // tests have unambiguous winners.
        //
        // After those 12 telemetry lines we append 6 dedicated
        // "python-eval lines": each is structured as a literal Python
        // assignment list `key = expr; key = expr;`.  That is exactly the
        // shape the bundled scipy helper script (yurii_universal_opt.py)
        // knows how to consume — `extractFeatures` will route them through
        // {@code UniversalDynamicOptimizer.evaluate} and merge the
        // resulting python_* keys back into the line's kvPairs.
        double[][] tuples = {
            //  cost   throughput   latency
            {0.95,    400,        12.5},
            {0.80,    600,        10.0},
            {0.65,    900,         8.5},
            {0.50,   1300,         6.5},
            {0.40,   1700,         5.5},
            {0.30,   2200,         5.0},     // best for max(throughput) AND target(latency)
            {0.25,   2600,         5.1},
            {0.20,   3000,         4.6},
            {0.15,   3400,         4.2},
            {0.12,   3800,         3.5},
            {0.10,   4200,         3.0},     // best for min(cost)
            {0.08,   4500,         2.5},
        };
        List<String> out = new ArrayList<>(tuples.length + 6);
        int i = 0;
        for (double[] t : tuples) {
            // Plain telemetry — also has '=' and ';' so the python path is
            // *invoked*; the helper just doesn't find anything to optimise
            // here, which is a separate (intended) outcome.
            out.add(String.format(Locale.ROOT,
                    "operation=run%02d; cost=%.3f; throughput=%.0f; latency=%.2f",
                    i++, t[0], t[1], t[2]));
        }
        // Pure python-eval lines: scipy will minimise these.
        double[] argmins = {0.5, 1.0, -0.7, 2.5, 0.0, 3.14};
        for (double a : argmins) {
            out.add(String.format(Locale.ROOT,
                    "objective = lambda x: (x[0]-%f)**2 + 0.1; params = {'start_point': [0.0]}",
                    a));
        }
        return out;
    }

    private static double parse(String s) {
        if (s == null) return Double.NaN;
        try { return Double.parseDouble(s.replace(',', '.').trim()); }
        catch (NumberFormatException e) { return Double.NaN; }
    }

    private static int check(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static LineResult bestBy(List<LineResult> rs, java.util.function.ToDoubleFunction<LineResult> f) {
        LineResult best = null; double bestV = Double.NEGATIVE_INFINITY;
        for (LineResult r : rs) {
            double v = f.applyAsDouble(r);
            if (v > bestV) { bestV = v; best = r; }
        }
        return best;
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
