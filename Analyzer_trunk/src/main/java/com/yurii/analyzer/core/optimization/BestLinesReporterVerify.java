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
import com.yurii.analyzer.core.optimization.BestLinesReporter.LineMention;
import com.yurii.analyzer.core.optimization.BestLinesReporter.MetricChampion;
import com.yurii.analyzer.core.optimization.BestLinesReporter.Report;
import com.yurii.analyzer.core.optimization.BestLinesReporter.RobustnessRank;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Headless end-to-end verification of the calibrated best-lines report that
 * the Summary panel now appends after every run. Uses the same Auto-Analysis
 * planner the GUI button uses, then drives the resulting plan through the
 * full {@link OptimizationAnalyzer} pipeline, and finally feeds the captured
 * results into {@link BestLinesReporter#build} to validate every section.
 *
 * Run:  java -cp target/classes:&lt;deps&gt;
 *             com.yurii.analyzer.core.optimization.BestLinesReporterVerify
 */
public final class BestLinesReporterVerify {
    private BestLinesReporterVerify() {}

    public static void main(String[] args) throws Exception {
        // Synthesise a corpus where the "best" line is unambiguous along
        // multiple optimisation axes — that lets us check robustness >1.
        // line indices (1-based, as the analyser numbers them):
        //
        //   1..12  telemetry rows; the 12th has the corpus-min cost,
        //          corpus-max throughput, corpus-min error_rate, and
        //          corpus-max accuracy. So it should appear on
        //          {top1, decl, auto, champ}-min[cost]/max[throughput]/...
        //
        //   13..14 distractor lines that don't carry the goal metrics.
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
        corpus.add("# distractor comment");
        corpus.add("free-form text without metrics");

        // Plan via the same path the GUI's Auto-Analysis button uses.
        Plan plan = AutoAnalysisPlanner.plan(corpus, false);

        // Construct the analyser exactly as MainWindow.startAnalysis does
        // when applyPlanToUi has populated the optimisation table.
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig("{}");
        ArrayNode opts = manual.putArray("optimizations");
        for (GoalRecommendation g : plan.goals()) {
            opts.addObject().put("key", g.key()).put("mode", g.mode())
                    .put("target_value", g.targetValue()).put("weight", g.weight());
        }
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false);

        Capture cap = new Capture();
        analyzer.analyzeLines(corpus, cap);

        Report report = BestLinesReporter.build(cap.profile, cap.results, analyzer.goals());
        System.out.println(report.render());

        int failures = 0;

        // ─── Section 1: top by score is non-empty and order is descending ─
        failures += assertCond("Section 1 non-empty", !report.topByScore().isEmpty());
        boolean ord1 = true;
        for (int i = 1; i < report.topByScore().size(); i++)
            if (report.topByScore().get(i).score() > report.topByScore().get(i - 1).score()) { ord1 = false; break; }
        failures += assertCond("Section 1 sorted by score desc", ord1);

        // ─── Section 2: declared-goal Pareto front is pairwise non-dominated ─
        failures += assertCond("Section 2 non-empty (declared-goal Pareto)",
                !report.declaredGoalPareto().isEmpty());
        boolean pairwiseOk = true;
        for (int i = 0; i < report.declaredGoalPareto().size() && pairwiseOk; i++)
            for (int j = i + 1; j < report.declaredGoalPareto().size() && pairwiseOk; j++) {
                LineResult ri = lookup(cap.results, report.declaredGoalPareto().get(i).lineNo());
                LineResult rj = lookup(cap.results, report.declaredGoalPareto().get(j).lineNo());
                if (dominates(ri, rj, analyzer.goals()) || dominates(rj, ri, analyzer.goals()))
                    pairwiseOk = false;
            }
        failures += assertCond("Section 2 pairwise non-dominated", pairwiseOk);

        // ─── Section 3: auto-Pareto is non-empty when ≥1 metric is auto-discovered ─
        failures += assertCond("Section 3 non-empty (auto-Pareto)",
                !report.autoPareto().isEmpty());

        // ─── Section 4: per-metric champions correspond to actual extrema in the data ─
        failures += assertCond("Section 4 has ≥4 metric champions (cost/lat/thr/acc/err)",
                report.metricChampions().size() >= 4);
        for (MetricChampion c : report.metricChampions()) {
            if (!Set.of("cost", "latency", "throughput", "accuracy", "error_rate").contains(c.key())) continue;
            // The argminLine carries the SERIES-min (Brent's reported min may
            // differ slightly because it operates on an interpolated curve and
            // converges in x, not f). The robust claim is: argminLine is the
            // line whose value equals (or strictly bounds below) every other
            // sample of this metric.
            double actualMin = parseMetric(cap.results, c.argminLine(), c.key());
            double actualMax = parseMetric(cap.results, c.argmaxLine(), c.key());
            double seriesMin = seriesExtreme(cap.results, c.key(), true);
            double seriesMax = seriesExtreme(cap.results, c.key(), false);
            failures += assertCond(String.format(Locale.ROOT,
                    "champion[%s].argmin → line#%d carries series-min %.4g",
                    c.key(), c.argminLine(), actualMin),
                    Math.abs(actualMin - seriesMin) < 1e-9);
            failures += assertCond(String.format(Locale.ROOT,
                    "champion[%s].argmax → line#%d carries series-max %.4g",
                    c.key(), c.argmaxLine(), actualMax),
                    Math.abs(actualMax - seriesMax) < 1e-9);
            // Brent's reported extremum lies in [seriesMin, seriesMax].
            failures += assertCond(String.format(Locale.ROOT,
                    "champion[%s].brentMin %.4g ∈ [%.4g, %.4g]",
                    c.key(), c.min(), seriesMin, seriesMax),
                    c.min() >= seriesMin - 1e-9 && c.min() <= seriesMax + 1e-9);
            failures += assertCond(String.format(Locale.ROOT,
                    "champion[%s].brentMax %.4g ∈ [%.4g, %.4g]",
                    c.key(), c.max(), seriesMin, seriesMax),
                    c.max() >= seriesMin - 1e-9 && c.max() <= seriesMax + 1e-9);
        }

        // ─── Section 5: robustness ranking — line #12 should be on
        //               every front (4/4) given the synthetic dominance ──
        RobustnessRank champion = report.robustness().isEmpty()
                ? null : report.robustness().get(0);
        failures += assertCond("Section 5 has a top robustness candidate", champion != null);
        if (champion != null) {
            failures += assertCond("top robustness line is #12 (corpus-best across all axes)",
                    champion.lineNo() == 12);
            failures += assertCond("top robustness frontHits == 4/4",
                    champion.frontHits() == 4 && champion.maxFronts() == 4);
            // Should mention top1, decl, auto, AND at least one min[*]/max[*] tag
            Set<String> tags = new HashSet<>(champion.fronts());
            failures += assertCond("top robustness tags include top1+decl+auto",
                    tags.contains("top1") && tags.contains("decl") && tags.contains("auto"));
            boolean hasChamp = tags.stream().anyMatch(t -> t.startsWith("min[") || t.startsWith("max["));
            failures += assertCond("top robustness tags include ≥1 per-metric champion", hasChamp);
        }
        boolean robustOrder = true;
        for (int i = 1; i < report.robustness().size(); i++) {
            if (report.robustness().get(i).frontHits() > report.robustness().get(i - 1).frontHits()) {
                robustOrder = false; break;
            }
        }
        failures += assertCond("Section 5 sorted by frontHits desc", robustOrder);

        // ─── Render output checks: report contains all five section headers ─
        String text = report.render();
        for (String header : List.of(
                "1. Top by aggregate score",
                "2. Pareto frontier across declared goals",
                "3. Auto-Pareto across auto-discovered metrics",
                "4. Per-metric champions",
                "5. Robustness ranking")) {
            failures += assertCond("rendered text contains '" + header + "'", text.contains(header));
        }

        if (failures == 0) System.out.println("\n✅ ALL BEST-LINES-REPORT CHECKS PASSED");
        else { System.out.println("\n❌ " + failures + " BEST-LINES-REPORT CHECK(S) FAILED"); System.exit(1); }
    }

    private static LineResult lookup(List<LineResult> results, int lineNo) {
        for (LineResult r : results) if (r.lineNo == lineNo) return r;
        return null;
    }

    private static double seriesExtreme(List<LineResult> results, String key, boolean min) {
        double best = min ? Double.POSITIVE_INFINITY : Double.NEGATIVE_INFINITY;
        for (LineResult r : results) {
            String v = r.features.kvPairs.get(key);
            if (v == null) continue;
            double d;
            try { d = Double.parseDouble(v.replace(',', '.').trim()); }
            catch (NumberFormatException e) { continue; }
            if (min ? (d < best) : (d > best)) best = d;
        }
        return best;
    }

    private static double parseMetric(List<LineResult> results, int lineNo, String key) {
        LineResult r = lookup(results, lineNo);
        if (r == null) return Double.NaN;
        String v = r.features.kvPairs.get(key);
        if (v == null) return Double.NaN;
        try { return Double.parseDouble(v.replace(',', '.').trim()); }
        catch (NumberFormatException e) { return Double.NaN; }
    }

    private static boolean dominates(LineResult a, LineResult b, List<OptimizationGoal> goals) {
        boolean strict = false;
        for (OptimizationGoal g : goals) {
            double va = metric(a, g.key);
            double vb = metric(b, g.key);
            if (!Double.isFinite(va) || !Double.isFinite(vb)) return false;
            boolean min = !"maximize".equals(g.mode);
            double diff = min ? va - vb : vb - va;
            if (diff > 0) return false;
            if (diff < 0) strict = true;
        }
        return strict;
    }

    private static double metric(LineResult r, String key) {
        if ("length".equals(key)) return r.features.length;
        if ("entropy".equals(key)) return r.features.entropy;
        String v = r.features.kvPairs.get(key);
        if (v == null) return Double.NaN;
        try { return Double.parseDouble(v.replace(',', '.').trim()); }
        catch (NumberFormatException e) { return Double.NaN; }
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
        @Override public void onError(String message, Throwable error) {}
    }
}
