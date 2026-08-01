package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.CorpusProfile;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationGoal;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Calibrated "best lines" report — adds the optimization-theory verdicts to
 * the Summary panel after analysis completes.  This is what turns the raw
 * per-line score table into a curated "here are the proposed best lines and
 * why" answer that a semi-AI tool is expected to produce.
 *
 * The report consists of five sections, each comparing every line to every
 * other line via a different optimisation lens:
 *
 *   1. Highest aggregate score              (scalar ranking)
 *   2. Pareto frontier across declared      (multi-objective, user-supplied
 *      optimisation goals                    weights)
 *   3. Auto-Pareto frontier across all      (multi-objective, no config —
 *      auto-discovered numeric metrics       agnostic line-to-line analysis)
 *   4. Per-metric champions                 (Brent argmin / argmax of each
 *                                            auto-discovered stream)
 *   5. Robustness ranking                   (how many of fronts 1-4 each
 *                                            line survives — multi-criteria
 *                                            consensus)
 *
 * The reporter is purely a read-only consumer of {@link LineResult}; it never
 * mutates the corpus, never re-runs scoring, and is therefore safe to invoke
 * either in-memory or on a DB-pulled diagnostic slice.
 */
public final class BestLinesReporter {
    private BestLinesReporter() {}

    /** Cap how many lines each section names so the Summary panel stays
     *  readable. The internal computations still run on the full set. */
    public static final int TOP_N = 5;

    /** A line surfaced in one of the report's sections.
     *
     *  <p>{@code crowdingDistance} carries the front-diversity metric for
     *  Pareto-front members (declared-goal section + auto-Pareto section).
     *  Semantics are algorithm-polymorphic:</p>
     *  <ul>
     *    <li>Under {@link FrontAlgorithm#NSGA_II} — the original NSGA-II
     *        crowding distance.  Larger = sparser neighbourhood.
     *        {@link Double#POSITIVE_INFINITY} marks axis-boundary members.</li>
     *    <li>Under {@link FrontAlgorithm#NSGA_III} — perpendicular distance
     *        to the candidate's nearest Das-Dennis reference direction.
     *        Smaller = better-aligned with that axial direction.  No
     *        {@code +∞} sentinel; all finite for valid candidates.</li>
     *    <li>Under {@link FrontAlgorithm#SPEA2} — distance to the candidate's
     *        {@code k}-th nearest neighbour in deviation space ({@code k = √N}).
     *        Bigger = more isolated = more preserved in environmental
     *        truncation.  Always finite + non-negative.</li>
     *    <li>Under {@link FrontAlgorithm#MOEA_D} — best Tchebycheff scalar
     *        value across the structured weight grid.  Smaller = better-
     *        aligned with one of the decomposition directions (not strictly
     *        a "diversity" metric, but the canonical per-candidate MOEA/D
     *        fitness; surfaced here for symmetry with the other algorithms).</li>
     *    <li>Under {@link FrontAlgorithm#PARETO} — left as {@link Double#NaN}
     *        (the legacy batch path doesn't compute diversity).</li>
     *  </ul>
     *  <p>Non-Pareto sections (top-by-score, robustness ranks) always leave
     *  this field {@link Double#NaN}.</p> */
    public record LineMention(int lineNo, double score, String decision,
                              String lineType, String snippet,
                              double crowdingDistance) {

        /** Backwards-compatible 5-arg constructor: {@code crowdingDistance}
         *  defaults to {@link Double#NaN} (= "not a Pareto front member"). */
        public LineMention(int lineNo, double score, String decision,
                           String lineType, String snippet) {
            this(lineNo, score, decision, lineType, snippet, Double.NaN);
        }
    }

    public record MetricChampion(String key, int n,
                                 double min, double argminLineApprox, int argminLine,
                                 double max, double argmaxLineApprox, int argmaxLine) {}

