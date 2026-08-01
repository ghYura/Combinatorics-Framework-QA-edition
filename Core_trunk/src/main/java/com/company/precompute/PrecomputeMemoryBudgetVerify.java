package com.company.precompute;

import com.company.SeqParser;
import com.company.config.AppConfig;
import com.company.excel.Flag;
import com.company.excel.ParsedWorkbook;
import com.company.excel.ProgrammaticScheduleBuilder;
import com.company.excel.XlsxScheduleParser;

import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

/**
 * Iter4.2 verification — runs {@link PrecomputeMemoryBudget#estimate} against
 * a small set of fixtures so the report shape can be inspected and the
 * AUTO decision logic exercised across "fits" and "doesn't fit" regimes.
 *
 * <p>Three fixtures:</p>
 * <ol>
 *   <li>tiny — single FW_Combi(2) over 5 cells (expect JAVA decision).</li>
 *   <li>medium — couple of FW_Cartes + FW_Combi chains (expect JAVA).</li>
 *   <li>heavy — FW_Subsets over wide source + multiple optional sheets
 *       (expect DB because the cartesian explodes).</li>
 * </ol>
 *
 * <p>Run via:
 * {@code java -cp target/classes:$(cat /tmp/cp.txt) com.company.precompute.PrecomputeMemoryBudgetVerify}</p>
 */
public final class PrecomputeMemoryBudgetVerify {

    private PrecomputeMemoryBudgetVerify() {}

    public static void main(String[] args) throws Exception {
        Path tinyXlsx   = Path.of("tmp_verify_iter4/budget_tiny.xlsx");
        Path mediumXlsx = Path.of("tmp_verify_iter4/budget_medium.xlsx");
        Path heavyXlsx  = Path.of("tmp_verify_iter4/budget_heavy.xlsx");

        buildTinyFixture(tinyXlsx);
        buildMediumFixture(mediumXlsx);
        buildHeavyFixture(heavyXlsx);

        AppConfig cfg = loadDefaultConfig();

        System.out.println("══════════════════════════════════════════════════════");
        System.out.println("FIXTURE 1: tiny (expect JAVA decision)");
        runOne(tinyXlsx, cfg, PrecomputeMemoryBudget.Mode.AUTO);

        System.out.println("\n══════════════════════════════════════════════════════");
        System.out.println("FIXTURE 2: medium (expect JAVA decision)");
        runOne(mediumXlsx, cfg, PrecomputeMemoryBudget.Mode.AUTO);

        System.out.println("\n══════════════════════════════════════════════════════");
        System.out.println("FIXTURE 3: heavy (expect DB decision)");
        runOne(heavyXlsx, cfg, PrecomputeMemoryBudget.Mode.AUTO);

        System.out.println("\n══════════════════════════════════════════════════════");
        System.out.println("FIXTURE 3 with FORCE_JAVA (override; estimate ignored)");
        runOne(heavyXlsx, cfg, PrecomputeMemoryBudget.Mode.FORCE_JAVA);

        System.out.println("\n══════════════════════════════════════════════════════");
        System.out.println("FIXTURE 1 with FORCE_DB (override; estimate ignored)");
        runOne(tinyXlsx, cfg, PrecomputeMemoryBudget.Mode.FORCE_DB);
    }

    private static void runOne(Path xlsx, AppConfig cfg, PrecomputeMemoryBudget.Mode mode) throws Exception {
        var wbCfg  = new AppConfig.WorkbookConfig(false, false, "FW_VIRTUAL_");
        var seqCfg = new AppConfig.SeqConfig(false, false, false);
        ParsedWorkbook pw = new XlsxScheduleParser().parse(xlsx, wbCfg);
        SeqParser.SeqParseResult seq = SeqParser.parse(pw, pw.sheetData, seqCfg);
        PrecomputeMemoryBudget.Report report = PrecomputeMemoryBudget.estimate(seq, pw, cfg, mode);
        System.out.println(report.render());
    }

    // ── fixtures ────────────────────────────────────────────────────────

