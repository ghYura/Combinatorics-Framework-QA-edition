package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Streaming aggregator for the {@code analyzeStream} pipeline.  Replaces the
 * legacy two-pass corpus-profile-then-score flow when the workload is too
 * large to materialise as {@code List<LineResult>}.  Bounded memory regardless
 * of the candidate count: O(K) per discovered metric key, plus O(|Pareto front|)
 * retained candidates.
 *
 * What it tracks per discovered numeric metric:
 *   • Welford running mean / population stdev / sample count
 *   • Running argmin / argmax (the {@link LineResult} that holds the extremum)
 *   • running min / max value
 *
 * Cross-metric:
 *   • Online Pareto front (minimisation by default; explicit max-set override)
 *
 * Thread safety: NOT internally locked — single-thread updater assumed.  For
 * parallel streaming, shard by lineNo and merge {@link Snapshot}s at the end.
 */
public final class OnlineMetricAggregator {

    /** Default bounded capacity of the per-key reservoir.  ~16 KB per key
     *  at this size; cheap even with hundreds of auto-discovered metrics.
     *  Override at construction via the explicit-reservoir-capacity ctor. */
    public static final int RESERVOIR_CAP = 1024;

    /** Per-key streaming stats + champion line references + bounded
     *  reservoir of (lineNo, value) samples (Algorithm R, capped at
     *  {@link #RESERVOIR_CAP}).  The reservoir lets the {@link Snapshot}
     *  call the full {@link MetricStreamAnalyzer} per-metric toolkit
     *  (exp-fit, Simpson AUC, RK4 smoothing, critical points) at
     *  finalisation time, even though we never store the full corpus. */
    public static final class KeyStats {
        public final String key;
        public long n;
        public double mean;
        public double m2;     // Welford's M2 for variance
        public double min = Double.POSITIVE_INFINITY;
        public double max = Double.NEGATIVE_INFINITY;
        public int argminLineNo = -1;
        public int argmaxLineNo = -1;
        public String argminSnippet = "";
        public String argmaxSnippet = "";

        /** Reservoir of (lineNo, value) pairs.  Null when reservoir is
         *  disabled (capacity ≤ 0); otherwise a fixed-size array filled
         *  uniformly-at-random via Algorithm R. */
        final double[][] reservoir;
        final java.util.Random reservoirRng;

        KeyStats(String key) { this(key, RESERVOIR_CAP); }

        KeyStats(String key, int reservoirCapacity) {
            this.key = key;
            this.reservoir = (reservoirCapacity > 0)
                    ? new double[reservoirCapacity][]
                    : null;
            // Per-key deterministic seed → reproducible reservoir
            // contents across runs on the same corpus.
            this.reservoirRng = (reservoir == null)
                    ? null
                    : new java.util.Random(0x9E3779B97F4A7C15L ^ key.hashCode());
        }

        void add(double v, int lineNo, String snippet) {
            n++;
            double d = v - mean;
            mean += d / n;
            m2 += d * (v - mean);
            if (v < min) { min = v; argminLineNo = lineNo; argminSnippet = snippet; }
            if (v > max) { max = v; argmaxLineNo = lineNo; argmaxSnippet = snippet; }
            // Reservoir sampling — Algorithm R (Vitter 1985).  Bounded
            // memory regardless of N, uniform-at-random sample property.
            if (reservoir != null) {
                int seen = (int) Math.min(n, Integer.MAX_VALUE);  // total seen so far
                if (seen <= reservoir.length) {
                    reservoir[seen - 1] = new double[]{lineNo, v};
                } else {
                    int j = reservoirRng.nextInt(seen);
                    if (j < reservoir.length) reservoir[j] = new double[]{lineNo, v};
                }
            }
        }

        /** Merge another shard's stats into this one.  Welford's parallel
         *  algorithm (Chan/Golub/LeVeque) for numerically-stable variance
         *  combination; min/max take the winner along with its line ref;
         *  reservoirs are concatenated and uniformly subsampled back to
         *  capacity (correct under round-robin shard assignment where each
         *  shard sees a similar number of items). */
        void merge(KeyStats o) {
            if (o == null || o.n == 0) return;
            if (this.n == 0) {
                this.n = o.n;
                this.mean = o.mean;
                this.m2 = o.m2;
                this.min = o.min;
                this.max = o.max;
                this.argminLineNo = o.argminLineNo;
                this.argmaxLineNo = o.argmaxLineNo;
                this.argminSnippet = o.argminSnippet;
                this.argmaxSnippet = o.argmaxSnippet;
                mergeReservoirs(o);
                return;
            }
            long total = this.n + o.n;
            double delta = o.mean - this.mean;
            double newMean = (this.mean * this.n + o.mean * o.n) / total;
            this.m2 = this.m2 + o.m2 + delta * delta * ((double) this.n * o.n) / total;
            this.mean = newMean;
            this.n = total;
            if (o.min < this.min) { this.min = o.min; this.argminLineNo = o.argminLineNo; this.argminSnippet = o.argminSnippet; }
            if (o.max > this.max) { this.max = o.max; this.argmaxLineNo = o.argmaxLineNo; this.argmaxSnippet = o.argmaxSnippet; }
            mergeReservoirs(o);
        }

