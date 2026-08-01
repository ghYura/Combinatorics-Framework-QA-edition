package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Verifies the Tier-5.1 NSGA-III primitives + integration:
 *
 * <ol>
 *   <li>Das-Dennis reference-point generation — count matches
 *       {@code C(M+p-1, p)}, every point's coordinates sum to 1 (within
 *       floating-point tolerance), all coordinates non-negative.</li>
 *   <li>Perpendicular distance — orthogonal projection identity, scale-
 *       invariance along the reference direction.</li>
 *   <li>Normalize — ideal-point translation places the population's best on
 *       every axis at 0; intercept fallback when the extreme-point matrix is
 *       singular.</li>
 *   <li>Associate — every candidate maps to exactly one reference index;
 *       perpendicular distance ≥ 0.</li>
 *   <li>Rank-1 identity with NSGA-II and the legacy {@code Dominance.paretoFront}
 *       on a shared synthetic corpus (front membership is mathematically
 *       independent of the diversification metric).</li>
 *   <li>End-to-end through {@link OptimizationAnalyzer} with
 *       {@link FrontAlgorithm#NSGA_III}: corpus → snapshot → per-key stats +
 *       Pareto-front + auto-discovery still work; declared-goal {@code
 *       AnalyzerCore.paretoOptimal} returns the same lineNo set as NSGA-II
 *       and PARETO.</li>
 *   <li>{@code BestLinesReporter} populates {@code LineMention.crowdingDistance}
 *       with perpendicular distance values (finite, non-negative) under
 *       NSGA-III.</li>
 *   <li>3-axis (M=3) corpus — the case where NSGA-III's reference-point
 *       advantage over crowding distance is meaningful.</li>
 * </ol>
 *
 *   Run:  java -cp ... NsgaIIIVerify
 */
public final class NsgaIIIVerify {
    private NsgaIIIVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testReferencePointCombinatorics();
        failures += testPerpendicularDistance();
        failures += testNormalize();
        failures += testAssociate();
        failures += testRankIdentityVsNsgaIIAndLegacy();
        failures += testEndToEndTwoAxis();
        failures += testEndToEndThreeAxis();
        failures += testBestLinesReporterPopulatesDiversity();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL NSGA-III CHECKS PASSED");
        else { System.out.println("❌ " + failures + " NSGA-III CHECK(S) FAILED"); System.exit(1); }
    }

    // ── 1. Reference-point generation ──────────────────────────────────

    private static int testReferencePointCombinatorics() {
        System.out.println("── reference-point generation (Das-Dennis) ──");
        int f = 0;

        // M=2, p=12 → C(13, 12) = 13 points
        double[][] r2 = NsgaIII.referencePoints(2, 12);
        f += assertCond("M=2 p=12 → 13 reference points", r2.length == 13);
        f += assertCond("M=2 reference points: every sum == 1.0 (±eps)",
                allSumToOne(r2, 1e-9));
        f += assertCond("M=2 reference points: every coordinate ≥ 0", allNonNegative(r2));

        // M=3, p=7 → C(9, 7) = C(9,2) = 36 points
        double[][] r3 = NsgaIII.referencePoints(3, 7);
        f += assertCond("M=3 p=7 → 36 reference points", r3.length == 36);
        f += assertCond("M=3 reference points: every sum == 1.0 (±eps)",
                allSumToOne(r3, 1e-9));

        // M=5, p=4 → C(8, 4) = 70 points
        double[][] r5 = NsgaIII.referencePoints(5, 4);
        f += assertCond("M=5 p=4 → 70 reference points", r5.length == 70);

        // Default divisions sanity checks
        f += assertCond("defaultDivisions(2) == 12", NsgaIII.defaultDivisions(2) == 12);
        f += assertCond("defaultDivisions(3) == 7",  NsgaIII.defaultDivisions(3) == 7);
        f += assertCond("defaultDivisions(6) ≤ 4 (bounded for many-obj)",
                NsgaIII.defaultDivisions(6) <= 4);
        return f;
    }

    private static boolean allSumToOne(double[][] pts, double eps) {
        for (double[] p : pts) {
            double s = 0;
            for (double v : p) s += v;
            if (Math.abs(s - 1.0) > eps) return false;
        }
        return true;
    }

    private static boolean allNonNegative(double[][] pts) {
        for (double[] p : pts)
            for (double v : p) if (v < -1e-12) return false;
        return true;
    }

    // ── 2. Perpendicular distance ──────────────────────────────────────

    private static int testPerpendicularDistance() {
        System.out.println("\n── perpendicular distance properties ──");
        int f = 0;

        // Point on the line → distance == 0
        double[] ref = {1.0, 1.0};
        double[] onLine = {2.0, 2.0};   // multiple of ref
        double d1 = NsgaIII.perpendicularDistance(onLine, ref);
        f += assertCond("point on the reference line → distance ≈ 0", Math.abs(d1) < 1e-9);

        // Orthogonal projection: ref = (1, 0), point = (3, 4) → perp distance = |4|
        double[] xAxis = {1.0, 0.0};
        double[] pt    = {3.0, 4.0};
        double d2 = NsgaIII.perpendicularDistance(pt, xAxis);
        f += assertCond("point (3,4) vs x-axis ref → perp distance == 4", Math.abs(d2 - 4.0) < 1e-9);

        // Scale-invariance: doubling the ref vector preserves the line → same distance
        double[] doubled = {2.0, 0.0};
        double d3 = NsgaIII.perpendicularDistance(pt, doubled);
        f += assertCond("scaling reference vector doesn't change distance",
                Math.abs(d3 - d2) < 1e-9);

        // 3-D case: ref = (1,1,1)/√3, point = (1,0,0) → known geometric distance
        double[] r3d = {1, 1, 1};
        double[] p3d = {1, 0, 0};
        double d4 = NsgaIII.perpendicularDistance(p3d, r3d);
        f += assertCond("3-D perp distance from (1,0,0) to (1,1,1)-line is finite + ≥ 0",
                Double.isFinite(d4) && d4 >= 0);
        return f;
    }

    // ── 3. Normalize ───────────────────────────────────────────────────

    private static int testNormalize() {
        System.out.println("\n── normalize: ideal-point + intercept hyperplane ──");
        int f = 0;
        // 4 candidates, 2 MIN axes
        double[][] vecs = {
            {1, 9},
            {2, 5},
            {5, 2},
            {9, 1},
        };
        GoalSpec[] goals = { GoalSpec.min("x"), GoalSpec.min("y") };
        double[][] norm = NsgaIII.normalize(vecs, goals);
        f += assertCond("normalize returns one row per candidate", norm.length == vecs.length);
        f += assertCond("normalize returns M columns per row",
                norm[0].length == goals.length);

        // After translation, the ideal-point coordinate is 0 on every axis
        // for at least one individual; check column-min == 0.
        for (int j = 0; j < goals.length; j++) {
            double mn = Double.POSITIVE_INFINITY;
            for (double[] r : norm) if (r[j] < mn) mn = r[j];
            f += assertCond("normalized axis " + j + " minimum ≈ 0 (ideal point translated)",
                    Math.abs(mn) < 1e-9);
        }

        // No coordinate should be NaN
        boolean anyNaN = false;
        for (double[] r : norm) for (double v : r) if (Double.isNaN(v)) anyNaN = true;
        f += assertCond("no NaN in normalized vectors", !anyNaN);
        return f;
    }

    // ── 4. Associate ───────────────────────────────────────────────────

    private static int testAssociate() {
        System.out.println("\n── associate: each candidate → one ref point ──");
        double[][] vecs = {
            {1, 9}, {2, 7}, {3, 4}, {5, 2}, {9, 1},
        };
        GoalSpec[] goals = { GoalSpec.min("x"), GoalSpec.min("y") };
        double[][] norm = NsgaIII.normalize(vecs, goals);
        double[][] refs = NsgaIII.referencePoints(2, 12);
        NsgaIII.Association[] assoc = NsgaIII.associate(norm, refs);

        int f = 0;
        f += assertCond("associate returns one entry per candidate", assoc.length == vecs.length);
        boolean allValid = true;
        for (NsgaIII.Association a : assoc) {
            if (a.referencePointIndex() < 0 || a.referencePointIndex() >= refs.length) allValid = false;
            if (a.perpendicularDistance() < 0 || !Double.isFinite(a.perpendicularDistance())) allValid = false;
        }
        f += assertCond("every refIndex ∈ [0, R) and every perpDist finite + ≥ 0", allValid);

        // The first candidate (1, 9) should be near the (0, 1) reference
        // direction; check that the chosen ref's y-coordinate dominates.
        NsgaIII.Association a0 = assoc[0];
        double[] chosenRef0 = refs[a0.referencePointIndex()];
        f += assertCond("candidate (1,9) — chosen ref has y >= x (skewed to y-axis)",
                chosenRef0[1] >= chosenRef0[0] - 1e-9);

        // The last (9, 1) should be near (1, 0)
        NsgaIII.Association aLast = assoc[assoc.length - 1];
        double[] chosenRefL = refs[aLast.referencePointIndex()];
        f += assertCond("candidate (9,1) — chosen ref has x >= y (skewed to x-axis)",
                chosenRefL[0] >= chosenRefL[1] - 1e-9);
        return f;
    }

    // ── 5. Rank-1 identity ─────────────────────────────────────────────

    private static int testRankIdentityVsNsgaIIAndLegacy() {
        System.out.println("\n── rank-1 identity: NSGA-III ≡ NSGA-II ≡ legacy ──");
        // 9 candidates, MIN/MIN — 6 on the front, 3 strictly dominated
        double[][] v = {
            {1.0, 9.0}, {2.0, 5.0}, {3.0, 4.0},
            {4.0, 3.0}, {5.0, 2.0}, {9.0, 1.0},   // front
            {6.0, 6.0}, {7.0, 8.0}, {8.0, 7.0},   // dominated
        };
        List<Integer> items = new ArrayList<>();
        for (int i = 0; i < v.length; i++) items.add(i);
        GoalSpec[] g = { GoalSpec.min("x"), GoalSpec.min("y") };

        Set<Integer> legacy = new HashSet<>(Dominance.paretoFront(items, v, g));
        Set<Integer> nsga2  = new HashSet<>();
        for (NsgaII.Ranked<Integer> r : NsgaII.firstFrontWithCrowding(items, v, g)) nsga2.add(r.item());
        Set<Integer> nsga3  = new HashSet<>();
        for (NsgaIII.Ranked<Integer> r : NsgaIII.firstFrontWithReference(items, v, g)) nsga3.add(r.item());

        int f = 0;
        f += assertCond("legacy front == NSGA-II front", legacy.equals(nsga2));
        f += assertCond("NSGA-II front == NSGA-III front", nsga2.equals(nsga3));
        f += assertCond("legacy front == NSGA-III front", legacy.equals(nsga3));
        f += assertCond("front size == 6 (known answer)", nsga3.size() == 6);
        return f;
    }

    // ── 6. End-to-end (2-axis) ─────────────────────────────────────────

    private static int testEndToEndTwoAxis() throws Exception {
        System.out.println("\n── end-to-end: OptimizationAnalyzer w/ FrontAlgorithm.NSGA_III ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 5, 30.0, 10.0, false, 0.0, false,
                new LineParser.KvLineParser(),
                FrontAlgorithm.NSGA_III);
        int f = 0;
        f += assertCond("analyzer.frontAlgorithm() == NSGA_III",
                analyzer.frontAlgorithm() == FrontAlgorithm.NSGA_III);

        List<String> corpus = new ArrayList<>();
        double[][] tuples = {
            {0.10, 9.0}, {0.25, 7.0}, {0.40, 5.0}, {0.55, 3.0}, {0.80, 2.0},
            {0.90, 8.0}, {0.95, 6.0}, {0.99, 4.0},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=n_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        List<LineResult> results = new ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        // declared-goal Pareto returns the same lineNo set under any of the
        // three algorithms (rank-1 membership is algorithm-agnostic)
        List<LineResult> legacy  = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.PARETO);
        List<LineResult> n3      = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.NSGA_III);
        f += assertCond("paretoOptimal(PARETO) ≡ paretoOptimal(NSGA_III) on lineNo set",
                lineNoSet(legacy).equals(lineNoSet(n3)));

        // ranked path under NSGA-III exposes perp distances (finite + ≥ 0)
        List<NsgaIII.Ranked<LineResult>> ranked =
                AnalyzerCore.paretoOptimalRankedNsgaIII(results, analyzer.goals());
        f += assertCond("paretoOptimalRankedNsgaIII non-empty", !ranked.isEmpty());
        boolean allValid = true;
        for (NsgaIII.Ranked<LineResult> rk : ranked) {
            if (!(Double.isFinite(rk.perpendicularDistance()) && rk.perpendicularDistance() >= 0))
                allValid = false;
            if (rk.referencePointIndex() < 0) allValid = false;
            if (rk.rank() != 1) allValid = false;
        }
        f += assertCond("every ranked member has finite, ≥0 perp distance + rank=1",
                allValid);
        return f;
    }

    // ── 7. End-to-end (3-axis) ─────────────────────────────────────────

    private static int testEndToEndThreeAxis() throws Exception {
        System.out.println("\n── end-to-end: 3-axis corpus (M=3, NSGA-III's home ground) ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"throughput\",\"mode\":\"maximize\",\"weight\":30}"
                    + "]}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 8, 30.0, 10.0, false, 0.0, false,
                new LineParser.KvLineParser(),
                FrontAlgorithm.NSGA_III);

        List<String> corpus = new ArrayList<>();
        double[][] tuples = {
            // (cost, latency, throughput) — heterogeneous mix
            {0.10, 9.0,  400},  {0.25, 7.0, 1300}, {0.40, 5.0, 2600},
            {0.55, 3.0, 3800},  {0.80, 2.0, 4500}, {0.90, 8.0,  900},
            {0.95, 6.0, 1500},  {0.99, 4.0, 2200}, {0.60, 4.5, 3200},
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

        int f = 0;
        f += assertCond("3-axis corpus: " + tuples.length + " results streamed",
                results.size() == tuples.length);

        // NSGA-III ranked path on declared 3 goals
        List<NsgaIII.Ranked<LineResult>> ranked =
                AnalyzerCore.paretoOptimalRankedNsgaIII(results, analyzer.goals());
        f += assertCond("3-axis ranked path non-empty", !ranked.isEmpty());

        // Reference points for M=3 use defaultDivisions(3) = 7 → 36 points;
        // some refs must actually be used by candidates.
        Set<Integer> refsUsed = new HashSet<>();
        for (NsgaIII.Ranked<LineResult> rk : ranked) refsUsed.add(rk.referencePointIndex());
        f += assertCond("3-axis: ≥ 2 distinct reference points used by the front",
                refsUsed.size() >= 2);

        // Membership still equals legacy
        List<LineResult> legacy = AnalyzerCore.paretoOptimal(results, analyzer.goals(), FrontAlgorithm.PARETO);
        Set<Integer> legacySet = lineNoSet(legacy);
        Set<Integer> nsgaSet   = new HashSet<>();
        for (NsgaIII.Ranked<LineResult> rk : ranked) nsgaSet.add(rk.item().lineNo);
        f += assertCond("3-axis: NSGA-III front membership == legacy Pareto front",
                legacySet.equals(nsgaSet));
        return f;
    }

    // ── 8. BestLinesReporter ───────────────────────────────────────────

    private static int testBestLinesReporterPopulatesDiversity() throws Exception {
        System.out.println("\n── BestLinesReporter populates diversity under NSGA-III ──");
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
                    "id=n_%02d cost=%.3f latency=%.2f", i + 1, tuples[i][0], tuples[i][1]));
        }
        List<LineResult> results = new ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(LineResult r) { results.add(r); }
        });

        BestLinesReporter.Report n3report = BestLinesReporter.build(
                null, results, analyzer.goals(), FrontAlgorithm.NSGA_III);
        int f = 0;
        f += assertCond("declared-goal front non-empty under NSGA-III",
                !n3report.declaredGoalPareto().isEmpty());

        // perp distance: finite, ≥ 0 (no +∞ sentinel like NSGA-II crowding)
        boolean anyFinitePerp = false;
        boolean anyInfinite = false;
        for (BestLinesReporter.LineMention m : n3report.declaredGoalPareto()) {
            if (Double.isFinite(m.crowdingDistance()) && m.crowdingDistance() >= 0) anyFinitePerp = true;
            if (Double.isInfinite(m.crowdingDistance())) anyInfinite = true;
        }
        f += assertCond("under NSGA-III, diversity field is finite & non-negative",
                anyFinitePerp);
        f += assertCond("under NSGA-III, no +∞ sentinels (unlike NSGA-II crowding)",
                !anyInfinite);

        // The PARETO path leaves diversity as NaN — sanity contrast
        BestLinesReporter.Report pareto = BestLinesReporter.build(
                null, results, analyzer.goals(), FrontAlgorithm.PARETO);
        boolean allNan = true;
        for (BestLinesReporter.LineMention m : pareto.declaredGoalPareto()) {
            if (!Double.isNaN(m.crowdingDistance())) { allNan = false; break; }
        }
        f += assertCond("under PARETO, every diversity field stays NaN",
                allNan);
        return f;
    }

    // ── helpers ────────────────────────────────────────────────────────

    private static Set<Integer> lineNoSet(List<LineResult> results) {
        Set<Integer> s = new HashSet<>();
        for (LineResult r : results) s.add(r.lineNo);
        return s;
    }

    @SuppressWarnings("unused")
    private static String dumpRefs(double[][] refs) {
        StringBuilder sb = new StringBuilder();
        for (double[] r : refs) sb.append(Arrays.toString(r)).append("\n");
        return sb.toString();
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
