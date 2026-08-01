package com.company.excel;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

/**
 * Symmetric writer to {@link JsonScheduleParser}.  Walks a
 * {@link ParsedWorkbook} (the canonical model the entire Core pipeline runs
 * against, regardless of whether the input was XLSX / JSON / YAML / TOML /
 * Programmatic) and emits a JSON document with the exact schema
 * {@link JsonScheduleParser} reads:
 *
 * <pre>
 * {
 *   "sheets": {
 *     "FW_Seq":            [["HEAD", "FW_Exclude", "FW_Reuse", ...], ...],
 *     "FW_SheetNames":     [[...], ...],
 *     "FW_RunMeFirstOnce": [["class RunMeFirstOnce { ... }"]],
 *     "FW_Arguments":      [["noargs"]],
 *     "FW_CUSTOM_VAR":     [[2, "FWCUSTOMVAR=2 nominal"]],
 *     "HEAD":              [["scenario=demo"]],
 *     "COST":              [[" id=1 cost=0.10"], ...],
 *     "LAT":               [[" latency=10ms"], ...],
 *     "TAIL":              [[" status=ok"]],
 *     "ROW":               [["FW_EMPTY_STRING"]]
 *   }
 * }
 * </pre>
 *
 * <p><strong>Tier-3.5 use-case.</strong> Each Master-mode iteration is a fresh
 * Core JVM (XLSX/JSON → fw_* → Reader → Analyzer → exit).  XLSX is a binary
 * format inconvenient to mutate programmatically between iterations; JSON is
 * not.  With this writer the workflow becomes:</p>
 *
 * <pre>
 *  Iter 0:  input.xlsx → Core (parses) → JsonScheduleWriter dumps
 *                                          workbook_iter0.json beside the
 *                                          legacy pipeline
 *           Core proceeds → fw_* → Reader → Analyzer → bundle_seed.json → exit
 *
 *  Iter N+: external orchestrator (out of scope here) reads
 *           workbook_iter{N}.json + bundle_seed.json, derives
 *           workbook_iter{N+1}.json (e.g. via FW_Seed_* sheet injection),
 *           re-launches Core with core.input.format=json,
 *                                  excel.file=workbook_iter{N+1}.json,
 *                                  core.seed.inputPath=bundle_seed.json
 * </pre>
 *
 * <p>Lossless round-trip with {@link JsonScheduleParser} for the cell content
 * the downstream pipeline cares about (every cell read via POI's
 * {@code DataFormatter}, same convention {@code WorkbookParser} uses).
 * Numeric / boolean cells become string-valued in the JSON because the
 * parser also normalises them to strings — bijection is on the
 * "formatted-string" view of the workbook, which is what the rest of Core
 * sees.</p>
 *
 * <p>Stateless, thread-safe.</p>
 */
public final class JsonScheduleWriter {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private JsonScheduleWriter() {}

    /**
     * Convert a {@link ParsedWorkbook} to the JSON document that
     * {@link JsonScheduleParser#parseJson} would read back to an equivalent
     * workbook.
     *
     * @param wb         the parsed workbook
     * @param prettyPrint {@code true} → 2-space-indented multi-line JSON;
     *                    {@code false} → compact single-line
     * @return the JSON string
     */
    public static String toJson(ParsedWorkbook wb, boolean prettyPrint) throws IOException {
        ObjectNode root = MAPPER.createObjectNode();
        ObjectNode sheets = root.putObject("sheets");
        DataFormatter fmt = new DataFormatter();

        // Iterate ALL sheets in registration order.  Three sources to merge:
        //   • shortStringSheetKey2SheetNameHM — canonical key → name map,
        //     covers both control AND data sheets in original POI order.
        //   • shortSheetHM — keyed POI Sheet objects (covers most sheets).
        //   • stringSheetHM — name-keyed POI Sheet objects (covers control
        //     sheets that may not appear in shortSheetHM for legacy reasons).
        //
        // We walk by key, look up Sheet object from whichever map has it,
        // and fall back to empty array for virtual / content-less sheets.
        java.util.LinkedHashSet<String> emitted = new java.util.LinkedHashSet<>();
        for (Map.Entry<Short, String> e : wb.shortStringSheetKey2SheetNameHM.entrySet()) {
            String name = e.getValue();
            if (name == null || emitted.contains(name)) continue;
            Sheet sheet = wb.shortSheetHM.get(e.getKey());
            if (sheet == null) sheet = wb.stringSheetHM.get(name);
            ArrayNode rows = sheets.putArray(name);
            appendSheetRows(rows, sheet, fmt);
            emitted.add(name);
        }

        // Catch any sheet that's in stringSheetHM but wasn't yet iterated
        // (defensive — keeps the writer lossless even when the parser's
        // key registration is incomplete).
        for (Map.Entry<String, Sheet> e : wb.stringSheetHM.entrySet()) {
            if (emitted.contains(e.getKey())) continue;
            ArrayNode rows = sheets.putArray(e.getKey());
            appendSheetRows(rows, e.getValue(), fmt);
            emitted.add(e.getKey());
        }

        // Virtual sheets — registered via Builder.registerVirtualSheet but
        // not necessarily having POI content — emit as empty arrays so the
        // round-trip preserves the name in sheets-list order.  Only include
        // when not already serialised above.
        for (String vname : wb.virtualSheetNames) {
            if (!emitted.contains(vname)) sheets.putArray(vname);
        }

        return prettyPrint
                ? MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(root)
                : MAPPER.writeValueAsString(root);
    }

