package com.company;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Parser/model for the Reader -> Executor ``bundle.handoff/v2`` manifest (STEP 19;
 *  schema: generator_trunk/bundle-handoff-v2.schema.json, Python model: bundle.handoff.HandoffV2,
 *  Reader writer: HandoffManifestWriter, Python reader: Executor_trunk/py_executor.read_manifest).
 *
 *  Hand-rolled JSON decoder on purpose -- Executor_trunk carries no JSON library
 *  (Jackson/Gson) and the plan forbids adding one when plain JDK suffices (mirrors
 *  HandoffManifestWriter's hand-rolled encoder on the Reader side).
 *
 *  Kept deliberately read-only and side-effect-free: loading a manifest never touches
 *  the filesystem beyond the manifest file itself, so MainWatch decides what to do with
 *  the parsed fields (legacy directories remain the actual data source -- STEP 17's
 *  dual-write means they arrive alongside the manifest; this model exists to validate
 *  the contract and expose its fields for cross-checks and the executor summary). */
public final class HandoffManifestV2 {
    public static final String EXPECTED_PROTOCOL = "bundle.handoff/v2";

    /** Raised on any structurally-invalid manifest: bad/missing protocol, wrong major
     *  version, missing required field, wrong type, empty source list, ... Callers must
     *  fail closed on this (acceptance: "Invalid major protocol fail closed"). */
    public static final class ManifestError extends RuntimeException {
        public ManifestError(String message) { super(message); }
    }

    public static final class CustomVerdict {
        public final int code;
        public final String message;
        CustomVerdict(int code, String message) { this.code = code; this.message = message; }
    }

    public static final class ResultTarget {
        public final String host;
        public final int port;
        public final String database;
        public final String user; // nullable
        ResultTarget(String host, int port, String database, String user) {
            this.host = host; this.port = port; this.database = database; this.user = user;
        }
    }

    public static final class SourceLocation {
        public final String kind;
        public final String path;
        public final String sha256; // nullable
        SourceLocation(String kind, String path, String sha256) {
            this.kind = kind; this.path = path; this.sha256 = sha256;
        }
    }

    public final String protocol;
    public final String runId;
    public final String language;
    public final String candidateTransport;
    public final long candidateCount;
    public final String idFormat;
    public final List<SourceLocation> sources;
    public final ResultTarget resultTarget;
    public final String resultSchemaMode;
    public final String verdictMode;
    public final List<CustomVerdict> customVerdicts;
    public final List<String> arguments;
    public final int shift;
    public final String preprocess; // nullable
    public final String executionPolicyRef; // nullable

    private HandoffManifestV2(String protocol, String runId, String language, String candidateTransport,
            long candidateCount, String idFormat, List<SourceLocation> sources, ResultTarget resultTarget,
            String resultSchemaMode, String verdictMode, List<CustomVerdict> customVerdicts,
            List<String> arguments, int shift, String preprocess, String executionPolicyRef) {
        this.protocol = protocol;
        this.runId = runId;
        this.language = language;
        this.candidateTransport = candidateTransport;
        this.candidateCount = candidateCount;
        this.idFormat = idFormat;
        this.sources = sources;
        this.resultTarget = resultTarget;
        this.resultSchemaMode = resultSchemaMode;
        this.verdictMode = verdictMode;
        this.customVerdicts = customVerdicts;
        this.arguments = arguments;
        this.shift = shift;
        this.preprocess = preprocess;
        this.executionPolicyRef = executionPolicyRef;
    }

    /** Reads + parses + validates a manifest file. Never returns a manifest whose
     *  protocol name/major version mismatches {@link #EXPECTED_PROTOCOL}, nor one
     *  missing a field the schema marks ``required`` -- both raise {@link ManifestError}
     *  so the caller can fail closed (P-19: "Invalid major protocol fail closed"). */
    public static HandoffManifestV2 load(Path manifestPath) {
        String text;
        try {
            text = Files.readString(manifestPath, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new ManifestError("cannot read manifest " + manifestPath + ": " + e.getMessage());
        }

        Object parsed;
        try {
            parsed = new JsonReader(text).readDocument();
        } catch (RuntimeException e) {
            throw new ManifestError("cannot parse manifest " + manifestPath + " as JSON: " + e.getMessage());
        }
        if (!(parsed instanceof Map)) {
            throw new ManifestError("manifest " + manifestPath + " is not a JSON object");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> root = (Map<String, Object>) parsed;

        String protocol = requireString(root, "protocol");
        requireMatchingProtocol(protocol);

        String runId = requireString(root, "run_id");
        if (runId.isBlank()) throw new ManifestError("manifest run_id is empty");

        String language = requireString(root, "language");
        if (!language.equals("python") && !language.equals("java")) {
            throw new ManifestError("manifest language " + quote(language) + " is not \"python\"/\"java\"");
        }

        String candidateTransport = requireString(root, "candidate_transport");
        if (!candidateTransport.equals("loose-files") && !candidateTransport.equals("sharded")
                && !candidateTransport.equals("grpc")) {
            throw new ManifestError("manifest candidate_transport " + quote(candidateTransport)
                    + " is not \"loose-files\"/\"sharded\"/\"grpc\"");
        }

        long candidateCount = requireLong(root, "candidate_count");
        if (candidateCount < 0) throw new ManifestError("manifest candidate_count must be >= 0, got " + candidateCount);

        String idFormat = requireString(root, "id_format");
        if (idFormat.isBlank()) throw new ManifestError("manifest id_format must not be empty");

        List<SourceLocation> sources = readSources(root);
        if (sources.isEmpty()) throw new ManifestError("manifest must declare at least one source location");

        ResultTarget resultTarget = readResultTarget(root);
        String resultSchemaMode = requireString(root, "result_schema_mode");
        String verdictMode = requireString(root, "verdict_mode");
        if (!verdictMode.equals("FW_VAR") && !verdictMode.equals("FW_CUSTOM_VAR")) {
            throw new ManifestError("manifest verdict_mode " + quote(verdictMode) + " is not FW_VAR/FW_CUSTOM_VAR");
        }

        List<CustomVerdict> customVerdicts = readCustomVerdicts(root);
        if (verdictMode.equals("FW_CUSTOM_VAR") && customVerdicts.isEmpty()) {
            throw new ManifestError("manifest verdict_mode=FW_CUSTOM_VAR requires a non-empty custom_verdicts list");
        }

        List<String> arguments = readStringArray(root.get("arguments"));
        int shift = root.containsKey("shift") ? (int) requireLong(root, "shift") : 1;
        String preprocess = optionalString(root.get("preprocess"));
        String executionPolicyRef = optionalString(root.get("execution_policy_ref"));

        return new HandoffManifestV2(protocol, runId, language, candidateTransport, candidateCount, idFormat,
                sources, resultTarget, resultSchemaMode, verdictMode, customVerdicts, arguments, shift,
                preprocess, executionPolicyRef);
    }

    /** STEP 27: parse a small JSON object file (e.g. execution_policy.json, which
     *  the launcher writes next to the manifest) with the same hand-rolled decoder.
     *  Returns the root map, or {@code null} if the file is absent/unreadable or not
     *  a JSON object -- callers treat a missing policy sidecar as "no policy
     *  recorded" (SQL NULLs in results_v2), never a hard failure. */
    public static Map<String, Object> readJsonObject(Path path) {
        try {
            Object parsed = new JsonReader(Files.readString(path, StandardCharsets.UTF_8)).readDocument();
            if (parsed instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> map = (Map<String, Object>) parsed;
                return map;
            }
        } catch (IOException | RuntimeException ignored) {
            // absent / unreadable / malformed -> treat as "no policy sidecar"
        }
        return null;
    }

    /** ``"<name>/v<major>"`` -- readers reject any value whose name or major differs
     *  (schema description), not just an exact mismatch, so a future v3 manifest fails
     *  closed here instead of being silently misread as v2. */
    private static void requireMatchingProtocol(String protocol) {
        int slash = protocol.lastIndexOf('/');
        if (slash < 0 || !protocol.substring(0, slash).equals("bundle.handoff")
                || !protocol.substring(slash + 1).startsWith("v")) {
            throw new ManifestError("manifest protocol " + quote(protocol) + " is not a bundle.handoff/vN identifier");
        }
        if (!protocol.equals(EXPECTED_PROTOCOL)) {
            throw new ManifestError("manifest protocol " + quote(protocol)
                    + " != expected " + quote(EXPECTED_PROTOCOL) + " (major version mismatch)");
        }
    }

    private static List<SourceLocation> readSources(Map<String, Object> root) {
        Object raw = root.get("sources");
        if (!(raw instanceof List)) throw new ManifestError("manifest \"sources\" must be an array");
        List<SourceLocation> out = new ArrayList<>();
        for (Object item : (List<?>) raw) {
            if (!(item instanceof Map)) throw new ManifestError("manifest source entry must be an object");
            @SuppressWarnings("unchecked")
            Map<String, Object> m = (Map<String, Object>) item;
            String kind = requireString(m, "kind");
            String path = requireString(m, "path");
            if (path.isBlank()) throw new ManifestError("manifest source has an empty path (kind=" + quote(kind) + ")");
            out.add(new SourceLocation(kind, path, optionalString(m.get("sha256"))));
        }
        return Collections.unmodifiableList(out);
    }

    private static ResultTarget readResultTarget(Map<String, Object> root) {
        Object raw = root.get("result_target");
        if (!(raw instanceof Map)) throw new ManifestError("manifest \"result_target\" must be an object");
        @SuppressWarnings("unchecked")
        Map<String, Object> m = (Map<String, Object>) raw;
        String host = requireString(m, "host");
        if (host.isBlank()) throw new ManifestError("manifest result_target.host must not be empty");
        long port = requireLong(m, "port");
        if (port < 1 || port > 65535) throw new ManifestError("manifest result_target.port out of range: " + port);
        String database = requireString(m, "database");
        if (database.isBlank()) throw new ManifestError("manifest result_target.database must not be empty");
        return new ResultTarget(host, (int) port, database, optionalString(m.get("user")));
    }

    private static List<CustomVerdict> readCustomVerdicts(Map<String, Object> root) {
        Object raw = root.get("custom_verdicts");
        if (raw == null) return Collections.emptyList();
        if (!(raw instanceof List)) throw new ManifestError("manifest \"custom_verdicts\" must be an array");
        List<CustomVerdict> out = new ArrayList<>();
        for (Object item : (List<?>) raw) {
            if (!(item instanceof Map)) throw new ManifestError("manifest custom_verdicts entry must be an object");
            @SuppressWarnings("unchecked")
            Map<String, Object> m = (Map<String, Object>) item;
            out.add(new CustomVerdict((int) requireLong(m, "code"), requireString(m, "message")));
        }
        return Collections.unmodifiableList(out);
    }

    private static List<String> readStringArray(Object raw) {
        if (raw == null) return Collections.emptyList();
        if (!(raw instanceof List)) throw new ManifestError("expected a JSON array of strings");
        List<String> out = new ArrayList<>();
        for (Object item : (List<?>) raw) {
            if (!(item instanceof String)) throw new ManifestError("expected a JSON array of strings");
            out.add((String) item);
        }
        return Collections.unmodifiableList(out);
    }

    private static String requireString(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (!(v instanceof String)) throw new ManifestError("manifest field " + quote(key) + " must be a non-null string");
        return (String) v;
    }

    private static long requireLong(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (!(v instanceof Number)) throw new ManifestError("manifest field " + quote(key) + " must be a number");
        return ((Number) v).longValue();
    }

    private static String optionalString(Object v) {
        if (v == null) return null;
        if (!(v instanceof String)) throw new ManifestError("expected a string or null");
        return (String) v;
    }

    private static String quote(String s) {
        return "\"" + (s == null ? "" : s) + "\"";
    }

    // ------------------------------- minimal JSON decoder ------------------------------ //
    // Covers exactly the value shapes the schema allows (objects, arrays, strings, numbers,
    // booleans, null) -- nothing more. Mirrors the "no JSON library" constraint that already
    // shaped HandoffManifestWriter's hand-rolled encoder on the Reader side.
    private static final class JsonReader {
        private final String src;
        private int pos;

        JsonReader(String src) { this.src = src; this.pos = 0; }

        Object readDocument() {
            Object value = readValue();
            skipWhitespace();
            if (pos != src.length()) throw new IllegalArgumentException("trailing content at offset " + pos);
            return value;
        }

        private Object readValue() {
            skipWhitespace();
            if (pos >= src.length()) throw new IllegalArgumentException("unexpected end of input");
            char c = src.charAt(pos);
            switch (c) {
                case '{': return readObject();
                case '[': return readArray();
                case '"': return readString();
                case 't': return readLiteral("true", Boolean.TRUE);
                case 'f': return readLiteral("false", Boolean.FALSE);
                case 'n': return readLiteral("null", null);
                default: return readNumber();
            }
        }

        private Map<String, Object> readObject() {
            expect('{');
            Map<String, Object> out = new LinkedHashMap<>();
            skipWhitespace();
            if (peek() == '}') { pos++; return out; }
            while (true) {
                skipWhitespace();
                if (peek() != '"') throw new IllegalArgumentException("expected object key at offset " + pos);
                String key = readString();
                skipWhitespace();
                expect(':');
                out.put(key, readValue());
                skipWhitespace();
                char c = next();
                if (c == ',') continue;
                if (c == '}') break;
                throw new IllegalArgumentException("expected ',' or '}' at offset " + (pos - 1));
            }
            return out;
        }

        private List<Object> readArray() {
            expect('[');
            List<Object> out = new ArrayList<>();
            skipWhitespace();
            if (peek() == ']') { pos++; return out; }
            while (true) {
                out.add(readValue());
                skipWhitespace();
                char c = next();
                if (c == ',') continue;
                if (c == ']') break;
                throw new IllegalArgumentException("expected ',' or ']' at offset " + (pos - 1));
            }
            return out;
        }

        private String readString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (true) {
                if (pos >= src.length()) throw new IllegalArgumentException("unterminated string");
                char c = src.charAt(pos++);
                if (c == '"') break;
                if (c == '\\') {
                    if (pos >= src.length()) throw new IllegalArgumentException("unterminated escape");
                    char esc = src.charAt(pos++);
                    switch (esc) {
                        case '"': sb.append('"'); break;
                        case '\\': sb.append('\\'); break;
                        case '/': sb.append('/'); break;
                        case 'b': sb.append('\b'); break;
                        case 'f': sb.append('\f'); break;
                        case 'n': sb.append('\n'); break;
                        case 'r': sb.append('\r'); break;
                        case 't': sb.append('\t'); break;
                        case 'u':
                            if (pos + 4 > src.length()) throw new IllegalArgumentException("truncated \\u escape");
                            sb.append((char) Integer.parseInt(src.substring(pos, pos + 4), 16));
                            pos += 4;
                            break;
                        default: throw new IllegalArgumentException("invalid escape \\" + esc);
                    }
                } else {
                    sb.append(c);
                }
            }
            return sb.toString();
        }

        private Object readNumber() {
            int start = pos;
            if (peek() == '-') pos++;
            while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            boolean isDouble = false;
            if (pos < src.length() && src.charAt(pos) == '.') {
                isDouble = true;
                pos++;
                while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            }
            if (pos < src.length() && (src.charAt(pos) == 'e' || src.charAt(pos) == 'E')) {
                isDouble = true;
                pos++;
                if (pos < src.length() && (src.charAt(pos) == '+' || src.charAt(pos) == '-')) pos++;
                while (pos < src.length() && Character.isDigit(src.charAt(pos))) pos++;
            }
            String token = src.substring(start, pos);
            if (token.isEmpty() || token.equals("-")) throw new IllegalArgumentException("invalid number at offset " + start);
            return isDouble ? (Object) Double.parseDouble(token) : (Object) Long.parseLong(token);
        }

        private Object readLiteral(String literal, Object value) {
            if (pos + literal.length() > src.length() || !src.regionMatches(pos, literal, 0, literal.length())) {
                throw new IllegalArgumentException("invalid literal at offset " + pos);
            }
            pos += literal.length();
            return value;
        }

        private void skipWhitespace() {
            while (pos < src.length() && Character.isWhitespace(src.charAt(pos))) pos++;
        }

        private char peek() {
            if (pos >= src.length()) throw new IllegalArgumentException("unexpected end of input");
            return src.charAt(pos);
        }

        private char next() {
            if (pos >= src.length()) throw new IllegalArgumentException("unexpected end of input");
            return src.charAt(pos++);
        }

        private void expect(char c) {
            if (next() != c) throw new IllegalArgumentException("expected '" + c + "' at offset " + (pos - 1));
        }
    }
}
