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
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * STEP 39 — verifies provenance + non-dominance explanation: every selected
 * (Pareto-front) candidate is traceable to a source/result row, the explanation
 * is deterministic, the formal JSON validates, and missing provenance is flagged
 * in formal mode. No Executor rerun — a static K=V corpus.
 *
 * Run:  java -cp target/classes:&lt;deps&gt;
 *             com.yurii.analyzer.core.optimization.ProvenanceExplanationVerify
 */
public final class ProvenanceExplanationVerify {
    private ProvenanceExplanationVerify() {}

    private static final List<GoalSpec> GOALS =
            List.of(GoalSpec.min("latency_ms"), GoalSpec.min("overcharge_cents"));

    // Secure-pipeline-shaped corpus. A = explicit provenance (candidate_id +
    // source_ref); B/C = derived from dimensions; M = metrics-only (NO id, NO
    // dimensions → missing provenance) and the strict latency champion so it is
    // on the front; D + extras are dominated.
    // Every line carries run_id (so the run_id formal policy is satisfied here — it
    // is exercised by the end-to-end stage test instead); this verifier isolates the
    // candidate_id / derived / missing-id policy.
    private static final List<String> CORPUS = List.of(
        "run_id=run_demo candidate_id=cand_A source_ref=candidates/cand_A.py mode=fast region=us latency_ms=1.0 overcharge_cents=5 FW_VAR=0",
        "run_id=run_demo mode=safe region=eu latency_ms=3.0 overcharge_cents=0 FW_VAR=0",
        "run_id=run_demo mode=mixed region=us latency_ms=2.0 overcharge_cents=2 FW_VAR=1",
        "run_id=run_demo latency_ms=0.5 overcharge_cents=8 FW_VAR=0",
        "run_id=run_demo mode=slow region=eu latency_ms=5.0 overcharge_cents=10 FW_VAR=0",
        "run_id=run_demo mode=fast region=ap latency_ms=4.0 overcharge_cents=7 FW_VAR=1",
        "run_id=run_demo mode=safe region=us latency_ms=3.5 overcharge_cents=6 FW_VAR=0",
        "run_id=run_demo mode=mixed region=ap latency_ms=2.5 overcharge_cents=9 FW_VAR=0",
        "run_id=run_demo mode=slow region=us latency_ms=6.0 overcharge_cents=12 FW_VAR=1",
        "run_id=run_demo mode=fast region=eu latency_ms=4.5 overcharge_cents=11 FW_VAR=0");

