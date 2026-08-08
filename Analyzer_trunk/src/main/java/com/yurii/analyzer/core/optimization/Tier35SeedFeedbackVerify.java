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
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Tier-3.5 verifier — closes the Master-mode feedback loop end-to-end:
 *
 *   corpus → Snapshot → toBundleSeed → JSON file → readFromFile → identical Seed
 *
 * <p>What's covered:</p>
 * <ul>
 *   <li>Pareto-front members surface as {@code role=pareto} winners.</li>
 *   <li>Per-metric champions surface as {@code role=champion-min:<key>} /
 *       {@code champion-max:<key>}.</li>
 *   <li>Balanced-optimum picks surface as {@code role=balanced:<strategy>}
 *       for all three scalarization strategies.</li>
 *   <li>{@code observedRanges} carries per-key min/max/mean/stdev that
 *       match the snapshot's {@code KeyStats}.</li>
 *   <li>{@code declaredMetrics} mirrors the analyzer's declared goal keys.</li>
 *   <li>Round-trip: write → read → distinct lineNos match + winner count
 *       matches + numeric fields stable through Jackson serialization.</li>
 *   <li>NSGA-II crowding distance, when supplied, threads through to winner
 *       JSON (including {@code Infinity} for boundary members and {@code null}
 *       for legacy non-NSGA winners).</li>
 * </ul>
 *
 *   Run:  java -cp ... Tier35SeedFeedbackVerify
 */
