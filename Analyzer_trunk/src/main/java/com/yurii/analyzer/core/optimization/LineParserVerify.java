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

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.OptimizationAnalyzer;

import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Verifies the new {@link LineParser} extension point end-to-end:
 *
 *   • KvLineParser (default) handles the original K=V format.
 *   • JsonLineParser handles `{ "cost": 0.5, ... }` rows, with flattening
 *     of nested objects and indexed arrays.
 *   • MultiParser falls back between formats.
 *   • The pluggable parser composes with the rest of the analyzer's
 *     optimization pipeline (auto-discovery + Pareto front + champions).
 *
 *   Run:  java -cp ... LineParserVerify
 */
public final class LineParserVerify {
    private LineParserVerify() {}

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testKvParser();
        failures += testJsonParser();
        failures += testCsvParser();
        failures += testMultiParserFallback();
        failures += testJsonEndToEnd();
        failures += testCsvEndToEnd();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL LINE-PARSER CHECKS PASSED");
        else { System.out.println("❌ " + failures + " LINE-PARSER CHECK(S) FAILED"); System.exit(1); }
    }

    private static int testKvParser() {
        System.out.println("── KvLineParser (default) ──");
        LineParser p = new LineParser.KvLineParser();
        Map<String, String> r = p.parse("operation=run cost=0.5 latency=12.4ms");
        int f = 0;
        f += assertCond("kv: 'cost' present + lower-cased",  "0.5".equals(r.get("cost")));
        f += assertCond("kv: 'operation' present",           "run".equals(r.get("operation")));
        f += assertCond("kv: 'latency' present + unit-suffix retained",
                "12.4ms".equals(r.get("latency")));
        return f;
    }

    private static int testJsonParser() {
        System.out.println("\n── JsonLineParser ──");
        LineParser p = new LineParser.JsonLineParser();
        Map<String, String> r = p.parse(
                "{ \"cost\": 0.5, \"latency\": 12.4, \"nested\": { \"throughput\": 1800 }, "
              + "\"samples\": [0.1, 0.2] }");
        int f = 0;
        f += assertCond("json: top-level 'cost' → 0.5",       "0.5".equals(r.get("cost")));
        f += assertCond("json: nested flattened to dot-path", "1800".equals(r.get("nested.throughput")));
        f += assertCond("json: array flattened with index",   "0.1".equals(r.get("samples.0")) && "0.2".equals(r.get("samples.1")));
        f += assertCond("json: non-JSON returns empty",       new LineParser.JsonLineParser().parse("plain text k=v").isEmpty());
        return f;
    }

    private static int testCsvParser() {
        System.out.println("\n── CsvLineParser ──");
        LineParser p = new LineParser.CsvLineParser("cost,latency,throughput");
        Map<String, String> r = p.parse("0.5, 12.4ms, 1800");
        int f = 0;
        f += assertCond("csv: 'cost' present",                      "0.5".equals(r.get("cost")));
        f += assertCond("csv: 'latency' present + unit retained",   "12.4ms".equals(r.get("latency")));
        f += assertCond("csv: 'throughput' present",                "1800".equals(r.get("throughput")));

        // Quoted cell containing delimiter is preserved as one cell.
        LineParser q = new LineParser.CsvLineParser("note,cost");
        Map<String, String> r2 = q.parse("\"a, b, c\",0.5");
        f += assertCond("csv: quoted cell with embedded comma → single cell",
                "a, b, c".equals(r2.get("note")) && "0.5".equals(r2.get("cost")));

        // No header → synthetic col_<i> keys.
        LineParser h = new LineParser.CsvLineParser();
        Map<String, String> r3 = h.parse("alpha,7,9.5");
        f += assertCond("csv: no-header → col_0 / col_1 / col_2 keys",
                "alpha".equals(r3.get("col_0")) && "7".equals(r3.get("col_1")) && "9.5".equals(r3.get("col_2")));

        // Non-CSV line (no delimiter, no header) → empty map so MultiParser
        // chaining works.
        f += assertCond("csv: line with no delimiter → empty (chain-safe)",
                new LineParser.CsvLineParser().parse("plain text k=v").isEmpty());
        return f;
    }

    private static int testMultiParserFallback() {
        System.out.println("\n── MultiParser (JSON → K=V fallback) ──");
        LineParser p = new LineParser.MultiParser(
                new LineParser.JsonLineParser(),
                new LineParser.KvLineParser());
        int f = 0;
        f += assertCond("multi: JSON row → JSON parser wins",
                "0.5".equals(p.parse("{\"cost\":0.5}").get("cost")));
        f += assertCond("multi: K=V row → KV parser fallback wins",
                "0.5".equals(p.parse("cost=0.5 throughput=1800").get("cost")));
        f += assertCond("multi: empty / unparseable → empty map",
                p.parse("just some text with no metrics").isEmpty());

        // CSV in the chain — JSON / KV fall through, CSV wins on the comma row.
        LineParser pcsv = new LineParser.MultiParser(
                new LineParser.JsonLineParser(),
                new LineParser.KvLineParser(),
                new LineParser.CsvLineParser("cost,latency,throughput"));
        f += assertCond("multi: CSV row → CSV parser wins after JSON/KV fall through",
                "0.5".equals(pcsv.parse("0.5,12.4,1800").get("cost"))
                        && "1800".equals(pcsv.parse("0.5,12.4,1800").get("throughput")));
        return f;
    }

    /** Plug JsonLineParser into a full OptimizationAnalyzer and confirm the
     *  pipeline (auto-discovery + Pareto + champions) works end-to-end. */
    private static int testJsonEndToEnd() throws Exception {
        System.out.println("\n── JsonLineParser + OptimizationAnalyzer end-to-end ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig("{}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual,
                /*minSupport*/ 1, /*topK*/ 5,
                /*optThreshold*/ 30.0, /*watchThreshold*/ 10.0,
                /*executeCommands*/ false, /*commandTimeout*/ 0.0,
                /*dynamicPython*/ false,
                new LineParser.JsonLineParser());

        java.util.List<String> corpus = new java.util.ArrayList<>();
        double[][] tuples = {
            {0.95, 12.5, 400},
            {0.50,  6.5, 1300},
            {0.25,  5.1, 2600},
            {0.10,  3.0, 4200},
            {0.08,  2.5, 4500},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "{\"id\":\"j_%02d\",\"cost\":%.3f,\"latency\":%.2f,\"throughput\":%.0f}",
                    i + 1, tuples[i][0], tuples[i][1], tuples[i][2]));
        }

        java.util.List<AnalyzerCore.LineResult> results = new java.util.ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(AnalyzerCore.LineResult r) { results.add(r); }
        });

        int f = 0;
        f += assertCond("e2e: 5 results streamed", results.size() == 5);
        // Every result should have cost, latency, throughput as auto-discovered K/V
        // entries even though the source was JSON.
        AnalyzerCore.LineResult first = results.get(0);
        f += assertCond("e2e: 'cost' in kvPairs (parsed from JSON)",   first.features.kvPairs.containsKey("cost"));
        f += assertCond("e2e: 'latency' in kvPairs",                    first.features.kvPairs.containsKey("latency"));
        f += assertCond("e2e: 'throughput' in kvPairs",                 first.features.kvPairs.containsKey("throughput"));

        // Auto-discovery should expose all three as numeric metric streams.
        List<String> discovered = MetricStreamAnalyzer.discoveredKeys(results, 2);
        f += assertCond("e2e: cost / latency / throughput auto-discovered",
                discovered.contains("cost") && discovered.contains("latency") && discovered.contains("throughput"));
        return f;
    }

    /** Plug CsvLineParser into a full OptimizationAnalyzer and confirm a
     *  comma-separated corpus runs through auto-discovery + Pareto +
     *  champions. */
    private static int testCsvEndToEnd() throws Exception {
        System.out.println("\n── CsvLineParser + OptimizationAnalyzer end-to-end ──");
        ObjectNode manual = (ObjectNode) AnalyzerCore.parseManualConfig("{}");
        OptimizationAnalyzer analyzer = new OptimizationAnalyzer(
                manual,
                /*minSupport*/ 1, /*topK*/ 5,
                /*optThreshold*/ 30.0, /*watchThreshold*/ 10.0,
                /*executeCommands*/ false, /*commandTimeout*/ 0.0,
                /*dynamicPython*/ false,
                new LineParser.CsvLineParser("id,cost,latency,throughput"));

        java.util.List<String> corpus = new java.util.ArrayList<>();
        double[][] tuples = {
            {0.95, 12.5, 400},
            {0.50,  6.5, 1300},
            {0.25,  5.1, 2600},
            {0.10,  3.0, 4200},
            {0.08,  2.5, 4500},
        };
        for (int i = 0; i < tuples.length; i++) {
            corpus.add(String.format(Locale.ROOT,
                    "c_%02d,%.3f,%.2f,%.0f",
                    i + 1, tuples[i][0], tuples[i][1], tuples[i][2]));
        }

        java.util.List<AnalyzerCore.LineResult> results = new java.util.ArrayList<>();
        analyzer.analyzeLines(corpus, new AnalyzerCore.AnalysisListener() {
            @Override public void onResult(AnalyzerCore.LineResult r) { results.add(r); }
        });

        int f = 0;
        f += assertCond("e2e-csv: 5 results streamed", results.size() == 5);
        AnalyzerCore.LineResult first = results.get(0);
        f += assertCond("e2e-csv: 'cost' in kvPairs (parsed from CSV)",       first.features.kvPairs.containsKey("cost"));
        f += assertCond("e2e-csv: 'latency' in kvPairs",                       first.features.kvPairs.containsKey("latency"));
        f += assertCond("e2e-csv: 'throughput' in kvPairs",                    first.features.kvPairs.containsKey("throughput"));

        List<String> discovered = MetricStreamAnalyzer.discoveredKeys(results, 2);
        f += assertCond("e2e-csv: cost / latency / throughput auto-discovered",
                discovered.contains("cost") && discovered.contains("latency") && discovered.contains("throughput"));
        return f;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
