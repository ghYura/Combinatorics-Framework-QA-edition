package com.yurii.analyzer.core.optimization;

import com.yurii.analyzer.core.AnalyzerCore;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Strategy for turning one Combinatorics-Framework-emitted line into a payload
 * carrying agnostic metrics.  The Analyzer's streaming pipeline doesn't care
 * what the line semantically represents (test scenario, Java method, prompt,
 * gene encoding, hyperparameter tuple, …).  All the domain-specific knowledge
 * — "is this a shell command?", "is this a path to source code I should
 * compile?", "is this already a metric line?" — is encapsulated here.
 *
 * Implementations MUST be thread-safe for use by parallel streaming workers.
 */
@FunctionalInterface
public interface LineExecutor {

    /**
     * @param lineNo  1-based candidate index
     * @param raw     the line as emitted by the Combinatorics Framework
     * @return        text from which metrics will be parsed (typically stdout
     *                of an executed candidate, or the line itself if it
     *                already carries inline metrics).  Empty string is fine.
     */
    String execute(int lineNo, String raw) throws Exception;

    /** Cumulative cache statistics for memoising executors.  Non-caching
     *  implementations return {@link CacheStats#EMPTY}.  The analyzer enriches
     *  the final {@link OnlineMetricAggregator.Snapshot} with this value, so
     *  GP / hyper-opt loops can see how often a candidate was re-evaluated
     *  versus served from cache. */
    default CacheStats cacheStats() { return CacheStats.EMPTY; }

    /** No-op executor: returns the input line verbatim.  Use when the
     *  Combinatorics Framework already writes metric K=V pairs into each line
     *  (variant A: framework precomputes everything, analyzer just selects). */
    final class Inline implements LineExecutor {
        @Override public String execute(int lineNo, String raw) {
            return raw == null ? "" : raw;
        }
    }

    /** Shell executor: each line is a CLI invocation.  Captures stdout (with
     *  stderr redirected) up to {@code timeoutSeconds} per candidate.  This
     *  is variant B — the most common case for the Combinatorics framework. */
    final class Shell implements LineExecutor {
        private final double timeoutSeconds;
        public Shell(double timeoutSeconds) { this.timeoutSeconds = timeoutSeconds; }
        @Override public String execute(int lineNo, String raw) {
            String resolved = AnalyzerCore.resolveLinePayload(raw, true, timeoutSeconds);
            return resolved == null ? "" : resolved;
        }
    }

    /** Compile-and-run executor for variant C: each line is a path (or short
     *  reference) to source code that needs to be built before execution.
     *  The build command + run command are templated with the line's content
     *  (or path).  Use this when the Combinatorics Framework writes one Java
     *  file (or .py / .c / .rs / …) per candidate and emits its path.
     *
     *  Two placeholders supported in the templates: {@code {path}} and {@code {code}}.
     *  If the line looks like an existing file path, {@code {path}} resolves to
     *  the line itself and {@code {code}} to the file's contents.  Otherwise
     *  the line text is treated as inline source: a temp file is written and
     *  its path substituted. */
    final class CompileAndRun implements LineExecutor {
        private final String buildTemplate;
        private final String runTemplate;
        private final double timeoutSeconds;
        private final String tmpExtension;

        /**
         * @param buildTemplate e.g. {@code "javac -d /tmp/build {path}"} (run before {@code runTemplate})
         * @param runTemplate   e.g. {@code "java -cp /tmp/build Generated"}
         * @param tmpExtension  e.g. {@code ".java"} — used when the line is inline source, not a path
         */
        public CompileAndRun(String buildTemplate, String runTemplate,
                             double timeoutSeconds, String tmpExtension) {
            this.buildTemplate = buildTemplate;
            this.runTemplate   = runTemplate;
            this.timeoutSeconds = timeoutSeconds;
            this.tmpExtension  = tmpExtension == null ? ".txt" : tmpExtension;
        }

