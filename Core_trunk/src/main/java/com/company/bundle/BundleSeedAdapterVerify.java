package com.company.bundle;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.OptionalDouble;

/**
 * Tier-3.5 Core-side verifier: confirms {@link BundleSeedAdapter} parses the
 * canonical BundleSeed JSON schema (produced by the Analyzer's
 * {@code com.yurii.analyzer.core.optimization.BundleSeed.toJson()}) into
 * usable accessors.
 *
 * <p>This is the schema contract between Analyzer and Core for closed-loop
 * Master mode.  The JSON literal below mirrors what
 * {@code BundleSeed.writeToFile(path)} would emit on the Analyzer side; any
 * future Analyzer schema change that doesn't update this literal will fail
 * here, surfacing the drift before it bites in production.</p>
 *
 *   Run:  java -cp ... BundleSeedAdapterVerify
 */
public final class BundleSeedAdapterVerify {
    private BundleSeedAdapterVerify() {}

    /** Canonical sample seed — three pareto winners, two per-metric champions,
     *  one balanced pick, plus observedRanges for two metrics. */
    private static final String SAMPLE_SEED_JSON = String.join("\n",
            "{",
            "  \"schemaVersion\": 1,",
            "  \"generatedAtEpochMs\": 1747200000000,",
            "  \"sourceRunId\": \"verify-run-001\",",
            "  \"totalCandidatesObserved\": 8,",
            "  \"declaredMetrics\": [\"cost\", \"latency\"],",
            "  \"observedRanges\": {",
            "    \"cost\":    { \"key\": \"cost\",    \"n\": 8, \"min\": 0.10, \"max\": 0.99, \"mean\": 0.55, \"stdev\": 0.30 },",
            "    \"latency\": { \"key\": \"latency\", \"n\": 8, \"min\": 2.0,  \"max\": 9.0,  \"mean\": 5.5,  \"stdev\": 2.5  }",
            "  },",
            "  \"winners\": [",
            "    { \"lineNo\": 1, \"score\": 90.0, \"role\": \"pareto\",",
            "      \"kvPairs\": { \"cost\": \"0.10\", \"latency\": \"9.0\" }, \"crowdingDistance\": \"Infinity\" },",
            "    { \"lineNo\": 4, \"score\": 45.0, \"role\": \"pareto\",",
            "      \"kvPairs\": { \"cost\": \"0.55\", \"latency\": \"3.0\" }, \"crowdingDistance\": 0.75 },",
            "    { \"lineNo\": 5, \"score\": 20.0, \"role\": \"pareto\",",
            "      \"kvPairs\": { \"cost\": \"0.80\", \"latency\": \"2.0\" }, \"crowdingDistance\": \"Infinity\" },",
            "    { \"lineNo\": 1, \"score\": 90.0, \"role\": \"champion-min:cost\",",
            "      \"kvPairs\": { \"cost\": \"0.10\", \"latency\": \"9.0\" }, \"crowdingDistance\": null },",
            "    { \"lineNo\": 5, \"score\": 20.0, \"role\": \"champion-max:throughput\",",
            "      \"kvPairs\": { \"cost\": \"0.80\", \"latency\": \"2.0\", \"throughput\": \"4500\" }, \"crowdingDistance\": null },",
            "    { \"lineNo\": 3, \"score\": 60.0, \"role\": \"balanced:tchebycheff\",",
            "      \"kvPairs\": { \"cost\": \"0.40\", \"latency\": \"5.0\" }, \"crowdingDistance\": null }",
            "  ]",
            "}");

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testParseInline();
        failures += testFileRoundTrip();
        failures += testForwardCompatibility();
        failures += testNumericCoercion();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL BUNDLE-SEED-ADAPTER CHECKS PASSED");
        else { System.out.println("❌ " + failures + " BUNDLE-SEED-ADAPTER CHECK(S) FAILED"); System.exit(1); }
    }

    private static int testParseInline() throws Exception {
        System.out.println("── parse canonical sample JSON ──");
        BundleSeedAdapter seed = BundleSeedAdapter.parseJson(SAMPLE_SEED_JSON);

        int f = 0;
        f += assertCond("schemaVersion == 1",            seed.schemaVersion == 1);
        f += assertCond("sourceRunId == verify-run-001", "verify-run-001".equals(seed.sourceRunId));
        f += assertCond("totalCandidatesObserved == 8",  seed.totalCandidatesObserved == 8);

        f += assertCond("declaredMetrics has 'cost' + 'latency'",
                seed.declaredMetrics.contains("cost") && seed.declaredMetrics.contains("latency"));

        f += assertCond("observedRanges has 'cost' min/max",
                seed.observedRange("cost").isPresent()
                && Math.abs(seed.observedRange("cost").get().min - 0.10) < 1e-9
                && Math.abs(seed.observedRange("cost").get().max - 0.99) < 1e-9);

        // Winner counts
        f += assertCond("6 winners total", seed.winnerCount() == 6);
        f += assertCond("3 distinct lineNos (1, 3, 4, 5 — one repeats)",
                seed.distinctLineNos().size() == 4);

        List<BundleSeedAdapter.Winner> pareto =  seed.winnersWithRolePrefix("pareto");
        List<BundleSeedAdapter.Winner> champ =   seed.winnersWithRolePrefix("champion-");
        List<BundleSeedAdapter.Winner> balanced = seed.winnersWithRolePrefix("balanced:");
        f += assertCond("3 pareto winners",        pareto.size() == 3);
        f += assertCond("2 champion winners",      champ.size() == 2);
        f += assertCond("1 balanced winner",       balanced.size() == 1);

        // Crowding distance — first pareto winner is +∞ boundary
        BundleSeedAdapter.Winner first = pareto.get(0);
        f += assertCond("first pareto winner has +∞ crowding",
                Double.isInfinite(first.crowdingDistance) && first.crowdingDistance > 0);
        // Interior winner has finite crowding
        BundleSeedAdapter.Winner interior = pareto.get(1);
        f += assertCond("interior pareto winner has finite crowding (0.75)",
                Math.abs(interior.crowdingDistance - 0.75) < 1e-9);
        // Champion winners → null crowding → NaN
        f += assertCond("champion winner crowding parsed as NaN (null in JSON)",
                Double.isNaN(champ.get(0).crowdingDistance));

        // Winners-by-metric filter
        f += assertCond("winnersForMetric('throughput') returns the 1 winner that carries it",
                seed.winnersForMetric("throughput").size() == 1);
        f += assertCond("winnersForMetric('cost') returns all 6 winners (every kvPairs has cost)",
                seed.winnersForMetric("cost").size() == 6);

        // Numeric coercion through Winner.numericValue
        OptionalDouble cost1 = pareto.get(0).numericValue("cost");
        f += assertCond("Winner.numericValue('cost') for lineNo=1 returns 0.10",
                cost1.isPresent() && Math.abs(cost1.getAsDouble() - 0.10) < 1e-9);
        return f;
    }

    private static int testFileRoundTrip() throws Exception {
        System.out.println("\n── file round-trip ──");
        Path tmp = Files.createTempFile("bundleseed_adapter_", ".json");
        Files.writeString(tmp, SAMPLE_SEED_JSON);
        BundleSeedAdapter seed = BundleSeedAdapter.loadFromFile(tmp);
        int f = 0;
        f += assertCond("loadFromFile yields same winner count as inline parse",
                seed.winnerCount() == 6);
        f += assertCond("loadFromFile preserves sourceRunId",
                "verify-run-001".equals(seed.sourceRunId));
        Files.deleteIfExists(tmp);
        return f;
    }

    /** Forward compatibility: unknown top-level keys + a higher schemaVersion
     *  must be tolerated.  Future Analyzer builds will add fields; old Core
     *  builds must keep parsing. */
    private static int testForwardCompatibility() throws Exception {
        System.out.println("\n── forward-compat: unknown keys tolerated ──");
        String unknownish = "{"
                + "\"schemaVersion\": 99,"
                + "\"newField\": {\"a\": 1, \"b\": [1, 2, 3]},"
                + "\"sourceRunId\": \"future-001\","
                + "\"winners\": ["
                + "  {\"lineNo\": 7, \"score\": 1.5, \"role\": \"pareto\","
                + "   \"kvPairs\": {\"x\": \"42\"}, \"crowdingDistance\": null,"
                + "   \"futureWinnerField\": \"ignored\" }"
                + "]"
                + "}";
        BundleSeedAdapter seed = BundleSeedAdapter.parseJson(unknownish);
        int f = 0;
        f += assertCond("schemaVersion=99 parsed",         seed.schemaVersion == 99);
        f += assertCond("sourceRunId preserved",           "future-001".equals(seed.sourceRunId));
        f += assertCond("1 winner parsed despite unknown fields",
                seed.winnerCount() == 1);
        f += assertCond("winner kvPairs intact (futureWinnerField ignored)",
                seed.winners.get(0).kvPairs.get("x").equals("42"));
        return f;
    }

    /** BundleSeedAdapter.parseNumeric must mirror AnalyzerCore.tryParseNumeric
     *  on the common cases — unit suffixes, percent, plain numbers.  Anchor a
     *  few values to prevent silent drift. */
    private static int testNumericCoercion() {
        System.out.println("\n── numeric coercion (unit suffixes) ──");
        int f = 0;
        f += assertCond("'0.5'   → 0.5",
                check(BundleSeedAdapter.parseNumeric("0.5"), 0.5));
        f += assertCond("'50ms'  → 0.05",
                check(BundleSeedAdapter.parseNumeric("50ms"), 0.05));
        f += assertCond("'5%'    → 0.05",
                check(BundleSeedAdapter.parseNumeric("5%"), 0.05));
        f += assertCond("'1.2MiB'→ 1258291.2",
                check(BundleSeedAdapter.parseNumeric("1.2MiB"), 1258291.2));
        f += assertCond("'abc'   → empty (no number)",
                BundleSeedAdapter.parseNumeric("abc").isEmpty());
        f += assertCond("'foo=42 bar' → 42 (first-substring fallback)",
                check(BundleSeedAdapter.parseNumeric("foo=42 bar"), 42.0));
        return f;
    }

    private static boolean check(OptionalDouble od, double expected) {
        return od.isPresent() && Math.abs(od.getAsDouble() - expected) < 1e-6;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    @SuppressWarnings("unused")
    private static String fmt(Map<String, ?> m) {
        return m == null ? "(null)" : m.toString();
    }

    @SuppressWarnings("unused")
    private static String fmt(double d) {
        return String.format(Locale.ROOT, "%.4g", d);
    }
}
