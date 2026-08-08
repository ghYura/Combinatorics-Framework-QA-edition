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

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Tier-3.5 — Core-side reader for the closed-loop feedback artifact produced
 * by the Analyzer's {@code com.yurii.analyzer.core.optimization.BundleSeed}.
 *
 * <p>Stays schema-compatible (forward-compatible) with the Analyzer's writer:
 * we read the JSON with Jackson directly, no shared class dependency on the
 * Analyzer module.  The fields this adapter cares about are documented as
 * {@code schemaVersion=1}; unknown keys are ignored, missing keys are
 * tolerated (the artifact may have been written by an older Analyzer build).</p>
 *
 * <p>Master mode flow:</p>
 * <pre>
 *   Analyzer.Snapshot.toBundleSeed()  →  bundle_seed.json  →  Core.BundleSeedAdapter
 *                                                                ↓
 *                                       declaredMetrics + observedRanges + winners
 *                                                                ↓
 *                                       Future: narrow FW_Seq generation around winners
 * </pre>
 *
 * <p>This MVP exposes <em>read-only</em> accessors so MainRefactored can log
 * what the previous iteration learned and future Tier-3.5 follow-up sessions
 * can wire the narrowing/elitism strategies on top.  The adapter itself
 * remains side-effect-free.</p>
 *
 * <p>Thread-safe: instances are immutable after construction.</p>
 */
public final class BundleSeedAdapter {

    /** One Pareto / champion / balanced-optimum winner from the previous
     *  iteration.  Mirrors {@code BundleSeed.Winner} on the Analyzer side. */
    public static final class Winner {
        public final int    lineNo;
        public final double score;
        /** {@code "pareto"} | {@code "champion-min:<key>"} |
         *  {@code "champion-max:<key>"} | {@code "balanced:<strategy>"} —
         *  see Analyzer's {@code BundleSeed.fromSnapshot} for the canonical list. */
        public final String role;
        /** Candidate's full K=V map.  Same parsing rules as the Reader's
         *  {@code KvLineParser} produces — keys lower-cased, values verbatim. */
        public final Map<String, String> kvPairs;
        /** {@link Double#NaN} = not produced by NSGA-II;
         *  {@link Double#POSITIVE_INFINITY} = boundary on at least one axis. */
        public final double crowdingDistance;

        Winner(int lineNo, double score, String role,
               Map<String, String> kvPairs, double crowdingDistance) {
            this.lineNo           = lineNo;
            this.score            = score;
            this.role             = role == null ? "" : role;
            this.kvPairs          = (kvPairs == null) ? Map.of() : Map.copyOf(kvPairs);
            this.crowdingDistance = crowdingDistance;
        }

        /** Numeric coercion for this winner's value on the named metric.
         *  Mirrors the Analyzer's {@code tryParseNumeric} loose contract:
         *  strips a collection-opener brace, tries direct parse, then a
         *  light unit-suffix table (ms / s / KB / MiB / % / …), then the
         *  first numeric-looking substring.  Returns empty when nothing
         *  parses. */
        public OptionalDouble numericValue(String key) {
            if (key == null) return OptionalDouble.empty();
            String v = kvPairs.get(key);
            return parseNumeric(v);
        }
    }

    /** Per-metric corpus statistics carried in the seed.  Mirrors
     *  {@code BundleSeed.MetricRange} on the Analyzer side. */
    public static final class MetricRange {
        public final String key;
        public final long   n;
        public final double min;
        public final double max;
        public final double mean;
        public final double stdev;
        MetricRange(String key, long n, double min, double max, double mean, double stdev) {
            this.key = key; this.n = n; this.min = min; this.max = max;
            this.mean = mean; this.stdev = stdev;
        }

        /** True iff {@code value} lies inside the corpus range observed for
         *  this metric (inclusive on both ends).  Use as the safest possible
         *  narrowing predicate — anything outside the observed range
         *  definitely wasn't sampled by the previous iteration. */
        public boolean contains(double value) {
            return Double.isFinite(value) && value >= min && value <= max;
        }
    }

    public final int                       schemaVersion;
    public final long                      generatedAtEpochMs;
    public final String                    sourceRunId;
    public final long                      totalCandidatesObserved;
    public final Set<String>               declaredMetrics;
    public final Map<String, MetricRange>  observedRanges;
    public final List<Winner>              winners;

