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

package com.company.precompute;

import com.company.SeqParser;
import com.company.config.AppConfig;
import com.company.excel.ParsedWorkbook;
import com.company.excel.WorkbookParser;

import java.lang.management.ManagementFactory;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Iter4 Layer 1 — pessimistic memory-budget estimator.
 *
 * <p>Walks the {@link SeqParser.SeqParseResult} and computes UPPER-BOUND bytes
 * per output table (per-sheet fw_&lt;k&gt;/fw2_&lt;k&gt;, fw_final, fw_opt&lt;i&gt;).
 * Compares simultaneous-peak estimate against {@code Runtime.maxMemory() ×
 * GC_HEADROOM × (1 / SAFETY_FACTOR)}.  Returns {@link Decision#JAVA} only
 * when the estimate fits comfortably; otherwise {@link Decision#DB}.</p>
 *
 * <p>Modelling choices (all intentionally pessimistic — false-DB is acceptable,
 * false-JAVA causes OOM):</p>
 * <ul>
 *   <li>Per-verb fanout uses worst-case formulas from
 *       {@link com.company.combinatorics.CombinatorialGenerator} (n!, n^k,
 *       C(n,k), 2^n, …) — verified in Iter4.1.</li>
 *   <li>Chains of verbs multiply: each subsequent verb operates on EACH ROW
 *       of the prior verb's output, so totals = prev_rows × per-row-fanout.</li>
 *   <li>Distinct / Group / ReplaceRE shrinkage is NOT modelled — they only
 *       reduce output, never grow it.</li>
 *   <li>Brace ops use {@code |excl1| × |excl2|} as the upper bound (covers
 *       M:N, M:M, 1:N).</li>
 *   <li>Final cartesian = product of mandatory sheets' rows, capped by
 *       {@code core.limitVarGivenLessThan}.</li>
 *   <li>fw_opt&lt;i&gt; = sum over C(n_opt, i) combos × per-combo cartesian,
 *       each capped by {@code core.optional.limitOptionalSheetsCombosMax}.</li>
 *   <li>Peak = simultaneous sum of all live tables (worst case — until Layer 2
 *       streaming lands, everything alive at once).</li>
 *   <li>Object overhead: 32 B per short[] row reference (header + list slot).</li>
 *   <li>GC headroom: 65% of {@code Runtime.maxMemory()} usable for data.</li>
 * </ul>
 *
 * <p>This module is intentionally side-effect-free except for logging.  No PG
 * connection required.  No memory allocations beyond the report struct.</p>
 */
public final class PrecomputeMemoryBudget {

    private static final Logger log = LogManager.getLogger(PrecomputeMemoryBudget.class);

    /** Strategy decision the orchestrator will route on. */
    public enum Decision { JAVA, DB }

    /** Caller-driven mode override.  AUTO consults the estimate; FORCE_* bypasses it. */
    public enum Mode { AUTO, FORCE_JAVA, FORCE_DB }

    // ── tuning constants ────────────────────────────────────────────────

    /** Short[] row reference overhead: object header (16) + ArrayList slot (4) + padding. */
    private static final long ROW_REF_OVERHEAD_BYTES = 32L;

    /** Fraction of -Xmx usable for data without provoking G1/ZGC Full GC. */
    private static final double GC_HEADROOM_FRACTION = 0.65;

    /** Multiplier applied to estimate before comparing to budget — pads against
     *  the things we DON'T model (HashMap dedup nodes, COPY-IN encoding buffer,
     *  transient JDBC ResultSet during result COPY, etc.). */
    private static final double SAFETY_FACTOR = 1.5;

    /** When estimate × SAFETY_FACTOR exceeds Long.MAX_VALUE, fall back to "huge". */
    private static final BigInteger HUGE = BigInteger.ONE.shiftLeft(63);

    // ── [Iter4.6] Streaming-model constants ─────────────────────────────
    // fw_final and fw_opt<i> stream through bounded queues + COPY-IN batches
    // (see FinalTableAssembler.runFnlThreadJavaPipeline — Refactor-#1
    // producer/consumer pattern; runOptionalInsert — Refactor-#14 per-combo
    // batching).  Peak memory is bounded by (queue depth × batch size ×
    // per-row encoded bytes) + per-sheet pre-encoded source buffers, NOT by
    // the full materialised cartesian table.

    /** Avg encoded bytes per cell value (e.g. "1234" + "," ≈ 4 bytes).  Heuristic. */
    private static final long ENCODED_BYTES_PER_CELL = 4L;

    /** Per-array overhead in encoded form: { } braces + tab delimiter. */
    private static final long ENCODED_BYTES_PER_ARRAY_OVERHEAD = 4L;

    /** fw_final pipeline producer count.  Fixed at 1 (step #10 reverted to
     *  single producer — multi-producer broke limitVar lex-order). */
    private static final int FW_FINAL_PRODUCER_COUNT = 1;

    private PrecomputeMemoryBudget() {}

    // ── public API ──────────────────────────────────────────────────────

    /** Estimate + decide.  Logs the full breakdown at INFO; returns the report. */
    public static Report estimate(SeqParser.SeqParseResult seq,
                                  ParsedWorkbook pw,
                                  AppConfig cfg,
                                  Mode mode) {
        long maxHeap = Runtime.getRuntime().maxMemory();
        long budget = (long) (maxHeap * GC_HEADROOM_FRACTION);
        long osFree = queryOsFreeRam();

        Map<Short, Stage> perSheet = computePerSheetStages(seq, pw);
        BigInteger perSheetBytes = BigInteger.ZERO;
        Map<Short, BigInteger> perSheetBytesMap = new LinkedHashMap<>();
        for (var e : perSheet.entrySet()) {
            BigInteger b = stageBytes(e.getValue());
            perSheetBytesMap.put(e.getKey(), b);
            perSheetBytes = perSheetBytes.add(b);
        }

        // [Iter4.6] Compute BOTH the full-materialised estimate (informational,
        // shows what fw_final/fw_opt WOULD cost if not streamed) and the
        // streaming-aware estimate (the actual peak when the pipeline runs).
        // Decision uses the streaming estimate — matches reality of the pure-Java
        // and PG-mode fnl pipelines (both stream via producer/consumer).
        BigInteger fwFinalFullBytes     = estimateFwFinal(seq, perSheet, cfg);
        BigInteger fwOptFullBytes       = estimateFwOpt(seq, perSheet, cfg);
        BigInteger fwFinalStreamedBytes = estimateFwFinalStreamed(seq, perSheet, cfg);
        BigInteger fwOptStreamedBytes   = estimateFwOptStreamed(seq, perSheet, cfg);

        BigInteger fwFinalBytes = fwFinalStreamedBytes;
        BigInteger fwOptBytes   = fwOptStreamedBytes;

        // Peak = simultaneous sum of (per-sheet materialised) + (fw_final
        // streaming buffers) + (fw_opt streaming buffers).  Both finals run
        // concurrently in FinalTableAssembler.assemble (fixed pool of 2).
        BigInteger peak = perSheetBytes.add(fwFinalBytes).add(fwOptBytes);
        BigInteger peakSafetied = peak.multiply(BigInteger.valueOf(3)).divide(BigInteger.TWO);  // × 1.5

        Decision decision;
        String rationale;
        switch (mode) {
            case FORCE_JAVA:
                decision = Decision.JAVA;
                rationale = "FORCE_JAVA (user override; estimate ignored)";
                break;
            case FORCE_DB:
                decision = Decision.DB;
                rationale = "FORCE_DB (user override; estimate ignored)";
                break;
            case AUTO:
            default:
                BigInteger budgetBI = BigInteger.valueOf(budget);
                if (peakSafetied.compareTo(budgetBI) <= 0) {
                    decision = Decision.JAVA;
                    BigInteger headroom = budgetBI.subtract(peakSafetied);
                    rationale = String.format(
                        "AUTO → JAVA: estimate × safety (%s) ≤ heap budget (%s); headroom %s",
                        formatBytes(peakSafetied), formatBytes(budgetBI), formatBytes(headroom));
                } else {
                    decision = Decision.DB;
                    BigInteger over = peakSafetied.subtract(budgetBI);
                    StringBuilder why = new StringBuilder(String.format(
                        "AUTO → DB: estimate × safety (%s) > heap budget (%s); over by %s",
                        formatBytes(peakSafetied), formatBytes(budgetBI), formatBytes(over)));
                    // Auto-heap-extension diagnostic: would OS RAM allow it?
                    if (osFree > 0) {
                        long need = peakSafetied.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0
                            ? Long.MAX_VALUE
                            : (long) (peakSafetied.longValueExact() / GC_HEADROOM_FRACTION);
                        if (osFree >= need - maxHeap) {
                            why.append(String.format(
                                "; OS free RAM %s — bumping -Xmx to ~%s would unlock JAVA mode",
                                formatBytes(osFree),
                                formatBytes(BigInteger.valueOf(need))));
                        } else {
                            why.append(String.format(
                                "; OS free RAM %s also insufficient (need ~%s) — DB is the only option",
                                formatBytes(osFree),
                                formatBytes(BigInteger.valueOf(need))));
                        }
                    }
                    rationale = why.toString();
                }
                break;
        }

        Report report = new Report(decision, maxHeap, budget, osFree,
                perSheetBytes, perSheetBytesMap, fwFinalBytes, fwOptBytes,
                fwFinalFullBytes, fwOptFullBytes,
                peak, peakSafetied, rationale,
                mode, perSheet);
        log.info("[Precompute Layer 1]\n{}", report.render());
        return report;
    }

    // ── [Iter4.6] Streaming-model estimators ────────────────────────────

    /** Bytes for one encoded short[] of avg-element-count {@code n}. */
    private static long encodedArrayBytes(int n) {
        return (long) Math.max(1, n) * ENCODED_BYTES_PER_CELL
                + ENCODED_BYTES_PER_ARRAY_OVERHEAD;
    }

    /** Bytes for one encoded fw_final / fw_opt output ROW = {@code numCols}
     *  arrays concatenated with tabs + trailing newline. */
    private static long encodedRowBytes(int numCols, int totalArrayElements) {
        if (numCols <= 0) return 0L;
        int avgPerCol = Math.max(1, totalArrayElements / numCols);
        return (long) numCols * encodedArrayBytes(avgPerCol);
    }

    /** [Iter4.6] fw_final STREAMING peak.  Composition:
     *  <ul>
     *    <li>per-sheet pre-encoded source buffers (held for the full cartesian
     *        iteration in {@code FinalTableAssembler.runFnlThreadJavaPipeline}
     *        — step #8 pre-encode optimisation).</li>
     *    <li>producer/consumer queue × batch size × per-output-row encoded
     *        bytes (queue depth = (producer + consumer) × 4 per Refactor-#1).</li>
     *  </ul> */
    private static BigInteger estimateFwFinalStreamed(SeqParser.SeqParseResult seq,
                                                       Map<Short, Stage> stages,
                                                       AppConfig cfg) {
        int numSheets = 0;
        long totalRowLen = 0L;
        BigInteger perSheetEncodedBytes = BigInteger.ZERO;
        for (Short k : seq.toCombinatoricsHM.keySet()) {
            Stage st = stages.get(k);
            if (st == null) continue;
            numSheets++;
            totalRowLen += st.rowLen;
            BigInteger sheetEnc = st.rowCount.multiply(
                    BigInteger.valueOf(encodedArrayBytes(st.rowLen)));
            perSheetEncodedBytes = perSheetEncodedBytes.add(sheetEnc);
        }
        if (numSheets == 0) return BigInteger.ZERO;

        int batchSize = Math.max(1_000, cfg.threading.counter4copyMax);
        int consumerCount = Math.max(2,
                Math.min(cfg.pool.maxConcurrentCopies, cfg.pool.maxSize));
        int queueDepth = (FW_FINAL_PRODUCER_COUNT + consumerCount) * 4;
        long perOutputRowBytes = encodedRowBytes(numSheets, (int) totalRowLen);
        BigInteger queueAndBatch = BigInteger.valueOf((long) queueDepth * batchSize)
                .multiply(BigInteger.valueOf(perOutputRowBytes));

        return perSheetEncodedBytes.add(queueAndBatch);
    }

    /** [Iter4.6] fw_opt STREAMING peak.  Per-table flow (runOptionalInsert,
     *  step #14): each combo loads its own per-sheet encoded sources +
     *  batch buffer; multiple combos run concurrently via the slot pool
     *  ({@code 2 × cores}).  Opt tables (i=1, 2, …) run SEQUENTIALLY in
     *  runOptsThread, so peak across all opt tables = max per-table peak. */
    private static BigInteger estimateFwOptStreamed(SeqParser.SeqParseResult seq,
                                                     Map<Short, Stage> stages,
                                                     AppConfig cfg) {
        List<Short> optKeys = new ArrayList<>(seq.toCombinatoricsHMoptional.keySet());
        if (optKeys.isEmpty()) return BigInteger.ZERO;
        Set<Integer> ks = Set.copyOf(cfg.optional.includeOptionalCombiPairsToDB);

        int batchSize    = Math.max(1_000, cfg.threading.counter4copyMax);
        int slotPoolSize = 2 * Runtime.getRuntime().availableProcessors();

        // For each i in includeList, compute per-table peak using the LARGEST
        // i opt sheets (sorted by encoded size desc) as the assumed combo.
        List<long[]> sheetSizes = new ArrayList<>();
        for (Short k : optKeys) {
            Stage st = stages.get(k);
            if (st == null) continue;
            BigInteger encB = st.rowCount.multiply(
                    BigInteger.valueOf(encodedArrayBytes(st.rowLen)));
            long enc = encB.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0
                    ? Long.MAX_VALUE : encB.longValueExact();
            sheetSizes.add(new long[]{ enc, st.rowLen });
        }
        sheetSizes.sort((a, b) -> Long.compare(b[0], a[0]));  // desc by encoded bytes

        BigInteger maxPerOptTable = BigInteger.ZERO;
        for (int i = 1; i <= optKeys.size(); i++) {
            if (!ks.contains(i)) continue;
            long topISourceBytes = 0L;
            long topISourceLen = 0L;
            for (int j = 0; j < i && j < sheetSizes.size(); j++) {
                topISourceBytes = addClamped(topISourceBytes, sheetSizes.get(j)[0]);
                topISourceLen  += sheetSizes.get(j)[1];
            }
            long batchBytes = (long) batchSize * encodedRowBytes(i, (int) topISourceLen);
            long perComboPeak = addClamped(topISourceBytes, batchBytes);
            long perTablePeak = mulClamped((long) slotPoolSize, perComboPeak);
            BigInteger pt = BigInteger.valueOf(perTablePeak);
            if (pt.compareTo(maxPerOptTable) > 0) maxPerOptTable = pt;
        }
        return maxPerOptTable;
    }

    private static long addClamped(long a, long b) {
        long sum = a + b;
        return (sum < a) ? Long.MAX_VALUE : sum;  // overflow guard
    }

    private static long mulClamped(long a, long b) {
        if (a == 0 || b == 0) return 0;
        long r = a * b;
        if (r / a != b) return Long.MAX_VALUE;
        return r;
    }

    // ── per-sheet stage walker ──────────────────────────────────────────

    /** Tracks (rowCount, rowLen) at each pipeline stage for one sheet. */
    static final class Stage {
        BigInteger rowCount = BigInteger.ONE;   // 1 logical "row" = the whole source list
        int        rowLen   = 0;                // length of that initial row = source.size()
        String     trace    = "";

        long bytesEstimate() {
            // bytes = rows × (cols × 2  +  per-row overhead)
            BigInteger cellBytes = rowCount.multiply(BigInteger.valueOf(2L * Math.max(1, rowLen)));
            BigInteger overheadBytes = rowCount.multiply(BigInteger.valueOf(ROW_REF_OVERHEAD_BYTES));
            BigInteger total = cellBytes.add(overheadBytes);
            return total.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0
                    ? Long.MAX_VALUE : total.longValueExact();
        }
    }

    private static Map<Short, Stage> computePerSheetStages(SeqParser.SeqParseResult seq,
                                                            ParsedWorkbook pw) {
        Map<Short, Stage> stages = new LinkedHashMap<>();
        for (var entry : seq.mapShKey2seqList.entrySet()) {
            Short key = entry.getKey();
            List<String> verbs = entry.getValue();
            List<Short> srcList = pw.sheetData.get(key);
            int srcSize = (srcList == null) ? 0 : srcList.size();

            Stage st = new Stage();
            st.rowCount = BigInteger.ONE;
            st.rowLen   = srcSize;
            StringBuilder trace = new StringBuilder().append("src(L=").append(srcSize).append(")");

            for (String verb : verbs) {
                applyVerb(verb, st, pw, stages, trace);
            }
            st.trace = trace.toString();
            stages.put(key, st);
        }
        return stages;
    }

    /** Mutates stage in-place by applying one verb's fanout (upper bound). */
    private static void applyVerb(String verb, Stage st,
                                  ParsedWorkbook pw,
                                  Map<Short, Stage> sheetsSoFar,
                                  StringBuilder trace) {
        String algoType = resolveAlgoType(verb);
        int m = resolveM(verb, algoType);

        BigInteger inRows = st.rowCount;
        int inLen = st.rowLen;
        BigInteger perRowOut = BigInteger.ONE;
        int outLen = inLen;

        switch (algoType) {
            case "FW_Combi":
                perRowOut = binom(inLen, m);
                outLen = m;
                break;
            case "FW_CombiR":
                perRowOut = binom(inLen + m - 1, m);
                outLen = m;
                break;
            case "FW_Permut":
                perRowOut = factorial(inLen);
                outLen = inLen;
                break;
            case "FW_PermutR":
                perRowOut = BigInteger.valueOf(inLen).pow(Math.max(0, m));
                outLen = m;
                break;
            case "FW_Subsets":
                perRowOut = subsetsRowCount(verb, inLen);
                outLen = inLen;  // worst-case: full subset
                break;
            case "FW_Cartes":
                int otherLen = cartesianOtherSize(verb, pw);
                perRowOut = BigInteger.valueOf((long) inLen * otherLen);
                outLen = 2;
                break;
            case "BRACE":
                // FW_(start,_,Ei,_,Ej,_,end,sep,formula) — operands are other sheets'
                // outputs.  Output rows ≈ |Ei| × |Ej| (pessimistic for any formula).
                BigInteger braceRows = braceRowCount(verb, pw, sheetsSoFar);
                int braceLen = braceRowLen(verb, pw, sheetsSoFar);
                st.rowCount = braceRows;
                st.rowLen = braceLen;
                trace.append(" -> brace(rows=").append(braceRows)
                     .append(", len=").append(braceLen).append(")");
                return;
            case "FW_Group":
            case "FW_Separator":
            case "FW_ReplaceRE":
            case "FW_Concatenator":
                // State-only verbs.  Don't change row count by themselves.  FW_Separator
                // INTERLEAVES into subsequent combo lengths (L → 2L-1) but only when
                // a subsequent combinatorial verb consumes it; modelled by next verb.
                trace.append(" -> ").append(algoType).append("(passthrough)");
                return;
            default:
                // Unknown verb: assume identity (no fanout, no change).  Pessimistic
                // about whether row count grows; if it does we under-estimate. Logged.
                log.debug("[Precompute] unknown verb '{}' on sheet stage — treating as identity", verb);
                trace.append(" -> ").append(algoType).append("(unknown)");
                return;
        }

        st.rowCount = inRows.multiply(perRowOut);
        st.rowLen = outLen;
        trace.append(" -> ").append(algoType)
             .append("(perRow=").append(perRowOut)
             .append(", outRows=").append(st.rowCount)
             .append(", outLen=").append(outLen).append(")");
    }

    // ── verb parsers (kept aligned with SheetWorker) ────────────────────

    private static String resolveAlgoType(String directive) {
        if (directive == null) return "UNKNOWN";
        if (directive.startsWith("FW_("))       return "BRACE";
        if (directive.startsWith("FW_CombiR"))  return "FW_CombiR";
        if (directive.startsWith("FW_Combi"))   return "FW_Combi";
        if (directive.startsWith("FW_PermutR")) return "FW_PermutR";
        if (directive.startsWith("FW_Permut"))  return "FW_Permut";
        if (directive.startsWith("FW_Subsets")) return "FW_Subsets";
        if (directive.startsWith("FW_Cartes"))  return "FW_Cartes";
        if (directive.startsWith("FW_Group"))   return "FW_Group";
        if (directive.startsWith("FW_Separator")) return "FW_Separator";
        if (directive.startsWith("FW_ReplaceRE")) return "FW_ReplaceRE";
        if (directive.startsWith("FW_Concatenator")) return "FW_Concatenator";
        return "UNKNOWN";
    }

    private static final Pattern PARAM_DIGIT = Pattern.compile("\\((\\d+)\\)");

    private static int resolveM(String directive, String algoType) {
        if (directive.endsWith(algoType) || directive.endsWith(algoType + "()")) return 1;
        Matcher m = PARAM_DIGIT.matcher(directive);
        if (m.find()) {
            try { return Integer.parseInt(m.group(1)); }
            catch (NumberFormatException ignored) {}
        }
        return 1;
    }

    /** Pessimistic upper bound for FW_Subsets variants.  Uses 2^n for DEFAULT;
     *  for modes uses sum of C(n,sz) over matching sizes. */
    private static BigInteger subsetsRowCount(String verb, int n) {
        if (n < 0) n = 0;
        if (!verb.contains("_") || verb.equals("FW_Subsets")) {
            return BigInteger.TWO.pow(n);
        }
        String modeStr = verb.replaceAll("FW_Subsets_|\\s+|[,]+|\\d+|\\(|\\)", "");
        int[] params = java.util.Arrays.stream(verb.replaceAll("[^\\d,]+", "").split(","))
                .filter(s -> !s.isEmpty()).mapToInt(Integer::parseInt).toArray();
        BigInteger total = BigInteger.ZERO;
        for (int sz = 0; sz <= n; sz++) {
            boolean match;
            switch (modeStr.toUpperCase()) {
                case "BEFORE": match = (params.length > 0) && sz < params[0]; break;
                case "AFTER":  match = (params.length > 0) && sz > params[0]; break;
                case "EXACT":  match = (params.length > 0) && sz == params[0]; break;
                case "RANGE":  match = (params.length > 1) && sz >= params[0] && sz <= params[1]; break;
                case "GIVEN":
                    boolean found = false;
                    for (int p : params) if (p == sz) { found = true; break; }
                    match = found; break;
                default:
                    return BigInteger.TWO.pow(n);  // unknown mode → fall back to 2^n
            }
            if (match) total = total.add(binom(n, sz));
        }
        return total;
    }

    /** Look up the FW_Cartes(otherSheetName) operand's source size. */
    private static int cartesianOtherSize(String verb, ParsedWorkbook pw) {
        int open = verb.indexOf('(');
        int close = verb.lastIndexOf(')');
        if (open < 0 || close <= open) return 1;
        String inner = verb.substring(open + 1, close);
        Short k = pw.stringShortSheetName2SheetKeyHM.get(inner);
        if (k == null) return 1;
        List<Short> other = pw.sheetData.get(k);
        return (other == null) ? 1 : other.size();
    }

    /** Estimate brace operation output row count.  Pessimistic: |Ei| × |Ej|. */
    private static BigInteger braceRowCount(String verb, ParsedWorkbook pw, Map<Short, Stage> sheetsSoFar) {
        List<String> parts = WorkbookParser.splitTopLevelByComma(
                verb.substring(verb.indexOf('(') + 1, verb.lastIndexOf(')')));
        BigInteger eiSize = operandSize(parts, 2, pw, sheetsSoFar);
        BigInteger ejSize = operandSize(parts, 4, pw, sheetsSoFar);
        return eiSize.multiply(ejSize);
    }

    /** Estimate brace output row length.  Sum of operand lengths + 4 slots
     *  (start, relation, sep, end at most contribute 4 short keys). */
    private static int braceRowLen(String verb, ParsedWorkbook pw, Map<Short, Stage> sheetsSoFar) {
        List<String> parts = WorkbookParser.splitTopLevelByComma(
                verb.substring(verb.indexOf('(') + 1, verb.lastIndexOf(')')));
        int eiLen = operandLen(parts, 2, pw, sheetsSoFar);
        int ejLen = operandLen(parts, 4, pw, sheetsSoFar);
        return eiLen + ejLen + 4;
    }

    private static BigInteger operandSize(List<String> parts, int idx,
                                          ParsedWorkbook pw,
                                          Map<Short, Stage> sheetsSoFar) {
        if (parts.size() <= idx) return BigInteger.ONE;
        String name = parts.get(idx).trim();
        if (name.isEmpty() || name.startsWith("FW_(")) return BigInteger.ONE;
        Short k = pw.stringShortSheetName2SheetKeyHM.get(name);
        if (k == null) return BigInteger.ONE;
        Stage upstream = sheetsSoFar.get(k);
        if (upstream != null) return upstream.rowCount;
        List<Short> src = pw.sheetData.get(k);
        return BigInteger.valueOf(src == null ? 1 : src.size());
    }

    private static int operandLen(List<String> parts, int idx,
                                   ParsedWorkbook pw,
                                   Map<Short, Stage> sheetsSoFar) {
        if (parts.size() <= idx) return 0;
        String name = parts.get(idx).trim();
        if (name.isEmpty() || name.startsWith("FW_(")) return 0;
        Short k = pw.stringShortSheetName2SheetKeyHM.get(name);
        if (k == null) return 0;
        Stage upstream = sheetsSoFar.get(k);
        if (upstream != null) return upstream.rowLen;
        List<Short> src = pw.sheetData.get(k);
        return (src == null) ? 0 : src.size();
    }

    // ── final-stage estimators ──────────────────────────────────────────

    private static BigInteger estimateFwFinal(SeqParser.SeqParseResult seq,
                                              Map<Short, Stage> stages,
                                              AppConfig cfg) {
        BigInteger rows = BigInteger.ONE;
        int len = 0;
        for (Short k : seq.toCombinatoricsHM.keySet()) {
            Stage st = stages.get(k);
            if (st == null) continue;
            rows = rows.multiply(st.rowCount.max(BigInteger.ONE));
            len += st.rowLen;
        }
        BigInteger cap = BigInteger.valueOf(cfg.threading.limitVarGivenLessThan);
        if (rows.compareTo(cap) > 0) rows = cap;
        return stageBytes(rows, len);
    }

    private static BigInteger estimateFwOpt(SeqParser.SeqParseResult seq,
                                            Map<Short, Stage> stages,
                                            AppConfig cfg) {
        List<Short> optKeys = new ArrayList<>(seq.toCombinatoricsHMoptional.keySet());
        if (optKeys.isEmpty()) return BigInteger.ZERO;
        Set<Integer> ks = Set.copyOf(cfg.optional.includeOptionalCombiPairsToDB);
        BigInteger total = BigInteger.ZERO;
        BigInteger combLimit = BigInteger.valueOf(cfg.optional.limitOptionalSheetsCombosMax);

        for (int i = 1; i <= optKeys.size(); i++) {
            if (!ks.contains(i)) continue;
            // C(n, i) combos × per-combo cartesian (pessimistic: max product over all
            // i-combos of opt sheets).  We approximate the max by sorting sheet sizes
            // descending and picking the top i.
            List<BigInteger> sortedRows = new ArrayList<>();
            List<Integer> sortedLens = new ArrayList<>();
            for (Short k : optKeys) {
                Stage st = stages.get(k);
                if (st == null) continue;
                sortedRows.add(st.rowCount);
                sortedLens.add(st.rowLen);
            }
            sortedRows.sort((a, b) -> b.compareTo(a));
            sortedLens.sort((a, b) -> b - a);

            BigInteger maxCombo = BigInteger.ONE;
            int maxLen = 0;
            for (int j = 0; j < i && j < sortedRows.size(); j++) {
                maxCombo = maxCombo.multiply(sortedRows.get(j));
                maxLen += sortedLens.get(j);
            }
            if (maxCombo.compareTo(combLimit) > 0) maxCombo = combLimit;
            BigInteger combosCount = binom(optKeys.size(), i);
            BigInteger perTable = combosCount.multiply(stageBytes(maxCombo, maxLen));
            total = total.add(perTable);
        }
        return total;
    }

    private static BigInteger stageBytes(Stage st) {
        return stageBytes(st.rowCount, st.rowLen);
    }

    private static BigInteger stageBytes(BigInteger rows, int len) {
        BigInteger cellBytes = rows.multiply(BigInteger.valueOf(2L * Math.max(1, len)));
        BigInteger overhead = rows.multiply(BigInteger.valueOf(ROW_REF_OVERHEAD_BYTES));
        return cellBytes.add(overhead);
    }

    // ── helpers ─────────────────────────────────────────────────────────

    private static BigInteger binom(int n, int k) {
        if (k < 0 || k > n) return BigInteger.ZERO;
        if (k == 0 || k == n) return BigInteger.ONE;
        if (k > n - k) k = n - k;
        BigInteger r = BigInteger.ONE;
        for (int i = 1; i <= k; i++) {
            r = r.multiply(BigInteger.valueOf(n - i + 1)).divide(BigInteger.valueOf(i));
        }
        return r;
    }

    private static BigInteger factorial(int n) {
        if (n < 0) return BigInteger.ZERO;
        BigInteger r = BigInteger.ONE;
        for (int i = 2; i <= n; i++) r = r.multiply(BigInteger.valueOf(i));
        return r;
    }

    /** Best-effort OS-free-RAM query via com.sun.management extension.
     *  Returns -1 if the bean isn't a SUN one (non-HotSpot JVM). */
    @SuppressWarnings("removal")
    private static long queryOsFreeRam() {
        try {
            var bean = ManagementFactory.getOperatingSystemMXBean();
            if (bean instanceof com.sun.management.OperatingSystemMXBean sunBean) {
                return sunBean.getFreeMemorySize();
            }
        } catch (Throwable t) { /* unsupported JVM */ }
        return -1L;
    }

    private static String formatBytes(BigInteger b) {
        if (b == null) return "n/a";
        if (b.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0) return ">9.2 EB (overflow)";
        return formatBytes(b.longValueExact());
    }

    private static String formatBytes(long b) {
        if (b < 0) return "n/a";
        if (b < 1024L) return b + " B";
        if (b < 1024L * 1024) return String.format("%.1f KB", b / 1024.0);
        if (b < 1024L * 1024 * 1024) return String.format("%.1f MB", b / (1024.0 * 1024));
        if (b < 1024L * 1024 * 1024 * 1024) return String.format("%.2f GB", b / (1024.0 * 1024 * 1024));
        return String.format("%.2f TB", b / (1024.0 * 1024 * 1024 * 1024));
    }

    // ── report ──────────────────────────────────────────────────────────

    public static final class Report {
        public final Decision decision;
        public final long maxHeapBytes;
        public final long heapBudgetBytes;
        public final long osFreeRamBytes;
        public final BigInteger perSheetBytesTotal;
        public final Map<Short, BigInteger> perSheetBytes;
        /** [Iter4.6] Streaming-aware fw_final peak (used for decision). */
        public final BigInteger fwFinalBytes;
        /** [Iter4.6] Streaming-aware fw_opt peak (used for decision). */
        public final BigInteger fwOptBytes;
        /** [Iter4.6] Theoretical full-materialised fw_final size (informational
         *  only — what the legacy estimator reported pre-Iter4.6; shown to
         *  expose the streaming-vs-materialised gap). */
        public final BigInteger fwFinalIfMaterialisedBytes;
        /** [Iter4.6] Theoretical full-materialised fw_opt size (informational). */
        public final BigInteger fwOptIfMaterialisedBytes;
        public final BigInteger estimatePeakBytes;
        public final BigInteger estimatePeakSafetiedBytes;
        public final String rationale;
        public final Mode mode;
        public final Map<Short, Stage> stages;

        Report(Decision decision, long maxHeapBytes, long heapBudgetBytes, long osFreeRamBytes,
               BigInteger perSheetBytesTotal, Map<Short, BigInteger> perSheetBytes,
               BigInteger fwFinalBytes, BigInteger fwOptBytes,
               BigInteger fwFinalIfMaterialisedBytes, BigInteger fwOptIfMaterialisedBytes,
               BigInteger peak, BigInteger peakSafetied,
               String rationale, Mode mode, Map<Short, Stage> stages) {
            this.decision = decision;
            this.maxHeapBytes = maxHeapBytes;
            this.heapBudgetBytes = heapBudgetBytes;
            this.osFreeRamBytes = osFreeRamBytes;
            this.perSheetBytesTotal = perSheetBytesTotal;
            this.perSheetBytes = perSheetBytes;
            this.fwFinalBytes = fwFinalBytes;
            this.fwOptBytes = fwOptBytes;
            this.fwFinalIfMaterialisedBytes = fwFinalIfMaterialisedBytes;
            this.fwOptIfMaterialisedBytes = fwOptIfMaterialisedBytes;
            this.estimatePeakBytes = peak;
            this.estimatePeakSafetiedBytes = peakSafetied;
            this.rationale = rationale;
            this.mode = mode;
            this.stages = stages;
        }

        public String render() {
            StringBuilder sb = new StringBuilder();
            sb.append("─── Precompute Layer 1 estimate (streaming model) ────\n");
            sb.append(String.format("mode                       : %s%n", mode));
            sb.append(String.format("-Xmx                       : %s%n", formatBytes(maxHeapBytes)));
            sb.append(String.format("heap budget (×%.2f)        : %s%n", GC_HEADROOM_FRACTION, formatBytes(heapBudgetBytes)));
            sb.append(String.format("OS free RAM                : %s%n",
                    osFreeRamBytes < 0 ? "n/a (non-Hotspot JVM)" : formatBytes(osFreeRamBytes)));
            sb.append(String.format("per-sheet peak (sum)       : %s%n", formatBytes(perSheetBytesTotal)));
            sb.append(String.format("fw_final peak (streamed)   : %s    [if materialised: %s]%n",
                    formatBytes(fwFinalBytes), formatBytes(fwFinalIfMaterialisedBytes)));
            sb.append(String.format("fw_opt peak (streamed)     : %s    [if materialised: %s]%n",
                    formatBytes(fwOptBytes), formatBytes(fwOptIfMaterialisedBytes)));
            sb.append(String.format("estimate (sum, streamed)   : %s%n", formatBytes(estimatePeakBytes)));
            sb.append(String.format("estimate × safety %.1f      : %s%n", SAFETY_FACTOR, formatBytes(estimatePeakSafetiedBytes)));
            sb.append(String.format("DECISION                   : %s%n", decision));
            sb.append(String.format("rationale                  : %s%n", rationale));
            sb.append("──────────────────────────────────────────────────────");
            return sb.toString();
        }
    }
}
