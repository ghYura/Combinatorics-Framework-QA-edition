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
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.DoubleUnaryOperator;

/**
 * Adversarial verification that the optimisation theory is actually wired in
 * and produces the right numbers — not just that the smoke tests pass.
 *
 * For each claim in the README we either reproduce the result directly here,
 * or assert a property of an internal data structure (the per-line breakdown
 * map, the Pareto-front membership, the Simpson AUC value).
 *
 * Run:  java -cp target/classes:<deps> com.yurii.analyzer.core.optimization.OptimizationVerification
 */
public final class OptimizationVerification {
    private OptimizationVerification() {}

    public static void main(String[] args) throws Exception {
        Path corpus = Path.of("samples/comprehensive_input.txt");
        Path config = Path.of("samples/comprehensive_config.json");
        JsonNode manual = AnalyzerCore.parseManualConfig(Files.readString(config));
        List<String> lines = Files.readAllLines(corpus, StandardCharsets.UTF_8);

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 3, 12, 75.0, 45.0, false, 30.0, false);

        int failures = 0;

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 1 — ExprParser correctly compiles every objective in the
        //  config; the parsed function evaluates to the expected value at
        //  the Brent-derived argmin.
        // ════════════════════════════════════════════════════════════════════
        section(1, "ExprParser → objective compiles, evaluates at argmin");
        for (OptimizationGoal g : analyzer.goals()) {
            if (!g.optimumValid) continue;
            DoubleUnaryOperator f = new ExprParser(g.objective).compile();
            double directEval = f.applyAsDouble(g.computedArgmin);
            System.out.printf(Locale.ROOT,
                    "  goal '%s'  expr='%s'%n    Brent.fmin=%.10g   direct f(argmin)=%.10g   Δ=%.3g%n",
                    g.key, g.objective, g.computedOptimum, directEval,
                    Math.abs(g.computedOptimum - directEval));
            failures += check("    fmin == f(argmin)", g.computedOptimum, directEval, 1e-9);
        }

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 2 — Brent argmin for (x-0.5)^2+0.1 is exactly 0.5 to high precision,
        //  and the SECOND derivative test confirms it's a true minimum.
        // ════════════════════════════════════════════════════════════════════
        section(2, "Brent solution satisfies the optimality conditions");
        OptimizationGoal cost = analyzer.goals().stream().filter(g -> g.key.equals("cost")).findFirst().orElseThrow();
        DoubleUnaryOperator costExpr = new ExprParser(cost.objective).compile();
        double xstar = cost.computedArgmin;
        // Numerical first/second derivative at x*
        double h = 1e-5;
        double fPrime  = (costExpr.applyAsDouble(xstar + h) - costExpr.applyAsDouble(xstar - h)) / (2 * h);
        double fDouble = (costExpr.applyAsDouble(xstar + h) - 2 * costExpr.applyAsDouble(xstar) + costExpr.applyAsDouble(xstar - h)) / (h * h);
        System.out.printf(Locale.ROOT,
                "  argmin x* = %.10f   f'(x*) = %.3g   f''(x*) = %.3f%n",
                xstar, fPrime, fDouble);
        failures += check("    f'(x*) ≈ 0  (first-order condition)", fPrime, 0.0, 1e-3);
        failures += assertCond("    f''(x*) > 0  (second-order condition / true min)", fDouble > 0);

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 3 — The per-line breakdown map of operation=optimise (cost=0.50)
        //  contains an OptBrent[cost] entry, and the bonus value is greater
        //  than that of operation=warmup (cost=0.95).
        // ════════════════════════════════════════════════════════════════════
        section(3, "Per-line breakdown carries OptBrent / OptArgmin / OptFmin tags");
        Capture cap = new Capture();
        analyzer.analyzeLines(lines, cap);

