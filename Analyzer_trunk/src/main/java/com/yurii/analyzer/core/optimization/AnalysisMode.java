package com.yurii.analyzer.core.optimization;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * STEP 38 — first-class split between the two ways the Analyzer may be driven,
 * so a <em>formal</em> Pareto study can never have its objectives changed
 * implicitly by auto-discovery, while an <em>exploratory</em> study keeps the
 * agnostic "observe every metric" behaviour (with the inferred axes clearly
 * labelled).
 *
 * <ul>
 *   <li>{@link #FORMAL} — explicit goals REQUIRED, NO auto-added dominance axes
 *       ({@link DiscoveryPolicy#DECLARED_ONLY}), directions are fixed exactly as
 *       declared, and a corpus count is REQUIRED (you must say how many
 *       candidates the front was computed over — a formal result without its
 *       denominator is not interpretable).</li>
 *   <li>{@link #EXPLORATORY} — auto-discovery allowed
 *       ({@link DiscoveryPolicy#DEFAULT} or a caller policy), inferred axes are
 *       surfaced and labelled, no corpus-count requirement.</li>
 * </ul>
 *
 * In BOTH modes, an explicit goal whose declared direction disagrees with what
 * lexical inference would have chosen is reported by {@link #directionConflicts}
 * — the explicit direction always wins (it is never silently overridden), but
 * the disagreement is surfaced rather than mixed in quietly (action #4).
 */
public enum AnalysisMode {
    FORMAL,
    EXPLORATORY;

    /** Parse a free-form mode token. {@code "formal"} → FORMAL; {@code
     *  "exploratory"}/{@code "explore"}/{@code "auto"} → EXPLORATORY; empty /
     *  null / unknown → EXPLORATORY (the backwards-compatible agnostic default). */
    public static AnalysisMode fromText(String s) {
        if (s == null) return EXPLORATORY;
        return switch (s.trim().toLowerCase(Locale.ROOT)) {
            case "formal", "strict"            -> FORMAL;
            case "exploratory", "explore",
                 "auto", ""                    -> EXPLORATORY;
            default -> throw new IllegalArgumentException(
                    "unknown analysis mode '" + s + "' (expected 'formal' or 'exploratory')");
        };
    }

    /** The auto-discovery policy this mode implies. FORMAL forbids auto axes;
     *  EXPLORATORY uses the supplied policy (or {@link DiscoveryPolicy#DEFAULT}
     *  when none is given). */
    public DiscoveryPolicy discoveryPolicy(DiscoveryPolicy exploratoryPolicy) {
        if (this == FORMAL) return DiscoveryPolicy.DECLARED_ONLY;
        return exploratoryPolicy == null ? DiscoveryPolicy.DEFAULT : exploratoryPolicy;
    }

    /** Validate the caller's inputs against this mode's contract, throwing
     *  {@link IllegalArgumentException} on a violation (fail closed — a formal
     *  study must not silently degrade into an exploratory one).
     *
     *  @param goals       the explicitly-declared goals (may be empty)
     *  @param corpusCount the number of candidates the analysis ran over, or
     *                     {@code null} if unknown */
    public void validate(List<GoalSpec> goals, Integer corpusCount) {
        if (this == FORMAL) {
            if (goals == null || goals.isEmpty())
                throw new IllegalArgumentException(
                        "formal mode requires explicit goals (none were declared) — "
                        + "auto-discovery is disabled in formal mode, so there would be no objectives");
            if (corpusCount == null || corpusCount <= 0)
                throw new IllegalArgumentException(
                        "formal mode requires a positive corpus count (got " + corpusCount + ") — "
                        + "a formal Pareto front is not interpretable without its denominator");
        }
    }

    /** Report any explicit goal whose declared direction DISAGREES with the
     *  lexical inference for its key (so explicit vs inferred are never silently
     *  mixed). TARGET goals are skipped (they have no min/max direction). Returns
     *  one human-readable line per conflicting key; empty when all agree. */
    public static List<String> directionConflicts(List<GoalSpec> goals) {
        List<String> out = new ArrayList<>();
        if (goals == null) return out;
        for (GoalSpec g : goals) {
            if (g.mode() == GoalSpec.Mode.TARGET) continue;
            GoalSpec.Mode inferred = AutoAnalysisPlanner.inferModeEnum(g.key());
            if (inferred != g.mode()) {
                out.add(String.format(Locale.ROOT,
                        "%s: explicit=%s but lexical inference suggests %s — keeping explicit (declared) direction",
                        g.key(), g.mode(), inferred));
            }
        }
        return out;
    }

    /** Lower-case label for logs / the run manifest. */
    public String label() {
        return name().toLowerCase(Locale.ROOT);
    }
}
