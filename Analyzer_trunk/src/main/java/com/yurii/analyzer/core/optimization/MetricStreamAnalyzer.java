package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore.LineResult;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.DoubleUnaryOperator;
import java.util.function.ToDoubleFunction;

/**
 * Auto-discovery + line-to-line analysis of agnostic numeric metrics that
 * appear in line outputs (executed stdout/stderr or static text).  No metric
 * keys are hardcoded — anything that parses as a number after the
 * upstream {@code KV_PAIR_RE}/{@code NUMBER_RE} regexes counts as a candidate.
 *
 * For every metric with ≥ {@code minSamples} occurrences, this class applies
 * the full Optimization-theory toolkit assembled in {@link Optimizers}:
 *   • Welford-style running mean and population stdev
 *   • Empirical quantiles (P5, P50, P95)
 *   • Composite Simpson AUC over the index-vs-metric series
 *   • Trapezoidal cumulative integral
 *   • Brent's method for argmin & argmax on a linearly-interpolated series
 *   • Nelder-Mead simplex fit of the relaxation model  a + b·exp(-c·n)
 *   • Simulated annealing for a stochastic global minimum
 *   • RK4 numerical integration of  dy/dn = (μ - y)/τ  with τ fitted by Brent
 *     against the residual norm — yields a smoothed trajectory
 *   • Newton-Raphson refinement of derivative sign-changes → critical points
 *
 * Cross-metric: {@link #autoPareto} runs Pareto-front extraction over every
 * discovered metric simultaneously (defaults to minimisation; {@link
 * #autoPareto(List, int, java.util.Set)} accepts an explicit "maximise these"
 * set).  This is the multi-objective complement to the config-declared
 * {@code AnalyzerCore.paretoOptimal}.
 */
public final class MetricStreamAnalyzer {
    private MetricStreamAnalyzer() {}

    public record MetricAnalysis(
            String key,
            int n,
            double mean, double stdev,
            double p5, double p50, double p95,
            double simpsonAuc,
            double trapezoidalSum,
            double brentArgmin, double brentMin,
            double brentArgmax, double brentMax,
            double[] expFitParams,    // a, b, c  for y(n) = a + b·exp(-c·n)
            double expFitLoss,
            double saArgmin, double saMin,
            double[] criticalPoints,
            double rk4Tau,            // fitted relaxation time
            double[] rk4Smoothed
    ) {}

    /** Run the full toolkit on every numeric metric appearing in ≥ minSamples lines.
     *  Truly agnostic: the ONLY filter is "does the value parse as a finite number?".
     *  No key-name blacklist — if a metric called "status" or "operation" carries a
     *  numeric value (e.g. status=200, operation=42), it counts as a metric stream. */
    public static List<MetricAnalysis> analyzeAll(List<LineResult> results, int minSamples) {
        Map<String, List<double[]>> seriesByKey = new LinkedHashMap<>();
        for (LineResult r : results) {
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                String key = e.getKey();
                java.util.OptionalDouble od = com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(e.getValue());
                if (od.isEmpty()) continue;
                double v = od.getAsDouble();
                if (!Double.isFinite(v)) continue;
                seriesByKey.computeIfAbsent(key, k -> new ArrayList<>())
                          .add(new double[]{r.lineNo, v});
            }
        }

