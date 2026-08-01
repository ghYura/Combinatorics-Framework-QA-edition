package com.yurii.analyzer.core.optimization;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.yurii.analyzer.core.AnalyzerCore;
import com.yurii.analyzer.core.AnalyzerCore.LineResult;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.Set;

/**
 * Tier-3.5 — closed-loop feedback artifact.  The "Master mode" payload that
 * the Analyzer hands back to the Combinatorics Core so the next FW_Seq
 * iteration can narrow generation around the Pareto winners.
 *
 * <p>Contract:</p>
 * <ul>
 *   <li>A list of {@link Winner} entries — every Pareto-front member, every
 *       per-metric champion (argmin / argmax), and every balanced-optimum
 *       pick (weighted-sum / tchebycheff / distance-to-ideal).  Each carries
 *       its {@code lineNo}, {@code score}, the {@code role} that admitted it
 *       to the seed, the candidate's full {@code kvPairs} map, and (when
 *       NSGA-II ran) its {@code crowdingDistance}.</li>
 *   <li>{@link #declaredMetrics} — the goal-axis key set the Analyzer was
 *       running with.  Core uses this to decide which sheets to narrow.</li>
 *   <li>{@link #observedRanges} — corpus min/max/mean/p50 per discovered
 *       metric.  Core uses these to scale the narrowing window
 *       ("generate values within ±σ around the winners' mean").</li>
 *   <li>{@link #generatedAtEpochMs} + {@link #sourceRunId} — provenance.</li>
 * </ul>
 *
 * <p>Serialization is plain Jackson JSON via {@link #toJson()} +
 * {@link #fromJson(JsonNode)} so the Reader-bridge can drop the artifact to
 * a file the next Core run reads from disk, no shared library coupling
 * required.</p>
 *
 * <p>Format-stable: the JSON schema is the inter-process contract between
 * Analyzer and Core.  Backwards-compatible additions only — never remove
 * fields, never change semantics of existing ones.  Producers may add new
 * top-level keys; consumers ignore unknown keys.</p>
 */
public final class BundleSeed {

    /** Single candidate admitted to the seed.  {@code role} explains why:
     *  {@code "pareto"} for raw front membership, {@code "champion-min:<key>"} /
     *  {@code "champion-max:<key>"} for per-metric argmin/argmax,
     *  {@code "balanced:weighted-sum"} / {@code "balanced:tchebycheff"} /
     *  {@code "balanced:distance-to-ideal"} for scalarized picks. */
    public record Winner(
            int lineNo,
            double score,
            String role,
            Map<String, String> kvPairs,
            double crowdingDistance,
            String originalLine,
            String lineType) {

        public JsonNode toJson(ObjectMapper mapper) {
            ObjectNode n = mapper.createObjectNode();
            n.put("lineNo",    lineNo);
            n.put("score",     score);
            n.put("role",      role == null ? "" : role);
            ObjectNode kv = n.putObject("kvPairs");
            if (kvPairs != null) for (Map.Entry<String, String> e : kvPairs.entrySet()) {
                kv.put(e.getKey(), e.getValue() == null ? "" : e.getValue());
            }
            // Encode +∞ as a string sentinel so JSON stays valid; NaN means
            // "not produced by NSGA-II" — emitted as null for cleanliness.
            if (Double.isNaN(crowdingDistance))      { n.putNull("crowdingDistance"); }
            else if (Double.isInfinite(crowdingDistance)) { n.put("crowdingDistance", "Infinity"); }
            else                                     { n.put("crowdingDistance", crowdingDistance); }
            if (originalLine != null) n.put("originalLine", originalLine);
            if (lineType     != null) n.put("lineType",     lineType);
            return n;
        }

        public static Winner fromJson(JsonNode n) {
            int lineNo   = n.path("lineNo").asInt(-1);
            double score = n.path("score").asDouble(Double.NaN);
            String role  = n.path("role").asText("");
            Map<String, String> kv = new LinkedHashMap<>();
            JsonNode kvNode = n.path("kvPairs");
            if (kvNode.isObject()) {
                kvNode.fields().forEachRemaining(e -> kv.put(e.getKey(), e.getValue().asText("")));
            }
            JsonNode cd = n.path("crowdingDistance");
            double crowd;
            if (cd.isMissingNode() || cd.isNull())      crowd = Double.NaN;
            else if (cd.isTextual() && "Infinity".equalsIgnoreCase(cd.asText()))
                                                          crowd = Double.POSITIVE_INFINITY;
            else                                          crowd = cd.asDouble(Double.NaN);
            String originalLine = n.has("originalLine") ? n.path("originalLine").asText("") : null;
            String lineType     = n.has("lineType")     ? n.path("lineType").asText("")     : null;
            return new Winner(lineNo, score, role, kv, crowd, originalLine, lineType);
        }
    }