    /** Write a {@link ParsedWorkbook} as JSON to the given path
     *  (auto-creates the parent directory). */
    public static void writeToFile(ParsedWorkbook wb, Path path, boolean prettyPrint) throws IOException {
        if (path == null) throw new IllegalArgumentException("path must be non-null");
        if (path.getParent() != null) Files.createDirectories(path.getParent());
        Files.writeString(path, toJson(wb, prettyPrint), StandardCharsets.UTF_8);
    }

    /** Pretty-printed file write — the common case (human-readable diffs
     *  between iterations are exactly what makes this useful). */
    public static void writeToFile(ParsedWorkbook wb, Path path) throws IOException {
        writeToFile(wb, path, true);
    }

    /**
     * Derive a sensible sibling-JSON path from the input schedule file.  Used
     * by MainRefactored's default-ON auto-dump so each Core run automatically
     * leaves a plain-text snapshot of its parsed schedule next to the original
     * input (XLSX is binary, JSON is mutable — the orchestrator + Tier-3.5
     * closed-loop work with the JSON sibling).
     *
     * <p>Rules:</p>
     * <ul>
     *   <li>Input ending in {@code .json} → {@code null} (skip; we don't
     *       dump JSON over JSON to avoid clobbering hand-authored sources).</li>
     *   <li>Otherwise: strip the last extension and append {@code suffix}.
     *       Default suffix {@code .iter0.json} makes the iteration semantics
     *       explicit and avoids clash with hand-authored {@code *.json}.</li>
     * </ul>
     *
     * @param inputFile the schedule file Core was asked to read
     * @param suffix    the suffix to append (e.g. {@code .iter0.json}); pass
     *                  {@code null} or empty to use the default
     * @return derived sibling path, or {@code null} when the input is JSON
     *         (don't double-dump)
     */
    public static Path deriveSiblingJsonPath(Path inputFile, String suffix) {
        if (inputFile == null) return null;
        String name = inputFile.getFileName().toString();
        String lower = name.toLowerCase(java.util.Locale.ROOT);
        if (lower.endsWith(".json")) return null;
        String stem;
        int dot = name.lastIndexOf('.');
        stem = (dot > 0) ? name.substring(0, dot) : name;
        String ext = (suffix == null || suffix.isBlank()) ? ".iter0.json" : suffix;
        if (!ext.startsWith(".")) ext = "." + ext;
        Path parent = inputFile.toAbsolutePath().getParent();
        return (parent == null)
                ? Path.of(stem + ext)
                : parent.resolve(stem + ext);
    }

    // ── implementation ───────────────────────────────────────────────────

    /** Append every row of {@code sheet} to {@code rows} as a JSON sub-array.
     *  Empty cells (null / blank) are emitted as JSON {@code null}; non-empty
     *  cells are formatted via POI's {@link DataFormatter} — same convention
     *  {@link WorkbookParser} uses to read XLSX, so the JSON faithfully
     *  represents what the downstream pipeline sees. */
    private static void appendSheetRows(ArrayNode rows, Sheet sheet, DataFormatter fmt) {
        if (sheet == null) return;
        int lastRow = sheet.getLastRowNum();
        // POI's getLastRowNum is the 0-based index of the last row OR -1 for
        // empty sheets.  Iterate inclusively up to that index, filling gaps
        // with empty arrays so positional information is preserved.
        for (int rIdx = 0; rIdx <= lastRow; rIdx++) {
            Row row = sheet.getRow(rIdx);
            ArrayNode cells = rows.addArray();
            if (row == null) continue;
            short lastCol = row.getLastCellNum();
            // getLastCellNum returns 1 past the last cell, or -1 if empty.
            for (int cIdx = 0; cIdx < lastCol; cIdx++) {
                Cell cell = row.getCell(cIdx);
                if (cell == null) { cells.addNull(); continue; }
                String v = fmt.formatCellValue(cell);
                if (v == null || v.isEmpty()) cells.addNull();
                else cells.add(v);
            }
        }
    }
}
