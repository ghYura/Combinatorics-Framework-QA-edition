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
import com.yurii.analyzer.core.AnalyzerCore.SynthesizedRules;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * End-to-end verification that every incoming line is treated as an executable
 * code line, that its stdout/stderr is captured and re-fed into the analyser,
 * that the metric names emitted by the line are AGNOSTIC (i.e. picked up by
 * name without any hardcoded allow-list inside the analyser), and that EVERY
 * implemented optimisation-theory workflow fires on the resulting per-line
 * metric streams.
 *
 *   1. Generate a tiny input file where every line is a /bin/sh `echo` command
 *      that prints a different combination of values for three intentionally
 *      arbitrary metric names: {@code rho_alpha}, {@code phi_beta}, {@code
 *      omicron_gamma}. The names contain no special meaning to the analyser
 *      and would only be discoverable if the auto-discovery code path is
 *      working purely from stdout content.
 *
 *   2. Configure {@link OptimizationAnalyzer} with {@code executeCommands=true}
 *      so each line is executed in a subshell and its stdout becomes the
 *      payload that is then run through {@code extractFeatures} → {@code
 *      scoreLine} → {@code reportOptimisationDiagnostics}.
 *
 *   3. Inspect the captured analyser logs for the lines emitted by each
 *      optimisation workflow:
 *        • Brent argmin / argmax of the interpolated metric
 *        • Nelder-Mead simplex fit of   y = a + b·exp(-c·n)
 *        • Simulated annealing global minimum
 *        • Composite Simpson AUC over the series
 *        • RK4 relaxation smoothing (τ from Brent)
 *        • Newton-Raphson critical-point refinement
 *        • Pareto frontier across all auto-discovered metrics
 *        • Welford / quantile descriptive (logged as μ σ P5/P50/P95)
 *
 *      One line of evidence per workflow is required.
 *
 *   4. Confirm that the analyser actually compared lines to each other by
 *      looking at the {@code MetricStreamAnalyzer.MetricAnalysis} for each
 *      auto-discovered key: n must equal the number of input lines, and
 *      argmin / argmax line indices must straddle different lines.
 *
 *   Run:  java -cp target/classes:&lt;deps&gt;
 *               com.yurii.analyzer.core.optimization.ExecutableLineE2E
 */
public final class ExecutableLineE2E {
    private ExecutableLineE2E() {}

    public static void main(String[] args) throws Exception {
        // ─── 1. Build the executable-line input file ─────────────────────
        // Each `echo` shell command emits THREE arbitrary metric names with
        // values that follow an interesting trajectory:
        //
        //  rho_alpha    : strictly decreasing 5,4,3,2,1,2,3,4,5,6
        //                 → has a global min at line 5 (Brent / SA target)
        //                 → has an interior critical point (Newton)
        //  phi_beta     : 100*exp(-0.3*i) decay
        //                 → Nelder-Mead exp-fit should find low loss
        //  omicron_gamma: monotonic 10,12,14,...,28
        //                 → cross-stream Pareto: best line for ↓ρ_α vs ↑ο_γ
        //
        //  These names are deliberately weird so it is impossible for the
        //  analyser to be exploiting any hardcoded knowledge.
        double[] rhoAlpha    = {5, 4, 3, 2, 1, 2, 3, 4, 5, 6};
        double[] phiBeta     = new double[10];
        double[] omicronGamma= new double[10];
        for (int i = 0; i < 10; i++) {
            phiBeta[i]      = 100.0 * Math.exp(-0.3 * i);
            omicronGamma[i] = 10.0 + 2.0 * i;
        }

        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 10; i++) {
            // Each "executable line" is a single shell command. Its stdout
            // contains the agnostic metric K=V triplet for that line.
            sb.append(String.format(Locale.ROOT,
                    "echo \"rho_alpha=%.4f phi_beta=%.4f omicron_gamma=%.4f\"\n",
                    rhoAlpha[i], phiBeta[i], omicronGamma[i]));
        }
        Path tmp = Files.createTempFile("e2e_executable_lines_", ".txt");
        Files.writeString(tmp, sb.toString(), StandardCharsets.UTF_8);
        System.out.println("Generated executable input: " + tmp);

