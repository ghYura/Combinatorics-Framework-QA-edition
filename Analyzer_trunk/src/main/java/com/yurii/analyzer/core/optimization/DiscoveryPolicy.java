package com.yurii.analyzer.core.optimization;

/**
 * Policy that controls how auto-discovered metric keys (those that appear in
 * incoming rows but were NOT declared as {@link GoalSpec} by the caller) are
 * treated by the streaming optimisation pipeline.
 *
 * Why this exists: the project's design statement is "agnostic to incoming
 * parameters".  Without a policy, only explicitly declared keys participated
 * in selection — which contradicts the agnostic stance.  With this policy,
 * the analyzer observes EVERY numeric K=V it sees and folds each one into
 * the Pareto front and the balanced-optimum scalarization automatically,
 * with a sensible inferred mode (cost/latency → MIN, throughput/accuracy →
 * MAX, etc., via {@link AutoAnalysisPlanner#inferMode}).
 *
 * Three knobs:
 *
 *   • {@link #include} — false to revert to "declared keys only" semantics.
 *     Auto-keys are still observed (Welford stats + champions), but they
 *     don't participate in Pareto dominance or balanced-optimum selection.
 *
 *   • {@link #forcedMode} — null = lexical inference; otherwise force every
 *     auto-key to {@link GoalSpec.Mode#MINIMIZE} or {@link GoalSpec.Mode#MAXIMIZE}.
 *
 *   • {@link #weight} — relative weight for auto-keys in scalarization
 *     (Pareto dominance is weight-agnostic).  0.0 = "observe but don't
 *     influence balanced-optimum" — useful when the user has explicit
 *     declared goals and wants auto-keys visible only as descriptive stats.
 */
public record DiscoveryPolicy(boolean include,
                              GoalSpec.Mode forcedMode,
                              double weight) {

    public DiscoveryPolicy {
        if (!Double.isFinite(weight) || weight < 0)
            throw new IllegalArgumentException("weight must be ≥ 0 and finite");
    }

    /** Default: include all auto-keys, infer mode from name, weight 1.0.
     *  This is the truly agnostic policy and is the recommended default. */
    public static final DiscoveryPolicy DEFAULT = new DiscoveryPolicy(true, null, 1.0);

    /** Don't include auto-keys in Pareto/scalarization at all.  Use when
     *  the caller wants strict "declared-keys-only" semantics. */
    public static final DiscoveryPolicy DECLARED_ONLY = new DiscoveryPolicy(false, null, 0.0);

    /** Include with inferred mode, but contribute nothing to scalarization
     *  (weight 0).  Useful when auto-keys should appear in stats/Pareto
     *  but not influence the "balanced optimum" pick. */
    public static final DiscoveryPolicy OBSERVE_ONLY = new DiscoveryPolicy(true, null, 0.0);

    /** Build a {@link GoalSpec} for a never-before-seen key, or null if
     *  this policy says "skip".  Memoise the result on the caller side. */
    public GoalSpec inferFor(String key) {
        if (!include) return null;
        GoalSpec.Mode m = (forcedMode != null) ? forcedMode
                : AutoAnalysisPlanner.inferModeEnum(key);
        return new GoalSpec(key, m, 0.0, weight);
    }

    /** Parse from a free-form mode string.  Accepts: {@code "auto"} (default,
     *  lexical inference), {@code "min"}/{@code "minimize"}, {@code "max"}/
     *  {@code "maximize"}.  Empty / null / unknown → {@code "auto"}. */
    public static DiscoveryPolicy fromText(String includeStr, String modeStr, String weightStr) {
        boolean inc = (includeStr == null) ? true
                : !("false".equalsIgnoreCase(includeStr.trim()) || "0".equals(includeStr.trim()));
        GoalSpec.Mode forced = null;
        String m = (modeStr == null) ? "auto" : modeStr.trim().toLowerCase(java.util.Locale.ROOT);
        switch (m) {
            case "min", "minimize" -> forced = GoalSpec.Mode.MINIMIZE;
            case "max", "maximize" -> forced = GoalSpec.Mode.MAXIMIZE;
            default                -> forced = null;     // "auto" or empty → lexical inference
        }
        double w = 1.0;
        if (weightStr != null && !weightStr.isBlank()) {
            try { w = Double.parseDouble(weightStr.trim()); }
            catch (NumberFormatException ignored) { w = 1.0; }
        }
        return new DiscoveryPolicy(inc, forced, w);
    }
}
