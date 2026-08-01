package com.yurii.analyzer.core;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.yurii.analyzer.core.optimization.ExprParser;
import com.yurii.analyzer.core.optimization.Optimizers;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.*;
import java.util.*;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.DoubleUnaryOperator;
import java.util.function.ToDoubleFunction;
import java.util.regex.MatchResult;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Heuristic analyzer core.
 *
 * Public surface (preserved from legacy): patterns, defaults, helper statics,
 * {@link LineFeatures}, {@link CorpusProfile}, {@link SynthesizedRules},
 * {@link LineResult}, {@link LineTask}, {@link AnalysisSettings},
 * {@link AnalysisContext}, {@link AnalysisListener}, {@link OptimizationGoal},
 * {@link OptimizationAnalyzer}, {@link DatabaseManager},
 * {@link UniversalDynamicOptimizer}.
 *
 * Internals rebuilt for: streaming statistics (Welford), bounded top-K selection,
 * single-pass character classification, percentile-clamped robust normalization,
 * thread-safe multi-worker pipelines, env-driven DB config (no destructive boot),
 * cached Python helper script for the dynamic optimizer.
 */
public final class AnalyzerCore {
    private AnalyzerCore() {}

    // ─── Defaults ────────────────────────────────────────────────────────
    public static final int DEFAULT_MIN_SUPPORT = 3;
    public static final int DEFAULT_TOP_K = 12;
    public static final double DEFAULT_OPT_THRESHOLD = 75.0;
    public static final double DEFAULT_WATCH_THRESHOLD = 45.0;
    public static final double DEFAULT_COMMAND_TIMEOUT = 30.0;
    public static final int DEFAULT_WORKERS = Math.max(2, Runtime.getRuntime().availableProcessors() - 1);
    public static final int DEFAULT_QUEUE_CAPACITY = 10_000;

    // ─── Patterns ────────────────────────────────────────────────────────
    public static final Pattern NUMBER_RE = Pattern.compile(
            "(?<!\\w)[-+]?(?:\\d+(?:[.,]\\d+)?|\\d*\\.\\d+)(?:[eE][-+]?\\d+)?");
    public static final Pattern TOKEN_RE = Pattern.compile("\\b\\w+\\b", Pattern.UNICODE_CHARACTER_CLASS);
    // Fixed: value class must also exclude whitespace, otherwise the first K/V
    // pair greedily eats the rest of a multi-pair line and the result is always
    // {kv.size() == 1}. The legacy regex permitted spaces in values, which made
    // 'k1=v1 k2=v2' match as a single pair {k1: "v1 k2=v2"}. After this fix
    // multi-pair telemetry lines are classified as 'kv_numeric' as intended.
    public static final Pattern KV_PAIR_RE = Pattern.compile(
            "([A-Za-zА-Яа-я_][\\w.\\-]*)\\s*[:=]\\s*([^\\s;|,\\]\\)\\}]+)",
            Pattern.UNICODE_CHARACTER_CLASS);
    // Fixed: alternation requires `|`. The legacy `\|` matched a literal pipe so the
    // pattern almost never fired and `placeholder_count` was effectively always 0.
    public static final Pattern PLACEHOLDER_RE = Pattern.compile(
            "\\$\\{[^}]+}|\\{\\{[^}]+}}|\\[[^\\]]+]|<[^>]+>");
    public static final Pattern COMMENT_RE = Pattern.compile("^\\s*(#|//)");

    public static final Set<String> STOPWORDS = Set.of(
            "and","or","the","a","an","to","of","in","on","for","with","by",
            "is","are","was","were","be","this","that","it","as","at","from",
            "not","no","if","then","else","when","while","into","over","under",
            "и","в","на","для","по","с","к","что","это","как","или","не",
            "да","нет","то","же","ли","бы","а","но"
    );

    private static final ObjectMapper MAPPER = new ObjectMapper();

    // DB credentials are sourced from env vars; the legacy hardcoded values
    // are only the fallback for local development.
    private static final String DB_URL  = envOr("ANALYZER_DB_URL",  "jdbc:postgresql://localhost:5433/analyzeMeDB");
    private static final String DB_USER = envOr("ANALYZER_DB_USER", "postgres");
    private static final String DB_PASS = envOr("ANALYZER_DB_PASS", "pass");

    private static String envOr(String key, String fallback) {
        String v = System.getenv(key);
        return v == null || v.isBlank() ? fallback : v;
    }

    // ─── Public numeric helpers (legacy API, kept) ───────────────────────
    public static double clamp(double v, double lo, double hi) { return Math.max(lo, Math.min(hi, v)); }

    public static double safeDouble(Object text, double defaultValue) {
        if (text == null) return defaultValue;
        String s = String.valueOf(text).replace(',', '.').trim();
        if (s.isEmpty() || "null".equalsIgnoreCase(s)) return defaultValue;
        try { return Double.parseDouble(s); } catch (NumberFormatException e) { return defaultValue; }
    }

    public static int safeInt(Object text, int defaultValue) {
        if (text == null) return defaultValue;
        String s = String.valueOf(text).replace(',', '.').trim();
        if (s.isEmpty() || "null".equalsIgnoreCase(s)) return defaultValue;
        try { return Integer.parseInt(s); } catch (NumberFormatException ignored) {}
        try { return (int) Double.parseDouble(s); } catch (NumberFormatException e) { return defaultValue; }
    }

    /**
     * Best-effort numeric extraction from a K=V value captured by the parser.
     *
     * Programs in the wild emit numbers wrapped in unit suffixes ({@code 0.5s},
     * {@code 18976B}, {@code 1.2MiB}, {@code 5.7%}) and inside truncated
     * collection literals ({@code (3,0,0)} survives the regex as {@code (3}).
     * Naive {@code Double.parseDouble} drops every such value. This helper:
     *   1. trims, replaces ',' → '.' and strips a leading '(' / '[' / '{';
     *   2. tries direct parse;
     *   3. tries stripping a trailing unit suffix (longest match first) and
     *      multiplying by the unit's SI scale;
     *   4. as a last resort, finds the first {@link #NUMBER_RE}-style number
     *      inside the string.
     *
     * Time units canonicalise to seconds; memory units to bytes; percent to
     * fractional. Returns an empty optional only when no number can be salvaged.
     */
    public static java.util.OptionalDouble tryParseNumeric(String value) {
        if (value == null) return java.util.OptionalDouble.empty();
        String s = value.replace(',', '.').trim();
        // strip leading collection openers — survives truncated tuples like "(3"
        while (!s.isEmpty() && (s.charAt(0) == '(' || s.charAt(0) == '['
                || s.charAt(0) == '{' || s.charAt(0) == '"' || s.charAt(0) == '\'')) {
            s = s.substring(1);
        }
        if (s.isEmpty() || "null".equalsIgnoreCase(s) || "none".equalsIgnoreCase(s)
                || "nan".equalsIgnoreCase(s)) return java.util.OptionalDouble.empty();

        // 1. direct parse
        try { return java.util.OptionalDouble.of(Double.parseDouble(s)); }
        catch (NumberFormatException ignored) {}

        // 2. unit suffix — longest first so "MiB" beats "B"
        for (String[] u : NUMERIC_UNITS) {
            if (s.length() > u[0].length() && s.endsWith(u[0])) {
                String num = s.substring(0, s.length() - u[0].length()).trim();
                try {
                    double v = Double.parseDouble(num) * Double.parseDouble(u[1]);
                    if (Double.isFinite(v)) return java.util.OptionalDouble.of(v);
                } catch (NumberFormatException ignored) {}
            }
        }

        // 3. fall back: first NUMBER_RE-looking substring (handles "(3, 0" → 3,
        //     "Score: 5/10" → 5, etc.)
        java.util.regex.Matcher m = NUMBER_RE.matcher(s);
        if (m.find()) {
            try {
                double v = Double.parseDouble(m.group());
                if (Double.isFinite(v)) return java.util.OptionalDouble.of(v);
            } catch (NumberFormatException ignored) {}
        }
        return java.util.OptionalDouble.empty();
    }

    /** Sorted longest-first so {@link #tryParseNumeric} picks "MiB" before "B". */
    private static final String[][] NUMERIC_UNITS = {
            {"GiB", "1.073741824e9"},
            {"MiB", "1.048576e6"},
            {"KiB", "1024.0"},
            {"GB",  "1.0e9"},
            {"MB",  "1.0e6"},
            {"KB",  "1.0e3"},
            {"ms",  "1.0e-3"},
            {"μs", "1.0e-6"}, // μs
            {"us",  "1.0e-6"},
            {"ns",  "1.0e-9"},
            {"%",   "0.01"},
            {"B",   "1.0"},
            {"s",   "1.0"},
    };

    public static double mean(List<Double> values) {
        if (values == null || values.isEmpty()) return 0.0;
        double sum = 0.0;
        for (double v : values) sum += v;
        return sum / values.size();
    }

    public static double median(List<Double> values) {
        if (values == null || values.isEmpty()) return 0.0;
        double[] a = new double[values.size()];
        for (int i = 0; i < a.length; i++) a[i] = values.get(i);
        Arrays.sort(a);
        int n = a.length;
        return n % 2 == 1 ? a[n / 2] : (a[n / 2 - 1] + a[n / 2]) / 2.0;
    }

    public static double pstdev(List<Double> values) {
        if (values == null || values.size() < 2) return 0.0;
        double m = mean(values), acc = 0.0;
        for (double v : values) { double d = v - m; acc += d * d; }
        return Math.sqrt(acc / values.size());
    }

    public static double percentile(List<Double> values, double p) {
        if (values == null || values.isEmpty()) return 0.0;
        double[] a = new double[values.size()];
        for (int i = 0; i < a.length; i++) a[i] = values.get(i);
        Arrays.sort(a);
        if (a.length == 1) return a[0];
        p = clamp(p, 0.0, 100.0);
        double k = (a.length - 1) * (p / 100.0);
        int f = (int) Math.floor(k), c = (int) Math.ceil(k);
        if (f == c) return a[(int) k];
        return a[f] * (c - k) + a[c] * (k - f);
    }

    /** Single-pass Shannon entropy with ASCII fast-path; non-ASCII handled via lazy map. */
    public static double charEntropy(String text) {
        if (text == null || text.isEmpty()) return 0.0;
        int[] ascii = new int[128];
        Map<Integer, Integer> ext = null;
        int n = 0, len = text.length();
        for (int i = 0; i < len; ) {
            int cp = text.codePointAt(i);
            if (cp < 128) ascii[cp]++;
            else { if (ext == null) ext = new HashMap<>(); ext.merge(cp, 1, Integer::sum); }
            i += Character.charCount(cp);
            n++;
        }
        if (n == 0) return 0.0;
        final double inv = 1.0 / n;
        final double invLog2 = 1.0 / Math.log(2);
        double entropy = 0.0;
        for (int c : ascii) if (c > 0) { double p = c * inv; entropy -= p * Math.log(p) * invLog2; }
        if (ext != null) for (int c : ext.values()) { double p = c * inv; entropy -= p * Math.log(p) * invLog2; }
        return entropy;
    }