        @Override public String execute(int lineNo, String raw) throws IOException {
            if (raw == null || raw.isBlank()) return "";
            String trimmed = raw.trim();
            String path; String code;
            try {
                Path p = Path.of(trimmed);
                if (Files.isRegularFile(p)) {
                    path = p.toAbsolutePath().toString();
                    code = Files.readString(p, StandardCharsets.UTF_8);
                } else { path = null; code = raw; }
            } catch (Exception e) { path = null; code = raw; }

            if (path == null) {
                // Materialise inline source to a temp file so {path} works.
                Path tmp = Files.createTempFile("combo_cand_" + lineNo + "_", tmpExtension);
                Files.writeString(tmp, code, StandardCharsets.UTF_8);
                tmp.toFile().deleteOnExit();
                path = tmp.toAbsolutePath().toString();
            }

            String build = substitute(buildTemplate, path, code);
            String run   = substitute(runTemplate, path, code);

            // Build phase — its stdout is folded into the run output to surface
            // compile errors as captured text, since downstream metrics live in
            // run-stdout but a compile failure should still be observable.
            String buildOut = AnalyzerCore.resolveLinePayload(build, true, timeoutSeconds);
            if (buildOut != null && buildOut.startsWith("ERROR:")) return buildOut;
            String runOut   = AnalyzerCore.resolveLinePayload(run, true, timeoutSeconds);
            return runOut == null ? "" : runOut;
        }

        private static String substitute(String template, String path, String code) {
            if (template == null) return "";
            String out = template;
            if (path != null) out = out.replace("{path}", path);
            // {code} is rare and dangerous (shell-injection); intentionally minimal.
            if (code != null) out = out.replace("{code}", code);
            return out;
        }
    }

    /**
     * Memoising decorator: caches {@code execute(_, raw)} results keyed by the
     * raw line.  The line number is intentionally NOT part of the key — the
     * same candidate at different positions should hit, which is the whole
     * point (GP loops re-emit winners, combinatorial fronts re-evaluate
     * survivors, NSGA-II re-tests boundary points).
     *
     * Bounded LRU eviction via {@link java.util.LinkedHashMap} access-order;
     * the map is wrapped in {@code synchronized} since parallel streaming
     * workers share one executor.  For the canonical workload (≤ a few × 10⁴
     * unique candidates), the contention cost is dwarfed by even a single
     * shell fork avoided.
     *
     * Cache OFF (i.e. the framework never constructs this) keeps legacy
     * output byte-for-byte identical — {@link CacheStats#EMPTY} suppresses
     * the cache section in {@link OnlineMetricAggregator.Snapshot#toJson()}
     * and {@link OnlineMetricAggregator.Snapshot#render()}.
     */
    final class Caching implements LineExecutor {
        private final LineExecutor delegate;
        private final int capacity;
        private final java.util.Map<String, String> cache;
        private final java.util.concurrent.atomic.AtomicLong hits = new java.util.concurrent.atomic.AtomicLong();
        private final java.util.concurrent.atomic.AtomicLong misses = new java.util.concurrent.atomic.AtomicLong();

        public Caching(LineExecutor delegate, int capacity) {
            this.delegate = (delegate == null) ? new Inline() : delegate;
            this.capacity = Math.max(16, capacity);
            final int cap = this.capacity;
            this.cache = java.util.Collections.synchronizedMap(
                    new java.util.LinkedHashMap<String, String>(cap, 0.75f, true) {
                        @Override protected boolean removeEldestEntry(
                                java.util.Map.Entry<String, String> eldest) {
                            return size() > cap;
                        }
                    });
        }

        @Override public String execute(int lineNo, String raw) throws Exception {
            if (raw == null) return "";
            String hit;
            synchronized (cache) { hit = cache.get(raw); }
            if (hit != null) { hits.incrementAndGet(); return hit; }
            String fresh = delegate.execute(lineNo, raw);
            if (fresh == null) fresh = "";
            synchronized (cache) { cache.put(raw, fresh); }
            misses.incrementAndGet();
            return fresh;
        }