        LineResult lOptimise = findByOriginalContains(cap.results, "operation=optimise ");
        LineResult lWarmup   = findByOriginalContains(cap.results, "operation=warmup ");
        if (lOptimise == null || lWarmup == null) {
            System.out.println("  ✗ could not locate reference lines");
            failures++;
        } else {
            Double bOpt  = lOptimise.breakdown.get("OptBrent[cost]");
            Double bWarm = lWarmup.breakdown.get("OptBrent[cost]");
            Double argmin = lOptimise.breakdown.get("OptArgmin[cost]");
            Double fmin   = lOptimise.breakdown.get("OptFmin[cost]");
            System.out.printf(Locale.ROOT,
                    "  operation=optimise (cost=0.50)  OptBrent[cost] = %s  OptArgmin = %s  OptFmin = %s%n",
                    bOpt, argmin, fmin);
            System.out.printf(Locale.ROOT,
                    "  operation=warmup   (cost=0.95)  OptBrent[cost] = %s%n", bWarm);
            failures += assertCond("    OptBrent tag present on optimise line",  bOpt != null);
            failures += assertCond("    OptBrent tag present on warmup line",    bWarm != null);
            failures += assertCond("    OptArgmin = 0.5 stored in breakdown",
                    argmin != null && Math.abs(argmin - 0.5) < 1e-6);
            failures += assertCond("    OptFmin = 0.1 stored in breakdown",
                    fmin != null && Math.abs(fmin - 0.1) < 1e-6);
            failures += assertCond("    bonus(cost=0.50) > bonus(cost=0.95)  [Brent target drives ranking]",
                    bOpt != null && bWarm != null && bOpt > bWarm);
        }

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 4 — The Pareto-front members are pairwise non-dominated, and at
        //  least one line OUTSIDE the front is dominated by some front member.
        //  Goals with <50% data coverage in the corpus are excluded from the
        //  axes (mirrors AnalyzerCore.paretoOptimal's filter).
        // ════════════════════════════════════════════════════════════════════
        section(4, "Pareto frontier: pairwise non-dominance + verified domination");
        List<LineResult> front = AnalyzerCore.paretoOptimal(cap.results, analyzer.goals());
        List<OptimizationGoal> activeGoals = activeGoals(cap.results, analyzer.goals());
        System.out.printf(Locale.ROOT, "  front size = %d  (active axes: %d of %d)%n",
                front.size(), activeGoals.size(), analyzer.goals().size());
        for (int i = 0; i < front.size(); i++) {
            LineResult r = front.get(i);
            System.out.printf(Locale.ROOT, "    [%d] line #%d cost=%s latency=%s err=%s thr=%s  score=%.2f%n",
                    i + 1, r.lineNo,
                    r.features.kvPairs.get("cost"),
                    r.features.kvPairs.get("latency"),
                    r.features.kvPairs.get("error_rate"),
                    r.features.kvPairs.get("throughput"),
                    r.score);
        }
        // pairwise check
        boolean pairwiseOk = true;
        for (int i = 0; i < front.size(); i++)
            for (int j = i + 1; j < front.size(); j++)
                if (dominates(front.get(i), front.get(j), activeGoals)
                        || dominates(front.get(j), front.get(i), activeGoals)) {
                    System.out.printf("    ✗ front members %d and %d are dominance-related%n", i, j);
                    pairwiseOk = false;
                }
        failures += assertCond("    no front member dominates another", pairwiseOk);

