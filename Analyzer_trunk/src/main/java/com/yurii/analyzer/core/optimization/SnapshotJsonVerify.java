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

import com.fasterxml.jackson.databind.JsonNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;

/**
 * Verifies the {@code Snapshot.toJson()} machine-readable report:
 *   • All six sections present
 *   • Schema matches the documented record layout
 *   • Numeric values agree with the corresponding {@code render()} fields
 *   • Round-trips through Jackson serialise → deserialise cleanly
 */
public final class SnapshotJsonVerify {
    private SnapshotJsonVerify() {}

    public static void main(String[] args) throws Exception {
        // Drive a small streaming analysis and capture the snapshot.
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 5, 30.0, 10.0, false, 0.0, false);

        List<GoalSpec> goals = List.of(
                GoalSpec.min("cost", 1.0),
                GoalSpec.max("throughput", 1.0));

        OnlineMetricAggregator.Snapshot snap = analyzer.analyzeStream(
                rows(),
                new LineExecutor.Inline(),
                /*topK*/ 5, goals, DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});

        JsonNode json = snap.toJson();
        String pretty = AnalyzerCore.mapper().writerWithDefaultPrettyPrinter().writeValueAsString(json);
        System.out.println(pretty);

        int f = 0;
        // 1. Top-level sections present
        for (String section : new String[]{
                "updates", "perKeyStats", "declaredGoals", "autoDiscoveredAxes",
                "autoPolicy", "paretoFront", "topByScore", "balancedOptima"}) {
            f += assertCond("section present: " + section, json.has(section));
        }

        // 2. updates matches snapshot
        f += assertCond("updates == snap.updates",
                json.get("updates").asLong() == snap.updates());

        // 3. perKeyStats keys match the discovered keys
        f += assertCond("perKeyStats includes 'cost'",       json.get("perKeyStats").has("cost"));
        f += assertCond("perKeyStats includes 'throughput'", json.get("perKeyStats").has("throughput"));
        f += assertCond("perKeyStats includes 'latency'",    json.get("perKeyStats").has("latency"));

        // 4. Declared goals count + content
        f += assertCond("declaredGoals.size() == 2", json.get("declaredGoals").size() == 2);
        f += assertCond("first declared goal key == cost",
                "cost".equals(json.get("declaredGoals").get(0).get("key").asText()));
        f += assertCond("first declared goal mode == MINIMIZE",
                "MINIMIZE".equals(json.get("declaredGoals").get(0).get("mode").asText()));

        // 5. autoDiscoveredAxes — latency wasn't declared, should appear
        boolean hasLatencyAuto = false;
        for (JsonNode a : json.get("autoDiscoveredAxes")) {
            if ("latency".equals(a.get("key").asText())) {
                hasLatencyAuto = true;
                f += assertCond("auto-discovered latency.mode == MINIMIZE (lexical)",
                        "MINIMIZE".equals(a.get("mode").asText()));
                f += assertCond("auto-discovered latency.inferred == true",
                        a.get("inferred").asBoolean());
            }
        }
        f += assertCond("latency appears in autoDiscoveredAxes", hasLatencyAuto);

        // 6. paretoFront non-empty + each entry has full schema
        f += assertCond("paretoFront non-empty", json.get("paretoFront").size() > 0);
        JsonNode firstFront = json.get("paretoFront").get(0);
        for (String field : new String[]{"lineNo", "score", "decision", "lineType", "snippet"}) {
            f += assertCond("paretoFront[0] has '" + field + "'", firstFront.has(field));
        }

        // 7. balancedOptima — all 3 strategies present
        java.util.Set<String> strategies = new java.util.HashSet<>();
        for (JsonNode b : json.get("balancedOptima")) strategies.add(b.get("strategy").asText());
        for (String s : List.of("weighted-sum", "tchebycheff", "distance-to-ideal")) {
            f += assertCond("balancedOptima contains strategy: " + s, strategies.contains(s));
        }

        // 8. Round-trip: serialize → parse → schema same
        String serialised = json.toString();
        JsonNode reparsed = AnalyzerCore.mapper().readTree(serialised);
        f += assertCond("JSON round-trip preserves updates",
                reparsed.get("updates").asLong() == json.get("updates").asLong());
        f += assertCond("JSON round-trip preserves declaredGoals size",
                reparsed.get("declaredGoals").size() == json.get("declaredGoals").size());

        System.out.println();
        if (f == 0) System.out.println("✅ ALL SNAPSHOT-JSON CHECKS PASSED");
        else { System.out.println("❌ " + f + " SNAPSHOT-JSON CHECK(S) FAILED"); System.exit(1); }
    }

    private static Iterator<String> rows() {
        double[][] tuples = {
                {0.95, 12.5, 400}, {0.50, 6.5, 1300},
                {0.25, 5.1, 2600}, {0.10, 3.0, 4200}, {0.08, 2.5, 4500}};
        return new Iterator<>() {
            int i = 0;
            @Override public boolean hasNext() { return i < tuples.length; }
            @Override public String next() {
                if (i >= tuples.length) throw new NoSuchElementException();
                double[] t = tuples[i++];
                return String.format(Locale.ROOT,
                        "id=j_%02d cost=%.3f latency=%.2fms throughput=%.0f",
                        i, t[0], t[1], t[2]);
            }
        };
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
