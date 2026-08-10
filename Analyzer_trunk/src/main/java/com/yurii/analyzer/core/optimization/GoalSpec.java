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

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Per-axis goal specification for multi-objective selection.  Mirrors what
 * {@link com.yurii.analyzer.core.AnalyzerCore.OptimizationGoal} carries on the
 * batch path, but is the public type used by the streaming API
 * ({@code analyzeStream}, {@code OnlineMetricAggregator}, balanced-optimum
 * selectors).
 *
 * Three modes are supported:
 *
 *   • {@link Mode#MINIMIZE} — lower value is better (cost, latency, error_rate, …)
 *   • {@link Mode#MAXIMIZE} — higher value is better (throughput, accuracy, …)
 *   • {@link Mode#TARGET}   — closer to {@code targetValue} is better (latency
 *                             near 50 ms, mem near 1 GiB, …).  Pareto dominance
 *                             on this axis uses {@code |value − target|}.
 *
 * The {@code weight} field is consumed only by the scalarization-based
 * selectors ({@link BalancedOptimumSelector}); Pareto extraction itself is
 * weight-agnostic.
 */
public record GoalSpec(String key, Mode mode, double targetValue, double weight) {

    public enum Mode { MINIMIZE, MAXIMIZE, TARGET }

    public GoalSpec {
        if (key == null || key.isBlank()) throw new IllegalArgumentException("key must be non-blank");
        if (mode == null) throw new IllegalArgumentException("mode must be non-null");
        if (!Double.isFinite(weight) || weight < 0) throw new IllegalArgumentException("weight must be ≥ 0");
    }

    public static GoalSpec min(String k)              { return new GoalSpec(k, Mode.MINIMIZE, 0.0, 1.0); }
    public static GoalSpec min(String k, double w)    { return new GoalSpec(k, Mode.MINIMIZE, 0.0, w); }
    public static GoalSpec max(String k)              { return new GoalSpec(k, Mode.MAXIMIZE, 0.0, 1.0); }
    public static GoalSpec max(String k, double w)    { return new GoalSpec(k, Mode.MAXIMIZE, 0.0, w); }
    public static GoalSpec target(String k, double t) { return new GoalSpec(k, Mode.TARGET, t, 1.0); }
    public static GoalSpec target(String k, double t, double w) { return new GoalSpec(k, Mode.TARGET, t, w); }

    /** Unit-aware target factory: parses strings like {@code "50ms"} → 0.05s,
     *  {@code "1.2GiB"} → 1.288e9, {@code "5%"} → 0.05.  Mirrors the same
     *  canonicalisation the analyzer applies to incoming K=V values, so the
     *  target lands on the same scale the candidates do. */
    public static GoalSpec target(String k, String targetWithUnit, double w) {
        java.util.OptionalDouble od = com.yurii.analyzer.core.AnalyzerCore.tryParseNumeric(targetWithUnit);
        if (od.isEmpty())
            throw new IllegalArgumentException("could not parse target '" + targetWithUnit + "' on key '" + k + "'");
        return new GoalSpec(k, Mode.TARGET, od.getAsDouble(), w);
    }

    /** Convert a candidate's raw metric value to a "deviation" — a quantity
     *  that is 0 at the ideal point and grows monotonically as the candidate
     *  gets worse on this axis.  Used for both Pareto dominance and scalarization. */
    public double deviation(double v) {
        return switch (mode) {
            case MINIMIZE -> v;
            case MAXIMIZE -> -v;
            case TARGET   -> Math.abs(v - targetValue);
        };
    }

    /** Compatibility shim: collapse a binary {@code maximizeKeys} set into
     *  a list of GoalSpec (default weight 1.0).  Used by legacy callers
     *  that haven't migrated to the GoalSpec API yet. */
    public static List<GoalSpec> fromMaximizeKeys(Set<String> maximizeKeys, Iterable<String> allKeys) {
        List<GoalSpec> out = new ArrayList<>();
        for (String k : allKeys) {
            out.add((maximizeKeys != null && maximizeKeys.contains(k))
                    ? max(k) : min(k));
        }
        return out;
    }
}
