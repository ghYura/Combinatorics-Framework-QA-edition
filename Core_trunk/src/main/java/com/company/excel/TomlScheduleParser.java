package com.company.excel;

import com.company.config.AppConfig;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Tier-4 win 4.4 (Phase 2) — TOML-driven schedule parser.
 *
 * Mirror of {@link JsonScheduleParser} for the TOML format.  Same single-source
 * design as {@link YamlScheduleParser}:
 *
 *   TOML text  →  JSON string  →  {@link JsonScheduleParser#parseJson}
 *
 * Supported subset:
 *   • A single {@code [sheets]} table.
 *   • Each key under it is an array-of-arrays:
 *     {@code FW_Seq = [["HEAD", "FW_Exclude", ...], ["COST", ...]]}.
 *   • Values may span multiple lines; trailing commas before {@code ]} are
 *     allowed (TOML convention) and stripped before JSON forwarding.
 *   • Line comments ({@code # ...}) inside or outside arrays.
 *   • {@code null} is accepted as a value token even though TOML proper lacks
 *     a null literal — pragmatic extension matching the schedule's JSON
 *     equivalent ({@code ["ROW", null, null, ...]}).
 *
 * Not supported (use JSON / YAML / programmatic):
 *   • Multiple tables (only one {@code [sheets]}).
 *   • Literal strings ({@code '...'}); use basic strings ({@code "..."}).
 *   • Multi-line basic strings ({@code """..."""}).
 *   • Inline tables ({@code {key=val}}).
 *   • TOML-only scalars (datetimes, hex/oct/bin ints).
 *
 * Example — same scenario as {@code test_e2e_metric.json}:
 *
 * <pre>{@code
 * [sheets]
 * FW_Seq = [
 *   ["HEAD", "FW_Exclude", "FW_Reuse", "FW_Combi(1)", "FW_Combi(1)"],
 *   ["ROW",  null, null, "FW_(HEAD,,COST,,LAT,,TAIL,,M:N)"],
 * ]
 * HEAD = [["scenario=demo"]]
 * COST = [
 *   [" id=1 cost=0.10"],
 *   [" id=2 cost=0.30"],
 * ]
 * }</pre>
 */
public final class TomlScheduleParser implements ScheduleParser {

    @Override
    public ParsedWorkbook parse(Path source, AppConfig.WorkbookConfig wbCfg) throws Exception {
        String text = new String(Files.readAllBytes(source), StandardCharsets.UTF_8);
        return parseToml(text, wbCfg, "toml:" + source.getFileName().toString());
    }

    /** Parse from a TOML string directly. */
    public ParsedWorkbook parseToml(String toml, AppConfig.WorkbookConfig wbCfg,
                                     String displayName) throws Exception {
        return new JsonScheduleParser().parseJson(tomlToJson(toml), wbCfg, displayName);
    }

    /** Render the TOML schedule subset to a canonical JSON string with the
     *  same shape {@link JsonScheduleParser} consumes.  Exposed for testing. */
    public String tomlToJson(String toml) {
        // Find the [sheets] table header — must be the only table in this subset.
        int headerStart = findTableHeader(toml, "sheets");
        if (headerStart < 0)
            throw new IllegalArgumentException("TOML schedule subset requires a '[sheets]' table");
        int pos = lineEnd(toml, headerStart) + 1;

        StringBuilder json = new StringBuilder("{\"sheets\":{");
        boolean firstKey = true;

        while (pos < toml.length()) {
            int t = skipWhitespaceAndComments(toml, pos);
            if (t >= toml.length()) break;
            // Another table header → end of [sheets] block.
            if (toml.charAt(t) == '[' && !isArrayStart(toml, t)) break;

            // Parse `key = value`.
            int keyStart = t;
            int keyEnd = keyStart;
            while (keyEnd < toml.length() && isBareKeyChar(toml.charAt(keyEnd))) keyEnd++;
            if (keyEnd == keyStart)
                throw new IllegalArgumentException(
                        "TOML schedule subset: expected bare key near offset " + keyStart);
            String key = toml.substring(keyStart, keyEnd);

            int eq = skipSpacesAndTabs(toml, keyEnd);
            if (eq >= toml.length() || toml.charAt(eq) != '=')
                throw new IllegalArgumentException(
                        "TOML schedule subset: expected '=' after key '" + key + "' near offset " + eq);
            int valueStart = skipSpacesAndTabs(toml, eq + 1);
            // Permit a line break + indent before the opening bracket.
            valueStart = skipWhitespaceAndComments(toml, valueStart);
            if (valueStart >= toml.length() || toml.charAt(valueStart) != '[')
                throw new IllegalArgumentException(
                        "TOML schedule subset: value for '" + key + "' must be an array; got "
                                + (valueStart < toml.length() ? toml.charAt(valueStart) : "<EOF>"));
            int valueEnd = findMatchingBracket(toml, valueStart);
            String rawArray = toml.substring(valueStart, valueEnd + 1);
            String jsonArray = cleanToJsonArray(rawArray);

            if (!firstKey) json.append(',');
            firstKey = false;
            json.append(jsonQuote(key)).append(':').append(jsonArray);

            pos = valueEnd + 1;
        }
        json.append("}}");
        return json.toString();
    }

    // ─── scanning helpers ────────────────────────────────────────────────

    /** Locate "[name]" at the start of a line (possibly after whitespace).
     *  Returns index of the '[' or -1 if not found. */
    private static int findTableHeader(String s, String name) {
        String target = "[" + name + "]";
        // Walk line-by-line.
        int pos = 0;
        while (pos < s.length()) {
            int lineStart = pos;
            int lineEnd = lineEnd(s, lineStart);
            // Strip leading whitespace + trailing whitespace, then strip
            // trailing inline comment ' # ...'.
            int trimL = lineStart;
            while (trimL < lineEnd && (s.charAt(trimL) == ' ' || s.charAt(trimL) == '\t')) trimL++;
            int trimR = lineEnd;
            // Strip comment.
            for (int i = trimL; i < lineEnd; i++) {
                if (s.charAt(i) == '#') { trimR = i; break; }
                if (s.charAt(i) == '"') {
                    // skip until matching " (no escapes traversal needed for header detection)
                    int j = i + 1;
                    while (j < lineEnd && s.charAt(j) != '"') {
                        if (s.charAt(j) == '\\') j++;
                        j++;
                    }
                    i = j;
                }
            }
            while (trimR > trimL && (s.charAt(trimR - 1) == ' ' || s.charAt(trimR - 1) == '\t')) trimR--;
            String ln = s.substring(trimL, trimR);
            if (ln.equals(target)) return trimL;
            pos = lineEnd + 1;
        }
        return -1;
    }

    private static int lineEnd(String s, int from) {
        int i = from;
        while (i < s.length() && s.charAt(i) != '\n') i++;
        return i;
    }

    private static int skipSpacesAndTabs(String s, int from) {
        int i = from;
        while (i < s.length() && (s.charAt(i) == ' ' || s.charAt(i) == '\t')) i++;
        return i;
    }

    /** Skip whitespace (incl. newlines) and full-line / trailing comments. */
    private static int skipWhitespaceAndComments(String s, int from) {
        int i = from;
        while (i < s.length()) {
            char c = s.charAt(i);
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') { i++; continue; }
            if (c == '#') {
                while (i < s.length() && s.charAt(i) != '\n') i++;
                continue;
            }
            break;
        }
        return i;
    }

    private static boolean isBareKeyChar(char c) {
        return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9') || c == '_' || c == '-';
    }

    private static boolean isArrayStart(String s, int pos) {
        // '[' at this offset begins an inline array, not a table header,
        // when it's part of a value expression — but here we only call this
        // after consuming whitespace at top-of-[sheets]-body level, so '['
        // at line start means a NEW table header.  We never re-enter at
        // value-start, so this is conservative: always false.
        return false;
    }

    /**
     * Starting at index of '[', scan forward tracking depth + in-string state +
     * comments; return index of matching ']' at depth 0.
     */
    private static int findMatchingBracket(String s, int openIdx) {
        if (s.charAt(openIdx) != '[')
            throw new IllegalStateException("findMatchingBracket: not at '['");
        int depth = 0;
        int i = openIdx;
        while (i < s.length()) {
            char c = s.charAt(i);
            if (c == '"') {
                // Skip basic string.  Honour \" and \\.
                int j = i + 1;
                while (j < s.length() && s.charAt(j) != '"') {
                    if (s.charAt(j) == '\\' && j + 1 < s.length()) j++;
                    j++;
                }
                i = (j < s.length() ? j : s.length() - 1) + 1;
                continue;
            }
            if (c == '#') {
                while (i < s.length() && s.charAt(i) != '\n') i++;
                continue;
            }
            if (c == '[') depth++;
            else if (c == ']') {
                depth--;
                if (depth == 0) return i;
            }
            i++;
        }
        throw new IllegalArgumentException("TOML schedule subset: unbalanced '['");
    }

    /**
     * Take a TOML array literal {@code [ ... ]} (already validated to balance)
     * and return JSON-compatible text:
     *   • strip line comments
     *   • strip trailing commas before {@code ]} (also before {@code }} for safety)
     *   • preserve {@code null} bare tokens (used as a pragmatic extension)
     */
    private static String cleanToJsonArray(String raw) {
        StringBuilder out = new StringBuilder(raw.length());
        int i = 0;
        while (i < raw.length()) {
            char c = raw.charAt(i);
            if (c == '"') {
                int j = i;
                out.append(c);
                j++;
                while (j < raw.length() && raw.charAt(j) != '"') {
                    if (raw.charAt(j) == '\\' && j + 1 < raw.length()) {
                        out.append(raw.charAt(j));
                        j++;
                    }
                    out.append(raw.charAt(j));
                    j++;
                }
                if (j < raw.length()) {
                    out.append(raw.charAt(j));     // closing quote
                    i = j + 1;
                } else { i = j; }
                continue;
            }
            if (c == '#') {
                while (i < raw.length() && raw.charAt(i) != '\n') i++;
                continue;
            }
            out.append(c);
            i++;
        }
        String s = out.toString();
        // Strip trailing commas before ']' (and ',\\s*\\n\\s*]' too).
        s = s.replaceAll(",(\\s*\\])", "$1");
        return s;
    }

    private static String jsonQuote(String s) {
        StringBuilder sb = new StringBuilder(s.length() + 2);
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n");  break;
                case '\r': sb.append("\\r");  break;
                case '\t': sb.append("\\t");  break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else          sb.append(c);
            }
        }
        sb.append('"');
        return sb.toString();
    }
}
