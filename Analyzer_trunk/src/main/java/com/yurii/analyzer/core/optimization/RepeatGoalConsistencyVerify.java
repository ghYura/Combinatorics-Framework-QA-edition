package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Regression (Automation 2026-06-20T12:44Z): when explicit Analyzer goals are supplied, the K=1 raw
 * path and the K&gt;1 repeat-aggregated path must rank ONLY the declared objective set — neither
 * may auto-discover an extra numeric field (e.g. a configuration parameter) into the objectives,
 * and both must produce the same effective goals + Pareto front on deterministic data. Fails if
 * either path changes the declared objective set. Forked by {@code AllVerifiersRunner}.
 */
public final class RepeatGoalConsistencyVerify {
    private RepeatGoalConsistencyVerify() {}

    private static final Pattern ID = Pattern.compile("candidate_id=(\\S+)");
    private static int failures = 0;

    private static void check(String d, boolean ok) {
        System.out.println((ok ? "  ok   " : "  FAIL ") + d);
        if (!ok) failures++;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("── RepeatGoalConsistencyVerify (declared-goal-set parity: K=1 raw vs K>1 aggregated) ──");
        // Two declared goals (cost:min, err:min) plus an irrelevant numeric config field `knob`.
        // c4 is dominated on the declared goals but has an extreme `knob`, so if `knob` is wrongly
        // auto-discovered as an objective the front/objective-set changes — that is the bug guard.
        List<GoalSpec> goals = List.of(GoalSpec.min("cost"), GoalSpec.min("err"));
        String[][] cands = {
                {"c1", "cost=10 err=5 knob=1"},
                {"c2", "cost=5 err=10 knob=1"},
                {"c3", "cost=8 err=8 knob=1"},
                {"c4", "cost=20 err=20 knob=99"},
        };
        List<String> raw = new ArrayList<>();          // K=1: one line per candidate
        for (String[] c : cands) raw.add("candidate_id=" + c[0] + " " + c[1]);
        List<String> repeat = new ArrayList<>();       // K=3: three repeat_idx samples per candidate
        for (String[] c : cands)
            for (int r = 0; r < 3; r++)
                repeat.add("candidate_id=" + c[0] + " repeat_idx=" + r + " env_id=e " + c[1]);

        // K=1 raw + the driver's explicit-goals policy (DECLARED_ONLY): objective set is exactly
        // the declared goals; `knob` is NOT discovered; c4 stays off the front.
        Snapshot rawDeclared = analyze(raw, goals, DiscoveryPolicy.DECLARED_ONLY);
        check("raw + DECLARED_ONLY: effective goals are exactly {cost, err} (no knob)",
                keys(rawDeclared.effectiveGoals()).equals(Set.of("cost", "err")));
        Set<String> rawFront = frontIds(rawDeclared);
        check("raw + DECLARED_ONLY: front = {c1,c2,c3} (c4 dominated; knob ignored)",
                rawFront.equals(Set.of("c1", "c2", "c3")));

        // Non-vacuous: with discovery ON, `knob` IS auto-discovered into the objectives — so the
        // DECLARED_ONLY suppression above is meaningful, not a no-op corpus.
        Snapshot rawDiscover = analyze(raw, goals, DiscoveryPolicy.DEFAULT);
        check("non-vacuous: discovery WOULD add `knob` to the objectives",
                keys(rawDiscover.effectiveGoals()).contains("knob")
                        && !keys(rawDiscover.effectiveGoals()).equals(Set.of("cost", "err")));

        // K=3 repeat-aware: aggregate over the declared goals, render analyzer lines, analyze with
        // the same DECLARED_ONLY policy — must match the K=1 raw objective set AND front.
        var aggregates = RepeatAggregator.aggregate(repeat, goals);
        check("K=3 aggregates: 4 candidate aggregates from 12 raw samples", aggregates.size() == 4);
        List<String> aggLines = RepeatAggregator.toAnalyzerLines(aggregates, goals);
        Snapshot repeatDeclared = analyze(aggLines, goals, DiscoveryPolicy.DECLARED_ONLY);
        check("repeat + DECLARED_ONLY: effective goals are exactly {cost, err} (no knob)",
                keys(repeatDeclared.effectiveGoals()).equals(Set.of("cost", "err")));
        check("repeat + DECLARED_ONLY: Pareto front IDENTICAL to the K=1 raw front",
                frontIds(repeatDeclared).equals(rawFront));

        System.out.println(failures == 0 ? "RepeatGoalConsistencyVerify: ALL OK"
                : "RepeatGoalConsistencyVerify: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static Snapshot analyze(List<String> corpus, List<GoalSpec> goals, DiscoveryPolicy policy) throws Exception {
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"), 1, 12, 30.0, 10.0, false, 0.0, false);
        return analyzer.analyzeStream(corpus.iterator(), new LineExecutor.Inline(),
                12, goals, policy, new AnalysisListener() {});
    }

    private static Set<String> keys(List<GoalSpec> goals) {
        Set<String> s = new LinkedHashSet<>();
        for (GoalSpec g : goals) s.add(g.key());
        return s;
    }

    private static Set<String> frontIds(Snapshot snap) {
        Set<String> ids = new LinkedHashSet<>();
        for (LineResult r : snap.paretoFront()) {
            Matcher m = ID.matcher(r.originalLine == null ? "" : r.originalLine);
            if (m.find()) ids.add(m.group(1));
        }
        return ids;
    }
}