        private void mergeReservoirs(KeyStats o) {
            if (this.reservoir == null || o.reservoir == null) return;
            java.util.List<double[]> all = new java.util.ArrayList<>();
            for (double[] s : this.reservoir) if (s != null) all.add(s);
            for (double[] s : o.reservoir) if (s != null) all.add(s);
            int cap = this.reservoir.length;
            if (all.size() > cap) {
                java.util.Collections.shuffle(all, this.reservoirRng);
                all = all.subList(0, cap);
            }
            for (int i = 0; i < this.reservoir.length; i++) this.reservoir[i] = null;
            for (int i = 0; i < all.size(); i++) this.reservoir[i] = all.get(i);
        }

        /** Snapshot of the reservoir, sorted by lineNo (the order
         *  {@link MetricStreamAnalyzer#analyzeOnePublic} expects). */
        java.util.List<double[]> reservoirSnapshot() {
            if (reservoir == null) return java.util.List.of();
            int kept = (int) Math.min(n, reservoir.length);
            java.util.List<double[]> out = new java.util.ArrayList<>(kept);
            for (int i = 0; i < kept; i++) {
                if (reservoir[i] != null) out.add(reservoir[i].clone());
            }
            out.sort(java.util.Comparator.comparingDouble(a -> a[0]));
            return out;
        }

