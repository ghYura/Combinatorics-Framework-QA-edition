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
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

/**
 * Decides, once per workbook and BEFORE the first cell key is issued, which integer width the
 * cell keys use and where the label counter starts.
 *
 * <p><b>What a key is.</b> Every key-consuming cell of every non-{@code FW_} sheet gets one
 * integer label; the labels are the "digits" that {@code AppUtil.appendPgArray} writes into
 * every COPY row.  Sheets get their own keys too (table names {@code fw_<key>}, exit codes),
 * but sheet keys never enter an array.</p>
 *
 * <p><b>Width.</b> {@link Tier#SHORT} is the default and reproduces the legacy behaviour (short
 * keys numbered {@code S+1..S+C}).  {@link Tier#BYTE} is an EXPERIMENT: it exists only when
 * {@code core.keys.dispatch=auto} is set in the properties, and even then only when the byte
 * range does not overflow.  The count that is compared with the byte range is (per
 * {@code core.keys.scope}) sheets + cells + virtual sheets — the legacy shared counter — or
 * cells only.  The signed range is used <em>except its {@code MIN_VALUE}</em>, which stays
 * reserved as the NULL array element: the Reader (CopyToReader.NULL_ELEMENT =
 * {@code Short.MIN_VALUE}) silently drops that value.  Capacity is therefore
 * {@code Byte.MAX_VALUE - Byte.MIN_VALUE = 255} labels ({@code -127..127}) for byte and
 * {@code Short.MAX_VALUE - Short.MIN_VALUE = 65535} ({@code -32767..32767}) for short.  Anything
 * beyond that throws instead of silently wrapping (the legacy {@code short[]} counter wrapped
 * past 32767 without a word).</p>
 *
 * <p><b>Counting is one lean pass.</b> No {@code DataFormatter}, no DB: a cell that is not a
 * string consumes a key without being read; only string cells are checked for the few
 * {@code FW_} directives that consume none.  The predicate is shared with the parser
 * ({@link WorkbookParser#keysConsumedBy(String)}) and the parser's {@link KeyLabeler} throws if
 * the census and the parse ever disagree, so a mismatch cannot pass unnoticed.  The scan stops
 * as soon as the count proves the workbook cannot fit even a short.</p>
 *
 * <p><b>Label placement.</b> Labels are an affine, order-preserving map of the workbook cell
 * order: {@code label(i) = firstLabel + i}.  Order preservation matters: {@code FW_Group}
 * sorts source rows by key value and its enumeration order depends on that sort, so a
 * non-monotone relabelling would silently change results.  {@code IDENTITY} keeps the legacy
 * numbering ({@code S+1..S+C}) whenever it fits the width.  {@code ANCHOR} / {@code OPTIMAL}
 * move the window so the cells that dominate the emitted text sit at the cheapest labels
 * (0..9 are one character, negatives cost one more); they are adopted only when the
 * predicted saving reaches {@code core.keys.minGainPercent} and the FW_Seq holds no
 * {@code FW_ReplaceRE} (its regexes may name literal keys).</p>
 */
public final class DataTypeDispatcher {

    private static final Logger log = LogManager.getLogger(DataTypeDispatcher.class);

    /** Usable byte labels: {@code Byte.MAX_VALUE - Byte.MIN_VALUE} = 255 ({@code MIN_VALUE} is the NULL element). */
    public static final int BYTE_CAPACITY  = Byte.MAX_VALUE  - Byte.MIN_VALUE;
    /** Usable short labels: {@code Short.MAX_VALUE - Short.MIN_VALUE} = 65535 ({@code MIN_VALUE} is the NULL element). */
    public static final int SHORT_CAPACITY = Short.MAX_VALUE - Short.MIN_VALUE;

    private DataTypeDispatcher() { }

    // ── width ────────────────────────────────────────────────────────────

    /** The integer width the cell keys may use.  {@code MIN_VALUE} of each width is never issued: the
     *  Reader reserves {@code Short.MIN_VALUE} as its NULL array element and skips it silently. */
    public enum Tier {
        BYTE (Byte.MIN_VALUE + 1,  Byte.MAX_VALUE,  1),
        SHORT(Short.MIN_VALUE + 1, Short.MAX_VALUE, 2);

        public final int min;
        public final int max;
        /** Bytes one key occupies in a primitive array of this width. */
        public final int bytesPerKey;

        Tier(int min, int max, int bytesPerKey) {
            this.min = min; this.max = max; this.bytesPerKey = bytesPerKey;
        }

        /** Distinct labels the width can hold (MIN_VALUE excluded). */
        public int capacity() { return max - min + 1; }
    }

    // ── census ───────────────────────────────────────────────────────────

