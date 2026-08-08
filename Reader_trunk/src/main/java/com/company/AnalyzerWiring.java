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

package com.company;

import java.util.*;

// Extracted from the Main god-class 2026-05-30 (behaviour-preserving Extract-Class).
/** SRP: build + install the optional Heuristic-Analyzer RowSink bridge from fw.properties. */
public final class AnalyzerWiring {
    private AnalyzerWiring() {}

    public static void installIfEnabled(java.util.Properties prop) {
if (Boolean.parseBoolean(prop.getProperty("fw.analyzer.enabled", "false"))) {
try {
int qCap   = Integer.parseInt(prop.getProperty("fw.analyzer.queueCapacity", "10000"));
int topK   = Integer.parseInt(prop.getProperty("fw.analyzer.topK", "20"));
// Per-axis goal spec.  Three property formats supported (newest first):
//
//   fw.analyzer.goals = cost:min:0:1, latency:target:50:2, throughput:max:0:1, accuracy:max:0:1
//                       └key┘ └mode┘ └tgt┘└w┘  ...
//   fw.analyzer.maximizeKeys = throughput,accuracy            (legacy: max-only set)
//   fw.analyzer.minimizeKeys = cost,latency,error_rate        (legacy: min-only set)
//
// 'goals' takes precedence; if absent, max/min sets are merged.
java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goalList =
new java.util.ArrayList<>();
String goalsCsv = prop.getProperty("fw.analyzer.goals", "");
if (!goalsCsv.isBlank()) {
for (String tok : goalsCsv.split(",")) {
String[] parts = tok.trim().split(":");
if (parts.length < 2) continue;
String key  = parts[0].trim();
String mode = parts[1].trim().toLowerCase(java.util.Locale.ROOT);
double tgt  = (parts.length >= 3) ? Double.parseDouble(parts[2].trim()) : 0.0;
double w    = (parts.length >= 4) ? Double.parseDouble(parts[3].trim()) : 1.0;
com.yurii.analyzer.core.optimization.GoalSpec.Mode m =
switch (mode) {
case "max", "maximize" -> com.yurii.analyzer.core.optimization.GoalSpec.Mode.MAXIMIZE;
case "target"           -> com.yurii.analyzer.core.optimization.GoalSpec.Mode.TARGET;
default                  -> com.yurii.analyzer.core.optimization.GoalSpec.Mode.MINIMIZE;
};
goalList.add(new com.yurii.analyzer.core.optimization.GoalSpec(key, m, tgt, w));
}
} else {
for (String k : prop.getProperty("fw.analyzer.minimizeKeys", "").split(","))
if (!k.isBlank()) goalList.add(com.yurii.analyzer.core.optimization.GoalSpec.min(k.trim()));
for (String k : prop.getProperty("fw.analyzer.maximizeKeys", "").split(","))
if (!k.isBlank()) goalList.add(com.yurii.analyzer.core.optimization.GoalSpec.max(k.trim()));
}
// ─── DiscoveryPolicy: how the analyzer treats auto-discovered keys
// (those that appear in rows but aren't declared in fw.analyzer.goals).
// Default = include with lexical mode inference + weight 1.0 →
// truly agnostic to incoming parameters as the analyzer was designed.
com.yurii.analyzer.core.optimization.DiscoveryPolicy autoPolicy =
com.yurii.analyzer.core.optimization.DiscoveryPolicy.fromText(
prop.getProperty("fw.analyzer.autoDiscover",       "true"),
prop.getProperty("fw.analyzer.autoDiscoverMode",   "auto"),
prop.getProperty("fw.analyzer.autoDiscoverWeight", "1.0"));
// ─── Tier-0 bug fix 0.3: pluggable LineExecutor type via fw.properties ──
// inline   = row text IS the metric line (default; current behaviour)
// shell    = each row is run as `bash -lc <row>`; stdout becomes metric text
// compile  = each row is path-or-source to compile and run; stdout collected
String execType = prop.getProperty("fw.analyzer.executorType", "inline")
.trim().toLowerCase(java.util.Locale.ROOT);
double execTimeout = 0.0;
try { execTimeout = Double.parseDouble(
prop.getProperty("fw.analyzer.executorTimeoutSeconds", "30.0")); }
catch (NumberFormatException _) { execTimeout = 30.0; }
com.yurii.analyzer.core.optimization.LineExecutor lineExecutor;
switch (execType) {
case "shell" -> lineExecutor = new com.yurii.analyzer.core.optimization.LineExecutor.Shell(execTimeout);
case "compile", "compile-and-run", "compile_and_run" -> lineExecutor = new com.yurii.analyzer.core.optimization.LineExecutor.CompileAndRun(
prop.getProperty("fw.analyzer.compileTemplate", "javac -d /tmp/build {path}"),
prop.getProperty("fw.analyzer.runTemplate",
"java -cp /tmp/build Generated"),
execTimeout,
prop.getProperty("fw.analyzer.compileTmpExtension", ".java"));
// Tier-4.2 — RemoteWorker: hand each candidate row off to the legacy
// Executor (separate JVM, watching srcDir, writing results to a
// Postgres table) and read back the verdict as K=V metrics.  Closes
// the Master/Slave loop the BundleResumeBrief calls out as #4.
//
// Required properties:
//   fw.analyzer.remote.srcDir          — same dir the Executor watches
//   fw.analyzer.remote.dbUrl           — JDBC URL Reader wrote to
//                                         resultsDbURL.properties
//   fw.analyzer.remote.tableName       — Executor's result table
//   fw.analyzer.remote.idColumn        — defaults to combi_id_final
//   fw.analyzer.remote.selectColumns   — CSV list of result columns
//                                         to surface as K=V metrics
// Optional:
//   fw.analyzer.remote.fileExtension   — defaults to .java
//   fw.analyzer.remote.pollIntervalMs  — defaults to 200
//   fw.analyzer.remote.writeFile       — true (default) for
//     standalone-analyzer flow; false when the Reader already
//     dropped the candidate file (pure-poller bridge mode).
//   fw.analyzer.remote.idExtractorRegex — first capture group is
//     the candidate id; fall back to lineNo on miss.  For Reader
//     rows carrying the <combi_id>_<opt>_<j> marker:
//     \b(\d+)_\d+_\d+\b
case "remote", "remote-worker", "remoteworker" -> {
String remoteSrcDir = prop.getProperty("fw.analyzer.remote.srcDir", "").trim();
String remoteDbUrl  = prop.getProperty("fw.analyzer.remote.dbUrl", "").trim();
String remoteTable  = prop.getProperty("fw.analyzer.remote.tableName", "").trim();
String remoteIdCol  = prop.getProperty("fw.analyzer.remote.idColumn", "combi_id_final").trim();
String remoteColsCsv = prop.getProperty("fw.analyzer.remote.selectColumns",
"fw_var,status,combi_id_final,combi_id_optional,fw_optJ").trim();
String remoteExt    = prop.getProperty("fw.analyzer.remote.fileExtension", ".java").trim();
long remotePollMs   = 200L;
try { remotePollMs = Long.parseLong(
prop.getProperty("fw.analyzer.remote.pollIntervalMs", "200").trim()); }
catch (NumberFormatException _) {}
boolean remoteWriteFile = Boolean.parseBoolean(
prop.getProperty("fw.analyzer.remote.writeFile", "true"));
String idExtractorRegex = prop.getProperty("fw.analyzer.remote.idExtractorRegex", "").trim();

if (remoteSrcDir.isEmpty() || remoteDbUrl.isEmpty() || remoteTable.isEmpty()) {
System.err.println("[Analyzer] fw.analyzer.executorType=remote requires"
+ " fw.analyzer.remote.{srcDir,dbUrl,tableName} — falling back to inline");
lineExecutor = new com.yurii.analyzer.core.optimization.LineExecutor.Inline();
} else {
java.util.List<String> cols = new java.util.ArrayList<>();
for (String c : remoteColsCsv.split(",")) {
String t = c.trim();
if (!t.isEmpty()) cols.add(t);
}
com.yurii.analyzer.core.optimization.LineExecutor.RemoteWorker.ResultPoller poller =
new com.yurii.analyzer.core.optimization.LineExecutor.RemoteWorker.JdbcPoller(
remoteDbUrl, remoteTable, remoteIdCol, cols);
com.yurii.analyzer.core.optimization.LineExecutor.RemoteWorker.Builder rwb =
new com.yurii.analyzer.core.optimization.LineExecutor.RemoteWorker.Builder()
.srcDir(java.nio.file.Path.of(remoteSrcDir))
.fileExtension(remoteExt)
.poller(poller)
.pollIntervalMs(remotePollMs)
.timeoutSeconds(execTimeout)
.writeFile(remoteWriteFile);
if (!idExtractorRegex.isEmpty()) rwb.idExtractorRegex(idExtractorRegex);
lineExecutor = rwb.build();
System.out.println("[Analyzer] RemoteWorker configured (srcDir=" + remoteSrcDir
+ ", dbUrl=" + remoteDbUrl + ", table=" + remoteTable
+ ", idColumn=" + remoteIdCol + ", selectColumns=" + cols
+ ", writeFile=" + remoteWriteFile + ")");
}
}
default -> lineExecutor = new com.yurii.analyzer.core.optimization.LineExecutor.Inline();
}
// ─── Tier-2 win 2.1: post-execution coverage probe (JaCoCo / coverage.py / gcov) ──
// Probe sits INSIDE the cache so a re-emitted candidate returns the
// cached payload that already carries the coverage suffix.
String probeType = prop.getProperty("fw.analyzer.coverage", "none")
.trim().toLowerCase(java.util.Locale.ROOT);
if (!probeType.equals("none") && !probeType.isEmpty()) {
String reportTpl = prop.getProperty("fw.analyzer.coverageReport", "");
com.yurii.analyzer.core.optimization.CoverageProbe probe;
switch (probeType) {
case "jacoco", "jacoco-xml" -> probe = new com.yurii.analyzer.core.optimization.CoverageProbe.JaCoCoXml(reportTpl);
case "coverage.py", "coveragepy", "python" -> probe = new com.yurii.analyzer.core.optimization.CoverageProbe.CoveragePyJson(reportTpl);
case "gcov", "gcovr", "c", "cpp" -> probe = new com.yurii.analyzer.core.optimization.CoverageProbe.GcovText(reportTpl);
default -> {
probe = com.yurii.analyzer.core.optimization.CoverageProbe.NONE;
System.err.println("[Analyzer] Unknown fw.analyzer.coverage='" + probeType + "' — disabled");
}
}
if (probe != com.yurii.analyzer.core.optimization.CoverageProbe.NONE) {
lineExecutor = new com.yurii.analyzer.core.optimization.LineExecutor.CoverageProbing(
lineExecutor, probe);
System.out.println("[Analyzer] CoverageProbe ENABLED (backend=" + probeType
+ ", reportTemplate=" + reportTpl + ")");
}
}
// ─── Tier-1 win 1.5: opt-in result memoisation per candidate hash ──
// fw.analyzer.cache=true wraps the configured executor in a bounded
// LRU cache.  HitRate appears in Snapshot.render() and toJson() under
// "cacheStats".  Default false → byte-for-byte identical legacy path.
// Placed AFTER CoverageProbing so cache is outermost: repeated raw
// lines return the cached payload that already includes coverage K=V.
if (Boolean.parseBoolean(prop.getProperty("fw.analyzer.cache", "false"))) {
int cacheCap = 4096;
try { cacheCap = Integer.parseInt(
prop.getProperty("fw.analyzer.cacheCapacity", "4096")); }
catch (NumberFormatException _) { cacheCap = 4096; }
lineExecutor = new com.yurii.analyzer.core.optimization.LineExecutor.Caching(
lineExecutor, cacheCap);
System.out.println("[Analyzer] Cache ENABLED (capacity=" + cacheCap + ")");
}
com.company.sink.AnalyzerBridge bridge = com.company.sink.AnalyzerBridge.start(
qCap, topK, lineExecutor,
goalList, autoPolicy, "{}");
com.company.sink.RowSinkRegistry.install(bridge);
System.out.println("[Analyzer] Bridge installed (queueCapacity=" + qCap
+ ", topK=" + topK + ", executor=" + lineExecutor.getClass().getSimpleName()
+ ", declared goals=" + goalList
+ ", autoPolicy=" + autoPolicy + ")");
// Tier-3.5 — optional seed dump for closed-loop feedback (Master mode).
// When set, the analyzer's snapshot is converted to BundleSeed JSON
// and dropped to disk so the next Core iteration can pick it up.
// Off by default — empty path skips the dump.  Source-run id from
// fw.analyzer.seedSourceRunId or auto-derived from epoch ms.
final String seedOutputPath = prop.getProperty("fw.analyzer.seedOutputPath", "").trim();
final String seedSourceRunId = prop.getProperty("fw.analyzer.seedSourceRunId",
"reader-" + System.currentTimeMillis()).trim();
// Print snapshot at JVM shutdown so the user sees the result.
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot snap =
bridge.finishAndGetSnapshot(60_000L);
if (snap != null) System.out.println(snap.render());
// Tier-3.5: dump BundleSeed to configured path.
if (snap != null && !seedOutputPath.isEmpty()) {
try {
com.yurii.analyzer.core.optimization.BundleSeed seed =
snap.toBundleSeed(seedSourceRunId);
java.nio.file.Path target = java.nio.file.Path.of(seedOutputPath);
seed.writeToFile(target);
System.out.println("[Analyzer] BundleSeed written to " + target
+ " (winners=" + seed.size()
+ ", distinctLineNos=" + seed.distinctLineNos().size()
+ ", sourceRunId=" + seedSourceRunId + ")");
} catch (Exception ex) {
System.err.println("[Analyzer] BundleSeed dump FAILED: " + ex);
}
}
com.company.sink.RowSinkRegistry.closeActive();
}, "analyzer-shutdown-hook"));
} catch (Throwable t) {
System.err.println("[Analyzer] Bridge install FAILED: " + t);
t.printStackTrace();
}
}

    }
}
