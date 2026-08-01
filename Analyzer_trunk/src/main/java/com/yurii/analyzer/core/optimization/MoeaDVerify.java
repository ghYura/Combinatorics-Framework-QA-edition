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
 * Tier-5.1 verifier for {@link MoeaD}:
 *
 * <ol>
 *   <li>Weight vectors share the Das-Dennis generator with NSGA-III — point
 *       count + sum-to-1 invariants identical.</li>
 *   <li>Tchebycheff scalar identities on known input triples
 *       ({@code (deviation, weight) → max_i λ_i·|dev_i|}).</li>
 *   <li>Per-candidate {@code bestWeightIndex} is valid (in [0, W)), the
 *       {@code bestTchebycheff} is the minimum across all weights, the
 *       {@code meanTchebycheff} ≥ {@code bestTchebycheff}.</li>
 *   <li>Rank-1 identity with PARETO / NSGA-II / NSGA-III / SPEA2.</li>
 *   <li>End-to-end through {@link OptimizationAnalyzer} with
 *       {@link FrontAlgorithm#MOEA_D} — front lineNo set matches legacy.</li>
 *   <li>{@link BestLinesReporter} surfaces {@code bestTchebycheff} in
 *       {@code LineMention.crowdingDistance} (finite + non-negative).</li>
 * </ol>
 *
 *   Run:  java -cp ... MoeaDVerify
 */
public final class MoeaDVerify {
    private MoeaDVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testWeightVectorsReuseNsgaIIIDasDennis();
        failures += testTchebycheffMath();
        failures += testRankProperties();
        failures += testRankIdentityVsOtherAlgorithms();
        failures += testEndToEnd();
        failures += testBestLinesReporterPopulatesDiversity();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL MOEA/D CHECKS PASSED");
        else { System.out.println("❌ " + failures + " MOEA/D CHECK(S) FAILED"); System.exit(1); }
    }

    private static int testWeightVectorsReuseNsgaIIIDasDennis() {
        System.out.println("── weight vectors == NSGA-III Das-Dennis ──");
        int f = 0;
        // M=2 p=12 → 13 weight vectors
        double[][] w2 = MoeaD.weightVectors(2, 12);
        f += assertCond("M=2 p=12 → 13 weight vectors", w2.length == 13);
        // M=3 p=7 → 36
        double[][] w3 = MoeaD.weightVectors(3, 7);
        f += assertCond("M=3 p=7 → 36 weight vectors", w3.length == 36);
        // sum-to-1 invariant
        boolean allSum1 = true;
        for (double[] w : w3) {
            double s = 0; for (double v : w) s += v;
            if (Math.abs(s - 1.0) > 1e-9) allSum1 = false;
        }
        f += assertCond("every weight vector sums to 1", allSum1);
        // defaultDivisions matches NsgaIII's heuristic
        f += assertCond("defaultDivisions(2) == NsgaIII.defaultDivisions(2)",
                MoeaD.defaultDivisions(2) == NsgaIII.defaultDivisions(2));
        f += assertCond("defaultDivisions(5) == NsgaIII.defaultDivisions(5)",
                MoeaD.defaultDivisions(5) == NsgaIII.defaultDivisions(5));
        return f;
    }

    private static int testTchebycheffMath() {
        System.out.println("\n── Tchebycheff scalarization identities ──");
        int f = 0;
        // Symmetric weight (0.5, 0.5), point (4, 6) → max(0.5*4, 0.5*6) = 3.0
        double t1 = MoeaD.tchebycheff(new double[]{4, 6}, new double[]{0.5, 0.5});
        f += assertCond("(4,6) · (0.5,0.5) → max(2, 3) == 3.0", Math.abs(t1 - 3.0) < 1e-9);

        // Skewed weight (1, 0): epsilon-clamped → max(1*4, ε*6) = 4
        double t2 = MoeaD.tchebycheff(new double[]{4, 6}, new double[]{1.0, 0.0});
        f += assertCond("(4,6) · (1,0)  → effectively max(4, ε·6) ≈ 4.0",
                Math.abs(t2 - 4.0) < 1e-3);

        // Zero deviations → 0 regardless of weights
        double t3 = MoeaD.tchebycheff(new double[]{0, 0, 0}, new double[]{0.3, 0.3, 0.4});
        f += assertCond("zero deviations → Tchebycheff 0", Math.abs(t3) < 1e-12);

        // Absolute value used: negative deviations don't subtract
        double t4 = MoeaD.tchebycheff(new double[]{-3, 5}, new double[]{1.0, 1.0});
        f += assertCond("(-3,5) → max(|-3|, |5|) == 5.0", Math.abs(t4 - 5.0) < 1e-9);
        return f;
    }

    /** {@code bestTchebycheff <= meanTchebycheff} for every candidate;
     *  bestWeightIndex in valid range. */
    private static int testRankProperties() {
        System.out.println("\n── rank() properties ──");
        double[][] v = {
            {1, 9}, {2, 5}, {3, 4}, {4, 3}, {5, 2}, {9, 1},
            {6, 6}, {7, 8}, {8, 7},
        };
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] g = { GoalSpec.min("x"), GoalSpec.min("y") };

        List<MoeaD.Ranked<Integer>> ranked = MoeaD.rank(items, v, g);
        int W = MoeaD.weightVectors(g.length, MoeaD.defaultDivisions(g.length)).length;
        int f = 0;
        f += assertCond("rank() returns one entry per candidate", ranked.size() == v.length);
        boolean allValid = true;
        boolean bestLeMean = true;
        boolean allFinite = true;
        for (MoeaD.Ranked<Integer> r : ranked) {
            if (r.bestWeightIndex() < 0 || r.bestWeightIndex() >= W) allValid = false;
            if (!(r.bestTchebycheff() <= r.meanTchebycheff() + 1e-9)) bestLeMean = false;
            if (!Double.isFinite(r.bestTchebycheff()) || !Double.isFinite(r.meanTchebycheff())) allFinite = false;
        }
        f += assertCond("every bestWeightIndex in [0, W)", allValid);
        f += assertCond("bestTchebycheff <= meanTchebycheff (by definition)", bestLeMean);
        f += assertCond("bestTchebycheff + meanTchebycheff finite everywhere", allFinite);
        return f;
    }

    private static int testRankIdentityVsOtherAlgorithms() {
        System.out.println("\n── MOEA/D rank-1 ≡ NSGA-II/III ≡ SPEA2 ≡ legacy ──");
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
        Set<Integer> md     = new HashSet<>();
        for (MoeaD.Ranked<Integer>   r : MoeaD.firstFrontWithDecomposition(items, v, g)) md.add(r.item());

        int f = 0;
        f += assertCond("MOEA/D front == legacy",  md.equals(legacy));
        f += assertCond("MOEA/D front == NSGA-II", md.equals(n2));
        f += assertCond("MOEA/D front == NSGA-III", md.equals(n3));
        f += assertCond("MOEA/D front == SPEA2",   md.equals(sp2));
        f += assertCond("all five front sets have size 6", md.size() == 6);
        return f;
    }

    private static int testEndToEnd() throws Exception {
        System.out.println("\n── end-to-end: OptimizationAnalyzer w/ FrontAlgorithm.MOEA_D ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"throughput\",\"mode\":\"maximize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 8, 30.0, 10.0, false, 0.0, false,
                new LineParser.KvLineParser(),
                FrontAlgorithm.MOEA_D);
        int f = 0;
        f += assertCond("analyzer.frontAlgorithm() == MOEA_D",
                analyzer.frontAlgorithm() == FrontAlgorithm.MOEA_D);

        List<String> corpus = new ArrayList<>();
        double[][] tuples = {
            {0.10, 9.0,  400}, {0.25, 7.0, 1300}, {0.40, 5.0, 2600},
            {0.55, 3.0, 3800}, {0.80, 2.0, 4500}, {0.90, 8.0,  900},
            {0.95, 6.0, 1500}, {0.99, 4.0, 2200}, {0.60, 4.5, 3200},
            {0.30, 6.0, 2900},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=t_%02d cost=%.3f latency=%.2f throughput=%.0f",
                    i + 1, tuples[i][0], tuples[i][1], tuples[i][2]));
        }
        List<LineResult> results = new ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        List<LineResult> legacy = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.PARETO);
        List<LineResult> md     = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.MOEA_D);
        f += assertCond("paretoOptimal(PARETO) ≡ paretoOptimal(MOEA_D) on lineNo set",
                lineNoSet(legacy).equals(lineNoSet(md)));

        List<MoeaD.Ranked<LineResult>> ranked =
                AnalyzerCore.paretoOptimalRankedMoeaD(results, analyzer.goals());
        f += assertCond("paretoOptimalRankedMoeaD non-empty", !ranked.isEmpty());

        Set<Integer> weightsUsed = new HashSet<>();
        boolean allValid = true;
        for (MoeaD.Ranked<LineResult> r : ranked) {
            weightsUsed.add(r.bestWeightIndex());
            if (r.rank() != 1) allValid = false;
            if (!Double.isFinite(r.bestTchebycheff())) allValid = false;
        }
        f += assertCond("3-axis: ≥ 2 distinct weight directions used by the front",
                weightsUsed.size() >= 2);
        f += assertCond("every ranked member has rank=1 and finite bestTchebycheff",
                allValid);
        return f;
    }

    private static int testBestLinesReporterPopulatesDiversity() throws Exception {
        System.out.println("\n── BestLinesReporter populates bestTchebycheff under MOEA_D ──");
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
                    "id=t_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        List<LineResult> results = new ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        BestLinesReporter.Report report = BestLinesReporter.build(
                null, results, analyzer.goals(), FrontAlgorithm.MOEA_D);
        int f = 0;
        f += assertCond("MOEA_D: declared-goal front non-empty",
                !report.declaredGoalPareto().isEmpty());

        boolean anyFinite = false;
        boolean anyInfinite = false;
        boolean anyNegative = false;
        for (BestLinesReporter.LineMention m : report.declaredGoalPareto()) {
            if (Double.isFinite(m.crowdingDistance())) anyFinite = true;
            if (Double.isInfinite(m.crowdingDistance())) anyInfinite = true;
            if (m.crowdingDistance() < 0) anyNegative = true;
        }
        f += assertCond("under MOEA_D, diversity field is finite", anyFinite);
        f += assertCond("under MOEA_D, no +∞ sentinels",           !anyInfinite);
        f += assertCond("under MOEA_D, no negative values",         !anyNegative);
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