    /** Result of the counting pass. */
    public static final class Census {
        /** Non-{@code FW_} sheets, workbook order (complete even when {@link #truncated}). */
        public final int sheets;
        /** Key-consuming cells over those sheets (a lower bound when {@link #truncated}). */
        public final long cells;
        /** Sheets the FW_Seq pre-scan would auto-register (0 when that option is off). */
        public final int virtualSheets;
        /** Names of the counted sheets, workbook order. */
        public final String[] sheetNames;
        /** Key-consuming cells per counted sheet, aligned with {@link #sheetNames}. */
        public final int[] cellsPerSheet;
        /** True when the scan stopped early because the cells alone exceed the short range. */
        public final boolean truncated;

        Census(int sheets, long cells, int virtualSheets, String[] sheetNames,
               int[] cellsPerSheet, boolean truncated) {
            this.sheets = sheets; this.cells = cells; this.virtualSheets = virtualSheets;
            this.sheetNames = sheetNames; this.cellsPerSheet = cellsPerSheet;
            this.truncated = truncated;
        }

        /** Every key the legacy shared counter would have issued. */
        public long totalKeys() { return sheets + cells + virtualSheets; }
    }

    /**
     * One lean pass over the non-{@code FW_} sheets.  Exact per-sheet counts; stops early once
     * the cells alone exceed {@link #SHORT_CAPACITY}.
     *
     * @param allSheets every sheet of the workbook, in workbook order
     * @param fwSeq     the {@code FW_Seq} sheet or null (only used to count virtual sheets)
     * @param wbCfg     workbook config or null (virtual sheets are counted only when enabled)
     */
    public static Census count(Sheet[] allSheets, Sheet fwSeq, AppConfig.WorkbookConfig wbCfg) {
        List<String> names = new ArrayList<>();
        int[] counts = new int[allSheets.length];
        long cells = 0L;
        int realSheets = 0;
        boolean truncated = false;
        for (Sheet sheet : allSheets) {
            String name = sheet.getSheetName();
            if (name.startsWith("FW_")) continue;
            realSheets++;
            if (truncated) continue;
            int n = 0;
            for (Row row : sheet) {
                for (Cell cell : row) n += WorkbookParser.keysConsumedBy(cell);
            }
            counts[names.size()] = n;
            names.add(name);
            cells += n;
            if (cells > SHORT_CAPACITY) truncated = true;
        }

        int virtual = 0;
        if (!truncated && fwSeq != null && wbCfg != null && wbCfg.autoGenerateMissingSheetsFromFwSeq) {
            virtual = WorkbookParser.discoverVirtualSheets(fwSeq, new LinkedHashSet<>(names),
                    wbCfg.virtualSheetNamePrefix, new DataFormatter()).size();
        }
        int[] perSheet = new int[names.size()];
        System.arraycopy(counts, 0, perSheet, 0, perSheet.length);
        return new Census(realSheets, cells, virtual, names.toArray(new String[0]), perSheet, truncated);
    }

    // ── plan ─────────────────────────────────────────────────────────────

    /** The decision: width + label window + sheet-key placement. Immutable. */
    public static final class Plan {
        public final Tier tier;
        public final int sheets;
        public final int virtualSheets;
        public final long cells;
        /** Label of the first key-consuming cell in workbook order. */
        public final int firstLabel;
        /** True when the labels equal the legacy numbering {@code S+1..S+C}. */
        public final boolean identity;
        /** Strategy that produced {@link #firstLabel} after fall-backs. */
        public final AppConfig.KeysConfig.Strategy strategy;
        /** Model-predicted saving of the emitted characters vs the baseline placement (0 = none). */
        public final double predictedGainPercent;
        /** One-line decision trail for the log. */
        public final String reason;

        Plan(Tier tier, int sheets, int virtualSheets, long cells, int firstLabel,
             AppConfig.KeysConfig.Strategy strategy, double predictedGainPercent, String reason) {
            this.tier = tier; this.sheets = sheets; this.virtualSheets = virtualSheets;
            this.cells = cells; this.firstLabel = firstLabel; this.strategy = strategy;
            this.predictedGainPercent = predictedGainPercent; this.reason = reason;
            this.identity = (cells == 0) || (firstLabel == sheets + 1);
            if (cells > 0 && (firstLabel < tier.min || firstLabel + cells - 1 > tier.max)) {
                throw new IllegalArgumentException("labels " + firstLabel + ".." + (firstLabel + cells - 1)
                        + " do not fit " + tier + " [" + tier.min + ".." + tier.max + "]");
            }
        }