        @Override public CacheStats cacheStats() {
            int size;
            synchronized (cache) { size = cache.size(); }
            return new CacheStats(hits.get(), misses.get(), size, capacity);
        }
    }

    /**
     * Tier-2 win 2.1 — post-execution coverage probe.  After the delegate
     * runs, asks a {@link CoverageProbe} for a {@code K=V} suffix and
     * concatenates it onto the candidate's payload.  The analyzer's existing
     * KvLineParser folds the {@code coverage_*} keys into the Pareto front;
     * {@link AutoAnalysisPlanner} already maps "coverage" to MAX, so QA-style
     * "more coverage is better" wins by default.
     *
     * Composes with {@link Caching}: place this INSIDE the cache (cache
     * outermost) so a repeated raw line returns the cached output that
     * already carries the probe's suffix — no redundant file IO.
     *
     * Forwards {@link #cacheStats()} from the delegate so cache stats
     * surface even when the decorator is the outermost layer.
     */
    final class CoverageProbing implements LineExecutor {
        private final LineExecutor delegate;
        private final CoverageProbe probe;

        public CoverageProbing(LineExecutor delegate, CoverageProbe probe) {
            this.delegate = (delegate == null) ? new Inline() : delegate;
            this.probe    = (probe == null)    ? CoverageProbe.NONE : probe;
        }

        @Override public String execute(int lineNo, String raw) throws Exception {
            String out = delegate.execute(lineNo, raw);
            if (out == null) out = "";
            String suffix = probe.collect(lineNo, raw, out);
            if (suffix == null || suffix.isEmpty()) return out;
            return out + suffix;
        }

        @Override public CacheStats cacheStats() { return delegate.cacheStats(); }
    }

    /**
     * Tier-4.2 — distributed scoring through the legacy Executor.
     *
     * <p>The bundle's pre-refactor scoring half (a separate JVM at
     * {@code ../../../../../../../../../Executor_trunk/}) watches a
     * directory for {@code <combi_id>.java} files, Janino-compiles each, runs
     * {@code main(String[])} via reflection, reads {@code public static int
     * FW_VAR} / {@code FW_CUSTOM_VAR}, and writes a row into a Postgres
     * <em>results</em> table.  This executor is the Analyzer's symmetric
     * other end of that pipe:</p>
     *
     * <ol>
     *   <li>Write {@code raw} atomically as {@code <candidateId>.<ext>} into
     *       {@code srcDir} — same directory the legacy Executor watches.
     *       The Executor's {@code WatchService} sees ENTRY_MODIFY, compiles,
     *       runs.</li>
     *   <li>Poll the results table for the row whose id column equals
     *       {@code candidateId}.  When the row appears, project the
     *       configured columns into a {@code K=V K=V ...} payload that
     *       {@link com.yurii.analyzer.core.optimization.LineParser.KvLineParser}
     *       can ingest.  {@code FW_VAR=0} ⇒ candidate passed; non-zero is
     *       the exit code.  Goes straight into NSGA-II as another axis.</li>
     * </ol>
     *
     * <p><strong>Composition.</strong> Wrap this with {@link Caching} (so
     * re-emitted survivors don't re-trigger compile-and-run on the remote
     * side) and {@link CoverageProbing} (if the remote pipeline also produces
     * a coverage report path).  The decorators apply unchanged because
     * RemoteWorker is just another {@link LineExecutor}.</p>
     *
     * <p><strong>Reader-bridge mode.</strong> When the CombinatoricsReader is
     * already writing {@code <combi_id>_0_0.java} files into the same
     * {@code srcDir}, use {@link Builder#writeFile(boolean)} {@code (false)}
     * so RemoteWorker only polls — no double-write collision.  The
     * default {@code true} is the standalone-Analyzer flow.</p>
     *
     * <p>Thread-safe: every {@link #execute} call is independent; the poller
     * implementation must also be thread-safe (the JDBC one opens a fresh
     * connection per call).</p>
     */
    final class RemoteWorker implements LineExecutor {