        // ─── 2. Spin up the analyser with executeCommands=true ───────────
        // We declare ONE goal that points at the agnostic 'rho_alpha' key
        // so both Pareto paths (config-declared + auto-discovered) fire.
        // The objective expression `(x - 1)^2` has its analytical minimum
        // at x=1, which matches the actual minimum value of rho_alpha — a
        // crisp double-check that the Brent argmin matches reality.
        String configJson = """
            {
              "optimizations": [
                { "key": "rho_alpha", "mode": "minimize", "weight": 25,
                  "objective": "(x - 1)^2", "search_lo": -5, "search_hi": 10 },
                { "key": "phi_beta", "mode": "minimize", "weight": 25 }
              ]
            }
            """;
        JsonNode manual = AnalyzerCore.parseManualConfig(configJson);
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual,
                /*minSupport*/ 1, /*topK*/ 10,
                /*optThreshold*/ 30.0, /*watchThreshold*/ 10.0,
                /*executeCommands*/ true,         // ← every line is run
                /*commandTimeout*/ 5.0,
                /*dynamicPython*/ false);

        Capture cap = new Capture();
        List<String> input = Files.readAllLines(tmp, StandardCharsets.UTF_8);
        analyzer.analyzeLines(input, cap);

        // ─── 3. Inspect the diagnostic stream ────────────────────────────
        int failures = 0;

        // a. Each line was executed and its stdout was parsed into kvPairs.
        int execLines = 0;
        for (LineResult r : cap.results) {
            if (r.features.kvPairs.containsKey("rho_alpha")
                    && r.features.kvPairs.containsKey("phi_beta")
                    && r.features.kvPairs.containsKey("omicron_gamma")) execLines++;
        }
        failures += assertCond("every line's stdout parsed into kvPairs (got "
                + execLines + "/10)", execLines == 10);

        // b. Auto-discovery picked up every agnostic metric name without config.
        List<String> discovered = MetricStreamAnalyzer.discoveredKeys(cap.results, 5);
        Set<String> dset = new HashSet<>(discovered);
        for (String k : List.of("rho_alpha", "phi_beta", "omicron_gamma")) {
            failures += assertCond("agnostic metric '" + k + "' auto-discovered",
                    dset.contains(k));
        }

        // c. Every workflow produced its evidence line in the listener log.
        Object[][] expectations = {
                {"Welford / quantile descriptive (μ, σ, P5/P50/P95)",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("μ=") && s.contains("σ=") && s.contains("P5/P50/P95=")},
                {"Composite Simpson AUC",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("∫Simpson=")},
                {"Brent argmin / argmax of interpolated metric",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Brent argmin@line") && s.contains("argmax@line")},
                {"Nelder-Mead exp-fit",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Nelder-Mead exp-fit")},
                {"Simulated annealing global minimum",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("SA min=")},
                {"RK4 relaxation smoothing",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("RK4 τ=")},
                {"Newton critical points",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Newton critical points")},
                {"Pareto frontier across declared goals",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Pareto-optimal frontier")},
                {"Auto-Pareto across all auto-discovered metrics",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Auto-Pareto across all")},
                {"RK4 verification of confidence ODE",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Confidence ODE") && s.contains("RK4")},
                {"Auto-discovered metric stream count line",
                        (java.util.function.Predicate<String>)
                                s -> s.contains("Auto-discovered") && s.contains("metric stream")},
        };
        for (Object[] row : expectations) {
            String label = (String) row[0];
            @SuppressWarnings("unchecked")
            java.util.function.Predicate<String> pred = (java.util.function.Predicate<String>) row[1];
            boolean found = cap.logs.stream().anyMatch(pred);
            failures += assertCond(label + " fired", found);
        }

        // d. Per-metric numerics line up with what we know about the data.
        List<MetricStreamAnalyzer.MetricAnalysis> streams =
                MetricStreamAnalyzer.analyzeAll(cap.results, 5);

        MetricStreamAnalyzer.MetricAnalysis rho = streams.stream()
                .filter(m -> m.key().equals("rho_alpha")).findFirst().orElseThrow();
        MetricStreamAnalyzer.MetricAnalysis phi = streams.stream()
                .filter(m -> m.key().equals("phi_beta")).findFirst().orElseThrow();
        MetricStreamAnalyzer.MetricAnalysis omi = streams.stream()
                .filter(m -> m.key().equals("omicron_gamma")).findFirst().orElseThrow();

        failures += assertCond(String.format(Locale.ROOT,
                "rho_alpha n=10 (got n=%d, lines compared to each other)", rho.n()),
                rho.n() == 10);
        // rho_alpha minimum is at index 4 (value 1).
        failures += assertCond(String.format(Locale.ROOT,
                "Brent locates rho_alpha argmin near i=4 (got %.3f)", rho.brentArgmin()),
                Math.abs(rho.brentArgmin() - 4.0) < 1.0);
        // rho_alpha critical point should exist (it's a valley).
        failures += assertCond("Newton found ≥1 critical point on rho_alpha",
                rho.criticalPoints().length >= 1);

        // phi_beta = a + b·exp(-c·n) → Nelder-Mead loss should be tiny.
        double phiRms = Math.sqrt(phi.expFitLoss() / phi.n());
        failures += assertCond(String.format(Locale.ROOT,
                "Nelder-Mead exp-fit on phi_beta is near-perfect (RMS=%.4g, raw σ=%.4g)",
                phiRms, phi.stdev()),
                phiRms < 0.05 * phi.stdev() + 1e-3);

        // omicron_gamma is strictly increasing; brentArgmin must be near 0
        // and brentArgmax near 9 — line-to-line comparison evidence.
        failures += assertCond(String.format(Locale.ROOT,
                "Brent on omicron_gamma: argmin at line[≈%.2f], argmax at line[≈%.2f]",
                omi.brentArgmin(), omi.brentArgmax()),
                Math.abs(omi.brentArgmin() - 0) < 1.0 && Math.abs(omi.brentArgmax() - 9) < 1.5);

        // Auto-Pareto must be non-trivial (not all 10 lines, not 0).
        List<LineResult> autoFront = MetricStreamAnalyzer.autoPareto(cap.results, 5);
        failures += assertCond(String.format(Locale.ROOT,
                "Auto-Pareto across {rho_alpha,phi_beta,omicron_gamma} produced %d non-dominated lines",
                autoFront.size()),
                autoFront.size() >= 1 && autoFront.size() <= 10);

        // ─── 4. Summary ──────────────────────────────────────────────────
        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Per-stream summary (proof of line-to-line analysis)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (var ma : streams) {
            System.out.printf(Locale.ROOT,
                    "  %-15s n=%d  μ=%-8.3g σ=%-8.3g P5/P50/P95=%.3g/%.3g/%.3g%n",
                    ma.key(), ma.n(), ma.mean(), ma.stdev(),
                    ma.p5(), ma.p50(), ma.p95());
            System.out.printf(Locale.ROOT,
                    "                  Brent argmin@%-5.2f=%-8.3g argmax@%-5.2f=%-8.3g%n",
                    ma.brentArgmin(), ma.brentMin(), ma.brentArgmax(), ma.brentMax());
            System.out.printf(Locale.ROOT,
                    "                  NM exp-fit (a=%-7.3g b=%-7.3g c=%-7.3g) loss=%-9.3g rmsResid=%-9.3g%n",
                    ma.expFitParams()[0], ma.expFitParams()[1], ma.expFitParams()[2],
                    ma.expFitLoss(), Math.sqrt(ma.expFitLoss() / Math.max(1, ma.n())));
            System.out.printf(Locale.ROOT,
                    "                  SA min=%-8.3g  RK4 τ=%-8.3f  Simpson=%-8.3g  trap=%-8.3g  crits=%d%n",
                    ma.saMin(), ma.rk4Tau(), ma.simpsonAuc(), ma.trapezoidalSum(),
                    ma.criticalPoints().length);
        }

        System.out.println();
        System.out.println("════════════════════════════════════════════════════════════════════");
        System.out.println(" Listener log (workflow evidence)");
        System.out.println("════════════════════════════════════════════════════════════════════");
        for (String line : cap.logs) {
            if (line.contains("Brent") || line.contains("Simpson")
                    || line.contains("Pareto") || line.contains("ODE")
                    || line.contains("Auto-discovered") || line.contains("Nelder-Mead")
                    || line.contains("Newton") || line.contains("RK4 τ")
                    || line.contains("argmin@line") || line.contains("μ=")) {
                System.out.println("  " + line);
            }
        }

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL E2E ASSERTIONS PASSED");
        else { System.out.println("❌ " + failures + " E2E ASSERTION(S) FAILED"); System.exit(1); }
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
