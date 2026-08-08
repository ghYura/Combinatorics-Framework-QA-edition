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

package com.company.bundle;

import com.company.config.AppConfig;
import com.company.excel.JsonScheduleParser;
import com.company.excel.ParsedWorkbook;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Tier-3.5 Option B MVP verifier — exercises the pluggable mutator end-to-end:
 *
 * <ol>
 *   <li>Synthetic workbook JSON (minimal HEAD / COST / LAT / ROW schedule
 *       mirroring {@code UniversalInputParityVerify}'s fixture).</li>
 *   <li>Synthetic BundleSeed JSON (5 Pareto winners + 1 champion-min +
 *       1 balanced pick) — schema-compatible with the Analyzer's
 *       {@code BundleSeed.toJson()}.</li>
 *   <li>{@link ElitismStrategy} default → all winners injected as
 *       {@code Seed_<lineNo>_<role>} sheets.</li>
 *   <li>Asserts: mutated JSON parseable via {@link JsonScheduleParser},
 *       Seed_* sheets present, cell content matches winner K=V row,
 *       provenance metadata block populated, idempotency (re-run = no-op
 *       additions).</li>
 *   <li>Role-prefix filter case: only {@code "pareto"} winners are injected.</li>
 *   <li>NoopStrategy passthrough sanity.</li>
 * </ol>
 *
 *   Run:  java -cp ... WorkbookMutatorVerify
 */
public final class WorkbookMutatorVerify {
    private WorkbookMutatorVerify() {}

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final String SCENARIO_JSON = "{"
            + "\"sheets\":{"
            + "  \"FW_Seq\":[\n"
            + "    [\"HEAD\",\"FW_Exclude\",\"FW_Reuse\",\"FW_Combi(1)\",\"FW_Combi(1)\"],\n"
            + "    [\"COST\",\"FW_Exclude\",\"FW_Reuse\",\"FW_Combi(1)\",\"FW_Combi(1)\"],\n"
            + "    [\"LAT\", \"FW_Exclude\",\"FW_Reuse\",\"FW_Combi(1)\",\"FW_Combi(1)\"],\n"
            + "    [\"ROW\",null,null,\"FW_(HEAD,,COST,,LAT,,ROW,,M:N)\"]\n"
            + "  ],"
            + "  \"FW_SheetNames\":[\n"
            + "    [\"HEAD\",\"FW_EMPTY_STRING\",\"FW_EMPTY_STRING\"],\n"
            + "    [\"COST\",\"FW_EMPTY_STRING\",\"FW_EMPTY_STRING\"],\n"
            + "    [\"LAT\", \"FW_EMPTY_STRING\",\"FW_EMPTY_STRING\"],\n"
            + "    [\"ROW\", \"FW_EMPTY_STRING\",\"FW_EMPTY_STRING\"]\n"
            + "  ],"
            + "  \"HEAD\":[[\"scenario=demo\"]],"
            + "  \"COST\":[[\" cost=0.10\"],[\" cost=0.30\"],[\" cost=0.50\"]],"
            + "  \"LAT\": [[\" latency=10ms\"],[\" latency=30ms\"],[\" latency=80ms\"]],"
            + "  \"ROW\": [[\"FW_EMPTY_STRING\"]]"
            + "}}";

    private static final String SEED_JSON = "{"
            + "\"schemaVersion\":1,"
            + "\"generatedAtEpochMs\":1747200000000,"
            + "\"sourceRunId\":\"verify-elitism\","
            + "\"totalCandidatesObserved\":8,"
            + "\"declaredMetrics\":[\"cost\",\"latency\"],"
            + "\"observedRanges\":{"
            + "  \"cost\":{\"key\":\"cost\",\"n\":8,\"min\":0.10,\"max\":0.99,\"mean\":0.55,\"stdev\":0.30},"
            + "  \"latency\":{\"key\":\"latency\",\"n\":8,\"min\":2.0,\"max\":9.0,\"mean\":5.5,\"stdev\":2.5}"
            + "},"
            + "\"winners\":["
            + "  {\"lineNo\":1,\"score\":90.0,\"role\":\"pareto\","
            + "   \"kvPairs\":{\"cost\":\"0.10\",\"latency\":\"9.0\"},\"crowdingDistance\":\"Infinity\"},"
            + "  {\"lineNo\":2,\"score\":70.0,\"role\":\"pareto\","
            + "   \"kvPairs\":{\"cost\":\"0.25\",\"latency\":\"7.0\"},\"crowdingDistance\":0.75},"
            + "  {\"lineNo\":4,\"score\":45.0,\"role\":\"pareto\","
            + "   \"kvPairs\":{\"cost\":\"0.55\",\"latency\":\"3.0\"},\"crowdingDistance\":0.75},"
            + "  {\"lineNo\":5,\"score\":20.0,\"role\":\"pareto\","
            + "   \"kvPairs\":{\"cost\":\"0.80\",\"latency\":\"2.0\"},\"crowdingDistance\":\"Infinity\"},"
            + "  {\"lineNo\":1,\"score\":90.0,\"role\":\"champion-min:cost\","
            + "   \"kvPairs\":{\"cost\":\"0.10\",\"latency\":\"9.0\"},\"crowdingDistance\":null},"
            + "  {\"lineNo\":3,\"score\":60.0,\"role\":\"balanced:tchebycheff\","
            + "   \"kvPairs\":{\"cost\":\"0.40\",\"latency\":\"5.0\"},\"crowdingDistance\":null}"
            + "]"
            + "}";

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testElitismFullRoundTrip();
        failures += testRolePrefixFilter();
        failures += testIdempotency();
        failures += testNoopPassthrough();
        failures += testMutateJsonFile();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL WORKBOOK-MUTATOR CHECKS PASSED");
        else { System.out.println("❌ " + failures + " WORKBOOK-MUTATOR CHECK(S) FAILED"); System.exit(1); }
    }

    /** Default ElitismStrategy injects all 6 winners; mutated workbook is
     *  parseable; Seed_* sheets carry the expected K=V rows. */
    private static int testElitismFullRoundTrip() throws Exception {
        System.out.println("── ElitismStrategy full round-trip ──");
        ObjectNode root = (ObjectNode) MAPPER.readTree(SCENARIO_JSON);
        BundleSeedAdapter seed = BundleSeedAdapter.parseJson(SEED_JSON);

        String summary = WorkbookMutator.mutateInMemory(root, seed, new ElitismStrategy());
        int f = 0;
        f += assertCond("summary mentions 6 winners",
                summary.contains("added 6") && summary.contains("6 total winners"));

        ObjectNode sheets = (ObjectNode) root.get("sheets");
        Set<String> sheetNames = new LinkedHashSet<>();
        sheets.fieldNames().forEachRemaining(sheetNames::add);

        // Existing schedule sheets preserved
        f += assertCond("original FW_Seq preserved",     sheetNames.contains("FW_Seq"));
        f += assertCond("original HEAD/COST/LAT/ROW preserved",
                sheetNames.contains("HEAD") && sheetNames.contains("COST")
                && sheetNames.contains("LAT")  && sheetNames.contains("ROW"));

        // Six Seed_* sheets injected
        long seedSheetCount = sheetNames.stream().filter(s -> s.startsWith("Seed_")).count();
        f += assertCond("6 Seed_* sheets injected (one per winner)", seedSheetCount == 6);

        // Spot-check content of one well-known sheet — line#1 / pareto
        JsonNode pareto1 = sheets.get("Seed_1_pareto");
        f += assertCond("Seed_1_pareto present", pareto1 != null && pareto1.isArray());
        if (pareto1 != null && pareto1.isArray() && pareto1.size() > 0) {
            JsonNode row = pareto1.get(0);
            f += assertCond("Seed_1_pareto row[0] is array of 1 cell",
                    row.isArray() && row.size() == 1);
            String cell = row.get(0).asText("");
            f += assertCond("cell encodes cost=0.10 latency=9.0",
                    cell.contains("cost=0.10") && cell.contains("latency=9.0"));
        }

        // Provenance metadata block present
        JsonNode meta = root.get("_bundleMeta");
        f += assertCond("_bundleMeta block present after mutateInMemory? (only via mutateJsonFile path)",
                meta == null);  // mutateInMemory does NOT add provenance; only file path does

        // Sanity: re-parse the mutated workbook via JsonScheduleParser — must succeed.
        // Seed_* sheets are non-FW_ → routed to shortSheetHM (data sheets);
        // original HEAD/COST/LAT/ROW also data → expect 4 + 6 = 10 entries.
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");
        String mutatedJson = MAPPER.writeValueAsString(root);
        ParsedWorkbook reparsed = new JsonScheduleParser().parseJson(mutatedJson, wbCfg, "elitism:mutated");
        f += assertCond("mutated JSON re-parseable via JsonScheduleParser",
                reparsed != null);
        f += assertCond("re-parsed workbook has 10 data sheets (4 original + 6 Seed_*)",
                reparsed != null && reparsed.shortSheetHM.size() == 10);
        // Spot-check: pick one of the injected sheet names and confirm it's in the data map
        boolean foundSeedSheet = false;
        if (reparsed != null) {
            for (var name : reparsed.shortStringSheetKey2SheetNameHM.values()) {
                if (name != null && name.startsWith("Seed_")) { foundSeedSheet = true; break; }
            }
        }
        f += assertCond("at least one Seed_* sheet present in shortStringSheetKey2SheetNameHM",
                foundSeedSheet);
        return f;
    }

    /** rolePrefixFilter="pareto" → only 4 Pareto winners injected. */
    private static int testRolePrefixFilter() throws Exception {
        System.out.println("\n── ElitismStrategy with role-prefix filter ──");
        ObjectNode root = (ObjectNode) MAPPER.readTree(SCENARIO_JSON);
        BundleSeedAdapter seed = BundleSeedAdapter.parseJson(SEED_JSON);

        ElitismStrategy paretoOnly = new ElitismStrategy("Seed_", "pareto", true);
        String summary = WorkbookMutator.mutateInMemory(root, seed, paretoOnly);

        ObjectNode sheets = (ObjectNode) root.get("sheets");
        long seedSheetCount = countSeedSheets(sheets);
        int f = 0;
        f += assertCond("4 pareto-role winners injected (champions/balanced filtered out)",
                seedSheetCount == 4);
        f += assertCond("summary mentions filtered-out count = 2 (champion + balanced)",
                summary.contains("filtered out 2"));
        return f;
    }

    /** Re-running ElitismStrategy on its own output adds 0 new sheets. */
    private static int testIdempotency() throws Exception {
        System.out.println("\n── ElitismStrategy idempotency ──");
        ObjectNode root = (ObjectNode) MAPPER.readTree(SCENARIO_JSON);
        BundleSeedAdapter seed = BundleSeedAdapter.parseJson(SEED_JSON);

        ElitismStrategy strat = new ElitismStrategy();
        WorkbookMutator.mutateInMemory(root, seed, strat);
        long countAfter1 = countSeedSheets((ObjectNode) root.get("sheets"));
        String secondSummary = WorkbookMutator.mutateInMemory(root, seed, strat);
        long countAfter2 = countSeedSheets((ObjectNode) root.get("sheets"));

        int f = 0;
        f += assertCond("first run injected 6 sheets",   countAfter1 == 6);
        f += assertCond("second run added 0 sheets (idempotent)",
                countAfter2 == 6);
        f += assertCond("second-run summary mentions 6 already-present",
                secondSummary.contains("skipped 6"));
        return f;
    }

    /** NoopStrategy leaves the workbook untouched. */
    private static int testNoopPassthrough() throws Exception {
        System.out.println("\n── NoopStrategy passthrough ──");
        ObjectNode root = (ObjectNode) MAPPER.readTree(SCENARIO_JSON);
        Set<String> beforeNames = new LinkedHashSet<>();
        root.get("sheets").fieldNames().forEachRemaining(beforeNames::add);

        BundleSeedAdapter seed = BundleSeedAdapter.parseJson(SEED_JSON);
        String summary = WorkbookMutator.mutateInMemory(root, seed, new NoopStrategy());

        Set<String> afterNames = new LinkedHashSet<>();
        root.get("sheets").fieldNames().forEachRemaining(afterNames::add);
        int f = 0;
        f += assertCond("Noop strategy preserves sheet set identical",
                beforeNames.equals(afterNames));
        f += assertCond("Noop summary signals passthrough",
                summary.contains("unchanged"));
        return f;
    }

    /** File-level path: write inputs, invoke mutateJsonFile, confirm output
     *  contains provenance + applied mutations.  Re-parse via JsonScheduleParser
     *  as the final integrity check. */
    private static int testMutateJsonFile() throws Exception {
        System.out.println("\n── WorkbookMutator.mutateJsonFile (file → file) ──");
        Path inputJson  = Files.createTempFile("mutator_in_",  ".json");
        Path seedJson   = Files.createTempFile("mutator_seed_", ".json");
        Path outputJson = Files.createTempFile("mutator_out_", ".json");
        Files.writeString(inputJson, SCENARIO_JSON, StandardCharsets.UTF_8);
        Files.writeString(seedJson,  SEED_JSON,     StandardCharsets.UTF_8);

        String summary = WorkbookMutator.mutateJsonFile(
                inputJson, seedJson, outputJson, new ElitismStrategy());

        int f = 0;
        f += assertCond("output file written", Files.exists(outputJson) && Files.size(outputJson) > 0);

        JsonNode outRoot = MAPPER.readTree(Files.readString(outputJson));
        JsonNode meta = outRoot.get("_bundleMeta");
        f += assertCond("output carries _bundleMeta provenance block",
                meta != null && meta.isObject());
        f += assertCond("_bundleMeta.lastMutationStrategy='Elitism'",
                meta != null && "Elitism".equals(meta.path("lastMutationStrategy").asText()));
        f += assertCond("_bundleMeta.seedSourceRunId='verify-elitism'",
                meta != null && "verify-elitism".equals(meta.path("seedSourceRunId").asText()));
        f += assertCond("_bundleMeta.seedWinnerCount=6",
                meta != null && meta.path("seedWinnerCount").asInt(-1) == 6);

        // Final integrity check: file is a valid schedule.
        // After ElitismStrategy: 4 original data sheets + 6 Seed_* data sheets
        // = 10 data sheets total in shortSheetHM.
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");
        ParsedWorkbook pw = new JsonScheduleParser().parse(outputJson, wbCfg);
        f += assertCond("output file parses as a valid ParsedWorkbook (10 data sheets)",
                pw != null && pw.shortSheetHM.size() == 10);

        Files.deleteIfExists(inputJson);
        Files.deleteIfExists(seedJson);
        Files.deleteIfExists(outputJson);
        return f;
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private static long countSeedSheets(ObjectNode sheets) {
        if (sheets == null) return 0;
        long count = 0;
        var names = sheets.fieldNames();
        while (names.hasNext()) if (names.next().startsWith("Seed_")) count++;
        return count;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
