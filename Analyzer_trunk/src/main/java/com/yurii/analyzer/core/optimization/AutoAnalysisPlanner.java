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

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineFeatures;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Auto-Analysis planner — the brain behind the GUI's "Auto-Analysis" button.
 * Given a sample of input lines, it returns a {@link Plan} describing what
 * goals to put into the Multi-Target Optimization table, whether to enable
 * executeCommands, whether to enable dynamic Python eval, and what each
 * goal's target value / weight should be.
 *
 * The planner is intentionally headless — no Swing dependency — so it can be
 * unit-tested and reused from any driver.
 */
public final class AutoAnalysisPlanner {
    private AutoAnalysisPlanner() {}

    /** How many physical lines to peek at when planning. */
    public static final int SAMPLE_LIMIT = 500;
    /** A metric key needs at least this many sightings in the sample. */
    public static final int MIN_OCCURRENCES = 3;
    /** Total weight budget split across the recommended goals. */
    public static final double WEIGHT_BUDGET = 100.0;

    /** Lower-cased key fragments that strongly imply minimisation. */
    private static final List<String> MIN_HINTS = List.of(
            "cost", "latency", "delay", "wait", "queue", "miss", "drop",
            "error", "fail", "loss", "overhead", "lag", "duration", "time",
            "size", "bytes", "kb", "mb", "gb", "memory", "ram", "footprint",
            "regret", "penalty", "attempt", "retry");
    /** Lower-cased key fragments that strongly imply maximisation. */
    private static final List<String> MAX_HINTS = List.of(
            "throughput", "qps", "rps", "tps", "ops", "bandwidth", "speed",
            "score", "quality", "accuracy", "precision", "recall", "f1",
            "uptime", "available", "success", "hit", "win", "yield",
            "coverage", "efficiency", "fitness", "reward", "utility");

    /** Heuristic detection of "this line looks runnable as a shell command". */
    private static final Pattern SHEBANG = Pattern.compile("^#!\\s*/");
    private static final List<String> COMMAND_HEADS = List.of(
            "echo ", "printf ", "cat ", "ls ", "grep ", "awk ", "sed ",
            "head ", "tail ", "find ", "curl ", "wget ", "python ",
            "python3 ", "java ", "node ", "ruby ", "perl ", "bash ",
            "sh ", "zsh ", "make ", "cmake ", "git ", "docker ", "kubectl ");

    public record GoalRecommendation(String key, String mode, double targetValue,
                                     double weight, int support, double median,
                                     double min, double max, String reason) {
        public Object[] asTableRow() {
            return new Object[]{key, mode, targetValue, weight};
        }
    }

    public record Plan(List<GoalRecommendation> goals,
                       boolean recommendExecuteCommands,
                       boolean recommendDynamicPython,
                       int sampledLines,
                       int nonEmptyLines,
                       int shellishLines,
                       int pythonEligibleLines,
                       Map<String, Integer> coverage) {

        /** Compact human-readable summary for the confirmation dialog. */
        public String renderSummary() {
            StringBuilder sb = new StringBuilder();
            sb.append("Auto-Analysis plan\n");
            sb.append("──────────────────\n");
            sb.append(String.format(Locale.ROOT,
                    "Sampled %d lines (%d non-empty).%n", sampledLines, nonEmptyLines));
            sb.append(String.format(Locale.ROOT,
                    "Shell-like lines: %d   Python-eligible lines (= and ;): %d%n",
                    shellishLines, pythonEligibleLines));
            sb.append('\n');
            if (goals.isEmpty()) {
                sb.append("No numeric metrics discovered (≥ ").append(MIN_OCCURRENCES)
                        .append(" sightings) — optimisation goals will be empty.\n");
            } else {
                sb.append("Recommended goals (").append(goals.size()).append("):\n");
                for (GoalRecommendation g : goals) {
                    sb.append(String.format(Locale.ROOT,
                            "  • %-18s mode=%-9s target=%-10.4g weight=%-5.1f  "
                                    + "n=%d  μ̃=%-10.4g range=[%g,%g]  (%s)%n",
                            g.key, g.mode, g.targetValue, g.weight, g.support,
                            g.median, g.min, g.max, g.reason));
                }
            }
            sb.append('\n');
            sb.append("Settings to apply:\n");
            sb.append("  ✔ Enable target optimization\n");
            sb.append("  ").append(recommendExecuteCommands ? "✔" : "✗")
                    .append(" Execute each line as shell command\n");
            sb.append("  ").append(recommendDynamicPython ? "✔" : "✗")
                    .append(" Dynamic Python eval (scipy)\n");
            return sb.toString();
        }
    }

