// AnalyzeKv — headless driver: ingest a corpus of candidate stdout K=V lines and
// run the Heuristic Analyzer's streaming multi-objective optimizer over them.
// Prints the canonical Snapshot (Welford per-metric stats + champions, online
// Pareto front via NSGA-II, top-K by score, balanced optima) for the data metrics.
//
//   java -cp <analyzer-jar:deps:.> AnalyzeKv <metrics.kv> [topK] [goals] \
//        [--mode formal|exploratory] [--corpus-count N]
//        [--seed-out bundle_seed.json] [--seed-source-run-id RUN]
//
// STEP 38: --mode selects FORMAL (explicit goals required, NO auto-added axes,
// fixed directions, corpus count required) vs EXPLORATORY (auto-discovery on,
// inferred axes labelled). Default is exploratory (backwards-compatible).
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.optimization.AnalysisMode;
import com.yurii.analyzer.core.optimization.DiscoveryPolicy;
import com.yurii.analyzer.core.optimization.GoalSpec;
import com.yurii.analyzer.core.optimization.BundleSeed;
import com.yurii.analyzer.core.optimization.LineExecutor;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot;
import com.yurii.analyzer.core.optimization.ProvenanceReport;
import com.yurii.analyzer.core.optimization.RepeatAggregator;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class AnalyzeKv {
    public static void main(String[] args) throws Exception {
        // --- split flags (--mode / --corpus-count) from the positional args --- //
        String modeStr = null;
        Integer corpusCount = null;
        String provenanceOut = null;
        String seedOut = null;
        String seedSourceRunId = "analyzekv-" + System.currentTimeMillis();
        List<String> pos = new ArrayList<>();
        for (int i = 0; i < args.length; i++) {
            String a = args[i];
            if (a.equals("--mode") && i + 1 < args.length)            modeStr = args[++i];
            else if (a.startsWith("--mode="))                         modeStr = a.substring("--mode=".length());
            else if (a.equals("--corpus-count") && i + 1 < args.length) corpusCount = Integer.valueOf(args[++i].trim());
            else if (a.startsWith("--corpus-count="))                 corpusCount = Integer.valueOf(a.substring("--corpus-count=".length()).trim());
            else if (a.equals("--provenance-out") && i + 1 < args.length) provenanceOut = args[++i];
            else if (a.startsWith("--provenance-out="))               provenanceOut = a.substring("--provenance-out=".length());
            else if (a.equals("--seed-out") && i + 1 < args.length)   seedOut = args[++i];
            else if (a.startsWith("--seed-out="))                     seedOut = a.substring("--seed-out=".length());
            else if (a.equals("--seed-source-run-id") && i + 1 < args.length) seedSourceRunId = args[++i];
            else if (a.startsWith("--seed-source-run-id="))           seedSourceRunId = a.substring("--seed-source-run-id=".length());
            else pos.add(a);
        }
        AnalysisMode mode = AnalysisMode.fromText(modeStr);

        Path corpus = Path.of(pos.size() > 0 ? pos.get(0) : "metrics.kv");
        int topK = pos.size() > 1 ? Integer.parseInt(pos.get(1)) : 12;

        List<String> lines = new ArrayList<>();
        for (String ln : Files.readAllLines(corpus)) {
            String s = ln.strip();
            if (!s.isEmpty() && !s.startsWith("#")) lines.add(s);
        }

        // Goals: optional 3rd positional "key:max,key:min,..." retargets the SAME
        // domain-agnostic analyzer to any domain. In FORMAL mode they are REQUIRED;
        // the default api_probe set is only an EXPLORATORY convenience.
        List<GoalSpec> goals = new ArrayList<>();
        boolean explicitGoals = pos.size() > 2 && !pos.get(2).isBlank();
        if (explicitGoals) {
            for (String tok : pos.get(2).split(",")) {
                if (tok.isBlank()) continue;
                String[] kv = tok.trim().split(":");
                String key = kv[0].trim();
                String dir = kv.length > 1 ? kv[1].trim().toLowerCase() : "min";
                goals.add(dir.startsWith("max") ? GoalSpec.max(key) : GoalSpec.min(key));
            }
        } else if (mode == AnalysisMode.EXPLORATORY) {
            goals.addAll(List.of(                  // default: api_probe DATA metrics
                    GoalSpec.max("dq_score"), GoalSpec.max("coverage"), GoalSpec.max("rows"),
                    GoalSpec.max("distinct_hours"), GoalSpec.min("latency_ms"),
                    GoalSpec.min("db_ms"), GoalSpec.min("violations"),
                    GoalSpec.min("nulls"), GoalSpec.min("monotonic_breaks")));
        }

        mode.validate(goals, corpusCount);

        // Repeat-aware corpora carry K raw observations per candidate. Collapse them exactly
        // once here, before the ordinary streaming/Pareto path; legacy K=1 corpora remain
        // byte-for-byte on the old path.
        boolean repeatAware = RepeatAggregator.containsRepeatIdentity(lines);
        List<String> analysisLines = lines;
        if (repeatAware) {
            var aggregates = RepeatAggregator.aggregate(lines, goals);
            analysisLines = RepeatAggregator.toAnalyzerLines(aggregates, goals);
            if (analysisLines.isEmpty())
                throw new IllegalArgumentException("repeat-aware corpus produced no candidate aggregates");
        }
        int prefilterCandidateCount = analysisLines.size();

        // --corpus-count is the generator's candidate count C. For repeat-aware input it
        // therefore closes against distinct candidate aggregates, not raw opportunities I.
        // Reconcile before FW_VAR eligibility filtering: C describes the generated corpus,
        // including candidates that executed and returned an explicit failing verdict.
        if (mode == AnalysisMode.FORMAL && corpusCount != null
                && corpusCount != prefilterCandidateCount)
            throw new IllegalArgumentException("formal mode: declared candidate count " + corpusCount
                    + " != " + prefilterCandidateCount + " candidate aggregates from "
                    + lines.size() + " raw line(s) in " + corpus);

        RepeatAggregator.EligibilityResult eligibility =
                RepeatAggregator.filterEligible(analysisLines);
        analysisLines = eligibility.eligibleLines();
        if (eligibility.missingVerdict() > 0)
            System.err.println("WARNING: " + eligibility.missingVerdict()
                    + " candidate(s) have no FW_VAR; retaining them for legacy compatibility");
        if (eligibility.rejectedNonzero() > 0)
            System.out.println("eligibility: excluded " + eligibility.rejectedNonzero()
                    + " candidate(s) with explicit nonzero FW_VAR; "
                    + analysisLines.size() + " eligible candidate(s) remain");

        // When the operator supplied explicit goals, rank ONLY those — never auto-discover extra
        // numeric fields (e.g. configuration params like threads/batch). This keeps the K=1 raw
        // path and the K>1 repeat-aggregated path on the SAME declared objective set, so a
        // deterministic spec yields the identical Pareto front at K=1 and K=3 (the repeat path
        // already emits only the declared goal keys via RepeatAggregator.toAnalyzerLines).
        DiscoveryPolicy policy = explicitGoals
                ? DiscoveryPolicy.DECLARED_ONLY
                : mode.discoveryPolicy(DiscoveryPolicy.DEFAULT);

        System.out.println("AnalyzeKv: mode=" + mode.label() + "  ingesting "
                + (repeatAware
                    ? lines.size() + " raw repeat sample(s) -> " + prefilterCandidateCount
                        + " candidate aggregate(s) -> " + analysisLines.size() + " eligible"
                    : prefilterCandidateCount + " candidate K=V line(s) -> "
                        + analysisLines.size() + " eligible")
                + " from " + corpus + "  (topK=" + topK
                + ", discovery=" + (policy.include() ? "on" : "off") + ")");
        // Explicit-vs-inferred direction disagreements are surfaced, never silently mixed.
        for (String c : AnalysisMode.directionConflicts(goals))
            System.out.println("  ⚠ direction conflict — " + c);

        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                /*minSupport*/ 1, /*topK*/ topK, /*optThreshold*/ 30.0,
                /*watchThreshold*/ 10.0, /*executeCommands*/ false,
                /*commandTimeout*/ 0.0, /*dynamicPython*/ false);

        Snapshot snap = analyzer.analyzeStream(
                analysisLines.iterator(),
                new LineExecutor.Inline(),       // lines are already-evaluated K=V
                topK,
                goals,
                policy,
                new AnalysisListener() {});      // all methods default → no-op

        System.out.println(snap.render());

        // STEP 39: provenance + non-dominance explanation — a VERSIONED JSON report
        // tracing every selected (Pareto) candidate back to its source/result row.
        // In FORMAL mode a provenance error (missing candidate/run id) fails the run.
        ObjectNode prov = ProvenanceReport.build(snap, goals, mode == AnalysisMode.FORMAL);
        boolean provOk = prov.path("provenance_ok").asBoolean(true);
        int provIssues = prov.path("provenance_issues").size();
        String provJson = AnalyzerCore.mapper().writerWithDefaultPrettyPrinter().writeValueAsString(prov);
        if (provenanceOut != null) {
            Path tmp = Path.of(provenanceOut + ".tmp");
            Files.writeString(tmp, provJson);
            Files.move(tmp, Path.of(provenanceOut), java.nio.file.StandardCopyOption.REPLACE_EXISTING,
                    java.nio.file.StandardCopyOption.ATOMIC_MOVE);
        }
        System.out.println("provenance: schema=" + ProvenanceReport.SCHEMA
                + " candidates=" + prov.path("candidates").size()
                + " issues=" + provIssues + " provenance_ok=" + provOk
                + (provenanceOut != null ? " -> " + provenanceOut : ""));
        if (mode == AnalysisMode.FORMAL && !provOk) {
            System.err.println("FORMAL provenance check FAILED: " + provIssues
                    + " issue(s) (missing candidate_id/run_id on selected candidates)");
            System.exit(3);
        }
        if (seedOut != null) {
            BundleSeed seed = BundleSeed.fromSnapshot(snap, seedSourceRunId);
            Path tmp = Path.of(seedOut + ".tmp");
            seed.writeToFile(tmp);
            Files.move(tmp, Path.of(seedOut), java.nio.file.StandardCopyOption.REPLACE_EXISTING,
                    java.nio.file.StandardCopyOption.ATOMIC_MOVE);
            System.out.println("seed: winners=" + seed.size()
                    + " distinctLineNos=" + seed.distinctLineNos().size()
                    + " metrics=" + seed.declaredMetrics.size()
                    + " -> " + seedOut);
        }
    }
}