    private static void buildTinyFixture(Path out) throws Exception {
        Files.createDirectories(out.getParent());
        XSSFWorkbook wb = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("A").flags(Flag.REUSE).verb("FW_Combi(2)").rows("a", "b", "c", "d", "e")
                .buildWorkbook();
        try (var os = Files.newOutputStream(out)) { wb.write(os); wb.close(); }
    }

    private static void buildMediumFixture(Path out) throws Exception {
        Files.createDirectories(out.getParent());
        XSSFWorkbook wb = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("A").flags(Flag.REUSE).verb("FW_Combi(3)").rows("a1","a2","a3","a4","a5","a6","a7","a8")
                .sheet("B").flags(Flag.REUSE).verb("FW_Permut").rows("b1","b2","b3","b4")
                .sheet("C").flags(Flag.REUSE).verb("FW_Subsets").rows("c1","c2","c3","c4","c5")
                .buildWorkbook();
        try (var os = Files.newOutputStream(out)) { wb.write(os); wb.close(); }
    }

    private static void buildHeavyFixture(Path out) throws Exception {
        Files.createDirectories(out.getParent());
        // 12-row source × FW_Subsets = 2^12 = 4096.  Then ×6 mandatory sheets of
        // size ~10 each → product approaches limitVar; fw_final estimate dominates.
        var b = ProgrammaticScheduleBuilder.newSchedule();
        b = b.sheet("H_BIG").flags(Flag.REUSE).verb("FW_Subsets")
                .rows("h0","h1","h2","h3","h4","h5","h6","h7","h8","h9","h10","h11").and();
        for (int s = 0; s < 5; s++) {
            String name = "H_M" + s;
            String[] rows = new String[10];
            for (int i = 0; i < 10; i++) rows[i] = name + "_v" + i;
            b = b.sheet(name).flags(Flag.REUSE).verb("FW_Combi(2)").rows(rows).and();
        }
        // A few optional sheets so fw_opt<i> estimates fire too.
        for (int s = 0; s < 4; s++) {
            String name = "H_O" + s;
            String[] rows = new String[8];
            for (int i = 0; i < 8; i++) rows[i] = name + "_v" + i;
            b = b.sheet(name).flags(Flag.OPTIONAL, Flag.REUSE).verb("FW_Combi(3)").rows(rows).and();
        }
        try (XSSFWorkbook wb = b.buildWorkbook();
             OutputStream os = Files.newOutputStream(out)) { wb.write(os); }
    }

    /** Load fw.properties from project root so config matches real defaults. */
    private static AppConfig loadDefaultConfig() throws Exception {
        Path props = Path.of("fw.properties");
        if (!Files.isRegularFile(props)) {
            // Synthesize a minimal config for tests where fw.properties isn't present.
            Properties p = new Properties();
            p.setProperty("db.user", "x"); p.setProperty("db.password", "x");
            p.setProperty("db.host", "localhost"); p.setProperty("db.name", "x");
            p.setProperty("db.port", "5433");
            p.setProperty("excel.file", "irrelevant.xlsx");
            p.setProperty("core.limitVarGivenLessThan", "9223372036854775799");
            p.setProperty("core.counter4copyMax", "100000");
            p.setProperty("core.sleepTimeAfterDisconnect4copyDB", "1000");
            p.setProperty("core.sleepTimeCheckFinalFilled", "1000");
            p.setProperty("core.optional.limitOptionalSheetsCombosMax", "2147483639");
            p.setProperty("core.optional.numberOptionalSheetCombosMultithreadStartsAfter", "3");
            p.setProperty("core.optional.includeOptionalCombiPairsToDBCSVList", "1,2,3,4");
            p.setProperty("delay_holdCleanupAndEraseExcludedTablesThread", "0");
            p.setProperty("delay_holdMockupPreparationOfSqlFinalTableThread", "0");
            p.setProperty("delay_holdFnlThread", "0");
            p.setProperty("delay_holdOptsThread", "0");
            Path tmp = Files.createTempFile("synthetic_fw_", ".properties");
            try (var os = Files.newOutputStream(tmp)) { p.store(os, "synthetic"); }
            return AppConfig.load(tmp);
        }
        return AppConfig.load(props);
    }
}
