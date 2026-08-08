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

package com.company.combinatorics;

import com.company.SeqParser;
import com.company.config.AppConfig;
import com.company.excel.Flag;
import com.company.excel.ParsedWorkbook;
import com.company.excel.ProgrammaticScheduleBuilder;
import com.company.excel.XlsxScheduleParser;

import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.OutputStream;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;

/**
 * Iter4 step 1 — verify {@link CombinatorialGenerator}'s precomputed
 * {@code rowCount} BigInteger matches the actual {@code stream().count()} for
 * every algorithm path the FW_Seq DSL exercises.  Per-verb rowCount feeds the
 * upcoming precompute-decision module's memory estimator; if rowCount drifts,
 * every Layer-1 decision is built on sand.
 *
 * <p>Scope: SINGLE-VERB math correctness against minimal edge-case data.
 * Compositional verb-chain totals (e.g. FW_Combi → FW_Group → FW_Combi) and
 * brace operand sizes are data-dependent and intentionally NOT covered here
 * — the precompute estimator handles them with pessimistic upper bounds
 * rather than exact prediction.</p>
 *
 * <p>Approach: build a small XLSX fixture programmatically via
 * {@link ProgrammaticScheduleBuilder}, persist it to disk, re-parse it through
 * {@link XlsxScheduleParser} (so the verification runs against the same data
 * shape the real engine sees), and for each sheet instantiate the generator
 * the way {@link com.company.SheetWorker#buildDirectiveGenerator} would.</p>
 *
 * <p>Run via:
 * {@code mvn -q exec:java -Dexec.mainClass=com.company.combinatorics.CombinatorialRowCountVerify}
 * (no DB required — Hibernate addKV calls fail silently and parsing still
 * completes correctly).</p>
 *
 * <p>Side effect: writes {@code tmp_verify_iter4/edge_cases.xlsx} at the
 * project root so the fixture can be inspected manually.</p>
 */
public final class CombinatorialRowCountVerify {

    private CombinatorialRowCountVerify() {}

    /** One edge case.  Inputs intentionally small so {@code stream().count()}
     *  is tractable on every algorithm including FW_PermutR which is n^k. */
    private record Case(String sheet, int srcRows, String verb, long expected, String formula) {}

    private static final List<Case> CASES = List.of(
        // ─── FW_Combi(k) — C(n, k) ──────────────────────────────────────
        new Case("E_COMBI_5_3",   5, "FW_Combi(3)",   10, "C(5,3)"),
        new Case("E_COMBI_5_2",   5, "FW_Combi(2)",   10, "C(5,2)"),
        new Case("E_COMBI_5_0",   5, "FW_Combi(0)",    1, "C(5,0) = empty set"),
        new Case("E_COMBI_5_5",   5, "FW_Combi(5)",    1, "C(5,5) = full set"),
        // ─── FW_CombiR(k) — C(n+k-1, k) ─────────────────────────────────
        new Case("E_COMBIR_4_3",  4, "FW_CombiR(3)",  20, "C(4+3-1, 3) = C(6,3)"),
        new Case("E_COMBIR_3_2",  3, "FW_CombiR(2)",   6, "C(3+2-1, 2) = C(4,2)"),
        // ─── FW_Permut — n! ─────────────────────────────────────────────
        new Case("E_PERMUT_4",    4, "FW_Permut",     24, "4!"),
        new Case("E_PERMUT_5",    5, "FW_Permut",    120, "5!"),
        // ─── FW_PermutR(k) — n^k ────────────────────────────────────────
        new Case("E_PERMUTR_3_2", 3, "FW_PermutR(2)",  9, "3^2"),
        new Case("E_PERMUTR_4_3", 4, "FW_PermutR(3)", 64, "4^3"),
        // ─── FW_Subsets DEFAULT — 2^n ───────────────────────────────────
        new Case("E_SUBSETS_4",   4, "FW_Subsets",    16, "2^4"),
        new Case("E_SUBSETS_5",   5, "FW_Subsets",    32, "2^5"),
        // ─── FW_Subsets modes ──────────────────────────────────────────
        new Case("E_SUBSETS_EXACT_5_2",   5, "FW_Subsets_EXACT(2)",   10, "C(5,2)"),
        new Case("E_SUBSETS_RANGE_5_2_3", 5, "FW_Subsets_RANGE(2,3)", 20, "C(5,2)+C(5,3)"),
        new Case("E_SUBSETS_BEFORE_5_2",  5, "FW_Subsets_BEFORE(2)",   6, "C(5,0)+C(5,1)"),
        new Case("E_SUBSETS_AFTER_5_3",   5, "FW_Subsets_AFTER(3)",    6, "C(5,4)+C(5,5)"),
        new Case("E_SUBSETS_GIVEN_5_1_3", 5, "FW_Subsets_GIVEN(1,3)", 15, "C(5,1)+C(5,3)"),
        // ─── FW_Cartes — |A|×|B|.  Needs a second sheet as RHS operand. ─
        new Case("E_CARTES_3x4",  3, "FW_Cartes(E_CARTES_RHS_4)", 12, "3×4")
    );

