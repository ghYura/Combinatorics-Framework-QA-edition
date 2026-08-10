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

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.KeyStats;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Picks ONE candidate from a Pareto front using a scalarizing function — the
 * answer to "what's the BALANCED optimum across these metrics?"  This is the
 * compromise-programming layer that sits on top of multi-objective Pareto
 * extraction.
 *
 * Three strategies are implemented:
 *
 *   1. {@link #weightedSum} — classic Σ w_i · normalize(deviation_i).
 *      Cheap, intuitive, but may miss optima on non-convex Pareto fronts.
 *
 *   2. {@link #tchebycheff} — min max w_i · normalize(deviation_i).
 *      Provably reaches every Pareto-optimal point on any front (convex or not).
 *      The "fairest" pick under min-max regret.
 *
 *   3. {@link #distanceToIdeal} — min Euclidean distance to the per-axis-best
 *      utopia point in normalised space.  Geometrically the most intuitive
 *      "balance" interpretation; well-defined even with mixed MIN/MAX/TARGET.
 *
 * All three operate on the **Pareto front** (not the full corpus) — by the
 * fundamental theorem, the scalarization optimum is Pareto-optimal under
 * positive weights, so restricting the search to the front is exact and
 * cheap.  Normalisation uses the min/max from {@link KeyStats}, which spans
 * the entire observed corpus.
 *
 * Returns {@link Selection} with the chosen LineResult, the achieved
 * scalarized score, and a per-axis breakdown (showing how each metric
 * contributed) so the user can see WHY this candidate was picked.
 */
public final class BalancedOptimumSelector {
    private BalancedOptimumSelector() {}

    public record Selection(
            String strategy,
            LineResult chosen,
            double score,
            Map<String, Double> perAxisContribution,
            String reason) {

        public String render() {
            StringBuilder sb = new StringBuilder();
            String snippet = chosen == null ? "(null)" :
                    (chosen.originalLine == null ? "" : chosen.originalLine);
            if (snippet.length() > 80) snippet = snippet.substring(0, 77) + "...";
            sb.append(String.format(Locale.ROOT,
                    "  [%s]   line #%-7d  score=%.4f%n",
                    strategy, chosen == null ? -1 : chosen.lineNo, score));
            sb.append("    ").append(snippet).append('\n');
            for (Map.Entry<String, Double> e : perAxisContribution.entrySet()) {
                sb.append(String.format(Locale.ROOT,
                        "      %-20s contrib=%.4f%n", e.getKey(), e.getValue()));
            }
            return sb.toString();
        }
    }

    /** Weighted sum: argmin Σ w_i · norm_i  where norm_i ∈ [0,1] is the
     *  fraction of the corpus range above the candidate's deviation on axis i.
     *  Lower score = better balance. */
    public static Selection weightedSum(List<LineResult> front,
                                        Map<String, KeyStats> stats,
                                        List<GoalSpec> goals) {
        return scalarize("weighted-sum", front, stats, goals,
                (axisContribs) -> axisContribs.values().stream().mapToDouble(Double::doubleValue).sum());
    }

    /** Tchebycheff: argmin max_i w_i · norm_i.  Robust on non-convex fronts. */
    public static Selection tchebycheff(List<LineResult> front,
                                        Map<String, KeyStats> stats,
                                        List<GoalSpec> goals) {
        return scalarize("tchebycheff", front, stats, goals,
                (axisContribs) -> axisContribs.values().stream().mapToDouble(Double::doubleValue).max().orElse(0.0));
    }

    /** Euclidean distance to ideal: argmin √(Σ w_i · norm_i²). */
    public static Selection distanceToIdeal(List<LineResult> front,
                                             Map<String, KeyStats> stats,
                                             List<GoalSpec> goals) {
        return scalarize("distance-to-ideal", front, stats, goals,
                (axisContribs) -> {
                    double s = 0;
                    for (double v : axisContribs.values()) s += v * v;
                    return Math.sqrt(s);
                });
    }

    /** Run all three strategies. */
    public static List<Selection> all(List<LineResult> front,
                                      Map<String, KeyStats> stats,
                                      List<GoalSpec> goals) {
        List<Selection> out = new ArrayList<>(3);
        out.add(weightedSum(front, stats, goals));
        out.add(tchebycheff(front, stats, goals));
        out.add(distanceToIdeal(front, stats, goals));
        return out;
    }

    @FunctionalInterface
    private interface Combiner { double combine(Map<String, Double> axisContribs); }

    private static Selection scalarize(String name,
                                        List<LineResult> front,
                                        Map<String, KeyStats> stats,
                                        List<GoalSpec> goals,
                                        Combiner combiner) {
        if (front == null || front.isEmpty() || goals == null || goals.isEmpty())
            return new Selection(name, null, Double.NaN, Map.of(), "empty front or no goals");

        // Filter out goals whose axis has no observations (KeyStats absent).
        List<GoalSpec> activeGoals = new ArrayList<>();
        for (GoalSpec g : goals) {
            KeyStats ks = stats.get(g.key());
            if (ks != null && ks.n > 0) activeGoals.add(g);
        }
        if (activeGoals.isEmpty())
            return new Selection(name, null, Double.NaN, Map.of(), "no active goal axes in corpus");

        LineResult bestCand = null;
        double bestScore = Double.POSITIVE_INFINITY;
        Map<String, Double> bestContrib = Map.of();

        for (LineResult r : front) {
            Map<String, Double> contribs = new LinkedHashMap<>();
            boolean usable = true;
            for (GoalSpec g : activeGoals) {
                KeyStats ks = stats.get(g.key());
                Double v = parse(r, g.key());
                if (v == null || !Double.isFinite(v)) { usable = false; break; }
                // normalise the deviation into [0, 1] using the corpus range
                // of deviations on this axis.
                double devCand   = g.deviation(v);
                double devMin    = g.deviation(g.mode() == GoalSpec.Mode.MAXIMIZE ? ks.max : ks.min);
                double devMax    = g.deviation(g.mode() == GoalSpec.Mode.MAXIMIZE ? ks.min : ks.max);
                if (g.mode() == GoalSpec.Mode.TARGET) {
                    // For TARGET: best deviation is 0 (at-target); worst is the
                    // corner of the [min, max] range farthest from target.
                    devMin = 0.0;
                    devMax = Math.max(Math.abs(ks.max - g.targetValue()),
                                      Math.abs(ks.min - g.targetValue()));
                }
                double range = devMax - devMin;
                double norm  = (range <= 1e-15) ? 0.0
                              : Math.max(0.0, Math.min(1.0, (devCand - devMin) / range));
                contribs.put(g.key(), g.weight() * norm);
            }
            if (!usable) continue;
            double s = combiner.combine(contribs);
            if (s < bestScore) {
                bestScore = s;
                bestCand = r;
                bestContrib = contribs;
            }
        }

        if (bestCand == null)
            return new Selection(name, null, Double.NaN, Map.of(), "no usable front member (all NaN)");

        return new Selection(name, bestCand, bestScore,
                Collections.unmodifiableMap(bestContrib),
                "scalarized over " + activeGoals.size() + " active axes via " + name);
    }

    private static Double parse(LineResult r, String key) {
        if ("length".equals(key))  return (double) r.features.length;
        if ("entropy".equals(key)) return r.features.entropy;
        String s = r.features.kvPairs.get(key);
        if (s == null) return null;
        java.util.OptionalDouble od = AnalyzerCore.tryParseNumeric(s);
        return od.isPresent() ? od.getAsDouble() : null;
    }
}