    public record Report(
            List<LineMention>      topByScore,
            List<LineMention>      declaredGoalPareto,
            List<LineMention>      autoPareto,
            List<MetricChampion>   metricChampions,
            List<RobustnessRank>   robustness,
            int                    totalLines,
            int                    declaredGoalCount,
            int                    autoMetricCount) {

        /** Pretty-print for direct injection into the Summary text area. */
        public String render() {
            StringBuilder sb = new StringBuilder();
            sb.append('\n');
            sb.append("════════════════════════════════════════════════════════════════════\n");
            sb.append(" Calibrated best-lines report (Optimisation-theory verdict)\n");
            sb.append("════════════════════════════════════════════════════════════════════\n");
            sb.append(String.format(Locale.ROOT,
                    "  corpus=%d lines   declared goals=%d   auto-discovered metrics=%d%n",
                    totalLines, declaredGoalCount, autoMetricCount));

            renderSection(sb, "1. Top by aggregate score",
                    "scalar ranking via the weighted score", topByScore);
            renderSection(sb, "2. Pareto frontier across declared goals",
                    "multi-objective, no line dominates another on every axis",
                    declaredGoalPareto);
            renderSection(sb, "3. Auto-Pareto across auto-discovered metrics",
                    "agnostic, no config, every numeric K=V key as an axis",
                    autoPareto);

            sb.append('\n');
            sb.append("4. Per-metric champions (Brent argmin / argmax of each stream)\n");
            sb.append("   — line index where each metric's stream achieves its extremum\n");
            if (metricChampions.isEmpty()) {
                sb.append("   (no auto-discovered streams)\n");
            } else {
                for (MetricChampion c : metricChampions) {
                    sb.append(String.format(Locale.ROOT,
                            "   • %-18s  argmin=%.4g @line#%d (Brent x≈%.2f)   "
                                    + "argmax=%.4g @line#%d (Brent x≈%.2f)%n",
                            c.key, c.min, c.argminLine, c.argminLineApprox,
                            c.max, c.argmaxLine, c.argmaxLineApprox));
                }
            }

            sb.append('\n');
            sb.append("5. Robustness ranking — lines surviving the most fronts\n");
            sb.append("   — best-of-many-criteria consensus; 4 = strictly dominant\n");
            if (robustness.isEmpty()) {
                sb.append("   (no candidates)\n");
            } else {
                int shown = 0;
                for (RobustnessRank r : robustness) {
                    if (shown++ >= TOP_N) break;
                    sb.append(String.format(Locale.ROOT,
                            "   • line #%-5d  appears in %d/%d fronts (%s)   score=%.2f  type=%-10s  %s%n",
                            r.lineNo, r.frontHits, r.maxFronts, String.join(",", r.fronts),
                            r.score, r.lineType, r.snippet));
                }
                if (robustness.size() > TOP_N)
                    sb.append("   … (").append(robustness.size() - TOP_N).append(" more)\n");
            }
            return sb.toString();
        }

        private void renderSection(StringBuilder sb, String header, String hint,
                                   List<LineMention> rows) {
            sb.append('\n').append(header).append('\n');
            sb.append("   — ").append(hint).append('\n');
            if (rows.isEmpty()) {
                sb.append("   (empty)\n");
                return;
            }
            int shown = 0;
            for (LineMention m : rows) {
                if (shown++ >= TOP_N) break;
                // Crowding distance only shown when finite — boundary members
                // get +∞ (annotated as such), non-front sections leave it NaN.
                String crowd = !Double.isNaN(m.crowdingDistance)
                        ? "  crowd=" + (Double.isInfinite(m.crowdingDistance)
                                        ? "∞"
                                        : String.format(Locale.ROOT, "%.3g", m.crowdingDistance))
                        : "";
                sb.append(String.format(Locale.ROOT,
                        "   • line #%-5d  score=%.2f  decision=%-6s  type=%-10s%s  %s%n",
                        m.lineNo, m.score, m.decision, m.lineType, crowd, m.snippet));
            }
            if (rows.size() > TOP_N)
                sb.append("   … (").append(rows.size() - TOP_N).append(" more)\n");
        }
    }