        List<MetricAnalysis> out = new ArrayList<>();
        for (Map.Entry<String, List<double[]>> e : seriesByKey.entrySet()) {
            if (e.getValue().size() < minSamples) continue;
            try {
                out.add(analyzeOne(e.getKey(), e.getValue()));
            } catch (Exception ex) {
                // A bad series shouldn't kill the whole sweep.
            }
        }
        out.sort(Comparator.comparingInt(a -> -a.n()));
        return out;
    }

    /** Public entry point so the streaming aggregator can apply the full
     *  per-metric toolkit (Welford / Simpson / Brent / Nelder-Mead / SA /
     *  RK4 / Newton) to a bounded reservoir of samples collected during
     *  streaming.  The {@code raw} list contains {@code [lineNo, value]}
     *  pairs; this method sorts by lineNo internally. */
    public static MetricAnalysis analyzeOnePublic(String key, List<double[]> raw) {
        return analyzeOne(key, raw);
    }

    private static MetricAnalysis analyzeOne(String key, List<double[]> raw) {
        raw.sort(Comparator.comparingDouble(a -> a[0]));
        int n = raw.size();
        double[] vals = new double[n];
        for (int i = 0; i < n; i++) vals[i] = raw.get(i)[1];

        // Descriptive (Welford-equivalent two-pass for clarity)
        double sum = 0;
        for (double v : vals) sum += v;
        final double mean = sum / n;
        double sumSq = 0;
        for (double v : vals) sumSq += (v - mean) * (v - mean);
        double stdev = Math.sqrt(sumSq / n);

        double[] sorted = vals.clone();
        Arrays.sort(sorted);
        double p5  = quantile(sorted, 0.05);
        double p50 = quantile(sorted, 0.50);
        double p95 = quantile(sorted, 0.95);

        // Numerical integration of the metric vs index.
        double simpson = Optimizers.simpsonOverSamples(vals, 1.0);
        double trap = 0;
        for (int i = 0; i < n - 1; i++) trap += 0.5 * (vals[i] + vals[i + 1]);

        // Linear-interpolation continuous extension on [0, n-1].
        DoubleUnaryOperator interp = x -> {
            if (x <= 0) return vals[0];
            if (x >= n - 1) return vals[n - 1];
            int lo = (int) Math.floor(x);
            double t = x - lo;
            return vals[lo] * (1 - t) + vals[lo + 1] * t;
        };

        // 1D minimisation of the interpolated series → argmin / argmax line index.
        Optimizers.Min1D bMin = Optimizers.brentMinimize(interp, 0, n - 1, 1e-6, 200);
        Optimizers.Min1D bMax = Optimizers.brentMinimize(x -> -interp.applyAsDouble(x), 0, n - 1, 1e-6, 200);

        // Nelder-Mead fit of  y(i) = a + b · exp(-c · i)
        Optimizers.MultivariateFunction lossExp = params -> {
            double a = params[0], b = params[1], c = params[2];
            double L = 0;
            for (int i = 0; i < n; i++) {
                double pred = a + b * Math.exp(-c * i);
                double d = pred - vals[i];
                L += d * d;
            }
            return L;
        };
        double[] x0 = {vals[n - 1], vals[0] - vals[n - 1], 0.05};
        Optimizers.MinND nm = Optimizers.nelderMead(lossExp, x0, 0.1, 3000, 1e-9);

        // Simulated annealing on the interpolated series (1D global min).
        Optimizers.MinND sa = Optimizers.simulatedAnnealing(
                params -> {
                    double x = Math.max(0, Math.min(n - 1, params[0]));
                    return interp.applyAsDouble(x);
                },
                new double[]{(n - 1) / 2.0},
                new double[]{Math.max(0.5, (n - 1) / 4.0)},
                1.0, 0.999, 5000, 12345L);

        // RK4-fitted relaxation:   dy/dn = (μ - y)/τ   with τ minimising residual.
        DoubleUnaryOperator rk4Loss = tau -> {
            if (tau <= 0) return Double.POSITIVE_INFINITY;
            final double tStar = tau;
            Optimizers.VectorField field = (tt, yy) -> new double[]{(mean - yy[0]) / tStar};
            double[] y = {vals[0]};
            double L = 0;
            for (int i = 0; i < n; i++) {
                if (i > 0) y = Optimizers.rk4(field, y, i - 1, i, 0.1);
                double d = y[0] - vals[i];
                L += d * d;
            }
            return L;
        };
        Optimizers.Min1D tauFit = Optimizers.brentMinimize(rk4Loss, 0.1, Math.max(2.0, n * 2.0), 1e-3, 50);
        final double tauStar = tauFit.x();

        double[] smoothed = new double[n];
        smoothed[0] = vals[0];
        Optimizers.VectorField smoothField = (tt, yy) -> new double[]{(mean - yy[0]) / tauStar};
        double[] yState = {vals[0]};
        for (int i = 1; i < n; i++) {
            yState = Optimizers.rk4(smoothField, yState, i - 1, i, 0.1);
            smoothed[i] = yState[0];
        }

        // Critical points: detect sign changes in the discrete derivative,
        // refine each via Newton-Raphson on the central-difference derivative
        // of the linear-interpolation function.
        DoubleUnaryOperator deriv = x -> {
            double h = 0.5;
            double xl = Math.max(0, x - h), xh = Math.min(n - 1, x + h);
            return (interp.applyAsDouble(xh) - interp.applyAsDouble(xl)) / Math.max(1e-12, xh - xl);
        };
        DoubleUnaryOperator deriv2 = x -> {
            double h = 0.5;
            double xl = Math.max(0, x - h), xh = Math.min(n - 1, x + h);
            return (deriv.applyAsDouble(xh) - deriv.applyAsDouble(xl)) / Math.max(1e-12, xh - xl);
        };
        List<Double> crits = new ArrayList<>();
        for (int i = 2; i < n; i++) {
            double diffPrev = vals[i - 1] - vals[i - 2];
            double diffCur  = vals[i] - vals[i - 1];
            if (diffPrev * diffCur < 0) {
                double seed = i - 1.0;
                double root = Optimizers.newtonRaphson(deriv, deriv2, seed, 1e-4, 30);
                if (root >= 0 && root <= n - 1) {
                    boolean dup = false;
                    for (double c : crits) if (Math.abs(c - root) < 0.5) { dup = true; break; }
                    if (!dup) crits.add(root);
                }
            }
        }
        double[] critArr = new double[crits.size()];
        for (int i = 0; i < crits.size(); i++) critArr[i] = crits.get(i);

        return new MetricAnalysis(
                key, n, mean, stdev, p5, p50, p95,
                simpson, trap,
                bMin.x(), bMin.fx(),
                bMax.x(), -bMax.fx(),
                nm.x(), nm.fx(),
                sa.x()[0], sa.fx(),
                critArr, tauStar, smoothed);
    }

    /**
     * Pareto front across every numeric metric auto-discovered in the
     * results — minimisation by default for every axis. This is the
     * complement to {@code AnalyzerCore.paretoOptimal} which only
     * considers config-declared goals.
     */
    public static List<LineResult> autoPareto(List<LineResult> results, int minSamples) {
        return autoPareto(results, minSamples, java.util.Set.of(), FrontAlgorithm.DEFAULT);
    }

    /** Variant: select between the legacy Pareto algorithm and NSGA-II.
     *  Same membership, but NSGA-II is the source for the crowding-distance
     *  values that {@link #autoParetoRanked} exposes. */
    public static List<LineResult> autoPareto(List<LineResult> results, int minSamples,
                                              FrontAlgorithm algo) {
        return autoPareto(results, minSamples, java.util.Set.of(), algo);
    }

    /**
     * Pareto front across all auto-discovered metrics, with explicit
     * "maximise these" override set.
     */
    public static List<LineResult> autoPareto(List<LineResult> results, int minSamples,
                                              java.util.Set<String> maximizeKeys) {
        return autoPareto(results, minSamples, maximizeKeys, FrontAlgorithm.DEFAULT);
    }

    /** Most-explicit autoPareto overload: maximise-set + front algorithm. */
    public static List<LineResult> autoPareto(List<LineResult> results, int minSamples,
                                              java.util.Set<String> maximizeKeys,
                                              FrontAlgorithm algo) {
        Map<String, Integer> coverage = new HashMap<>();
        for (LineResult r : results) {
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(e.getValue()).isEmpty()) continue;
                coverage.merge(e.getKey(), 1, Integer::sum);
            }
        }
        List<String> keys = new ArrayList<>();
        for (Map.Entry<String, Integer> e : coverage.entrySet())
            if (e.getValue() >= minSamples) keys.add(e.getKey());
        if (keys.isEmpty()) return List.of();

        // Sort axes by coverage descending so we drop the lowest-coverage one
        // first if no line happens to carry every key. This adaptive filter
        // mirrors the spirit of {@code AnalyzerCore.paretoOptimal}'s
        // PARETO_MIN_COVERAGE gate without picking an arbitrary fraction —
        // the corpus tells us how thin to slice.
        keys.sort((a, b) -> Integer.compare(coverage.get(b), coverage.get(a)));
        List<String> activeKeys = new ArrayList<>(keys);
        List<LineResult> eligible = new ArrayList<>();
        while (!activeKeys.isEmpty()) {
            eligible.clear();
            outer:
            for (LineResult r : results) {
                for (String k : activeKeys) {
                    String v = r.features.kvPairs.get(k);
                    if (v == null) continue outer;
                    if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(v).isEmpty()) continue outer;
                }
                eligible.add(r);
            }
            if (!eligible.isEmpty()) break;
            activeKeys.remove(activeKeys.size() - 1); // drop sparsest axis and retry
        }
        if (eligible.isEmpty()) return List.of();

        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>();
        List<Boolean> minimize = new ArrayList<>();
        for (String key : activeKeys) {
            objs.add(r -> com.yurii.analyzer.core.AnalyzerCore
                    .tryParseNumeric(r.features.kvPairs.get(key)).orElse(Double.NaN));
            minimize.add(!maximizeKeys.contains(key));
        }
        FrontAlgorithm effective = (algo == null) ? FrontAlgorithm.DEFAULT : algo;
        if (effective == FrontAlgorithm.NSGA_II  || effective == FrontAlgorithm.NSGA_III
                || effective == FrontAlgorithm.SPEA2 || effective == FrontAlgorithm.MOEA_D) {
            GoalSpec[] goalSpecs = new GoalSpec[activeKeys.size()];
            for (int i = 0; i < activeKeys.size(); i++) {
                goalSpecs[i] = minimize.get(i)
                        ? GoalSpec.min("axis_" + i)
                        : GoalSpec.max("axis_" + i);
            }
            double[][] vectors = Dominance.extractVectors(eligible, objs);
            switch (effective) {
                case NSGA_III: return Dominance.paretoFrontNsgaIII(eligible, vectors, goalSpecs);
                case SPEA2:    return Dominance.paretoFrontSpea2(eligible, vectors, goalSpecs);
                case MOEA_D:   return Dominance.paretoFrontMoeaD(eligible, vectors, goalSpecs);
                default:       return Dominance.paretoFrontNsgaII(eligible, vectors, goalSpecs);
            }
        }
        return Optimizers.paretoFront(eligible, objs, minimize);
    }

    /**
     * NSGA-II flavoured auto-Pareto: the same first-front membership as
     * {@link #autoPareto}, but each member is wrapped in
     * {@link NsgaII.Ranked} with its crowding distance.  Used by
     * {@link BestLinesReporter} to populate {@code LineMention.crowdingDistance}
     * on the auto-Pareto section.
     */
    public static List<NsgaII.Ranked<LineResult>> autoParetoRanked(List<LineResult> results, int minSamples) {
        return autoParetoRanked(results, minSamples, java.util.Set.of());
    }

    /** As {@link #autoParetoRanked(List, int)} but with explicit maximise-set. */
    public static List<NsgaII.Ranked<LineResult>> autoParetoRanked(List<LineResult> results, int minSamples,
                                                                    java.util.Set<String> maximizeKeys) {
        Map<String, Integer> coverage = new HashMap<>();
        for (LineResult r : results) {
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(e.getValue()).isEmpty()) continue;
                coverage.merge(e.getKey(), 1, Integer::sum);
            }
        }
        List<String> keys = new ArrayList<>();
        for (Map.Entry<String, Integer> e : coverage.entrySet())
            if (e.getValue() >= minSamples) keys.add(e.getKey());
        if (keys.isEmpty()) return List.of();
        keys.sort((a, b) -> Integer.compare(coverage.get(b), coverage.get(a)));
        List<String> activeKeys = new ArrayList<>(keys);
        List<LineResult> eligible = new ArrayList<>();
        while (!activeKeys.isEmpty()) {
            eligible.clear();
            outer:
            for (LineResult r : results) {
                for (String k : activeKeys) {
                    String v = r.features.kvPairs.get(k);
                    if (v == null) continue outer;
                    if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(v).isEmpty()) continue outer;
                }
                eligible.add(r);
            }
            if (!eligible.isEmpty()) break;
            activeKeys.remove(activeKeys.size() - 1);
        }
        if (eligible.isEmpty()) return List.of();
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>();
        GoalSpec[] goalSpecs = new GoalSpec[activeKeys.size()];
        for (int i = 0; i < activeKeys.size(); i++) {
            String key = activeKeys.get(i);
            objs.add(r -> com.yurii.analyzer.core.AnalyzerCore
                    .tryParseNumeric(r.features.kvPairs.get(key)).orElse(Double.NaN));
            goalSpecs[i] = maximizeKeys.contains(key) ? GoalSpec.max("axis_" + i) : GoalSpec.min("axis_" + i);
        }
        double[][] vectors = Dominance.extractVectors(eligible, objs);
        return NsgaII.firstFrontWithCrowding(eligible, vectors, goalSpecs);
    }

    /**
     * Tier-5.1 — NSGA-III flavoured auto-Pareto.  Same eligibility filter +
     * adaptive axis-dropping as {@link #autoParetoRanked}, but the ranked
     * payload is {@link NsgaIII.Ranked} (referencePointIndex +
     * perpendicularDistance) instead of crowding distance.  Used by
     * {@link BestLinesReporter} under {@link FrontAlgorithm#NSGA_III}.
     */
    public static List<NsgaIII.Ranked<LineResult>> autoParetoRankedNsgaIII(List<LineResult> results, int minSamples) {
        return autoParetoRankedNsgaIII(results, minSamples, java.util.Set.of());
    }

    /** As {@link #autoParetoRankedNsgaIII(List, int)} with explicit maximise-set. */
    public static List<NsgaIII.Ranked<LineResult>> autoParetoRankedNsgaIII(List<LineResult> results, int minSamples,
                                                                              java.util.Set<String> maximizeKeys) {
        Map<String, Integer> coverage = new HashMap<>();
        for (LineResult r : results) {
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(e.getValue()).isEmpty()) continue;
                coverage.merge(e.getKey(), 1, Integer::sum);
            }
        }
        List<String> keys = new ArrayList<>();
        for (Map.Entry<String, Integer> e : coverage.entrySet())
            if (e.getValue() >= minSamples) keys.add(e.getKey());
        if (keys.isEmpty()) return List.of();
        keys.sort((a, b) -> Integer.compare(coverage.get(b), coverage.get(a)));
        List<String> activeKeys = new ArrayList<>(keys);
        List<LineResult> eligible = new ArrayList<>();
        while (!activeKeys.isEmpty()) {
            eligible.clear();
            outer:
            for (LineResult r : results) {
                for (String k : activeKeys) {
                    String v = r.features.kvPairs.get(k);
                    if (v == null) continue outer;
                    if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(v).isEmpty()) continue outer;
                }
                eligible.add(r);
            }
            if (!eligible.isEmpty()) break;
            activeKeys.remove(activeKeys.size() - 1);
        }
        if (eligible.isEmpty()) return List.of();
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>();
        GoalSpec[] goalSpecs = new GoalSpec[activeKeys.size()];
        for (int i = 0; i < activeKeys.size(); i++) {
            String key = activeKeys.get(i);
            objs.add(r -> com.yurii.analyzer.core.AnalyzerCore
                    .tryParseNumeric(r.features.kvPairs.get(key)).orElse(Double.NaN));
            goalSpecs[i] = maximizeKeys.contains(key) ? GoalSpec.max("axis_" + i) : GoalSpec.min("axis_" + i);
        }
        double[][] vectors = Dominance.extractVectors(eligible, objs);
        return NsgaIII.firstFrontWithReference(eligible, vectors, goalSpecs);
    }

    /**
     * Tier-5.1 — SPEA2 flavoured auto-Pareto.  Same adaptive axis-dropping +
     * eligibility as the NSGA variants; the ranked payload is
     * {@link Spea2.Ranked} (strength + raw fitness + k-NN distance + density
     * + final fitness).  Used by {@link BestLinesReporter} under
     * {@link FrontAlgorithm#SPEA2}.
     */
    public static List<Spea2.Ranked<LineResult>> autoParetoRankedSpea2(List<LineResult> results, int minSamples) {
        return autoParetoRankedSpea2(results, minSamples, java.util.Set.of());
    }

    public static List<Spea2.Ranked<LineResult>> autoParetoRankedSpea2(List<LineResult> results, int minSamples,
                                                                          java.util.Set<String> maximizeKeys) {
        Object[] prep = autoRankedPrologue(results, minSamples, maximizeKeys);
        if (prep == null) return List.of();
        @SuppressWarnings("unchecked")
        List<LineResult> eligible = (List<LineResult>) prep[0];
        double[][] vectors = (double[][]) prep[1];
        GoalSpec[] goalSpecs = (GoalSpec[]) prep[2];
        return Spea2.firstFrontWithFitness(eligible, vectors, goalSpecs);
    }

    /**
     * Tier-5.1 — MOEA/D flavoured auto-Pareto.  Same adaptive axis-dropping
     * as the NSGA variants; the ranked payload is {@link MoeaD.Ranked}
     * (bestWeightIndex + bestTchebycheff + meanTchebycheff).  Used by
     * {@link BestLinesReporter} under {@link FrontAlgorithm#MOEA_D}.
     */
    public static List<MoeaD.Ranked<LineResult>> autoParetoRankedMoeaD(List<LineResult> results, int minSamples) {
        return autoParetoRankedMoeaD(results, minSamples, java.util.Set.of());
    }

    public static List<MoeaD.Ranked<LineResult>> autoParetoRankedMoeaD(List<LineResult> results, int minSamples,
                                                                          java.util.Set<String> maximizeKeys) {
        Object[] prep = autoRankedPrologue(results, minSamples, maximizeKeys);
        if (prep == null) return List.of();
        @SuppressWarnings("unchecked")
        List<LineResult> eligible = (List<LineResult>) prep[0];
        double[][] vectors = (double[][]) prep[1];
        GoalSpec[] goalSpecs = (GoalSpec[]) prep[2];
        return MoeaD.firstFrontWithDecomposition(eligible, vectors, goalSpecs);
    }

    /**
     * Shared eligibility / adaptive axis-dropping / vector-extraction
     * prologue for the ranked-front auto-discovery extractors (SPEA2 +
     * MOEA/D — and applicable to NSGA-II/III if desired, though those keep
     * their bespoke implementations for legacy stability).  Returns
     * {@code null} when nothing eligible remains.
     */
    private static Object[] autoRankedPrologue(List<LineResult> results, int minSamples,
                                                  java.util.Set<String> maximizeKeys) {
        Map<String, Integer> coverage = new HashMap<>();
        for (LineResult r : results) {
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(e.getValue()).isEmpty()) continue;
                coverage.merge(e.getKey(), 1, Integer::sum);
            }
        }
        List<String> keys = new ArrayList<>();
        for (Map.Entry<String, Integer> e : coverage.entrySet())
            if (e.getValue() >= minSamples) keys.add(e.getKey());
        if (keys.isEmpty()) return null;
        keys.sort((a, b) -> Integer.compare(coverage.get(b), coverage.get(a)));
        List<String> activeKeys = new ArrayList<>(keys);
        List<LineResult> eligible = new ArrayList<>();
        while (!activeKeys.isEmpty()) {
            eligible.clear();
            outer:
            for (LineResult r : results) {
                for (String k : activeKeys) {
                    String v = r.features.kvPairs.get(k);
                    if (v == null) continue outer;
                    if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(v).isEmpty()) continue outer;
                }
                eligible.add(r);
            }
            if (!eligible.isEmpty()) break;
            activeKeys.remove(activeKeys.size() - 1);
        }
        if (eligible.isEmpty()) return null;
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>();
        GoalSpec[] goalSpecs = new GoalSpec[activeKeys.size()];
        for (int i = 0; i < activeKeys.size(); i++) {
            String key = activeKeys.get(i);
            objs.add(r -> com.yurii.analyzer.core.AnalyzerCore
                    .tryParseNumeric(r.features.kvPairs.get(key)).orElse(Double.NaN));
            goalSpecs[i] = maximizeKeys.contains(key) ? GoalSpec.max("axis_" + i) : GoalSpec.min("axis_" + i);
        }
        double[][] vectors = Dominance.extractVectors(eligible, objs);
        return new Object[]{ eligible, vectors, goalSpecs };
    }

    /** Active metric keys (≥ minSamples occurrences after filtering helper/categorical keys). */
    public static List<String> discoveredKeys(List<LineResult> results, int minSamples) {
        Map<String, Integer> coverage = new HashMap<>();
        for (LineResult r : results) {
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                if (com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(e.getValue()).isEmpty()) continue;
                coverage.merge(e.getKey(), 1, Integer::sum);
            }
        }
        List<String> out = new ArrayList<>();
        for (Map.Entry<String, Integer> e : coverage.entrySet())
            if (e.getValue() >= minSamples) out.add(e.getKey());
        out.sort(Comparator.comparingInt(coverage::get).reversed());
        return out;
    }

    private static double quantile(double[] sortedAsc, double q) {
        if (sortedAsc.length == 0) return 0;
        if (sortedAsc.length == 1) return sortedAsc[0];
        double pos = q * (sortedAsc.length - 1);
        int lo = (int) Math.floor(pos), hi = (int) Math.ceil(pos);
        double t = pos - lo;
        return sortedAsc[lo] * (1 - t) + sortedAsc[hi] * t;
    }
}
