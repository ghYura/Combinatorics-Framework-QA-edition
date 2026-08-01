package com.company.excel;

import com.company.config.AppConfig;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.Map;

/**
 * JSON-driven schedule parser.  Reads a JSON document describing the same
 * structure as an XLSX (FW_Seq + FW_SheetNames + FW_RunMeFirstOnce +
 * payload sheets) and materialises it as an in-memory POI
 * {@link XSSFWorkbook}, then delegates to
 * {@link WorkbookParser#parseWorkbook} so the downstream pipeline (SeqParser
 * / SheetWorker / FinalTableAssembler) sees the same {@link ParsedWorkbook}
 * regardless of input format.
 *
 * Schema (rationale: 1:1 mirror of XLSX sheet/row/cell structure so users
 * can mechanically translate one to the other):
 *
 * <pre>
 * {
 *   "sheets": {
 *     "FW_Seq": [
 *       ["HEAD", "FW_Exclude", "FW_Reuse", "FW_Combi(1)", "FW_Combi(1)"],
 *       ["COST", "FW_Exclude", "FW_Reuse", "FW_Combi(1)", "FW_Combi(1)"],
 *       ...,
 *       ["ROW",  null, null, "FW_(HEAD,,COST,,LAT,,TAIL,,M:N)"]
 *     ],
 *     "FW_SheetNames": [
 *       ["HEAD", "FW_EMPTY_STRING", "FW_EMPTY_STRING"],
 *       ...
 *     ],
 *     "FW_RunMeFirstOnce": [
 *       ["class RunMeFirstOnce { ... }"]
 *     ],
 *     "FW_Arguments": [["noargs"]],
 *     "FW_CUSTOM_VAR": [[2, "FWCUSTOMVAR=2 nominal"]],
 *
 *     "HEAD":  [["scenario=demo"]],
 *     "COST":  [[" id=1 cost=0.10"], [" id=2 cost=0.30"], [" id=3 cost=0.50"]],
 *     "LAT":   [[" latency=10ms"], [" latency=30ms"], [" latency=80ms"]],
 *     "TAIL":  [[" status=ok"]],
 *     "ROW":   [["FW_EMPTY_STRING"]]
 *   }
 * }
 * </pre>
 *
 * Sheet order is preserved (LinkedHashMap-style iteration of the {@code
 * sheets} object).  Each cell value is written as a string by default;
 * numeric JSON values are converted via {@code String.valueOf}.  Null cells
 * become empty cells (mirroring XLSX's missing-cell convention).
 */
public final class JsonScheduleParser implements ScheduleParser {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public ParsedWorkbook parse(Path source, AppConfig.WorkbookConfig wbCfg) throws Exception {
        byte[] bytes = Files.readAllBytes(source);
        return parseJson(new String(bytes, StandardCharsets.UTF_8), wbCfg,
                "json:" + source.getFileName().toString());
    }

    /** Parse from a JSON string directly — useful for programmatic /
     *  embedded-config callers and for tests. */
    public ParsedWorkbook parseJson(String json, AppConfig.WorkbookConfig wbCfg,
                                     String displayName) throws Exception {
        JsonNode root = MAPPER.readTree(json);
        JsonNode sheetsNode = root.path("sheets");
        if (!sheetsNode.isObject())
            throw new IllegalArgumentException("Expected top-level 'sheets' object in JSON schedule");

        try (XSSFWorkbook wb = new XSSFWorkbook()) {
            Iterator<Map.Entry<String, JsonNode>> sheetIt = sheetsNode.fields();
            while (sheetIt.hasNext()) {
                Map.Entry<String, JsonNode> e = sheetIt.next();
                String sheetName = e.getKey();
                JsonNode rowsNode = e.getValue();
                if (!rowsNode.isArray())
                    throw new IllegalArgumentException(
                            "sheets[\"" + sheetName + "\"] must be a JSON array of row arrays");

                Sheet sheet = wb.createSheet(sheetName);
                int rowIdx = 0;
                for (JsonNode rowNode : rowsNode) {
                    Row row = sheet.createRow(rowIdx++);
                    if (rowNode.isArray()) {
                        int colIdx = 0;
                        for (JsonNode cellNode : rowNode) {
                            if (cellNode == null || cellNode.isNull()) { colIdx++; continue; }
                            Cell cell = row.createCell(colIdx++);
                            // Keep everything as STRING for downstream-stability.
                            // POI's DataFormatter (used by WorkbookParser) will
                            // format the same way it would for XLSX strings.
                            if (cellNode.isNumber()) {
                                cell.setCellValue(cellNode.asText());
                            } else if (cellNode.isBoolean()) {
                                cell.setCellValue(Boolean.toString(cellNode.asBoolean()));
                            } else {
                                cell.setCellValue(cellNode.asText());
                            }
                        }
                    } else if (rowNode.isTextual() || rowNode.isNumber()) {
                        // Convenience: a 1-cell row can be a scalar in JSON.
                        Cell cell = row.createCell(0);
                        cell.setCellValue(rowNode.asText());
                    }
                }
            }
            return WorkbookParser.parseWorkbook(wb, wbCfg, displayName);
        }
    }

    /** Build a {@link Workbook} from JSON without parsing it through
     *  WorkbookParser — exposed so callers can inspect / transform the
     *  intermediate POI workbook for debugging.  Caller MUST close the
     *  returned workbook. */
    public Workbook buildWorkbookOnly(String json) throws Exception {
        JsonNode root = MAPPER.readTree(json);
        JsonNode sheetsNode = root.path("sheets");
        XSSFWorkbook wb = new XSSFWorkbook();
        Iterator<Map.Entry<String, JsonNode>> sheetIt = sheetsNode.fields();
        while (sheetIt.hasNext()) {
            Map.Entry<String, JsonNode> e = sheetIt.next();
            Sheet sheet = wb.createSheet(e.getKey());
            int rowIdx = 0;
            for (JsonNode rowNode : e.getValue()) {
                Row row = sheet.createRow(rowIdx++);
                if (rowNode.isArray()) {
                    int colIdx = 0;
                    for (JsonNode cellNode : rowNode) {
                        if (cellNode != null && !cellNode.isNull())
                            row.createCell(colIdx).setCellValue(cellNode.asText());
                        colIdx++;
                    }
                }
            }
        }
        return wb;
    }
}