    /**
     * Build a plan from a list of raw input lines. Uses an
     * {@link OptimizationAnalyzer} with no goals declared — purely for its
     * {@link OptimizationAnalyzer#extractFeatures} side-effect-free regex
     * extraction. Lines beyond {@link #SAMPLE_LIMIT} are ignored to keep the
     * planning step fast on huge inputs.
     */
    public static Plan plan(List<String> rawLines, boolean scipyAvailable) {
        if (rawLines == null) rawLines = List.of();
        OptimizationAnalyzer probe = new OptimizationAnalyzer(
                AnalyzerCore.mapper().createObjectNode(),
                /*minSupport*/ 1, /*topK*/ 1,
                /*optThreshold*/ 100.0, /*watchThreshold*/ 0.0,
                /*executeCommands*/ false, /*commandTimeout*/ 0.0,
                /*dynamicPythonEnabled*/ false);

        Map<String, List<Double>> values = new LinkedHashMap<>();
        int sampled = 0, nonEmpty = 0, shellish = 0, pyEligible = 0;

        int upper = Math.min(SAMPLE_LIMIT, rawLines.size());
        for (int i = 0; i < upper; i++) {
            String raw = rawLines.get(i);
            sampled++;
            if (raw == null || raw.isBlank()) continue;
            nonEmpty++;
            String text = raw.trim();
            if (looksShellish(text)) shellish++;
            if (text.contains("=") && text.contains(";")) pyEligible++;

            LineFeatures f = probe.extractFeatures(i + 1, raw, raw);
            for (Map.Entry<String, String> e : f.kvPairs.entrySet()) {
                String key = e.getKey();
                java.util.OptionalDouble od = AnalyzerCore.tryParseNumeric(e.getValue());
                if (od.isEmpty()) continue;
                double v = od.getAsDouble();
                if (!Double.isFinite(v)) continue;
                values.computeIfAbsent(key, k -> new ArrayList<>()).add(v);
            }
        }

        // Coverage map (sorted by descending count) — surfaces the popular
        // numeric keys so we can pick the most-informative ones first.
        Map<String, Integer> coverage = new LinkedHashMap<>();
        values.entrySet().stream()
                .sorted((a, b) -> Integer.compare(b.getValue().size(), a.getValue().size()))
                .forEach(e -> coverage.put(e.getKey(), e.getValue().size()));

        // Build recommendations.
        List<GoalRecommendation> goals = new ArrayList<>();
        for (Map.Entry<String, Integer> e : coverage.entrySet()) {
            if (e.getValue() < MIN_OCCURRENCES) continue;
            String key = e.getKey();
            List<Double> vs = values.get(key);
            String mode = inferMode(key, vs);
            double median = median(vs);
            double[] mm = minMax(vs);
            String reason = explainMode(key, mode, vs);
            // target_value defaults to median for "minimize"/"maximize" (it's
            // largely informational — the score only uses it in 'target' mode).
            // For 'target' mode we pick median as the centre of the band so the
            // user lands on something sensible without having to look at the
            // distribution first.
            goals.add(new GoalRecommendation(key, mode, median, 0.0,
                    e.getValue(), median, mm[0], mm[1], reason));
        }
        // Cap at 8 goals — beyond that the score formula gets noisy.
        if (goals.size() > 8) goals = goals.subList(0, 8);
        // Re-distribute weight budget evenly.
        if (!goals.isEmpty()) {
            double w = WEIGHT_BUDGET / goals.size();
            List<GoalRecommendation> reweighted = new ArrayList<>(goals.size());
            for (GoalRecommendation g : goals)
                reweighted.add(new GoalRecommendation(g.key, g.mode, g.targetValue,
                        round2(w), g.support, g.median, g.min, g.max, g.reason));
            goals = reweighted;
        }

        // Recommend executeCommands when at least 30% of non-empty lines look shellish.
        boolean recExec = nonEmpty > 0 && shellish * 100.0 / nonEmpty >= 30.0;
        // Recommend dynamic Python only if ≥1 line is python-eligible AND scipy is available.
        boolean recPy = pyEligible >= 1 && scipyAvailable;

        return new Plan(goals, recExec, recPy, sampled, nonEmpty, shellish, pyEligible,
                Collections.unmodifiableMap(coverage));
    }