    private BundleSeedAdapter(int schemaVersion, long generatedAtEpochMs,
                              String sourceRunId, long totalCandidatesObserved,
                              Set<String> declaredMetrics,
                              Map<String, MetricRange> observedRanges,
                              List<Winner> winners) {
        this.schemaVersion           = schemaVersion;
        this.generatedAtEpochMs      = generatedAtEpochMs;
        this.sourceRunId             = sourceRunId == null ? "" : sourceRunId;
        this.totalCandidatesObserved = totalCandidatesObserved;
        this.declaredMetrics         = Collections.unmodifiableSet(new LinkedHashSet<>(declaredMetrics));
        this.observedRanges          = Collections.unmodifiableMap(new LinkedHashMap<>(observedRanges));
        this.winners                 = Collections.unmodifiableList(new ArrayList<>(winners));
    }

    /** Load a BundleSeed JSON file produced by the Analyzer.  Tolerant to
     *  unknown / missing keys for forward compatibility. */
    public static BundleSeedAdapter loadFromFile(Path path) throws IOException {
        if (path == null) throw new IllegalArgumentException("path must be non-null");
        if (!Files.isRegularFile(path))
            throw new IOException("BundleSeed file not found: " + path);
        String json = Files.readString(path, StandardCharsets.UTF_8);
        return parseJson(json);
    }