    public record RobustnessRank(int lineNo, int frontHits, int maxFronts,
                                 List<String> fronts, double score, String lineType,
                                 String snippet) {}

    /** Build the report from an in-memory results list, using the project
     *  default front algorithm ({@link FrontAlgorithm#DEFAULT}, currently
     *  NSGA-II — adds crowding distance to front members). */
    public static Report build(CorpusProfile profile, List<LineResult> results,
                               List<OptimizationGoal> goals) {
        return build(profile, results, goals, FrontAlgorithm.DEFAULT);
    }

    /** As {@link #build(CorpusProfile, List, List)} but with explicit
     *  algorithm selection.  PARETO suppresses crowding info (front members
     *  get NaN); NSGA_II populates it. */
    public static Report build(CorpusProfile profile, List<LineResult> results,
                               List<OptimizationGoal> goals, FrontAlgorithm algo) {
        if (results == null) results = List.of();
        if (goals == null)   goals   = List.of();
        if (algo == null)    algo    = FrontAlgorithm.DEFAULT;
        int total = results.size();

        // 1. Top by aggregate score.
        List<LineMention> topScore = results.stream()
                .sorted(Comparator.comparingDouble((LineResult r) -> r.score).reversed())
                .limit(TOP_N * 2L)   // keep a bit extra for the robustness pass
                .map(BestLinesReporter::mention)
                .toList();

        // 2. Declared-goal Pareto.  NSGA-II / NSGA-III run the ranked path so
        //    we can populate a per-front diversity metric (crowding distance
        //    or perpendicular-distance-to-reference) into LineMention; PARETO
        //    uses the legacy O(N²) batch path and leaves diversity as NaN.
        //    LineMention.crowdingDistance carries crowding under NSGA-II and
        //    perpendicular distance under NSGA-III — same field, algorithm-
        //    polymorphic semantics documented on the record.
        List<LineResult> declaredFront;
        java.util.Map<Integer, Double> declaredCrowding = new java.util.HashMap<>();
        if (goals.isEmpty()) {
            declaredFront = List.of();
        } else if (algo == FrontAlgorithm.NSGA_II) {
            List<NsgaII.Ranked<LineResult>> declaredRanked =
                    AnalyzerCore.paretoOptimalRanked(results, goals);
            for (NsgaII.Ranked<LineResult> rk : declaredRanked)
                declaredCrowding.put(rk.item().lineNo, rk.crowdingDistance());
            declaredFront = declaredRanked.stream().map(NsgaII.Ranked::item).toList();
        } else if (algo == FrontAlgorithm.NSGA_III) {
            List<NsgaIII.Ranked<LineResult>> declaredRanked =
                    AnalyzerCore.paretoOptimalRankedNsgaIII(results, goals);
            for (NsgaIII.Ranked<LineResult> rk : declaredRanked)
                declaredCrowding.put(rk.item().lineNo, rk.perpendicularDistance());
            declaredFront = declaredRanked.stream().map(NsgaIII.Ranked::item).toList();
        } else if (algo == FrontAlgorithm.SPEA2) {
            List<Spea2.Ranked<LineResult>> declaredRanked =
                    AnalyzerCore.paretoOptimalRankedSpea2(results, goals);
            for (Spea2.Ranked<LineResult> rk : declaredRanked)
                declaredCrowding.put(rk.item().lineNo, rk.kNearestDistance());
            declaredFront = declaredRanked.stream().map(Spea2.Ranked::item).toList();
        } else if (algo == FrontAlgorithm.MOEA_D) {
            List<MoeaD.Ranked<LineResult>> declaredRanked =
                    AnalyzerCore.paretoOptimalRankedMoeaD(results, goals);
            for (MoeaD.Ranked<LineResult> rk : declaredRanked)
                declaredCrowding.put(rk.item().lineNo, rk.bestTchebycheff());
            declaredFront = declaredRanked.stream().map(MoeaD.Ranked::item).toList();
        } else {
            declaredFront = AnalyzerCore.paretoOptimal(results, goals, algo);
        }
        List<LineMention> declared = declaredFront.stream()
                .sorted(Comparator.comparingDouble((LineResult r) -> r.score).reversed())
                .map(r -> mention(r, declaredCrowding.getOrDefault(r.lineNo, Double.NaN)))
                .toList();

        // 3. Auto-Pareto across auto-discovered numeric metrics — same
        //    NSGA-II / NSGA-III treatment so the auto-front members are also
        //    annotated with their diversity metric when applicable.
        List<LineResult> autoFront;
        java.util.Map<Integer, Double> autoCrowding = new java.util.HashMap<>();
        if (algo == FrontAlgorithm.NSGA_II) {
            List<NsgaII.Ranked<LineResult>> autoRanked =
                    MetricStreamAnalyzer.autoParetoRanked(results, 5);
            for (NsgaII.Ranked<LineResult> rk : autoRanked)
                autoCrowding.put(rk.item().lineNo, rk.crowdingDistance());
            autoFront = autoRanked.stream().map(NsgaII.Ranked::item).toList();
        } else if (algo == FrontAlgorithm.NSGA_III) {
            List<NsgaIII.Ranked<LineResult>> autoRanked =
                    MetricStreamAnalyzer.autoParetoRankedNsgaIII(results, 5);
            for (NsgaIII.Ranked<LineResult> rk : autoRanked)
                autoCrowding.put(rk.item().lineNo, rk.perpendicularDistance());
            autoFront = autoRanked.stream().map(NsgaIII.Ranked::item).toList();
        } else if (algo == FrontAlgorithm.SPEA2) {
            List<Spea2.Ranked<LineResult>> autoRanked =
                    MetricStreamAnalyzer.autoParetoRankedSpea2(results, 5);
            for (Spea2.Ranked<LineResult> rk : autoRanked)
                autoCrowding.put(rk.item().lineNo, rk.kNearestDistance());
            autoFront = autoRanked.stream().map(Spea2.Ranked::item).toList();
        } else if (algo == FrontAlgorithm.MOEA_D) {
            List<MoeaD.Ranked<LineResult>> autoRanked =
                    MetricStreamAnalyzer.autoParetoRankedMoeaD(results, 5);
            for (MoeaD.Ranked<LineResult> rk : autoRanked)
                autoCrowding.put(rk.item().lineNo, rk.bestTchebycheff());
            autoFront = autoRanked.stream().map(MoeaD.Ranked::item).toList();
        } else {
            autoFront = MetricStreamAnalyzer.autoPareto(results, 5, algo);
        }
        List<LineMention> auto = autoFront.stream()
                .sorted(Comparator.comparingDouble((LineResult r) -> r.score).reversed())
                .map(r -> mention(r, autoCrowding.getOrDefault(r.lineNo, Double.NaN)))
                .toList();

        // 4. Per-metric champions.
        List<MetricStreamAnalyzer.MetricAnalysis> streams =
                MetricStreamAnalyzer.analyzeAll(results, 5);
        List<MetricChampion> champs = new ArrayList<>(streams.size());
        for (var ma : streams) {
            int argminLine = mapBrentIndexToLineNo(ma.brentArgmin(), ma.key(), results);
            int argmaxLine = mapBrentIndexToLineNo(ma.brentArgmax(), ma.key(), results);
            champs.add(new MetricChampion(ma.key(), ma.n(),
                    ma.brentMin(), ma.brentArgmin(), argminLine,
                    ma.brentMax(), ma.brentArgmax(), argmaxLine));
        }

        // 5. Robustness ranking.
        Map<Integer, Set<String>> hitsByLine = new HashMap<>();
        Map<Integer, LineResult> byLine = new HashMap<>();
        for (LineResult r : results) byLine.put(r.lineNo, r);
        registerHit(hitsByLine, topScore.isEmpty() ? List.of() : List.of(topScore.get(0).lineNo), "top1");
        for (LineMention m : declared) registerHit(hitsByLine, List.of(m.lineNo), "decl");
        for (LineMention m : auto)     registerHit(hitsByLine, List.of(m.lineNo), "auto");
        for (MetricChampion c : champs) {
            if (c.argminLine > 0) registerHit(hitsByLine, List.of(c.argminLine), "min[" + c.key + "]");
            if (c.argmaxLine > 0) registerHit(hitsByLine, List.of(c.argmaxLine), "max[" + c.key + "]");
        }
        int maxFronts = 4;   // top1 + decl + auto + per-metric
        List<RobustnessRank> robust = new ArrayList<>();
        for (Map.Entry<Integer, Set<String>> e : hitsByLine.entrySet()) {
            LineResult r = byLine.get(e.getKey());
            if (r == null) continue;
            // Bucket the per-metric tags into a single "champ" front so the
            // robustness count caps at 4 even when many metrics co-elect a line.
            int hits = bucket(e.getValue());
            List<String> tags = new ArrayList<>(e.getValue());
            tags.sort(Comparator.naturalOrder());
            robust.add(new RobustnessRank(r.lineNo, hits, maxFronts, tags,
                    r.score, r.features.lineType, snippet(r)));
        }
        robust.sort(Comparator
                .comparingInt(RobustnessRank::frontHits).reversed()
                .thenComparingDouble((RobustnessRank x) -> -x.score));

        return new Report(topScore, declared, auto, champs, robust,
                total, goals.size(), streams.size());
    }

