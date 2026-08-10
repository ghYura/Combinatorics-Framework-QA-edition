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

import com.fasterxml.jackson.databind.JsonNode;
import com.yurii.analyzer.core.AnalyzerCore;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;

/**
 * Pluggable strategy for turning one line of input text into a flat
 * {@code key → value} map of agnostic K/V metrics.  Addresses the gap I
 * called out in the "agnostic" audit: the analyzer's optimization layer is
 * agnostic about what metrics MEAN, but the parser was opinionated about
 * how input is FORMATTED (only {@code key=value} / {@code key:value} via
 * the {@code KV_PAIR_RE} regex).
 *
 * Three default implementations:
 *
 *   • {@link KvLineParser} — the original behaviour: regex-based scan for
 *     {@code key=value} / {@code key:value} pairs.  Default, unchanged.
 *
 *   • {@link JsonLineParser} — each line is a JSON object; every numeric
 *     or string-numeric leaf becomes one K/V entry.  Nested objects are
 *     flattened with dot-paths ({@code outer.inner = 42}).
 *
 *   • {@link CsvLineParser} — each line is a row of a comma-separated table.
 *     Header column names are supplied at construction time (or auto-named
 *     {@code col_0}, {@code col_1}, … when omitted).  Quoted cells with
 *     embedded delimiters and escaped quotes (RFC-4180 style) are honoured.
 *
 *   • {@link MultiParser} — try parsers in order; the first one that
 *     returns a non-empty map wins.  Useful for heterogeneous corpora.
 *
 * Implementations MUST be thread-safe and stateless across calls.
 */
@FunctionalInterface
public interface LineParser {

    /**
     * @param text  the line content (already trimmed and CR-stripped by the
     *              caller); never null
     * @return      flat map of (key, value-as-string) pairs.  Empty map is
     *              fine — the caller treats it as "no K/V info in this line".
     */
    Map<String, String> parse(String text);

    /** Default: regex-based K=V / K:V parser, identical to the original
     *  inline behaviour in {@code OptimizationAnalyzer.extractFeatures}.
     *  Keys are lower-cased; values are kept verbatim (trimmed). */
    final class KvLineParser implements LineParser {
        @Override public Map<String, String> parse(String text) {
            Map<String, String> kv = new LinkedHashMap<>();
            if (text == null || text.isEmpty()) return kv;
            Matcher km = AnalyzerCore.KV_PAIR_RE.matcher(text);
            while (km.find()) {
                kv.put(km.group(1).trim().toLowerCase(Locale.ROOT),
                       km.group(2).trim());
            }
            return kv;
        }
    }

    /** Each line is a JSON object; numeric and string-numeric leaves
     *  become K/V entries.  Nested objects are flattened with dot-paths.
     *  Arrays of primitives become indexed keys (e.g. {@code latencies.0 = 12.3}).
     *  Non-JSON input returns an empty map (so this parser can be safely
     *  chained behind {@link KvLineParser} via {@link MultiParser}). */
    final class JsonLineParser implements LineParser {
        @Override public Map<String, String> parse(String text) {
            Map<String, String> kv = new LinkedHashMap<>();
            if (text == null || text.isEmpty()) return kv;
            String s = text.trim();
            // Cheap rejection: JSON objects always start with '{' (after trim).
            if (!s.startsWith("{")) return kv;
            try {
                JsonNode root = AnalyzerCore.mapper().readTree(s);
                if (root == null || !root.isObject()) return kv;
                flatten(root, "", kv);
            } catch (Exception ignored) {
                // Malformed JSON → empty map; caller's MultiParser fallback
                // can try the next parser (KvLineParser usually).
            }
            return kv;
        }

        private static void flatten(JsonNode node, String prefix, Map<String, String> out) {
            if (node.isObject()) {
                var it = node.fields();
                while (it.hasNext()) {
                    var e = it.next();
                    String childPrefix = prefix.isEmpty() ? e.getKey().toLowerCase(Locale.ROOT)
                                                          : prefix + "." + e.getKey().toLowerCase(Locale.ROOT);
                    flatten(e.getValue(), childPrefix, out);
                }
            } else if (node.isArray()) {
                for (int i = 0; i < node.size(); i++) {
                    flatten(node.get(i), prefix + "." + i, out);
                }
            } else if (node.isValueNode()) {
                // Skip nulls and explicit booleans (they don't parseNumeric anyway).
                if (node.isNull()) return;
                out.put(prefix, node.asText());
            }
        }
    }