        /** Pluggable result-lookup.  Default {@link JdbcPoller} talks to
         *  the Executor's results Postgres; tests can supply a stub. */
        @FunctionalInterface
        public interface ResultPoller {
            /** @return {@code null} if no result yet; map column → string
             *          value otherwise.  Map iteration order should be stable
             *          (LinkedHashMap is fine) so the K=V output is
             *          deterministic. */
            java.util.Map<String, String> pollOnce(String candidateId) throws Exception;
            /** Optional cleanup hook for connection-pool-backed implementations. */
            default void close() throws Exception {}
        }

        /** Derive the candidate id from {@code (lineNo, raw)}.  Default is
         *  {@code String.valueOf(lineNo)} — the streaming pipeline's 1-based
         *  iterator position.  For the Reader-bridge case, supply a regex
         *  via {@link Builder#idExtractor} that pulls the {@code combi_id}
         *  out of the row's {@code FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE}
         *  substitution. */
        @FunctionalInterface
        public interface IdExtractor {
            String extract(int lineNo, String raw);
        }

        private final java.nio.file.Path srcDir;
        private final String fileExtension;
        private final ResultPoller poller;
        private final long pollIntervalMs;
        private final double timeoutSeconds;
        private final IdExtractor idExtractor;
        private final boolean writeFile;

        /** Most-explicit constructor.  See {@link Builder} for ergonomic
         *  construction. */
        public RemoteWorker(java.nio.file.Path srcDir, String fileExtension,
                            ResultPoller poller, long pollIntervalMs,
                            double timeoutSeconds, IdExtractor idExtractor,
                            boolean writeFile) {
            if (srcDir == null) throw new IllegalArgumentException("srcDir must be non-null");
            this.srcDir         = srcDir;
            this.fileExtension  = (fileExtension == null || fileExtension.isBlank()) ? ".java" : fileExtension;
            this.poller         = (poller == null)        ? (id -> null) : poller;
            this.pollIntervalMs = Math.max(10L, pollIntervalMs);
            this.timeoutSeconds = (timeoutSeconds <= 0)   ? 30.0 : timeoutSeconds;
            this.idExtractor    = (idExtractor == null)   ? (n, r) -> String.valueOf(n) : idExtractor;
            this.writeFile      = writeFile;
        }

