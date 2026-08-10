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

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Tier-5.1 verifier for {@link Spea2}:
 *
 * <ol>
 *   <li>Strength counts on a known 9-candidate corpus — strength[i] equals
 *       the count of candidates {@code i} dominates.</li>
 *   <li>Raw fitness — non-dominated members have {@code rawFitness == 0},
 *       which is exactly the rank-1 set.</li>
 *   <li>k-NN distance — finite + non-negative for every candidate.</li>
 *   <li>Final fitness {@code F = R + D} arithmetic identity.</li>
 *   <li>Rank-1 identity with PARETO / NSGA-II / NSGA-III on shared corpus.</li>
 *   <li>End-to-end through {@link OptimizationAnalyzer} with
 *       {@link FrontAlgorithm#SPEA2}: same lineNo set as PARETO; ranked
 *       path exposes all SPEA2 components.</li>
 *   <li>{@link BestLinesReporter} surfaces {@code kNearestDistance} in
 *       {@code LineMention.crowdingDistance} (finite + non-negative).</li>
 * </ol>
 *
 *   Run:  java -cp ... Spea2Verify
 */
public final class Spea2Verify {
    private Spea2Verify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testStrengthCountsAndRaw();
        failures += testKnnAndFinalFitness();
        failures += testRankIdentityVsOtherAlgorithms();
        failures += testEndToEnd();
        failures += testBestLinesReporterPopulatesDiversity();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL SPEA2 CHECKS PASSED");
        else { System.out.println("❌ " + failures + " SPEA2 CHECK(S) FAILED"); System.exit(1); }
    }

    /** 9 candidates, MIN/MIN — 6 on front, 3 dominated.  Strength counts
     *  must equal the number of strictly-dominated candidates. */
    private static int testStrengthCountsAndRaw() {
        System.out.println("── strength + raw fitness ──");
        double[][] v = {
            {1.0, 9.0}, {2.0, 5.0}, {3.0, 4.0},   // front (0,1,2)
            {4.0, 3.0}, {5.0, 2.0}, {9.0, 1.0},   // front (3,4,5)
            {6.0, 6.0}, {7.0, 8.0}, {8.0, 7.0},   // dominated
        };
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] g = { GoalSpec.min("x"), GoalSpec.min("y") };

        List<Spea2.Ranked<Integer>> ranked = Spea2.rank(items, v, g);
        int f = 0;
        f += assertCond("rank() returns one entry per candidate", ranked.size() == v.length);

        // Non-dominated set: raw == 0 ⇔ rank == 1
        Set<Integer> rawZero = new HashSet<>();
        Set<Integer> rank1   = new HashSet<>();
        for (Spea2.Ranked<Integer> r : ranked) {
            if (Math.abs(r.rawFitness()) < 1e-9) rawZero.add(r.item());
            if (r.rank() == 1) rank1.add(r.item());
        }
        f += assertCond("rawFitness == 0 set equals rank-1 set",
                rawZero.equals(rank1));
        f += assertCond("front size == 6 (known answer)", rawZero.size() == 6);

        // Strength of (1, 9) — the y-axis boundary winner.  It dominates only
        // the 3 strictly-dominated candidates that have y >= 9: (7, 8), (8, 7)
        // → no, they have y < 9.  Actually (1, 9) dominates someone iff that
        // someone has BOTH x >= 1 AND y >= 9 with at least one strict.
        // Looking at corpus: (7,8), (8,7), (6,6), (9,1), (5,2) etc — none have
        // y >= 9 strictly worse.  So strength[0] should be 0.
        Spea2.Ranked<Integer> r0 = ranked.get(0);   // (1,9)
        f += assertCond("strength of (1,9) on min/min == 0 (no one is uniformly worse)",
                r0.strength() == 0);

        // (3, 4) dominates: (6,6) yes, (7,8) yes, (8,7) yes  → strength = 3
        Spea2.Ranked<Integer> r2 = ranked.get(2);   // (3,4)
        f += assertCond("strength of (3,4) == 3 (dominates the three off-front candidates)",
                r2.strength() == 3);

        // Strictly dominated candidates have raw > 0
        Spea2.Ranked<Integer> r6 = ranked.get(6);   // (6,6) — dominated
        f += assertCond("(6,6) has rawFitness > 0 (it's dominated)",
                r6.rawFitness() > 0);
        f += assertCond("(6,6) is rank > 1",
                r6.rank() > 1);
        return f;
    }

    private static int testKnnAndFinalFitness() {
        System.out.println("\n── k-NN distance + final fitness identity ──");
        double[][] v = {
            {1, 9}, {2, 5}, {3, 4}, {4, 3}, {5, 2}, {9, 1},
            {6, 6}, {7, 8}, {8, 7},
        };
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] g = { GoalSpec.min("x"), GoalSpec.min("y") };

        List<Spea2.Ranked<Integer>> ranked = Spea2.rank(items, v, g);

        int f = 0;
        boolean allFinite = true;
        boolean allNonNeg = true;
        boolean fIsRplusD  = true;
        boolean densityFormula = true;
        for (Spea2.Ranked<Integer> r : ranked) {
            if (!Double.isFinite(r.kNearestDistance())) allFinite = false;
            if (r.kNearestDistance() < 0) allNonNeg = false;
            double expectedD = 1.0 / (r.kNearestDistance() + 2.0);
            if (Math.abs(r.density() - expectedD) > 1e-9) densityFormula = false;
            double expectedF = r.rawFitness() + r.density();
            if (Math.abs(r.finalFitness() - expectedF) > 1e-9) fIsRplusD = false;
        }
        f += assertCond("every k-NN distance is finite", allFinite);
        f += assertCond("every k-NN distance is non-negative", allNonNeg);
        f += assertCond("density(i) == 1 / (kNN(i) + 2) for every i", densityFormula);
        f += assertCond("finalFitness(i) == rawFitness(i) + density(i) for every i", fIsRplusD);
        return f;
    }

    private static int testRankIdentityVsOtherAlgorithms() {
        System.out.println("\n── SPEA2 rank-1 ≡ NSGA-II ≡ NSGA-III ≡ legacy ──");
        double[][] v = {
            {1, 9}, {2, 5}, {3, 4}, {4, 3}, {5, 2}, {9, 1},
            {6, 6}, {7, 8}, {8, 7},
        };
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] g = { GoalSpec.min("x"), GoalSpec.min("y") };

        Set<Integer> legacy = new HashSet<>(Dominance.paretoFront(items, v, g));
        Set<Integer> n2     = new HashSet<>();
        for (NsgaII.Ranked<Integer>  r : NsgaII.firstFrontWithCrowding(items, v, g))  n2.add(r.item());
        Set<Integer> n3     = new HashSet<>();
        for (NsgaIII.Ranked<Integer> r : NsgaIII.firstFrontWithReference(items, v, g)) n3.add(r.item());
        Set<Integer> sp2    = new HashSet<>();
        for (Spea2.Ranked<Integer>   r : Spea2.firstFrontWithFitness(items, v, g))   sp2.add(r.item());

        int f = 0;
        f += assertCond("SPEA2 front == legacy", sp2.equals(legacy));
        f += assertCond("SPEA2 front == NSGA-II", sp2.equals(n2));
        f += assertCond("SPEA2 front == NSGA-III", sp2.equals(n3));
        f += assertCond("all four front sets have size 6", sp2.size() == 6);
        return f;
    }

    private static int testEndToEnd() throws Exception {
        System.out.println("\n── end-to-end: OptimizationAnalyzer w/ FrontAlgorithm.SPEA2 ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false,
                new LineParser.KvLineParser(),
                FrontAlgorithm.SPEA2);
        int f = 0;
        f += assertCond("analyzer.frontAlgorithm() == SPEA2",
                analyzer.frontAlgorithm() == FrontAlgorithm.SPEA2);

        List<String> corpus = new ArrayList<>();
        double[][] tuples = {
            {0.10, 9.0}, {0.25, 7.0}, {0.40, 5.0}, {0.55, 3.0}, {0.80, 2.0},
            {0.90, 8.0}, {0.95, 6.0}, {0.99, 4.0},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=s_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        List<LineResult> results = new ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        List<LineResult> legacy = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.PARETO);
        List<LineResult> sp2    = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.SPEA2);
        f += assertCond("paretoOptimal(PARETO) ≡ paretoOptimal(SPEA2) on lineNo set",
                lineNoSet(legacy).equals(lineNoSet(sp2)));

        List<Spea2.Ranked<LineResult>> ranked =
                AnalyzerCore.paretoOptimalRankedSpea2(results, analyzer.goals());
        f += assertCond("paretoOptimalRankedSpea2 non-empty", !ranked.isEmpty());
        boolean allRankOneZeroRaw = true;
        boolean allKnnFiniteNonNeg = true;
        for (Spea2.Ranked<LineResult> r : ranked) {
            if (r.rank() != 1 || r.rawFitness() != 0) allRankOneZeroRaw = false;
            if (!Double.isFinite(r.kNearestDistance()) || r.kNearestDistance() < 0) allKnnFiniteNonNeg = false;
        }
        f += assertCond("every ranked member has rank=1 and rawFitness=0",
                allRankOneZeroRaw);
        f += assertCond("every ranked member has finite, ≥0 k-NN distance",
                allKnnFiniteNonNeg);
        return f;
    }

    private static int testBestLinesReporterPopulatesDiversity() throws Exception {
        System.out.println("\n── BestLinesReporter populates k-NN distance under SPEA2 ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false);
        List<String> corpus = new ArrayList<>();
        double[][] tuples = {
            {0.10, 9.0}, {0.25, 7.0}, {0.40, 5.0}, {0.55, 3.0}, {0.80, 2.0},
            {0.90, 8.0}, {0.95, 6.0}, {0.99, 4.0},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=s_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        List<LineResult> results = new ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        BestLinesReporter.Report report = BestLinesReporter.build(
                null, results, analyzer.goals(), FrontAlgorithm.SPEA2);
        int f = 0;
        f += assertCond("SPEA2: declared-goal front non-empty",
                !report.declaredGoalPareto().isEmpty());

        boolean anyFinite = false;
        boolean anyInfinite = false;
        boolean anyNegative = false;
        for (BestLinesReporter.LineMention m : report.declaredGoalPareto()) {
            if (Double.isFinite(m.crowdingDistance())) anyFinite = true;
            if (Double.isInfinite(m.crowdingDistance())) anyInfinite = true;
            if (m.crowdingDistance() < 0) anyNegative = true;
        }
        f += assertCond("under SPEA2, diversity field is finite",  anyFinite);
        f += assertCond("under SPEA2, no +∞ sentinels",            !anyInfinite);
        f += assertCond("under SPEA2, no negative values",          !anyNegative);
        return f;
    }

    private static Set<Integer> lineNoSet(List<LineResult> results) {
        Set<Integer> s = new HashSet<>();
        for (LineResult r : results) s.add(r.lineNo);
        return s;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