    /** Per-metric corpus statistics — enough for Core to scale the narrowing
     *  window around winner values without re-running the corpus. */
    public record MetricRange(
            String key,
            long n,
            double min,
            double max,
            double mean,
            double stdev) {

        public JsonNode toJson(ObjectMapper mapper) {
            ObjectNode o = mapper.createObjectNode();
            o.put("key",   key);
            o.put("n",     n);
            o.put("min",   min);
            o.put("max",   max);
            o.put("mean",  mean);
            o.put("stdev", stdev);
            return o;
        }

        public static MetricRange fromJson(JsonNode n) {
            return new MetricRange(
                    n.path("key").asText(""),
                    n.path("n").asLong(0),
                    n.path("min").asDouble(Double.NaN),
                    n.path("max").asDouble(Double.NaN),
                    n.path("mean").asDouble(Double.NaN),
                    n.path("stdev").asDouble(Double.NaN));
        }
    }

    public final List<Winner>             winners;
    public final Set<String>              declaredMetrics;
    public final Map<String, MetricRange> observedRanges;
    public final long                     generatedAtEpochMs;
    public final String                   sourceRunId;
    public final long                     totalCandidatesObserved;

    public BundleSeed(List<Winner> winners,
                       Set<String> declaredMetrics,
                       Map<String, MetricRange> observedRanges,
                       long generatedAtEpochMs,
                       String sourceRunId,
                       long totalCandidatesObserved) {
        this.winners                  = (winners == null) ? List.of() : List.copyOf(winners);
        this.declaredMetrics          = (declaredMetrics == null) ? Set.of() : Set.copyOf(declaredMetrics);
        this.observedRanges           = (observedRanges == null) ? Map.of() : Map.copyOf(observedRanges);
        this.generatedAtEpochMs       = generatedAtEpochMs;
        this.sourceRunId              = sourceRunId == null ? "" : sourceRunId;
        this.totalCandidatesObserved  = totalCandidatesObserved;
    }

    /** Reverse of {@link #toJson()} — tolerant to missing fields and unknown
     *  top-level keys for forward compatibility. */
    public static BundleSeed fromJson(JsonNode root) {
        if (root == null || !root.isObject()) {
            return new BundleSeed(List.of(), Set.of(), Map.of(), 0L, "", 0L);
        }
        List<Winner> w = new ArrayList<>();
        JsonNode arr = root.path("winners");
        if (arr.isArray()) for (JsonNode n : arr) w.add(Winner.fromJson(n));
        Set<String> declared = new LinkedHashSet<>();
        JsonNode dm = root.path("declaredMetrics");
        if (dm.isArray()) for (JsonNode n : dm) declared.add(n.asText(""));
        Map<String, MetricRange> ranges = new LinkedHashMap<>();
        JsonNode ro = root.path("observedRanges");
        if (ro.isObject()) ro.fields().forEachRemaining(e ->
                ranges.put(e.getKey(), MetricRange.fromJson(e.getValue())));
        return new BundleSeed(
                w,
                declared,
                ranges,
                root.path("generatedAtEpochMs").asLong(0L),
                root.path("sourceRunId").asText(""),
                root.path("totalCandidatesObserved").asLong(0L));
    }

    public JsonNode toJson() {
        ObjectMapper mapper = AnalyzerCore.mapper();
        ObjectNode root = mapper.createObjectNode();
        root.put("schemaVersion", 1);
        root.put("generatedAtEpochMs", generatedAtEpochMs);
        if (!sourceRunId.isEmpty()) root.put("sourceRunId", sourceRunId);
        root.put("totalCandidatesObserved", totalCandidatesObserved);

        ArrayNode declared = root.putArray("declaredMetrics");
        for (String k : declaredMetrics) declared.add(k);

        ObjectNode ranges = root.putObject("observedRanges");
        for (Map.Entry<String, MetricRange> e : observedRanges.entrySet()) {
            ranges.set(e.getKey(), e.getValue().toJson(mapper));
        }

        ArrayNode wArr = root.putArray("winners");
        for (Winner w : winners) wArr.add(w.toJson(mapper));
        return root;
    }