    /** Parse from a JSON string.  Public for testing + for callers that
     *  receive the artifact via channels other than the filesystem. */
    public static BundleSeedAdapter parseJson(String json) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode root = mapper.readTree(json == null ? "{}" : json);
        return fromJson(root);
    }

    /** Parse from a Jackson {@link JsonNode}.  All accessors below assume the
     *  schema laid out in {@code com.yurii.analyzer.core.optimization.BundleSeed}
     *  schemaVersion=1.  Higher schemaVersion is accepted; unknown fields
     *  ignored. */
    public static BundleSeedAdapter fromJson(JsonNode root) {
        int    schemaVersion          = root.path("schemaVersion").asInt(1);
        long   generatedAtEpochMs     = root.path("generatedAtEpochMs").asLong(0L);
        String sourceRunId            = root.path("sourceRunId").asText("");
        long   totalCandidatesObserved = root.path("totalCandidatesObserved").asLong(0L);

        Set<String> declared = new LinkedHashSet<>();
        JsonNode dm = root.path("declaredMetrics");
        if (dm.isArray()) for (JsonNode n : dm) {
            String k = n.asText(""); if (!k.isEmpty()) declared.add(k);
        }

        Map<String, MetricRange> ranges = new LinkedHashMap<>();
        JsonNode ro = root.path("observedRanges");
        if (ro.isObject()) {
            var it = ro.fields();
            while (it.hasNext()) {
                Map.Entry<String, JsonNode> e = it.next();
                JsonNode v = e.getValue();
                ranges.put(e.getKey(), new MetricRange(
                        v.path("key").asText(e.getKey()),
                        v.path("n").asLong(0),
                        v.path("min").asDouble(Double.NaN),
                        v.path("max").asDouble(Double.NaN),
                        v.path("mean").asDouble(Double.NaN),
                        v.path("stdev").asDouble(Double.NaN)));
            }
        }

        List<Winner> winners = new ArrayList<>();
        JsonNode wArr = root.path("winners");
        if (wArr.isArray()) for (JsonNode w : wArr) {
            int    lineNo = w.path("lineNo").asInt(-1);
            double score  = w.path("score").asDouble(Double.NaN);
            String role   = w.path("role").asText("");
            Map<String, String> kv = new LinkedHashMap<>();
            JsonNode kvNode = w.path("kvPairs");
            if (kvNode.isObject()) {
                var it = kvNode.fields();
                while (it.hasNext()) {
                    Map.Entry<String, JsonNode> e = it.next();
                    kv.put(e.getKey(), e.getValue().asText(""));
                }
            }
            JsonNode cd = w.path("crowdingDistance");
            double crowd;
            if (cd.isMissingNode() || cd.isNull())              crowd = Double.NaN;
            else if (cd.isTextual() && "Infinity".equalsIgnoreCase(cd.asText()))
                                                                  crowd = Double.POSITIVE_INFINITY;
            else                                                  crowd = cd.asDouble(Double.NaN);
            winners.add(new Winner(lineNo, score, role, kv, crowd));
        }

        return new BundleSeedAdapter(schemaVersion, generatedAtEpochMs, sourceRunId,
                totalCandidatesObserved, declared, ranges, winners);
    }

    // ── Query API used by MainRefactored / future narrowing strategies ────

    public int winnerCount() { return winners.size(); }

    public Set<Integer> distinctLineNos() {
        Set<Integer> s = new LinkedHashSet<>();
        for (Winner w : winners) s.add(w.lineNo);
        return s;
    }

    /** Winners whose role starts with the given prefix
     *  (e.g. {@code "pareto"}, {@code "champion-min:"}, {@code "balanced:"}). */
    public List<Winner> winnersWithRolePrefix(String prefix) {
        if (prefix == null) return List.copyOf(winners);
        List<Winner> out = new ArrayList<>();
        for (Winner w : winners) if (w.role.startsWith(prefix)) out.add(w);
        return out;
    }

    /** Winners that carry the given metric key in their kvPairs.  Useful for
     *  narrowing strategies that operate per-axis. */
    public List<Winner> winnersForMetric(String metricKey) {
        List<Winner> out = new ArrayList<>();
        for (Winner w : winners) if (w.kvPairs.containsKey(metricKey)) out.add(w);
        return out;
    }

    public Optional<MetricRange> observedRange(String metricKey) {
        return Optional.ofNullable(observedRanges.get(metricKey));
    }

    /** All winners' kvPairs as a flat list, in source order.  Future narrowing
     *  / elitism strategies use this as the seed candidate pool. */
    public List<Map<String, String>> allWinnerKvMaps() {
        List<Map<String, String>> out = new ArrayList<>(winners.size());
        for (Winner w : winners) out.add(w.kvPairs);
        return out;
    }

    /** Short single-line summary suitable for log4j INFO. */
    public String renderSummary() {
        return String.format(Locale.ROOT,
                "BundleSeed[v%d, runId=%s, observed=%d, winners=%d (distinct=%d), "
                        + "declared=%s, observedRanges=%s]",
                schemaVersion, sourceRunId, totalCandidatesObserved,
                winners.size(), distinctLineNos().size(),
                declaredMetrics, observedRanges.keySet());
    }

    // ── Loose numeric coercion (mirrors AnalyzerCore.tryParseNumeric) ─────

    private static final Pattern NUM = Pattern.compile(
            "[-+]?\\d+(?:\\.\\d+)?(?:[eE][-+]?\\d+)?");

    /** Best-effort: direct parse → unit-suffix table → first number substring.
     *  Kept lightweight + Analyzer-free so Core doesn't pick up the analyzer dep. */
    static OptionalDouble parseNumeric(String s) {
        if (s == null || s.isEmpty()) return OptionalDouble.empty();
        String t = s.trim();
        if (t.startsWith("{") || t.startsWith("[")) t = t.substring(1).trim();
        try { return OptionalDouble.of(Double.parseDouble(t)); }
        catch (NumberFormatException ignored) {}
        // Unit suffixes — basic set covering the cases the analyzer also
        // canonicalises.  Result is in "base" units (s / B / 1.0 fraction).
        double[] r = applyUnit(t);
        if (r != null) return OptionalDouble.of(r[0]);
        // Last resort: first numeric substring.
        Matcher m = NUM.matcher(t);
        if (m.find()) {
            try { return OptionalDouble.of(Double.parseDouble(m.group())); }
            catch (NumberFormatException ignored) {}
        }
        return OptionalDouble.empty();
    }

    private static double[] applyUnit(String t) {
        // returns single-element array {value} on success, null otherwise
        String[][] suffixes = {
            {"ms",  "1e-3"},  {"us",  "1e-6"},  {"μs",  "1e-6"},  {"ns",  "1e-9"},
            {"%",   "0.01"},
            {"GiB", "1073741824"}, {"MiB", "1048576"}, {"KiB", "1024"},
            {"GB",  "1e9"},   {"MB",  "1e6"},   {"KB",  "1e3"},
            {"B",   "1"},     {"s",   "1"},
        };
        for (String[] su : suffixes) {
            if (t.length() <= su[0].length()) continue;
            if (!t.endsWith(su[0])) continue;
            String head = t.substring(0, t.length() - su[0].length()).trim();
            try {
                double v = Double.parseDouble(head);
                double mul = Double.parseDouble(su[1]);
                return new double[]{ v * mul };
            } catch (NumberFormatException ignored) {}
        }
        return null;
    }
}
