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
import com.yurii.analyzer.core.AnalyzerCore;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Tier-2 win 2.1 — pluggable coverage-report adapter.
 *
 * After a candidate executes, the probe reads the coverage tool's report file
 * and returns a space-prefixed {@code K=V} suffix to be concatenated onto the
 * candidate's stdout.  The analyzer's existing KvLineParser folds those keys
 * into the Pareto front automatically; since {@code coverage} is in
 * {@link AutoAnalysisPlanner} MAX_HINTS, every {@code coverage_*} axis is
 * inferred as MAXIMIZE under {@link DiscoveryPolicy#DEFAULT}.
 *
 * Three concrete backends (one per supported ecosystem):
 *   • {@link JaCoCoXml}       — Java / JVM   (reads JaCoCo XML report)
 *   • {@link CoveragePyJson}  — Python       (reads {@code coverage json -o coverage.json})
 *   • {@link GcovText}        — C / C++      (reads gcov / gcovr summary text)
 *
 * The report path is a TEMPLATE: the token {@code {lineNo}} is replaced with
 * the 1-based candidate index, so per-candidate runs can write to distinct
 * files (e.g. {@code /tmp/jacoco_{lineNo}.xml}); a path with no token is a
 * single shared report (single-candidate workflows).
 *
 * Thread-safety: all built-in probes are stateless and thread-safe (read-only
 * file IO on a fresh path each call).
 *
 * Failure mode: a missing / unreadable / malformed report returns "" rather
 * than throwing, so a transient coverage-tool failure doesn't kill the
 * candidate.  Use the {@link #NONE} sentinel to disable probing entirely.
 */
@FunctionalInterface
public interface CoverageProbe {

    /**
     * @param lineNo          1-based candidate index
     * @param raw             original line emitted by the framework
     * @param delegateOutput  what the inner LineExecutor produced for this candidate
     * @return                space-prefixed K=V suffix (e.g. {@code " coverage_line=0.85 coverage_branch=0.72"}),
     *                        or "" if no coverage data is available.
     */
    String collect(int lineNo, String raw, String delegateOutput) throws Exception;

    /** No-op sentinel — emits nothing. */
    CoverageProbe NONE = (lineNo, raw, delegateOutput) -> "";

    // ─── helpers ─────────────────────────────────────────────────────────
    static String resolvePath(String template, int lineNo) {
        if (template == null) return null;
        return template.replace("{lineNo}", Integer.toString(lineNo));
    }
    static String readIfExists(String pathStr) throws IOException {
        if (pathStr == null || pathStr.isBlank()) return "";
        Path p = Path.of(pathStr);
        if (!Files.isRegularFile(p)) return "";
        return Files.readString(p, StandardCharsets.UTF_8);
    }
    static String fmtFrac(double v) { return String.format(Locale.ROOT, "%.6f", v); }

    // ─── JaCoCo XML ──────────────────────────────────────────────────────
    // Matches: <counter type="LINE" missed="..." covered="..."/>
    // The report contains per-package counters AND a final report-level
    // total per type (last-emitted).  We keep the LAST observed pair per
    // type so coverage reflects the whole report, not the first package.
    final class JaCoCoXml implements CoverageProbe {
        private static final Pattern COUNTER = Pattern.compile(
                "<counter\\s+type=\"([A-Z]+)\"\\s+missed=\"(\\d+)\"\\s+covered=\"(\\d+)\"\\s*/?>");
        private final String pathTemplate;
        public JaCoCoXml(String pathTemplate) { this.pathTemplate = pathTemplate; }

        @Override public String collect(int lineNo, String raw, String delegateOutput) throws IOException {
            String xml = readIfExists(resolvePath(pathTemplate, lineNo));
            if (xml.isEmpty()) return "";
            Map<String, long[]> totals = new LinkedHashMap<>();
            Matcher m = COUNTER.matcher(xml);
            while (m.find()) {
                totals.put(m.group(1),
                        new long[]{Long.parseLong(m.group(2)), Long.parseLong(m.group(3))});
            }
            if (totals.isEmpty()) return "";
            StringBuilder sb = new StringBuilder();
            emit(sb, "line",        totals.get("LINE"));
            emit(sb, "branch",      totals.get("BRANCH"));
            emit(sb, "method",      totals.get("METHOD"));
            emit(sb, "class",       totals.get("CLASS"));
            emit(sb, "instruction", totals.get("INSTRUCTION"));
            return sb.toString();
        }
        private static void emit(StringBuilder sb, String tag, long[] pair) {
            if (pair == null) return;
            long total = pair[0] + pair[1];
            if (total <= 0) return;
            double frac = (double) pair[1] / (double) total;
            sb.append(" coverage_").append(tag).append('=').append(fmtFrac(frac));
            sb.append(" coverage_").append(tag).append("_covered=").append(pair[1]);
            sb.append(" coverage_").append(tag).append("_total=").append(total);
        }
    }

    // ─── coverage.py JSON (coverage json -o coverage.json) ───────────────
    // Schema (subset we consume):
    //   { "totals": { "percent_covered": 85.0,
    //                 "covered_lines":   85,
    //                 "num_statements":  100,
    //                 "missing_lines":   15,
    //                 "covered_branches": 18,
    //                 "num_branches":     20 } }
    final class CoveragePyJson implements CoverageProbe {
        private final String pathTemplate;
        public CoveragePyJson(String pathTemplate) { this.pathTemplate = pathTemplate; }

        @Override public String collect(int lineNo, String raw, String delegateOutput) throws IOException {
            String json = readIfExists(resolvePath(pathTemplate, lineNo));
            if (json.isEmpty()) return "";
            JsonNode root;
            try { root = AnalyzerCore.mapper().readTree(json); }
            catch (Exception e) { return ""; }
            JsonNode totals = root.path("totals");
            if (totals.isMissingNode() || totals.isNull()) return "";

            StringBuilder sb = new StringBuilder();
            double pct = totals.path("percent_covered").asDouble(Double.NaN);
            if (!Double.isNaN(pct)) sb.append(" coverage_line=").append(fmtFrac(pct / 100.0));
            long covered = totals.path("covered_lines").asLong(-1L);
            long stmts   = totals.path("num_statements").asLong(-1L);
            if (covered >= 0) sb.append(" coverage_line_covered=").append(covered);
            if (stmts   >= 0) sb.append(" coverage_line_total=").append(stmts);
            long missing = totals.path("missing_lines").asLong(-1L);
            if (missing >= 0) sb.append(" coverage_line_missed=").append(missing);
            long numBr = totals.path("num_branches").asLong(-1L);
            long covBr = totals.path("covered_branches").asLong(-1L);
            if (numBr > 0 && covBr >= 0) {
                sb.append(" coverage_branch=").append(fmtFrac((double) covBr / (double) numBr));
                sb.append(" coverage_branch_covered=").append(covBr);
                sb.append(" coverage_branch_total=").append(numBr);
            }
            return sb.toString();
        }
    }

    // ─── gcov / gcovr summary text ──────────────────────────────────────
    // gcov per-file:    "Lines executed:75.00% of 40"
    //                   "Branches executed:62.50% of 16"
    //                   "Calls executed:80.00% of 5"
    // gcovr summary:    "lines: 85.00% (170 out of 200)"  (looser format)
    // We keep the LAST match per category so the aggregate (final) figure
    // wins over per-file figures sprinkled earlier in the file.
    final class GcovText implements CoverageProbe {
        private static final Pattern LINE_PCT = Pattern.compile(
                "Lines\\s+(?:executed|covered)\\s*:?\\s*(\\d+(?:\\.\\d+)?)\\s*%(?:\\s+of\\s+(\\d+))?",
                Pattern.CASE_INSENSITIVE);
        private static final Pattern BRANCH_PCT = Pattern.compile(
                "Branches\\s+(?:executed|covered)\\s*:?\\s*(\\d+(?:\\.\\d+)?)\\s*%(?:\\s+of\\s+(\\d+))?",
                Pattern.CASE_INSENSITIVE);
        private static final Pattern CALL_PCT = Pattern.compile(
                "Calls\\s+executed\\s*:?\\s*(\\d+(?:\\.\\d+)?)\\s*%(?:\\s+of\\s+(\\d+))?",
                Pattern.CASE_INSENSITIVE);
        private final String pathTemplate;
        public GcovText(String pathTemplate) { this.pathTemplate = pathTemplate; }

        @Override public String collect(int lineNo, String raw, String delegateOutput) throws IOException {
            String text = readIfExists(resolvePath(pathTemplate, lineNo));
            if (text.isEmpty()) return "";
            StringBuilder sb = new StringBuilder();
            emitLast(sb, "line",   LINE_PCT.matcher(text));
            emitLast(sb, "branch", BRANCH_PCT.matcher(text));
            emitLast(sb, "call",   CALL_PCT.matcher(text));
            return sb.toString();
        }
        private static void emitLast(StringBuilder sb, String tag, Matcher m) {
            String pct = null, ofN = null;
            while (m.find()) { pct = m.group(1); ofN = m.group(2); }
            if (pct == null) return;
            try {
                double frac = Double.parseDouble(pct) / 100.0;
                sb.append(" coverage_").append(tag).append('=').append(fmtFrac(frac));
                if (ofN != null) sb.append(" coverage_").append(tag).append("_total=").append(ofN);
            } catch (NumberFormatException ignored) { /* skip */ }
        }
    }
}