    public static void main(String[] args) throws Exception {
        int failures = 0;

        ObjectNode explore = ProvenanceReport.build(run(CORPUS, GOALS), GOALS, /*formal*/ false);
        ObjectNode formal = ProvenanceReport.build(run(CORPUS, GOALS), GOALS, /*formal*/ true);

        // ── versioned schema + structure ────────────────────────────────────
        failures += assertCond("report carries the versioned schema analyzer.provenance/v1",
                ProvenanceReport.SCHEMA.equals(formal.path("schema").asText()));
        failures += assertCond("report has a candidates array + a goals array",
                formal.path("candidates").isArray() && formal.path("candidates").size() > 0
                        && formal.path("goals").isArray());

        JsonNode cands = formal.path("candidates");
        JsonNode A = find(cands, "cand_A");
        JsonNode M = findMissing(cands);

        // ── traceability: every selected candidate explainable ──────────────
        boolean allHaveRequiredFields = true;
        int tracedToRow = 0;
        for (JsonNode c : cands) {
            allHaveRequiredFields &= c.has("provenance") && c.has("objectives")
                    && c.has("reason_non_dominated") && c.has("dominated_by") && c.has("dominates")
                    && c.has("dimensions");
            if (!c.path("candidate_id").isNull() && !c.path("candidate_id").asText().isEmpty()) tracedToRow++;
        }
        failures += assertCond("every selected candidate carries the required explanation fields",
                allHaveRequiredFields);
        failures += assertCond("at least the explicit + derived candidates trace to a source/result row "
                        + "(" + tracedToRow + " of " + cands.size() + ")",
                tracedToRow >= cands.size() - 1);     // all but the deliberately-missing M

        // ── explicit vs derived provenance ──────────────────────────────────
        failures += assertCond("explicit candidate cand_A: provenance=explicit + source_ref present",
                A != null && "explicit".equals(A.path("provenance").asText())
                        && A.path("source_ref").asText().startsWith("candidates/"));
        boolean derivedSeen = false;
        for (JsonNode c : cands)
            if ("derived-from-dimensions".equals(c.path("provenance").asText())
                    && c.path("candidate_id").asText().startsWith("dim:")) derivedSeen = true;
        failures += assertCond("a derived-from-dimensions candidate has a dim: id (traceable to the combination)",
                derivedSeen);

        // ── outcome / objectives / reason ───────────────────────────────────
        failures += assertCond("explicit candidate carries objectives (latency_ms + overcharge_cents) + verdict",
                A != null && A.path("objectives").has("latency_ms") && A.path("objectives").has("overcharge_cents")
                        && A.path("outcome").asText().equals("pass"));
        // M is the strict latency champion → its reason names latency_ms
        failures += assertCond("non-dominance reason for the latency champion names latency_ms",
                M != null && M.path("reason_non_dominated").asText().contains("latency_ms")
                        && M.path("reason_non_dominated").asText().contains("champion"));

        // ── formal provenance policy ────────────────────────────────────────
        JsonNode issues = formal.path("provenance_issues");
        boolean missingError = false, derivedWarning = false;
        for (JsonNode is : issues) {
            if ("error".equals(is.path("level").asText())
                    && is.path("message").asText().contains("missing provenance")) missingError = true;
            if ("warning".equals(is.path("level").asText())) derivedWarning = true;
        }
        failures += assertCond("formal mode flags the metrics-only candidate as a MISSING-provenance ERROR",
                missingError && M != null && "missing".equals(M.path("provenance").asText()));
        failures += assertCond("formal mode flags derived (no explicit id) candidates as WARNINGs",
                derivedWarning);
        failures += assertCond("formal report marks provenance_ok=false when a selected candidate is unprovenanced",
                !formal.path("provenance_ok").asBoolean(true));
        failures += assertCond("exploratory report records NO provenance issues (policy is formal-only)",
                explore.path("provenance_issues").size() == 0);

        // ── determinism ─────────────────────────────────────────────────────
        String j1 = AnalyzerCore.mapper().writeValueAsString(ProvenanceReport.build(run(CORPUS, GOALS), GOALS, true));
        String j2 = AnalyzerCore.mapper().writeValueAsString(ProvenanceReport.build(run(CORPUS, GOALS), GOALS, true));
        failures += assertCond("explanation is deterministic across two independent analyzer runs",
                j1.equals(j2));

        // ── inspect 2–3 selected candidates ─────────────────────────────────
        System.out.println("\n  inspected selected candidates:");
        int shown = 0;
        for (JsonNode c : cands) {
            if (shown++ >= 3) break;
            System.out.printf("    • id=%-22s outcome=%-5s obj=%s  reason=%s%n",
                    c.path("candidate_id").asText("<null>"), c.path("outcome").asText("?"),
                    c.path("objectives"), c.path("reason_non_dominated").asText());
        }

        // ── optional: the existing on-disk pricing corpus (if present) ──────
        Path pricing = Path.of("..", "generator_trunk", "tryout_own", "pricing", "pricing_metrics.kv");
        if (Files.exists(pricing)) {
            List<String> real = new ArrayList<>();
            for (String ln : Files.readAllLines(pricing)) {
                String s = ln.strip();
                if (!s.isEmpty() && !s.startsWith("#")) real.add(s);
            }
            List<GoalSpec> g = List.of(GoalSpec.min("latency_ms"), GoalSpec.min("overcharge_cents"),
                    GoalSpec.min("price_err_cents"), GoalSpec.max("correct"));
            ObjectNode rep = ProvenanceReport.build(run(real, g), g, false);
            boolean allTraced = true;
            for (JsonNode c : rep.path("candidates"))
                allTraced &= !c.path("candidate_id").isNull() && !c.path("candidate_id").asText().isEmpty();
            failures += assertCond("real pricing corpus (" + real.size() + " lines): every front candidate "
                    + "traces to a result row via its dimensions", allTraced);
        } else {
            System.out.println("  ◌ on-disk pricing corpus not present — skipping real-corpus check");
        }

        if (failures == 0) System.out.println("✅ ALL PROVENANCE/EXPLANATION CHECKS PASSED");
        else { System.out.println("❌ " + failures + " PROVENANCE CHECK(S) FAILED"); System.exit(1); }
    }

    // ── helpers ──────────────────────────────────────────────────────────── //
    private static Snapshot run(List<String> corpus, List<GoalSpec> goals) throws Exception {
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 20, 30.0, 10.0, false, 0.0, false);
        return analyzer.analyzeStream(corpus.iterator(), new LineExecutor.Inline(),
                20, goals, DiscoveryPolicy.DECLARED_ONLY, new AnalysisListener() {});
    }

    private static JsonNode find(JsonNode cands, String id) {
        for (JsonNode c : cands) if (id.equals(c.path("candidate_id").asText())) return c;
        return null;
    }

    private static JsonNode findMissing(JsonNode cands) {
        for (JsonNode c : cands) if ("missing".equals(c.path("provenance").asText())) return c;
        return null;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
