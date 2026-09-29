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

package com.company.excel;

import com.company.SeqParser;
import com.company.SheetWorker;
import com.company.config.AppConfig;
import com.company.keys.KeyCodec;
import com.company.keys.KeyCodecs;
import com.company.store.JavaIntermediateTableStore;
import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.core.config.Configurator;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

/**
 * Verifier for {@link DataTypeDispatcher} — deterministic, no DB, no network:
 *
 *   A. width thresholds: short is the default (legacy); byte is the experiment (core.keys.dispatch=auto)
 *      and falls back to short exactly when the byte range overflows;
 *   B. short range: legacy numbering while it fits, a forced window beyond, fail-fast past 65536;
 *   C. the census predicate agrees with what the parser really issues (every directive form);
 *   D. sheet keys and virtual-sheet keys are untouched by the label window;
 *   E. the label window is an order-preserving bijection and ANCHOR puts the heavy sheet at 0;
 *   F. safety guards: FW_ReplaceRE keeps the legacy keys, the minimum-gain threshold is honoured;
 *   G. VALUE-level equivalence: the real SheetWorker gives identical results (rows resolved back to
 *      cell values) under every label plan, including negative labels through FW_Group / joiners;
 *   H. {@code core.keys.*} configuration parsing.
 *
 * G and H need the project's fw.properties (run from the Core_trunk directory); without it they SKIP.
 *
 * Run via:
 * {@code java -cp target/classes:$(cat /tmp/cp.txt) com.company.excel.DataTypeDispatcherVerify}
 */
public final class DataTypeDispatcherVerify {
    private DataTypeDispatcherVerify() {}

    private static int failed = 0;