    /** Mode inference: token-fragment match against MIN_HINTS / MAX_HINTS,
     *  with a numerical-distribution fallback when the name is uninformative.
     *  - "error_rate" → minimize  (the 'error' fragment dominates 'rate')
     *  - "throughput" → maximize  (token match)
     *  - "x_count"    → minimize  (no hint match → distribution check; if all
     *                              values are positive integers, default to
     *                              minimize, treating 'count' as a defect count;
     *                              this is conservative — user can flip in UI).
     *
     *  Promoted to public so the streaming pipeline (OnlinePareto +
     *  BalancedOptimumSelector) can use it for lazily discovered keys
     *  without re-implementing the same lexical heuristic. */
    public static String inferMode(String key, List<Double> values) {
        String lc = key.toLowerCase(Locale.ROOT);
        // Negative-affinity hints take precedence so 'error_rate' → minimize.
        for (String h : MIN_HINTS) if (lc.contains(h)) return "minimize";
        for (String h : MAX_HINTS) if (lc.contains(h)) return "maximize";
        return "minimize";
    }

    /** Convenience: returns the inferred mode as a {@link GoalSpec.Mode} enum. */
    public static GoalSpec.Mode inferModeEnum(String key) {
        return "maximize".equals(inferMode(key, List.of()))
                ? GoalSpec.Mode.MAXIMIZE : GoalSpec.Mode.MINIMIZE;
    }

    static String explainMode(String key, String mode, List<Double> values) {
        String lc = key.toLowerCase(Locale.ROOT);
        for (String h : MIN_HINTS) if (lc.contains(h)) return "name match: '" + h + "' → " + mode;
        for (String h : MAX_HINTS) if (lc.contains(h)) return "name match: '" + h + "' → " + mode;
        return "no name hint, defaulted to " + mode;
    }

    static boolean looksShellish(String text) {
        if (text == null || text.isEmpty()) return false;
        if (SHEBANG.matcher(text).find()) return true;
        if (text.startsWith("./") || text.startsWith("/usr/") || text.startsWith("/bin/")) return true;
        for (String h : COMMAND_HEADS) if (text.startsWith(h)) return true;
        return false;
    }

    static double median(List<Double> values) {
        if (values == null || values.isEmpty()) return 0.0;
        double[] a = new double[values.size()];
        for (int i = 0; i < a.length; i++) a[i] = values.get(i);
        Arrays.sort(a);
        return a.length % 2 == 1 ? a[a.length / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2.0;
    }

    static double[] minMax(List<Double> values) {
        double mn = Double.POSITIVE_INFINITY, mx = Double.NEGATIVE_INFINITY;
        for (double v : values) { if (v < mn) mn = v; if (v > mx) mx = v; }
        if (!Double.isFinite(mn)) mn = 0;
        if (!Double.isFinite(mx)) mx = 0;
        return new double[]{mn, mx};
    }

    static double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }

    /** Cheap probe — `python3 -c 'import scipy.optimize'` returns 0 if scipy
     *  is importable. Cached after the first call. */
    private static volatile Boolean SCIPY_AVAILABLE;
    public static boolean detectScipyAvailable() {
        Boolean cached = SCIPY_AVAILABLE;
        if (cached != null) return cached;
        try {
            String py = System.getProperty("os.name", "").toLowerCase(Locale.ROOT)
                    .contains("win") ? "python" : "python3";
            Process p = new ProcessBuilder(py, "-c",
                    "import importlib, sys; sys.exit(0 if importlib.util.find_spec('scipy.optimize') else 1)")
                    .redirectErrorStream(true).start();
            boolean done = p.waitFor(5, java.util.concurrent.TimeUnit.SECONDS);
            cached = done && p.exitValue() == 0;
        } catch (Exception e) {
            cached = false;
        }
        SCIPY_AVAILABLE = cached;
        return cached;
    }
}