public final class Tier35SeedFeedbackVerify {
    private Tier35SeedFeedbackVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testBasicSeedExtraction();
        failures += testJsonRoundTrip();
        failures += testEmptySnapshotEdgeCases();
        failures += testCrowdingDistanceThreading();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL TIER-3.5 SEED-FEEDBACK CHECKS PASSED");
        else { System.out.println("❌ " + failures + " TIER-3.5 SEED-FEEDBACK CHECK(S) FAILED");
               System.exit(1); }
    }

    /** Run a small 2-axis MIN/MAX corpus through the streaming aggregator and
     *  confirm BundleSeed contains the three winner classes. */
    private static int testBasicSeedExtraction() throws Exception {
        System.out.println("── Seed extraction (Pareto + champions + balanced) ──");
        OnlineMetricAggregator.Snapshot snap = runCorpus(false);

        BundleSeed seed = BundleSeed.fromSnapshot(snap, "test-run-001");
        int f = 0;
        f += assertCond("seed has non-zero winners",          seed.size() > 0);
        f += assertCond("seed has sourceRunId='test-run-001'", "test-run-001".equals(seed.sourceRunId));
        f += assertCond("seed.totalCandidatesObserved equals snapshot.updates()",
                seed.totalCandidatesObserved == snap.updates());

        List<BundleSeed.Winner> pareto =      seed.winnersWithRolePrefix("pareto");
        List<BundleSeed.Winner> champMin =    seed.winnersWithRolePrefix("champion-min:");
        List<BundleSeed.Winner> champMax =    seed.winnersWithRolePrefix("champion-max:");
        List<BundleSeed.Winner> balanced =    seed.winnersWithRolePrefix("balanced:");
        f += assertCond("seed has ≥1 'pareto' winner",         !pareto.isEmpty());
        f += assertCond("seed has ≥1 'champion-min:' winner",  !champMin.isEmpty());
        f += assertCond("seed has ≥1 'champion-max:' winner",  !champMax.isEmpty());
        f += assertCond("seed has 3 'balanced:' winners (weighted/tcheby/dist)",
                balanced.size() == 3);

        // declaredMetrics matches the analyzer's goal keys
        f += assertCond("seed.declaredMetrics contains 'cost'",
                seed.declaredMetrics.contains("cost"));
        f += assertCond("seed.declaredMetrics contains 'latency'",
                seed.declaredMetrics.contains("latency"));

        // observedRanges carries every per-key stat with positive n
        f += assertCond("seed.observedRanges has 'cost'",
                seed.observedRanges.containsKey("cost"));
        f += assertCond("seed.observedRanges has 'latency'",
                seed.observedRanges.containsKey("latency"));
        BundleSeed.MetricRange costRange = seed.observedRanges.get("cost");
        OnlineMetricAggregator.KeyStats costStats = snap.perKeyStats().get("cost");
        f += assertCond("cost range matches KeyStats (min/max/mean)",
                costRange != null && costStats != null
                && Math.abs(costRange.min()  - costStats.min)  < 1e-9
                && Math.abs(costRange.max()  - costStats.max)  < 1e-9
                && Math.abs(costRange.mean() - costStats.mean) < 1e-9);
        return f;
    }

    /** writeToFile → readFromFile → verify distinct lineNos preserved and
     *  numeric fields stable through Jackson. */
    private static int testJsonRoundTrip() throws Exception {
        System.out.println("\n── Seed JSON round-trip (file write/read) ──");
        OnlineMetricAggregator.Snapshot snap = runCorpus(false);
        BundleSeed seed = snap.toBundleSeed("rt-001");

        Path tmp = Files.createTempFile("bundle_seed_rt_", ".json");
        seed.writeToFile(tmp);
        BundleSeed read = BundleSeed.readFromFile(tmp);

        int f = 0;
        f += assertCond("round-trip preserves winner count",
                seed.size() == read.size());
        f += assertCond("round-trip preserves distinct lineNos",
                seed.distinctLineNos().equals(read.distinctLineNos()));
        f += assertCond("round-trip preserves sourceRunId",
                seed.sourceRunId.equals(read.sourceRunId));
        f += assertCond("round-trip preserves totalCandidatesObserved",
                seed.totalCandidatesObserved == read.totalCandidatesObserved);
        f += assertCond("round-trip preserves declaredMetrics",
                seed.declaredMetrics.equals(read.declaredMetrics));
        f += assertCond("round-trip preserves observedRanges keys",
                seed.observedRanges.keySet().equals(read.observedRanges.keySet()));

        // Spot-check one winner's kvPairs are identical
        BundleSeed.Winner orig = seed.winners.get(0);
        BundleSeed.Winner round = read.winners.get(0);
        f += assertCond("winner[0] role identical",     orig.role().equals(round.role()));
        f += assertCond("winner[0] lineNo identical",   orig.lineNo() == round.lineNo());
        f += assertCond("winner[0] kvPairs identical",  orig.kvPairs().equals(round.kvPairs()));

        // JSON has the schemaVersion key (forward-compat marker)
        JsonNode root = AnalyzerCore.mapper().readTree(Files.readString(tmp));
        f += assertCond("JSON carries 'schemaVersion'", root.has("schemaVersion"));
        Files.deleteIfExists(tmp);
        return f;
    }

    private static int testEmptySnapshotEdgeCases() throws Exception {
        System.out.println("\n── Edge cases (null / empty snapshot) ──");
        BundleSeed nullSeed = BundleSeed.fromSnapshot(null, "x");
        int f = 0;
        f += assertCond("null snapshot → empty seed (no exception)",
                nullSeed.winners.isEmpty() && nullSeed.observedRanges.isEmpty());
        f += assertCond("null snapshot seed preserves sourceRunId",
                "x".equals(nullSeed.sourceRunId));

        // Round-trip the empty seed → still valid
        Path tmp = Files.createTempFile("bundle_seed_empty_", ".json");
        nullSeed.writeToFile(tmp);
        BundleSeed read = BundleSeed.readFromFile(tmp);
        f += assertCond("empty seed round-trips through JSON",
                read.winners.isEmpty() && "x".equals(read.sourceRunId));
        Files.deleteIfExists(tmp);
        return f;
    }

    /** Pass an NSGA-II crowding-distance map to fromSnapshot and confirm:
     *  (a) winners carry the supplied crowding,
     *  (b) JSON encodes Infinity as a string sentinel + null for NaN,
     *  (c) round-trip restores both. */
    private static int testCrowdingDistanceThreading() throws Exception {
        System.out.println("\n── NSGA-II crowding distance flows through ──");
        OnlineMetricAggregator.Snapshot snap = runCorpus(true);
        // Mock a crowding map: assign +∞ to the first front member, finite to others.
        java.util.Map<Integer, Double> crowd = new java.util.LinkedHashMap<>();
        List<LineResult> front = snap.paretoFront();
        for (int i = 0; i < front.size(); i++) {
            if (i == 0)                  crowd.put(front.get(i).lineNo, Double.POSITIVE_INFINITY);
            else if (i == front.size()-1)crowd.put(front.get(i).lineNo, Double.POSITIVE_INFINITY);
            else                          crowd.put(front.get(i).lineNo, 0.5);
        }

        BundleSeed seed = BundleSeed.fromSnapshot(snap, "nsga-001", crowd);

        boolean sawInfinity = false, sawFinite = false, sawNan = false;
        for (BundleSeed.Winner w : seed.winners) {
            if (Double.isInfinite(w.crowdingDistance())) sawInfinity = true;
            else if (Double.isFinite(w.crowdingDistance()) && w.crowdingDistance() > 0) sawFinite = true;
            else if (Double.isNaN(w.crowdingDistance())) sawNan = true;
        }
        int f = 0;
        f += assertCond("at least one winner has +∞ crowding (front boundary)", sawInfinity);
        // sawFinite depends on front size — for our 8-candidate corpus the
        // front is usually 4-5 long so interior members exist.  Skip if not.
        f += assertCond("either finite-crowding winners exist OR front too small to have interior",
                sawFinite || front.size() <= 2);
        f += assertCond("champion / balanced winners may have NaN crowding (no NSGA on them)",
                sawNan || seed.winnersWithRolePrefix("champion-min:").isEmpty());

        // JSON round-trip preserves both Infinity and NaN representations
        Path tmp = Files.createTempFile("bundle_seed_crowding_", ".json");
        seed.writeToFile(tmp);
        String json = Files.readString(tmp);
        f += assertCond("JSON encodes +∞ as the string 'Infinity'",
                json.contains("\"Infinity\""));

        BundleSeed read = BundleSeed.readFromFile(tmp);
        boolean readInfinity = false, readNan = false;
        for (BundleSeed.Winner w : read.winners) {
            if (Double.isInfinite(w.crowdingDistance())) readInfinity = true;
            if (Double.isNaN(w.crowdingDistance()))      readNan      = true;
        }
        f += assertCond("readback preserves +∞ crowding distance",
                readInfinity == sawInfinity);
        f += assertCond("readback preserves NaN crowding distance",
                readNan == sawNan);
        Files.deleteIfExists(tmp);
        return f;
    }

    // ── helpers ──────────────────────────────────────────────────────────

    /** Spin up an 8-candidate 2-axis MIN/MIN run and return its Snapshot. */
    private static OnlineMetricAggregator.Snapshot runCorpus(boolean useNsga) throws Exception {
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig(
                "{\"optimizations\":["
                    + "{\"key\":\"cost\",\"mode\":\"minimize\",\"weight\":30},"
                    + "{\"key\":\"latency\",\"mode\":\"minimize\",\"weight\":30}"
                    + "]}");
        com.yurii.analyzer.core.optimization.FrontAlgorithm algo =
                useNsga
                        ? com.yurii.analyzer.core.optimization.FrontAlgorithm.NSGA_II
                        : com.yurii.analyzer.core.optimization.FrontAlgorithm.PARETO;
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual, 1, 8, 30.0, 10.0, false, 0.0, false,
                new com.yurii.analyzer.core.optimization.LineParser.KvLineParser(),
                algo);

        List<String> corpus = new ArrayList<>();
        // Eight 2-axis MIN/MIN candidates — five on the Pareto front, three
        // strictly dominated.
        double[][] tuples = {
            {0.10, 9.0}, {0.25, 7.0}, {0.40, 5.0}, {0.55, 3.0}, {0.80, 2.0},
            {0.90, 8.0}, {0.95, 6.0}, {0.99, 4.0},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "id=s_%02d cost=%.3f latency=%.2f score=%.2f",
                    i + 1, tuples[i][0], tuples[i][1], (1.0 - tuples[i][0]) * 100));
        }

        return analyzer.analyzeStream(
                corpus.iterator(),
                new LineExecutor.Inline(),
                /*topK*/ 5,
                analyzer.goals().stream().map(g -> "maximize".equals(g.mode)
                        ? GoalSpec.max(g.key, g.weight)
                        : GoalSpec.min(g.key, g.weight)).toList(),
                DiscoveryPolicy.DEFAULT,
                new AnalyzerCore.AnalysisListener() {});
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