    /** Write to disk as pretty-printed JSON.  Path parent is auto-created if
     *  missing (so the property-driven path doesn't fail on first run). */
    public void writeToFile(Path path) throws IOException {
        if (path == null) throw new IllegalArgumentException("path must be non-null");
        if (path.getParent() != null) Files.createDirectories(path.getParent());
        String json = AnalyzerCore.mapper()
                .writerWithDefaultPrettyPrinter()
                .writeValueAsString(toJson());
        Files.writeString(path, json, StandardCharsets.UTF_8);
    }

    public static BundleSeed readFromFile(Path path) throws IOException {
        if (path == null) throw new IllegalArgumentException("path must be non-null");
        String json = Files.readString(path, StandardCharsets.UTF_8);
        JsonNode root = AnalyzerCore.mapper().readTree(json);
        return fromJson(root);
    }

    /**
     * Extract a {@link BundleSeed} from an aggregator {@link OnlineMetricAggregator.Snapshot}.
     *
     * <p>Winners are collected from three sources, in order:</p>
     * <ol>
     *   <li>Every {@code paretoFront} member — role tag includes crowding
     *       distance when the analyzer ran with NSGA-II.</li>
     *   <li>Per-metric champions — for every key with finite argmin/argmax,
     *       emit one {@code champion-min:<key>} and one {@code champion-max:<key>}
     *       winner pointing at the line whose value hit that extremum.</li>
     *   <li>Balanced-optimum picks — {@link BalancedOptimumSelector#all} run
     *       on the front; one winner per strategy tagged {@code balanced:<name>}.</li>
     * </ol>
     *
     * <p>Same {@code lineNo} can appear under multiple roles — Core decides
     * how to dedup.  The seed is intentionally redundant so Core can pick the
     * narrowing strategy without losing information.</p>
     *
     * @param snapshot   the post-stream snapshot
     * @param sourceRunId optional traceability tag; {@code null} → empty
     * @param crowdingByLineNo optional NSGA-II crowding-distance map; pass
     *                         {@code null} or empty to leave winners' crowding as
     *                         {@link Double#NaN}
     */
    public static BundleSeed fromSnapshot(OnlineMetricAggregator.Snapshot snapshot,
                                           String sourceRunId,
                                           Map<Integer, Double> crowdingByLineNo) {
        if (snapshot == null) {
            return new BundleSeed(List.of(), Set.of(), Map.of(),
                    System.currentTimeMillis(),
                    sourceRunId == null ? "" : sourceRunId, 0L);
        }
        Map<Integer, Double> crowd = (crowdingByLineNo == null)
                ? Map.of() : crowdingByLineNo;

        List<Winner> winners = new ArrayList<>();

        // 1. Pareto-front winners.
        for (LineResult r : snapshot.paretoFront()) {
            winners.add(toWinner(r, "pareto",
                    crowd.getOrDefault(r.lineNo, Double.NaN)));
        }

        // 2. Per-metric champions — argmin / argmax of every observed stream
        //    whose KeyStats carry a recorded extremum line.  We look up the
        //    LineResult in either the paretoFront or topByScore lists; if not
        //    found, emit a sparse winner with just lineNo + value.
        Map<Integer, LineResult> byLine = new LinkedHashMap<>();
        for (LineResult r : snapshot.paretoFront()) byLine.put(r.lineNo, r);
        for (LineResult r : snapshot.topByScore())  byLine.putIfAbsent(r.lineNo, r);

        for (Map.Entry<String, OnlineMetricAggregator.KeyStats> e :
                snapshot.perKeyStats().entrySet()) {
            String key = e.getKey();
            OnlineMetricAggregator.KeyStats ks = e.getValue();
            if (ks == null || ks.n <= 0) continue;
            // argmin
            if (Double.isFinite(ks.min) && ks.argminLineNo > 0) {
                LineResult r = byLine.get(ks.argminLineNo);
                winners.add(toWinnerOrSparse(r, ks.argminLineNo, "champion-min:" + key,
                        Double.NaN, key, ks.min));
            }
            // argmax
            if (Double.isFinite(ks.max) && ks.argmaxLineNo > 0
                    && ks.argmaxLineNo != ks.argminLineNo) {
                LineResult r = byLine.get(ks.argmaxLineNo);
                winners.add(toWinnerOrSparse(r, ks.argmaxLineNo, "champion-max:" + key,
                        Double.NaN, key, ks.max));
            }
        }

        // 3. Balanced-optimum picks — run all 3 scalarization strategies on
        //    the front using the effective goal set.
        List<GoalSpec> effective = snapshot.effectiveGoals();
        if (!effective.isEmpty() && !snapshot.paretoFront().isEmpty()) {
            for (BalancedOptimumSelector.Selection sel :
                    BalancedOptimumSelector.all(snapshot.paretoFront(),
                            snapshot.perKeyStats(), effective)) {
                if (sel.chosen() == null) continue;
                winners.add(toWinner(sel.chosen(),
                        "balanced:" + sel.strategy(),
                        crowd.getOrDefault(sel.chosen().lineNo, Double.NaN)));
            }
        }

        // declaredMetrics = explicit goals' keys.
        Set<String> declared = new LinkedHashSet<>();
        for (GoalSpec g : snapshot.goals()) declared.add(g.key());

        // observedRanges = per-key stats projected into the public schema.
        Map<String, MetricRange> ranges = new LinkedHashMap<>();
        for (Map.Entry<String, OnlineMetricAggregator.KeyStats> e :
                snapshot.perKeyStats().entrySet()) {
            OnlineMetricAggregator.KeyStats ks = e.getValue();
            if (ks == null || ks.n <= 0) continue;
            ranges.put(e.getKey(), new MetricRange(
                    e.getKey(), ks.n, ks.min, ks.max, ks.mean, ks.stdev()));
        }

        return new BundleSeed(winners, declared, ranges,
                System.currentTimeMillis(),
                sourceRunId == null ? "" : sourceRunId,
                snapshot.updates());
    }

