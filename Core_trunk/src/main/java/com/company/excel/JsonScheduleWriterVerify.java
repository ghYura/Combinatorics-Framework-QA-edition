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

package com.company.excel;

import com.company.config.AppConfig;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Tier-3.5 round-trip verifier for {@link JsonScheduleWriter}: writes a
 * {@link ParsedWorkbook}, re-parses the JSON via {@link JsonScheduleParser},
 * and confirms the resulting ParsedWorkbook is cell-for-cell identical
 * (on the {@code DataFormatter}-formatted view, which is what the downstream
 * Core pipeline sees).
 *
 * <p>What this proves:</p>
 * <ul>
 *   <li>Writer + parser form a bijection on the canonical schedule
 *       fixture (the {@code test_e2e_metric} mini-scenario shared with
 *       {@link UniversalInputParityVerify}).</li>
 *   <li>Sheet order, row count, cell count, and formatted cell values are
 *       all preserved through JSON round-trip.</li>
 *   <li>Virtual sheets registered through the parser-side
 *       {@code registerVirtualSheet} survive the round-trip even when
 *       carrying no POI rows (their name stays in the sheet list).</li>
 *   <li>Both {@code stringSheetHM.keySet()} (control sheets) and the
 *       data-sheet set derived from {@code shortSheetHM} are preserved.</li>
 * </ul>
 *
 * <p>The fixture is intentionally the same one {@link UniversalInputParityVerify}
 * uses — that gives us "writer compatible with the 4-way input parity" as a
 * single transitive property, not a new isolated claim.</p>
 *
 *   Run:  java -cp ... JsonScheduleWriterVerify
 */
public final class JsonScheduleWriterVerify {
    private JsonScheduleWriterVerify() {}

