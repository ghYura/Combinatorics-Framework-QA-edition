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
 * Tier-2 win 2.4 — equivalence verifier for {@link ProgrammaticScheduleBuilder}.
 *
 * Pins the load-bearing invariant: a scenario expressed via the fluent Java
 * DSL produces a {@link ParsedWorkbook} cell-for-cell identical to the same
 * scenario expressed as JSON ({@link JsonScheduleParser}) and as XLSX
 * ({@link XlsxScheduleParser}).  Three input formats, one canonical model.
 *
 * Path:
 *   <ol>
 *     <li>Build the {@code test_e2e_metric} scenario via the fluent DSL.</li>
 *     <li>Parse the on-disk {@code test_e2e_metric.json} via JsonScheduleParser.</li>
 *     <li>Compare ParsedWorkbook.stringSheetHM: same sheet name set, same
 *         insertion order, identical row counts, identical cell strings.</li>
 *   </ol>
 *
 * Run via {@code run-tests.sh} on this module, or ad-hoc:
 * {@code java -cp target/migrated-project-*-shaded.jar com.company.excel.BuilderEquivalenceVerify}
 */
public final class BuilderEquivalenceVerify {
    private BuilderEquivalenceVerify() {}

    private static final String DEFAULT_JSON_PATH =
            System.getenv().getOrDefault("CORE_EQUIVALENCE_JSON", "test_e2e_metric.json");

    public static void main(String[] args) throws Exception {
        String jsonPath = (args.length > 0) ? args[0] : DEFAULT_JSON_PATH;
        Path json = Path.of(jsonPath);
        if (!Files.isRegularFile(json)) {
            System.out.println("◌ SKIP  scenario JSON not present at " + jsonPath
                    + " — pass an explicit path as arg #1 to run this verifier");
            return;
        }

        // Workbook config matching the brief's defaults (no auto-generation needed
        // here — the builder/JSON both emit every sheet the engine looks for).
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");

        System.out.println("── Build same scenario via fluent DSL ──");
        ParsedWorkbook viaBuilder = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("HEAD").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .row("scenario=demo")
                .sheet("COST").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .rows(" id=1 cost=0.10", " id=2 cost=0.30", " id=3 cost=0.50")
                .sheet("LAT").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .rows(" latency=10ms", " latency=30ms", " latency=80ms")
                .sheet("TAIL").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .row(" status=ok")
                .join("ROW", JoinSpec.from("HEAD").via("COST", "LAT")
                                     .to("TAIL").as(Multiplicity.M_N))
                    .row("FW_EMPTY_STRING")
                .runMeFirstOnce(
                        "class RunMeFirstOnce { public static String FW_ARGS;"
                      + " public static void main(String[] args){ FW_ARGS = \"\"; "
                      + "System.out.println(\"json-driven scenario\"); } }")
                .arguments("noargs")
                .customVar(2, "FWCUSTOMVAR=2 nominal")
                .build(wbCfg);

        System.out.println("── Parse same scenario via JsonScheduleParser ──");
        ParsedWorkbook viaJson = new JsonScheduleParser().parse(json, wbCfg);

        int failed = 0;
        failed += compare(viaBuilder, viaJson);

        // Spot-check the joiner row: column 4 should literally be the FW_(...) form.
        failed += assertCond(
                "FW_Seq joiner expression matches expected canonical 8-comma form",
                getCellString(viaBuilder.stringSheetHM.get("FW_Seq"), 4, 3)
                        .equals("FW_(HEAD,,COST,,LAT,,TAIL,,M:N)"));

        System.out.println();
        if (failed == 0) System.out.println("✅ BUILDER ↔ JSON EQUIVALENCE VERIFIED");
        else { System.out.println("❌ " + failed + " EQUIVALENCE CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── comparison harness ──────────────────────────────────────────────

    private static int compare(ParsedWorkbook a, ParsedWorkbook b) {
        int f = 0;
        // Control sheets — keyed by string name in stringSheetHM.
        Set<String> aNames = new LinkedHashSet<>(a.stringSheetHM.keySet());
        Set<String> bNames = new LinkedHashSet<>(b.stringSheetHM.keySet());
        f += assertCond("control sheet name set is identical", aNames.equals(bNames));
        f += assertCond("control sheet insertion order is identical",
                aNames.toString().equals(bNames.toString()));
        for (String name : aNames) {
            f += compareSheets("control '" + name + "'",
                    a.stringSheetHM.get(name), b.stringSheetHM.get(name));
        }

        // Data sheets — keyed by Short in shortSheetHM, with name lookup via
        // shortStringSheetKey2SheetNameHM.  Compared in Short-key order,
        // which mirrors workbook insertion order on both sides.
        Set<String> aData = new LinkedHashSet<>();
        Set<String> bData = new LinkedHashSet<>();
        for (var e : a.shortSheetHM.entrySet())
            aData.add(a.shortStringSheetKey2SheetNameHM.get(e.getKey()));
        for (var e : b.shortSheetHM.entrySet())
            bData.add(b.shortStringSheetKey2SheetNameHM.get(e.getKey()));
        f += assertCond("data sheet name set is identical (" + aData + ")",
                aData.equals(bData));
        f += assertCond("data sheet insertion order is identical",
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
        int rowsA = lastRowNumOrZero(sa);
        int rowsB = lastRowNumOrZero(sb);
        f += assertCond(label + ": row count match (" + rowsA + " vs " + rowsB + ")",
                rowsA == rowsB);
        for (int r = 0; r <= Math.max(rowsA, rowsB); r++) {
            Row ra = sa == null ? null : sa.getRow(r);
            Row rb = sb == null ? null : sb.getRow(r);
            if (ra == null && rb == null) continue;
            if (ra == null || rb == null) {
                f += assertCond(label + ": row #" + r + " presence mismatch", false);
                continue;
            }
            short lastA = ra.getLastCellNum();
            short lastB = rb.getLastCellNum();
            int wide = Math.max(lastA, lastB);
            for (int c = 0; c < wide; c++) {
                String va = getCellString(sa, r, c);
                String vb = getCellString(sb, r, c);
                if (!va.equals(vb)) {
                    f += assertCond(label + " row #" + r + " col #" + c
                            + ": '" + va + "' vs '" + vb + "'", false);
                }
            }
        }
        return f;
    }

    private static int lastRowNumOrZero(Sheet s) {
        return s == null ? 0 : s.getLastRowNum();
    }

    private static String getCellString(Sheet s, int rowIdx, int colIdx) {
        if (s == null) return "";
        Row r = s.getRow(rowIdx);
        if (r == null) return "";
        Cell c = r.getCell(colIdx);
        if (c == null) return "";
        return new DataFormatter(Locale.ROOT).formatCellValue(c);
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