    /** Bucket sub-tags into the four canonical fronts so the count is in [0,4]. */
    private static int bucket(Set<String> tags) {
        boolean top = false, decl = false, auto = false, champ = false;
        for (String t : tags) {
            if (t.equals("top1")) top = true;
            else if (t.equals("decl")) decl = true;
            else if (t.equals("auto")) auto = true;
            else if (t.startsWith("min[") || t.startsWith("max[")) champ = true;
        }
        return (top ? 1 : 0) + (decl ? 1 : 0) + (auto ? 1 : 0) + (champ ? 1 : 0);
    }

    private static void registerHit(Map<Integer, Set<String>> map, List<Integer> lines, String tag) {
        for (int n : lines) map.computeIfAbsent(n, k -> new HashSet<>()).add(tag);
    }

    private static LineMention mention(LineResult r) {
        return new LineMention(r.lineNo, r.score, r.decision, r.features.lineType, snippet(r));
    }

    private static LineMention mention(LineResult r, double crowdingDistance) {
        return new LineMention(r.lineNo, r.score, r.decision, r.features.lineType, snippet(r), crowdingDistance);
    }

    private static String snippet(LineResult r) {
        String s = r.originalLine == null ? "" : r.originalLine;
        if (s.length() > 80) s = s.substring(0, 77) + "...";
        return s;
    }