    private static final String SCENARIO_YAML =
        "sheets:\n"
      + "  FW_Seq:\n"
      + "    - [\"HEAD\", \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"]\n"
      + "    - [\"COST\", \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"]\n"
      + "    - [\"LAT\",  \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"]\n"
      + "    - [\"TAIL\", \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"]\n"
      + "    - [\"ROW\", null, null, \"FW_(HEAD,,COST,,LAT,,TAIL,,M:N)\"]\n"
      + "  FW_SheetNames:\n"
      + "    - [\"HEAD\", \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"]\n"
      + "    - [\"COST\", \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"]\n"
      + "    - [\"LAT\",  \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"]\n"
      + "    - [\"TAIL\", \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"]\n"
      + "    - [\"ROW\",  \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"]\n"
      + "  FW_RunMeFirstOnce:\n"
      + "    - [\"class RunMeFirstOnce { public static String FW_ARGS;"
      +                " public static void main(String[] args){ FW_ARGS = \\\"\\\"; } }\"]\n"
      + "  FW_Arguments:\n"
      + "    - [\"noargs\"]\n"
      + "  FW_CUSTOM_VAR:\n"
      + "    - [2, \"FWCUSTOMVAR=2 nominal\"]\n"
      + "  HEAD:\n"
      + "    - [\"scenario=demo\"]\n"
      + "  COST:\n"
      + "    - [\" id=1 cost=0.10\"]\n"
      + "    - [\" id=2 cost=0.30\"]\n"
      + "    - [\" id=3 cost=0.50\"]\n"
      + "  LAT:\n"
      + "    - [\" latency=10ms\"]\n"
      + "    - [\" latency=30ms\"]\n"
      + "    - [\" latency=80ms\"]\n"
      + "  TAIL:\n"
      + "    - [\" status=ok\"]\n"
      + "  ROW:\n"
      + "    - [\"FW_EMPTY_STRING\"]\n";

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testRoundTrip();
        failures += testFileWrite();
        failures += testPrettyPrintMode();
        failures += testSiblingPathDerivation();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL JSON-SCHEDULE-WRITER CHECKS PASSED");
        else { System.out.println("❌ " + failures + " JSON-SCHEDULE-WRITER CHECK(S) FAILED"); System.exit(1); }
    }

    /** {@link JsonScheduleWriter#deriveSiblingJsonPath} is the load-bearing
     *  helper for MainRefactored's default-ON auto-dump.  Lock in the rules. */
    private static int testSiblingPathDerivation() {
        System.out.println("\n── deriveSiblingJsonPath (default-ON auto-dump helper) ──");
        int f = 0;

        Path xlsx = Path.of("/tmp/scenario_dir/test_e2e_metric.xlsx");
        Path d1 = JsonScheduleWriter.deriveSiblingJsonPath(xlsx, null);
        f += assertCond(".xlsx → .iter0.json sibling in same dir",
                d1 != null && d1.toString().endsWith("/test_e2e_metric.iter0.json")
                && d1.getParent().equals(xlsx.toAbsolutePath().getParent()));

        Path yaml = Path.of("/tmp/scenario_dir/sched.yaml");
        Path d2 = JsonScheduleWriter.deriveSiblingJsonPath(yaml, null);
        f += assertCond(".yaml → .iter0.json sibling (any extension stripped)",
                d2 != null && d2.toString().endsWith("/sched.iter0.json"));

        Path toml = Path.of("/tmp/scenario_dir/x.toml");
        Path d3 = JsonScheduleWriter.deriveSiblingJsonPath(toml, ".dump.json");
        f += assertCond(".toml + custom suffix '.dump.json' → x.dump.json",
                d3 != null && d3.toString().endsWith("/x.dump.json"));

        Path bare = Path.of("/tmp/scenario_dir/no_extension_at_all");
        Path d4 = JsonScheduleWriter.deriveSiblingJsonPath(bare, null);
        f += assertCond("no-extension input → appended .iter0.json",
                d4 != null && d4.toString().endsWith("/no_extension_at_all.iter0.json"));

        Path json = Path.of("/tmp/scenario_dir/already.json");
        Path d5 = JsonScheduleWriter.deriveSiblingJsonPath(json, null);
        f += assertCond("input already .json → null (skip double-dump)",
                d5 == null);

        Path jsonUpper = Path.of("/tmp/scenario_dir/Already.JSON");
        Path d6 = JsonScheduleWriter.deriveSiblingJsonPath(jsonUpper, null);
        f += assertCond("input .JSON (uppercase) → null (case-insensitive skip)",
                d6 == null);

        // Suffix without leading dot → still works (prepends dot)
        Path noDot = JsonScheduleWriter.deriveSiblingJsonPath(xlsx, "snap.json");
        f += assertCond("suffix without leading dot is normalised",
                noDot != null && noDot.toString().endsWith("/test_e2e_metric.snap.json"));

        // Null input → null output (no NPE)
        f += assertCond("null inputFile → null (no crash)",
                JsonScheduleWriter.deriveSiblingJsonPath(null, null) == null);
        return f;
    }

    private static int testRoundTrip() throws Exception {
        System.out.println("── ParsedWorkbook ⇄ JSON round-trip ──");
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");

        // 1. Parse the canonical YAML fixture → ParsedWorkbook A.
        ParsedWorkbook a = new YamlScheduleParser().parseYaml(SCENARIO_YAML, wbCfg, "yaml:rt");

        // 2. Serialize via JsonScheduleWriter → JSON string.
        String roundTripJson = JsonScheduleWriter.toJson(a, false);

        // 3. Re-parse JSON → ParsedWorkbook B.
        ParsedWorkbook b = new JsonScheduleParser().parseJson(roundTripJson, wbCfg, "json:rt");

        int f = 0;
        f += compare("YAML-parsed  ↔  JSON-round-tripped", a, b);
        return f;
    }

    private static int testFileWrite() throws Exception {
        System.out.println("\n── writeToFile + re-load ──");
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");
        ParsedWorkbook a = new YamlScheduleParser().parseYaml(SCENARIO_YAML, wbCfg, "yaml:file");

        Path tmp = Files.createTempFile("schedule_writer_", ".json");
        JsonScheduleWriter.writeToFile(a, tmp);
        ParsedWorkbook b = new JsonScheduleParser().parse(tmp, wbCfg);

        int f = 0;
        f += assertCond("file written to " + tmp, Files.exists(tmp) && Files.size(tmp) > 0);
        f += compare("file ↔ parser re-load", a, b);
        Files.deleteIfExists(tmp);
        return f;
    }

    private static int testPrettyPrintMode() throws Exception {
        System.out.println("\n── pretty-print toggle ──");
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");
        ParsedWorkbook a = new YamlScheduleParser().parseYaml(SCENARIO_YAML, wbCfg, "yaml:pp");

        String compact = JsonScheduleWriter.toJson(a, false);
        String pretty  = JsonScheduleWriter.toJson(a, true);
        int f = 0;
        f += assertCond("compact mode is shorter (no leading whitespace)",
                compact.length() < pretty.length());
        f += assertCond("compact mode has no newlines outside string literals",
                compact.indexOf('\n') < 0);
        f += assertCond("pretty mode has newlines (2-space indentation)",
                pretty.indexOf('\n') >= 0);
        return f;
    }

    // ─── pairwise comparison (mirrors UniversalInputParityVerify.compare) ──

    private static int compare(String label, ParsedWorkbook a, ParsedWorkbook b) {
        int f = 0;
        System.out.println("  ── " + label + " ──");

        Set<String> aCtrl = new LinkedHashSet<>(a.stringSheetHM.keySet());
        Set<String> bCtrl = new LinkedHashSet<>(b.stringSheetHM.keySet());
        f += assertCond("control sheet set identical (" + aCtrl + ")", aCtrl.equals(bCtrl));
        f += assertCond("control sheet order identical",
                aCtrl.toString().equals(bCtrl.toString()));
        for (String name : aCtrl) {
            f += compareSheets("control '" + name + "'",
                    a.stringSheetHM.get(name), b.stringSheetHM.get(name));
        }

        Set<String> aData = new LinkedHashSet<>();
        Set<String> bData = new LinkedHashSet<>();
        for (var e : a.shortSheetHM.entrySet())
            aData.add(a.shortStringSheetKey2SheetNameHM.get(e.getKey()));
        for (var e : b.shortSheetHM.entrySet())
            bData.add(b.shortStringSheetKey2SheetNameHM.get(e.getKey()));
        f += assertCond("data sheet set identical (" + aData + ")", aData.equals(bData));
        f += assertCond("data sheet order identical",
                aData.toString().equals(bData.toString()));
        for (String name : aData) {
            Short ka = a.stringShortSheetName2SheetKeyHM.get(name);
            Short kb = b.stringShortSheetName2SheetKeyHM.get(name);
            f += compareSheets("data '" + name + "'",
                    a.shortSheetHM.get(ka), b.shortSheetHM.get(kb));
        }
        f += assertCond("numOfFwSheets match (" + a.numOfFwSheets + " vs " + b.numOfFwSheets + ")",
                a.numOfFwSheets == b.numOfFwSheets);
        f += assertCond("maxSheetNumber match (" + a.maxSheetNumber + " vs " + b.maxSheetNumber + ")",
                a.maxSheetNumber == b.maxSheetNumber);
        return f;
    }

    private static int compareSheets(String label, Sheet sa, Sheet sb) {
        int f = 0;
        int rowsA = sa == null ? 0 : sa.getLastRowNum();
        int rowsB = sb == null ? 0 : sb.getLastRowNum();
        f += assertCond(label + ": rows " + rowsA + " vs " + rowsB, rowsA == rowsB);
        for (int r = 0; r <= Math.max(rowsA, rowsB); r++) {
            Row ra = sa == null ? null : sa.getRow(r);
            Row rb = sb == null ? null : sb.getRow(r);
            if (ra == null && rb == null) continue;
            if (ra == null || rb == null) {
                f += assertCond(label + " row #" + r + " presence mismatch", false);
                continue;
            }
            int wide = Math.max(ra.getLastCellNum(), rb.getLastCellNum());
            for (int c = 0; c < wide; c++) {
                String va = cellStr(sa, r, c);
                String vb = cellStr(sb, r, c);
                if (!va.equals(vb)) {
                    f += assertCond(label + " row #" + r + " col #" + c
                            + ": '" + va + "' vs '" + vb + "'", false);
                }
            }
        }
        return f;
    }

    private static String cellStr(Sheet s, int rowIdx, int colIdx) {
        if (s == null) return "";
        Row r = s.getRow(rowIdx);
        if (r == null) return "";
        Cell c = r.getCell(colIdx);
        if (c == null) return "";
        return new DataFormatter(Locale.ROOT).formatCellValue(c);
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "    ✓ " : "    ✗ ") + label);
        return cond ? 0 : 1;
    }
}