    public static void main(String[] args) throws Exception {
        Path fixturePath = Path.of("tmp_verify_iter4/edge_cases.xlsx");
        buildFixture(fixturePath);
        System.out.println("Fixture written: " + fixturePath.toAbsolutePath());
        System.out.println();

        AppConfig.WorkbookConfig wbCfg =
                new AppConfig.WorkbookConfig(false, false, "FW_VIRTUAL_");
        AppConfig.SeqConfig seqCfg =
                new AppConfig.SeqConfig(false, false, false);  // autoPromote OFF

        ParsedWorkbook pw = new XlsxScheduleParser().parse(fixturePath, wbCfg);
        SeqParser.SeqParseResult seq = SeqParser.parse(pw, pw.sheetData, seqCfg);

        int passed = 0, failed = 0;
        for (Case c : CASES) {
            String result = verifyCase(c, pw, seq);
            if (result.startsWith("PASS")) passed++; else failed++;
            System.out.printf("%-38s  %s%n", c.sheet, result);
        }

        // ── standalone cases (paths not reachable via XLSX cell-key indirection) ──
        // Multiset permutations: cell-key counter always issues distinct keys per
        // cell, so the "treatDuplicatesAsIdentical=true" branch of
        // CombinatorialGenerator.permutations() never triggers via a workbook.
        int extraPassed = 0, extraFailed = 0;

        // Case: CombinatorialGenerator.permutations(treatDup=true, par=false)
        {
            List<Short> src = List.of((short) 1, (short) 1, (short) 2, (short) 3);
            var gen = CombinatorialGenerator.permutations(src, true, false);
            long expected = 12;
            long rc = gen.rowCount.longValueExact();
            long sc = gen.stream().count();
            boolean ok = (rc == expected) && (sc == expected);
            if (ok) extraPassed++; else extraFailed++;
            System.out.printf("%-38s  %s  [4!/2! multiset, par=false]%n",
                    "STANDALONE_PERMUT_DUP_SEQ",
                    ok ? String.format("PASS  rowCount=%d stream=%d", rc, sc)
                       : String.format("FAIL  expected=%d rowCount=%d stream=%d", expected, rc, sc));
        }

        // Case: same input, parallel=true (uses MultiPermutationGenerator)
        {
            List<Short> src = List.of((short) 1, (short) 1, (short) 2, (short) 3);
            var gen = CombinatorialGenerator.permutations(src, true, true);
            long expected = 12;
            long rc = gen.rowCount.longValueExact();
            long sc = gen.stream().count();
            boolean ok = (rc == expected) && (sc == expected);
            if (ok) extraPassed++; else extraFailed++;
            System.out.printf("%-38s  %s  [4!/2! multiset, par=true]%n",
                    "STANDALONE_PERMUT_DUP_PAR",
                    ok ? String.format("PASS  rowCount=%d stream=%d", rc, sc)
                       : String.format("FAIL  expected=%d rowCount=%d stream=%d", expected, rc, sc));
        }

        // Diagnostic A: call dpaukov directly, bypass CombinatorialGenerator
        {
            var dp = org.paukov.combinatorics3.Generator
                    .permutation(List.of("a", "a", "b", "c"))
                    .simple(org.paukov.combinatorics3.PermutationGenerator
                            .TreatDuplicatesAs.IDENTICAL);
            long sc = dp.stream().count();
            System.out.printf("%-38s  count=%d  (expected 12 if IDENTICAL dedups)%n",
                    "DIAG_DPAUKOV_simple(IDENTICAL)", sc);
        }

        // Diagnostic B: call ghYura MultiPermutationGenerator directly
        {
            var gh = new org.ghYura.combinatorics3parallel.MultiPermutationGenerator<>(
                    List.of("a", "a", "b", "c"));
            long counted = gh.getNumberOfGeneratedElements();
            long streamed = gh.stream().count();
            System.out.printf("%-38s  countMethod=%d  stream=%d%n",
                    "DIAG_GHYURA_MultiPermutation", counted, streamed);
        }

        System.out.println();
        System.out.println("──────────────────────────────────────────────────────────────");
        System.out.printf("Summary: PASS=%d  FAIL=%d  (TOTAL=%d)%n",
                passed + extraPassed, failed + extraFailed,
                CASES.size() + extraPassed + extraFailed);
        if (failed + extraFailed > 0) System.exit(1);
    }