        /** Test/benchmark hook: a plan with an explicit first label (validated against the width). */
        public static Plan custom(Tier tier, int sheets, int virtualSheets, long cells, int firstLabel) {
            return new Plan(tier, sheets, virtualSheets, cells, firstLabel,
                    AppConfig.KeysConfig.Strategy.IDENTITY, 0.0, "custom");
        }

        /** Last label issued (== {@link #firstLabel} - 1 when there are no cells). */
        public int lastLabel() { return (int) (firstLabel + cells - 1); }

        /** Label of the {@code ordinal}-th key-consuming cell (0-based, workbook order). */
        public short label(long ordinal) {
            if (ordinal < 0 || ordinal >= cells) {
                throw new IndexOutOfBoundsException("cell ordinal " + ordinal + " outside 0.." + (cells - 1));
            }
            return (short) (firstLabel + ordinal);
        }

        /**
         * Where auto-registered (virtual) sheets start.  Legacy: right after the last cell key
         * ({@code S+C}) — kept whenever every sheet key still fits a positive short; otherwise
         * right after the real sheets, because the cell labels no longer occupy that line.
         */
        public int virtualKeyBase() {
            return (sheets + cells + virtualSheets <= Short.MAX_VALUE) ? (int) (sheets + cells) : sheets;
        }

        public KeyLabeler newLabeler() { return new KeyLabeler(this); }

        public String describe() {
            return "tier=" + tier + " sheets=" + sheets + " cells=" + cells + " virtual=" + virtualSheets
                    + " labels=" + (cells == 0 ? "-" : firstLabel + ".." + lastLabel())
                    + (identity ? " (legacy numbering)" : " (relabelled)")
                    + " strategy=" + strategy
                    + (predictedGainPercent > 0 ? String.format(" predictedGain=%.1f%%", predictedGainPercent) : "")
                    + " | " + reason;
        }

        @Override public String toString() { return describe(); }
    }

    /** Issues the labels of a {@link Plan} in order and refuses to run past the census. */
    public static final class KeyLabeler {
        private final Plan plan;
        private int issued;

        KeyLabeler(Plan plan) { this.plan = plan; }

        /** Next label; throws if the parser consumes more keys than the census counted. */
        public short next() {
            if (issued >= plan.cells) {
                throw new IllegalStateException("DataTypeDispatcher census mismatch: the parser needs key #"
                        + (issued + 1) + " but only " + plan.cells + " were counted — "
                        + "WorkbookParser.keysConsumedBy and parseCellValues have diverged");
            }
            return (short) (plan.firstLabel + issued++);
        }

        /** The label most recently issued (the previous cell, for FW_Optional / FW_Refine...). */
        public short last() {
            if (issued == 0) throw new IllegalStateException("no key issued yet");
            return (short) (plan.firstLabel + issued - 1);
        }

        public int issued() { return issued; }

        /** True when the parse issued exactly the counted number of keys. */
        public boolean exhausted() { return issued == plan.cells; }
    }

    /** Count + plan in one call (what {@link WorkbookParser} uses). */
    public static Plan dispatch(Sheet[] allSheets, Sheet fwSeq, AppConfig.WorkbookConfig wbCfg) {
        AppConfig.KeysConfig cfg = (wbCfg == null) ? AppConfig.KeysConfig.DEFAULT : wbCfg.keys;
        Plan plan = plan(count(allSheets, fwSeq, wbCfg), fwSeq, cfg);
        log.info("[Keys] {}", plan.describe());
        return plan;
    }

