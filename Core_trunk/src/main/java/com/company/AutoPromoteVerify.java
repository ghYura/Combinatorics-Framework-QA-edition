package com.company;

import com.company.config.AppConfig;
import com.company.excel.Flag;
import com.company.excel.JoinSpec;
import com.company.excel.Multiplicity;
import com.company.excel.ParsedWorkbook;
import com.company.excel.ProgrammaticScheduleBuilder;
import com.company.excel.Verb;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Verifier for Tier-0 bug fix 0.6 — auto-promotion of single combo-rule verbs.
 *
 * Scenarios covered:
 *   A. Single-verb entity row → after SeqParser, seqList has TWO identical verbs.
 *   B. Already-dual entity row → unchanged (idempotent).
 *   C. Joiner row containing FW_(...) → unchanged.
 *   D. Single FW_Cartes (non-combo verb) → unchanged.
 *   E. autoPromoteSingleVerb=false → scenario A stays single.
 *
 * Why we check {@code mapShKey2seqList}: that's the per-row directive vector
 * the downstream pipeline ({@code SheetWorker}, {@code FinalTableAssembler})
 * consumes.  Without dual verbs, only {@code fw_<key>} gets populated and
 * joiners read {@code fw2_<key>} → 0 rows.
 */
public final class AutoPromoteVerify {
    private AutoPromoteVerify() {}

    public static void main(String[] args) throws Exception {
        AppConfig.WorkbookConfig wbCfg = new AppConfig.WorkbookConfig(false, false, "FW_virtual_");
        AppConfig.SeqConfig seqOn  = new AppConfig.SeqConfig(false, false, true);
        AppConfig.SeqConfig seqOff = new AppConfig.SeqConfig(false, false, false);

        int failed = 0;

        // ── A: single-verb row gets promoted ─────────────────────────────
        System.out.println("── A. Single FW_Combi(1) → promoted to dual ──");
        ParsedWorkbook a = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("HEAD").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1))                              // single!
                    .row("scenario=demo")
                .sheet("TAIL").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .row(" status=ok")
                .join("ROW", JoinSpec.from("HEAD").to("TAIL").as(Multiplicity.M_N))
                    .row("FW_EMPTY_STRING")
                .build(wbCfg);
        SeqParser.SeqParseResult ra = SeqParser.parse(a, new LinkedHashMap<>(), seqOn);
        failed += assertCond("A: HEAD seqList now has 2 verbs",
                rowVerbCount(ra, a, "HEAD") == 2);
        failed += assertCond("A: HEAD seqList both verbs are FW_Combi(1)",
                rowAllEqual(ra, a, "HEAD", "FW_Combi(1)"));
        failed += assertCond("A: TAIL seqList unchanged (still 2)",
                rowVerbCount(ra, a, "TAIL") == 2);

        // ── B: already-dual is idempotent ───────────────────────────────
        System.out.println("\n── B. Already-dual row is idempotent ──");
        ParsedWorkbook b = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("HEAD").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))               // dual
                    .row("scenario=demo")
                .sheet("TAIL").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .row(" status=ok")
                .join("ROW", JoinSpec.from("HEAD").to("TAIL").as(Multiplicity.M_N))
                    .row("FW_EMPTY_STRING")
                .build(wbCfg);
        SeqParser.SeqParseResult rb = SeqParser.parse(b, new LinkedHashMap<>(), seqOn);
        failed += assertCond("B: HEAD seqList unchanged (still 2, not 3)",
                rowVerbCount(rb, b, "HEAD") == 2);

        // ── C: joiner row is untouched ──────────────────────────────────
        System.out.println("\n── C. Joiner FW_(...) row is not promoted ──");
        // Reuse scenario A; its ROW row carries FW_(HEAD,,,,,,TAIL,,M:N).
        // Auto-promote must leave joiner seqList at size 1.
        int rowJoinerSize = rowVerbCount(ra, a, "ROW");
        failed += assertCond("C: ROW (joiner) seqList size == 1 (not promoted)",
                rowJoinerSize == 1);

        // ── D: single FW_Cartes is NOT promoted ─────────────────────────
        System.out.println("\n── D. Single FW_Cartes is excluded from auto-promote ──");
        ParsedWorkbook d = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("X").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.cartes())
                    .row("any=value")
                .sheet("Y").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .row("b=2")
                .join("ROW", JoinSpec.from("X").to("Y").as(Multiplicity.M_N))
                    .row("FW_EMPTY_STRING")
                .build(wbCfg);
        SeqParser.SeqParseResult rd = SeqParser.parse(d, new LinkedHashMap<>(), seqOn);
        failed += assertCond("D: FW_Cartes-only row stays size 1 (non-combo verb)",
                rowVerbCount(rd, d, "X") == 1);

        // ── E: opt-out config disables the fix ──────────────────────────
        System.out.println("\n── E. autoPromoteSingleVerb=false preserves legacy behaviour ──");
        SeqParser.SeqParseResult re = SeqParser.parse(a, new LinkedHashMap<>(), seqOff);
        failed += assertCond("E: HEAD seqList stays single under opt-out",
                rowVerbCount(re, a, "HEAD") == 1);

        // ── F: FW_Permut single also promotes ───────────────────────────
        System.out.println("\n── F. Single FW_Permut(2) also promoted ──");
        ParsedWorkbook fwb = ProgrammaticScheduleBuilder.newSchedule()
                .sheet("P").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.permut(2))
                    .row("x=1")
                    .row("x=2")
                .sheet("Q").flags(Flag.EXCLUDE, Flag.REUSE)
                    .verbs(Verb.combi(1), Verb.combi(1))
                    .row("y=1")
                .join("ROW", JoinSpec.from("P").to("Q").as(Multiplicity.M_N))
                    .row("FW_EMPTY_STRING")
                .build(wbCfg);
        SeqParser.SeqParseResult rf = SeqParser.parse(fwb, new LinkedHashMap<>(), seqOn);
        failed += assertCond("F: P seqList promoted to 2 FW_Permut(2)",
                rowVerbCount(rf, fwb, "P") == 2
                        && rowAllEqual(rf, fwb, "P", "FW_Permut(2)"));

        System.out.println();
        if (failed == 0) System.out.println("✅ ALL AUTO-PROMOTE CHECKS PASSED");
        else { System.out.println("❌ " + failed + " AUTO-PROMOTE CHECK(S) FAILED"); System.exit(1); }
    }

    private static int rowVerbCount(SeqParser.SeqParseResult r, ParsedWorkbook pw, String sheet) {
        Short key = pw.stringShortSheetName2SheetKeyHM.get(sheet);
        if (key == null) return -1;
        List<String> list = r.mapShKey2seqList.get(key);
        return list == null ? 0 : list.size();
    }

    private static boolean rowAllEqual(SeqParser.SeqParseResult r, ParsedWorkbook pw,
                                       String sheet, String expected) {
        Short key = pw.stringShortSheetName2SheetKeyHM.get(sheet);
        if (key == null) return false;
        List<String> list = r.mapShKey2seqList.get(key);
        if (list == null || list.isEmpty()) return false;
        for (String s : list) if (!expected.equals(s)) return false;
        return true;
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    // Suppress unused-import lint when Map isn't directly referenced.
    @SuppressWarnings("unused") private static final Map<String,String> UNUSED = Map.of();
}
