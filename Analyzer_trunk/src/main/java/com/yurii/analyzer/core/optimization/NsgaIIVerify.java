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

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationGoal;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Verifies the Tier-2 win 2.3 — NSGA-II non-dominated sort + crowding distance:
 *
 *   • Rank-1 membership of NSGA-II matches the legacy Pareto front
 *     ({@code Dominance.paretoFront}) bit-for-bit on a synthetic 2-axis corpus
 *     (the diversification adds info, never changes membership).
 *   • Boundary front members get +∞ crowding distance (the NSGA-II invariant).
 *   • Interior members get finite, non-negative crowding distance.
 *   • The fast non-dominated sort assigns every candidate to some front
 *     (no candidate left unranked).
 *   • Default {@link FrontAlgorithm#DEFAULT} is NSGA-II — flipping the
 *     analyzer between PARETO and NSGA-II yields identical declared-goal
 *     Pareto front membership through {@code AnalyzerCore.paretoOptimal}.
 *   • The downstream {@code BestLinesReporter.LineMention.crowdingDistance}
 *     is populated for front members under the NSGA-II default.
 *
 *   Run:  java -cp ... NsgaIIVerify
 */
public final class NsgaIIVerify {
    private NsgaIIVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testRankOneMembershipMatchesLegacy();
        failures += testBoundaryHasInfinityCrowding();
        failures += testFastSortRanksEveryItem();
        failures += testDefaultIsNsgaII();
        failures += testReporterPopulatesCrowding();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL NSGA-II CHECKS PASSED");
        else { System.out.println("❌ " + failures + " NSGA-II CHECK(S) FAILED"); System.exit(1); }
    }

    /** A small synthetic 2-axis MIN/MIN corpus — front is well-known. */
    private static double[][] corpusVectors() {
        return new double[][]{
            {1.0, 9.0},   // on front
            {2.0, 5.0},   // on front
            {3.0, 4.0},   // on front
            {4.0, 3.0},   // on front
            {5.0, 2.0},   // on front
            {9.0, 1.0},   // on front
            {6.0, 6.0},   // dominated by (3,4) and (4,3) and (5,2)
            {7.0, 8.0},   // dominated
            {8.0, 7.0},   // dominated
        };
    }

    private static GoalSpec[] minMinGoals() {
        return new GoalSpec[]{GoalSpec.min("x"), GoalSpec.min("y")};
    }

    private static int testRankOneMembershipMatchesLegacy() {
        System.out.println("── Rank-1 ⊆ legacy Pareto front ──");
        double[][] v = corpusVectors();
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] goals = minMinGoals();

        List<Integer> legacy   = Dominance.paretoFront(items, v, goals);
        List<NsgaII.Ranked<Integer>> ranked = NsgaII.firstFrontWithCrowding(items, v, goals);
        Set<Integer> legacySet = new HashSet<>(legacy);
        Set<Integer> nsgaSet   = new HashSet<>();
        for (NsgaII.Ranked<Integer> r : ranked) nsgaSet.add(r.item());

        int f = 0;
        f += assertCond("NSGA-II rank-1 size == legacy front size", legacySet.size() == nsgaSet.size());
        f += assertCond("NSGA-II rank-1 == legacy front (same indices)", legacySet.equals(nsgaSet));
        return f;
    }

    private static int testBoundaryHasInfinityCrowding() {
        System.out.println("\n── Boundary front members → +∞ crowding ──");
        double[][] v = corpusVectors();
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] goals = minMinGoals();
        List<NsgaII.Ranked<Integer>> ranked = NsgaII.firstFrontWithCrowding(items, v, goals);

        int infCount = 0, finiteNonNegCount = 0;
        for (NsgaII.Ranked<Integer> r : ranked) {
            if (Double.isInfinite(r.crowdingDistance())) infCount++;
            else if (Double.isFinite(r.crowdingDistance()) && r.crowdingDistance() >= 0) finiteNonNegCount++;
        }
        int f = 0;
        f += assertCond("at least 2 boundary members got +∞ crowding", infCount >= 2);
        f += assertCond("all interior crowding values finite + non-negative",
                infCount + finiteNonNegCount == ranked.size());
        return f;
    }

    private static int testFastSortRanksEveryItem() {
        System.out.println("\n── fastNonDominatedSort ranks every item ──");
        double[][] v = corpusVectors();
        GoalSpec[] goals = minMinGoals();
        List<List<Integer>> fronts = NsgaII.fastNonDominatedSort(v, goals);
        int total = 0;
        for (List<Integer> f : fronts) total += f.size();
        int rc = 0;
        rc += assertCond("union of all fronts covers the input set",
                total == v.length);
        rc += assertCond("at least one front exists", !fronts.isEmpty());
        return rc;
    }

    /** Run the full OptimizationAnalyzer pipeline with NSGA-II vs PARETO
     *  and confirm the declared-goal front membership is identical. */
    private static int testDefaultIsNsgaII() throws Exception {
        System.out.println("\n── Analyzer default = NSGA-II; membership matches PARETO ──");
        int f = 0;
        f += assertCond("FrontAlgorithm.DEFAULT == NSGA_II",
                FrontAlgorithm.DEFAULT == FrontAlgorithm.NSGA_II);

        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false);
        f += assertCond("analyzer.frontAlgorithm() defaults to NSGA-II",
                analyzer.frontAlgorithm() == FrontAlgorithm.NSGA_II);

        java.util.List<String> corpus = new java.util.ArrayList<>();
        // 5 mostly-Pareto + 3 dominated samples; enough to exercise the
        // PARETO_MIN_COVERAGE=5 gate inside AnalyzerCore.paretoOptimal.
        double[][] tuples = {
            {0.10, 9.0}, {0.25, 7.0}, {0.40, 5.0}, {0.55, 3.0}, {0.80, 2.0},
            {0.90, 8.0}, {0.95, 6.0}, {0.99, 4.0},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=n_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        java.util.List<LineResult> results = new java.util.ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        List<OptimizationGoal> goals = analyzer.goals();
        List<LineResult> legacyFront = AnalyzerCore.paretoOptimal(results, goals, FrontAlgorithm.PARETO);
        List<LineResult> nsgaFront   = AnalyzerCore.paretoOptimal(results, goals, FrontAlgorithm.NSGA_II);
        Set<Integer> legacySet = new HashSet<>();
        Set<Integer> nsgaSet   = new HashSet<>();
        for (LineResult r : legacyFront) legacySet.add(r.lineNo);
        for (LineResult r : nsgaFront)   nsgaSet.add(r.lineNo);
        f += assertCond("paretoOptimal(PARETO) ≡ paretoOptimal(NSGA_II) on lineNo set",
                legacySet.equals(nsgaSet));

        // Ranked variant should expose crowding distance, with at least 2 +∞.
        List<NsgaII.Ranked<LineResult>> ranked = AnalyzerCore.paretoOptimalRanked(results, goals);
        int infCount = 0;
        for (NsgaII.Ranked<LineResult> r : ranked) if (Double.isInfinite(r.crowdingDistance())) infCount++;
        f += assertCond("paretoOptimalRanked exposes ≥ 2 +∞ boundary members",
                ranked.size() >= 2 && infCount >= 2);
        return f;
    }

    /** Round-trip: NSGA-II analyzer → BestLinesReporter → LineMention.crowdingDistance. */
    private static int testReporterPopulatesCrowding() throws Exception {
        System.out.println("\n── BestLinesReporter populates crowdingDistance ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false);
        java.util.List<String> corpus = new java.util.ArrayList<>();
        double[][] tuples = {
            {0.10, 9.0}, {0.25, 7.0}, {0.40, 5.0}, {0.55, 3.0}, {0.80, 2.0},
            {0.90, 8.0}, {0.95, 6.0}, {0.99, 4.0},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=n_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        java.util.List<LineResult> results = new java.util.ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        BestLinesReporter.Report nsga = BestLinesReporter.build(
                null, results, analyzer.goals(), FrontAlgorithm.NSGA_II);
        BestLinesReporter.Report pareto = BestLinesReporter.build(
                null, results, analyzer.goals(), FrontAlgorithm.PARETO);

        int f = 0;
        f += assertCond("declared-goal Pareto section non-empty under NSGA-II",
                !nsga.declaredGoalPareto().isEmpty());

        boolean anyFinite = false, anyInfinite = false;
        for (BestLinesReporter.LineMention m : nsga.declaredGoalPareto()) {
            if (Double.isFinite(m.crowdingDistance())) anyFinite = true;
            if (Double.isInfinite(m.crowdingDistance())) anyInfinite = true;
        }
        f += assertCond("at least one NSGA-II declared-front member has finite crowding",
                anyFinite || nsga.declaredGoalPareto().size() <= 2);
        f += assertCond("at least one NSGA-II declared-front member has +∞ crowding",
                anyInfinite);
        boolean allNan = true;
        for (BestLinesReporter.LineMention m : pareto.declaredGoalPareto()) {
            if (!Double.isNaN(m.crowdingDistance())) { allNan = false; break; }
        }
        f += assertCond("PARETO mode leaves crowding = NaN on every mention", allNan);
        return f;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
