package com.yurii.analyzer.core.optimization;

/**
 * Selector for which non-dominated-set algorithm the analyzer uses on
 * batch / post-stream Pareto-front extraction.  Both options are O(N²) on the
 * candidate count and produce identical rank-1 membership; what differs is
 * the auxiliary information the algorithm computes alongside the front.
 *
 * <ul>
 *   <li>{@link #PARETO} — the original {@link Dominance#paretoFront} path.
 *       Boolean "dominated" flag per candidate, allocation-light, drops the
 *       dominated tail.  Use this when callers only need the rank-1 set and
 *       don't care about diversification.</li>
 *   <li>{@link #NSGA_II} — the NSGA-II fast non-dominated sort
 *       ({@link NsgaII#fastNonDominatedSort}) with per-candidate crowding
 *       distance.  Same rank-1 set, plus a diversity-aware score that lets
 *       the reporter rank front members by "how distinct this objective
 *       vector is from its peers".  <strong>Default</strong> across the
 *       analyzer — additive-only feature, no behaviour change to rank-1
 *       membership.</li>
 * </ul>
 */
public enum FrontAlgorithm {
    PARETO,
    NSGA_II,
    /** Tier-5.1 — Deb &amp; Jain (2014) reference-point NSGA.  Same fast non-
     *  dominated sort as NSGA-II (rank-1 membership identical) but the
     *  per-front diversity metric is perpendicular distance to a structured
     *  set of Das-Dennis reference directions instead of crowding distance.
     *  Scales cleanly to many-objective scoring ({@code M} ≥ 4) where
     *  crowding loses discriminative power.  See {@link NsgaIII}. */
    NSGA_III,
    /** Tier-5.1 — Zitzler, Laumanns &amp; Thiele (2001) Strength Pareto
     *  Evolutionary Algorithm 2.  Same rank-1 set, but the per-candidate
     *  diversity metric is the {@code k}-th nearest-neighbour distance in
     *  deviation-space ({@code k = √N}) — used in SPEA2's environmental
     *  truncation to keep isolated members alive.  See {@link Spea2}. */
    SPEA2,
    /** Tier-5.1 — Zhang &amp; Li (2007) Multi-Objective EA based on
     *  Decomposition.  Generates a structured set of weight vectors
     *  (Das-Dennis, same as NSGA-III) and scores each candidate by its best
     *  Tchebycheff scalarization across all weight directions.  Surfaces
     *  {@code bestWeightIndex + bestTchebycheff} in the ranked path; the
     *  best Tchebycheff value goes into the polymorphic {@code crowdingDistance}
     *  slot.  See {@link MoeaD}. */
    MOEA_D;

    /** Project-wide default: NSGA-II.  Lives here (rather than as a literal
     *  in callers) so a single edit can flip the default for everything that
     *  honours the {@code AnalysisSettings.frontAlgorithm} contract. */
    public static final FrontAlgorithm DEFAULT = NSGA_II;
}
