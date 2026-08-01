package com.yurii.analyzer.core.optimization;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Verifier for {@link RepeatAggregator} (Automation handoff #35 step 7; design docs/24 §6).
 * Forked by {@link com.yurii.analyzer.AllVerifiersRunner}; prints per-check status and exits
 * non-zero on any failure. No external dependencies, no DB, no corpus files — pure aggregation.
 */
public final class RepeatAggregatorVerify {
    private RepeatAggregatorVerify() {}

    private static int failures = 0;

    private static void check(String desc, boolean ok) {
        System.out.println((ok ? "  ok   " : "  FAIL ") + desc);
        if (!ok) failures++;
    }

    private static String line(String id, int rep, String env, String kv) {
        return "candidate_id=" + id + " repeat_idx=" + rep + " env_id=" + env
                + " source_ref=" + id + ".py run_id=r " + kv;
    }

    public static void main(String[] args) {
        System.out.println("── RepeatAggregatorVerify (repeat-aware median + order-statistic CI + ties) ──");
        oddEvenMedian();
        targetTransformedBeforeAggregate();
        missingSamples();
        duplicateIdentity();
        invalidIdentityFailsClosed();
        inconsistentEnvironmentFailsClosed();
        nonFiniteMetricIsMissing();
        analyzerLinePreservesProvenanceAndObjectiveSemantics();
        aggregateVerdictAndEligibility();
        noEligibleCandidatesFailClosed();
        k1IsPointNoInterval();
        insufficientN();
        exactCiRanks();
        invalidAlphaFailsClosed();
        legacyK1CorpusLine();
        nonTransitiveTie();
        System.out.println(failures == 0
                ? "RepeatAggregatorVerify: ALL OK"
                : "RepeatAggregatorVerify: " + failures + " FAILURE(S)");
        System.exit(failures == 0 ? 0 : 1);
    }

    private static void oddEvenMedian() {
        GoalSpec lat = GoalSpec.min("lat");
        // odd n: {10,20,30} -> median 20
        var odd = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=10"), line("A", 1, "e", "lat=30"), line("A", 2, "e", "lat=20")),
                List.of(lat));
        check("odd-n median is the central order statistic (20)",
                odd.get("A").objective().get("lat").median() == 20.0
                        && odd.get("A").medianRaw().get("lat") == 20.0);
        // even n: {10,20,30,40} -> median 25
        var even = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=40"), line("A", 1, "e", "lat=10"),
                line("A", 2, "e", "lat=30"), line("A", 3, "e", "lat=20")), List.of(lat));
        check("even-n median is the mean of the two central order statistics (25)",
                even.get("A").objective().get("lat").median() == 25.0);
    }

    private static void targetTransformedBeforeAggregate() {
        // TARGET 50: samples {10,90} -> deviations {40,40} -> median 40.
        // The wrong order |median(10,90) - 50| = |50-50| = 0 must NOT be produced.
        GoalSpec g = GoalSpec.target("lat", 50.0);
        var agg = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=10"), line("A", 1, "e", "lat=90")), List.of(g));
        double dev = agg.get("A").objective().get("lat").median();
        check("TARGET transforms each raw sample to |v-target| BEFORE the median (40, not 0)", dev == 40.0);
        check("TARGET keeps the raw median for reporting (50)", agg.get("A").medianRaw().get("lat") == 50.0);
    }

    private static void missingSamples() {
        // 3 samples, one missing the metric -> n=2 for the goal, 1 missing counted.
        GoalSpec lat = GoalSpec.min("lat");
        var agg = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=10"), line("A", 1, "e", "other=5"), line("A", 2, "e", "lat=20")),
                List.of(lat));
        RepeatAggregator.MetricStat s = agg.get("A").objective().get("lat");
        check("missing samples reduce n (2, not 3) and are counted",
                s.n() == 2 && agg.get("A").sampleCount() == 3 && agg.get("A").missingTotal() == 1);
    }

    private static void duplicateIdentity() {
        GoalSpec lat = GoalSpec.min("lat");
        var aggregate = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=10"), line("A", 0, "e", "lat=10"),
                line("A", 1, "e", "lat=20")), List.of(lat));
        check("identical replay of one sample identity is idempotently de-duplicated",
                aggregate.get("A").sampleCount() == 2
                        && aggregate.get("A").medianRaw().get("lat") == 15.0);
        check("conflicting duplicate sample identity fails closed",
                throwsIAE(() -> RepeatAggregator.aggregate(List.of(
                        line("A", 0, "e", "lat=10"),
                        line("A", 0, "e", "lat=999")), List.of(lat))));
    }

    private static void invalidIdentityFailsClosed() {
        check("malformed repeat_idx fails closed",
                throwsIAE(() -> RepeatAggregator.parseLine(
                        "candidate_id=A repeat_idx=x env_id=e lat=1")));
        check("negative repeat_idx fails closed",
                throwsIAE(() -> RepeatAggregator.parseLine(
                        "candidate_id=A repeat_idx=-1 env_id=e lat=1")));
        check("repeat-aware row without candidate_id fails closed",
                throwsIAE(() -> RepeatAggregator.parseLine(
                        "repeat_idx=0 env_id=e lat=1")));
    }

    private static void inconsistentEnvironmentFailsClosed() {
        GoalSpec lat = GoalSpec.min("lat");
        check("local aggregate refuses to merge different environments",
                throwsIAE(() -> RepeatAggregator.aggregate(List.of(
                        line("A", 0, "e1", "lat=1"),
                        line("A", 1, "e2", "lat=2")), List.of(lat))));
    }

    private static void nonFiniteMetricIsMissing() {
        GoalSpec lat = GoalSpec.min("lat");
        var aggregate = RepeatAggregator.aggregate(
                List.of(line("A", 0, "e", "lat=Infinity")), List.of(lat));
        check("non-finite metric is excluded and counted missing",
                !aggregate.get("A").objective().containsKey("lat")
                        && aggregate.get("A").missingTotal() == 1);
    }

    private static void analyzerLinePreservesProvenanceAndObjectiveSemantics() {
        GoalSpec target = GoalSpec.target("lat", 50.0);
        GoalSpec maximize = GoalSpec.max("throughput");
        var aggregate = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=10 throughput=10"),
                line("A", 1, "e", "lat=90 throughput=30")),
                List.of(target, maximize));
        String rendered = RepeatAggregator.toAnalyzerLines(
                aggregate, List.of(target, maximize)).get(0);
        check("aggregate line preserves candidate/run/source provenance",
                rendered.contains("candidate_id=A")
                        && rendered.contains("source_ref=A.py")
                        && rendered.contains("run_id=r"));
        RepeatAggregator.Sample reparsed = RepeatAggregator.parseLine(rendered);
        check("aggregate line re-applies original goals to median deviations",
                target.deviation(reparsed.metrics().get("lat")) == 40.0
                        && maximize.deviation(reparsed.metrics().get("throughput")) == -20.0);
    }

    private static void aggregateVerdictAndEligibility() {
        GoalSpec lat = GoalSpec.min("lat");
        var aggregates = RepeatAggregator.aggregate(List.of(
                line("pass", 0, "e", "FW_VAR=0 lat=1"),
                line("pass", 1, "e", "FW_VAR=0 lat=3"),
                line("fail", 0, "e", "FW_VAR=7 lat=0"),
                line("fail", 1, "e", "FW_VAR=7 lat=0"),
                line("legacy", 0, "e", "lat=2"),
                line("legacy", 1, "e", "lat=4")), List.of(lat));
        List<String> rendered = RepeatAggregator.toAnalyzerLines(aggregates, List.of(lat));
        check("aggregate output propagates explicit FW_VAR verdicts",
                rendered.stream().anyMatch(s -> s.contains("candidate_id=pass")
                        && s.contains("FW_VAR=0"))
                        && rendered.stream().anyMatch(s -> s.contains("candidate_id=fail")
                        && s.contains("FW_VAR=7"))
                        && rendered.stream().anyMatch(s -> s.contains("candidate_id=legacy")
                        && !s.contains("FW_VAR=")));

        RepeatAggregator.EligibilityResult filtered =
                RepeatAggregator.filterEligible(rendered);
        check("eligibility excludes explicit nonzero FW_VAR after aggregation",
                filtered.rejectedNonzero() == 1
                        && filtered.eligibleLines().stream()
                        .noneMatch(s -> s.contains("candidate_id=fail")));
        check("missing FW_VAR remains eligible and is counted for compatibility warning",
                filtered.missingVerdict() == 1
                        && filtered.eligibleLines().stream()
                        .anyMatch(s -> s.contains("candidate_id=legacy")));
    }

    private static void noEligibleCandidatesFailClosed() {
        check("all explicit nonzero FW_VAR candidates fail closed",
                throwsIAE(() -> RepeatAggregator.filterEligible(List.of(
                        "candidate_id=A FW_VAR=1 lat=1",
                        "candidate_id=B FW_VAR=-2 lat=2"))));
        check("malformed explicit FW_VAR fails closed during eligibility filtering",
                throwsIAE(() -> RepeatAggregator.filterEligible(List.of(
                        "candidate_id=A FW_VAR=not_an_int lat=1"))));
    }

    private static boolean throwsIAE(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }
    private static void k1IsPointNoInterval() {
        GoalSpec lat = GoalSpec.min("lat");
        var agg = RepeatAggregator.aggregate(List.of(line("A", 0, "e", "lat=42")), List.of(lat));
        RepeatAggregator.MetricStat s = agg.get("A").objective().get("lat");
        check("K=1 is a point, no interval (median 42, ci invalid, method point_k1)",
                s.median() == 42.0 && !s.ciValid() && s.method().equals("point_k1") && s.n() == 1);
    }

    private static void insufficientN() {
        // n=3, alpha=0.05: the extreme rank tail (0.5^3=0.125) already exceeds alpha/2 -> insufficient.
        GoalSpec lat = GoalSpec.min("lat");
        var agg = RepeatAggregator.aggregate(List.of(
                line("A", 0, "e", "lat=10"), line("A", 1, "e", "lat=20"), line("A", 2, "e", "lat=30")),
                List.of(lat), 0.05);
        RepeatAggregator.MetricStat s = agg.get("A").objective().get("lat");
        check("insufficient n (3 @ 95%) reports range, ci invalid, method range_insufficient_n",
                !s.ciValid() && s.method().equals("range_insufficient_n")
                        && s.ciLow() == 10.0 && s.ciHigh() == 30.0 && s.median() == 20.0);
    }

    private static void exactCiRanks() {
        // n=6, alpha=0.05: extreme ranks l=1,u=6 -> CI=[min,max], achieved coverage 0.96875.
        GoalSpec lat = GoalSpec.min("lat");
        List<String> corpus = new java.util.ArrayList<>();
        double[] vals = {1, 2, 3, 4, 5, 6};
        for (int i = 0; i < vals.length; i++) corpus.add(line("A", i, "e", "lat=" + (int) vals[i]));
        RepeatAggregator.MetricStat s =
                RepeatAggregator.aggregate(corpus, List.of(lat), 0.05).get("A").objective().get("lat");
        check("n=6 @95% gives exact order-statistic ranks l=1,u=6 (CI [1,6])",
                s.ciValid() && s.method().equals("order_statistic")
                        && s.ciLow() == 1.0 && s.ciHigh() == 6.0 && s.median() == 3.5);
        check("n=6 @95% achieved coverage is 0.96875", Math.abs(s.coverage() - 0.96875) < 1e-9);
    }

    private static void invalidAlphaFailsClosed() {
        check("alpha outside (0,1) fails closed",
                throwsIAE(() -> RepeatAggregator.orderStatisticCI(
                        new double[]{1, 2, 3}, 0.0))
                        && throwsIAE(() -> RepeatAggregator.orderStatisticCI(
                        new double[]{1, 2, 3}, 1.0)));
    }

    private static void legacyK1CorpusLine() {
        // a legacy corpus line with NO repeat_idx/env_id tokens parses as one sample (repeat 0).
        GoalSpec lat = GoalSpec.min("lat");
        var agg = RepeatAggregator.aggregate(
                List.of("candidate_id=A source_ref=A.py run_id=r lat=7"), List.of(lat));
        check("legacy K=1 line (no repeat identity tokens) aggregates as one sample",
                agg.containsKey("A") && agg.get("A").sampleCount() == 1
                        && agg.get("A").medianRaw().get("lat") == 7.0);
    }

    private static void nonTransitiveTie() {
        // A~B, B~C, A≁C: anchored neighborhoods must NOT transitively merge A and C.
        // n=6 ⇒ CI = [min,max]. A=[8,13], B=[11,16], C=[14,19].
        GoalSpec lat = GoalSpec.min("lat");
        List<String> corpus = new java.util.ArrayList<>();
        int[][] vals = {{8, 9, 10, 11, 12, 13}, {11, 12, 13, 14, 15, 16}, {14, 15, 16, 17, 18, 19}};
        String[] ids = {"A", "B", "C"};
        for (int c = 0; c < 3; c++)
            for (int i = 0; i < 6; i++) corpus.add(line(ids[c], i, "e", "lat=" + vals[c][i]));
        var aggs = RepeatAggregator.aggregate(corpus, List.of(lat), 0.05);
        Map<String, Set<String>> tiers = RepeatAggregator.tieNeighborhoods(aggs, List.of(lat));
        check("T(A) = {A,B} (A is NOT tied with the disjoint C — no transitive closure)",
                tiers.get("A").equals(Set.of("A", "B")));
        check("T(C) = {B,C} (C is NOT tied with the disjoint A)",
                tiers.get("C").equals(Set.of("B", "C")));
        check("T(B) = {A,B,C} (B legitimately overlaps both anchors)",
                tiers.get("B").equals(Set.of("A", "B", "C")));
    }
}