    /**
     * MetricStreamAnalyzer's Brent argmin/argmax is expressed as a continuous
     * x in [0, n-1] over the metric's per-line series.  Map that back to the
     * actual {@code lineNo} of the closest sample by re-collecting the series
     * exactly the way MetricStreamAnalyzer did.
     */
    private static int mapBrentIndexToLineNo(double brentX, String key, List<LineResult> results) {
        // Re-collect the (lineNo, value) sequence in lineNo order — same order
        // MetricStreamAnalyzer uses internally, so the returned brentArgmin /
        // brentArgmax indices correspond 1:1 with this sequence.  Uses the
        // same {@link AnalyzerCore#tryParseNumeric} helper as MetricStreamAnalyzer
        // so unit-suffixed values like "0.5s" or "(3,0,0)" are kept.
        List<int[]> seq = new ArrayList<>();
        for (LineResult r : results) {
            String v = r.features.kvPairs.get(key);
            if (v == null) continue;
            if (AnalyzerCore.tryParseNumeric(v).isEmpty()) continue;
            seq.add(new int[]{r.lineNo});
        }
        if (seq.isEmpty()) return -1;
        int idx = (int) Math.round(brentX);
        if (idx < 0) idx = 0;
        if (idx >= seq.size()) idx = seq.size() - 1;
        return seq.get(idx)[0];
    }
}
