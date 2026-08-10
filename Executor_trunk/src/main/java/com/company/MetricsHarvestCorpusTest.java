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

package com.company;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Plan-1 3c -- unit checks for MainWatch's Java metrics-harvest corpus writer
 * ({@link MainWatch#flushMetricsCorpusOnShutdown}). Asserts byte-format parity with
 * {@code py_executor._write_metrics_corpus}:
 *   - K=1 (non-repeat-aware) lines: `candidate_id=<id> source_ref=<name> [run_id=<run>] <app= …>`;
 *   - K>1 (repeat-aware) lines add `repeat_idx=<N> env_id=<env>` after run_id;
 *   - deterministic CODE-POINT sort by (candidate_id, repeat_idx, env_id) (so '_' sorts after digits,
 *     exactly like Python's sorted()), '\n'-separated with a trailing newline;
 *   - run_id token omitted when no run id is set (legacy K=1 parity);
 *   - empty harvest -> empty corpus file (parity: "").
 *
 * Pure in-process: no DB, no candidate compile/run. The K-loop execution + accounting are covered by
 * {@link JavaRepeatFanoutTest}. Run against the FAT JAR (this loads MainWatch, whose static init needs
 * the dependency jars): {@code java -cp target/Executor-1.0-jar-with-dependencies.jar
 * com.company.MetricsHarvestCorpusTest}
 */
public class MetricsHarvestCorpusTest {

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testK1FormatAndCodePointSort();
        failures += testRunIdOmittedWhenAbsent();
        failures += testRepeatAwareCorpus();
        failures += testEmptyCorpus();

        System.out.println();
        if (failures == 0) {
            System.out.println("✅ ALL METRICS-HARVEST CORPUS CHECKS PASSED");
        } else {
            System.out.println("❌ " + failures + " METRICS-HARVEST CORPUS CHECK(S) FAILED");
        }
        System.exit(failures == 0 ? 0 : 1);
    }

    // ── K=1 corpus format + code-point sort + run_id prefix ──────────────────────────
    private static int testK1FormatAndCodePointSort() throws Exception {
        System.out.println("\n── K=1 corpus format + code-point sort + run_id prefix ──");
        Path tmp = Files.createTempFile("metrics-corpus-test", ".kv");
        int f = 0;
        try {
            MainWatch.metricsCorpusFile = tmp.toString();
            MainWatch.resultsV2RunId = "run-XYZ";
            // Insertion order deliberately NOT sorted; ids chosen so '_' (0x5F) vs digit ordering
            // matters: "10_0_0" < "1_0_0" < "9_0_0" by code point.
            put(new MainWatch.HarvestedSample("9_0_0", "9_0_0.java", 0, "", false,
                    "app=perf_opt_java algo=simd threads=8 batch=256 cache=large latency_ms=4.648 throughput_rps=1548.9 memory_mb=244.0 FW_VAR=0"));
            put(new MainWatch.HarvestedSample("10_0_0", "10_0_0.java", 0, "", false,
                    "app=perf_opt_java algo=naive threads=2 batch=64 cache=large latency_ms=33.024 throughput_rps=54.5 memory_mb=114.0 FW_VAR=0"));
            put(new MainWatch.HarvestedSample("1_0_0", "1_0_0.java", 0, "", false,
                    "app=perf_opt_java algo=naive threads=1 batch=16 cache=small latency_ms=100.000 throughput_rps=9.0 memory_mb=18.5 FW_VAR=0"));

            MainWatch.flushMetricsCorpusOnShutdown();

            String got = Files.readString(tmp, StandardCharsets.UTF_8);
            String expected =
                    "candidate_id=10_0_0 source_ref=10_0_0.java run_id=run-XYZ app=perf_opt_java algo=naive threads=2 batch=64 cache=large latency_ms=33.024 throughput_rps=54.5 memory_mb=114.0 FW_VAR=0\n"
                  + "candidate_id=1_0_0 source_ref=1_0_0.java run_id=run-XYZ app=perf_opt_java algo=naive threads=1 batch=16 cache=small latency_ms=100.000 throughput_rps=9.0 memory_mb=18.5 FW_VAR=0\n"
                  + "candidate_id=9_0_0 source_ref=9_0_0.java run_id=run-XYZ app=perf_opt_java algo=simd threads=8 batch=256 cache=large latency_ms=4.648 throughput_rps=1548.9 memory_mb=244.0 FW_VAR=0\n";
            f += assertCond("K=1 corpus byte-identical to _write_metrics_corpus string-key format",
                    expected.equals(got));
            if (!expected.equals(got)) { System.out.println("  --- expected ---\n" + expected + "  --- got ---\n" + got); }
        } finally {
            Files.deleteIfExists(tmp);
            reset();
        }
        return f;
    }

    // ── run_id token omitted when no run id ──────────────────────────────────────────
    private static int testRunIdOmittedWhenAbsent() throws Exception {
        System.out.println("\n── run_id token omitted when no run id ──");
        Path tmp = Files.createTempFile("metrics-corpus-test", ".kv");
        int f = 0;
        try {
            MainWatch.metricsCorpusFile = tmp.toString();
            MainWatch.resultsV2RunId = null;
            put(new MainWatch.HarvestedSample("3_0_0", "3_0_0.java", 0, "", false, "app=u key=1 FW_VAR=0"));
            MainWatch.flushMetricsCorpusOnShutdown();
            String got = Files.readString(tmp, StandardCharsets.UTF_8);
            String expected = "candidate_id=3_0_0 source_ref=3_0_0.java app=u key=1 FW_VAR=0\n";
            f += assertCond("no run_id= token when runId is null", expected.equals(got));
            if (!expected.equals(got)) System.out.println("  expected: [" + expected + "] got: [" + got + "]");
        } finally {
            Files.deleteIfExists(tmp);
            reset();
        }
        return f;
    }

    // ── K>1 repeat-aware corpus (repeat_idx/env_id tokens, sorted by identity) ────────
    private static int testRepeatAwareCorpus() throws Exception {
        System.out.println("\n── K>1 repeat-aware corpus (repeat_idx/env_id, identity sort) ──");
        Path tmp = Files.createTempFile("metrics-corpus-test", ".kv");
        int f = 0;
        try {
            MainWatch.metricsCorpusFile = tmp.toString();
            MainWatch.resultsV2RunId = "run-r";
            // two candidates, K=2 each; insertion order scrambled; env_id=local:run-r
            put(new MainWatch.HarvestedSample("7_0_0", "7_0_0.java", 1, "local:run-r", true, "app=x FW_VAR=0 latency_ms=90"));
            put(new MainWatch.HarvestedSample("7_0_0", "7_0_0.java", 0, "local:run-r", true, "app=x FW_VAR=0 latency_ms=10"));
            put(new MainWatch.HarvestedSample("12_0_0", "12_0_0.java", 0, "local:run-r", true, "app=x FW_VAR=0 latency_ms=20"));
            MainWatch.flushMetricsCorpusOnShutdown();
            String got = Files.readString(tmp, StandardCharsets.UTF_8);
            // sort by (candidate_id, repeat_idx, env_id) code-point: "12_0_0" < "7_0_0"; within 7_0_0, idx 0 < 1
            String expected =
                    "candidate_id=12_0_0 source_ref=12_0_0.java run_id=run-r repeat_idx=0 env_id=local:run-r app=x FW_VAR=0 latency_ms=20\n"
                  + "candidate_id=7_0_0 source_ref=7_0_0.java run_id=run-r repeat_idx=0 env_id=local:run-r app=x FW_VAR=0 latency_ms=10\n"
                  + "candidate_id=7_0_0 source_ref=7_0_0.java run_id=run-r repeat_idx=1 env_id=local:run-r app=x FW_VAR=0 latency_ms=90\n";
            f += assertCond("K>1 corpus byte-identical to _write_metrics_corpus repeat-aware format",
                    expected.equals(got));
            if (!expected.equals(got)) { System.out.println("  --- expected ---\n" + expected + "  --- got ---\n" + got); }
        } finally {
            Files.deleteIfExists(tmp);
            reset();
        }
        return f;
    }

    // ── empty corpus when nothing harvested ──────────────────────────────────────────
    private static int testEmptyCorpus() throws Exception {
        System.out.println("\n── empty corpus when nothing harvested ──");
        Path tmp = Files.createTempFile("metrics-corpus-test", ".kv");
        int f = 0;
        try {
            MainWatch.metricsCorpusFile = tmp.toString();
            MainWatch.resultsV2RunId = "r";
            MainWatch.flushMetricsCorpusOnShutdown();
            String got = Files.readString(tmp, StandardCharsets.UTF_8);
            f += assertCond("empty harvest -> empty corpus file", got.isEmpty());
            if (!got.isEmpty()) System.out.println("  got: [" + got + "]");
        } finally {
            Files.deleteIfExists(tmp);
            reset();
        }
        return f;
    }

    // The map key is internal (the writer sorts/formats from the sample's own fields), so any distinct
    // key works; use the same scheme recordSample uses so dedup behaviour matches production.
    private static void put(MainWatch.HarvestedSample s) {
        String key = s.repeatAware ? (s.candidateId + ' ' + s.repeatIdx + ' ' + s.envId) : s.candidateId;
        MainWatch.harvestedMetrics.put(key, s);
    }

    private static void reset() {
        MainWatch.harvestedMetrics.clear();
        MainWatch.metricsCorpusFile = null;
        MainWatch.metricsScratchDir = null;
        MainWatch.resultsV2RunId = null;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✅ " : "  ❌ ") + label);
        return cond ? 0 : 1;
    }
}