    /**
     * Pick the width and place the label window.
     *
     * @throws IllegalStateException when the workbook needs more keys than a short holds
     */
    public static Plan plan(Census c, Sheet fwSeq, AppConfig.KeysConfig cfg) {
        final AppConfig.KeysConfig k = (cfg == null) ? AppConfig.KeysConfig.DEFAULT : cfg;
        final boolean allKeys = (k.scope == AppConfig.KeysConfig.Scope.ALL);
        final long gate = allKeys ? c.totalKeys() : c.cells;

        if (c.truncated || gate > SHORT_CAPACITY || c.sheets + (long) c.virtualSheets > Short.MAX_VALUE) {
            throw new IllegalStateException("DataTypeDispatcher: the workbook needs "
                    + (c.truncated ? "more than " + SHORT_CAPACITY : String.valueOf(gate))
                    + " distinct keys (" + c.sheets + " sheets + " + (c.truncated ? ">" : "") + c.cells
                    + " cells + " + c.virtualSheets + " virtual sheets, scope=" + k.scope
                    + ") but the widest supported key type, short, holds " + SHORT_CAPACITY
                    + ". The legacy counter would have wrapped silently at " + Short.MAX_VALUE
                    + "; split the workbook into smaller ones.");
        }

        final Tier tier = (k.dispatch == AppConfig.KeysConfig.Dispatch.SHORT) ? Tier.SHORT
                : (gate <= BYTE_CAPACITY ? Tier.BYTE : Tier.SHORT);
        final String gateWhy = "gate(" + (allKeys ? "sheets+cells+virtual" : "cells") + ")=" + gate
                + (k.dispatch == AppConfig.KeysConfig.Dispatch.SHORT ? ", dispatch=short"
                : (tier == Tier.BYTE ? " <= " + BYTE_CAPACITY : " > " + BYTE_CAPACITY + " (byte overflow)"));

        final long cells = c.cells;
        final int[] prefix = lengthPrefix(tier);
        final int identityBase = c.sheets + 1;
        final boolean identityFits = cells == 0 || (long) identityBase + cells - 1 <= tier.max;

        int base;
        String placement;
        if (identityFits) {
            base = identityBase;
            placement = "legacy numbering fits " + tier;
        } else {
            base = uniformBestBase(cells, tier, prefix);
            placement = "legacy numbering exceeds " + tier + ", cheapest window forced";
        }

        AppConfig.KeysConfig.Strategy effective = AppConfig.KeysConfig.Strategy.IDENTITY;
        double gain = 0.0;
        if (k.strategy != AppConfig.KeysConfig.Strategy.IDENTITY && cells > 0) {
            if (fwSeq == null) {
                placement += "; strategy " + k.strategy + " skipped (no FW_Seq)";
            } else {
                KeyWeightModel model = KeyWeightModel.build(c, fwSeq);
                if (model.replaceRePresent) {
                    placement += "; strategy " + k.strategy + " skipped (FW_ReplaceRE present: its regexes may"
                            + " name literal keys)";
                } else if (!model.hasWeights()) {
                    placement += "; strategy " + k.strategy + " skipped (nothing in FW_Seq emits these cells)";
                } else {
                    int lo = tier.min, hi = (int) (tier.max - cells + 1);
                    int candidate;
                    if (k.strategy == AppConfig.KeysConfig.Strategy.ANCHOR) {
                        int heavy = model.heavySheet(k.anchorSheet, c);
                        int ordFirst = 0;
                        for (int s = 0; s < heavy; s++) ordFirst += c.cellsPerSheet[s];
                        candidate = Math.max(lo, Math.min(hi, -ordFirst));
                    } else {
                        candidate = model.optimalBase(c, tier, prefix, lo, hi);
                    }
                    double baseCost = model.cost(c, base, tier, prefix);
                    double candCost = model.cost(c, candidate, tier, prefix);
                    double pct = baseCost <= 0 ? 0.0 : 100.0 * (baseCost - candCost) / baseCost;
                    if (candidate != base && pct >= k.minGainPercent) {
                        base = candidate;
                        effective = k.strategy;
                        gain = pct;
                        placement += String.format("; %s window adopted (predicted %.1f%% fewer key characters)",
                                k.strategy, pct);
                    } else {
                        placement += String.format("; %s rejected (predicted %.1f%% < minGain %.1f%%)",
                                k.strategy, pct, k.minGainPercent);
                    }
                }
            }
        }
        return new Plan(tier, c.sheets, c.virtualSheets, cells, base, effective, gain,
                gateWhy + "; " + placement);
    }

    // ── label geometry (shared with KeyWeightModel) ──────────────────────

    /** Characters a label occupies: digits, plus the minus sign for negatives. */
    static int labelChars(int v) {
        int a = v < 0 ? -v : v;
        int d = a < 10 ? 1 : a < 100 ? 2 : a < 1000 ? 3 : a < 10000 ? 4 : 5;
        return v < 0 ? d + 1 : d;
    }

    /** {@code P[i]} = total characters of the labels {@code tier.min .. tier.min+i-1}. */
    static int[] lengthPrefix(Tier tier) {
        int[] p = new int[tier.capacity() + 1];
        for (int i = 0; i < tier.capacity(); i++) p[i + 1] = p[i] + labelChars(tier.min + i);
        return p;
    }

    /** First label of the {@code cells}-wide window with the fewest total characters (ties: fewer negatives). */
    static int uniformBestBase(long cells, Tier tier, int[] prefix) {
        int n = (int) cells;
        int lo = tier.min, hi = tier.max - n + 1;
        int best = hi;
        long bestCost = Long.MAX_VALUE;
        for (int base = hi; base >= lo; base--) {
            long cost = prefix[base + n - tier.min] - prefix[base - tier.min];
            if (cost < bestCost) { bestCost = cost; best = base; }
        }
        return best;
    }
}