    /** Each line is one row of a comma-separated table.  Column names come
     *  from a header supplied at construction time; if no header is supplied,
     *  cells are exposed as {@code col_0}, {@code col_1}, … so the analyzer's
     *  auto-discovery still has stable keys to latch onto.
     *
     *  Splitting is RFC-4180-lite: double-quoted cells may contain the
     *  delimiter; a doubled quote inside such a cell is treated as a literal
     *  quote.  Empty trailing cells are preserved (matches {@code String.split}
     *  with {@code -1} limit).  Stateless across calls — the header is fixed
     *  at construction time, so passing in the header row mid-stream is the
     *  caller's job (typically: skip {@code n=0}, parse {@code n=0} as the
     *  header, build the parser, then parse the rest).  Keys are lower-cased
     *  to match {@link KvLineParser}. */
    final class CsvLineParser implements LineParser {
        private final String[] headers;        // null → use synthetic "col_<i>"
        private final char     delimiter;

        /** Comma-delimited CSV with no headers (cells exposed as
         *  {@code col_0}, {@code col_1}, …).  Useful when the first row is
         *  data, not metadata. */
        public CsvLineParser() { this(null, ','); }

        /** Comma-delimited CSV with the supplied header.  Pass either a
         *  single comma-separated string ({@code "cost,latency,throughput"})
         *  or pre-split column names. */
        public CsvLineParser(String headerLine) {
            this(splitCsvCells(headerLine, ','), ',');
        }

        /** Full control: explicit headers (or {@code null} for synthetic
         *  {@code col_<i>} keys) and delimiter (typically {@code ','} or
         *  {@code '\t'} for TSV).  Header tokens are lower-cased and trimmed
         *  to match the rest of the analyzer's key-handling. */
        public CsvLineParser(String[] headers, char delimiter) {
            if (headers == null) {
                this.headers = null;
            } else {
                this.headers = new String[headers.length];
                for (int i = 0; i < headers.length; i++) {
                    String h = headers[i] == null ? "" : headers[i].trim().toLowerCase(Locale.ROOT);
                    this.headers[i] = h.isEmpty() ? ("col_" + i) : h;
                }
            }
            this.delimiter = delimiter;
        }

        @Override public Map<String, String> parse(String text) {
            Map<String, String> kv = new LinkedHashMap<>();
            if (text == null || text.isEmpty()) return kv;
            String s = text;
            // Skip CR before LF (input is per-line, but be lenient).
            if (s.endsWith("\r")) s = s.substring(0, s.length() - 1);
            // Cheap rejection: pure K=V / JSON lines have no delimiter — skip
            // so MultiParser can chain past us cleanly.
            if (s.indexOf(delimiter) < 0 && (headers == null || headers.length <= 1)) {
                return kv;
            }
            String[] cells = splitCsvCells(s, delimiter);
            for (int i = 0; i < cells.length; i++) {
                String key = (headers != null && i < headers.length)
                        ? headers[i]
                        : "col_" + i;
                String v = cells[i] == null ? "" : cells[i].trim();
                if (v.isEmpty()) continue;
                kv.put(key, v);
            }
            return kv;
        }

        /** RFC-4180-lite cell split: handles double-quoted cells with
         *  embedded delimiters and {@code ""} as a literal quote.  Public for
         *  the header overload above; never returns {@code null}. */
        static String[] splitCsvCells(String line, char delim) {
            if (line == null || line.isEmpty()) return new String[0];
            java.util.List<String> out = new java.util.ArrayList<>();
            StringBuilder cur = new StringBuilder();
            boolean inQuotes = false;
            for (int i = 0; i < line.length(); i++) {
                char c = line.charAt(i);
                if (inQuotes) {
                    if (c == '"') {
                        if (i + 1 < line.length() && line.charAt(i + 1) == '"') {
                            cur.append('"');
                            i++;
                        } else {
                            inQuotes = false;
                        }
                    } else {
                        cur.append(c);
                    }
                } else {
                    if (c == '"' && cur.length() == 0) {
                        inQuotes = true;
                    } else if (c == delim) {
                        out.add(cur.toString());
                        cur.setLength(0);
                    } else {
                        cur.append(c);
                    }
                }
            }
            out.add(cur.toString());
            return out.toArray(new String[0]);
        }
    }

    /** Composite: try parsers in order; first non-empty result wins.
     *  Use to support corpora where some rows are JSON and others are K=V. */
    final class MultiParser implements LineParser {
        private final LineParser[] parsers;
        public MultiParser(LineParser... parsers) { this.parsers = parsers; }
        @Override public Map<String, String> parse(String text) {
            for (LineParser p : parsers) {
                Map<String, String> r = p.parse(text);
                if (!r.isEmpty()) return r;
            }
            return Map.of();
        }
    }
}
