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
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Tier-2 win 2.4 — fluent Java DSL for constructing a Combinatorics schedule
 * in code, alongside the existing {@link XlsxScheduleParser} and
 * {@link JsonScheduleParser} input formats.
 *
 * Design rationale — mirror, not re-implement:
 *   The builder materialises an in-memory POI {@code XSSFWorkbook} with the
 *   same sheet/row/cell structure that {@link XlsxScheduleParser} would read
 *   from an XLSX file or {@link JsonScheduleParser} from JSON, then delegates
 *   to {@link WorkbookParser#parseWorkbook(org.apache.poi.ss.usermodel.Workbook, AppConfig.WorkbookConfig, String)}.
 *   The downstream pipeline ({@code SeqParser} → {@code SheetWorker} → final
 *   table assembly) sees a {@link ParsedWorkbook} identical to what it would
 *   have built from the same scenario expressed as XLSX or JSON.
 *
 * That equivalence is the load-bearing invariant: three input formats, one
 * canonical model, zero divergence.  {@code BuilderEquivalenceVerify}
 * pins this by building the same scenario via JSON and via the builder and
 * asserting cell-for-cell equality of the resulting {@link ParsedWorkbook}.
 *
 * Example — closed form of {@code test_e2e_metric.json}:
 *
 * <pre>{@code
 * ParsedWorkbook pw = ProgrammaticScheduleBuilder.newSchedule()
 *     .sheet("HEAD").flags(Flag.EXCLUDE, Flag.REUSE)
 *         .verbs(Verb.combi(1), Verb.combi(1))
 *         .row("scenario=demo")
 *     .sheet("COST").flags(Flag.EXCLUDE, Flag.REUSE)
 *         .verbs(Verb.combi(1), Verb.combi(1))
 *         .rows(" id=1 cost=0.10", " id=2 cost=0.30", " id=3 cost=0.50")
 *     .sheet("LAT").flags(Flag.EXCLUDE, Flag.REUSE)
 *         .verbs(Verb.combi(1), Verb.combi(1))
 *         .rows(" latency=10ms", " latency=30ms", " latency=80ms")
 *     .sheet("TAIL").flags(Flag.EXCLUDE, Flag.REUSE)
 *         .verbs(Verb.combi(1), Verb.combi(1))
 *         .row(" status=ok")
 *     .join("ROW", JoinSpec.from("HEAD").via("COST", "LAT")
 *                          .to("TAIL").as(Multiplicity.M_N))
 *         .row("FW_EMPTY_STRING")
 *     .runMeFirstOnce("class RunMeFirstOnce { public static String FW_ARGS;"
 *                   + " public static void main(String[] a){ FW_ARGS = \"\"; } }")
 *     .arguments("noargs")
 *     .customVar(2, "FWCUSTOMVAR=2 nominal")
 *     .build(wbCfg);
 * }</pre>
 *
 * Single-use: {@link #build(AppConfig.WorkbookConfig)} closes the intermediate
 * workbook.  Re-running on the same builder is undefined; create a fresh one.
 *
 * Thread-safety: not thread-safe.  A single builder is meant to be used by one
 * thread at a time; the produced {@link ParsedWorkbook} IS thread-safe (its
 * fields are unmodifiable views — same guarantee XLSX/JSON parsers provide).
 */
public final class ProgrammaticScheduleBuilder {

    /** Per-sheet record kept until {@link #materialise()}. */
    private static final class SheetSpec {
        final String name;
        final List<Flag> flags = new ArrayList<>(2);
        final List<String> verbs = new ArrayList<>(2);
        final List<List<String>> rows = new ArrayList<>();
        SheetSpec(String name) { this.name = name; }
    }

    /** Per-joiner record (special FW_Seq row that emits a {@code FW_(...)} verb). */
    private static final class JoinerSpec {
        final String name;
        final String fwExpression;
        final List<List<String>> rows = new ArrayList<>();
        JoinerSpec(String name, String fwExpression) {
            this.name = name;
            this.fwExpression = fwExpression;
        }
    }

    private final Map<String, SheetSpec>  sheets   = new LinkedHashMap<>();
    private final Map<String, JoinerSpec> joiners  = new LinkedHashMap<>();
    private String runMeFirstOnce = null;
    private String arguments = null;
    private final Map<Integer, String> customVars = new LinkedHashMap<>();

    private ProgrammaticScheduleBuilder() {}

    /** Entry point. */
    public static ProgrammaticScheduleBuilder newSchedule() {
        return new ProgrammaticScheduleBuilder();
    }

    // ─── fluent root methods ─────────────────────────────────────────────

    /**
     * Introduce (or re-select) a payload sheet.  The returned entry exposes
     * {@code flags / verbs / row / rows} chaining and inherits navigation
     * back to the root builder.
     *
     * If a sheet with this name already exists in the builder, the same
     * entry is returned — append-only mutation on it is fine.
     */
    public SheetEntry sheet(String name) {
        requireName(name);
        SheetSpec s = sheets.computeIfAbsent(name, SheetSpec::new);
        return new SheetEntry(this, s);
    }

    /**
     * Introduce a joiner row.  A joiner has no per-entity sheet of its own —
     * its single FW_Seq row carries the {@code FW_(...)} expression.  Payload
     * rows (typically just {@code FW_EMPTY_STRING}) live on a same-named
     * sheet that the engine reads as the joiner's output placeholder.
     */
    public SheetEntry join(String name, JoinSpec spec) {
        requireName(name);
        if (spec == null) throw new IllegalArgumentException("join: spec must not be null");
        joiners.put(name, new JoinerSpec(name, spec.toFwExpression()));
        // Joiner also gets its own sheet (so FW_SheetNames sees it) — payload
        // rows attach to it via row()/rows().
        SheetSpec s = sheets.computeIfAbsent(name, SheetSpec::new);
        return new SheetEntry(this, s);
    }

    /**
     * Raw-expression escape hatch for joiner forms not covered by {@link JoinSpec}
     * (e.g. exotic separators or experimental relations).  Pass the full
     * {@code FW_(...)} string with all 8 commas — caller is responsible for
     * correctness.
     */
    public SheetEntry joinRaw(String name, String fwExpression) {
        requireName(name);
        if (fwExpression == null || !fwExpression.startsWith("FW_("))
            throw new IllegalArgumentException("joinRaw: expression must start with 'FW_('");
        joiners.put(name, new JoinerSpec(name, fwExpression));
        SheetSpec s = sheets.computeIfAbsent(name, SheetSpec::new);
        return new SheetEntry(this, s);
    }

    public ProgrammaticScheduleBuilder runMeFirstOnce(String javaSource) {
        this.runMeFirstOnce = javaSource;
        return this;
    }

    public ProgrammaticScheduleBuilder arguments(String args) {
        this.arguments = args;
        return this;
    }

    public ProgrammaticScheduleBuilder customVar(int index, String declaration) {
        customVars.put(index, declaration);
        return this;
    }

    /** Build the canonical model directly.  The intermediate POI workbook is
     *  managed internally (try-with-resources). */
    public ParsedWorkbook build(AppConfig.WorkbookConfig wbCfg) throws Exception {
        try (XSSFWorkbook wb = materialise()) {
            return WorkbookParser.parseWorkbook(wb, wbCfg, "programmatic:builder");
        }
    }

    /** Expose the intermediate workbook (caller must close).  Useful for
     *  debugging and for tests that want to inspect cell-level structure
     *  before the WorkbookParser consumes it. */
    public XSSFWorkbook buildWorkbook() {
        return materialise();
    }

    /** Adapt this builder as a {@link ScheduleParser} so callers can plug a
     *  programmatic schedule into the same shelf as XLSX/JSON.  The path
     *  argument is ignored. */
    public ScheduleParser asScheduleParser() {
        return (path, cfg) -> this.build(cfg);
    }

    // ─── materialisation ─────────────────────────────────────────────────

    /**
     * Build the in-memory POI {@code XSSFWorkbook} matching the FW_Seq schema
     * the engine consumes.  Sheet order is preserved:
     *   FW_Seq, FW_SheetNames, FW_RunMeFirstOnce?, FW_Arguments?, FW_CUSTOM_VAR?,
     *   then payload sheets in user-declared order.
     */
    private XSSFWorkbook materialise() {
        XSSFWorkbook wb = new XSSFWorkbook();

        // FW_Seq: one row per sheet (flags + verbs), one row per joiner (FW_(...) in col 4).
        Sheet seq = wb.createSheet("FW_Seq");
        int seqRow = 0;
        // Stable iteration order via LinkedHashMap.
        for (SheetSpec s : sheets.values()) {
            if (joiners.containsKey(s.name)) continue;  // joiners get a different row format
            Row r = seq.createRow(seqRow++);
            r.createCell(0).setCellValue(s.name);
            r.createCell(1).setCellValue(flagToken(s.flags, 0));
            r.createCell(2).setCellValue(flagToken(s.flags, 1));
            for (int i = 0; i < s.verbs.size() && i < 3; i++) {
                r.createCell(3 + i).setCellValue(s.verbs.get(i));
            }
        }
        // Joiners last (matches the JSON/XLSX examples where the joiner row is
        // emitted after all entity rows).
        for (JoinerSpec j : joiners.values()) {
            Row r = seq.createRow(seqRow++);
            r.createCell(0).setCellValue(j.name);
            // cols 1 and 2 left blank — matches "FW_(HEAD,,COST,,LAT,,TAIL,,M:N)"
            // row layout in test_e2e_metric.json.
            r.createCell(3).setCellValue(j.fwExpression);
        }

        // FW_SheetNames: 3 cols, all entities including joiners.
        Sheet sn = wb.createSheet("FW_SheetNames");
        int snRow = 0;
        for (String name : sheets.keySet()) {
            Row r = sn.createRow(snRow++);
            r.createCell(0).setCellValue(name);
            r.createCell(1).setCellValue("FW_EMPTY_STRING");
            r.createCell(2).setCellValue("FW_EMPTY_STRING");
        }

        if (runMeFirstOnce != null) {
            Sheet rmf = wb.createSheet("FW_RunMeFirstOnce");
            rmf.createRow(0).createCell(0).setCellValue(runMeFirstOnce);
        }
        if (arguments != null) {
            Sheet ar = wb.createSheet("FW_Arguments");
            ar.createRow(0).createCell(0).setCellValue(arguments);
        }
        if (!customVars.isEmpty()) {
            Sheet cv = wb.createSheet("FW_CUSTOM_VAR");
            int idx = 0;
            for (Map.Entry<Integer, String> e : customVars.entrySet()) {
                Row r = cv.createRow(idx++);
                r.createCell(0).setCellValue(String.valueOf(e.getKey()));
                r.createCell(1).setCellValue(e.getValue());
            }
        }

        // Payload sheets in declared order.
        for (SheetSpec s : sheets.values()) {
            Sheet ps = wb.createSheet(s.name);
            int rowIdx = 0;
            for (List<String> rowCells : s.rows) {
                Row r = ps.createRow(rowIdx++);
                for (int c = 0; c < rowCells.size(); c++) {
                    String v = rowCells.get(c);
                    if (v != null) r.createCell(c).setCellValue(v);
                }
            }
        }

        return wb;
    }

    private static String flagToken(List<Flag> flags, int idx) {
        if (idx >= flags.size()) return "";
        return flags.get(idx).token;
    }

    private static void requireName(String name) {
        if (name == null || name.isBlank())
            throw new IllegalArgumentException("sheet/join name must not be blank");
        if (name.startsWith("FW_"))
            throw new IllegalArgumentException(
                    "sheet/join name '" + name + "' collides with the FW_* control namespace");
    }

    // ─── nested sheet entry ──────────────────────────────────────────────

    /**
     * Per-sheet (or per-joiner) accumulator.  Methods are append-only — calling
     * {@code flags} or {@code verbs} multiple times concatenates; calling
     * {@code row}/{@code rows} appends payload rows.  Navigation back to the
     * root builder is via {@link #sheet}/{@link #join}/{@link #runMeFirstOnce}/
     * {@link #arguments}/{@link #customVar}/{@link #build}.
     */
    public static final class SheetEntry {
        private final ProgrammaticScheduleBuilder parent;
        private final SheetSpec spec;
        private SheetEntry(ProgrammaticScheduleBuilder p, SheetSpec s) {
            this.parent = p; this.spec = s;
        }

        public SheetEntry flag(Flag f) {
            if (f != null) spec.flags.add(f);
            return this;
        }
        public SheetEntry flags(Flag... fs) {
            if (fs != null) for (Flag f : fs) if (f != null) spec.flags.add(f);
            return this;
        }
        public SheetEntry verb(String token) {
            if (token != null) spec.verbs.add(token);
            return this;
        }
        public SheetEntry verbs(String... tokens) {
            if (tokens != null) for (String t : tokens) if (t != null) spec.verbs.add(t);
            return this;
        }
        public SheetEntry row(String value) {
            List<String> r = new ArrayList<>(1);
            r.add(value);
            spec.rows.add(r);
            return this;
        }
        public SheetEntry rows(String... values) {
            if (values != null) for (String v : values) row(v);
            return this;
        }
        /** Multi-cell row (for sheets where cell-1 / cell-2 / … matter). */
        public SheetEntry rowCells(String... cells) {
            List<String> r = new ArrayList<>(cells == null ? 0 : cells.length);
            if (cells != null) for (String c : cells) r.add(c);
            spec.rows.add(r);
            return this;
        }

        // Navigation pass-through to the root builder.
        public SheetEntry sheet(String name)            { return parent.sheet(name); }
        public SheetEntry join(String name, JoinSpec s) { return parent.join(name, s); }
        public SheetEntry joinRaw(String name, String e){ return parent.joinRaw(name, e); }
        public ProgrammaticScheduleBuilder runMeFirstOnce(String src)
                                                         { return parent.runMeFirstOnce(src); }
        public ProgrammaticScheduleBuilder arguments(String args)
                                                         { return parent.arguments(args); }
        public ProgrammaticScheduleBuilder customVar(int idx, String decl)
                                                         { return parent.customVar(idx, decl); }
        public ParsedWorkbook build(AppConfig.WorkbookConfig wbCfg) throws Exception
                                                         { return parent.build(wbCfg); }
        public XSSFWorkbook buildWorkbook()              { return parent.buildWorkbook(); }
        public ScheduleParser asScheduleParser()         { return parent.asScheduleParser(); }
        /** Return to root builder explicitly — useful when an IDE's chain
         *  inference loses the SheetEntry context. */
        public ProgrammaticScheduleBuilder and()         { return parent; }
    }
}