        @Override public String execute(int lineNo, String raw) throws Exception {
            if (raw == null) return "";
            String candidateId = idExtractor.extract(lineNo, raw);
            if (candidateId == null || candidateId.isBlank()) {
                candidateId = String.valueOf(lineNo);
            }

            if (writeFile) {
                java.nio.file.Files.createDirectories(srcDir);
                java.nio.file.Path target = srcDir.resolve(candidateId + fileExtension);
                // Atomic move so the Executor's WatchService never sees a
                // half-written file (a partial Janino cook() throws).
                java.nio.file.Path tmp = java.nio.file.Files.createTempFile(
                        srcDir, "remote_", fileExtension + ".tmp");
                java.nio.file.Files.writeString(tmp, raw, java.nio.charset.StandardCharsets.UTF_8);
                try {
                    java.nio.file.Files.move(tmp, target,
                            java.nio.file.StandardCopyOption.ATOMIC_MOVE,
                            java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                } catch (java.nio.file.AtomicMoveNotSupportedException amns) {
                    java.nio.file.Files.move(tmp, target,
                            java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            }

            long deadlineNanos = System.nanoTime() + (long)(timeoutSeconds * 1e9);
            while (System.nanoTime() < deadlineNanos) {
                java.util.Map<String, String> row = poller.pollOnce(candidateId);
                if (row != null && !row.isEmpty()) {
                    StringBuilder sb = new StringBuilder();
                    sb.append("remote_id=").append(candidateId);
                    for (java.util.Map.Entry<String, String> e : row.entrySet()) {
                        sb.append(' ').append(e.getKey()).append('=');
                        String v = e.getValue();
                        sb.append(v == null ? "" : v);
                    }
                    return sb.toString();
                }
                try {
                    Thread.sleep(pollIntervalMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return "remote_id=" + candidateId + " remote_status=interrupted";
                }
            }
            return "remote_id=" + candidateId + " remote_status=timeout";
        }

        /**
         * Default {@link ResultPoller}: opens a JDBC connection per call,
         * runs {@code SELECT <cols> FROM <table> WHERE <idColumn> = ? LIMIT 1},
         * returns {@code null} if no row matches.  Selected columns become
         * the K=V keys emitted by {@link RemoteWorker#execute}.
         *
         * <p>The Executor's results table (per fw.properties
         * {@code results.db.*}) typically carries at minimum:
         * {@code status, attachment, fw_var, combi_id_final,
         * combi_id_optional, fw_optJ}.  Score on {@code fw_var} (smaller is
         * better — 0 = passed) and {@code status} (true/false).</p>
         */
        public static final class JdbcPoller implements ResultPoller {
            private final String jdbcUrl;
            private final String selectSql;
            private final java.util.List<String> columns;
            private final java.util.concurrent.atomic.AtomicBoolean forceTextIdBinding =
                    new java.util.concurrent.atomic.AtomicBoolean(false);

            public JdbcPoller(String jdbcUrl, String tableName, String idColumn,
                              java.util.List<String> selectColumns) {
                if (jdbcUrl == null || jdbcUrl.isBlank())
                    throw new IllegalArgumentException("jdbcUrl must be non-blank");
                if (tableName == null || tableName.isBlank())
                    throw new IllegalArgumentException("tableName must be non-blank");
                if (idColumn == null || idColumn.isBlank())
                    throw new IllegalArgumentException("idColumn must be non-blank");
                if (selectColumns == null || selectColumns.isEmpty())
                    throw new IllegalArgumentException("selectColumns must be non-empty");
                this.jdbcUrl   = jdbcUrl;
                this.columns   = java.util.List.copyOf(selectColumns);
                // Quote EACH column identifier AND the id column — not just the table.
                // The Executor's results DDL creates "fw_optJ" QUOTED (case-sensitive,
                // ResultsDbProvisioner), so an unquoted SELECT folds it to fw_optj and
                // Postgres errors `column "fw_optj" does not exist`, breaking every poll.
                // Quoting by the exact configured name matches both the quoted mixed-case
                // columns (fw_optJ) and the unquoted-lowercase ones (fw_var/status/…). 2026-05-31.
                String cols    = this.columns.stream()
                        .map(JdbcPoller::quoteIdent)
                        .collect(java.util.stream.Collectors.joining(", "));
                String quoted  = tableName.contains("\"") ? tableName : "\"" + tableName + "\"";
                this.selectSql = "SELECT " + cols
                        + " FROM " + quoted
                        + " WHERE " + quoteIdent(idColumn) + " = ? LIMIT 1";
            }

            /** Double-quote a column/identifier (idempotent if already quoted) so
             *  Postgres treats it case-sensitively and matches the exact stored name. */
            private static String quoteIdent(String id) {
                return id.contains("\"") ? id : "\"" + id + "\"";
            }

            @Override public java.util.Map<String, String> pollOnce(String candidateId)
                    throws java.sql.SQLException {
                if (forceTextIdBinding.get()) return pollOnceBound(candidateId, false);
                if (candidateId != null) {
                    try {
                        Long.parseLong(candidateId);
                        try {
                            return pollOnceBound(candidateId, true);
                        } catch (java.sql.SQLException ex) {
                            if (!looksLikeIdTypeMismatch(ex)) throw ex;
                            // Canonical results_v2.candidate_id is text. A numeric-looking id such as
                            // "1" must still be bound as text there; cache the decision after the
                            // first PostgreSQL text=bigint/operator-mismatch failure.
                            forceTextIdBinding.set(true);
                            return pollOnceBound(candidateId, false);
                        }
                    } catch (NumberFormatException ignored) { /* bind non-numeric ids as text below */ }
                }
                return pollOnceBound(candidateId, false);
            }

            private java.util.Map<String, String> pollOnceBound(String candidateId, boolean bindLong)
                    throws java.sql.SQLException {
                try (java.sql.Connection c = java.sql.DriverManager.getConnection(jdbcUrl);
                     java.sql.PreparedStatement ps = c.prepareStatement(selectSql)) {
                    if (bindLong) ps.setLong(1, Long.parseLong(candidateId));
                    else ps.setString(1, candidateId);
                    try (java.sql.ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) return null;
                        java.util.Map<String, String> row = new java.util.LinkedHashMap<>();
                        for (String col : columns) {
                            Object v;
                            try { v = rs.getObject(col); }
                            catch (java.sql.SQLException unknownCol) { continue; }
                            row.put(col.toLowerCase(java.util.Locale.ROOT),
                                    v == null ? "" : v.toString());
                        }
                        return row;
                    }
                }
            }

            private static boolean looksLikeIdTypeMismatch(java.sql.SQLException ex) {
                for (java.sql.SQLException cur = ex; cur != null; cur = cur.getNextException()) {
                    String state = cur.getSQLState();
                    String msg = cur.getMessage() == null ? "" : cur.getMessage().toLowerCase(java.util.Locale.ROOT);
                    if ("42883".equals(state) || "42804".equals(state)
                            || msg.contains("operator does not exist")
                            || msg.contains("text = bigint")
                            || msg.contains("character varying = bigint")) {
                        return true;
                    }
                }
                return false;
            }
        }

        /** Fluent builder.  Required: {@code srcDir} and {@code poller}.
         *  Everything else has a sensible default.  Use this rather than the
         *  raw 7-arg constructor for clarity at call sites. */
        public static final class Builder {
            private java.nio.file.Path srcDir;
            private String fileExtension = ".java";
            private ResultPoller poller;
            private long pollIntervalMs = 200L;
            private double timeoutSeconds = 30.0;
            private IdExtractor idExtractor; // null → lineNo
            private boolean writeFile = true;

            public Builder srcDir(java.nio.file.Path p)         { this.srcDir = p;            return this; }
            public Builder fileExtension(String e)              { this.fileExtension = e;     return this; }
            public Builder poller(ResultPoller p)               { this.poller = p;            return this; }
            public Builder pollIntervalMs(long ms)              { this.pollIntervalMs = ms;   return this; }
            public Builder timeoutSeconds(double t)             { this.timeoutSeconds = t;    return this; }
            public Builder idExtractor(IdExtractor x)           { this.idExtractor = x;       return this; }
            public Builder writeFile(boolean w)                 { this.writeFile = w;         return this; }

            /** Convenience: derive the id from a regex's first capture group
             *  applied to the raw line; fall back to {@code lineNo} when no
             *  match.  Most useful for Reader-bridge rows that carry the
             *  {@code <combi_id>_<opt>_<j>} marker. */
            public Builder idExtractorRegex(String regex) {
                if (regex == null || regex.isBlank()) { this.idExtractor = null; return this; }
                final java.util.regex.Pattern p = java.util.regex.Pattern.compile(regex);
                this.idExtractor = (n, r) -> {
                    if (r == null) return String.valueOf(n);
                    java.util.regex.Matcher m = p.matcher(r);
                    if (m.find() && m.groupCount() >= 1) return m.group(1);
                    return String.valueOf(n);
                };
                return this;
            }

            public RemoteWorker build() {
                return new RemoteWorker(srcDir, fileExtension, poller,
                        pollIntervalMs, timeoutSeconds, idExtractor, writeFile);
            }
        }
    }
}