    /** Convenience: same as the 3-arg overload with no crowding map. */
    public static BundleSeed fromSnapshot(OnlineMetricAggregator.Snapshot snapshot,
                                           String sourceRunId) {
        return fromSnapshot(snapshot, sourceRunId, Map.of());
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private static Winner toWinner(LineResult r, String role, double crowdingDistance) {
        Map<String, String> kv = (r.features == null) ? Map.of() : r.features.kvPairs;
        String lt = (r.features == null) ? null : r.features.lineType;
        return new Winner(r.lineNo, r.score, role, kv, crowdingDistance,
                r.originalLine, lt);
    }

    /** Fallback when the champion's lineNo wasn't surfaced in paretoFront
     *  or topByScore — we still emit the lineNo + the single key=value that
     *  earned it the champion role, so Core has something to narrow on. */
    private static Winner toWinnerOrSparse(LineResult r, int lineNo, String role,
                                            double crowd, String championKey, double championValue) {
        if (r != null) return toWinner(r, role, crowd);
        Map<String, String> kv = new LinkedHashMap<>();
        kv.put(championKey, formatNumeric(championValue));
        return new Winner(lineNo, Double.NaN, role, kv, crowd, null, null);
    }

    private static String formatNumeric(double v) {
        if (Double.isNaN(v))     return "NaN";
        if (Double.isInfinite(v))return (v > 0 ? "Infinity" : "-Infinity");
        // Mirrors the analyzer's other places: %.6g-ish without trailing zeros.
        if (v == Math.rint(v) && Math.abs(v) < 1e15)
            return String.valueOf((long) v);
        return String.valueOf(v);
    }

    /** Number of winners across all roles. */
    public int size() { return winners.size(); }

    /** Distinct lineNos across all roles (a candidate may appear with multiple roles). */
    public Set<Integer> distinctLineNos() {
        Set<Integer> s = new LinkedHashSet<>();
        for (Winner w : winners) s.add(w.lineNo);
        return s;
    }

    /** Convenience accessor: all winners whose role starts with the given prefix. */
    public List<Winner> winnersWithRolePrefix(String prefix) {
        if (prefix == null) return List.copyOf(winners);
        List<Winner> out = new ArrayList<>();
        for (Winner w : winners) if (w.role != null && w.role.startsWith(prefix)) out.add(w);
        return out;
    }

    /** Quick numeric coercion of a winner's kv value, mirroring the analyzer's
     *  {@code tryParseNumeric}.  Returns empty when the key is absent or the
     *  value isn't numeric-coercible — Core can fall back to its own parsing. */
    public OptionalDouble numericValue(Winner w, String key) {
        if (w == null || key == null || w.kvPairs == null) return OptionalDouble.empty();
        String v = w.kvPairs.get(key);
        if (v == null) return OptionalDouble.empty();
        return AnalyzerCore.tryParseNumeric(v);
    }
}