    /** Build the edge-case workbook via {@link ProgrammaticScheduleBuilder}
     *  and serialize to disk so the fixture survives runs and can be inspected. */
    private static void buildFixture(Path out) throws Exception {
        Files.createDirectories(out.getParent());

        ProgrammaticScheduleBuilder b = ProgrammaticScheduleBuilder.newSchedule();
        // RHS operand for the Cartes case — added first so the lookup succeeds.
        b = b.sheet("E_CARTES_RHS_4")
                .flags(Flag.EXCLUDE, Flag.REUSE)
                .verb("FW_Combi(1)")
                .rows("rhs_a", "rhs_b", "rhs_c", "rhs_d")
                .and();

        for (Case c : CASES) {
            if (c.sheet.equals("E_CARTES_RHS_4")) continue;
            String[] rows = new String[c.srcRows];
            for (int i = 0; i < c.srcRows; i++) rows[i] = c.sheet + "_v" + i;
            b = b.sheet(c.sheet)
                    .flags(Flag.EXCLUDE, Flag.REUSE)
                    .verb(c.verb)
                    .rows(rows)
                    .and();
        }

        try (XSSFWorkbook wb = b.buildWorkbook();
             OutputStream os = Files.newOutputStream(out)) {
            wb.write(os);
        }
    }

    private static String verifyCase(Case c, ParsedWorkbook pw, SeqParser.SeqParseResult seq) {
        Short key = pw.stringShortSheetName2SheetKeyHM.get(c.sheet);
        if (key == null) return "FAIL  sheet not registered in workbook";

        List<Short> srcList = pw.sheetData.get(key);
        if (srcList == null) return "FAIL  sheetData missing for key=" + key;
        if (srcList.size() != c.srcRows) {
            return String.format("FAIL  src size mismatch: expected %d, got %d",
                    c.srcRows, srcList.size());
        }

        try {
            CombinatorialGenerator<Short> gen = buildGenerator(c.verb, srcList, pw);
            BigInteger expected = BigInteger.valueOf(c.expected);
            BigInteger rowCount = gen.rowCount;
            long streamCount = gen.stream().count();

            boolean rc_eq_exp = expected.equals(rowCount);
            boolean st_eq_rc  = (rowCount.bitLength() < 63
                                  && rowCount.longValueExact() == streamCount);
            boolean st_eq_exp = (c.expected == streamCount);

            if (rc_eq_exp && st_eq_rc) {
                return String.format("PASS  rowCount=%d stream=%d  [%s]",
                        rowCount, streamCount, c.formula);
            }
            return String.format(
                    "FAIL  expected=%d  rowCount=%d  stream=%d  "
                    + "(rc-vs-expected:%s, stream-vs-rc:%s, stream-vs-expected:%s)  [%s]",
                    c.expected, rowCount, streamCount,
                    rc_eq_exp ? "OK" : "BAD",
                    st_eq_rc  ? "OK" : "BAD",
                    st_eq_exp ? "OK" : "BAD",
                    c.formula);
        } catch (Exception e) {
            return "ERROR  " + e.getClass().getSimpleName() + ": " + e.getMessage();
        }
    }

