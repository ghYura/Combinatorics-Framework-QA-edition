package com.yurii.analyzer.core.optimization;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Plan-2 — the Java 21 virtual-thread <b>runtime control plane</b> that EXECUTES
 * Plan-1's {@code repeatPolicy}.  Plan-1 defines the repeat parameters, the
 * {@code results_v2} 5-column sample identity
 * {@code (run_id, candidate_id, attempt, repeat_idx, env_id)} and the Analyzer
 * aggregation.  <b>This class is the dispatch / fan-out / result-collection
 * layer that runs Plan-1's policy</b> — it does not redefine any of Plan-1's
 * contracts.
 *
 * <h2>What it is (and is not)</h2>
 * <ul>
 *   <li><b>Is</b> the runtime that fans out {@code candidate × repeat ×
 *       executor} work units, enforces the policy assignment
 *       (disperse / local / nested), bounds in-flight work, serializes
 *       latency-sensitive candidates per host, applies a budget deadline with
 *       cooperative cancellation, and collects results keyed by
 *       {@code (candidate_id, repeat_idx, env_id)}.</li>
 *   <li><b>Is not</b> a rewrite of the Python experiment-design / spec-authoring
 *       front-end (fwgen / ZEN / testme5 stay Python — Plan-2 §P2.0).  It also
 *       does not crunch metrics: aggregation (Welford / NSGA-II) stays on
 *       platform threads in the Analyzer (Plan-2 §P2.4 — control plane is I/O
 *       coordination only).</li>
 * </ul>
 *
 * <h2>Design decision: stable virtual-thread API, not preview StructuredTaskScope</h2>
 * Plan-2 §P2.1 sketches {@code StructuredTaskScope}; QA design-decision #9
 * requires an explicit Java-21 preview call.  {@code StructuredTaskScope} is a
 * <em>preview</em> API in 21 (needs {@code --enable-preview}); virtual threads
 * themselves are <em>final</em>.  The rest of the Bundle Data Plane already uses
 * the <em>stable</em> idiom — {@code Executors.newVirtualThreadPerTaskExecutor()}
 * (Core {@code SheetWorker}, Reader {@code ComboGenerationPipeline}) and
 * {@code Thread.ofVirtual()} (Executor {@code MainWatch}) — and no module enables
 * {@code --enable-preview}.  So this control plane is built on the <b>stable</b>
 * API: one virtual thread per work unit + {@link Semaphore} backpressure +
 * {@link Future} join with a deadline + {@link ExecutorService#shutdownNow()}
 * cancellation.  This delivers the same "fan out N → join → aggregate with
 * deadline/cancel" structure the spec wanted, with zero build-flag churn and
 * full consistency with the existing stack.
 *
 * <h2>Composition with the existing seam (evolution, not greenfield)</h2>
 * Each work unit is run through a {@link UnitExecutor} — the Plan-2 seam.  The
 * stock implementation {@link #remoteWorkerExecutor} wraps the existing
 * {@link LineExecutor.RemoteWorker} (file-drop + {@code ResultPoller} poll loop),
 * one per env, so a unit's blocking DB/IPC poll is exactly today's RemoteWorker
 * behaviour — only now fanned out concurrently and policy-assigned.  Because
 * {@code RemoteWorker.execute} already honours {@link Thread#interrupt()}
 * (returns {@code remote_status=interrupted}), cancellation propagates for free.
 *
 * <h2>Thread-safety</h2>
 * One {@code BundleControlPlane} drives one {@link #run}.  {@link #cancel()} is
 * safe to call from any thread.  The supplied {@link UnitExecutor} must be
 * thread-safe (the RemoteWorker / JDBC pollers are — fresh connection per call).
 */
public final class BundleControlPlane {

    /** Plan-1 distribution strategy (Plan-1 §1, §5; Plan-2 §P2.3 #3). */
    public enum RepeatPolicy {
        /** Each candidate's K repeats pinned to ONE env (within-env σ²). */
        LOCAL,
        /** Each candidate's K repeats scattered, balanced, across the pool
         *  (between-env σ²; Plan-1 §4.5 randomized block). */
        DISPERSE,
        /** K repeats on EACH of the E envs (full decomposition; E×K per cand). */
        NESTED;

        public static RepeatPolicy from(String s) {
            if (s == null) return LOCAL;
            return switch (s.trim().toLowerCase(Locale.ROOT)) {
                case "disperse" -> DISPERSE;
                case "nested"   -> NESTED;
                case "local", "" -> LOCAL;
                default -> throw new IllegalArgumentException("unknown repeatPolicy: " + s);
            };
        }
    }

    /**
     * Metric type — drives per-host concurrency (Plan-1 §4.4, Plan-2 §P2.3 #6).
     * A <b>noisy</b> continuous metric (latency/throughput) must be measured
     * one-candidate-per-host: parallel candidates on one host contend for
     * CPU/cache/memory bandwidth and corrupt each other's numbers. A
     * <b>deterministic</b> verdict (FW_VAR) is env-agnostic, so it fans out at
     * full width. The dispatcher selects the per-host limit from this.
     */
    public enum MetricSensitivity { DETERMINISTIC, NOISY }

    /** Noisy ⇒ serialize one candidate per host; deterministic ⇒ fan out. */
    public static boolean serializePerHostFor(MetricSensitivity m) {
        return m == MetricSensitivity.NOISY;
    }

    public static MetricSensitivity metricSensitivityFrom(String s) {
        if (s == null) return MetricSensitivity.DETERMINISTIC;
        return switch (s.trim().toLowerCase(Locale.ROOT)) {
            case "noisy", "perf", "latency", "throughput", "continuous" -> MetricSensitivity.NOISY;
            case "deterministic", "verdict", "fw_var", "" -> MetricSensitivity.DETERMINISTIC;
            default -> throw new IllegalArgumentException("unknown metricSensitivity: " + s);
        };
    }

    /** A candidate to be (repeatedly) executed. {@code candidateId} is the
     *  Plan-1 {@code combi_id_final}; {@code lineNo}/{@code raw} feed the
     *  executor seam exactly as {@link LineExecutor#execute}. */
    public record Candidate(int lineNo, String candidateId, String raw) {}

    /** One unit of work after policy expansion: a single
     *  {@code (candidate_id, repeat_idx, env_id)} sample — the Plan-1 identity. */
    public record WorkUnit(int lineNo, String candidateId, String raw,
                           int repeatIdx, String envId) {}

    /** Terminal state of a unit. */
    public enum Outcome { COMPLETED, TIMEOUT, CANCELLED, ERROR }

    /** Result of one unit: the raw metric text (RemoteWorker K=V form) + state. */
    public record UnitResult(WorkUnit unit, String output, Outcome outcome, String note) {}

    /**
     * The Plan-2 execution seam.  Runs a single work unit on its assigned env
     * and returns the metric text (typically {@code remote_id=… k=v …}).  Must
     * be thread-safe and should be interrupt-aware (so the budget/cancel gate
     * can stop it).
     */
    @FunctionalInterface
    public interface UnitExecutor {
        String run(WorkUnit unit) throws Exception;
        default void close() throws Exception {}
    }

    /** Control-plane configuration.  {@link #fromProperties} reads the
     *  {@code fw.controlplane.*} namespace (falling back to Plan-1's
     *  {@code fw.executor.*}). */
    public record Config(RepeatPolicy policy, int repeatK, List<String> envs,
                         int maxInFlight, boolean serializePerHost, long budgetMillis) {
        public Config {
            if (policy == null) policy = RepeatPolicy.LOCAL;
            if (repeatK < 1) repeatK = 1;
            envs = (envs == null || envs.isEmpty()) ? List.of("") : List.copyOf(envs);
            if (maxInFlight < 1) maxInFlight = 1;
            if (budgetMillis < 0) budgetMillis = 0;
        }

        /** Build a config whose per-host serialization is derived from the
         *  metric type (noisy ⇒ serialize, deterministic ⇒ fan out). */
        public static Config forMetric(RepeatPolicy policy, int repeatK, List<String> envs,
                int maxInFlight, MetricSensitivity sensitivity, long budgetMillis) {
            return new Config(policy, repeatK, envs, maxInFlight,
                    serializePerHostFor(sensitivity), budgetMillis);
        }

        public static Config fromProperties(Map<String, String> p) {
            String pol = first(p, "fw.controlplane.policy", "fw.executor.repeatPolicy", "local");
            int k = parseInt(first(p, "fw.controlplane.repeatK", "fw.executor.repeatEachCandidate", "1"), 1);
            int maxInFlight = parseInt(p.getOrDefault("fw.controlplane.maxInFlight", "64"), 64);
            // Explicit serializePerHost wins; otherwise derive from the metric type.
            String serialProp = p.get("fw.controlplane.serializePerHost");
            boolean serial = (serialProp != null && !serialProp.isBlank())
                    ? Boolean.parseBoolean(serialProp)
                    : serializePerHostFor(metricSensitivityFrom(p.get("fw.controlplane.metricSensitivity")));
            long budget = parseLong(p.getOrDefault("fw.controlplane.budgetMillis", "0"), 0L);
            List<String> envs = parseEnvs(p.getOrDefault("fw.controlplane.envs", ""));
            return new Config(RepeatPolicy.from(pol), k, envs, maxInFlight, serial, budget);
        }

        private static String first(Map<String, String> p, String a, String b, String dflt) {
            String v = p.get(a);
            if (v == null) v = p.get(b);
            return (v == null || v.isBlank()) ? dflt : v;
        }
        private static List<String> parseEnvs(String csv) {
            if (csv == null || csv.isBlank()) return List.of("");
            List<String> out = new ArrayList<>();
            for (String s : csv.split(",")) { String t = s.trim(); if (!t.isEmpty()) out.add(t); }
            return out.isEmpty() ? List.of("") : out;
        }
    }

    /** Roll-up of one run. {@code maxInFlightObserved} proves the backpressure
     *  cap held; {@code maxPerEnvObserved} proves per-host serialization. */
    public record RunStats(int planned, int completed, int timedOut, int cancelled,
                           int errored, int maxInFlightObserved,
                           Map<String, Integer> maxPerEnvObserved, long elapsedMillis) {}

    /** Full run output: per-unit results (collected keyed by the Plan-1
     *  identity) + stats. */
    public record RunResult(List<UnitResult> results, RunStats stats) {}

    private final Config config;
    private volatile boolean cancelled = false;

    public BundleControlPlane(Config config) {
        this.config = (config == null) ? Config.fromProperties(Map.of()) : config;
    }

    public Config config() { return config; }

    /** Cooperative cancel — stop dispatch and interrupt in-flight units (the
     *  budget/timeout gate, or an external stop).  Sticky: a cancelled plane
     *  will not start new work. */
    public void cancel() { this.cancelled = true; }

    // ---------------------------------------------------------------- planning

    /**
     * Expand candidates into work units per the configured policy — the
     * assignment strategy (Plan-2 §P2.3 #3).  Every emitted unit has a unique
     * {@code (candidateId, repeatIdx, envId)} triple, so it maps 1:1 onto a
     * distinct {@code results_v2} row under Plan-1's 5-column key.
     */
    public List<WorkUnit> planUnits(List<Candidate> candidates) {
        List<String> envs = config.envs();
        final int E = envs.size();
        final int K = config.repeatK();
        List<WorkUnit> units = new ArrayList<>();
        switch (config.policy()) {
            case LOCAL -> {
                // All K repeats of a candidate pinned to one env; candidates
                // round-robin across the pool so load is balanced.
                for (int ci = 0; ci < candidates.size(); ci++) {
                    Candidate c = candidates.get(ci);
                    String env = envs.get(ci % E);
                    for (int r = 0; r < K; r++)
                        units.add(new WorkUnit(c.lineNo(), c.candidateId(), c.raw(), r, env));
                }
            }
            case DISPERSE -> {
                // Each candidate's K repeats scattered across envs, balanced:
                // candidate ci's repeat r -> envs[(ci + r) % E].  The per-candidate
                // rotation makes every candidate see the same env multiset shape
                // (when K % E == 0, each env exactly K/E times) while spreading the
                // remainder evenly across the pool — the randomized-block balance
                // Plan-1 §4.5 requires for an unbiased between-env comparison.
                for (int ci = 0; ci < candidates.size(); ci++) {
                    Candidate c = candidates.get(ci);
                    for (int r = 0; r < K; r++) {
                        String env = envs.get((ci + r) % E);
                        units.add(new WorkUnit(c.lineNo(), c.candidateId(), c.raw(), r, env));
                    }
                }
            }
            case NESTED -> {
                // K repeats on EACH env → E*K units per candidate; env_id keeps
                // same-repeat_idx samples on different envs distinct.
                for (Candidate c : candidates) {
                    for (int e = 0; e < E; e++) {
                        String env = envs.get(e);
                        for (int r = 0; r < K; r++)
                            units.add(new WorkUnit(c.lineNo(), c.candidateId(), c.raw(), r, env));
                    }
                }
            }
        }
        return units;
    }

    // ----------------------------------------------------------------- running

    /**
     * Fan out all work units on virtual threads, enforcing the in-flight cap,
     * per-host serialization, and the budget deadline; collect every unit's
     * result.  Single-shot per instance.
     */
    public RunResult run(List<Candidate> candidates, UnitExecutor exec) {
        final List<WorkUnit> units = planUnits(candidates);
        final int planned = units.size();

        final Semaphore inFlight = new Semaphore(config.maxInFlight());
        final Map<String, Semaphore> perEnvGate = new ConcurrentHashMap<>();
        if (config.serializePerHost())
            for (String e : config.envs()) perEnvGate.put(e, new Semaphore(1));

        final AtomicInteger curInFlight = new AtomicInteger();
        final AtomicInteger maxInFlight = new AtomicInteger();
        final Map<String, AtomicInteger> curPerEnv = new ConcurrentHashMap<>();
        final Map<String, AtomicInteger> maxPerEnv = new ConcurrentHashMap<>();
        for (String e : config.envs()) { curPerEnv.put(e, new AtomicInteger()); maxPerEnv.put(e, new AtomicInteger()); }

        final long t0 = System.nanoTime();
        final long deadlineNanos = config.budgetMillis() > 0
                ? t0 + config.budgetMillis() * 1_000_000L : Long.MAX_VALUE;

        final List<UnitResult> results = new ArrayList<>(planned);
        try (ExecutorService vexec = Executors.newVirtualThreadPerTaskExecutor()) {
            final List<Future<UnitResult>> futures = new ArrayList<>(planned);
            for (WorkUnit u : units) {
                futures.add(vexec.submit(() -> runOneUnit(
                        u, exec, inFlight, perEnvGate,
                        curInFlight, maxInFlight, curPerEnv, maxPerEnv)));
            }

            boolean finishedInTime = awaitAllOrDeadline(futures, deadlineNanos);
            if (!finishedInTime || cancelled) {
                // Budget exceeded or external cancel: interrupt every in-flight
                // vthread.  RemoteWorker / interrupt-aware executors unwind and
                // return; semaphore acquires throw InterruptedException → CANCELLED.
                vexec.shutdownNow();
            }

            for (int i = 0; i < futures.size(); i++) {
                Future<UnitResult> f = futures.get(i);
                WorkUnit u = units.get(i);
                try {
                    results.add(f.get(5, TimeUnit.SECONDS));
                } catch (Exception e) {
                    // A task that never produced a result (cancelled before
                    // returning) is synthesized so the corpus stays complete.
                    results.add(new UnitResult(u, "",
                            cancelled ? Outcome.CANCELLED : Outcome.TIMEOUT,
                            "no result: " + e.getClass().getSimpleName()));
                }
            }
        }

        int completed = 0, timeout = 0, cancel = 0, err = 0;
        for (UnitResult r : results) {
            switch (r.outcome()) {
                case COMPLETED -> completed++;
                case TIMEOUT   -> timeout++;
                case CANCELLED -> cancel++;
                case ERROR     -> err++;
            }
        }
        Map<String, Integer> maxPerEnvOut = new LinkedHashMap<>();
        for (String e : config.envs()) maxPerEnvOut.put(e, maxPerEnv.get(e).get());

        long elapsed = (System.nanoTime() - t0) / 1_000_000L;
        RunStats stats = new RunStats(planned, completed, timeout, cancel, err,
                maxInFlight.get(), maxPerEnvOut, elapsed);
        return new RunResult(results, stats);
    }

    private UnitResult runOneUnit(WorkUnit u, UnitExecutor exec, Semaphore inFlight,
            Map<String, Semaphore> perEnvGate, AtomicInteger curInFlight, AtomicInteger maxInFlight,
            Map<String, AtomicInteger> curPerEnv, Map<String, AtomicInteger> maxPerEnv) {
        if (cancelled) return new UnitResult(u, "", Outcome.CANCELLED, "cancelled before start");

        // Global admission first (the backpressure cap), then the per-host
        // gate.  Both are always acquired in this order, so no deadlock.
        try {
            inFlight.acquire();
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            return new UnitResult(u, "", Outcome.CANCELLED, "interrupted before admission");
        }
        Semaphore envGate = perEnvGate.get(u.envId());
        boolean envHeld = false;
        try {
            if (envGate != null) { envGate.acquire(); envHeld = true; }

            int nowGlobal = curInFlight.incrementAndGet();
            bumpMax(maxInFlight, nowGlobal);
            AtomicInteger ce = curPerEnv.get(u.envId());
            AtomicInteger me = maxPerEnv.get(u.envId());
            if (ce != null) bumpMax(me, ce.incrementAndGet());
            try {
                String out = exec.run(u);
                return new UnitResult(u, out == null ? "" : out, classify(out), null);
            } finally {
                if (ce != null) ce.decrementAndGet();
                curInFlight.decrementAndGet();
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            return new UnitResult(u, "", Outcome.CANCELLED, "interrupted");
        } catch (Exception e) {
            return new UnitResult(u, "", Outcome.ERROR, e.toString());
        } finally {
            if (envHeld) envGate.release();
            inFlight.release();
        }
    }

    /** Poll futures on the (platform) orchestrating thread until all are done,
     *  the deadline passes, or a cancel arrives.  5 ms sleeps — no CPU spin
     *  (Plan-2 §P2.4: the control plane must not burn cores). */
    private boolean awaitAllOrDeadline(List<Future<UnitResult>> futures, long deadlineNanos) {
        while (true) {
            if (cancelled) return false;
            boolean allDone = true;
            for (Future<?> f : futures) if (!f.isDone()) { allDone = false; break; }
            if (allDone) return true;
            if (System.nanoTime() >= deadlineNanos) return false;
            try { Thread.sleep(5); }
            catch (InterruptedException ie) { Thread.currentThread().interrupt(); return false; }
        }
    }

    private static Outcome classify(String out) {
        if (out == null) return Outcome.ERROR;
        if (out.contains("remote_status=timeout"))      return Outcome.TIMEOUT;
        if (out.contains("remote_status=interrupted"))  return Outcome.CANCELLED;
        return Outcome.COMPLETED;
    }

    private static void bumpMax(AtomicInteger max, int observed) {
        max.updateAndGet(prev -> Math.max(prev, observed));
    }

    // ----------------------------------------------- dispatch → aggregation

    /**
     * Build a repeat-aware corpus from a finished run — one line per COMPLETED
     * unit, in the form {@code candidate_id=<id> repeat_idx=<r> env_id=<e>
     * <metric>=<v> …} that Plan-1's {@link RepeatAggregator} consumes. The
     * RemoteWorker envelope tokens ({@code remote_id}/{@code remote_status}) are
     * dropped; everything else in the unit's output is treated as a metric
     * token. Non-completed units (timeout/cancel/error) contribute no row — a
     * missing sample, exactly as the aggregator's coverage accounting expects.
     */
    public static List<String> toAggregatorCorpus(RunResult run) {
        List<String> lines = new ArrayList<>();
        for (UnitResult r : run.results()) {
            if (r.outcome() != Outcome.COMPLETED) continue;
            WorkUnit u = r.unit();
            StringBuilder sb = new StringBuilder()
                    .append("candidate_id=").append(u.candidateId())
                    .append(" repeat_idx=").append(u.repeatIdx())
                    .append(" env_id=").append(u.envId());
            String out = r.output();
            if (out != null) {
                for (String tok : out.trim().split("\\s+")) {
                    int eq = tok.indexOf('=');
                    if (eq <= 0) continue;
                    String key = tok.substring(0, eq);
                    if (key.equals("remote_id") || key.equals("remote_status")) continue;
                    sb.append(' ').append(tok);
                }
            }
            lines.add(sb.toString());
        }
        return lines;
    }

    /**
     * Collect this run's COMPLETED units into a repeat-aware corpus and aggregate
     * per candidate (median + order-statistic CI, tie-ready) via the Plan-1
     * {@link RepeatAggregator}. This is the dispatch → aggregation join: a
     * fanned-out K-repeat campaign becomes a per-candidate aggregate.
     *
     * <p>Requires one {@code env_id} per candidate (the {@code local} /
     * within-env model — {@code RepeatAggregator} enforces it). Cross-env
     * decomposition for {@code disperse}/{@code nested} (between-env σ²) is the
     * Plan-1 §5 #12 aggregator extension and is not done here.</p>
     */
    public static Map<String, RepeatAggregator.CandidateAggregate> aggregate(
            RunResult run, List<GoalSpec> goals) {
        return RepeatAggregator.aggregate(toAggregatorCorpus(run), goals);
    }

    // ------------------------------------------ cross-env decomposition (§12)

    /**
     * Per-candidate, per-metric cross-environment decomposition (Plan-1 §5 #12)
     * for {@code nested} (and partially {@code disperse}) runs, where one
     * candidate is sampled across multiple {@code env_id}s — the case the
     * single-env {@link #aggregate} (and {@link RepeatAggregator}) deliberately
     * rejects.
     *
     * <p><b>Method (chosen, documented for review):</b> nonparametric, to stay
     * consistent with the order-statistic CIs adopted in QA decision #5 (no
     * Gaussian σ²/ANOVA assumption on a possibly-skewed noisy metric):
     * <ul>
     *   <li>per-env median {@code m_e} over that env's K repeats;</li>
     *   <li><b>point estimate</b> = {@code grandMedian} = median of the {@code m_e}
     *       (median-of-per-env-medians — the candidate's representative value);</li>
     *   <li><b>between-env spread</b> = range of the {@code m_e}
     *       ({@code max−min}) — environment-to-environment variability (σ²_env proxy);</li>
     *   <li><b>within-env spread</b> = median over envs of each env's sample range
     *       ({@code max−min} of its K repeats) — temporal noise on one host
     *       (σ²_temporal proxy);</li>
     *   <li>{@link NestedMetricStat#envSensitive()} = between &gt; within (the
     *       candidate's metric depends on which environment ran it).</li>
     * </ul>
     * A parametric variance-components (nested ANOVA) alternative is possible but
     * would clash with the order-statistic stance; revisit if Yuri prefers it.
     */
    public record NestedMetricStat(double grandMedian, double betweenEnvRange,
                                   double withinEnvMedianRange, int envCount,
                                   List<Double> perEnvMedians) {
        /** True when between-env variability exceeds the typical within-env
         *  variability — i.e. the metric is environment-sensitive. */
        public boolean envSensitive() { return betweenEnvRange > withinEnvMedianRange; }
    }

    /** Per-candidate nested aggregate across {@code envCount} environments. */
    public record NestedAggregate(String candidateId, int envCount, int totalSamples,
                                  Map<String, NestedMetricStat> objective) {}

    /**
     * Decompose a {@code nested}/{@code disperse} run per candidate across its
     * environments (see {@link NestedMetricStat} for the method). Only COMPLETED
     * units contribute; metric values are read from the unit output for each
     * declared goal key. Single-env runs collapse to one env (between-env = 0).
     */
    public static Map<String, NestedAggregate> aggregateNested(RunResult run, List<GoalSpec> goals) {
        // candidateId -> envId -> metricKey -> raw values
        Map<String, Map<String, Map<String, List<Double>>>> byCand = new LinkedHashMap<>();
        Map<String, Integer> totals = new LinkedHashMap<>();
        for (UnitResult r : run.results()) {
            if (r.outcome() != Outcome.COMPLETED) continue;
            WorkUnit u = r.unit();
            Map<String, Double> metrics = parseMetrics(r.output(), goals);
            Map<String, List<Double>> metricMap = byCand
                    .computeIfAbsent(u.candidateId(), k -> new LinkedHashMap<>())
                    .computeIfAbsent(u.envId(), k -> new LinkedHashMap<>());
            for (Map.Entry<String, Double> e : metrics.entrySet())
                metricMap.computeIfAbsent(e.getKey(), k -> new ArrayList<>()).add(e.getValue());
            totals.merge(u.candidateId(), 1, Integer::sum);
        }

        Map<String, NestedAggregate> out = new LinkedHashMap<>();
        for (Map.Entry<String, Map<String, Map<String, List<Double>>>> ce : byCand.entrySet()) {
            Map<String, Map<String, List<Double>>> envMap = ce.getValue();
            Map<String, NestedMetricStat> objective = new LinkedHashMap<>();
            for (GoalSpec g : goals) {
                String key = g.key();
                List<Double> perEnvMedians = new ArrayList<>();
                List<Double> perEnvRanges = new ArrayList<>();
                for (Map<String, List<Double>> metricMap : envMap.values()) {
                    List<Double> vals = metricMap.get(key);
                    if (vals == null || vals.isEmpty()) continue;
                    double[] sorted = vals.stream().mapToDouble(Double::doubleValue).sorted().toArray();
                    perEnvMedians.add(RepeatAggregator.median(sorted));
                    perEnvRanges.add(sorted[sorted.length - 1] - sorted[0]);
                }
                if (perEnvMedians.isEmpty()) continue;
                double[] pem = perEnvMedians.stream().mapToDouble(Double::doubleValue).sorted().toArray();
                double[] per = perEnvRanges.stream().mapToDouble(Double::doubleValue).sorted().toArray();
                objective.put(key, new NestedMetricStat(
                        RepeatAggregator.median(pem),
                        pem[pem.length - 1] - pem[0],
                        RepeatAggregator.median(per),
                        perEnvMedians.size(),
                        List.copyOf(perEnvMedians)));
            }
            out.put(ce.getKey(), new NestedAggregate(
                    ce.getKey(), envMap.size(), totals.getOrDefault(ce.getKey(), 0), objective));
        }
        return out;
    }

    private static Map<String, Double> parseMetrics(String output, List<GoalSpec> goals) {
        Map<String, Double> m = new LinkedHashMap<>();
        if (output == null) return m;
        java.util.Set<String> keys = new java.util.HashSet<>();
        for (GoalSpec g : goals) keys.add(g.key());
        for (String tok : output.trim().split("\\s+")) {
            int eq = tok.indexOf('=');
            if (eq <= 0) continue;
            String k = tok.substring(0, eq);
            if (!keys.contains(k)) continue;
            try { m.put(k, Double.parseDouble(tok.substring(eq + 1))); }
            catch (NumberFormatException ignored) { /* non-numeric metric token */ }
        }
        return m;
    }

    // ------------------------------------------------------------- executors

    /**
     * Stock {@link UnitExecutor}: dispatch each unit to a per-env
     * {@link LineExecutor.RemoteWorker} (file-drop + poll), reusing the existing
     * Tier-4.2 machinery.  {@code envSrcDirs} maps {@code env_id → srcDir} (each
     * Executor instance's watch directory).  The {@code poller} is the result
     * lookup ({@link LineExecutor.RemoteWorker.JdbcPoller} against
     * {@code results_v2}, or a stub).
     *
     * <p>NOTE: today's {@code RemoteWorker} polls by {@code candidate_id} only.
     * Repeat/env-aware polling — keying on {@code (candidate_id, repeat_idx,
     * env_id)} so each of the K samples is read back distinctly — is the
     * JdbcPoller evolution that a real multi-instance Executor pool requires;
     * see the ADR.  This factory is exact for the verdict (FW_VAR) path and for
     * K=1 parity.</p>
     */
    public static UnitExecutor remoteWorkerExecutor(
            Map<String, java.nio.file.Path> envSrcDirs,
            LineExecutor.RemoteWorker.ResultPoller poller,
            long pollIntervalMs, double timeoutSeconds) {
        Map<String, LineExecutor.RemoteWorker> perEnv = new ConcurrentHashMap<>();
        for (Map.Entry<String, java.nio.file.Path> e : envSrcDirs.entrySet()) {
            perEnv.put(e.getKey(), new LineExecutor.RemoteWorker.Builder()
                    .srcDir(e.getValue())
                    .poller(poller)
                    .pollIntervalMs(pollIntervalMs)
                    .timeoutSeconds(timeoutSeconds)
                    .build());
        }
        return unit -> {
            LineExecutor.RemoteWorker rw = perEnv.get(unit.envId());
            if (rw == null) throw new IllegalStateException("no RemoteWorker for env '" + unit.envId() + "'");
            return rw.execute(unit.lineNo(), unit.raw());
        };
    }

    /**
     * Repeat/env-aware results poller — the Plan-2 evolution of
     * {@link LineExecutor.RemoteWorker.JdbcPoller}.  Where the legacy poller
     * keys on {@code candidate_id} only (one row per candidate), this keys on
     * the full Plan-1 sample identity {@code (candidate_id, repeat_idx, env_id)}
     * so each of the K (or E×K) samples is read back distinctly.  Column names
     * are configurable; identifiers are double-quoted exactly like the legacy
     * poller (the results DDL creates mixed-case {@code fw_optJ} quoted).
     *
     * <p>The {@code buildSelectSql} construction is pure and unit-tested; the
     * live {@code poll} (one connection per call, bounded by the control plane's
     * {@code maxInFlight}) is exercised only against a real results DB — that
     * run, plus connection pooling for hundreds–thousands of Executors, is the
     * infra-gated step (see the ADR).</p>
     */
    public static final class RepeatEnvJdbcPoller {
        private final String jdbcUrl;
        private final String selectSql;
        private final java.util.List<String> columns;

        public RepeatEnvJdbcPoller(String jdbcUrl, String tableName, String idColumn,
                String repeatIdxColumn, String envIdColumn, java.util.List<String> selectColumns) {
            if (jdbcUrl == null || jdbcUrl.isBlank())
                throw new IllegalArgumentException("jdbcUrl must be non-blank");
            if (selectColumns == null || selectColumns.isEmpty())
                throw new IllegalArgumentException("selectColumns must be non-empty");
            this.jdbcUrl = jdbcUrl;
            this.columns = java.util.List.copyOf(selectColumns);
            this.selectSql = buildSelectSql(tableName, idColumn, repeatIdxColumn, envIdColumn, this.columns);
        }

        /** {@code SELECT <cols> FROM <table> WHERE <id>=? AND <repeat>=? AND <env>=? LIMIT 1}. */
        public static String buildSelectSql(String tableName, String idColumn,
                String repeatIdxColumn, String envIdColumn, java.util.List<String> selectColumns) {
            if (tableName == null || tableName.isBlank())
                throw new IllegalArgumentException("tableName must be non-blank");
            String cols = selectColumns.stream().map(BundleControlPlane::quoteIdent)
                    .collect(java.util.stream.Collectors.joining(", "));
            String table = tableName.contains("\"") ? tableName : "\"" + tableName + "\"";
            return "SELECT " + cols + " FROM " + table
                    + " WHERE " + quoteIdent(idColumn) + " = ? AND "
                    + quoteIdent(repeatIdxColumn) + " = ? AND "
                    + quoteIdent(envIdColumn) + " = ? LIMIT 1";
        }

        /** @return column→value row, or {@code null} if the sample isn't written yet. */
        public java.util.Map<String, String> poll(WorkUnit u) throws java.sql.SQLException {
            try (java.sql.Connection c = java.sql.DriverManager.getConnection(jdbcUrl);
                 java.sql.PreparedStatement ps = c.prepareStatement(selectSql)) {
                // results_v2.candidate_id is text in the canonical executor schema.
                // Bind as text even when the id looks numeric; otherwise PostgreSQL
                // sees text = bigint and rejects real bundle result tables.
                ps.setString(1, u.candidateId());
                ps.setInt(2, u.repeatIdx());
                ps.setString(3, u.envId());
                try (java.sql.ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) return null;
                    java.util.Map<String, String> row = new LinkedHashMap<>();
                    for (String col : columns) {
                        Object v;
                        try { v = rs.getObject(col); }
                        catch (java.sql.SQLException unknownCol) { continue; }
                        row.put(col.toLowerCase(Locale.ROOT), v == null ? "" : v.toString());
                    }
                    return row;
                }
            }
        }
    }

    /**
     * {@link UnitExecutor} backed by a {@link RepeatEnvJdbcPoller}: poll the
     * sample's row until present or the per-unit timeout, returning the
     * RemoteWorker-style {@code remote_id=<id> k=v …} text.  Interrupt-aware (the
     * {@code Thread.sleep} unwinds on cancel), so the control plane's budget/
     * cancel gate propagates.
     */
    public static UnitExecutor jdbcUnitExecutor(RepeatEnvJdbcPoller poller,
            long pollIntervalMs, double timeoutSeconds) {
        long interval = Math.max(10L, pollIntervalMs);
        double timeout = timeoutSeconds <= 0 ? 30.0 : timeoutSeconds;
        return unit -> {
            long deadline = System.nanoTime() + (long) (timeout * 1e9);
            while (System.nanoTime() < deadline) {
                java.util.Map<String, String> row = poller.poll(unit);
                if (row != null && !row.isEmpty()) {
                    StringBuilder sb = new StringBuilder("remote_id=").append(unit.candidateId());
                    for (Map.Entry<String, String> e : row.entrySet())
                        sb.append(' ').append(e.getKey()).append('=')
                          .append(e.getValue() == null ? "" : e.getValue());
                    return sb.toString();
                }
                Thread.sleep(interval);
            }
            return "remote_id=" + unit.candidateId() + " remote_status=timeout";
        };
    }

    private static String quoteIdent(String id) {
        if (id == null || id.isBlank()) throw new IllegalArgumentException("identifier must be non-blank");
        return id.contains("\"") ? id : "\"" + id + "\"";
    }

    // ------------------------------------------- plan JSON (Python ↔ Java seam)

    /**
     * A run plan as emitted by the Python front-end (§P2.3 #1) — the policy /
     * scale config plus the candidate list.  JSON shape:
     * <pre>{"policy","repeatK","envs":[…],"maxInFlight",
     *      ("serializePerHost"|"metricSensitivity"),"budgetMillis",
     *      "candidates":[{"lineNo","candidateId","raw"}]}</pre>
     * This is the seam that lets the Python planner keep owning experiment design
     * while the Java control plane owns dispatch (ADR-8): Python emits a Plan,
     * Java consumes it.
     */
    public record Plan(Config config, List<Candidate> candidates) {
        public static Plan fromJson(String json) throws Exception {
            com.fasterxml.jackson.databind.JsonNode root =
                    new com.fasterxml.jackson.databind.ObjectMapper().readTree(json);
            Map<String, String> p = new java.util.HashMap<>();
            if (root.hasNonNull("policy"))            p.put("fw.controlplane.policy", root.get("policy").asText());
            if (root.hasNonNull("repeatK"))           p.put("fw.controlplane.repeatK", String.valueOf(root.get("repeatK").asInt()));
            if (root.hasNonNull("maxInFlight"))       p.put("fw.controlplane.maxInFlight", String.valueOf(root.get("maxInFlight").asInt()));
            if (root.hasNonNull("metricSensitivity")) p.put("fw.controlplane.metricSensitivity", root.get("metricSensitivity").asText());
            if (root.hasNonNull("serializePerHost"))  p.put("fw.controlplane.serializePerHost", String.valueOf(root.get("serializePerHost").asBoolean()));
            if (root.hasNonNull("budgetMillis"))      p.put("fw.controlplane.budgetMillis", String.valueOf(root.get("budgetMillis").asLong()));
            if (root.has("envs") && root.get("envs").isArray()) {
                List<String> envs = new ArrayList<>();
                for (com.fasterxml.jackson.databind.JsonNode e : root.get("envs")) envs.add(e.asText());
                p.put("fw.controlplane.envs", String.join(",", envs));
            }
            Config cfg = Config.fromProperties(p);
            List<Candidate> cands = new ArrayList<>();
            if (root.has("candidates"))
                for (com.fasterxml.jackson.databind.JsonNode c : root.get("candidates"))
                    cands.add(new Candidate(c.path("lineNo").asInt(),
                            c.path("candidateId").asText(), c.path("raw").asText("")));
            return new Plan(cfg, cands);
        }
    }

    /**
     * Emit the expanded dispatch plan — the assignment of every
     * {@code (candidate, repeat_idx, env_id)} unit — as JSON.  This is what a
     * dry-run produces, so the Python front-end can preview
     * {@code candidates × K = executions} (the budget ×K, Plan-1 §5 #2) without a
     * live Executor pool.
     */
    public static String unitsToJson(Config cfg, List<WorkUnit> units) throws Exception {
        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        com.fasterxml.jackson.databind.node.ObjectNode root = mapper.createObjectNode();
        root.put("policy", cfg.policy().name().toLowerCase(Locale.ROOT));
        root.put("repeatK", cfg.repeatK());
        root.put("envs", String.join(",", cfg.envs()));
        root.put("serializePerHost", cfg.serializePerHost());
        root.put("plannedUnits", units.size());
        root.put("executions", units.size());
        com.fasterxml.jackson.databind.node.ArrayNode arr = root.putArray("units");
        for (WorkUnit u : units) {
            com.fasterxml.jackson.databind.node.ObjectNode n = arr.addObject();
            n.put("candidateId", u.candidateId());
            n.put("repeatIdx", u.repeatIdx());
            n.put("envId", u.envId());
        }
        return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(root);
    }

    /**
     * CLI entry: {@code BundleControlPlane <plan.json>} reads a Python-emitted
     * plan and prints the expanded dispatch plan (dry-run — no live Executors).
     * A real run needs a wired {@link #jdbcUnitExecutor} against a live results
     * DB + an Executor pool (infra-gated).
     */
    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: BundleControlPlane <plan.json>   (prints the expanded dispatch plan)");
            System.exit(2);
        }
        String json = java.nio.file.Files.readString(java.nio.file.Path.of(args[0]));
        Plan plan = Plan.fromJson(json);
        BundleControlPlane cp = new BundleControlPlane(plan.config());
        System.out.println(unitsToJson(plan.config(), cp.planUnits(plan.candidates())));
    }

    private static int parseInt(String s, int dflt) {
        try { return Integer.parseInt(s.trim()); } catch (Exception e) { return dflt; }
    }
    private static long parseLong(String s, long dflt) {
        try { return Long.parseLong(s.trim()); } catch (Exception e) { return dflt; }
    }
}
