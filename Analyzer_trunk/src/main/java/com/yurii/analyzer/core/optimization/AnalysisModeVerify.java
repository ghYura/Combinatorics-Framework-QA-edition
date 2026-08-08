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

import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.AnalysisListener;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;
import com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * STEP 38 — verifies the FORMAL vs EXPLORATORY analysis-mode split on a
 * secure-pipeline-shaped metrics corpus, with NO Executor rerun (a static K=V
 * corpus). Asserts the three acceptance criteria:
 *
 *   1. {@code security_failures:max} stays MAX in formal mode even though lexical
 *      inference would say min ("fail" → minimize) — and the disagreement is
 *      surfaced by {@link AnalysisMode#directionConflicts}, never silently flipped.
 *   2. An auto-discovered failure/cost axis ({@code db_ms}) does NOT change the
 *      formal Pareto front (DECLARED_ONLY ignores it) — proven by the formal
 *      front being identical with vs without the {@code db_ms} column, while the
 *      EXPLORATORY front (which folds {@code db_ms} in) genuinely differs.
 *   3. The exploratory report lists the inferred goal ({@code db_ms}) as an
 *      auto-discovered axis, labelled "(inferred)".
 *
 * Plus the formal-mode contract: explicit goals + a matching corpus count are
 * required (fail closed).
 *
 * Run:  java -cp target/classes:&lt;deps&gt;
 *             com.yurii.analyzer.core.optimization.AnalysisModeVerify
 */
public final class AnalysisModeVerify {
    private AnalysisModeVerify() {}

    private static final Pattern ID = Pattern.compile("id=(\\S+)");

    public static void main(String[] args) throws Exception {
        int failures = 0;

        // ─── secure-pipeline-shaped corpus ──────────────────────────────────
        // declared axes: security_failures (MAX — finding failures is the goal),
        // latency_ms (MIN), coverage (MAX). Undeclared auto axis: db_ms (cost).
        // Data is built so c4 is Pareto-optimal ONLY once db_ms is considered:
        // formal (db_ms ignored) front = {c0,c1,c2,c3}; exploratory front adds c4.
        String[] withDb = {
            "id=c0 security_failures=10 latency_ms=5  coverage=0.90 db_ms=100",
            "id=c1 security_failures=8  latency_ms=3  coverage=0.80 db_ms=10",
            "id=c2 security_failures=5  latency_ms=2  coverage=0.95 db_ms=5",
            "id=c3 security_failures=12 latency_ms=8  coverage=0.70 db_ms=200",
            "id=c4 security_failures=6  latency_ms=4  coverage=0.60 db_ms=2",
            "id=c5 security_failures=3  latency_ms=10 coverage=0.50 db_ms=300",
        };
        List<String> corpusWith = List.of(withDb);
        List<String> corpusWithout = new ArrayList<>();
        for (String s : withDb) corpusWithout.add(s.replaceAll("\\s*db_ms=\\S+", ""));

        List<GoalSpec> formalGoals = List.of(
                GoalSpec.max("security_failures"), GoalSpec.min("latency_ms"), GoalSpec.max("coverage"));

        // ─── FORMAL mode ────────────────────────────────────────────────────
        Snapshot formal = analyze(corpusWith, formalGoals,
                AnalysisMode.FORMAL.discoveryPolicy(DiscoveryPolicy.DEFAULT));
        Snapshot formalNoDb = analyze(corpusWithout, formalGoals,
                AnalysisMode.FORMAL.discoveryPolicy(DiscoveryPolicy.DEFAULT));

        // (1) security_failures stays MAX
        failures += assertCond("formal: security_failures is MAXIMIZE (not flipped to min by inference)",
                modeOf(formal.effectiveGoals(), "security_failures") == GoalSpec.Mode.MAXIMIZE);
        // no auto axis added in formal
        Set<String> formalKeys = keys(formal.effectiveGoals());
        failures += assertCond("formal: effective goals are exactly the 3 declared (no auto db_ms axis)",
                formalKeys.equals(new LinkedHashSet<>(List.of("security_failures", "latency_ms", "coverage"))));
        failures += assertCond("formal: db_ms NOT folded into the objectives",
                !formalKeys.contains("db_ms"));

        // (2) auto axis does not change the formal front
        Set<String> frontWith = frontIds(formal);
        Set<String> frontWithout = frontIds(formalNoDb);
        failures += assertCond("formal: front identical with vs without the db_ms column "
                        + frontWith + " == " + frontWithout,
                frontWith.equals(frontWithout));

        // ─── EXPLORATORY mode ───────────────────────────────────────────────
        Snapshot exploratory = analyze(corpusWith, formalGoals,
                AnalysisMode.EXPLORATORY.discoveryPolicy(DiscoveryPolicy.DEFAULT));
        Set<String> exploreKeys = keys(exploratory.effectiveGoals());
        // (3) inferred goal listed + labelled
        failures += assertCond("exploratory: db_ms auto-discovered into the objectives",
                exploreKeys.contains("db_ms"));
        failures += assertCond("exploratory: db_ms is inferred, not declared",
                !exploratory.declaredKeys().contains("db_ms"));
        String report = exploratory.render();
        failures += assertCond("exploratory report lists the auto-discovered axis db_ms as '(inferred)'",
                report.contains("Auto-discovered axes") && report.contains("db_ms") && report.contains("(inferred)"));

        // the auto axis genuinely matters (test isn't vacuous): exploratory front differs
        Set<String> exploreFront = frontIds(exploratory);
        failures += assertCond("auto axis is load-bearing: exploratory front " + exploreFront
                        + " differs from formal front " + frontWith + " (c4 enters only via db_ms)",
                !exploreFront.equals(frontWith) && exploreFront.contains("c4") && !frontWith.contains("c4"));

        // ─── direction-conflict surfacing (action #4) ───────────────────────
        List<String> conflicts = AnalysisMode.directionConflicts(formalGoals);
        failures += assertCond("direction conflict surfaced for security_failures (explicit max vs inferred min)",
                conflicts.stream().anyMatch(c -> c.startsWith("security_failures") && c.contains("MAXIMIZE")));
        failures += assertCond("no spurious conflicts for latency_ms/coverage (both agree with inference)",
                conflicts.size() == 1);

        // ─── FORMAL contract: fail closed ───────────────────────────────────
        failures += assertThrows("formal mode rejects empty goals",
                () -> AnalysisMode.FORMAL.validate(List.of(), 6));
        failures += assertThrows("formal mode rejects a missing corpus count",
                () -> AnalysisMode.FORMAL.validate(formalGoals, null));
        failures += assertThrows("formal mode rejects a non-positive corpus count",
                () -> AnalysisMode.FORMAL.validate(formalGoals, 0));
        failures += assertNoThrow("formal mode accepts explicit goals + positive corpus count",
                () -> AnalysisMode.FORMAL.validate(formalGoals, 6));
        failures += assertNoThrow("exploratory mode accepts no goals + no corpus count",
                () -> AnalysisMode.EXPLORATORY.validate(List.of(), null));
        failures += assertCond("fromText parses formal/exploratory",
                AnalysisMode.fromText("formal") == AnalysisMode.FORMAL
                && AnalysisMode.fromText("exploratory") == AnalysisMode.EXPLORATORY
                && AnalysisMode.fromText(null) == AnalysisMode.EXPLORATORY);

        if (failures == 0) System.out.println("✅ ALL ANALYSIS-MODE CHECKS PASSED");
        else { System.out.println("❌ " + failures + " ANALYSIS-MODE CHECK(S) FAILED"); System.exit(1); }
    }

    // ── helpers ──────────────────────────────────────────────────────────── //
    private static Snapshot analyze(List<String> corpus, List<GoalSpec> goals, DiscoveryPolicy policy) throws Exception {
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                AnalyzerCore.parseManualConfig("{}"),
                1, 12, 30.0, 10.0, false, 0.0, false);
        return analyzer.analyzeStream(corpus.iterator(), new LineExecutor.Inline(),
                12, goals, policy, new AnalysisListener() {});
    }

    private static Set<String> keys(List<GoalSpec> goals) {
        Set<String> s = new LinkedHashSet<>();
        for (GoalSpec g : goals) s.add(g.key());
        return s;
    }

    private static GoalSpec.Mode modeOf(List<GoalSpec> goals, String key) {
        for (GoalSpec g : goals) if (g.key().equals(key)) return g.mode();
        return null;
    }

    private static Set<String> frontIds(Snapshot snap) {
        Set<String> ids = new LinkedHashSet<>();
        for (LineResult r : snap.paretoFront()) {
            Matcher m = ID.matcher(r.originalLine == null ? "" : r.originalLine);
            if (m.find()) ids.add(m.group(1));
        }
        return ids;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static int assertThrows(String label, Runnable r) {
        try { r.run(); }
        catch (RuntimeException ex) { return assertCond(label + " (threw: " + ex.getMessage() + ")", true); }
        return assertCond(label + " (did NOT throw)", false);
    }

    private static int assertNoThrow(String label, Runnable r) {
        try { r.run(); return assertCond(label, true); }
        catch (RuntimeException ex) { return assertCond(label + " (threw: " + ex.getMessage() + ")", false); }
    }
}