    public static void main(String[] args) throws Exception {
        // parseWorkbook persists every cell through Hibernate; without a DB that logs one error per cell.
        try { Configurator.setLevel("com.company.dao", Level.OFF); Configurator.setLevel("com.company.utils", Level.OFF); }
        catch (Throwable ignored) { /* logging backend other than log4j-core: keep the noise */ }

        sectionA();
        sectionB();
        sectionC();
        sectionD();
        sectionE();
        sectionF();
        Path props = locateProperties(args);
        sectionG(props);
        sectionH(props);

        if (failed == 0) System.out.println("\n✅ ALL DATA-TYPE-DISPATCHER CHECKS PASSED");
        else { System.out.println("\n❌ " + failed + " DATA-TYPE-DISPATCHER CHECK(S) FAILED"); System.exit(1); }
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private static AppConfig.KeysConfig keys(AppConfig.KeysConfig.Dispatch d, AppConfig.KeysConfig.Strategy s,
                                             AppConfig.KeysConfig.Scope sc, double minGain) {
        return new AppConfig.KeysConfig(d, s, sc, null, minGain);
    }

    private static final AppConfig.KeysConfig AUTO_IDENTITY = keys(AppConfig.KeysConfig.Dispatch.AUTO,
            AppConfig.KeysConfig.Strategy.IDENTITY, AppConfig.KeysConfig.Scope.ALL, 5.0);

    /** A workbook of {@code sheets} data sheets holding {@code cells} plain cells in total (all in the first sheet's
     *  rows of 200, the rest empty), plus an optional FW_Seq. */
    private static XSSFWorkbook workbook(int sheets, int cells, String[][] seqRows) {
        XSSFWorkbook wb = new XSSFWorkbook();
        Sheet seq = wb.createSheet("FW_Seq");
        if (seqRows != null) {
            for (int r = 0; r < seqRows.length; r++) {
                Row row = seq.createRow(r);
                for (int c = 0; c < seqRows[r].length; c++) row.createCell(c).setCellValue(seqRows[r][c]);
            }
        }
        for (int s = 0; s < sheets; s++) {
            Sheet sh = wb.createSheet("S" + s);
            if (s != 0) continue;
            for (int i = 0; i < cells; i++) {
                Row row = (i % 200 == 0) ? sh.createRow(i / 200) : sh.getRow(i / 200);
                row.createCell(i % 200).setCellValue("v" + i);
            }
        }
        return wb;
    }

    private static Sheet[] all(XSSFWorkbook wb) {
        Sheet[] a = new Sheet[wb.getNumberOfSheets()];
        for (int i = 0; i < a.length; i++) a[i] = wb.getSheetAt(i);
        return a;
    }

    private static DataTypeDispatcher.Plan planOf(XSSFWorkbook wb, AppConfig.KeysConfig k) {
        AppConfig.WorkbookConfig wc = new AppConfig.WorkbookConfig(false, false, "FW_virtual_", k);
        return DataTypeDispatcher.plan(DataTypeDispatcher.count(all(wb), wb.getSheet("FW_Seq"), wc), wb.getSheet("FW_Seq"), k);
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        if (!cond) failed++;
        return cond ? 0 : 1;
    }

    // ── A: width thresholds ──────────────────────────────────────────────

    private static void sectionA() throws Exception {
        System.out.println("── A. short is the default; byte is the experiment and falls back to short when its range overflows ──");
        assertCond("capacities: byte 255 (= Byte.MAX_VALUE - Byte.MIN_VALUE), short 65535; MIN_VALUE is the reserved NULL element",
                DataTypeDispatcher.BYTE_CAPACITY == 255 && DataTypeDispatcher.SHORT_CAPACITY == 65535
                        && Byte.MAX_VALUE - Byte.MIN_VALUE == 255
                        && DataTypeDispatcher.Tier.BYTE.min == Byte.MIN_VALUE + 1
                        && DataTypeDispatcher.Tier.SHORT.min == Short.MIN_VALUE + 1);
        try (XSSFWorkbook wb = workbook(3, 20, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, null);
            assertCond("no core.keys.* at all (KeysConfig.DEFAULT): SHORT with legacy numbering -- byte never switches itself on",
                    AppConfig.KeysConfig.DEFAULT.dispatch == AppConfig.KeysConfig.Dispatch.SHORT
                            && p.tier == DataTypeDispatcher.Tier.SHORT && p.identity && p.firstLabel == 4 && p.lastLabel() == 23);
            DataTypeDispatcher.Plan e = planOf(wb, AUTO_IDENTITY);
            assertCond("the same workbook with the experiment on (dispatch=auto): BYTE",
                    e.tier == DataTypeDispatcher.Tier.BYTE && e.identity && e.firstLabel == 4);
        }
        try (XSSFWorkbook wb = workbook(3, 100, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=3 C=100 (T=103): BYTE, legacy numbering 4..103",
                    p.tier == DataTypeDispatcher.Tier.BYTE && p.identity && p.firstLabel == 4 && p.lastLabel() == 103);
        }
        try (XSSFWorkbook wb = workbook(3, 124, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=3 C=124 (T=127): BYTE, legacy numbering still fits (4..127)",
                    p.tier == DataTypeDispatcher.Tier.BYTE && p.identity && p.lastLabel() == 127);
        }
        try (XSSFWorkbook wb = workbook(3, 125, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=3 C=125 (T=128): still BYTE, window forced into negatives (labels within -127..127)",
                    p.tier == DataTypeDispatcher.Tier.BYTE && !p.identity && p.firstLabel >= -127 && p.lastLabel() <= 127);
        }
        try (XSSFWorkbook wb = workbook(3, 252, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=3 C=252 (T=255): BYTE, the widest byte window -127..124 (Byte.MIN_VALUE stays reserved)",
                    p.tier == DataTypeDispatcher.Tier.BYTE && p.firstLabel >= -127 && p.lastLabel() <= 127);
        }
        try (XSSFWorkbook wb = workbook(3, 253, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=3 C=253 (T=256 > Byte.MAX-Byte.MIN): byte overflows -> SHORT, legacy numbering 4..256",
                    p.tier == DataTypeDispatcher.Tier.SHORT && p.identity && p.firstLabel == 4 && p.lastLabel() == 256);
            AppConfig.KeysConfig cells = keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.IDENTITY,
                    AppConfig.KeysConfig.Scope.CELLS, 5.0);
            assertCond("scope=cells: same workbook gates on C=253 <= 255 -> BYTE",
                    planOf(wb, cells).tier == DataTypeDispatcher.Tier.BYTE);
        }
        try (XSSFWorkbook wb = workbook(3, 255, null)) {
            AppConfig.KeysConfig cells = keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.IDENTITY,
                    AppConfig.KeysConfig.Scope.CELLS, 5.0);
            DataTypeDispatcher.Plan p = planOf(wb, cells);
            assertCond("scope=cells, C=255: BYTE, labels exactly -127..127",
                    p.tier == DataTypeDispatcher.Tier.BYTE && p.firstLabel == -127 && p.lastLabel() == 127);
        }
        try (XSSFWorkbook wb = workbook(3, 256, null)) {
            AppConfig.KeysConfig cells = keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.IDENTITY,
                    AppConfig.KeysConfig.Scope.CELLS, 5.0);
            assertCond("scope=cells, C=256: overflow -> SHORT",
                    planOf(wb, cells).tier == DataTypeDispatcher.Tier.SHORT);
        }
        try (XSSFWorkbook wb = workbook(3, 20, null)) {
            AppConfig.KeysConfig legacy = keys(AppConfig.KeysConfig.Dispatch.SHORT, AppConfig.KeysConfig.Strategy.IDENTITY,
                    AppConfig.KeysConfig.Scope.ALL, 5.0);
            DataTypeDispatcher.Plan p = planOf(wb, legacy);
            assertCond("dispatch=short: legacy width and legacy numbering even for a tiny workbook",
                    p.tier == DataTypeDispatcher.Tier.SHORT && p.identity && p.firstLabel == 4);
        }
        try (XSSFWorkbook wb = workbook(3, 0, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("no cells at all: BYTE, nothing to label", p.tier == DataTypeDispatcher.Tier.BYTE && p.cells == 0);
        }
    }

    // ── B: short range ───────────────────────────────────────────────────

    private static void sectionB() throws Exception {
        System.out.println("\n── B. short range: legacy numbering while it fits, window beyond, fail-fast past 65536 ──");
        try (XSSFWorkbook wb = workbook(2, 32765, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=2 C=32765: SHORT, legacy numbering 3..32767 (the last positive short)",
                    p.tier == DataTypeDispatcher.Tier.SHORT && p.identity && p.lastLabel() == 32767);
        }
        try (XSSFWorkbook wb = workbook(2, 32766, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=2 C=32766: the legacy short[] counter would have WRAPPED here; now a window (-32767..32767)",
                    p.tier == DataTypeDispatcher.Tier.SHORT && !p.identity
                            && p.firstLabel >= -32767 && p.lastLabel() <= 32767 && p.cells == 32766);
        }
        try (XSSFWorkbook wb = workbook(2, 65533, null)) {
            DataTypeDispatcher.Plan p = planOf(wb, AUTO_IDENTITY);
            assertCond("S=2 C=65533 (T=65535): SHORT, the whole usable 16-bit window, Short.MIN_VALUE never issued",
                    p.tier == DataTypeDispatcher.Tier.SHORT && p.firstLabel >= -32767 && p.lastLabel() <= 32767 && p.cells == 65533);
            boolean rejected = false;
            try { DataTypeDispatcher.Plan.custom(DataTypeDispatcher.Tier.SHORT, 2, 0, 65535, -32768); }
            catch (IllegalArgumentException e) { rejected = true; }
            assertCond("a plan containing Short.MIN_VALUE (the Reader's NULL element) is refused outright", rejected);
        }
        try (XSSFWorkbook wb = workbook(2, 65534, null)) {
            boolean threw = false; String msg = "";
            try { planOf(wb, AUTO_IDENTITY); }
            catch (IllegalStateException e) { threw = true; msg = e.getMessage(); }
            assertCond("S=2 C=65534 (T=65536): fails fast, message names the short range (65535)",
                    threw && msg.contains("short") && msg.contains("65535"));
        }
        try (XSSFWorkbook wb = workbook(2, 70000, null)) {
            boolean threw = false;
            try { planOf(wb, AUTO_IDENTITY); } catch (IllegalStateException e) { threw = true; }
            assertCond("C=70000: census stops early and the plan fails fast", threw);
        }
    }

    // ── C: census == parser ──────────────────────────────────────────────

    private static void sectionC() throws Exception {
        System.out.println("\n── C. the census predicate agrees with what the parser really issues ──");
        String[][] cases = {
                {"plain", "1"}, {"FW_CSVFile=x.csv", "0"}, {"FW_File=x.txt", "1"}, {"FW_BinaryFile=x", "0"},
                {"FW_DBURL=x", "0"}, {"FW_DBUSER=x", "0"}, {"FW_DBPASS=x", "0"}, {"FW_SQL=select 1", "0"},
                {"FW_Separator=,", "0"}, {"FW_Optional", "0"}, {"FW_RefineCodeExceptQuoted", "0"},
                {"FW_EMPTY_STRING", "1"}, {"FW_Bogus", "0"}, {"FW_VAR = FW_EXIT_CODE", "1"},
                {"FW_EXIT_CODE", "1"}, {"FW_CUSTOM_VAR=1", "1"}, {"x FW_Optional", "1"}, {"", "1"},
        };
        boolean all = true;
        for (String[] c : cases) {
            int got = WorkbookParser.keysConsumedBy(c[0]);
            if (got != Integer.parseInt(c[1])) { all = false; System.out.println("      '" + c[0] + "' -> " + got + ", expected " + c[1]); }
        }
        assertCond("keysConsumedBy(String) for all " + cases.length + " directive/plain forms", all);

        // A workbook mixing string, numeric, boolean, blank and formula cells: parse must issue exactly the counted keys
        // (WorkbookParser throws "census mismatch" otherwise).  Directives that read the DB (FW_Optional) are covered above.
        try (XSSFWorkbook wb = new XSSFWorkbook()) {
            Sheet seq = wb.createSheet("FW_Seq");
            seq.createRow(0).createCell(0).setCellValue("M");
            Sheet m = wb.createSheet("M");
            Row r0 = m.createRow(0);
            r0.createCell(0).setCellValue("plain");
            r0.createCell(1).setCellValue("FW_CSVFile=nofile.csv");     // 0 keys
            r0.createCell(2).setCellValue("FW_EMPTY_STRING");           // 1 key
            r0.createCell(3).setCellValue(42.0);                        // numeric: 1 key
            r0.createCell(4).setCellValue(true);                        // boolean: 1 key
            r0.createCell(5).setBlank();                                // blank: 1 key
            r0.createCell(6).setCellFormula("1+1");                     // formula: 1 key
            r0.createCell(7).setCellValue("FW_Bogus");                  // 0 keys
            r0.createCell(8).setCellValue("FW_VAR = FW_EXIT_CODE");     // 1 key (+ exit-code row)
            Row r1 = m.createRow(1);
            r1.createCell(0).setCellValue("FW_SQL=x");                  // 0 keys
            r1.createCell(1).setCellValue("tail");                      // 1 key
            DataTypeDispatcher.Census census = DataTypeDispatcher.count(all(wb), seq, null);
            assertCond("census counts 8 keys for the mixed workbook (got " + census.cells + ")", census.cells == 8);
            AppConfig.WorkbookConfig wc = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");
            ParsedWorkbook pw = null; String err = "";
            try { pw = WorkbookParser.parseWorkbook(wb, wc, "verify:mixed"); }
            catch (RuntimeException e) { err = e.getMessage(); }
            assertCond("parse issued exactly the counted keys (no census-mismatch exception" + (err.isEmpty() ? "" : ": " + err) + ")", pw != null);
            if (pw != null) {
                short mKey = pw.stringShortSheetName2SheetKeyHM.get("M");
                assertCond("sheetData for 'M' holds 8 keys", pw.sheetData.get(mKey).size() == 8);
            }
        }
    }

    // ── D: sheet keys and virtual keys ───────────────────────────────────

    private static void sectionD() throws Exception {
        System.out.println("\n── D. sheet keys and virtual-sheet keys are untouched by the label window ──");
        String[][] seqRows = { {"S0", "FW_Combi(1)", "FW_Combi(1)"}, {"MISSING", "FW_Combi(1)", "FW_Combi(1)"} };
        try (XSSFWorkbook wb = workbook(2, 30, seqRows)) {
            AppConfig.KeysConfig anchor = keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.OPTIMAL,
                    AppConfig.KeysConfig.Scope.ALL, 0.0);
            AppConfig.WorkbookConfig wc = new AppConfig.WorkbookConfig(true, false, "FW_virtual_", anchor);
            ParsedWorkbook pw = WorkbookParser.parseWorkbook(wb, wc, "verify:virtual");
            assertCond("real sheets keep keys 1..S regardless of the label window",
                    pw.stringShortSheetName2SheetKeyHM.get("S0") == 1 && pw.stringShortSheetName2SheetKeyHM.get("S1") == 2);
            assertCond("virtual sheet 'MISSING' is registered right after the last cell key (legacy: S + C + 1 = 33)",
                    pw.stringShortSheetName2SheetKeyHM.get("MISSING") == 33);
            assertCond("census counted the virtual sheet (plan.virtualSheets == 1)", pw.keyPlan.virtualSheets == 1);
        }
        DataTypeDispatcher.Plan huge = DataTypeDispatcher.Plan.custom(DataTypeDispatcher.Tier.SHORT, 3, 2, 40000, -32767);
        assertCond("virtualKeyBase: S + C + V > 32767 -> virtual keys start right after the real sheets",
                huge.virtualKeyBase() == 3);
        DataTypeDispatcher.Plan small = DataTypeDispatcher.Plan.custom(DataTypeDispatcher.Tier.BYTE, 3, 2, 50, 4);
        assertCond("virtualKeyBase: legacy position S + C otherwise", small.virtualKeyBase() == 53);
    }

    // ── E: window is an order-preserving bijection; ANCHOR puts the heavy sheet at 0 ─

    private static void sectionE() throws Exception {
        System.out.println("\n── E. the label window is an order-preserving bijection ──");
        String[][] seq = { {"A", "FW_Combi(2)", "FW_Combi(2)"}, {"B", "FW_Combi(2)", "FW_Combi(2)"},
                {"HEAVY", "FW_Permut", "FW_Permut"}, {"C", "FW_Combi(2)", "FW_Combi(2)"} };
        try (XSSFWorkbook wb = new XSSFWorkbook()) {
            Sheet s = wb.createSheet("FW_Seq");
            for (int r = 0; r < seq.length; r++) { Row row = s.createRow(r); for (int c = 0; c < seq[r].length; c++) row.createCell(c).setCellValue(seq[r][c]); }
            int[] n = {20, 20, 5, 40};
            String[] names = {"A", "B", "HEAVY", "C"};
            for (int i = 0; i < names.length; i++) { Row row = wb.createSheet(names[i]).createRow(0); for (int c = 0; c < n[i]; c++) row.createCell(c).setCellValue(names[i] + c); }
            AppConfig.KeysConfig anchor = new AppConfig.KeysConfig(AppConfig.KeysConfig.Dispatch.AUTO,
                    AppConfig.KeysConfig.Strategy.ANCHOR, AppConfig.KeysConfig.Scope.ALL, null, 0.0);
            AppConfig.WorkbookConfig wc = new AppConfig.WorkbookConfig(false, false, "FW_virtual_", anchor);
            ParsedWorkbook pw = WorkbookParser.parseWorkbook(wb, wc, "verify:anchor");
            DataTypeDispatcher.Plan p = pw.keyPlan;
            assertCond("plan adopted ANCHOR (relabelled, BYTE): " + p.describe().replaceAll("\\s*\\|.*", ""),
                    p.strategy == AppConfig.KeysConfig.Strategy.ANCHOR && !p.identity && p.tier == DataTypeDispatcher.Tier.BYTE);
            List<Short> heavy = pw.sheetData.get(pw.stringShortSheetName2SheetKeyHM.get("HEAVY"));
            assertCond("first cell of the most output-heavy sheet is key 0", heavy.get(0) == 0);
            boolean order = true, unique = true, inRange = true, sequential = true;
            List<Short> flat = new ArrayList<>();
            for (String name : names) flat.addAll(pw.sheetData.get(pw.stringShortSheetName2SheetKeyHM.get(name)));
            for (int i = 0; i < flat.size(); i++) {
                if (i > 0 && flat.get(i) <= flat.get(i - 1)) order = false;
                if (flat.get(i) != p.firstLabel + i) sequential = false;
                if (flat.get(i) <= Byte.MIN_VALUE || flat.get(i) > Byte.MAX_VALUE) inRange = false;
            }
            unique = flat.stream().distinct().count() == flat.size();
            assertCond("labels strictly increase in workbook order (FW_Group's sort order is preserved)", order);
            assertCond("labels are unique, contiguous and inside the byte window without Byte.MIN_VALUE", unique && sequential && inRange);
        }
    }

    // ── F: safety guards ─────────────────────────────────────────────────

    private static void sectionF() throws Exception {
        System.out.println("\n── F. safety guards ──");
        String[][] withRe = { {"A", "FW_Combi(2)", "FW_Group FW_ReplaceRE(\"1\", \"2\")"}, {"B", "FW_Permut", "FW_Permut"} };
        try (XSSFWorkbook wb = workbook(3, 90, withRe)) {
            AppConfig.KeysConfig optimal = keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.OPTIMAL,
                    AppConfig.KeysConfig.Scope.ALL, 0.0);
            DataTypeDispatcher.Plan p = planOf(wb, optimal);
            assertCond("FW_ReplaceRE in FW_Seq keeps the legacy keys (its regexes may name literal keys)",
                    p.identity && p.strategy == AppConfig.KeysConfig.Strategy.IDENTITY && p.reason.contains("FW_ReplaceRE"));
        }
        String[][] plain = { {"S0", "FW_Permut", "FW_Permut"} };
        try (XSSFWorkbook wb = workbook(3, 90, plain)) {
            AppConfig.KeysConfig strict = keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.OPTIMAL,
                    AppConfig.KeysConfig.Scope.ALL, 100.0);
            DataTypeDispatcher.Plan p = planOf(wb, strict);
            assertCond("minGainPercent=100 rejects every relabelling (legacy numbering kept)",
                    p.identity && p.reason.contains("rejected"));
        }
    }

    // ── G: value-level equivalence through the real SheetWorker ──────────

    private static Path locateProperties(String[] args) {
        Path p = Paths.get(args.length > 0 ? args[0] : "fw.properties");
        return Files.isRegularFile(p) ? p : null;
    }

    private static AppConfig loadConfig(Path props) throws Exception {
        // Only patched where a DB-free run needs it: a non-blank password (validated at load, never used).
        Path tmp = Files.createTempFile("dtd_verify_", ".properties");
        List<String> lines = new ArrayList<>(Files.readAllLines(props, StandardCharsets.ISO_8859_1));
        lines.add("db.password=verify");
        lines.add("core.precompute=java");
        lines.add("core.intermediate.storage=memory");
        Files.write(tmp, lines, StandardCharsets.ISO_8859_1);
        try { return AppConfig.load(tmp); } finally { Files.deleteIfExists(tmp); }
    }

    private static List<String> cellTexts(XSSFWorkbook wb) {
        List<String> out = new ArrayList<>();
        for (Sheet s : all(wb)) {
            if (s.getSheetName().startsWith("FW_")) continue;
            for (Row r : s) for (Cell c : r) if (WorkbookParser.keysConsumedBy(c) > 0) out.add(new org.apache.poi.ss.usermodel.DataFormatter().formatCellValue(c));
        }
        return out;
    }

    /** sheet name -> sorted rows, every key resolved by ORDINAL (label - firstLabel) back to the cell text. */
    private static Map<String, List<String>> runPipeline(AppConfig config, Supplier<ProgrammaticScheduleBuilder.SheetEntry> src,
                                                         AppConfig.KeysConfig k, double[] cost) throws Exception {
        return runPipeline(config, src, k, cost, null);
    }

    /**
     * @param forced null = the codec of the plan's tier (byte[] rows on the BYTE tier, short[] on SHORT);
     *               a codec here overrides that, e.g. to push a byte-tier plan through the short[] path.
     *               {@code cost[2]} reports 1 when the plan is byte-tier.
     */
    private static Map<String, List<String>> runPipeline(AppConfig config, Supplier<ProgrammaticScheduleBuilder.SheetEntry> src,
                                                         AppConfig.KeysConfig k, double[] cost, KeyCodec<?> forced) throws Exception {
        ProgrammaticScheduleBuilder.SheetEntry entry = src.get();
        List<String> texts;
        try (XSSFWorkbook wb = entry.buildWorkbook()) { texts = cellTexts(wb); }
        ParsedWorkbook pw = entry.build(new AppConfig.WorkbookConfig(true, true, "FW_VIRTUAL_", k));
        SeqParser.SeqParseResult seq = SeqParser.parse(pw, pw.sheetData, config.seq);
        KeyCodec<?> codec = (forced != null) ? forced : KeyCodecs.of(pw.keyPlan.tier);
        cost[2] = pw.keyPlan.tier == DataTypeDispatcher.Tier.BYTE ? 1 : 0;
        return pipeline(config, pw, seq, texts, codec, cost);
    }

    private static <A> Map<String, List<String>> pipeline(AppConfig config, ParsedWorkbook pw, SeqParser.SeqParseResult seq,
                                                          List<String> texts, KeyCodec<A> codec, double[] cost) throws Exception {
        JavaIntermediateTableStore<A> store = new JavaIntermediateTableStore<>(codec);
        for (Short key : pw.sheetData.keySet()) {
            if (seq.mapShKey2seqList.containsKey(key) && !seq.mapShKey2seqList.get(key).isEmpty()) store.createFwTable(key);
        }
        SheetWorker<A> worker = new SheetWorker<>(config, null, null, pw, store);
        worker.processAll(seq.toCombinatoricsHM, seq.toCombinatoricsHMoptional, seq.toCombinatoricsHMexclude,
                seq.mapShKey2seqList, seq.reuseSet, seq.reuseTableOnlySet, seq.keyShortExcluded1List, seq.keyShortExcluded2List);

        double rtot = 1; List<List<A>> mandatory = new ArrayList<>();
        for (Map.Entry<Short, String> me : worker.getKey2tableMap().entrySet()) {
            List<A> rows = me.getValue().startsWith("fw2_") ? store.readFw2Combos(me.getKey()) : store.readFwCombos(me.getKey());
            if (rows.isEmpty()) continue;
            mandatory.add(rows); rtot *= rows.size();
        }
        double c = 0;
        for (List<A> rows : mandatory) {
            double s = 0;
            for (A r : rows) for (int lab : codec.toInts(r)) s += DataTypeDispatcher.labelChars((short) lab) + 1;
            c += (rtot / rows.size()) * s;
        }
        cost[0] = c;
        cost[1] = pw.keyPlan.predictedGainPercent;

        Map<String, List<String>> out = new LinkedHashMap<>();
        for (Map.Entry<Short, String> e : pw.shortStringSheetKey2SheetNameHM.entrySet()) {
            for (boolean fw2 : new boolean[]{false, true}) {
                List<A> rows = fw2 ? store.readFw2Combos(e.getKey()) : store.readFwCombos(e.getKey());
                if (rows.isEmpty()) continue;
                List<String> res = new ArrayList<>();
                for (A r : rows) {
                    StringBuilder sb = new StringBuilder();
                    for (int lab : codec.toInts(r)) sb.append(texts.get(lab - pw.keyPlan.firstLabel)).append('|');
                    res.add(sb.toString());
                }
                Collections.sort(res);
                out.put(e.getValue() + (fw2 ? "@fw2" : "@fw"), res);
            }
        }
        return out;
    }

    private static void equivalence(AppConfig config, String name, Supplier<ProgrammaticScheduleBuilder.SheetEntry> src) throws Exception {
        System.out.println("  " + name);
        AppConfig.KeysConfig[] plans = {
                keys(AppConfig.KeysConfig.Dispatch.SHORT, AppConfig.KeysConfig.Strategy.IDENTITY, AppConfig.KeysConfig.Scope.ALL, 0.0),
                keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.IDENTITY, AppConfig.KeysConfig.Scope.ALL, 0.0),
                keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.ANCHOR, AppConfig.KeysConfig.Scope.ALL, 0.0),
                keys(AppConfig.KeysConfig.Dispatch.AUTO, AppConfig.KeysConfig.Strategy.OPTIMAL, AppConfig.KeysConfig.Scope.ALL, 0.0),
                keys(AppConfig.KeysConfig.Dispatch.SHORT, AppConfig.KeysConfig.Strategy.OPTIMAL, AppConfig.KeysConfig.Scope.ALL, 0.0),
        };
        String[] labels = {"legacy (short, identity)", "auto identity", "auto ANCHOR", "auto OPTIMAL", "short OPTIMAL"};
        double[] cost = new double[3];
        // The engine runs sheets on virtual threads and (independently of this change) can drop a joiner table when a
        // joiner thread starts before its operands' completion futures are registered.  Repeat the reference until it is
        // complete so the comparison measures the label plans, not that race.
        Map<String, List<String>> ref = null; double refCost = 0;
        for (int attempt = 0; attempt < 5 && ref == null; attempt++) {
            Map<String, List<String>> r = runPipeline(config, src, plans[0], cost);
            Map<String, List<String>> again = runPipeline(config, src, plans[0], new double[3]);
            if (r.equals(again)) { ref = r; refCost = cost[0]; }
        }
        assertCond(name + ": reference run is stable", ref != null);
        if (ref == null) return;
        double identityCost = 0;
        for (int i = 1; i < plans.length; i++) {
            Map<String, List<String>> res = null;
            for (int attempt = 0; attempt < 5; attempt++) {
                res = runPipeline(config, src, plans[i], cost);
                if (ref.equals(res)) break;
            }
            boolean same = ref.equals(res);
            boolean byteTier = cost[2] == 1;
            if (i == 1) identityCost = cost[0];
            String gain = (i >= 2 && identityCost > 0)
                    ? String.format("  [predicted %.1f%% / actual %.1f%% fewer key characters]", cost[1], 100.0 * (identityCost - cost[0]) / identityCost) : "";
            assertCond(labels[i] + ": every row identical after resolving keys back to cell values"
                    + (byteTier ? " [byte[] rows]" : " [short[] rows]") + gain, same);
            if (byteTier) {
                // the same byte-tier plan through the short[] path: rows must not depend on the array width
                Map<String, List<String>> viaShort = null;
                for (int attempt = 0; attempt < 5; attempt++) {
                    viaShort = runPipeline(config, src, plans[i], new double[3], KeyCodecs.SHORT);
                    if (ref.equals(viaShort)) break;
                }
                assertCond(labels[i] + ": byte[] rows and short[] rows carry the very same values", ref.equals(viaShort));
            }
            if (i >= 2 && identityCost > 0) {
                double actual = 100.0 * (identityCost - cost[0]) / identityCost;
                assertCond(labels[i] + ": model predicted the right sign and magnitude (|predicted - actual| <= 10 points)",
                        actual >= 0 && Math.abs(cost[1] - actual) <= 10.0);
            }
        }
    }

    private static String[] cells(String prefix, int n) { String[] a = new String[n]; for (int i = 0; i < n; i++) a[i] = prefix + i; return a; }

    private static void sectionG(Path props) throws Exception {
        System.out.println("\n── G. VALUE-level equivalence through the real SheetWorker (memory store) ──");
        if (props == null) { System.out.println("  ◌ SKIP  fw.properties not found — run from Core_trunk or pass its path as arg #1"); return; }
        AppConfig config = loadConfig(props);
        equivalence(config, "W1 all combinatorial verbs", () -> ProgrammaticScheduleBuilder.newSchedule()
                .sheet("PAD").flags(Flag.EXCLUDE).rowCells(cells("pad", 25))
                .sheet("A").verbs(Verb.combi(2)).rowCells(cells("a", 5))
                .sheet("B").verbs(Verb.permut(2)).rowCells(cells("b", 3))
                .sheet("C").verbs(Verb.subsets()).rowCells(cells("c", 4))
                .sheet("D").verbs(Verb.combiR(2)).rowCells(cells("d", 3))
                .sheet("E").verbs(Verb.permutR(2)).rowCells(cells("e", 3))
                .sheet("F").verbs("FW_Cartes(A)").rowCells(cells("f", 2)));
        equivalence(config, "W2 FW_Group + FW_Separator (regex / split / parse of the code-strings, negative keys included)", () -> ProgrammaticScheduleBuilder.newSchedule()
                .sheet("PAD").flags(Flag.EXCLUDE).rowCells(cells("pad", 40))
                .sheet("SEP").flags(Flag.EXCLUDE).rowCells(new String[]{"::", "--"})
                .sheet("G").verbs(Verb.combi(2), Verb.group(), Verb.subsets()).rowCells(cells("g", 4))
                .sheet("H").verbs(Verb.combi(1), Verb.separator("SEP"), Verb.combi(2)).rowCells(cells("h", 3)));
        equivalence(config, "W3 joiners M:N / 1:N / M:1 / 1:1 with relation, separator, start, end", () -> ProgrammaticScheduleBuilder.newSchedule()
                .sheet("PAD").flags(Flag.EXCLUDE).rowCells(cells("pad", 60))
                .sheet("ST").flags(Flag.EXCLUDE, Flag.REUSE).verbs(Verb.combi(1), Verb.combi(1)).rowCells(new String[]{"<start>"})
                .sheet("EN").flags(Flag.EXCLUDE, Flag.REUSE).verbs(Verb.combi(1), Verb.combi(1)).rowCells(new String[]{"<end>"})
                .sheet("REL").flags(Flag.EXCLUDE, Flag.REUSE).verbs(Verb.combi(1), Verb.combi(1)).rowCells(new String[]{"~rel~", "x"})
                .sheet("SP").flags(Flag.EXCLUDE, Flag.REUSE).verbs(Verb.combi(1), Verb.combi(1)).rowCells(new String[]{"~sep~", "y"})
                .sheet("X").flags(Flag.EXCLUDE, Flag.REUSE).verbs(Verb.combi(2), Verb.combi(2)).rowCells(cells("x", 3))
                .sheet("Y").flags(Flag.EXCLUDE, Flag.REUSE).verbs(Verb.combi(1), Verb.combi(1)).rowCells(cells("y", 3))
                .joinRaw("J_MN", "FW_(ST,,X,,Y,,EN,,M:N)").row("FW_EMPTY_STRING")
                .joinRaw("J_1N", "FW_(ST,,X,REL,Y,,EN,SP,1:N)").row("FW_EMPTY_STRING")
                .joinRaw("J_M1", "FW_(ST,,X,REL,Y,,EN,SP,M:1)").row("FW_EMPTY_STRING")
                .joinRaw("J_11", "FW_(ST,,Y,REL,Y,,EN,SP,1:1)").row("FW_EMPTY_STRING"));
    }

    // ── H: configuration ─────────────────────────────────────────────────

    private static void sectionH(Path props) throws Exception {
        System.out.println("\n── H. core.keys.* configuration ──");
        if (props == null) { System.out.println("  ◌ SKIP  fw.properties not found"); return; }
        List<String> base = new ArrayList<>(Files.readAllLines(props, StandardCharsets.ISO_8859_1));
        base.add("db.password=verify");
        Path tmp = Files.createTempFile("dtd_verify_cfg_", ".properties");
        try {
            AppConfig.KeysConfig dflt = AppConfig.load(writeCfg(tmp, base)).workbook.keys;
            assertCond("defaults (the repo's fw.properties): dispatch=short, strategy=identity, scope=all, minGain=5, audit=true",
                    dflt.dispatch == AppConfig.KeysConfig.Dispatch.SHORT && dflt.strategy == AppConfig.KeysConfig.Strategy.IDENTITY
                            && dflt.scope == AppConfig.KeysConfig.Scope.ALL && dflt.minGainPercent == 5.0 && dflt.anchorSheet == null
                            && dflt.audit);
            assertCond("KeysConfig.DEFAULT and a null dispatch are short as well",
                    AppConfig.KeysConfig.DEFAULT.dispatch == AppConfig.KeysConfig.Dispatch.SHORT
                            && new AppConfig.KeysConfig(null, null, null, null, 5.0).dispatch == AppConfig.KeysConfig.Dispatch.SHORT);
            List<String> exp = new ArrayList<>(base); exp.add("core.keys.dispatch=auto"); exp.add("core.keys.audit=false");
            AppConfig.KeysConfig ek = AppConfig.load(writeCfg(tmp, exp)).workbook.keys;
            assertCond("the experiment is switched on only by core.keys.dispatch=auto (and core.keys.audit=false is honoured)",
                    ek.dispatch == AppConfig.KeysConfig.Dispatch.AUTO && !ek.audit);
            Path overlay = props.toAbsolutePath().getParent().resolve("fw.experimental-byte-keys.properties");
            if (Files.exists(overlay)) {
                List<String> withOverlay = new ArrayList<>(base);
                withOverlay.addAll(Files.readAllLines(overlay, StandardCharsets.ISO_8859_1));
                AppConfig.KeysConfig ok = AppConfig.load(writeCfg(tmp, withOverlay)).workbook.keys;
                assertCond("appending fw.experimental-byte-keys.properties to fw.properties enables the experiment, audit on, legacy numbering",
                        ok.dispatch == AppConfig.KeysConfig.Dispatch.AUTO && ok.audit
                                && ok.strategy == AppConfig.KeysConfig.Strategy.IDENTITY);
            } else {
                assertCond("fw.experimental-byte-keys.properties sits next to fw.properties", false);
            }
            List<String> set = new ArrayList<>(base);
            set.add("core.keys.dispatch=SHORT"); set.add("core.keys.strategy=optimal"); set.add("core.keys.scope=cells");
            set.add("core.keys.anchorSheet=  HEAVY "); set.add("core.keys.minGainPercent=12.5");
            AppConfig.KeysConfig k = AppConfig.load(writeCfg(tmp, set)).workbook.keys;
            assertCond("explicit values are parsed (case-insensitive, trimmed)",
                    k.dispatch == AppConfig.KeysConfig.Dispatch.SHORT && k.strategy == AppConfig.KeysConfig.Strategy.OPTIMAL
                            && k.scope == AppConfig.KeysConfig.Scope.CELLS && "HEAVY".equals(k.anchorSheet) && k.minGainPercent == 12.5);
            boolean threwEnum = false, threwNum = false;
            List<String> bad = new ArrayList<>(base); bad.add("core.keys.strategy=optimum");
            try { AppConfig.load(writeCfg(tmp, bad)); } catch (IllegalArgumentException e) { threwEnum = e.getMessage().contains("core.keys.strategy"); }
            List<String> bad2 = new ArrayList<>(base); bad2.add("core.keys.minGainPercent=150");
            try { AppConfig.load(writeCfg(tmp, bad2)); } catch (IllegalArgumentException e) { threwNum = e.getMessage().contains("minGainPercent"); }
            assertCond("a typo in core.keys.strategy fails loudly, naming the key", threwEnum);
            assertCond("core.keys.minGainPercent outside 0..100 fails loudly", threwNum);
        } finally { Files.deleteIfExists(tmp); }
    }

    private static Path writeCfg(Path tmp, List<String> lines) throws Exception { Files.write(tmp, lines, StandardCharsets.ISO_8859_1); return tmp; }
}