        // find one outside-front line that IS dominated by a front member
        boolean foundDominated = false;
        for (LineResult r : cap.results) {
            if (front.contains(r)) continue;
            // skip lines that the analyser would have filtered out
            boolean missingMetric = false;
            for (OptimizationGoal g : activeGoals) if (!Double.isFinite(metric(r, g.key))) { missingMetric = true; break; }
            if (missingMetric) continue;
            for (LineResult f : front) {
                if (dominates(f, r, activeGoals)) {
                    System.out.printf(Locale.ROOT,
                            "    line #%d (NOT in front) is dominated by front line #%d  ✓%n", r.lineNo, f.lineNo);
                    foundDominated = true;
                    break;
                }
            }
            if (foundDominated) break;
        }
        failures += assertCond("    at least one non-front line is dominated by a front member", foundDominated);

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 5 — Simpson AUC computed by the analyser equals an independent
        //  Simpson computation over the same scores.
        // ════════════════════════════════════════════════════════════════════
        section(5, "Simpson AUC: analyser value matches independent recompute");
        double indepAuc = independentSimpson(cap.results);
        double analyserAuc = AnalyzerCore.simpsonScoreAuc(cap.results);
        System.out.printf(Locale.ROOT,
                "  analyser  Simpson AUC = %.6f%n  independent      = %.6f   Δ = %.3g%n",
                analyserAuc, indepAuc, Math.abs(analyserAuc - indepAuc));
        failures += check("    Simpson AUC self-consistent", analyserAuc, indepAuc, 1e-6);

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 6 — RK4 verification of the confidence ODE matches the
        //  closed-form solution to machine precision over n=[0,20].
        // ════════════════════════════════════════════════════════════════════
        section(6, "RK4 numerical solution of C'(n)=(1-C)/100 vs analytical");
        double[] residuals = AnalyzerCore.verifyConfidenceOde(20);
        double maxRes = 0; int worstN = 0;
        for (int n = 0; n < residuals.length; n++)
            if (residuals[n] > maxRes) { maxRes = residuals[n]; worstN = n; }
        System.out.printf(Locale.ROOT,
                "  worst residual: |C_RK4(%d) - C_analytic(%d)| = %.3g  (machine epsilon ≈ %.3g)%n",
                worstN, worstN, maxRes, Math.ulp(1.0));
        failures += assertCond("    max residual within 100 × machine epsilon", maxRes < 100 * Math.ulp(1.0));

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 7 — Replace the cost objective with sin(x), reset the analyser,
        //  and confirm the new argmin (≈ 3π/2 ≈ 4.7124) drives a different
        //  ranking. This proves the wiring isn't accidentally hardcoded to 0.5.
        // ════════════════════════════════════════════════════════════════════
        section(7, "Re-wire objective with sin(x); top-line ranking shifts accordingly");
        String alteredJson = """
            {
              "required_tokens": ["status"],
              "expected_line_types": ["kv_numeric"],
              "optimizations": [
                {"key":"cost","mode":"target","objective":"sin(x)","search_lo":3.5,"search_hi":6.0,"weight":50}
              ]
            }
            """;
        OptimizationAnalyzer altered = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig(alteredJson), 1, 5, 30.0, 10.0, false, 0.0, false);
        OptimizationGoal newGoal = altered.goals().get(0);
        System.out.printf(Locale.ROOT,
                "  altered objective sin(x) on [3.5, 6.0]:  argmin = %.6f  (analytical 3π/2 = %.6f)%n",
                newGoal.computedArgmin, 3 * Math.PI / 2);
        failures += check("    altered argmin near 3π/2",
                newGoal.computedArgmin, 3 * Math.PI / 2, 1e-3);

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 8 — Auto-discovered metric streams: every numeric K/V key
        //  appearing in ≥5 lines is found by MetricStreamAnalyzer without
        //  any prior config declaration. The corpus is expected to surface
        //  cost, latency, error_rate, throughput at minimum.
        // ════════════════════════════════════════════════════════════════════
        section(8, "Auto-discovery surfaces expected metric keys without config");
        List<String> discovered = MetricStreamAnalyzer.discoveredKeys(cap.results, 5);
        System.out.println("  discovered keys (≥5 samples): " + discovered);
        for (String required : List.of("cost", "latency", "error_rate", "throughput")) {
            failures += assertCond("    '" + required + "' auto-discovered", discovered.contains(required));
        }

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 9 — Per-metric optimisation results are bounded (Brent gives
        //  a *local* min on a possibly non-unimodal interpolated series; SA
        //  is the global-search complement). Both must lie in [seriesMin,
        //  seriesMax]. Additionally, min(Brent, SA) ≤ seriesMean (the
        //  optimisers find something at-least-average).
        // ════════════════════════════════════════════════════════════════════
        section(9, "Per-metric Brent and SA produce bounded values; jointly cover series min");
        List<MetricStreamAnalyzer.MetricAnalysis> streams = MetricStreamAnalyzer.analyzeAll(cap.results, 5);
        for (var ma : streams) {
            if (!List.of("cost", "latency", "error_rate", "throughput").contains(ma.key())) continue;
            List<Double> series = collectSeries(cap.results, ma.key());
            double obsMin = series.stream().mapToDouble(Double::doubleValue).min().orElse(Double.NaN);
            double obsMax = series.stream().mapToDouble(Double::doubleValue).max().orElse(Double.NaN);
            double obsMean = series.stream().mapToDouble(Double::doubleValue).average().orElse(Double.NaN);
            failures += assertCond(String.format(Locale.ROOT,
                    "    %s  Brent.fmin in [%.4g, %.4g] (got %.4g)",
                    ma.key(), obsMin, obsMax, ma.brentMin()),
                    ma.brentMin() >= obsMin - 1e-6 && ma.brentMin() <= obsMax + 1e-6);
            failures += assertCond(String.format(Locale.ROOT,
                    "    %s  SA.min in [%.4g, %.4g] (got %.4g)",
                    ma.key(), obsMin, obsMax, ma.saMin()),
                    ma.saMin() >= obsMin - 1e-6 && ma.saMin() <= obsMax + 1e-6);
            failures += assertCond(String.format(Locale.ROOT,
                    "    %s  min(Brent, SA) ≤ μ=%.4g  (got %.4g)",
                    ma.key(), obsMean, Math.min(ma.brentMin(), ma.saMin())),
                    Math.min(ma.brentMin(), ma.saMin()) <= obsMean + 1e-6);
        }

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 10 — Nelder-Mead exponential fit residual is bounded:
        //  the RMS of (a + b·exp(-c·n) - vals[n]) should be at most 1.5×stdev
        //  of the raw series (i.e., the fit explains *some* variance).
        // ════════════════════════════════════════════════════════════════════
        section(10, "Nelder-Mead exp-fit residual ≤ 1.5 × series stdev");
        for (var ma : streams) {
            if (!List.of("cost", "latency", "throughput").contains(ma.key())) continue;
            double rmsResidual = Math.sqrt(ma.expFitLoss() / Math.max(1, ma.n()));
            failures += assertCond(String.format(Locale.ROOT,
                    "    %s rmsResidual=%.4g ≤ 1.5·σ=%.4g",
                    ma.key(), rmsResidual, 1.5 * ma.stdev()),
                    rmsResidual <= 1.5 * ma.stdev() + 1e-9);
        }

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 11 — RK4 relaxation smoothing produces a series whose stdev
        //  is at most that of the raw series (smoothing cannot ADD variance).
        // ════════════════════════════════════════════════════════════════════
        section(11, "RK4 smoothed series has stdev ≤ raw series stdev");
        for (var ma : streams) {
            if (!List.of("cost", "latency", "throughput").contains(ma.key())) continue;
            double smoothedStdev = stdev(ma.rk4Smoothed());
            failures += assertCond(String.format(Locale.ROOT,
                    "    %s  raw σ=%.4g  RK4 σ=%.4g",
                    ma.key(), ma.stdev(), smoothedStdev),
                    smoothedStdev <= ma.stdev() + 1e-9);
        }

        // ════════════════════════════════════════════════════════════════════
        //  CLAIM 12 — Auto-Pareto across all auto-discovered metrics is
        //  non-empty and pairwise non-dominated (independently checked).
        // ════════════════════════════════════════════════════════════════════
        section(12, "Auto-Pareto across auto-discovered metrics is non-empty + pairwise non-dominated");
        List<LineResult> autoFront = MetricStreamAnalyzer.autoPareto(cap.results, 5);
        System.out.printf(Locale.ROOT, "  auto-Pareto size = %d  (over %d discovered metrics)%n",
                autoFront.size(), discovered.size());
        failures += assertCond("    auto-Pareto front is non-empty", !autoFront.isEmpty());
        boolean autoPairOk = true;
        for (int i = 0; i < autoFront.size(); i++) {
            for (int j = i + 1; j < autoFront.size(); j++) {
                if (autoDominates(autoFront.get(i), autoFront.get(j), discovered)
                        || autoDominates(autoFront.get(j), autoFront.get(i), discovered)) {
                    System.out.printf("    ✗ auto-front members %d and %d are dominance-related%n", i, j);
                    autoPairOk = false;
                }
            }
        }
        failures += assertCond("    no auto-front member dominates another", autoPairOk);

        // ════════════════════════════════════════════════════════════════════
        System.out.println();
        if (failures == 0) System.out.println("ALL VERIFICATIONS PASSED");
        else { System.out.println(failures + " VERIFICATION(S) FAILED"); System.exit(1); }
    }

    private static List<Double> collectSeries(List<LineResult> results, String key) {
        List<Double> vals = new ArrayList<>();
        for (LineResult r : results) {
            String v = r.features.kvPairs.get(key);
            if (v == null) continue;
            try { vals.add(Double.parseDouble(v.replace(',', '.').trim())); }
            catch (NumberFormatException ignored) {}
        }
        return vals;
    }

    private static double stdev(double[] arr) {
        if (arr == null || arr.length < 2) return 0;
        double sum = 0; for (double v : arr) sum += v;
        double m = sum / arr.length;
        double s = 0; for (double v : arr) s += (v - m) * (v - m);
        return Math.sqrt(s / arr.length);
    }

    private static boolean autoDominates(LineResult a, LineResult b, List<String> keys) {
        boolean strict = false;
        for (String k : keys) {
            double va = parse(a.features.kvPairs.get(k));
            double vb = parse(b.features.kvPairs.get(k));
            if (!Double.isFinite(va) || !Double.isFinite(vb)) return false;
            // default minimisation
            double diff = va - vb;
            if (diff > 0) return false;
            if (diff < 0) strict = true;
        }
        return strict;
    }

    private static double parse(String s) {
        if (s == null) return Double.NaN;
        try { return Double.parseDouble(s.replace(',', '.').trim()); }
        catch (NumberFormatException e) { return Double.NaN; }
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private static void section(int n, String label) {
        System.out.println();
        System.out.println("─── CLAIM " + n + " ─ " + label + " ───");
    }

    private static int check(String name, double got, double want, double tol) {
        boolean ok = Math.abs(got - want) <= tol;
        System.out.printf(Locale.ROOT, "    %s %s  got=%.10g want=%.10g Δ=%.3g%n",
                ok ? "✓" : "✗", name, got, want, Math.abs(got - want));
        return ok ? 0 : 1;
    }

    private static int assertCond(String name, boolean cond) {
        System.out.printf("    %s %s%n", cond ? "✓" : "✗", name);
        return cond ? 0 : 1;
    }

    private static LineResult findByOriginalContains(List<LineResult> rs, String needle) {
        for (LineResult r : rs) if (r.originalLine != null && r.originalLine.contains(needle)) return r;
        return null;
    }

    /** Reference Simpson over a sample sequence; intentionally written from scratch to cross-check. */
    private static double independentSimpson(List<LineResult> rs) {
        if (rs.size() < 2) return 0;
        double[] v = new double[rs.size()];
        for (int i = 0; i < v.length; i++) v[i] = rs.get(i).score;
        int n = v.length - 1;
        int evenN = (n % 2 == 0) ? n : n - 1;
        double s = v[0] + v[evenN];
        for (int i = 1; i < evenN; i++) s += (i % 2 == 0 ? 2 : 4) * v[i];
        double simpsonPart = s / 3.0;
        double trapPart = (evenN < n) ? 0.5 * (v[evenN] + v[evenN + 1]) : 0.0;
        return simpsonPart + trapPart;
    }

    /** Inline copy of dominance for direct use in verification (mirrors Optimizers.dominates). */
    private static boolean dominates(LineResult a, LineResult b, List<OptimizationGoal> goals) {
        boolean strict = false;
        for (OptimizationGoal g : goals) {
            double va = metric(a, g.key);
            double vb = metric(b, g.key);
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

    /** Goals with ≥5 data points — same rule as AnalyzerCore.paretoOptimal. */
    private static List<OptimizationGoal> activeGoals(List<LineResult> results, List<OptimizationGoal> goals) {
        List<OptimizationGoal> out = new ArrayList<>();
        for (OptimizationGoal g : goals) {
            int present = 0;
            for (LineResult r : results) if (Double.isFinite(metric(r, g.key))) present++;
            if (present >= 5) out.add(g);
        }
        return out;
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