    public static String compressSignature(String text) {
        if (text == null || text.isEmpty()) return "";
        StringBuilder sb = new StringBuilder();
        char prev = 0;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            char cur = Character.isDigit(ch) ? 'D'
                     : Character.isLetter(ch) ? 'L'
                     : Character.isWhitespace(ch) ? 'S' : 'P';
            if (cur != prev) { sb.append(cur); prev = cur; }
        }
        return sb.toString();
    }

    public static String canonicalNumber(double n) {
        if (Math.abs(n - Math.rint(n)) < 1e-9) return String.valueOf((long) Math.round(n));
        return String.format(Locale.ROOT, "%.3f", n);
    }

    public static String toPrettyJson(Object value) throws IOException {
        return MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(value);
    }

    public static ObjectMapper mapper() { return MAPPER; }

    public static JsonNode parseManualConfig(String textOrPath) throws IOException {
        if (textOrPath == null || textOrPath.isBlank()) return MAPPER.createObjectNode();
        String raw = textOrPath;
        try {
            Path p = Path.of(textOrPath);
            if (Files.exists(p)) raw = Files.readString(p, StandardCharsets.UTF_8);
        } catch (Exception ignored) {}
        JsonNode node = MAPPER.readTree(raw);
        if (!node.isObject()) throw new IllegalArgumentException("Manual config must be a JSON object");
        return node;
    }

    public static List<String> jsonArray(JsonNode node, String field) {
        if (node == null || !node.has(field) || !node.get(field).isArray()) return List.of();
        ArrayList<String> out = new ArrayList<>();
        for (JsonNode item : node.get(field)) out.add(item.asText());
        return out;
    }

    public static Map<String, Double> jsonMapDouble(JsonNode node, String field) {
        if (node == null || !node.has(field) || !node.get(field).isObject()) return Map.of();
        Map<String, Double> out = new LinkedHashMap<>();
        for (Map.Entry<String, JsonNode> e : node.get(field).properties())
            out.put(e.getKey(), e.getValue().asDouble(1.0));
        return out;
    }

    public static Map<String, Object> jsonMapObject(JsonNode node, String field) {
        if (node == null || !node.has(field) || !node.get(field).isObject()) return Map.of();
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<String, JsonNode> e : node.get(field).properties())
            out.put(e.getKey(), e.getValue().isNumber() ? e.getValue().numberValue() : e.getValue().asText());
        return out;
    }

    // ─── Streaming-stats primitives ──────────────────────────────────────

    /** Welford online mean / population variance — single pass, O(1) memory, numerically stable. */
    static final class Welford {
        long n;
        double mean;
        double m2;

        void add(double v) {
            n++;
            double d = v - mean;
            mean += d / n;
            m2 += d * (v - mean);
        }

        double variance() { return n < 2 ? 0.0 : m2 / n; }
        double stdev() { return Math.sqrt(variance()); }

        void merge(Welford o) {
            if (o.n == 0) return;
            if (n == 0) { n = o.n; mean = o.mean; m2 = o.m2; return; }
            long total = n + o.n;
            double delta = o.mean - mean;
            double newMean = (mean * n + o.mean * o.n) / total;
            m2 = m2 + o.m2 + delta * delta * ((double) n * o.n) / total;
            mean = newMean;
            n = total;
        }
    }

    /** Bounded min-heap top-K selector: O(N log K) instead of O(N log N) full-sort. */
    static <K> List<Map.Entry<K, Integer>> topK(Map<K, Integer> source, int k, int minSupport) {
        if (source == null || source.isEmpty() || k <= 0) return List.of();
        PriorityQueue<Map.Entry<K, Integer>> heap = new PriorityQueue<>(k + 1,
                Comparator.comparingInt(Map.Entry::getValue));
        for (Map.Entry<K, Integer> e : source.entrySet()) {
            if (e.getValue() < minSupport) continue;
            if (heap.size() < k) heap.offer(e);
            else if (heap.peek().getValue() < e.getValue()) {
                heap.poll();
                heap.offer(e);
            }
        }
        List<Map.Entry<K, Integer>> out = new ArrayList<>(heap);
        out.sort((a, b) -> Integer.compare(b.getValue(), a.getValue()));
        return out;
    }

    /** Sort entries descending by count; stable, fast path uses primitive arrays. */
    static <K> Map<K, Integer> sortDescByCount(Map<K, Integer> map) {
        if (map == null || map.isEmpty()) return new LinkedHashMap<>();
        @SuppressWarnings("unchecked")
        Map.Entry<K, Integer>[] entries = map.entrySet().toArray(new Map.Entry[0]);
        Arrays.sort(entries, (a, b) -> Integer.compare(b.getValue(), a.getValue()));
        Map<K, Integer> out = new LinkedHashMap<>(entries.length * 4 / 3 + 1);
        for (Map.Entry<K, Integer> e : entries) out.put(e.getKey(), e.getValue());
        return out;
    }

    /** Single-pass character classifier (counts + entropy together). */
    static final class CharStats {
        long alpha, digit, space, punct, upper;
        int total;
        double entropy;

        static CharStats of(String text) {
            CharStats s = new CharStats();
            if (text == null || text.isEmpty()) return s;
            int[] ascii = new int[128];
            Map<Integer, Integer> ext = null;
            int len = text.length();
            for (int i = 0; i < len; ) {
                int cp = text.codePointAt(i);
                if (Character.isDigit(cp)) s.digit++;
                if (Character.isLetter(cp)) s.alpha++;
                if (Character.isWhitespace(cp)) s.space++;
                if (Character.isUpperCase(cp)) s.upper++;
                if (!Character.isLetterOrDigit(cp) && !Character.isWhitespace(cp)) s.punct++;
                if (cp < 128) ascii[cp]++;
                else { if (ext == null) ext = new HashMap<>(); ext.merge(cp, 1, Integer::sum); }
                i += Character.charCount(cp);
                s.total++;
            }
            if (s.total == 0) return s;
            final double inv = 1.0 / s.total;
            final double invLog2 = 1.0 / Math.log(2);
            double e = 0.0;
            for (int c : ascii) if (c > 0) { double p = c * inv; e -= p * Math.log(p) * invLog2; }
            if (ext != null) for (int c : ext.values()) { double p = c * inv; e -= p * Math.log(p) * invLog2; }
            s.entropy = e;
            return s;
        }
    }

    // ─── Domain types (legacy API, preserved) ────────────────────────────

    public static final class LineFeatures {
        public final int lineNo;
        public final String raw;
        public final String originalLine;
        public final String text;
        public final int length;
        public final List<String> tokens;
        public final List<String> tokenLowers;
        public final List<Double> numbers;
        public final Map<String, String> kvPairs;
        public final Map<String, Integer> delimiters;
        public final int placeholderCount;
        public final double entropy;
        public final double alphaRatio;
        public final double digitRatio;
        public final double spaceRatio;
        public final double punctRatio;
        public final double uppercaseRatio;
        public final double uniqueTokenRatio;
        public final String signature;
        public final String prefix;
        public final String suffix;
        public final String lineType;

        public LineFeatures(int lineNo, String raw, String originalLine, String text, int length,
                            List<String> tokens, List<String> tokenLowers, List<Double> numbers,
                            Map<String, String> kvPairs, Map<String, Integer> delimiters, int placeholderCount,
                            double entropy, double alphaRatio, double digitRatio, double spaceRatio,
                            double punctRatio, double uppercaseRatio, double uniqueTokenRatio,
                            String signature, String prefix, String suffix, String lineType) {
            this.lineNo = lineNo;
            this.raw = raw;
            this.originalLine = originalLine;
            this.text = text;
            this.length = length;
            this.tokens = tokens;
            this.tokenLowers = tokenLowers;
            this.numbers = numbers;
            this.kvPairs = kvPairs;
            this.delimiters = delimiters;
            this.placeholderCount = placeholderCount;
            this.entropy = entropy;
            this.alphaRatio = alphaRatio;
            this.digitRatio = digitRatio;
            this.spaceRatio = spaceRatio;
            this.punctRatio = punctRatio;
            this.uppercaseRatio = uppercaseRatio;
            this.uniqueTokenRatio = uniqueTokenRatio;
            this.signature = signature;
            this.prefix = prefix;
            this.suffix = suffix;
            this.lineType = lineType;
        }

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("line_no", lineNo);
            m.put("raw", raw);
            m.put("original_line", originalLine);
            m.put("text", text);
            m.put("length", length);
            m.put("tokens", tokens);
            m.put("token_lowers", tokenLowers);
            m.put("numbers", numbers);
            m.put("kv_pairs", kvPairs);
            m.put("delimiters", delimiters);
            m.put("placeholder_count", placeholderCount);
            m.put("entropy", entropy);
            m.put("alpha_ratio", alphaRatio);
            m.put("digit_ratio", digitRatio);
            m.put("space_ratio", spaceRatio);
            m.put("punct_ratio", punctRatio);
            m.put("uppercase_ratio", uppercaseRatio);
            m.put("unique_token_ratio", uniqueTokenRatio);
            m.put("signature", signature);
            m.put("prefix", prefix);
            m.put("suffix", suffix);
            m.put("line_type", lineType);
            return m;
        }
    }

    public static final class CorpusProfile {
        public int totalLines;
        public int nonemptyLines;
        public int emptyLines;
        public double lengthMean;
        public double lengthMedian;
        public double lengthP10;
        public double lengthP90;
        public double lengthStdev;
        public double entropyMean;
        public double entropyMedian;
        public double entropyP10;
        public double entropyP90;
        public double entropyStdev;
        public Map<String, Integer> tokenFrequency = new LinkedHashMap<>();
        public Map<String, Integer> keyFrequency = new LinkedHashMap<>();
        public Map<String, Integer> numberFrequency = new LinkedHashMap<>();
        public Map<String, Integer> signatureFrequency = new LinkedHashMap<>();
        public Map<String, Integer> lineTypeFrequency = new LinkedHashMap<>();
        public List<String> commonTokens = new ArrayList<>();
        public List<String> commonKeys = new ArrayList<>();
        public List<String> commonNumbers = new ArrayList<>();
        public String dominantLineType = "";
        public String dominantSignature = "";

        public Map<String, Double> optMetricMin = new LinkedHashMap<>();
        public Map<String, Double> optMetricMax = new LinkedHashMap<>();
        public Map<String, Integer> optMetricCount = new LinkedHashMap<>();
        // Robust normalization bands (5th / 95th percentile): outlier-stable.
        public Map<String, Double> optMetricLow = new LinkedHashMap<>();
        public Map<String, Double> optMetricHigh = new LinkedHashMap<>();

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("total_lines", totalLines);
            m.put("nonempty_lines", nonemptyLines);
            m.put("empty_lines", emptyLines);
            m.put("length_mean", lengthMean);
            m.put("length_median", lengthMedian);
            m.put("length_p10", lengthP10);
            m.put("length_p90", lengthP90);
            m.put("length_stdev", lengthStdev);
            m.put("entropy_mean", entropyMean);
            m.put("entropy_median", entropyMedian);
            m.put("entropy_p10", entropyP10);
            m.put("entropy_p90", entropyP90);
            m.put("entropy_stdev", entropyStdev);
            m.put("token_frequency", tokenFrequency);
            m.put("key_frequency", keyFrequency);
            m.put("number_frequency", numberFrequency);
            m.put("signature_frequency", signatureFrequency);
            m.put("line_type_frequency", lineTypeFrequency);
            m.put("common_tokens", commonTokens);
            m.put("common_keys", commonKeys);
            m.put("common_numbers", commonNumbers);
            m.put("dominant_line_type", dominantLineType);
            m.put("dominant_signature", dominantSignature);
            m.put("opt_metric_min", optMetricMin);
            m.put("opt_metric_max", optMetricMax);
            m.put("opt_metric_count", optMetricCount);
            m.put("opt_metric_low_p5", optMetricLow);
            m.put("opt_metric_high_p95", optMetricHigh);
            return m;
        }
    }

    public static final class SynthesizedRules {
        public final String dominantLineType;
        public final String dominantSignature;
        public final List<String> topTokens;
        public final List<String> topKeys;
        public final List<String> topNumbers;
        public final Map<String, Integer> lineTypeSupport;
        public final Map<String, Integer> signatureSupport;
        public final Map<String, Integer> tokenSupport;
        public final Map<String, Integer> keySupport;
        public final Map<String, Integer> numberSupport;
        public final double lengthMedian;
        public final double lengthP10;
        public final double lengthP90;
        public final double entropyMedian;
        public final double entropyP10;
        public final double entropyP90;
        public final int tokenDfCutoff;
        public final int numberDfCutoff;
        public final double confidence;

        public SynthesizedRules(String dominantLineType, String dominantSignature, List<String> topTokens,
                                List<String> topKeys, List<String> topNumbers,
                                Map<String, Integer> lineTypeSupport, Map<String, Integer> signatureSupport,
                                Map<String, Integer> tokenSupport, Map<String, Integer> keySupport,
                                Map<String, Integer> numberSupport, double lengthMedian, double lengthP10,
                                double lengthP90, double entropyMedian, double entropyP10, double entropyP90,
                                int tokenDfCutoff, int numberDfCutoff, double confidence) {
            this.dominantLineType = dominantLineType;
            this.dominantSignature = dominantSignature;
            this.topTokens = topTokens;
            this.topKeys = topKeys;
            this.topNumbers = topNumbers;
            this.lineTypeSupport = lineTypeSupport;
            this.signatureSupport = signatureSupport;
            this.tokenSupport = tokenSupport;
            this.keySupport = keySupport;
            this.numberSupport = numberSupport;
            this.lengthMedian = lengthMedian;
            this.lengthP10 = lengthP10;
            this.lengthP90 = lengthP90;
            this.entropyMedian = entropyMedian;
            this.entropyP10 = entropyP10;
            this.entropyP90 = entropyP90;
            this.tokenDfCutoff = tokenDfCutoff;
            this.numberDfCutoff = numberDfCutoff;
            this.confidence = confidence;
        }

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("dominant_line_type", dominantLineType);
            m.put("dominant_signature", dominantSignature);
            m.put("top_tokens", topTokens);
            m.put("top_keys", topKeys);
            m.put("top_numbers", topNumbers);
            m.put("line_type_support", lineTypeSupport);
            m.put("signature_support", signatureSupport);
            m.put("token_support", tokenSupport);
            m.put("key_support", keySupport);
            m.put("number_support", numberSupport);
            m.put("length_median", lengthMedian);
            m.put("length_p10", lengthP10);
            m.put("length_p90", lengthP90);
            m.put("entropy_median", entropyMedian);
            m.put("entropy_p10", entropyP10);
            m.put("entropy_p90", entropyP90);
            m.put("token_df_cutoff", tokenDfCutoff);
            m.put("number_df_cutoff", numberDfCutoff);
            m.put("confidence", confidence);
            return m;
        }
    }

    public static final class LineResult {
        public final int lineNo;
        public final String originalLine;
        public final String raw;
        public final LineFeatures features;
        public final double score;
        public final String decision;
        public final Map<String, Double> breakdown;
        public final List<String> notes;
        public final List<String> matchedRules;

        public LineResult(int lineNo, String originalLine, String raw, LineFeatures features, double score,
                          String decision, Map<String, Double> breakdown, List<String> notes,
                          List<String> matchedRules) {
            this.lineNo = lineNo;
            this.originalLine = originalLine;
            this.raw = raw;
            this.features = features;
            this.score = score;
            this.decision = decision;
            this.breakdown = breakdown;
            this.notes = notes;
            this.matchedRules = matchedRules;
        }

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("line_no", lineNo);
            m.put("original_line", originalLine);
            m.put("raw", raw);
            m.put("score", score);
            m.put("decision", decision);
            m.put("breakdown", breakdown);
            m.put("notes", notes);
            m.put("matched_rules", matchedRules);
            m.put("features", features.toMap());
            return m;
        }
    }

    public static final class LineTask {
        public final int lineNo;
        public final String originalLine;
        public final String payload;
        public final boolean poison;

        LineTask(int lineNo, String originalLine, String payload) {
            this.lineNo = lineNo;
            this.originalLine = originalLine;
            this.payload = payload;
            this.poison = false;
        }

        private LineTask() {
            this.lineNo = -1;
            this.originalLine = "";
            this.payload = "";
            this.poison = true;
        }

        public static LineTask poison() { return new LineTask(); }
    }

    public static final class AnalysisSettings {
        public final int minSupport;
        public final int topK;
        public final double optThreshold;
        public final double watchThreshold;
        public final boolean executeCommands;
        public final double commandTimeout;
        public final int queueCapacity;
        public final int workers;
        public final boolean dynamicPythonEnabled;

        public AnalysisSettings(int minSupport, int topK, double optThreshold, double watchThreshold,
                                boolean executeCommands, double commandTimeout, int queueCapacity, int workers,
                                boolean dynamicPythonEnabled) {
            this.minSupport = Math.max(1, minSupport);
            this.topK = Math.max(1, topK);
            this.optThreshold = optThreshold;
            this.watchThreshold = watchThreshold;
            this.executeCommands = executeCommands;
            this.commandTimeout = commandTimeout;
            this.queueCapacity = Math.max(100, queueCapacity);
            this.workers = Math.max(1, workers);
            this.dynamicPythonEnabled = dynamicPythonEnabled;
        }
    }

    public static final class AnalysisContext {
        public final CorpusProfile profile;
        public final SynthesizedRules rules;
        public final List<LineResult> results;
        public final long runId;

        public AnalysisContext(CorpusProfile profile, SynthesizedRules rules, List<LineResult> results, long runId) {
            this.profile = profile;
            this.rules = rules;
            this.results = results;
            this.runId = runId;
        }
    }

    public interface AnalysisListener {
        default void onLog(String message) {}
        default void onProfileReady(CorpusProfile profile, SynthesizedRules rules) {}
        default void onResult(LineResult result) {}
        default void onProgress(int processed, int totalHint, String message) {}
        default void onFinished(AnalysisContext context) {}
        default void onError(String message, Throwable error) {}
    }

    public static final class OptimizationGoal {
        public final String key;
        public final String mode;
        public final double targetValue;
        public final double weight;
        /** Optional pure-Java expression in variable {@code x} — minimised analytically via Brent. */
        public final String objective;
        /** Lower / upper search bracket for {@link #objective}; {@code NaN} disables optimisation. */
        public final double searchLo;
        public final double searchHi;
        /** Argmin of {@link #objective} on [searchLo, searchHi] (NaN if not computed). */
        public final double computedArgmin;
        /** f(argmin), the analytical optimum value (NaN if not computed). */
        public final double computedOptimum;
        public final boolean optimumValid;

        public OptimizationGoal(String key, String mode, double targetValue, double weight) {
            this(key, mode, targetValue, weight, null, Double.NaN, Double.NaN);
        }

        public OptimizationGoal(String key, String mode, double targetValue, double weight,
                                String objective, double searchLo, double searchHi) {
            this.key = key;
            this.mode = mode;
            this.targetValue = targetValue;
            this.weight = weight;
            this.objective = objective;
            this.searchLo = searchLo;
            this.searchHi = searchHi;

            double xstar = Double.NaN, fstar = Double.NaN;
            boolean valid = false;
            if (objective != null && !objective.isBlank()
                    && Double.isFinite(searchLo) && Double.isFinite(searchHi) && searchHi > searchLo) {
                try {
                    DoubleUnaryOperator f = new ExprParser(objective).compile();
                    Optimizers.Min1D r = Optimizers.brentMinimize(f, searchLo, searchHi, 1e-9, 200);
                    xstar = r.x();
                    fstar = r.fx();
                    valid = r.converged();
                } catch (Exception ignored) {
                    // Bad expression / divergence — keep NaN sentinel.
                }
            }
            this.computedArgmin = xstar;
            this.computedOptimum = fstar;
            this.optimumValid = valid;
        }
    }

    public static LineResult findOptimalResult(List<LineResult> results) {
        if (results == null || results.isEmpty()) return null;
        return results.stream().max(Comparator.comparingDouble(r -> r.score)).orElse(null);
    }

    // ─── Real optimisation theory utilities (Pareto, Simpson AUC, ODE check) ──

    /**
     * Pareto-optimal subset of results across all configured optimisation goals
     * — the multi-objective alternative to scalar score ranking. A result is
     * dominated iff some other result is at-least-as-good on every goal and
     * strictly better on at least one. To keep the O(N²) check tractable on
     * large corpora we cap on the top 1000 by aggregate score before filtering.
     */
    public static List<LineResult> paretoOptimal(List<LineResult> results, List<OptimizationGoal> goals) {
        return paretoOptimal(results, goals,
                com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT);
    }

    /**
     * Overload that accepts a {@link com.yurii.analyzer.core.optimization.FrontAlgorithm}
     * selector.  Both algorithms produce identical rank-1 membership, so this
     * is purely an opt-in for the NSGA-II diversification metric (visible via
     * {@link #paretoOptimalRanked} or downstream reporters that ask for
     * crowding distance).  Existing call-sites that pass no algorithm get the
     * project-wide default ({@link com.yurii.analyzer.core.optimization.FrontAlgorithm#DEFAULT}).
     */
    public static List<LineResult> paretoOptimal(List<LineResult> results, List<OptimizationGoal> goals,
                                                  com.yurii.analyzer.core.optimization.FrontAlgorithm algo) {
        if (results == null || results.isEmpty() || goals == null || goals.isEmpty()) return List.of();

        // 1. Drop goals with effectively no data in the corpus. A goal needs
        //    at least PARETO_MIN_COVERAGE lines carrying its metric to count
        //    as a Pareto axis; demo-only goals (e.g. 'alpha_metric' that exists
        //    purely to exercise the Brent code path) are skipped.
        final int PARETO_MIN_COVERAGE = 5;
        List<OptimizationGoal> activeGoals = new ArrayList<>(goals.size());
        for (OptimizationGoal g : goals) {
            int present = 0;
            for (LineResult r : results) if (Double.isFinite(goalMetric(r, g.key))) present++;
            if (present >= PARETO_MIN_COVERAGE) activeGoals.add(g);
        }
        if (activeGoals.isEmpty()) return List.of();

        // 2. Drop any line missing one of the *active* goal metrics — an undefined
        //    coordinate would always escape domination on that axis.
        List<LineResult> eligible = new ArrayList<>(results.size());
        candidate:
        for (LineResult r : results) {
            for (OptimizationGoal g : activeGoals) {
                if (!Double.isFinite(goalMetric(r, g.key))) continue candidate;
            }
            eligible.add(r);
        }
        if (eligible.isEmpty()) return List.of();

        // 3. Compose objective lambdas + minimise flags for the Optimizers util.
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>(activeGoals.size());
        List<Boolean> minimize = new ArrayList<>(activeGoals.size());
        for (OptimizationGoal g : activeGoals) {
            String key = g.key;
            objs.add(r -> goalMetric(r, key));
            minimize.add(!"maximize".equals(g.mode));
        }

        List<LineResult> capped = eligible.size() > 1000
                ? eligible.stream().sorted((a, b) -> Double.compare(b.score, a.score)).limit(1000).toList()
                : eligible;
        com.yurii.analyzer.core.optimization.FrontAlgorithm effectiveAlgo =
                (algo == null) ? com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT : algo;
        if (effectiveAlgo == com.yurii.analyzer.core.optimization.FrontAlgorithm.NSGA_II
                || effectiveAlgo == com.yurii.analyzer.core.optimization.FrontAlgorithm.NSGA_III
                || effectiveAlgo == com.yurii.analyzer.core.optimization.FrontAlgorithm.SPEA2
                || effectiveAlgo == com.yurii.analyzer.core.optimization.FrontAlgorithm.MOEA_D) {
            com.yurii.analyzer.core.optimization.GoalSpec[] goalSpecs =
                    new com.yurii.analyzer.core.optimization.GoalSpec[activeGoals.size()];
            for (int i = 0; i < goalSpecs.length; i++) {
                OptimizationGoal og = activeGoals.get(i);
                boolean min = !"maximize".equals(og.mode);
                goalSpecs[i] = min
                        ? com.yurii.analyzer.core.optimization.GoalSpec.min("axis_" + i)
                        : com.yurii.analyzer.core.optimization.GoalSpec.max("axis_" + i);
            }
            double[][] vectors =
                    com.yurii.analyzer.core.optimization.Dominance.extractVectors(capped, objs);
            switch (effectiveAlgo) {
                case NSGA_III: return com.yurii.analyzer.core.optimization.Dominance.paretoFrontNsgaIII(capped, vectors, goalSpecs);
                case SPEA2:    return com.yurii.analyzer.core.optimization.Dominance.paretoFrontSpea2(capped, vectors, goalSpecs);
                case MOEA_D:   return com.yurii.analyzer.core.optimization.Dominance.paretoFrontMoeaD(capped, vectors, goalSpecs);
                default:       return com.yurii.analyzer.core.optimization.Dominance.paretoFrontNsgaII(capped, vectors, goalSpecs);
            }
        }
        return Optimizers.paretoFront(capped, objs, minimize);
    }

    /**
     * NSGA-II-flavoured Pareto-optimal extraction: same membership as
     * {@link #paretoOptimal} but each rank-1 member comes back with its
     * crowding distance.  Larger crowding = sparser neighbourhood in the
     * objective space = keep this member when diversifying a selection.
     * Used by {@link com.yurii.analyzer.core.optimization.BestLinesReporter}
     * to populate {@code LineMention.crowdingDistance}.
     *
     * <p>The returned list parallels the legacy {@link #paretoOptimal} output
     * in membership — same eligibility filter, same coverage gate — but
     * wraps each {@link LineResult} in a {@link com.yurii.analyzer.core.optimization.NsgaII.Ranked}
     * record so callers see both the candidate and its diversification
     * score.</p>
     */
    public static List<com.yurii.analyzer.core.optimization.NsgaII.Ranked<LineResult>>
            paretoOptimalRanked(List<LineResult> results, List<OptimizationGoal> goals) {
        if (results == null || results.isEmpty() || goals == null || goals.isEmpty()) return List.of();
        final int PARETO_MIN_COVERAGE = 5;
        List<OptimizationGoal> activeGoals = new ArrayList<>(goals.size());
        for (OptimizationGoal g : goals) {
            int present = 0;
            for (LineResult r : results) if (Double.isFinite(goalMetric(r, g.key))) present++;
            if (present >= PARETO_MIN_COVERAGE) activeGoals.add(g);
        }
        if (activeGoals.isEmpty()) return List.of();

        List<LineResult> eligible = new ArrayList<>(results.size());
        candidate:
        for (LineResult r : results) {
            for (OptimizationGoal g : activeGoals) {
                if (!Double.isFinite(goalMetric(r, g.key))) continue candidate;
            }
            eligible.add(r);
        }
        if (eligible.isEmpty()) return List.of();

        List<LineResult> capped = eligible.size() > 1000
                ? eligible.stream().sorted((a, b) -> Double.compare(b.score, a.score)).limit(1000).toList()
                : eligible;

        com.yurii.analyzer.core.optimization.GoalSpec[] goalSpecs =
                new com.yurii.analyzer.core.optimization.GoalSpec[activeGoals.size()];
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>(activeGoals.size());
        for (int i = 0; i < activeGoals.size(); i++) {
            OptimizationGoal og = activeGoals.get(i);
            boolean min = !"maximize".equals(og.mode);
            goalSpecs[i] = min
                    ? com.yurii.analyzer.core.optimization.GoalSpec.min("axis_" + i)
                    : com.yurii.analyzer.core.optimization.GoalSpec.max("axis_" + i);
            String key = og.key;
            objs.add(r -> goalMetric(r, key));
        }
        double[][] vectors = com.yurii.analyzer.core.optimization.Dominance.extractVectors(capped, objs);
        return com.yurii.analyzer.core.optimization.NsgaII.firstFrontWithCrowding(capped, vectors, goalSpecs);
    }

    /**
     * Tier-5.1 — NSGA-III flavoured Pareto-optimal extraction.  Mirrors
     * {@link #paretoOptimalRanked} but returns
     * {@link com.yurii.analyzer.core.optimization.NsgaIII.Ranked} entries
     * carrying {@code referencePointIndex} + {@code perpendicularDistance}
     * instead of crowding distance.  Rank-1 membership is identical to the
     * NSGA-II ranked variant on the same input — only the per-front
     * diversification metric changes (better-behaved at high objective
     * counts where crowding distance loses meaning).
     *
     * <p>The eligibility filter, coverage gate, and 1000-row cap are
     * byte-for-byte identical to {@link #paretoOptimalRanked} so callers can
     * swap algorithms without observing membership drift.</p>
     */
    public static List<com.yurii.analyzer.core.optimization.NsgaIII.Ranked<LineResult>>
            paretoOptimalRankedNsgaIII(List<LineResult> results, List<OptimizationGoal> goals) {
        if (results == null || results.isEmpty() || goals == null || goals.isEmpty()) return List.of();
        final int PARETO_MIN_COVERAGE = 5;
        List<OptimizationGoal> activeGoals = new ArrayList<>(goals.size());
        for (OptimizationGoal g : goals) {
            int present = 0;
            for (LineResult r : results) if (Double.isFinite(goalMetric(r, g.key))) present++;
            if (present >= PARETO_MIN_COVERAGE) activeGoals.add(g);
        }
        if (activeGoals.isEmpty()) return List.of();

        List<LineResult> eligible = new ArrayList<>(results.size());
        candidate:
        for (LineResult r : results) {
            for (OptimizationGoal g : activeGoals) {
                if (!Double.isFinite(goalMetric(r, g.key))) continue candidate;
            }
            eligible.add(r);
        }
        if (eligible.isEmpty()) return List.of();

        List<LineResult> capped = eligible.size() > 1000
                ? eligible.stream().sorted((a, b) -> Double.compare(b.score, a.score)).limit(1000).toList()
                : eligible;

        com.yurii.analyzer.core.optimization.GoalSpec[] goalSpecs =
                new com.yurii.analyzer.core.optimization.GoalSpec[activeGoals.size()];
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>(activeGoals.size());
        for (int i = 0; i < activeGoals.size(); i++) {
            OptimizationGoal og = activeGoals.get(i);
            boolean min = !"maximize".equals(og.mode);
            goalSpecs[i] = min
                    ? com.yurii.analyzer.core.optimization.GoalSpec.min("axis_" + i)
                    : com.yurii.analyzer.core.optimization.GoalSpec.max("axis_" + i);
            String key = og.key;
            objs.add(r -> goalMetric(r, key));
        }
        double[][] vectors = com.yurii.analyzer.core.optimization.Dominance.extractVectors(capped, objs);
        return com.yurii.analyzer.core.optimization.NsgaIII.firstFrontWithReference(capped, vectors, goalSpecs);
    }

    /**
     * Tier-5.1 — SPEA2 flavoured Pareto-optimal extraction with full
     * strength/raw-fitness/k-NN-density breakdown per member.  Same
     * rank-1 membership as the NSGA-II/III ranked variants on the same
     * input; only the per-front diversity scoring changes.
     */
    public static List<com.yurii.analyzer.core.optimization.Spea2.Ranked<LineResult>>
            paretoOptimalRankedSpea2(List<LineResult> results, List<OptimizationGoal> goals) {
        Object[] prep = rankedFrontPrologue(results, goals);
        if (prep == null) return List.of();
        @SuppressWarnings("unchecked")
        List<LineResult> capped = (List<LineResult>) prep[0];
        double[][] vectors = (double[][]) prep[1];
        com.yurii.analyzer.core.optimization.GoalSpec[] goalSpecs =
                (com.yurii.analyzer.core.optimization.GoalSpec[]) prep[2];
        return com.yurii.analyzer.core.optimization.Spea2.firstFrontWithFitness(capped, vectors, goalSpecs);
    }

    /**
     * Tier-5.1 — MOEA/D flavoured Pareto-optimal extraction with full
     * Tchebycheff decomposition (bestWeightIndex + bestTchebycheff +
     * meanTchebycheff) per member.  Same rank-1 membership as the NSGA
     * variants; the surfaced metric is the candidate's best alignment
     * with one of the structured weight directions.
     */
    public static List<com.yurii.analyzer.core.optimization.MoeaD.Ranked<LineResult>>
            paretoOptimalRankedMoeaD(List<LineResult> results, List<OptimizationGoal> goals) {
        Object[] prep = rankedFrontPrologue(results, goals);
        if (prep == null) return List.of();
        @SuppressWarnings("unchecked")
        List<LineResult> capped = (List<LineResult>) prep[0];
        double[][] vectors = (double[][]) prep[1];
        com.yurii.analyzer.core.optimization.GoalSpec[] goalSpecs =
                (com.yurii.analyzer.core.optimization.GoalSpec[]) prep[2];
        return com.yurii.analyzer.core.optimization.MoeaD.firstFrontWithDecomposition(capped, vectors, goalSpecs);
    }

    /**
     * Shared eligibility + cap + vector-extraction prologue used by all
     * ranked-front extractors (NSGA-II, NSGA-III, SPEA2, MOEA/D).  Returns
     * {@code null} when no candidates remain after filtering; otherwise an
     * {@code Object[3]} of {@code [List<LineResult> capped, double[][] vectors,
     * GoalSpec[] goalSpecs]}.  Kept package-private so future MOEA additions
     * can call into it cheaply.
     */
    static Object[] rankedFrontPrologue(List<LineResult> results, List<OptimizationGoal> goals) {
        if (results == null || results.isEmpty() || goals == null || goals.isEmpty()) return null;
        final int PARETO_MIN_COVERAGE = 5;
        List<OptimizationGoal> activeGoals = new ArrayList<>(goals.size());
        for (OptimizationGoal g : goals) {
            int present = 0;
            for (LineResult r : results) if (Double.isFinite(goalMetric(r, g.key))) present++;
            if (present >= PARETO_MIN_COVERAGE) activeGoals.add(g);
        }
        if (activeGoals.isEmpty()) return null;

        List<LineResult> eligible = new ArrayList<>(results.size());
        candidate:
        for (LineResult r : results) {
            for (OptimizationGoal g : activeGoals) {
                if (!Double.isFinite(goalMetric(r, g.key))) continue candidate;
            }
            eligible.add(r);
        }
        if (eligible.isEmpty()) return null;

        List<LineResult> capped = eligible.size() > 1000
                ? eligible.stream().sorted((a, b) -> Double.compare(b.score, a.score)).limit(1000).toList()
                : eligible;

        com.yurii.analyzer.core.optimization.GoalSpec[] goalSpecs =
                new com.yurii.analyzer.core.optimization.GoalSpec[activeGoals.size()];
        List<ToDoubleFunction<LineResult>> objs = new ArrayList<>(activeGoals.size());
        for (int i = 0; i < activeGoals.size(); i++) {
            OptimizationGoal og = activeGoals.get(i);
            boolean min = !"maximize".equals(og.mode);
            goalSpecs[i] = min
                    ? com.yurii.analyzer.core.optimization.GoalSpec.min("axis_" + i)
                    : com.yurii.analyzer.core.optimization.GoalSpec.max("axis_" + i);
            String key = og.key;
            objs.add(r -> goalMetric(r, key));
        }
        double[][] vectors = com.yurii.analyzer.core.optimization.Dominance.extractVectors(capped, objs);
        return new Object[]{ capped, vectors, goalSpecs };
    }

    private static double goalMetric(LineResult r, String key) {
        if ("length".equals(key)) return r.features.length;
        if ("entropy".equals(key)) return r.features.entropy;
        String v = r.features.kvPairs.get(key);
        if (v == null) return Double.NaN;
        return tryParseNumeric(v).orElse(Double.NaN);
    }

    /**
     * Composite Simpson integration of the score curve (treated as samples at
     * unit spacing in line index). Produces an "area under the score curve"
     * — a single scalar quality summary of the corpus.
     */
    public static double simpsonScoreAuc(List<LineResult> results) {
        if (results == null || results.size() < 2) return 0.0;
        double[] vals = new double[results.size()];
        for (int i = 0; i < vals.length; i++) vals[i] = results.get(i).score;
        return Optimizers.simpsonOverSamples(vals, 1.0);
    }

    /**
     * Numerically integrates the rule-confidence ODE
     *   dC/dn = (1 - C) / 100 ,  C(0) = 0.5
     * via Runge-Kutta 4 and reports the residual against the closed-form
     * solution C(n) = 1 - 0.5·exp(-n/100). The legacy heuristic {@code
     * 0.5 + 0.5·(1 - exp(-n/100))} is in fact this analytical solution; the
     * residual proves the formula is correctly implementing the ODE.
     *
     * @implNote <b>DECORATIVE</b> in the strict sense: RK4 reproduces
     *   {@code exp()} to machine precision — that's a well-known property,
     *   not a discovery.  The 5.55×10⁻¹⁶ residual we report is a tautology.
     *   The function is kept (a) because it documents the ODE
     *   interpretation of the legacy confidence formula (which IS load-bearing
     *   pedagogy) and (b) because it exercises the {@link Optimizers#rk4}
     *   primitive in the regression suite.  Don't take the green ✓ here as
     *   evidence the analyzer is "doing real optimisation" — it's evidence
     *   that RK4 still works.  Real evidence lives in
     *   {@code MetricStreamAnalyzer} and the streaming reservoir analysis.
     */
    public static double[] verifyConfidenceOde(int nSamples) {
        double[] residuals = new double[nSamples + 1];
        double[] y = new double[]{0.5};
        Optimizers.VectorField field = (t, yy) -> new double[]{(1.0 - yy[0]) / 100.0};
        residuals[0] = 0.0;
        for (int n = 1; n <= nSamples; n++) {
            y = Optimizers.rk4(field, y, n - 1, n, 0.1);
            double analytical = 1.0 - 0.5 * Math.exp(-n / 100.0);
            residuals[n] = Math.abs(y[0] - analytical);
        }
        return residuals;
    }

    private static LineFeatures emptyFeatures() {
        return new LineFeatures(-1, "", "", "", 0, List.of(), List.of(), List.of(), Map.of(), Map.of(), 0,
                0, 0, 0, 0, 0, 0, 0, "", "", "", "empty");
    }

    /** Sentinel used to signal end-of-stream to scoring workers. */
    private static final LineFeatures POISON_FEATURES = emptyFeatures();

    // ─── Shell + logical-command parsing (legacy behavior) ───────────────

    public static String resolveLinePayload(String line, boolean execute, double timeoutSeconds) {
        if (!execute) return line;
        String command = line == null ? "" : line.replace("\r", "");
        String stripped = command.trim();
        if (stripped.isEmpty() || COMMENT_RE.matcher(stripped).lookingAt()) return line;
        try {
            ProcessBuilder pb = shellBuilder(command);
            pb.redirectErrorStream(true);
            Process process = pb.start();
            boolean finished = process.waitFor((long) Math.ceil(timeoutSeconds), TimeUnit.SECONDS);
            if (!finished) {
                process.descendants().forEach(ProcessHandle::destroyForcibly);
                process.destroyForcibly();
                return "ERROR: Execution timed out after " + timeoutSeconds + " seconds.";
            }
            String output = readAll(process.getInputStream()).trim();
            if (!output.isEmpty()) {
                List<String> outputLines = output.lines().toList();
                for (int i = outputLines.size() - 1; i >= 0; i--) {
                    String candidate = stripPrefix(outputLines.get(i));
                    if (!candidate.isEmpty()) {
                        try {
                            Path p = Path.of(candidate);
                            if (Files.isRegularFile(p)) return Files.readString(p, StandardCharsets.UTF_8);
                        } catch (Exception ignored) {}
                    }
                }
                return output;
            }
            return "";
        } catch (Exception ex) {
            return "ERROR: Execution failed - " + ex.getMessage();
        }
    }

    private static ProcessBuilder shellBuilder(String command) {
        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        if (os.contains("win")) return new ProcessBuilder("cmd.exe", "/c", command);
        return new ProcessBuilder("bash", "-lc", command);
    }

    private static String readAll(InputStream in) throws IOException {
        try (BufferedReader br = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                if (sb.length() > 0) sb.append('\n');
                sb.append(line);
            }
            return sb.toString();
        }
    }

    private static String stripPrefix(String s) {
        String out = s == null ? "" : s.trim();
        for (String prefix : List.of("FILE:", "LOG:", "REPORT:", "OUT:")) {
            if (out.regionMatches(true, 0, prefix, 0, prefix.length())) return out.substring(prefix.length()).trim();
        }
        return out;
    }

    @FunctionalInterface
    private interface LogicalCommandConsumer {
        void accept(int startLineNo, int endLineNo, String commandText) throws IOException;
    }

    private static final class LogicalCommandBlock {
        final int startLineNo;
        final int endLineNo;
        final String commandText;

        LogicalCommandBlock(int startLineNo, int endLineNo, String commandText) {
            this.startLineNo = startLineNo;
            this.endLineNo = endLineNo;
            this.commandText = commandText;
        }
    }

    private static void forEachLogicalCommand(Path inputPath, AtomicBoolean cancelled,
                                              LogicalCommandConsumer consumer) throws IOException {
        try (BufferedReader br = Files.newBufferedReader(inputPath, StandardCharsets.UTF_8)) {
            StringBuilder current = new StringBuilder();
            int startLineNo = -1;
            int lineNo = 0;
            String line;
            while ((cancelled == null || !cancelled.get()) && (line = br.readLine()) != null) {
                lineNo++;
                String normalized = line.replace("\r", "");
                String trimmed = normalized.trim();

                if (current.length() == 0) {
                    if (trimmed.isEmpty() || COMMENT_RE.matcher(trimmed).lookingAt()) {
                        consumer.accept(lineNo, lineNo, normalized);
                        continue;
                    }
                    startLineNo = lineNo;
                } else if (trimmed.isEmpty() && isShellCommandComplete(current.toString())) {
                    consumer.accept(startLineNo, lineNo - 1, current.toString());
                    current.setLength(0);
                    consumer.accept(lineNo, lineNo, normalized);
                    startLineNo = -1;
                    continue;
                }

                if (current.length() > 0) current.append('\n');
                current.append(normalized);

                if (isShellCommandComplete(current.toString())) {
                    consumer.accept(startLineNo, lineNo, current.toString());
                    current.setLength(0);
                    startLineNo = -1;
                }
            }

            if (current.length() > 0 && (cancelled == null || !cancelled.get())) {
                consumer.accept(startLineNo < 0 ? lineNo : startLineNo, lineNo, current.toString());
            }
        }
    }

    private static List<LogicalCommandBlock> collectLogicalCommands(List<String> physicalLines) {
        if (physicalLines == null || physicalLines.isEmpty()) return List.of();
        ArrayList<LogicalCommandBlock> blocks = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        int startLineNo = -1;
        int physicalLineNo = 0;

        for (String rawLine : physicalLines) {
            String safeLine = rawLine == null ? "" : rawLine.replace("\r", "");
            String[] segments = safeLine.split("\\R", -1);
            for (String normalized : segments) {
                physicalLineNo++;
                String trimmed = normalized.trim();

                if (current.length() == 0) {
                    if (trimmed.isEmpty() || COMMENT_RE.matcher(trimmed).lookingAt()) {
                        blocks.add(new LogicalCommandBlock(physicalLineNo, physicalLineNo, normalized));
                        continue;
                    }
                    startLineNo = physicalLineNo;
                } else if (trimmed.isEmpty() && isShellCommandComplete(current.toString())) {
                    blocks.add(new LogicalCommandBlock(startLineNo, physicalLineNo - 1, current.toString()));
                    current.setLength(0);
                    blocks.add(new LogicalCommandBlock(physicalLineNo, physicalLineNo, normalized));
                    startLineNo = -1;
                    continue;
                }

                if (current.length() > 0) current.append('\n');
                current.append(normalized);

                if (isShellCommandComplete(current.toString())) {
                    blocks.add(new LogicalCommandBlock(startLineNo, physicalLineNo, current.toString()));
                    current.setLength(0);
                    startLineNo = -1;
                }
            }
        }

        if (current.length() > 0) {
            blocks.add(new LogicalCommandBlock(startLineNo < 0 ? physicalLineNo : physicalLineNo,
                    physicalLineNo, current.toString()));
        }
        return blocks;
    }

    private static boolean isShellCommandComplete(String text) {
        if (text == null) return false;
        String normalized = text.replace("\r", "");
        if (normalized.trim().isEmpty()) return false;

        boolean singleQuote = false;
        boolean doubleQuote = false;
        boolean backtick = false;
        int parenDepth = 0;
        int braceDepth = 0;
        int bracketDepth = 0;
        boolean continuation = false;
        int scriptDepth = 0;
        List<String> heredocs = new ArrayList<>();

        String[] lines = normalized.split("\\n", -1);
        for (String line : lines) {
            if (!heredocs.isEmpty()) {
                String terminator = heredocs.get(0);
                String trimmed = line.trim();
                if (trimmed.equals(terminator) || trimmed.equals("-" + terminator)) heredocs.remove(0);
                continuation = false;
                continue;
            }

            boolean escaped = false;
            for (int i = 0; i < line.length(); i++) {
                char ch = line.charAt(i);
                if (singleQuote) { if (ch == '\'') singleQuote = false; continue; }
                if (doubleQuote) {
                    if (escaped) { escaped = false; continue; }
                    if (ch == '\\') { escaped = true; continue; }
                    if (ch == '"') doubleQuote = false;
                    continue;
                }
                if (backtick) { if (ch == '`') backtick = false; continue; }
                if (ch == '\\') { escaped = !escaped; continue; }
                if (ch == '\'') { singleQuote = true; continue; }
                if (ch == '"') { doubleQuote = true; continue; }
                if (ch == '`') { backtick = true; continue; }
                if (ch == '(') { parenDepth++; continue; }
                if (ch == ')' && parenDepth > 0) { parenDepth--; continue; }
                if (ch == '{') { braceDepth++; continue; }
                if (ch == '}' && braceDepth > 0) { braceDepth--; continue; }
                if (ch == '[') { bracketDepth++; continue; }
                if (ch == ']' && bracketDepth > 0) { bracketDepth--; continue; }
                if (ch == '<' && i + 1 < line.length() && line.charAt(i + 1) == '<') {
                    int j = i + 2;
                    if (j < line.length() && line.charAt(j) == '-') j++;
                    while (j < line.length() && Character.isWhitespace(line.charAt(j))) j++;
                    int start = j;
                    while (j < line.length()) {
                        char c = line.charAt(j);
                        if (Character.isLetterOrDigit(c) || c == '_' || c == '-') j++;
                        else break;
                    }
                    if (j > start) {
                        heredocs.add(line.substring(start, j));
                        i = j - 1;
                    }
                }
            }

            String trimmed = line.trim();
            if (!singleQuote && !doubleQuote && !backtick) {
                if (trimmed.matches("(?i)^(if|for|while|until|select|case)\\b.*")) scriptDepth++;
                if (trimmed.matches("(?i)^(fi|done|esac)\\b.*")) scriptDepth = Math.max(0, scriptDepth - 1);
                continuation = trimmed.endsWith("\\") || trimmed.endsWith("&&") || trimmed.endsWith("||")
                        || trimmed.endsWith("|") || trimmed.endsWith("|&")
                        || trimmed.endsWith("(") || trimmed.endsWith("{");
            } else {
                continuation = true;
            }
        }

        return !singleQuote && !doubleQuote && !backtick && parenDepth == 0 && braceDepth == 0
                && bracketDepth == 0 && heredocs.isEmpty() && scriptDepth == 0 && !continuation;
    }

    // ─── Universal dynamic optimizer (cached, scipy-probed) ──────────────
    // Moved out to com.yurii.analyzer.core.UniversalDynamicOptimizer (own file)
    // so this 2200-line bag-of-nested-classes shrinks toward something readable.
    // Same-package callers (this file) reach it by simple name without import;
    // external callers had no imports for the nested type (only doc-comments),
    // so the move is API-compatible. See UniversalDynamicOptimizer.java.
    //
    // DatabaseManager is still nested (tightly coupled with internal MAPPER /
    // DB_URL / emptyFeatures / LineFeatures fields).  Earmarked for a future
    // iteration once the coupling is cleaned up.

    // ─── Optimization analyzer ───────────────────────────────────────────

    public static final class OptimizationAnalyzer {
        private final JsonNode manual;
        private final int minSupport;
        private final int topK;
        private final double optThreshold;
        private final double watchThreshold;
        private final boolean executeCommands;
        private final double commandTimeout;
        private final boolean dynamicPythonEnabled;

        private final List<String> reqTokens;
        private final List<String> forbidTokens;
        private final Map<String, Double> tokenWeights;
        private final List<String> reqKeys;
        private final List<String> forbidKeys;
        private final List<String> expTypes;
        private final List<String> expSigs;
        private final List<Pattern> reqRegex;
        private final List<Pattern> forbidRegex;
        private final List<String> notesCfg;
        private final Integer lenMin;
        private final Integer lenMax;
        private final Map<String, double[]> numRanges;

        private final List<OptimizationGoal> optGoals;
        /** Pluggable parser for K/V extraction.  Default = original regex
         *  behaviour; callers can swap to JSON / multi-format via the overloaded
         *  constructor.  Format-agnosticism extension (see {@link com.yurii.analyzer.core.optimization.LineParser}). */
        private final com.yurii.analyzer.core.optimization.LineParser kvParser;
        /** Pluggable Pareto-front algorithm.  Default = NSGA-II (rank-1 front
         *  identical to the legacy Pareto path, plus crowding distance for
         *  diversity-aware reporting).  Selectable through the GUI; callers
         *  that don't care default to {@link com.yurii.analyzer.core.optimization.FrontAlgorithm#DEFAULT}. */
        private final com.yurii.analyzer.core.optimization.FrontAlgorithm frontAlgorithm;

        private volatile CorpusProfile profile = new CorpusProfile();
        private volatile SynthesizedRules rules = emptyRules();

        /** Original 8-arg constructor: defaults to the regex K=V parser
         *  (current behaviour, byte-for-byte unchanged). */
        public OptimizationAnalyzer(JsonNode manual, int minSupport, int topK, double optThreshold,
                                    double watchThreshold, boolean executeCommands, double commandTimeout,
                                    boolean dynamicPythonEnabled) {
            this(manual, minSupport, topK, optThreshold, watchThreshold,
                 executeCommands, commandTimeout, dynamicPythonEnabled,
                 new com.yurii.analyzer.core.optimization.LineParser.KvLineParser(),
                 com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT);
        }

        /** Extended constructor: lets the caller plug in a custom
         *  {@link com.yurii.analyzer.core.optimization.LineParser} (e.g.
         *  {@code JsonLineParser} or {@code MultiParser}) so the analyzer can
         *  ingest JSON / mixed corpora without giving up its optimization
         *  pipeline. */
        public OptimizationAnalyzer(JsonNode manual, int minSupport, int topK, double optThreshold,
                                    double watchThreshold, boolean executeCommands, double commandTimeout,
                                    boolean dynamicPythonEnabled,
                                    com.yurii.analyzer.core.optimization.LineParser kvParser) {
            this(manual, minSupport, topK, optThreshold, watchThreshold,
                 executeCommands, commandTimeout, dynamicPythonEnabled,
                 kvParser,
                 com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT);
        }

        /** Most-explicit constructor: parser + Pareto-front algorithm.
         *  {@code frontAlgorithm} controls how rank-1 front extraction is
         *  performed; default ({@code null} permitted) is
         *  {@link com.yurii.analyzer.core.optimization.FrontAlgorithm#DEFAULT}
         *  which currently resolves to NSGA-II. */
        public OptimizationAnalyzer(JsonNode manual, int minSupport, int topK, double optThreshold,
                                    double watchThreshold, boolean executeCommands, double commandTimeout,
                                    boolean dynamicPythonEnabled,
                                    com.yurii.analyzer.core.optimization.LineParser kvParser,
                                    com.yurii.analyzer.core.optimization.FrontAlgorithm frontAlgorithm) {
            this.manual = manual == null ? MAPPER.createObjectNode() : manual;
            this.minSupport = minSupport;
            this.topK = topK;
            this.optThreshold = optThreshold;
            this.watchThreshold = watchThreshold;
            this.executeCommands = executeCommands;
            this.commandTimeout = commandTimeout;
            this.dynamicPythonEnabled = dynamicPythonEnabled;
            this.kvParser = (kvParser == null) ? new com.yurii.analyzer.core.optimization.LineParser.KvLineParser() : kvParser;
            this.frontAlgorithm = (frontAlgorithm == null)
                    ? com.yurii.analyzer.core.optimization.FrontAlgorithm.DEFAULT
                    : frontAlgorithm;

            this.reqTokens = jsonArray(this.manual, "required_tokens");
            this.forbidTokens = jsonArray(this.manual, "forbidden_tokens");
            this.tokenWeights = jsonMapDouble(this.manual, "token_weights");
            this.reqKeys = jsonArray(this.manual, "required_keys");
            this.forbidKeys = jsonArray(this.manual, "forbidden_keys");
            this.expTypes = jsonArray(this.manual, "expected_line_types");
            this.expSigs = jsonArray(this.manual, "expected_signatures");
            this.reqRegex = parseRegex(jsonArray(this.manual, "required_regexes"));
            this.forbidRegex = parseRegex(jsonArray(this.manual, "forbidden_regexes"));
            this.notesCfg = jsonArray(this.manual, "notes");

            Map<String, Object> band = jsonMapObject(this.manual, "line_length");
            this.lenMin = band.containsKey("min") ? safeInt(band.get("min"), 0) : null;
            this.lenMax = band.containsKey("max") ? safeInt(band.get("max"), Integer.MAX_VALUE) : null;

            this.numRanges = new LinkedHashMap<>();
            JsonNode nr = this.manual.path("numeric_ranges");
            if (nr.isObject()) {
                for (Map.Entry<String, JsonNode> e : nr.properties()) {
                    JsonNode v = e.getValue();
                    if (v.isArray() && v.size() >= 2) {
                        this.numRanges.put(e.getKey(), new double[]{
                                safeDouble(v.get(0), Double.NEGATIVE_INFINITY),
                                safeDouble(v.get(1), Double.POSITIVE_INFINITY)});
                    }
                }
            }

            this.optGoals = new ArrayList<>();
            JsonNode optsNode = this.manual.path("optimizations");
            if (optsNode.isArray()) {
                for (JsonNode opt : optsNode) {
                    OptimizationGoal g = parseGoal(opt);
                    if (g != null) optGoals.add(g);
                }
            } else {
                OptimizationGoal g = parseGoal(this.manual.path("optimization"));
                if (g != null) optGoals.add(g);
            }
        }

        private static OptimizationGoal parseGoal(JsonNode opt) {
            String key = opt.path("key").asText("").toLowerCase(Locale.ROOT);
            if (key.isEmpty()) return null;
            String mode = opt.path("mode").asText("minimize").toLowerCase(Locale.ROOT);
            double target = opt.path("target_value").asDouble(0.0);
            double weight = opt.path("weight").asDouble(30.0);
            String objective = opt.has("objective") && opt.get("objective").isTextual()
                    ? opt.path("objective").asText(null) : null;
            double lo = opt.path("search_lo").asDouble(Double.NaN);
            double hi = opt.path("search_hi").asDouble(Double.NaN);
            return new OptimizationGoal(key, mode, target, weight, objective, lo, hi);
        }

        private static SynthesizedRules emptyRules() {
            return new SynthesizedRules("", "", List.of(), List.of(), List.of(),
                    Map.of(), Map.of(), Map.of(), Map.of(), Map.of(),
                    0, 0, 0, 0, 0, 0, 1, 1, 0.0);
        }

        private static List<Pattern> parseRegex(List<String> list) {
            List<Pattern> out = new ArrayList<>();
            for (String s : list) {
                try { out.add(Pattern.compile(s)); } catch (Exception ignored) {}
            }
            return out;
        }

        public LineFeatures extractFeatures(int lineNo, String raw, String originalLine) {
            String text = raw == null ? "" : raw.replace("\r", "").trim();
            List<String> tokens = TOKEN_RE.matcher(text).results().map(MatchResult::group).toList();
            List<String> lowers = tokens.stream().map(t -> t.toLowerCase(Locale.ROOT)).toList();

            List<Double> numbers = new ArrayList<>();
            Matcher nm = NUMBER_RE.matcher(text);
            while (nm.find()) numbers.add(safeDouble(nm.group(), 0.0));

            // Delegate K/V extraction to the pluggable parser.  Default is
            // KvLineParser (identical to the previous regex-based behaviour);
            // callers can pass JsonLineParser / MultiParser via the
            // 9-arg constructor for JSON or mixed-format corpora.
            Map<String, String> kv = new LinkedHashMap<>(this.kvParser.parse(text));

            if (this.dynamicPythonEnabled && text.contains("=") && text.contains(";")) {
                try {
                    kv.putAll(UniversalDynamicOptimizer.evaluate(text));
                } catch (Throwable t) {
                    kv.put("python_eval_error", t.getMessage());
                }
            }

            Map<String, Integer> del = new LinkedHashMap<>();
            for (int i = 0; i < text.length(); i++) {
                char ch = text.charAt(i);
                if (":=,;|/\\()[]{}<>".indexOf(ch) >= 0) del.merge(String.valueOf(ch), 1, Integer::sum);
            }

            int placeholders = (int) PLACEHOLDER_RE.matcher(text).results().count();
            CharStats cs = CharStats.of(text);
            int length = text.length();
            int total = Math.max(1, length);
            double alphaRatio = cs.alpha / (double) total;
            double digitRatio = cs.digit / (double) total;
            double spaceRatio = cs.space / (double) total;
            double punctRatio = cs.punct / (double) total;
            double upperRatio = cs.alpha == 0 ? 0.0 : cs.upper / (double) cs.alpha;
            double uniqRatio = lowers.isEmpty() ? 0.0 : new HashSet<>(lowers).size() / (double) lowers.size();
            String sig = compressSignature(text);
            String prefix = text.length() <= 32 ? text : text.substring(0, 32);
            String suffix = text.length() <= 32 ? text : text.substring(text.length() - 32);
            String lineType = lineKind(text, tokens, kv, numbers, placeholders);

            return new LineFeatures(lineNo, raw, originalLine == null ? raw : originalLine, text, length,
                    tokens, lowers, numbers, kv, del, placeholders, cs.entropy, alphaRatio, digitRatio,
                    spaceRatio, punctRatio, upperRatio, uniqRatio, sig, prefix, suffix, lineType);
        }

        private String lineKind(String line, List<String> tokens, Map<String, String> kv,
                                List<Double> numbers, int placeholders) {
            String t = line == null ? "" : line.trim();
            if (t.isEmpty()) return "empty";
            if (COMMENT_RE.matcher(t).lookingAt()) return "comment";
            if (kv.size() >= 2 && !numbers.isEmpty()) return "kv_numeric";
            if (kv.size() >= 2) return "kv";
            if (placeholders > 0) return "templated";
            if (numbers.size() >= 3 && tokens.size() <= 10) return "numeric";
            if (tokens.size() >= 10) return "text";
            return "mixed";
        }

        // ─── Profile aggregation: shared online-statistics with local merges ───

        private static final class ProfileBuilder {
            // Online running stats (single pass, numerically stable)
            final Welford lengths = new Welford();
            final Welford entropies = new Welford();
            // Sample reservoirs needed for percentiles. Bounded so memory stays predictable.
            static final int SAMPLE_CAP = 100_000;
            final ArrayList<Double> lengthSamples = new ArrayList<>();
            final ArrayList<Double> entropySamples = new ArrayList<>();
            final Map<String, ArrayList<Double>> optSamples = new HashMap<>();

            int totalLines, nonemptyLines, emptyLines;
            final Map<String, Integer> tokenDf = new HashMap<>();
            final Map<String, Integer> keyDf = new HashMap<>();
            final Map<String, Integer> numberDf = new HashMap<>();
            final Map<String, Integer> lineTypeDf = new HashMap<>();
            final Map<String, Integer> sigDf = new HashMap<>();

            void addLength(double v) { lengths.add(v); if (lengthSamples.size() < SAMPLE_CAP) lengthSamples.add(v); }
            void addEntropy(double v) { entropies.add(v); if (entropySamples.size() < SAMPLE_CAP) entropySamples.add(v); }
            void addOpt(String key, double v) {
                optSamples.computeIfAbsent(key, k -> new ArrayList<>()).add(v);
            }
        }

        private void accumulateInto(ProfileBuilder b, LineFeatures f) {
            b.totalLines++;
            if ("empty".equals(f.lineType)) { b.emptyLines++; return; }
            b.nonemptyLines++;
            b.addLength(f.length);
            b.addEntropy(f.entropy);

            for (OptimizationGoal goal : optGoals) {
                Double m = extractMetric(f, goal.key);
                if (m != null) b.addOpt(goal.key, m);
            }

            HashSet<String> uniqTokens = new HashSet<>(f.tokenLowers);
            for (String t : uniqTokens) if (!STOPWORDS.contains(t) && t.length() > 2) b.tokenDf.merge(t, 1, Integer::sum);
            for (String k : f.kvPairs.keySet()) b.keyDf.merge(k, 1, Integer::sum);
            HashSet<Double> uniqNum = new HashSet<>(f.numbers);
            for (Double n : uniqNum) b.numberDf.merge(canonicalNumber(n), 1, Integer::sum);
            b.lineTypeDf.merge(f.lineType, 1, Integer::sum);
            b.sigDf.merge(f.signature, 1, Integer::sum);
        }

        private CorpusProfile finalize(ProfileBuilder b) {
            CorpusProfile p = new CorpusProfile();
            p.totalLines = b.totalLines;
            p.nonemptyLines = b.nonemptyLines;
            p.emptyLines = b.emptyLines;

            p.lengthMean = b.lengths.mean;
            p.lengthStdev = b.lengths.stdev();
            p.lengthMedian = percentile(b.lengthSamples, 50.0);
            p.lengthP10 = percentile(b.lengthSamples, 10.0);
            p.lengthP90 = percentile(b.lengthSamples, 90.0);

            p.entropyMean = b.entropies.mean;
            p.entropyStdev = b.entropies.stdev();
            p.entropyMedian = percentile(b.entropySamples, 50.0);
            p.entropyP10 = percentile(b.entropySamples, 10.0);
            p.entropyP90 = percentile(b.entropySamples, 90.0);

            p.tokenFrequency = sortDescByCount(b.tokenDf);
            p.keyFrequency = sortDescByCount(b.keyDf);
            p.numberFrequency = sortDescByCount(b.numberDf);
            p.lineTypeFrequency = sortDescByCount(b.lineTypeDf);
            p.signatureFrequency = sortDescByCount(b.sigDf);

            p.commonTokens = topK(b.tokenDf, topK, minSupport).stream().map(Map.Entry::getKey).toList();
            p.commonKeys = topK(b.keyDf, topK, minSupport).stream().map(Map.Entry::getKey).toList();
            p.commonNumbers = topK(b.numberDf, topK, minSupport).stream().map(Map.Entry::getKey).toList();

            p.dominantLineType = p.lineTypeFrequency.keySet().stream().findFirst().orElse("unknown");
            p.dominantSignature = p.signatureFrequency.keySet().stream().findFirst().orElse("");

            for (Map.Entry<String, ArrayList<Double>> entry : b.optSamples.entrySet()) {
                String key = entry.getKey();
                ArrayList<Double> values = entry.getValue();
                if (values.isEmpty()) continue;
                double min = Double.POSITIVE_INFINITY, max = Double.NEGATIVE_INFINITY;
                for (double v : values) { if (v < min) min = v; if (v > max) max = v; }
                p.optMetricMin.put(key, min);
                p.optMetricMax.put(key, max);
                p.optMetricCount.put(key, values.size());
                // Robust band: clamp to 5th–95th percentile so outliers don't crush normalization.
                p.optMetricLow.put(key, percentile(values, 5.0));
                p.optMetricHigh.put(key, percentile(values, 95.0));
            }
            return p;
        }

        private SynthesizedRules synthesizeRules(CorpusProfile p, int nonempty) {
            if (nonempty == 0) return emptyRules();
            // Confidence: monotone-in-N, capped in [0.5,1.0]. Saturates around 200 observations.
            double conf = 0.5 + 0.5 * (1.0 - Math.exp(-nonempty / 100.0));
            int tfCut = Math.max(minSupport, (int) Math.ceil(conf * minSupport));
            int nfCut = Math.max(minSupport, (int) Math.ceil(conf * minSupport));
            return new SynthesizedRules(p.dominantLineType, p.dominantSignature,
                    p.commonTokens, p.commonKeys, p.commonNumbers,
                    p.lineTypeFrequency, p.signatureFrequency, p.tokenFrequency, p.keyFrequency, p.numberFrequency,
                    p.lengthMedian, p.lengthP10, p.lengthP90, p.entropyMedian, p.entropyP10, p.entropyP90,
                    tfCut, nfCut, conf);
        }

        public LineResult scoreLine(LineFeatures f, CorpusProfile p, SynthesizedRules r) {
            if ("empty".equals(f.lineType))
                return new LineResult(f.lineNo, f.originalLine, f.raw, f, 0.0, "reject", Map.of(), List.of("Empty line"), List.of());

            double total = 0.0;
            Map<String, Double> b = new LinkedHashMap<>();
            List<String> n = new ArrayList<>();
            List<String> mr = new ArrayList<>();
            double conf = r.confidence;

            if (f.lineType.equals(r.dominantLineType)) { double x = 10.0 * conf; total += x; b.put("DominantType", x); mr.add("DominantType"); }
            if (f.signature.equals(r.dominantSignature)) { double x = 10.0 * conf; total += x; b.put("DominantSignature", x); mr.add("DominantSignature"); }

            double tok = 0.0;
            int lowersSize = Math.max(1, f.tokenLowers.size());
            for (String t : f.tokenLowers) {
                if (r.topTokens.contains(t) && r.tokenSupport.getOrDefault(t, 0) >= r.tokenDfCutoff)
                    tok += (5.0 * conf / lowersSize);
            }
            if (tok > 0) { total += tok; b.put("FreqTokens", tok); mr.add("FreqTokens"); }

            double key = 0.0;
            int kvSize = Math.max(1, f.kvPairs.size());
            for (String k : f.kvPairs.keySet())
                if (r.topKeys.contains(k)) key += (10.0 * conf / kvSize);
            if (key > 0) { total += key; b.put("FreqKeys", key); mr.add("FreqKeys"); }

            double num = 0.0;
            int numSize = Math.max(1, f.numbers.size());
            for (Double nm : f.numbers)
                if (r.topNumbers.contains(canonicalNumber(nm))) num += (5.0 * conf / numSize);
            if (num > 0) { total += num; b.put("FreqNumbers", num); mr.add("FreqNumbers"); }

            if (f.length >= r.lengthP10 && f.length <= r.lengthP90) { double x = 5.0 * conf; total += x; b.put("LengthInIQR", x); mr.add("LengthInIQR"); }
            if (f.entropy >= r.entropyP10 && f.entropy <= r.entropyP90) { double x = 5.0 * conf; total += x; b.put("EntropyInIQR", x); mr.add("EntropyInIQR"); }

            if (!reqTokens.isEmpty() || !forbidTokens.isEmpty() || !tokenWeights.isEmpty()) {
                Set<String> toks = new HashSet<>(f.tokenLowers);
                for (String req : reqTokens) {
                    if (toks.contains(req)) { double x = 15.0; total += x; b.put("ReqToken:" + req, x); mr.add("ReqToken"); }
                    else { double x = -15.0; total += x; b.put("MissReqToken:" + req, x); n.add("Missing required token: " + req); }
                }
                for (String fb : forbidTokens)
                    if (toks.contains(fb)) { double x = -50.0; total += x; b.put("ForbidToken:" + fb, x); n.add("Contains forbidden token: " + fb); }
                for (Map.Entry<String, Double> e : tokenWeights.entrySet())
                    if (toks.contains(e.getKey())) { total += e.getValue(); b.put("TokenWeight:" + e.getKey(), e.getValue()); mr.add("TokenWeight"); }
            }

            if (!reqKeys.isEmpty() || !forbidKeys.isEmpty()) {
                Set<String> keys = f.kvPairs.keySet();
                for (String req : reqKeys) {
                    if (keys.contains(req)) { double x = 15.0; total += x; b.put("ReqKey:" + req, x); mr.add("ReqKey"); }
                    else { double x = -15.0; total += x; b.put("MissReqKey:" + req, x); n.add("Missing required key: " + req); }
                }
                for (String fb : forbidKeys)
                    if (keys.contains(fb)) { double x = -50.0; total += x; b.put("ForbidKey:" + fb, x); n.add("Contains forbidden key: " + fb); }
            }

            if (!expTypes.isEmpty()) {
                if (expTypes.contains(f.lineType)) { double x = 20.0; total += x; b.put("ExpType", x); mr.add("ExpType"); }
                else { double x = -10.0; total += x; b.put("WrongType", x); n.add("Unexpected type: " + f.lineType); }
            }

            if (!expSigs.isEmpty()) {
                if (expSigs.contains(f.signature)) { double x = 20.0; total += x; b.put("ExpSignature", x); mr.add("ExpSignature"); }
                else { double x = -10.0; total += x; b.put("WrongSignature", x); n.add("Unexpected signature: " + f.signature); }
            }

            if (lenMin != null && f.length < lenMin) { double x = -20.0; total += x; b.put("TooShort", x); n.add("Length " + f.length + " < " + lenMin); }
            if (lenMax != null && f.length > lenMax) { double x = -20.0; total += x; b.put("TooLong", x); n.add("Length " + f.length + " > " + lenMax); }

            for (Pattern pat : reqRegex) {
                if (pat.matcher(f.raw).find()) { double x = 20.0; total += x; b.put("ReqRegex:" + pat.pattern(), x); mr.add("ReqRegex"); }
                else { double x = -20.0; total += x; b.put("MissRegex:" + pat.pattern(), x); n.add("Misses regex: " + pat.pattern()); }
            }
            for (Pattern pat : forbidRegex)
                if (pat.matcher(f.raw).find()) { double x = -50.0; total += x; b.put("ForbidRegex:" + pat.pattern(), x); n.add("Matches forbid regex: " + pat.pattern()); }

            for (Map.Entry<String, double[]> e : numRanges.entrySet()) {
                String k = e.getKey();
                double[] rge = e.getValue();
                Double val = extractMetric(f, k);
                if (val != null) {
                    if (val >= rge[0] && val <= rge[1]) { double x = 10.0; total += x; b.put("Range:" + k, x); mr.add("NumRange"); }
                    else { double x = -10.0; total += x; b.put("OutRange:" + k, x); n.add(k + "=" + val + " out of [" + rge[0] + "," + rge[1] + "]"); }
                }
            }

            n.addAll(notesCfg);

            // Multi-target optimisation. Three regimes are blended:
            //   1. Robust percentile-clamped normalisation against the corpus distribution.
            //   2. If goal carries a parsed objective expression, the analytical argmin
            //      computed via Brent's method is used as the target instead of the
            //      manual target_value (calculus-of-variations style — the user
            //      describes the cost surface, the analyser solves for its extremum).
            for (OptimizationGoal goal : optGoals) {
                String optKey = goal.key;
                double optWeight = goal.weight;
                int count = p.optMetricCount.getOrDefault(optKey, 0);
                if (optWeight <= 0 || count <= 1) continue;
                Double val = extractMetric(f, optKey);
                if (val == null) {
                    double x = -optWeight * 0.5;
                    total += x;
                    b.put("MissOptMetric[" + optKey + "]", x);
                    continue;
                }
                double lo = p.optMetricLow.getOrDefault(optKey, p.optMetricMin.getOrDefault(optKey, 0.0));
                double hi = p.optMetricHigh.getOrDefault(optKey, p.optMetricMax.getOrDefault(optKey, 0.0));
                if (hi <= lo) continue; // degenerate distribution; skip rather than divide by zero
                double norm = clamp((val - lo) / (hi - lo), 0.0, 1.0);
                double bonus = 0.0;
                String breakdownTag;

                if (goal.optimumValid) {
                    // Brent-derived analytical optimum drives the target.
                    double tNorm = clamp((goal.computedArgmin - lo) / (hi - lo), 0.0, 1.0);
                    bonus = (1.0 - Math.abs(norm - tNorm)) * optWeight;
                    breakdownTag = "OptBrent[" + optKey + "]";
                    b.put("OptArgmin[" + optKey + "]", goal.computedArgmin);
                    b.put("OptFmin[" + optKey + "]", goal.computedOptimum);
                } else if ("minimize".equals(goal.mode)) {
                    bonus = (1.0 - norm) * optWeight;
                    breakdownTag = "OptTarget[" + optKey + "]";
                } else if ("maximize".equals(goal.mode)) {
                    bonus = norm * optWeight;
                    breakdownTag = "OptTarget[" + optKey + "]";
                } else if ("target".equals(goal.mode)) {
                    double tNorm = clamp((goal.targetValue - lo) / (hi - lo), 0.0, 1.0);
                    bonus = (1.0 - Math.abs(norm - tNorm)) * optWeight;
                    breakdownTag = "OptTarget[" + optKey + "]";
                } else {
                    breakdownTag = "OptTarget[" + optKey + "]";
                }
                total += bonus;
                b.put(breakdownTag, bonus);
                mr.add(goal.optimumValid ? "OptBrent" : "OptTarget");
            }

            String dec = total >= optThreshold ? "opt" : (total >= watchThreshold ? "watch" : "reject");
            return new LineResult(f.lineNo, f.originalLine, f.raw, f, total, dec, b, n, mr);
        }

        private Double extractMetric(LineFeatures f, String key) {
            if ("length".equals(key)) return (double) f.length;
            if ("entropy".equals(key)) return f.entropy;
            String v = f.kvPairs.get(key);
            if (v == null) return null;
            java.util.OptionalDouble od = tryParseNumeric(v);
            return od.isPresent() ? od.getAsDouble() : null;
        }

        // ─── In-memory analysis (small files / sample text) ───────────────

        public List<OptimizationGoal> goals() { return List.copyOf(optGoals); }

        /** Which Pareto-front algorithm this instance was configured with.
         *  Surfaced so GUI / report code can pass the same choice down to
         *  {@link #paretoOptimal(java.util.List, java.util.List, com.yurii.analyzer.core.optimization.FrontAlgorithm)}
         *  and {@link com.yurii.analyzer.core.optimization.MetricStreamAnalyzer#autoPareto(java.util.List, int, com.yurii.analyzer.core.optimization.FrontAlgorithm)}. */
        public com.yurii.analyzer.core.optimization.FrontAlgorithm frontAlgorithm() { return frontAlgorithm; }

        /**
         * Streaming entry point for combinatorial workloads at 100K–10M+ scale.
         *
         * Single-pass over an {@code Iterator<String>} of candidates emitted
         * by an external Combinatorics Framework — line content can be
         * anything textual (test scenario, source-code path, prompt template,
         * gene encoding…); domain semantics live entirely inside the
         * {@code LineExecutor}.  Memory is bounded regardless of input size:
         *   • no input buffering (iterator consumed lazily),
         *   • no result buffering (each {@link LineResult} streamed via
         *     {@code listener.onResult} and dropped),
         *   • aggregation through {@link com.yurii.analyzer.core.optimization.OnlineMetricAggregator}
         *     which keeps O(K) per-metric stats + O(|Pareto front|) candidates.
         *
         * The legacy two-pass score formula is intentionally NOT used here —
         * it requires the full corpus in memory.  Selection at this scale is
         * Pareto + per-metric champions only, which is the right primitive
         * for combinatorial / GP / superoptimization workloads anyway.
         *
         * @param candidates  iterator over raw candidate text (one per line)
         * @param executor    pluggable strategy to turn each line into
         *                    metric-bearing payload (see {@link com.yurii.analyzer.core.optimization.LineExecutor})
         * @param topK        how many top-by-score lines to retain in the snapshot
         * @param maximizeKeys keys whose Pareto axis should be maximised
         *                    (default minimise for everything else)
         * @param listener    receives onResult per candidate, onProgress every 1000
         * @return            final snapshot from the online aggregator
         */
        public com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot
                analyzeStream(java.util.Iterator<String> candidates,
                              com.yurii.analyzer.core.optimization.LineExecutor executor,
                              int topK,
                              java.util.Set<String> maximizeKeys,
                              AnalysisListener listener) {
            // Legacy overload: convert binary maximizeKeys → List<GoalSpec> on
            // the fly. Modern callers should use analyzeStream(..., List<GoalSpec>).
            return analyzeStream(candidates, executor, topK,
                    /* fake conversion: per-key goals built lazily as keys appear */
                    binaryGoalsAdapter(maximizeKeys),
                    listener);
        }

        /** Turn a {@code Set<String>} of "maximise these" into a List<GoalSpec>
         *  with the convention "everything in the set is MAX, everything else
         *  is MIN".  Since we don't yet know all keys, we return a "blueprint"
         *  list that the aggregator extends lazily as new keys arrive. */
        private static java.util.List<com.yurii.analyzer.core.optimization.GoalSpec>
                binaryGoalsAdapter(java.util.Set<String> maximizeKeys) {
            java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> out = new java.util.ArrayList<>();
            if (maximizeKeys != null) for (String k : maximizeKeys) {
                out.add(com.yurii.analyzer.core.optimization.GoalSpec.max(k));
            }
            return out;
        }

        /**
         * Modern streaming entry point: per-axis modes (MIN/MAX/TARGET) and
         * weights via {@link com.yurii.analyzer.core.optimization.GoalSpec}.
         * The resulting {@link com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot}
         * carries the goal list so {@link com.yurii.analyzer.core.optimization.BalancedOptimumSelector}
         * can compute "balanced optimum" picks (weighted sum / Tchebycheff /
         * distance-to-ideal) without re-specification.
         */
        public com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot
                analyzeStream(java.util.Iterator<String> candidates,
                              com.yurii.analyzer.core.optimization.LineExecutor executor,
                              int topK,
                              java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals,
                              AnalysisListener listener) {
            return analyzeStream(candidates, executor, topK, goals,
                    com.yurii.analyzer.core.optimization.DiscoveryPolicy.DEFAULT, listener);
        }

        /** Most-explicit streaming entry point: declared goals + auto-discovery
         *  policy.  All auto-discovered numeric K=V keys are included by
         *  default (with lexical mode inference) — making the analyzer
         *  agnostic-to-incoming-keys as originally intended. */
        public com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot
                analyzeStream(java.util.Iterator<String> candidates,
                              com.yurii.analyzer.core.optimization.LineExecutor executor,
                              int topK,
                              java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals,
                              com.yurii.analyzer.core.optimization.DiscoveryPolicy autoPolicy,
                              AnalysisListener listener) {
            if (executor == null) executor = new com.yurii.analyzer.core.optimization.LineExecutor.Inline();
            if (listener == null) listener = new AnalysisListener() {};
            com.yurii.analyzer.core.optimization.OnlineMetricAggregator agg =
                    new com.yurii.analyzer.core.optimization.OnlineMetricAggregator(topK, goals, autoPolicy);

            listener.onLog("Streaming analysis started (executor="
                    + executor.getClass().getSimpleName() + ")");
            int lineNo = 0;
            long failures = 0;
            while (candidates != null && candidates.hasNext()) {
                String raw = candidates.next();
                if (raw == null) continue;
                lineNo++;
                try {
                    String resolved = executor.execute(lineNo, raw);
                    LineFeatures f = extractFeatures(lineNo, resolved, raw);
                    // Light-weight LineResult — no aggregate score (would need
                    // 2 passes).  We pass 0.0 for score and let the
                    // aggregator's Pareto + champions do the selection.
                    LineResult r = new LineResult(lineNo, raw, raw, f, 0.0,
                            "stream", java.util.Map.of(),
                            java.util.List.of(), java.util.List.of());
                    agg.add(r);
                    listener.onResult(r);
                } catch (Exception ex) {
                    failures++;
                    listener.onError("candidate #" + lineNo + " failed", ex);
                }
                if (lineNo % 1000 == 0) {
                    listener.onProgress(lineNo, -1,
                            "Streaming: " + lineNo + " candidates, |Pareto|=" + agg.paretoSize());
                }
            }
            listener.onLog("Streaming analysis complete: " + lineNo
                    + " candidates, " + failures + " failures, |Pareto|="
                    + agg.paretoSize());
            return agg.snapshot().withCacheStats(executor.cacheStats());
        }

        /**
         * Parallel streaming overload.  When {@code parallelism > 1}, spawns
         * that many workers each with a local {@link com.yurii.analyzer.core.optimization.OnlineMetricAggregator};
         * the main thread drains the input iterator into a bounded queue
         * with a poison-pill cascade; workers drain the queue, run
         * {@code executor.execute} → {@code extractFeatures} → local
         * aggregator update; on shutdown, local aggregators are merged into
         * a global one via {@code OnlineMetricAggregator.merge}.
         *
         * Determinism: numerical statistics (μ/σ/min/max/champions) are
         * identical to single-threaded — Welford's parallel algorithm is
         * associative.  Pareto-front membership is a SET property and
         * therefore deterministic.  Reservoir contents differ from the
         * single-threaded version because each shard runs Algorithm R
         * independently then merges, but the uniform-sample property is
         * preserved under approximately-equal shard sizes (round-robin
         * distribution achieves this).
         *
         * @param parallelism  workers to spawn.  ≤ 1 falls back to
         *                     the single-threaded path.  Caller should pick
         *                     based on (a) CPU cores AND (b) executor
         *                     concurrency cost — e.g. {@code LineExecutor.Shell}
         *                     spawns subprocesses, so high parallelism may
         *                     overwhelm the OS.
         * @param listener     called from worker threads — must be thread-safe.
         */
        public com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot
                analyzeStreamParallel(java.util.Iterator<String> candidates,
                                       com.yurii.analyzer.core.optimization.LineExecutor executor,
                                       int topK,
                                       java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals,
                                       com.yurii.analyzer.core.optimization.DiscoveryPolicy autoPolicy,
                                       int parallelism,
                                       AnalysisListener listener) {
            // Default scheduler is byte-for-byte equivalent to the legacy
            // hard-coded path: single shared queue + cascaded poison.
            return analyzeStreamParallel(candidates, executor, topK, goals, autoPolicy,
                    parallelism,
                    new com.yurii.analyzer.core.parallel.WorkStealingScheduler(Math.max(2, parallelism)),
                    listener);
        }

        /**
         * Tier-3 win 3.3 — explicit pluggable scheduler overload.  Pass any
         * {@link com.yurii.analyzer.core.parallel.Scheduler} to control work
         * distribution; defaults available:
         *   • {@link com.yurii.analyzer.core.parallel.WorkStealingScheduler}
         *     — uniform candidates, shared queue, free-worker-takes-first.
         *   • {@link com.yurii.analyzer.core.parallel.LeastLoadedScheduler}
         *     — high cost variance, per-worker queues with min-size routing.
         *   • {@link com.yurii.analyzer.core.parallel.CapabilityAwareScheduler}
         *     — mixed runtimes, tag-affinity per worker.
         */
        public com.yurii.analyzer.core.optimization.OnlineMetricAggregator.Snapshot
                analyzeStreamParallel(java.util.Iterator<String> candidates,
                                       com.yurii.analyzer.core.optimization.LineExecutor executor,
                                       int topK,
                                       java.util.List<com.yurii.analyzer.core.optimization.GoalSpec> goals,
                                       com.yurii.analyzer.core.optimization.DiscoveryPolicy autoPolicy,
                                       int parallelism,
                                       com.yurii.analyzer.core.parallel.Scheduler scheduler,
                                       AnalysisListener listener) {
            if (parallelism <= 1)
                return analyzeStream(candidates, executor, topK, goals, autoPolicy, listener);
            if (executor == null) executor = new com.yurii.analyzer.core.optimization.LineExecutor.Inline();
            if (listener == null) listener = new AnalysisListener() {};
            if (scheduler == null) scheduler = new com.yurii.analyzer.core.parallel.WorkStealingScheduler(parallelism);

            final com.yurii.analyzer.core.optimization.LineExecutor execRef = executor;
            final AnalysisListener listenerRef = listener;
            final com.yurii.analyzer.core.parallel.Scheduler schedRef = scheduler;

            // Each worker holds its own aggregator; the global is built by merging.
            java.util.List<com.yurii.analyzer.core.optimization.OnlineMetricAggregator> locals =
                    new java.util.ArrayList<>(parallelism);
            for (int i = 0; i < parallelism; i++) {
                locals.add(new com.yurii.analyzer.core.optimization.OnlineMetricAggregator(topK, goals, autoPolicy));
            }

            final java.util.concurrent.atomic.AtomicLong failures = new java.util.concurrent.atomic.AtomicLong();
            final java.util.concurrent.atomic.AtomicLong processed = new java.util.concurrent.atomic.AtomicLong();

            java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newFixedThreadPool(
                    parallelism,
                    r -> {
                        // Thread name is overwritten per-task with the worker-id suffix
                        // inside the lambda below so verifiers can introspect routing.
                        Thread t = new Thread(r, "analyzeStream-worker");
                        t.setDaemon(true);
                        return t;
                    });
            java.util.List<java.util.concurrent.Future<?>> futures = new java.util.ArrayList<>(parallelism);
            final int finalParallelism = parallelism;
            for (int w = 0; w < parallelism; w++) {
                final int workerId = w;
                final com.yurii.analyzer.core.optimization.OnlineMetricAggregator local = locals.get(w);
                futures.add(pool.submit(() -> {
                    // Stamp the thread with the lambda's worker id so external
                    // tooling (and the SchedulerVerify capability-routing check)
                    // can correlate a thread's activity with the scheduler slot.
                    Thread.currentThread().setName("analyzeStream-worker-" + workerId);
                    try {
                        while (true) {
                            com.yurii.analyzer.core.parallel.Scheduler.Task task = schedRef.take(workerId);
                            if (task == com.yurii.analyzer.core.parallel.Scheduler.Task.POISON) return;
                            long t0 = System.nanoTime();
                            try {
                                String resolved = execRef.execute(task.lineNo(), task.raw());
                                LineFeatures f = extractFeatures(task.lineNo(), resolved, task.raw());
                                LineResult r = new LineResult(task.lineNo(), task.raw(), task.raw(), f, 0.0,
                                        "stream", java.util.Map.of(),
                                        java.util.List.of(), java.util.List.of());
                                local.add(r);
                                listenerRef.onResult(r);
                                long pc = processed.incrementAndGet();
                                if ((pc & 0x3FF) == 0)
                                    listenerRef.onProgress((int) pc, -1,
                                            "Streaming(P=" + finalParallelism + "): " + pc + " candidates");
                            } catch (Exception ex) {
                                failures.incrementAndGet();
                                listenerRef.onError("candidate #" + task.lineNo() + " failed", ex);
                            } finally {
                                schedRef.taskCompleted(workerId, System.nanoTime() - t0);
                            }
                        }
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    }
                }));
            }

            listener.onLog("Streaming analysis started (parallel=" + parallelism
                    + ", executor=" + executor.getClass().getSimpleName()
                    + ", scheduler=" + scheduler.getClass().getSimpleName() + ")");
            int lineNo = 0;
            try {
                while (candidates != null && candidates.hasNext()) {
                    String raw = candidates.next();
                    if (raw == null) continue;
                    lineNo++;
                    try {
                        schedRef.submit(lineNo, raw);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            } finally {
                try { schedRef.close(); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
            }
            for (java.util.concurrent.Future<?> f : futures) {
                try { f.get(); } catch (Exception ignored) {}
            }
            pool.shutdown();

            // Reduce: merge all locals into a single global aggregator.
            com.yurii.analyzer.core.optimization.OnlineMetricAggregator global =
                    new com.yurii.analyzer.core.optimization.OnlineMetricAggregator(topK, goals, autoPolicy);
            for (com.yurii.analyzer.core.optimization.OnlineMetricAggregator local : locals) {
                global.merge(local);
            }

            listener.onLog("Streaming analysis complete: " + lineNo
                    + " candidates, " + failures.get() + " failures, |Pareto|="
                    + global.paretoSize() + " (parallel " + parallelism + " workers, merged)");
            return global.snapshot().withCacheStats(execRef.cacheStats());
        }

        public void analyzeLines(List<String> rawLines, AnalysisListener listener) {
            listener.onLog("Initializing batch memory processing for " + rawLines.size() + " lines.");
            for (OptimizationGoal g : optGoals) {
                if (g.optimumValid) {
                    listener.onLog(String.format(Locale.ROOT,
                            "Brent-minimised objective '%s' on [%g, %g]: argmin=%.6g, fmin=%.6g",
                            g.objective, g.searchLo, g.searchHi, g.computedArgmin, g.computedOptimum));
                }
            }

            List<LogicalCommandBlock> blocks = collectLogicalCommands(rawLines);
            int n = blocks.size();
            ProfileBuilder builder = new ProfileBuilder();
            List<LineFeatures> feats = new ArrayList<>(n);

            for (int i = 0; i < n; i++) {
                LogicalCommandBlock block = blocks.get(i);
                String resolved = resolveLinePayload(block.commandText, executeCommands, commandTimeout);
                LineFeatures f = extractFeatures(block.startLineNo, resolved, block.commandText);
                feats.add(f);
                accumulateInto(builder, f);
                if (i % 50 == 0) listener.onProgress(i, n, "Profiling (Memory) " + i + " / " + n);
            }

            this.profile = finalize(builder);
            this.rules = synthesizeRules(this.profile, this.profile.nonemptyLines);
            listener.onProfileReady(this.profile, this.rules);

            List<LineResult> res = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                LineResult lr = scoreLine(feats.get(i), this.profile, this.rules);
                res.add(lr);
                listener.onResult(lr);
                if (i % 50 == 0) listener.onProgress(i, n, "Scoring (Memory) " + i + " / " + n);
            }

            reportOptimisationDiagnostics(res, listener);
            listener.onFinished(new AnalysisContext(this.profile, this.rules, res, -1));
        }

        /**
         * Surface the real optimisation-theory results: Simpson-integrated AUC of the score
         * curve, Pareto-optimal subset across configured goals, and the RK4 residual against
         * the analytical confidence ODE. Logged via the listener so the UI can show them.
         */
        private void reportOptimisationDiagnostics(List<LineResult> results, AnalysisListener listener) {
            if (results == null || results.isEmpty()) return;
            try {
                double auc = simpsonScoreAuc(results);
                listener.onLog(String.format(Locale.ROOT,
                        "Simpson AUC over %d-line score curve = %.4f (mean score ≈ %.4f)",
                        results.size(), auc, auc / Math.max(1, results.size() - 1)));

                if (!optGoals.isEmpty()) {
                    List<LineResult> front = paretoOptimal(results, optGoals);
                    listener.onLog(String.format(Locale.ROOT,
                            "Pareto-optimal frontier: %d non-dominated line(s) across %d objective(s)",
                            front.size(), optGoals.size()));
                    int reported = 0;
                    for (LineResult r : front) {
                        if (reported++ >= 5) {
                            listener.onLog("  … (" + (front.size() - 5) + " more)");
                            break;
                        }
                        listener.onLog(String.format(Locale.ROOT,
                                "  • line #%d  score=%.2f  type=%s  decision=%s",
                                r.lineNo, r.score, r.features.lineType, r.decision));
                    }
                }

                double[] residuals = verifyConfidenceOde(20);
                double maxResidual = 0;
                for (double v : residuals) if (v > maxResidual) maxResidual = v;
                listener.onLog(String.format(Locale.ROOT,
                        "Confidence ODE C'(n) = (1-C)/100 verified by RK4: max |C_RK4 - C_analytical| = %.3g over n=[0,20]",
                        maxResidual));

                // ─── Auto-discovered metric stream → full optimisation-theory sweep ────
                // Every numeric K/V key in line outputs (executed stdout/stderr or
                // static text) is treated as a time series indexed by lineNo. The
                // toolkit (Brent / Newton / Nelder-Mead / SA / Simpson / RK4) is
                // applied per-metric without any prior config declaration.
                List<com.yurii.analyzer.core.optimization.MetricStreamAnalyzer.MetricAnalysis> streams =
                        com.yurii.analyzer.core.optimization.MetricStreamAnalyzer.analyzeAll(results, 5);
                if (!streams.isEmpty()) {
                    listener.onLog("Auto-discovered " + streams.size()
                            + " numeric metric stream(s); per-metric optimisation-theory sweep:");
                    int reported = 0;
                    for (var ma : streams) {
                        if (reported++ >= 8) {
                            listener.onLog("  … (" + (streams.size() - 8) + " more metric(s) elided)");
                            break;
                        }
                        listener.onLog(String.format(Locale.ROOT,
                                "  '%s' n=%d  μ=%.4g  σ=%.4g  P5/P50/P95=%.3g/%.3g/%.3g  ∫Simpson=%.4g",
                                ma.key(), ma.n(), ma.mean(), ma.stdev(),
                                ma.p5(), ma.p50(), ma.p95(), ma.simpsonAuc()));
                        listener.onLog(String.format(Locale.ROOT,
                                "    Brent argmin@line[≈%.2f]=%.4g  argmax@line[≈%.2f]=%.4g",
                                ma.brentArgmin(), ma.brentMin(), ma.brentArgmax(), ma.brentMax()));
                        listener.onLog(String.format(Locale.ROOT,
                                "    Nelder-Mead exp-fit (a=%.4g, b=%.4g, c=%.4g)  loss=%.4g  |  SA min=%.4g  |  RK4 τ=%.3f",
                                ma.expFitParams()[0], ma.expFitParams()[1], ma.expFitParams()[2],
                                ma.expFitLoss(), ma.saMin(), ma.rk4Tau()));
                        if (ma.criticalPoints().length > 0) {
                            StringBuilder sb = new StringBuilder("    Newton critical points (line indices): ");
                            for (double cp : ma.criticalPoints()) sb.append(String.format(Locale.ROOT, "%.2f ", cp));
                            listener.onLog(sb.toString());
                        }
                    }

                    List<LineResult> autoFront =
                            com.yurii.analyzer.core.optimization.MetricStreamAnalyzer.autoPareto(results, 5);
                    listener.onLog(String.format(Locale.ROOT,
                            "Auto-Pareto across all %d discovered metrics: %d non-dominated line(s)",
                            streams.size(), autoFront.size()));
                }
            } catch (Exception e) {
                listener.onError("Optimisation diagnostics failed", e);
            }
        }

        public void analyzeStreamed(Path file, AnalysisSettings settings, AnalysisListener listener,
                                    AtomicBoolean cancelled, boolean useDb) throws Exception {
            if (useDb) {
                try {
                    analyzeWithDatabase(file, settings, listener, cancelled);
                    return;
                } catch (SQLException sqle) {
                    listener.onError("DB unavailable, falling back to in-memory streaming: " + sqle.getMessage(), sqle);
                }
            }
            listener.onLog("Fallback: in-memory stream");
            List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
            analyzeLines(lines, listener);
        }

        // ─── Database-backed streaming analysis (true multi-worker) ───────

        private void analyzeWithDatabase(Path file, AnalysisSettings set, AnalysisListener listener,
                                         AtomicBoolean cancelled) throws Exception {
            DatabaseManager db = DatabaseManager.getInstance();
            db.initSchema();
            long runId = db.startRun(file.toString(), toPrettyJson(this.manual));
            listener.onLog("Started DB run ID: " + runId);

            int workers = set.workers;
            ExecutorService exec = Executors.newFixedThreadPool(workers, daemonFactory("analyzer-worker"));
            BlockingQueue<LineTask> taskQueue = new ArrayBlockingQueue<>(set.queueCapacity);

            ProfileBuilder shared = new ProfileBuilder();
            Object profileLock = new Object();

            AtomicInteger processedPhase1 = new AtomicInteger();
            List<Future<?>> phase1 = new ArrayList<>();
            for (int w = 0; w < workers; w++) {
                phase1.add(exec.submit(() -> {
                    try {
                        ProfileBuilder local = new ProfileBuilder();
                        List<LineFeatures> batch = new ArrayList<>(500);
                        while (!cancelled.get()) {
                            LineTask t = taskQueue.take();
                            if (t.poison) {
                                taskQueue.put(t); // cascade poison to siblings
                                break;
                            }
                            LineFeatures f = extractFeatures(t.lineNo, t.payload, t.originalLine);
                            accumulateInto(local, f);
                            batch.add(f);
                            if (batch.size() >= 500) {
                                db.insertFeaturesBatch(runId, batch);
                                batch.clear();
                            }
                            int pc = processedPhase1.incrementAndGet();
                            if (pc % 1000 == 0) listener.onProgress(pc, -1, "Phase 1 (Profile & DB): " + pc + " lines");
                        }
                        if (!batch.isEmpty()) db.insertFeaturesBatch(runId, batch);
                        synchronized (profileLock) { mergeBuilders(shared, local); }
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    } catch (Exception e) {
                        listener.onError("Phase 1 worker died", e);
                    }
                }));
            }

            try {
                forEachLogicalCommand(file, cancelled, (startLineNo, endLineNo, cmd) -> {
                    if (cancelled.get()) return;
                    String resolved = resolveLinePayload(cmd, set.executeCommands, set.commandTimeout);
                    try {
                        taskQueue.put(new LineTask(startLineNo, cmd, resolved));
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    }
                });
            } finally {
                taskQueue.put(LineTask.poison());
            }
            for (Future<?> f : phase1) try { f.get(); } catch (Exception ignored) {}

            if (cancelled.get()) {
                exec.shutdownNow();
                return;
            }

            CorpusProfile finalProfile = finalize(shared);
            SynthesizedRules finalRules = synthesizeRules(finalProfile, finalProfile.nonemptyLines);
            this.profile = finalProfile;
            this.rules = finalRules;
            db.updateRunStats(runId, finalProfile.totalLines, toPrettyJson(finalProfile.toMap()),
                    toPrettyJson(finalRules.toMap()));
            listener.onProfileReady(finalProfile, finalRules);

            // ─── Phase 2: parallel scoring from DB ────────────────────────
            listener.onLog("Phase 2: Scoring lines from DB...");
            int totalDbLines = finalProfile.totalLines;
            AtomicInteger processedPhase2 = new AtomicInteger();
            BlockingQueue<LineFeatures> scoreQueue = new ArrayBlockingQueue<>(set.queueCapacity);
            Object dbResultLock = new Object();

            List<Future<?>> phase2 = new ArrayList<>();
            for (int w = 0; w < workers; w++) {
                phase2.add(exec.submit(() -> {
                    try {
                        List<LineResult> batch = new ArrayList<>(500);
                        while (!cancelled.get()) {
                            LineFeatures f = scoreQueue.take();
                            if (f == POISON_FEATURES || f.lineNo == -1) {
                                scoreQueue.put(POISON_FEATURES);
                                break;
                            }
                            LineResult r = scoreLine(f, finalProfile, finalRules);
                            batch.add(r);
                            if (batch.size() >= 500) flushPhase2(db, runId, batch, listener, dbResultLock);
                            int pc = processedPhase2.incrementAndGet();
                            if (pc % 1000 == 0) listener.onProgress(pc, totalDbLines,
                                    "Phase 2 (Scoring): " + pc + " / " + totalDbLines);
                        }
                        if (!batch.isEmpty()) flushPhase2(db, runId, batch, listener, dbResultLock);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                    } catch (Exception e) {
                        listener.onError("Phase 2 worker died", e);
                    }
                }));
            }

            try {
                db.streamFeatures(runId, f -> {
                    if (cancelled.get()) return;
                    try { scoreQueue.put(f); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
                });
            } finally {
                scoreQueue.put(POISON_FEATURES);
            }
            for (Future<?> f : phase2) try { f.get(); } catch (Exception ignored) {}
            exec.shutdown();

            db.finalizeRun(runId);

            // Pull a representative top slice from the DB to compute Pareto / Simpson AUC.
            try {
                List<LineResult> diagnosticsSlice = db.getLatestResults(runId, 2000);
                Collections.reverse(diagnosticsSlice); // line_no order, ascending
                reportOptimisationDiagnostics(diagnosticsSlice, listener);
            } catch (SQLException sqle) {
                listener.onLog("Diagnostics slice unavailable: " + sqle.getMessage());
            }
            listener.onFinished(new AnalysisContext(finalProfile, finalRules, null, runId));
        }

        private static void flushPhase2(DatabaseManager db, long runId, List<LineResult> batch,
                                        AnalysisListener listener, Object lock) throws SQLException {
            synchronized (lock) {
                db.insertResultsBatch(runId, batch);
                for (LineResult br : batch) listener.onResult(br);
            }
            batch.clear();
        }

        private static void mergeBuilders(ProfileBuilder a, ProfileBuilder b) {
            a.totalLines += b.totalLines;
            a.nonemptyLines += b.nonemptyLines;
            a.emptyLines += b.emptyLines;
            a.lengths.merge(b.lengths);
            a.entropies.merge(b.entropies);
            int budget = ProfileBuilder.SAMPLE_CAP - a.lengthSamples.size();
            if (budget > 0) {
                List<Double> take = b.lengthSamples.subList(0, Math.min(budget, b.lengthSamples.size()));
                a.lengthSamples.addAll(take);
            }
            budget = ProfileBuilder.SAMPLE_CAP - a.entropySamples.size();
            if (budget > 0) {
                List<Double> take = b.entropySamples.subList(0, Math.min(budget, b.entropySamples.size()));
                a.entropySamples.addAll(take);
            }
            for (Map.Entry<String, ArrayList<Double>> e : b.optSamples.entrySet())
                a.optSamples.computeIfAbsent(e.getKey(), k -> new ArrayList<>()).addAll(e.getValue());
            for (Map.Entry<String, Integer> e : b.tokenDf.entrySet()) a.tokenDf.merge(e.getKey(), e.getValue(), Integer::sum);
            for (Map.Entry<String, Integer> e : b.keyDf.entrySet()) a.keyDf.merge(e.getKey(), e.getValue(), Integer::sum);
            for (Map.Entry<String, Integer> e : b.numberDf.entrySet()) a.numberDf.merge(e.getKey(), e.getValue(), Integer::sum);
            for (Map.Entry<String, Integer> e : b.lineTypeDf.entrySet()) a.lineTypeDf.merge(e.getKey(), e.getValue(), Integer::sum);
            for (Map.Entry<String, Integer> e : b.sigDf.entrySet()) a.sigDf.merge(e.getKey(), e.getValue(), Integer::sum);
        }

        private static java.util.concurrent.ThreadFactory daemonFactory(String name) {
            AtomicInteger idx = new AtomicInteger();
            return r -> {
                Thread t = new Thread(r, name + "-" + idx.incrementAndGet());
                t.setDaemon(true);
                return t;
            };
        }
    }

    // ─── DatabaseManager: env-driven, no destructive boot ────────────────

    public static final class DatabaseManager {
        private static volatile DatabaseManager instance;
        private final Connection conn;

        private DatabaseManager() throws SQLException {
            this.conn = openOrCreate();
            this.conn.setAutoCommit(true);
            initSchema();
            registerShutdownHook();
        }

        private static Connection openOrCreate() throws SQLException {
            try {
                return DriverManager.getConnection(DB_URL, DB_USER, DB_PASS);
            } catch (SQLException e) {
                // SQLState 3D000 => undefined database. Try to create it from the maintenance DB.
                if ("3D000".equals(e.getSQLState())) {
                    String dbName = extractDbName(DB_URL);
                    String adminUrl = DB_URL.replaceAll("/[^/?]+(\\?|$)", "/postgres$1");
                    try (Connection admin = DriverManager.getConnection(adminUrl, DB_USER, DB_PASS);
                         Statement st = admin.createStatement()) {
                        admin.setAutoCommit(true);
                        st.executeUpdate("CREATE DATABASE \"" + dbName.replace("\"", "\"\"") + "\"");
                    }
                    return DriverManager.getConnection(DB_URL, DB_USER, DB_PASS);
                }
                throw e;
            }
        }

        private static String extractDbName(String jdbcUrl) {
            String stripped = jdbcUrl.split("\\?")[0];
            int slash = stripped.lastIndexOf('/');
            return slash >= 0 ? stripped.substring(slash + 1) : stripped;
        }

        private void registerShutdownHook() {
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                try { if (conn != null && !conn.isClosed()) conn.close(); } catch (SQLException ignored) {}
            }, "db-shutdown"));
        }

        public static DatabaseManager getInstance() throws SQLException {
            DatabaseManager local = instance;
            if (local != null) return local;
            synchronized (DatabaseManager.class) {
                if (instance == null) instance = new DatabaseManager();
                return instance;
            }
        }

        public Connection rawConnection() { return conn; }

        public void initSchema() throws SQLException {
            try (Statement s = conn.createStatement()) {
                s.execute("CREATE TABLE IF NOT EXISTS analysis_runs (" +
                        "run_id BIGSERIAL PRIMARY KEY, " +
                        "start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, " +
                        "end_time TIMESTAMP, " +
                        "file_path TEXT, " +
                        "manual_config JSONB, " +
                        "total_lines INT DEFAULT 0, " +
                        "profile JSONB, " +
                        "rules JSONB, " +
                        "status VARCHAR(20) DEFAULT 'RUNNING')");

                s.execute("CREATE TABLE IF NOT EXISTS analysis_features (" +
                        "run_id BIGINT REFERENCES analysis_runs(run_id), " +
                        "line_no INT, " +
                        "original_line TEXT, " +
                        "raw_payload TEXT, " +
                        "length INT, " +
                        "entropy FLOAT, " +
                        "line_type VARCHAR(50), " +
                        "signature TEXT, " +
                        "features_json JSONB, " +
                        "PRIMARY KEY (run_id, line_no))");

                s.execute("CREATE TABLE IF NOT EXISTS analysis_results (" +
                        "run_id BIGINT REFERENCES analysis_runs(run_id), " +
                        "line_no INT, " +
                        "score FLOAT, " +
                        "decision VARCHAR(20), " +
                        "original_line TEXT, " +
                        "raw_payload TEXT, " +
                        "line_type VARCHAR(50), " +
                        "length INT, " +
                        "entropy FLOAT, " +
                        "tokens INT, " +
                        "keys INT, " +
                        "numbers INT, " +
                        "signature TEXT, " +
                        "notes TEXT, " +
                        "matched_rules TEXT, " +
                        "PRIMARY KEY (run_id, line_no))");

                s.execute("CREATE INDEX IF NOT EXISTS idx_features_run ON analysis_features(run_id)");
                s.execute("CREATE INDEX IF NOT EXISTS idx_results_run_score ON analysis_results(run_id, score DESC)");
            }
        }

        public synchronized long startRun(String filePath, String manualJson) throws SQLException {
            String sql = "INSERT INTO analysis_runs (file_path, manual_config) VALUES (?, ?::jsonb) RETURNING run_id";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setString(1, filePath);
                ps.setString(2, manualJson);
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next()) return rs.getLong(1);
                }
            }
            return -1;
        }

        public synchronized void updateRunStats(long runId, int totalLines, String profileJson, String rulesJson) throws SQLException {
            String sql = "UPDATE analysis_runs SET total_lines = ?, profile = ?::jsonb, rules = ?::jsonb WHERE run_id = ?";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setInt(1, totalLines);
                ps.setString(2, profileJson);
                ps.setString(3, rulesJson);
                ps.setLong(4, runId);
                ps.executeUpdate();
            }
        }

        public synchronized void finalizeRun(long runId) throws SQLException {
            String sql = "UPDATE analysis_runs SET status = 'FINISHED', end_time = CURRENT_TIMESTAMP WHERE run_id = ?";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setLong(1, runId);
                ps.executeUpdate();
            }
        }

        public synchronized void insertFeaturesBatch(long runId, List<LineFeatures> batch) throws SQLException {
            boolean auto = conn.getAutoCommit();
            conn.setAutoCommit(false);
            String sql = "INSERT INTO analysis_features (run_id, line_no, original_line, raw_payload, length, entropy, line_type, signature, features_json) " +
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb) ON CONFLICT DO NOTHING";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                for (LineFeatures f : batch) {
                    ps.setLong(1, runId);
                    ps.setInt(2, f.lineNo);
                    ps.setString(3, f.originalLine);
                    ps.setString(4, f.raw);
                    ps.setInt(5, f.length);
                    ps.setDouble(6, f.entropy);
                    ps.setString(7, f.lineType);
                    ps.setString(8, f.signature);
                    try { ps.setString(9, MAPPER.writeValueAsString(f.toMap())); }
                    catch (Exception e) { ps.setString(9, "{}"); }
                    ps.addBatch();
                }
                ps.executeBatch();
                conn.commit();
            } finally {
                conn.setAutoCommit(auto);
            }
        }

        public synchronized void insertResultsBatch(long runId, List<LineResult> batch) throws SQLException {
            boolean auto = conn.getAutoCommit();
            conn.setAutoCommit(false);
            String sql = "INSERT INTO analysis_results (run_id, line_no, score, decision, original_line, raw_payload, line_type, length, entropy, tokens, keys, numbers, signature, notes, matched_rules) " +
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                for (LineResult r : batch) {
                    ps.setLong(1, runId);
                    ps.setInt(2, r.lineNo);
                    ps.setDouble(3, r.score);
                    ps.setString(4, r.decision);
                    ps.setString(5, r.originalLine);
                    ps.setString(6, r.raw);
                    ps.setString(7, r.features.lineType);
                    ps.setInt(8, r.features.length);
                    ps.setDouble(9, r.features.entropy);
                    ps.setInt(10, r.features.tokens.size());
                    ps.setInt(11, r.features.kvPairs.size());
                    ps.setInt(12, r.features.numbers.size());
                    ps.setString(13, r.features.signature);
                    ps.setString(14, String.join(" ; ", r.notes));
                    ps.setString(15, String.join(" ; ", r.matchedRules));
                    ps.addBatch();
                }
                ps.executeBatch();
                conn.commit();
            } finally {
                conn.setAutoCommit(auto);
            }
        }

        public interface FeatureConsumer { void accept(LineFeatures f); }

        public synchronized void streamFeatures(long runId, FeatureConsumer consumer) throws SQLException {
            boolean auto = conn.getAutoCommit();
            conn.setAutoCommit(false);
            String sql = "SELECT features_json FROM analysis_features WHERE run_id = ? ORDER BY line_no";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setLong(1, runId);
                ps.setFetchSize(5000);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        String j = rs.getString(1);
                        try {
                            JsonNode n = MAPPER.readTree(j);
                            LineFeatures f = new LineFeatures(
                                    n.path("line_no").asInt(),
                                    n.path("raw").asText(),
                                    n.path("original_line").asText(),
                                    n.path("text").asText(),
                                    n.path("length").asInt(),
                                    jsonArray(n, "tokens"),
                                    jsonArray(n, "token_lowers"),
                                    new ArrayList<>(),
                                    Map.of(), Map.of(), 0,
                                    n.path("entropy").asDouble(),
                                    0, 0, 0, 0, 0, 0,
                                    n.path("signature").asText(),
                                    "", "", n.path("line_type").asText());
                            consumer.accept(f);
                        } catch (Exception ignored) {}
                    }
                }
            } finally {
                conn.setAutoCommit(auto);
            }
        }

        public synchronized LineResult getLineResult(long runId, int offsetRowIndex) throws SQLException {
            String sql = "SELECT * FROM analysis_results WHERE run_id = ? ORDER BY line_no OFFSET ? LIMIT 1";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setLong(1, runId);
                ps.setInt(2, offsetRowIndex);
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next()) return materializeResult(rs);
                }
            }
            return null;
        }

        public synchronized LineResult getOptimalResult(long runId) throws SQLException {
            String sql = "SELECT * FROM analysis_results WHERE run_id = ? ORDER BY score DESC LIMIT 1";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setLong(1, runId);
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next()) return materializeResult(rs);
                }
            }
            return null;
        }

        private static LineResult materializeResult(ResultSet rs) throws SQLException {
            return new LineResult(
                    rs.getInt("line_no"),
                    rs.getString("original_line"),
                    rs.getString("raw_payload"),
                    emptyFeatures(),
                    rs.getDouble("score"),
                    rs.getString("decision"),
                    Map.of(),
                    splitNonNull(rs.getString("notes")),
                    splitNonNull(rs.getString("matched_rules")));
        }

        private static List<String> splitNonNull(String s) {
            if (s == null || s.isEmpty()) return List.of();
            return List.of(s.split(" ; "));
        }

        public synchronized void exportJson(long runId, Path path) throws Exception {
            String sqlRun = "SELECT profile, rules FROM analysis_runs WHERE run_id = ?";
            String sqlRes = "SELECT row_to_json(r) FROM analysis_results r WHERE run_id = ? ORDER BY line_no";
            try (PrintWriter pw = new PrintWriter(Files.newBufferedWriter(path, StandardCharsets.UTF_8))) {
                pw.println("{");
                try (PreparedStatement ps = conn.prepareStatement(sqlRun)) {
                    ps.setLong(1, runId);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            pw.println("\"profile\": " + rs.getString(1) + ",");
                            pw.println("\"rules\": " + rs.getString(2) + ",");
                        }
                    }
                }
                pw.println("\"results\": [");
                try (PreparedStatement ps = conn.prepareStatement(sqlRes)) {
                    ps.setLong(1, runId);
                    ps.setFetchSize(5000);
                    try (ResultSet rs = ps.executeQuery()) {
                        boolean first = true;
                        while (rs.next()) {
                            if (!first) pw.println(",");
                            pw.print("  " + rs.getString(1));
                            first = false;
                        }
                    }
                }
                pw.println("\n]}");
            }
        }

        /**
         * CSV export via PostgreSQL COPY. Uses the JDBC driver's CopyManager — the legacy
         * {@code COPY ... TO STDOUT} via {@link PreparedStatement#executeQuery} was a no-op.
         */
        public synchronized void exportCsv(long runId, Path path) throws Exception {
            String sql = "COPY (SELECT line_no, score, decision, original_line, raw_payload, line_type, length, entropy, " +
                    "tokens, keys, numbers, signature, notes, matched_rules FROM analysis_results " +
                    "WHERE run_id = " + runId + " ORDER BY line_no) TO STDOUT WITH CSV HEADER";
            try (Writer w = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                org.postgresql.copy.CopyManager cm = conn.unwrap(org.postgresql.PGConnection.class).getCopyAPI();
                cm.copyOut(sql, w);
            }
        }

        public synchronized List<LineResult> getLatestResults(long runId, int limit) throws SQLException {
            List<LineResult> list = new ArrayList<>();
            String sql = "SELECT * FROM analysis_results WHERE run_id = ? ORDER BY line_no DESC LIMIT ?";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setLong(1, runId);
                ps.setInt(2, limit);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) list.add(materializeResult(rs));
                }
            }
            return list;
        }
    }

    // ─── Static export helpers (in-memory paths) ────────────────────────

    public static void exportCsv(Path path, List<LineResult> results) throws IOException {
        try (BufferedWriter bw = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            bw.write("LineNo,Score,Decision,OriginalLine,Type,Length,Entropy,Tokens,Keys,Numbers,Signature,Notes,MatchedRules\n");
            for (LineResult r : results) {
                LineFeatures f = r.features;
                bw.write(String.format(Locale.ROOT, "%d,%.2f,%s,%s,%s,%d,%.3f,%d,%d,%d,%s,%s,%s\n",
                        r.lineNo, r.score, r.decision, csv(r.originalLine), f.lineType, f.length, f.entropy,
                        f.tokens.size(), f.kvPairs.size(), f.numbers.size(), csv(f.signature),
                        csv(String.join(" ; ", r.notes)), csv(String.join(" ; ", r.matchedRules))));
            }
        }
    }

    public static void exportJson(Path path, CorpusProfile profile, SynthesizedRules rules,
                                  List<LineResult> results) throws IOException {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("profile", profile.toMap());
        root.put("rules", rules.toMap());
        root.put("results", results.stream().map(LineResult::toMap).toList());
        Files.writeString(path, toPrettyJson(root), StandardCharsets.UTF_8);
    }

    private static String csv(Object val) {
        if (val == null) return "";
        String s = String.valueOf(val);
        if (s.contains(",") || s.contains("\"") || s.contains("\n") || s.contains("\r"))
            return "\"" + s.replace("\"", "\"\"") + "\"";
        return s;
    }
}