        public double stdev() { return n < 2 ? 0.0 : Math.sqrt(m2 / n); }

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("n", n);
            m.put("mean", mean);
            m.put("stdev", stdev());
            m.put("min", min);
            m.put("max", max);
            m.put("argmin_line", argminLineNo);
            m.put("argmax_line", argmaxLineNo);
            return m;
        }
    }

    /** Online Pareto front: each {@code add()} is O(|front|).  Default rule
     *  is minimise every axis.  Pass a non-empty {@code maximizeKeys} to flip
     *  the comparison on those axes. */
    public static final class OnlinePareto {
        /** Per-key goals.  Declared goals seed this map; auto-discovered
         *  keys are added lazily on first sighting using {@link #autoPolicy}
         *  (inferred mode + weight).  When the policy says "skip", no entry
         *  is added and the axis is excluded from dominance comparisons. */
        private final Map<String, GoalSpec> goalByKey;
        private final java.util.Set<String> declaredKeys;     // for telemetry only
        private final DiscoveryPolicy autoPolicy;
        /** Front members keyed by the metric vector at which they entered, so
         *  late updates that change a member's position aren't possible — once
         *  on the front, the candidate is frozen. */
        private final List<LineResult> front = new ArrayList<>();
        private final List<double[]> frontVecs = new ArrayList<>();
        private List<String> currentKeys = new ArrayList<>();

        /** Most-explicit constructor: declared goals + auto-discovery policy. */
        public OnlinePareto(List<GoalSpec> goals, DiscoveryPolicy autoPolicy) {
            this.goalByKey = new LinkedHashMap<>();
            this.declaredKeys = new java.util.LinkedHashSet<>();
            if (goals != null) for (GoalSpec g : goals) {
                this.goalByKey.put(g.key(), g);
                this.declaredKeys.add(g.key());
            }
            this.autoPolicy = (autoPolicy == null) ? DiscoveryPolicy.DEFAULT : autoPolicy;
        }

        /** Goals only — auto-keys handled per {@link DiscoveryPolicy#DEFAULT}
         *  (include with lexical inference). */
        public OnlinePareto(List<GoalSpec> goals) {
            this(goals, DiscoveryPolicy.DEFAULT);
        }

        /** Legacy: binary minimise/maximise via key-set; auto-keys per
         *  {@link DiscoveryPolicy#DEFAULT}. */
        public OnlinePareto(java.util.Set<String> maximizeKeys) {
            this(maximizeKeys == null ? List.<GoalSpec>of() :
                    maximizeKeys.stream().map(GoalSpec::max).toList(),
                 DiscoveryPolicy.DEFAULT);
        }

        /** Look up the effective goal for a key.  Returns null when the
         *  policy says "skip auto-discovered" and the key isn't declared. */
        private GoalSpec goalFor(String key) {
            GoalSpec g = goalByKey.get(key);
            if (g != null) return g;
            // Lazy inference for auto-discovered keys via policy.
            GoalSpec inferred = autoPolicy.inferFor(key);
            if (inferred != null) goalByKey.put(key, inferred);
            return inferred;   // may be null if policy.include == false
        }

        /**
         * Try to admit a new candidate to the front.  Discovers metric keys
         * lazily — when a never-seen-before key arrives, the existing front
         * is widened with a sentinel coordinate (NaN→treated as "missing,
         * candidate is incomparable on this axis", so existing members are
         * not retroactively dominated by the new axis).
         */
        public void update(LineResult cand, Map<String, Double> metrics) {
            if (metrics == null || metrics.isEmpty()) return;

            // Extend the canonical key list with any new keys.
            for (String k : metrics.keySet())
                if (!currentKeys.contains(k)) currentKeys.add(k);

            double[] cv = vector(metrics);

            // Pad existing front vectors with NaN for any newly seen keys.
            for (int i = 0; i < frontVecs.size(); i++) {
                double[] old = frontVecs.get(i);
                if (old.length < currentKeys.size()) {
                    double[] grown = new double[currentKeys.size()];
                    System.arraycopy(old, 0, grown, 0, old.length);
                    for (int j = old.length; j < grown.length; j++) grown[j] = Double.NaN;
                    frontVecs.set(i, grown);
                }
            }

            // 1. Skip candidate if dominated by any front member.
            for (double[] fv : frontVecs)
                if (dominates(fv, cv)) return;

            // 2. Remove front members dominated by candidate (in reverse for safe removal).
            for (int i = frontVecs.size() - 1; i >= 0; i--) {
                if (dominates(cv, frontVecs.get(i))) {
                    frontVecs.remove(i);
                    front.remove(i);
                }
            }

            // 3. Admit.
            front.add(cand);
            frontVecs.add(cv);
        }

        private double[] vector(Map<String, Double> metrics) {
            double[] v = new double[currentKeys.size()];
            for (int i = 0; i < v.length; i++) {
                Double d = metrics.get(currentKeys.get(i));
                v[i] = d == null ? Double.NaN : d;
            }
            return v;
        }

        /** {@code a} dominates {@code b} per {@link Dominance#dominates}.
         *  Cached goal array is rebuilt lazily when {@link #currentKeys}
         *  grows (new axis discovered).  TARGET axes, NaN handling, and
         *  policy-excluded auto-keys (null goal) all come from the unified
         *  algorithm — this method is now a one-line delegation. */
        private GoalSpec[] cachedGoalArray;
        private int cachedKeyCount = -1;

        private boolean dominates(double[] a, double[] b) {
            // Rebuild the goal-array cache if the key set grew (or first call).
            if (cachedKeyCount != currentKeys.size()) {
                cachedGoalArray = new GoalSpec[currentKeys.size()];
                for (int i = 0; i < cachedGoalArray.length; i++) {
                    cachedGoalArray[i] = goalFor(currentKeys.get(i));
                }
                cachedKeyCount = currentKeys.size();
            }
            return Dominance.dominates(a, b, cachedGoalArray);
        }

        /** Read-only view of the goals map (declared + lazily-inferred auto). */
        public Map<String, GoalSpec> goals() { return java.util.Collections.unmodifiableMap(goalByKey); }
        /** Just the explicitly-declared keys (for telemetry / rendering). */
        public java.util.Set<String> declaredKeys() { return java.util.Collections.unmodifiableSet(declaredKeys); }
        /** The auto-discovery policy this instance was built with. */
        public DiscoveryPolicy autoPolicy() { return autoPolicy; }
        /** Canonical key order for vector lookup. */
        public List<String> keysInOrder() { return java.util.Collections.unmodifiableList(currentKeys); }
        /** Vectors aligned with {@link #snapshot()} and {@link #keysInOrder()}. */
        public List<double[]> frontVectors() { return java.util.Collections.unmodifiableList(frontVecs); }

        public List<LineResult> snapshot() { return new ArrayList<>(front); }
        public int size() { return front.size(); }
    }

    // ─── Aggregator state ───────────────────────────────────────────────
    private final Map<String, KeyStats> stats = new LinkedHashMap<>();
    private final OnlinePareto pareto;
    private long updates;

    /** Top-K lines by score (heap-based; bounded memory). */
    private final java.util.PriorityQueue<LineResult> topByScore;
    private final int topK;

    /** Most-explicit constructor: declared goals + auto-discovery policy. */
    public OnlineMetricAggregator(int topK, List<GoalSpec> goals, DiscoveryPolicy autoPolicy) {
        this.topK = Math.max(1, topK);
        this.topByScore = new java.util.PriorityQueue<>(this.topK + 1,
                java.util.Comparator.comparingDouble((LineResult r) -> r.score));
        this.pareto = new OnlinePareto(goals, autoPolicy);
    }

    /** Goals only — auto-keys per {@link DiscoveryPolicy#DEFAULT}. */
    public OnlineMetricAggregator(int topK, List<GoalSpec> goals) {
        this(topK, goals, DiscoveryPolicy.DEFAULT);
    }

    /** Legacy: binary minimise/maximise via key-set; auto-keys per DEFAULT policy. */
    public OnlineMetricAggregator(int topK, java.util.Set<String> maximizeKeys) {
        this.topK = Math.max(1, topK);
        this.topByScore = new java.util.PriorityQueue<>(this.topK + 1,
                java.util.Comparator.comparingDouble((LineResult r) -> r.score));
        this.pareto = new OnlinePareto(maximizeKeys);
    }

    /** Feed one streamed result into the aggregator.  Idempotent on re-call
     *  with the same {@code lineNo} only if you intend to overwrite — otherwise
     *  metrics will be double-counted.  Caller controls deduplication. */
    public void add(LineResult r) {
        if (r == null) return;
        updates++;
        // 1. extract numeric metrics for this line (uses tryParseNumeric, so
        //    unit-suffixed values like "0.5s", "1.2MiB" are accepted).
        Map<String, Double> metrics = new LinkedHashMap<>();
        for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
            java.util.OptionalDouble od = AnalyzerCore.tryParseNumeric(e.getValue());
            if (od.isEmpty()) continue;
            double v = od.getAsDouble();
            if (!Double.isFinite(v)) continue;
            metrics.put(e.getKey(), v);
        }
        // 2. update per-key Welford + champions
        String snippet = snippet(r);
        for (Map.Entry<String, Double> e : metrics.entrySet()) {
            stats.computeIfAbsent(e.getKey(), KeyStats::new)
                  .add(e.getValue(), r.lineNo, snippet);
        }
        // 3. update online Pareto
        pareto.update(r, metrics);
        // 4. update top-K by score
        if (topByScore.size() < topK) topByScore.offer(r);
        else if (topByScore.peek().score < r.score) {
            topByScore.poll();
            topByScore.offer(r);
        }
    }

    private static String snippet(LineResult r) {
        String s = r.originalLine == null ? "" : r.originalLine;
        return s.length() > 80 ? s.substring(0, 77) + "..." : s;
    }

    /** Immutable view of the aggregator at one point in time.  Carries the
     *  declared goals AND the auto-discovery policy + the actually-discovered
     *  keys (Welford KeyStats covers them) AND a per-key {@link
     *  MetricStreamAnalyzer.MetricAnalysis} built from each key's bounded
     *  reservoir at snapshot time.  {@link #effectiveGoals()} merges declared
     *  with policy-inferred for auto-keys, so balanced-optimum selection sees
     *  the full agnostic axis set.
     *
     *  {@link #deepAnalysis} is the streaming-time equivalent of what
     *  {@code MetricStreamAnalyzer.analyzeAll} produces in batch mode —
     *  populated lazily by the aggregator when {@link #snapshot()} is
     *  called; lets external tools see Brent argmin/argmax on the
     *  interpolated stream, Nelder-Mead exp-fit, Simpson AUC, RK4 smoothing,
     *  Newton critical points — all without materialising the full corpus. */
    public record Snapshot(long updates,
                           Map<String, KeyStats> perKeyStats,
                           List<LineResult> paretoFront,
                           List<LineResult> topByScore,
                           List<GoalSpec> goals,
                           DiscoveryPolicy autoPolicy,
                           java.util.Set<String> declaredKeys,
                           Map<String, MetricStreamAnalyzer.MetricAnalysis> deepAnalysis,
                           CacheStats cacheStats) {

        /** Backwards-compatible 4-arg constructor (no goals, no deep analysis). */
        public Snapshot(long updates,
                        Map<String, KeyStats> perKeyStats,
                        List<LineResult> paretoFront,
                        List<LineResult> topByScore) {
            this(updates, perKeyStats, paretoFront, topByScore,
                    List.of(), DiscoveryPolicy.DEFAULT, java.util.Set.of(), Map.of(),
                    CacheStats.EMPTY);
        }

        /** Backwards-compatible 5-arg constructor (legacy goals only). */
        public Snapshot(long updates,
                        Map<String, KeyStats> perKeyStats,
                        List<LineResult> paretoFront,
                        List<LineResult> topByScore,
                        List<GoalSpec> goals) {
            this(updates, perKeyStats, paretoFront, topByScore,
                    goals, DiscoveryPolicy.DEFAULT,
                    goals.stream().map(GoalSpec::key).collect(java.util.stream.Collectors.toSet()),
                    Map.of(), CacheStats.EMPTY);
        }

        /** Backwards-compatible 7-arg constructor (no deep analysis). */
        public Snapshot(long updates,
                        Map<String, KeyStats> perKeyStats,
                        List<LineResult> paretoFront,
                        List<LineResult> topByScore,
                        List<GoalSpec> goals,
                        DiscoveryPolicy autoPolicy,
                        java.util.Set<String> declaredKeys) {
            this(updates, perKeyStats, paretoFront, topByScore,
                    goals, autoPolicy, declaredKeys, Map.of(), CacheStats.EMPTY);
        }

        /** Backwards-compatible 8-arg constructor (no cache stats — pre-Tier-1.5). */
        public Snapshot(long updates,
                        Map<String, KeyStats> perKeyStats,
                        List<LineResult> paretoFront,
                        List<LineResult> topByScore,
                        List<GoalSpec> goals,
                        DiscoveryPolicy autoPolicy,
                        java.util.Set<String> declaredKeys,
                        Map<String, MetricStreamAnalyzer.MetricAnalysis> deepAnalysis) {
            this(updates, perKeyStats, paretoFront, topByScore,
                    goals, autoPolicy, declaredKeys, deepAnalysis, CacheStats.EMPTY);
        }

        /** Return a copy with the supplied cache stats — used by the
         *  streaming entry points to attach the executor's cache stats
         *  post-aggregation without coupling the aggregator to the executor. */
        public Snapshot withCacheStats(CacheStats cs) {
            return new Snapshot(updates, perKeyStats, paretoFront, topByScore,
                    goals, autoPolicy, declaredKeys, deepAnalysis,
                    cs == null ? CacheStats.EMPTY : cs);
        }

        /** Merge declared goals with auto-policy-inferred goals for every
         *  observed-but-not-declared numeric key.  This is the FULL agnostic
         *  axis set used by {@link BalancedOptimumSelector}. */
        public List<GoalSpec> effectiveGoals() {
            java.util.Map<String, GoalSpec> byKey = new java.util.LinkedHashMap<>();
            for (GoalSpec g : goals) byKey.put(g.key(), g);
            if (autoPolicy != null && autoPolicy.include()) {
                for (String autoKey : perKeyStats.keySet()) {
                    if (!byKey.containsKey(autoKey)) {
                        GoalSpec inferred = autoPolicy.inferFor(autoKey);
                        if (inferred != null) byKey.put(autoKey, inferred);
                    }
                }
            }
            return new java.util.ArrayList<>(byKey.values());
        }

        public String render() {
            StringBuilder sb = new StringBuilder();
            sb.append("\n════════════════════════════════════════════════════════════════════\n");
            sb.append(" Streaming aggregator snapshot (").append(updates).append(" candidates)\n");
            sb.append("════════════════════════════════════════════════════════════════════\n");
            sb.append("\nPer-metric streaming stats (Welford + champions):\n");
            if (perKeyStats.isEmpty()) sb.append("  (no numeric metrics discovered)\n");
            else for (KeyStats k : perKeyStats.values()) {
                sb.append(String.format(Locale.ROOT,
                        "  %-20s n=%-7d  μ=%-12.4g σ=%-12.4g  min=%-12.4g @line#%-5d  max=%-12.4g @line#%-5d%n",
                        k.key, k.n, k.mean, k.stdev(),
                        k.min, k.argminLineNo, k.max, k.argmaxLineNo));
            }
            // Effective goals = declared + policy-inferred-for-each-auto-key.
            // We render BOTH sets so the user can see what was explicitly
            // requested vs. what the agnostic policy added for them.
            List<GoalSpec> eff = effectiveGoals();
            if (!goals.isEmpty()) {
                sb.append("\nDeclared goals (explicit, from caller):\n");
                for (GoalSpec g : goals) {
                    sb.append(String.format(Locale.ROOT,
                            "  %-20s mode=%-8s  target=%-12.4g  weight=%.2f%n",
                            g.key(), g.mode(), g.targetValue(), g.weight()));
                }
            }
            if (eff.size() > goals.size()) {
                sb.append("\nAuto-discovered axes (added by DiscoveryPolicy ")
                  .append(autoPolicy == null ? "DEFAULT" : autoPolicy)
                  .append("):\n");
                java.util.Set<String> declared = (declaredKeys == null) ? java.util.Set.of() : declaredKeys;
                for (GoalSpec g : eff) {
                    if (declared.contains(g.key())) continue;
                    sb.append(String.format(Locale.ROOT,
                            "  %-20s mode=%-8s (inferred)  weight=%.2f%n",
                            g.key(), g.mode(), g.weight()));
                }
            }
            sb.append("\nOnline Pareto front (").append(paretoFront.size()).append(" non-dominated):\n");
            int shown = 0;
            for (LineResult r : paretoFront) {
                if (shown++ >= 10) {
                    sb.append("  … (").append(paretoFront.size() - 10).append(" more)\n");
                    break;
                }
                String s = r.originalLine == null ? "" : r.originalLine;
                if (s.length() > 80) s = s.substring(0, 77) + "...";
                sb.append(String.format(Locale.ROOT, "  • line #%-7d score=%6.2f  %s%n",
                        r.lineNo, r.score, s));
            }
            sb.append("\nTop ").append(topByScore.size()).append(" by score:\n");
            for (LineResult r : topByScore) {
                String s = r.originalLine == null ? "" : r.originalLine;
                if (s.length() > 80) s = s.substring(0, 77) + "...";
                sb.append(String.format(Locale.ROOT, "  • line #%-7d score=%6.2f  %s%n",
                        r.lineNo, r.score, s));
            }
            // Deep per-key analysis (reservoir → full MetricStreamAnalyzer
            // toolkit).  Streaming-time equivalent of the batch-mode
            // "Auto-discovered N numeric metric stream(s)" section.  The
            // load-bearing outputs are exp-fit, Simpson AUC, and RK4
            // smoothing; Brent argmin/argmax + SA + Newton are decorative
            // on monotone streams (they reproduce the corpus min/max
            // already shown in Per-metric streaming stats).
            if (!deepAnalysis.isEmpty()) {
                sb.append("\nDeep per-metric analysis (").append(deepAnalysis.size())
                  .append(" stream(s), reservoir-sampled):\n");
                int deepShown = 0;
                for (MetricStreamAnalyzer.MetricAnalysis ma : deepAnalysis.values()) {
                    if (deepShown++ >= 8) {
                        sb.append("  … (").append(deepAnalysis.size() - 8).append(" more elided)\n");
                        break;
                    }
                    sb.append(String.format(Locale.ROOT,
                            "  '%s' n=%d  μ=%-10.4g σ=%-10.4g  ∫Simpson=%-10.4g  P5/P50/P95=%.3g/%.3g/%.3g%n",
                            ma.key(), ma.n(), ma.mean(), ma.stdev(),
                            ma.simpsonAuc(), ma.p5(), ma.p50(), ma.p95()));
                    sb.append(String.format(Locale.ROOT,
                            "    Nelder-Mead exp-fit  a=%-9.3g b=%-9.3g c=%-9.3g  loss=%-9.3g%n",
                            ma.expFitParams()[0], ma.expFitParams()[1], ma.expFitParams()[2],
                            ma.expFitLoss()));
                    sb.append(String.format(Locale.ROOT,
                            "    RK4 τ=%-7.3f   Brent[argmin@%.2f=%-9.4g  argmax@%.2f=%-9.4g]%s%n",
                            ma.rk4Tau(),
                            ma.brentArgmin(), ma.brentMin(),
                            ma.brentArgmax(), ma.brentMax(),
                            (ma.criticalPoints().length > 0)
                                ? "   Newton crits: " + ma.criticalPoints().length
                                : ""));
                }
            }

            // Cache stats — only rendered when the analyzer was driven by a
            // memoising executor (LineExecutor.Caching).  Gated on total>0 so
            // the legacy non-caching path keeps byte-for-byte identical output.
            if (cacheStats != null && cacheStats.total() > 0) {
                sb.append(String.format(Locale.ROOT,
                        "%nLineExecutor cache: hits=%d  misses=%d  hit-rate=%.2f%%  size=%d / capacity=%d%n",
                        cacheStats.hits(), cacheStats.misses(),
                        100.0 * cacheStats.hitRate(),
                        cacheStats.size(), cacheStats.capacity()));
            }

            // Balanced-optimum picks via scalarization.  Uses EFFECTIVE goals
            // (declared + auto-discovered with inferred mode) so the agnostic
            // axes participate even when the caller declared none.
            if (!eff.isEmpty() && !paretoFront.isEmpty()) {
                sb.append("\nBalanced optima (scalarized over the Pareto front, "
                       + eff.size() + " axes — " + goals.size() + " declared + "
                       + (eff.size() - goals.size()) + " auto):\n");
                for (BalancedOptimumSelector.Selection sel :
                        BalancedOptimumSelector.all(paretoFront, perKeyStats, eff)) {
                    sb.append(sel.render());
                }
            }
            return sb.toString();
        }

        /**
         * Machine-readable counterpart of {@link #render()}.  Returns a
         * Jackson {@link com.fasterxml.jackson.databind.JsonNode} with the
         * same six sections — for piping the report into external tools,
         * CI dashboards, or a Combinatorics-engine feedback loop.
         *
         * Schema:
         * <pre>
         * {
         *   "updates": &lt;long&gt;,
         *   "perKeyStats": { "&lt;key&gt;": { "n", "mean", "stdev", "min",
         *                                  "max", "argminLineNo", "argmaxLineNo" } },
         *   "declaredGoals":   [ { "key","mode","targetValue","weight" } ],
         *   "autoDiscoveredAxes": [ { "key","mode","weight","inferred":true } ],
         *   "autoPolicy":      { "include","forcedMode","weight" },
         *   "paretoFront":     [ { "lineNo","score","decision","lineType","snippet" } ],
         *   "topByScore":      [ { "lineNo","score","decision","lineType","snippet" } ],
         *   "balancedOptima":  [ { "strategy","lineNo","score","contribution":{...} } ]
         * }
         * </pre>
         */
        /**
         * Tier-3.5 — extract a {@link BundleSeed} closed-loop feedback
         * artifact from this snapshot.  Pareto-front members + per-metric
         * champions + balanced-optimum picks are all collected; observed
         * per-key ranges are carried so Core can scale the narrowing window
         * on the next iteration.
         *
         * <p>Convenience wrapper around
         * {@link BundleSeed#fromSnapshot(Snapshot, String, java.util.Map)}.
         * Pass an NSGA-II crowding-distance map (lineNo → distance) when
         * available so winners carry it; pass {@code null} or an empty map
         * for the legacy Pareto path (winners' {@code crowdingDistance} stays
         * {@link Double#NaN}).</p>
         */
        public BundleSeed toBundleSeed(String sourceRunId,
                                        java.util.Map<Integer, Double> crowdingByLineNo) {
            return BundleSeed.fromSnapshot(this, sourceRunId, crowdingByLineNo);
        }

        /** No-crowding convenience overload.  Equivalent to
         *  {@code toBundleSeed(sourceRunId, java.util.Map.of())}. */
        public BundleSeed toBundleSeed(String sourceRunId) {
            return BundleSeed.fromSnapshot(this, sourceRunId);
        }

        public com.fasterxml.jackson.databind.JsonNode toJson() {
            var mapper = com.yurii.analyzer.core.AnalyzerCore.mapper();
            com.fasterxml.jackson.databind.node.ObjectNode root = mapper.createObjectNode();
            root.put("updates", updates);

            // perKeyStats
            com.fasterxml.jackson.databind.node.ObjectNode statsNode = root.putObject("perKeyStats");
            for (KeyStats k : perKeyStats.values()) {
                com.fasterxml.jackson.databind.node.ObjectNode kn = statsNode.putObject(k.key);
                kn.put("n", k.n);
                kn.put("mean", k.mean);
                kn.put("stdev", k.stdev());
                kn.put("min", k.min);
                kn.put("max", k.max);
                kn.put("argminLineNo", k.argminLineNo);
                kn.put("argmaxLineNo", k.argmaxLineNo);
            }

            // declaredGoals
            com.fasterxml.jackson.databind.node.ArrayNode declNode = root.putArray("declaredGoals");
            for (GoalSpec g : goals) {
                com.fasterxml.jackson.databind.node.ObjectNode gn = declNode.addObject();
                gn.put("key", g.key());
                gn.put("mode", g.mode().name());
                gn.put("targetValue", g.targetValue());
                gn.put("weight", g.weight());
            }

            // autoDiscoveredAxes (effective − declared)
            List<GoalSpec> eff = effectiveGoals();
            java.util.Set<String> declSet = (declaredKeys == null) ? java.util.Set.of() : declaredKeys;
            com.fasterxml.jackson.databind.node.ArrayNode autoNode = root.putArray("autoDiscoveredAxes");
            for (GoalSpec g : eff) {
                if (declSet.contains(g.key())) continue;
                com.fasterxml.jackson.databind.node.ObjectNode gn = autoNode.addObject();
                gn.put("key", g.key());
                gn.put("mode", g.mode().name());
                gn.put("weight", g.weight());
                gn.put("inferred", true);
            }

            // autoPolicy
            if (autoPolicy != null) {
                com.fasterxml.jackson.databind.node.ObjectNode pn = root.putObject("autoPolicy");
                pn.put("include", autoPolicy.include());
                pn.put("forcedMode", autoPolicy.forcedMode() == null ? null : autoPolicy.forcedMode().name());
                pn.put("weight", autoPolicy.weight());
            }

            // paretoFront
            com.fasterxml.jackson.databind.node.ArrayNode frontNode = root.putArray("paretoFront");
            for (LineResult r : paretoFront) appendLineMention(frontNode, r);
            // topByScore
            com.fasterxml.jackson.databind.node.ArrayNode topNode = root.putArray("topByScore");
            for (LineResult r : topByScore) appendLineMention(topNode, r);

            // deepAnalysis — streaming-time MetricStreamAnalyzer results
            // per auto-discovered key, derived from each key's bounded
            // reservoir sample.  Load-bearing outputs documented in render().
            if (!deepAnalysis.isEmpty()) {
                com.fasterxml.jackson.databind.node.ObjectNode deepNode = root.putObject("deepAnalysis");
                for (MetricStreamAnalyzer.MetricAnalysis ma : deepAnalysis.values()) {
                    com.fasterxml.jackson.databind.node.ObjectNode mn = deepNode.putObject(ma.key());
                    mn.put("n", ma.n());
                    mn.put("mean", ma.mean());
                    mn.put("stdev", ma.stdev());
                    mn.put("p5", ma.p5());
                    mn.put("p50", ma.p50());
                    mn.put("p95", ma.p95());
                    mn.put("simpsonAuc", ma.simpsonAuc());
                    mn.put("trapezoidalSum", ma.trapezoidalSum());
                    mn.put("brentArgmin", ma.brentArgmin());
                    mn.put("brentMin", ma.brentMin());
                    mn.put("brentArgmax", ma.brentArgmax());
                    mn.put("brentMax", ma.brentMax());
                    mn.put("rk4Tau", ma.rk4Tau());
                    com.fasterxml.jackson.databind.node.ObjectNode efn = mn.putObject("expFit");
                    efn.put("a", ma.expFitParams()[0]);
                    efn.put("b", ma.expFitParams()[1]);
                    efn.put("c", ma.expFitParams()[2]);
                    efn.put("loss", ma.expFitLoss());
                    com.fasterxml.jackson.databind.node.ObjectNode san = mn.putObject("simulatedAnnealing");
                    san.put("argmin", ma.saArgmin());
                    san.put("min", ma.saMin());
                    com.fasterxml.jackson.databind.node.ArrayNode cpn = mn.putArray("criticalPoints");
                    for (double cp : ma.criticalPoints()) cpn.add(cp);
                }
            }

            // cacheStats — emitted only when a memoising executor recorded
            // any traffic; the EMPTY default suppresses the key so the
            // legacy non-caching snapshot JSON stays byte-for-byte identical.
            if (cacheStats != null && cacheStats.total() > 0) {
                com.fasterxml.jackson.databind.node.ObjectNode csn = root.putObject("cacheStats");
                csn.put("hits", cacheStats.hits());
                csn.put("misses", cacheStats.misses());
                csn.put("hitRate", cacheStats.hitRate());
                csn.put("size", cacheStats.size());
                csn.put("capacity", cacheStats.capacity());
            }

            // balancedOptima
            if (!eff.isEmpty() && !paretoFront.isEmpty()) {
                com.fasterxml.jackson.databind.node.ArrayNode boNode = root.putArray("balancedOptima");
                for (BalancedOptimumSelector.Selection sel :
                        BalancedOptimumSelector.all(paretoFront, perKeyStats, eff)) {
                    com.fasterxml.jackson.databind.node.ObjectNode sn = boNode.addObject();
                    sn.put("strategy", sel.strategy());
                    sn.put("lineNo", sel.chosen() == null ? -1 : sel.chosen().lineNo);
                    sn.put("score", sel.score());
                    com.fasterxml.jackson.databind.node.ObjectNode cn = sn.putObject("contribution");
                    for (var e : sel.perAxisContribution().entrySet()) cn.put(e.getKey(), e.getValue());
                }
            }
            return root;
        }

        private static void appendLineMention(
                com.fasterxml.jackson.databind.node.ArrayNode arr, LineResult r) {
            if (r == null) return;
            com.fasterxml.jackson.databind.node.ObjectNode n = arr.addObject();
            n.put("lineNo",    r.lineNo);
            n.put("score",     r.score);
            n.put("decision",  r.decision);
            n.put("lineType",  r.features.lineType);
            String snippet = r.originalLine == null ? "" : r.originalLine;
            if (snippet.length() > 200) snippet = snippet.substring(0, 197) + "...";
            n.put("snippet",   snippet);
        }
    }

    /**
     * Merge another aggregator's state into this one — the reduce step for
     * sharded parallel streaming.  Per-key Welford stats are combined via
     * Chan's parallel algorithm; min/max/champions take the winner;
     * reservoirs are concatenated and uniformly subsampled back to
     * capacity; Pareto fronts are unioned by re-inserting the other's
     * front members through this front's update logic (which re-applies
     * dominance, so the result is the proper merged front); top-K is
     * unioned and trimmed.
     *
     * Not thread-safe — the caller must serialise merges (typical pattern:
     * after all workers are joined, the main thread merges each local
     * aggregator into the global one sequentially).
     */
    public void merge(OnlineMetricAggregator other) {
        if (other == null) return;
        this.updates += other.updates;
        for (Map.Entry<String, KeyStats> e : other.stats.entrySet()) {
            KeyStats local = this.stats.computeIfAbsent(e.getKey(),
                    k -> new KeyStats(k, (other.stats.get(k).reservoir != null) ? RESERVOIR_CAP : 0));
            local.merge(e.getValue());
        }
        // Pareto merge: re-insert each of other's front members.  We
        // recover their metric vector by extracting numeric values from
        // r.features.kvPairs the same way add() did.
        for (LineResult r : other.pareto.front) {
            Map<String, Double> metrics = new LinkedHashMap<>();
            for (Map.Entry<String, String> e : r.features.kvPairs.entrySet()) {
                java.util.OptionalDouble od = AnalyzerCore.tryParseNumeric(e.getValue());
                if (od.isPresent() && Double.isFinite(od.getAsDouble())) {
                    metrics.put(e.getKey(), od.getAsDouble());
                }
            }
            this.pareto.update(r, metrics);
        }
        // Top-K merge.
        for (LineResult r : other.topByScore) {
            if (this.topByScore.size() < this.topK) this.topByScore.offer(r);
            else if (this.topByScore.peek().score < r.score) {
                this.topByScore.poll();
                this.topByScore.offer(r);
            }
        }
    }

    public Snapshot snapshot() {
        // top-K is a min-heap; pull and reverse for descending order
        List<LineResult> top = new ArrayList<>(topByScore);
        top.sort((a, b) -> Double.compare(b.score, a.score));
        // Declared goals only (not the lazily-added auto ones) — the
        // Snapshot recomputes effectiveGoals from declared+policy on demand.
        List<GoalSpec> declaredGoals = new ArrayList<>();
        java.util.Set<String> declared = pareto.declaredKeys();
        for (var e : pareto.goals().entrySet()) {
            if (declared.contains(e.getKey())) declaredGoals.add(e.getValue());
        }
        // Deep per-key analysis from each reservoir — bounded compute,
        // bounded memory, runs once at snapshot time.  Keys with fewer
        // than 5 reservoir samples are skipped (MetricStreamAnalyzer needs
        // ≥5 samples to fit Nelder-Mead exp / interpolate / RK4 / Newton).
        Map<String, MetricStreamAnalyzer.MetricAnalysis> deep = new LinkedHashMap<>();
        for (KeyStats ks : stats.values()) {
            java.util.List<double[]> samples = ks.reservoirSnapshot();
            if (samples.size() < 5) continue;
            try {
                deep.put(ks.key, MetricStreamAnalyzer.analyzeOnePublic(ks.key, samples));
            } catch (Exception ignored) {
                // One pathological metric shouldn't kill the whole snapshot.
            }
        }
        return new Snapshot(updates,
                Collections.unmodifiableMap(new LinkedHashMap<>(stats)),
                pareto.snapshot(), top,
                Collections.unmodifiableList(declaredGoals),
                pareto.autoPolicy(),
                Collections.unmodifiableSet(new java.util.LinkedHashSet<>(declared)),
                Collections.unmodifiableMap(deep),
                CacheStats.EMPTY);
    }

    public long updates() { return updates; }
    public int paretoSize() { return pareto.size(); }
    public Map<String, KeyStats> perKey() { return Collections.unmodifiableMap(stats); }
}
