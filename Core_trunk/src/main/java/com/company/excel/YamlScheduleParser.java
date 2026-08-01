package com.company.excel;

import com.company.config.AppConfig;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Tier-4 win 4.4 (Phase 2) — YAML-driven schedule parser.
 *
 * Mirror of {@link JsonScheduleParser} for the YAML format.  The supported
 * subset is intentionally narrow so the parser stays offline-friendly (no
 * snakeyaml / jackson-dataformat-yaml dependency needed) and the conversion
 * to the canonical {@link ParsedWorkbook} is single-sourced:
 *
 *   YAML text  →  JSON string  →  {@link JsonScheduleParser#parseJson}
 *
 * Supported subset:
 *   • Top-level {@code sheets:} block mapping.
 *   • Each sheet: a block sequence ({@code - ...} prefix) whose items are
 *     <b>flow-style arrays</b> ({@code ["a", "b", "c"]}) — these are
 *     literally JSON-compatible, so each row is forwarded byte-for-byte
 *     into the assembled JSON.
 *   • Full-line comments ({@code # ...} as the first non-whitespace token).
 *   • Two-space indentation (any consistent indent works; we count leading
 *     spaces).  Tabs are not supported (mirrors the YAML 1.2 rule against
 *     tabs in indentation).
 *
 * Not supported (use JSON or the {@link ProgrammaticScheduleBuilder} instead):
 *   • Trailing comments after a value.
 *   • Anchors / aliases / merge keys ({@code &}, {@code *}, {@code <<:}).
 *   • Block scalars ({@code |}, {@code >}).
 *   • Multi-document files ({@code ---}).
 *   • Block sequences of block mappings (only flow arrays for rows).
 *
 * Example — same as {@code test_e2e_metric.json}, expressed as YAML:
 *
 * <pre>{@code
 * sheets:
 *   FW_Seq:
 *     - ["HEAD", "FW_Exclude", "FW_Reuse", "FW_Combi(1)", "FW_Combi(1)"]
 *     - ["COST", "FW_Exclude", "FW_Reuse", "FW_Combi(1)", "FW_Combi(1)"]
 *     - ["ROW", null, null, "FW_(HEAD,,COST,,LAT,,TAIL,,M:N)"]
 *   COST:
 *     - [" id=1 cost=0.10"]
 *     - [" id=2 cost=0.30"]
 *   ROW:
 *     - ["FW_EMPTY_STRING"]
 * }</pre>
 *
 * On unsupported syntax the parser raises {@link IllegalArgumentException} with
 * the line number — easier to fix than a silent miss-parse.
 */
public final class YamlScheduleParser implements ScheduleParser {

    private static final Pattern SHEET_NAME_LINE  = Pattern.compile("^(\\s+)([A-Za-z_][A-Za-z0-9_]*)\\s*:\\s*$");
    private static final Pattern SHEET_ROW_LINE   = Pattern.compile("^(\\s+)-\\s*(.+)$");
    private static final Pattern TOP_LEVEL_LINE   = Pattern.compile("^([A-Za-z_][A-Za-z0-9_]*)\\s*:\\s*$");

    @Override
    public ParsedWorkbook parse(Path source, AppConfig.WorkbookConfig wbCfg) throws Exception {
        String text = new String(Files.readAllBytes(source), StandardCharsets.UTF_8);
        return parseYaml(text, wbCfg, "yaml:" + source.getFileName().toString());
    }

    /** Parse from a YAML string directly — useful for programmatic /
     *  embedded-config callers and for tests. */
    public ParsedWorkbook parseYaml(String yaml, AppConfig.WorkbookConfig wbCfg,
                                     String displayName) throws Exception {
        String jsonString = yamlToJson(yaml);
        return new JsonScheduleParser().parseJson(jsonString, wbCfg, displayName);
    }

    /** Render the YAML schedule subset to a canonical JSON string with the
     *  same shape {@link JsonScheduleParser} consumes.  Exposed for testing
     *  the conversion in isolation. */
    public String yamlToJson(String yaml) {
        Map<String, List<String>> sheetRowsAsJson = parseToRowJsonByName(yaml);

        StringBuilder sb = new StringBuilder();
        sb.append("{\"sheets\":{");
        boolean firstSheet = true;
        for (Map.Entry<String, List<String>> e : sheetRowsAsJson.entrySet()) {
            if (!firstSheet) sb.append(',');
            firstSheet = false;
            sb.append(jsonQuote(e.getKey())).append(":[");
            boolean firstRow = true;
            for (String rowJson : e.getValue()) {
                if (!firstRow) sb.append(',');
                firstRow = false;
                sb.append(rowJson);
            }
            sb.append(']');
        }
        sb.append("}}");
        return sb.toString();
    }

    // ─── parsing ────────────────────────────────────────────────────────

    private Map<String, List<String>> parseToRowJsonByName(String yaml) {
        Map<String, List<String>> out = new LinkedHashMap<>();
        String[] lines = yaml.split("\\R", -1);

        boolean inSheetsBlock = false;
        int sheetsIndent  = -1;            // indent col of `sheets:` itself (always 0 here)
        int sheetIndent   = -1;            // indent col of a `<name>:` under sheets
        String currentSheet = null;

        for (int i = 0; i < lines.length; i++) {
            String raw = lines[i];
            // Full-line comments and blanks: skip.
            String trimmed = raw.strip();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) continue;

            int indent = leadingSpaces(raw);

            // Look for top-level `sheets:` line.
            if (!inSheetsBlock) {
                Matcher topm = TOP_LEVEL_LINE.matcher(raw);
                if (topm.matches() && "sheets".equals(topm.group(1)) && indent == 0) {
                    inSheetsBlock = true;
                    sheetsIndent = 0;
                    continue;
                }
                if (indent == 0) {
                    // Unrecognised top-level key — strict parser.
                    throw new IllegalArgumentException(
                            "YAML schedule subset expects top-level 'sheets:' first; got line "
                                    + (i + 1) + ": " + raw);
                }
                continue;
            }

            // Dedent back to top → end of sheets block.
            if (indent <= sheetsIndent) {
                Matcher topm = TOP_LEVEL_LINE.matcher(raw);
                if (topm.matches()) {
                    // Another top-level key encountered (e.g. _comment).  Ignore.
                    inSheetsBlock = false;
                    continue;
                }
                throw new IllegalArgumentException(
                        "YAML schedule subset: unexpected dedent at line " + (i + 1) + ": " + raw);
            }

            // New sheet name?
            Matcher mName = SHEET_NAME_LINE.matcher(raw);
            if (mName.matches()) {
                if (sheetIndent < 0) sheetIndent = mName.group(1).length();
                // Allow same-level peers; deeper nesting is an error here.
                if (indent != sheetIndent) {
                    throw new IllegalArgumentException(
                            "YAML schedule subset: sheet name indent inconsistent at line "
                                    + (i + 1) + " (expected " + sheetIndent + ", got " + indent + ")");
                }
                currentSheet = mName.group(2);
                out.computeIfAbsent(currentSheet, k -> new ArrayList<>());
                continue;
            }

            // Row line?
            Matcher mRow = SHEET_ROW_LINE.matcher(raw);
            if (mRow.matches()) {
                if (currentSheet == null) {
                    throw new IllegalArgumentException(
                            "YAML schedule subset: row '- ...' before any sheet name at line "
                                    + (i + 1));
                }
                if (indent <= sheetIndent) {
                    throw new IllegalArgumentException(
                            "YAML schedule subset: row indent must exceed sheet-name indent at line "
                                    + (i + 1));
                }
                String rowContent = mRow.group(2).trim();
                // Rows MUST be flow-style arrays so we can forward them as JSON.
                if (!rowContent.startsWith("[")) {
                    throw new IllegalArgumentException(
                            "YAML schedule subset requires rows to be flow-style arrays "
                                    + "(e.g. '- [\"a\", \"b\"]') at line " + (i + 1) + ": " + rowContent);
                }
                out.get(currentSheet).add(rowContent);
                continue;
            }

            throw new IllegalArgumentException(
                    "YAML schedule subset: unrecognised syntax at line " + (i + 1) + ": " + raw);
        }
        return out;
    }

    private static int leadingSpaces(String s) {
        int n = 0;
        while (n < s.length() && s.charAt(n) == ' ') n++;
        return n;
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
