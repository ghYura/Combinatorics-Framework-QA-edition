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

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Tier-4 win 4.4 (Phase 2) — universal input parity.
 *
 * The {@code test_e2e_metric} scenario is materialised three additional
 * ways — inline YAML, inline TOML, and via the fluent
 * {@link ProgrammaticScheduleBuilder} — and the resulting
 * {@link ParsedWorkbook} for each is compared cell-for-cell against the
 * JSON-driven canonical form (built from the same YAML, converted to JSON
 * via {@link YamlScheduleParser#yamlToJson}).
 *
 * That pins the load-bearing invariant the brief calls out (universal input
 * adapter, Phase 2): one canonical model, four equivalent surfaces.
 */
public final class UniversalInputParityVerify {
    private UniversalInputParityVerify() {}

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

    private static final String SCENARIO_TOML =
        "[sheets]\n"
      + "FW_Seq = [\n"
      + "  [\"HEAD\", \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"],\n"
      + "  [\"COST\", \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"],\n"
      + "  [\"LAT\",  \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"],\n"
      + "  [\"TAIL\", \"FW_Exclude\", \"FW_Reuse\", \"FW_Combi(1)\", \"FW_Combi(1)\"],\n"
      + "  [\"ROW\", null, null, \"FW_(HEAD,,COST,,LAT,,TAIL,,M:N)\"],\n"
      + "]\n"
      + "FW_SheetNames = [\n"
      + "  [\"HEAD\", \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"],\n"
      + "  [\"COST\", \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"],\n"
      + "  [\"LAT\",  \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"],\n"
      + "  [\"TAIL\", \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"],\n"
      + "  [\"ROW\",  \"FW_EMPTY_STRING\", \"FW_EMPTY_STRING\"],\n"
      + "]\n"
      + "FW_RunMeFirstOnce = [[\"class RunMeFirstOnce { public static String FW_ARGS;"
      +                          " public static void main(String[] args){ FW_ARGS = \\\"\\\"; } }\"]]\n"
      + "FW_Arguments  = [[\"noargs\"]]\n"
      + "FW_CUSTOM_VAR = [[2, \"FWCUSTOMVAR=2 nominal\"]]\n"
      + "HEAD = [[\"scenario=demo\"]]\n"
      + "COST = [\n"
      + "  [\" id=1 cost=0.10\"],\n"
      + "  [\" id=2 cost=0.30\"],\n"
      + "  [\" id=3 cost=0.50\"],\n"
      + "]\n"
      + "LAT = [\n"
      + "  [\" latency=10ms\"],\n"
      + "  [\" latency=30ms\"],\n"
      + "  [\" latency=80ms\"],\n"
      + "]\n"
      + "TAIL = [[\" status=ok\"]]\n"
      + "ROW  = [[\"FW_EMPTY_STRING\"]]\n";

    public static void main(String[] args) throws Exception {
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");

        System.out.println("── Parse scenario via YamlScheduleParser ──");
        ParsedWorkbook yamlPw = new YamlScheduleParser().parseYaml(SCENARIO_YAML, wbCfg, "yaml:inline");

        System.out.println("── Parse scenario via TomlScheduleParser ──");
        ParsedWorkbook tomlPw = new TomlScheduleParser().parseToml(SCENARIO_TOML, wbCfg, "toml:inline");

        System.out.println("── Parse same scenario via JsonScheduleParser (JSON derived from YAML) ──");
        String generatedJson = new YamlScheduleParser().yamlToJson(SCENARIO_YAML);
        ParsedWorkbook jsonPw = new JsonScheduleParser().parseJson(generatedJson, wbCfg, "json:from-yaml");

        System.out.println("── Build scenario via ProgrammaticScheduleBuilder ──");
        ParsedWorkbook builderPw = ProgrammaticScheduleBuilder.newSchedule()
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
                .runMeFirstOnce("class RunMeFirstOnce { public static String FW_ARGS;"
                              + " public static void main(String[] args){ FW_ARGS = \"\"; } }")
                .arguments("noargs")
                .customVar(2, "FWCUSTOMVAR=2 nominal")
                .build(wbCfg);

        int failed = 0;
        failed += compare("YAML  ↔ JSON   ", yamlPw,    jsonPw);
        failed += compare("TOML  ↔ JSON   ", tomlPw,    jsonPw);
        failed += compare("Build ↔ JSON   ", builderPw, jsonPw);
        // Transitive sanity:
        failed += compare("YAML  ↔ TOML   ", yamlPw,    tomlPw);
        failed += compare("Build ↔ YAML   ", builderPw, yamlPw);

        System.out.println();
        if (failed == 0) System.out.println("✅ ALL FOUR INPUT FORMATS PRODUCE IDENTICAL ParsedWorkbook");
        else { System.out.println("❌ " + failed + " PARITY CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── pairwise cell-for-cell comparison (mirrors BuilderEquivalenceVerify) ──

    private static int compare(String label, ParsedWorkbook a, ParsedWorkbook b) {
        int f = 0;
        System.out.println("\n── " + label + " ──");

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
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