    /** Replicates the verb-to-generator mapping in
     *  {@link com.company.SheetWorker#buildDirectiveGenerator}, with parallel=false
     *  for deterministic {@code stream().count()}. */
    private static CombinatorialGenerator<Short> buildGenerator(
            String directive, List<Short> src, ParsedWorkbook pw) {

        String algoType = resolveAlgoType(directive);
        int m = resolveM(directive, algoType);
        boolean allowDuplicates = directive.endsWith(
                "FW_Permut(PermutationGenerator.TreatDuplicatesAs.IDENTICAL)");
        boolean isCartesFirst = directive.matches("FW_Cartes(?i)_first\\(.*\\)");
        boolean par = false;

        CombinatorialGenerator.SubsetMode subsetMode =
                CombinatorialGenerator.SubsetMode.DEFAULT;
        int[] subsetParams = new int[]{};
        if (algoType.equals("FW_Subsets") && directive.contains("_")) {
            String modeStr = directive.replaceAll("FW_Subsets_|\\s+|[,]+|\\d+|\\(|\\)", "");
            try {
                subsetMode = CombinatorialGenerator.SubsetMode.valueOf(modeStr.toUpperCase());
            } catch (IllegalArgumentException ignored) {}
            subsetParams = Arrays.stream(directive.replaceAll("[^\\d,]+", "").split(","))
                    .filter(s -> !s.isEmpty())
                    .mapToInt(Integer::parseInt)
                    .toArray();
        }

        List<Short> src2 = null;
        if (algoType.equals("FW_Cartes")) {
            String inner = directive.substring(
                    directive.indexOf('(') + 1, directive.lastIndexOf(')'));
            Short otherKey = pw.stringShortSheetName2SheetKeyHM.get(inner);
            if (otherKey != null) src2 = pw.sheetData.get(otherKey);
        }

        switch (algoType) {
            case "FW_Combi":
                return CombinatorialGenerator.combinations(src, m, par);
            case "FW_CombiR":
                return CombinatorialGenerator.combinationsWithRepetitions(src, m, par);
            case "FW_Permut":
                return CombinatorialGenerator.permutations(src, allowDuplicates, par);
            case "FW_PermutR":
                return CombinatorialGenerator.permutationsWithRepetitions(src, m, par);
            case "FW_Subsets":
                return CombinatorialGenerator.subsets(src, subsetMode, subsetParams, par);
            case "FW_Cartes": {
                List<Short> a = isCartesFirst ? (src2 != null ? src2 : List.of()) : src;
                List<Short> bL = isCartesFirst ? src : (src2 != null ? src2 : List.of());
                return CombinatorialGenerator.cartesian(a, bL, par);
            }
            default:
                throw new IllegalArgumentException("Unknown algo: " + algoType);
        }
    }

    private static String resolveAlgoType(String directive) {
        if (directive.startsWith("FW_CombiR"))  return "FW_CombiR";
        if (directive.startsWith("FW_Combi"))   return "FW_Combi";
        if (directive.startsWith("FW_PermutR")) return "FW_PermutR";
        if (directive.startsWith("FW_Permut"))  return "FW_Permut";
        if (directive.startsWith("FW_Subsets")) return "FW_Subsets";
        if (directive.startsWith("FW_Cartes"))  return "FW_Cartes";
        return "UNKNOWN";
    }

    private static int resolveM(String directive, String algoType) {
        if (directive.endsWith(algoType) || directive.endsWith(algoType + "()")) return 1;
        var m = java.util.regex.Pattern.compile("\\((\\d+)\\)").matcher(directive);
        if (m.find()) {
            try { return Integer.parseInt(m.group(1)); }
            catch (NumberFormatException ignored) {}
        }
        return 1;
    }
}
