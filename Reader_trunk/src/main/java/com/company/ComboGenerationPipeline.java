package com.company;

import static com.company.ReaderConfig.*;
import com.company.io.ReaderIoStreams;
import java.util.concurrent.TimeUnit;
import com.company.helpers.DBStreamer;
import com.company.helpers.StreamRowWriter;
import com.company.helpers.*;
import net.lingala.zip4j.ZipFile;
import net.lingala.zip4j.exception.ZipException;
import net.lingala.zip4j.model.ZipParameters;
import net.lingala.zip4j.model.enums.CompressionMethod;
import java.io.*;
import java.lang.ref.SoftReference;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import static com.company.excel.Numerator.fwOpts;
import static com.company.excel.Numerator.columnNamesFirstRowStaticHM;
import static com.company.Main.*;

// Extracted from the Main god-class 2026-05-30 (behaviour-preserving Extract-Class).
/** SRP: the combinatorial generator/stream pipeline — the FINAL-ONLY pass, the
 *  CARTESIAN (x opt) pass, the virtual-thread executor lifecycle, and the post-run
 *  flush/verify/cleanup. VERBATIM move out of Main.main(); shared inputs are set as
 *  fields (by name, no positional swap) by Main before run().
 *
 *  ── perf 2026-07-02 rewrite of the two per-candidate hot loops ────────────────────────────
 *  The emitted candidate set, per-candidate bytes, filenames, sink rows and log structure are
 *  UNCHANGED. What changed is only how each candidate's bytes are produced:
 *   1. per-run KeyPlan — output keys / sheet prefixes / endings / base-row segments / a flat
 *      code→bytes table are resolved ONCE (they were re-looked-up per candidate through a
 *      LinkedHashMap clone + remove + removeIf + string-keyed maps + a ConcurrentHashMap with
 *      Short boxing per code element);
 *   2. per-row byte SEGMENTS — each DB row's per-column bytes (prefix+codes+separator) are
 *      assembled ONCE per row and then reused across every cartesian pair the row appears in
 *      (a row used to be re-decoded and re-concatenated for each of its up-to-millions pairs);
 *   3. per-pair work is now: pick the per-key segment (opt ▸ final ▸ base — the same override
 *      order the old merged-map clone produced), memcpy them into a reusable buffer, splice
 *      the FW_REPLACE marker at byte level (identical to the old decode→String.replace→encode
 *      round-trip, see Main.fwMarkerPositions), and hand the bytes to the unchanged emitters;
 *   4. virtual-thread tasks are BATCHED (a task processes a slice of pairs instead of one), so
 *      67.5M pairs cost ~0.5M task submissions instead of 67.5M;
 *   5. opt-chunk rows (as prebuilt segments) are cached per (table,low,high) in a SoftReference
 *      cache — when a run has several final chunks the same opt chunk is no longer re-read from
 *      Postgres once per final chunk (soft refs keep this memory-safe for huge tables).
 */
public final class ComboGenerationPipeline {

    Queue<String> outZipDirsConcurLQ;
    Map<String, byte[]> sheetNameMapByteArr;
    Map<String, byte[]> sheetNameMapEndingByteArr;
    ConcurrentHashMap<Short, ByteArrayOutputStream> concurrentHashMapKVbyteArrStream;
    byte[] bArr;
    LinkedHashMap<String, Object> rowDbFieldDbCellHMbaseKeysRefined;
    Map<Long, LinkedHashMap<Integer, short[]>>[] curMap4readerFinal;
    List<String> fwFinals;
    List<Long> fwFinalsMaxCombiIds;
    List<Long> fwOptsMaxCombiIds;
    boolean isOpt;
    BigInteger control;
    List arrayListKeysRefined;
    long desiredCurrentChunkFinal;
    long desiredCurrentChunkOpt;
    long[] combiIdLowLimitFinal;
    long[] combiIdHighLimitFinal;
    Map<String, List<Map.Entry<Long, Long>>> table2combiIdChunksEntryFinals;
    Map<String, List<Map.Entry<Long, Long>>> table2combiIdChunksEntryOpts;
    int numOfColumnsIn_fw_final_base_copy_Total;
    QueryToDB2 q2d;
    QueryToDB q2d1;
    QueryToDB2 q2d4reader;
    QueryToDB2 q2d4reader2;
    DataBaseManager2 q2dbMgr;

    /** Pairs (or rows) per virtual-thread task. Small enough to keep cancel/pacing granular,
     *  large enough that task-submission overhead disappears from the profile. */
    private static final int TASK_BATCH = 128;

    private static final byte[] EMPTY_BYTES = new byte[0];
    /** Identity sentinel for a key whose sheet name/ending mapping is missing. The legacy code
     *  NPE'd inside the writer task for such a key, silently dropping the whole candidate (the
     *  Future was never inspected); candidates picking a poisoned key are dropped the same way. */
    private static final byte[] POISON_SEG = new byte[0];

    // ── per-run write plan (immutable after build; shared read-only by every writer task) ──
    private static final class KeyPlan {
        final String[] keys;            // output keys in base-map order, "combi_id" excluded
        final byte[][] namePrefix;      // sheet name bytes per key (null → poisoned key)
        final byte[][] ending;          // sheet ending bytes per key (may be null when FW_B_ARR set)
        final int[] sepTrim;            // trailing separator length per key
        final boolean[] poison;         // missing name (or missing ending while FW_B_ARR empty)
        final byte[][] baseSeg;         // prebuilt segment for the base row's value (null → absent)
        final short[][] baseVal;        // base row short[] per key (null → absent)
        final int[] colIdxToJ;          // 1-based DB column index → key position; -1 = not mapped
        final byte[][] codeBytes;       // flat code → bytes; index = code - Short.MIN_VALUE
        final byte[] fwBArr;
        final int fwBArrLen;

        KeyPlan(String[] keys, byte[][] namePrefix, byte[][] ending, int[] sepTrim, boolean[] poison,
                byte[][] baseSeg, short[][] baseVal, int[] colIdxToJ, byte[][] codeBytes,
                byte[] fwBArr) {
            this.keys = keys;
            this.namePrefix = namePrefix;
            this.ending = ending;
            this.sepTrim = sepTrim;
            this.poison = poison;
            this.baseSeg = baseSeg;
            this.baseVal = baseVal;
            this.colIdxToJ = colIdxToJ;
            this.codeBytes = codeBytes;
            this.fwBArr = fwBArr;
            this.fwBArrLen = fwBArr.length;
        }
    }

    /** One DB row, pre-rendered: per-key byte segment + raw values (for the bond filter). */
    private static final class SegRow {
        final long id;
        final String idStr;
        final byte[][] seg;     // per key j; null = key absent in this row; POISON_SEG = drop
        final short[][] val;    // per key j; null = absent
        final boolean poison;   // row referenced an unmappable column (legacy: task died silently)

        SegRow(long id, String idStr, byte[][] seg, short[][] val, boolean poison) {
            this.id = id;
            this.idStr = idStr;
            this.seg = seg;
            this.val = val;
            this.poison = poison;
        }
    }

    private KeyPlan buildKeyPlan() {
        // flat code → bytes table (replaces per-element CHM lookup + Short boxing;
        // a miss used to resolve to an empty array — null plays that role here)
        final byte[][] codeBytes = new byte[65536][];
        for (Map.Entry<Short, ByteArrayOutputStream> e : concurrentHashMapKVbyteArrStream.entrySet()) {
            codeBytes[e.getKey() - Short.MIN_VALUE] = e.getValue().toByteArray();
        }

        final byte[] fwBArr = (FW_B_ARR == null) ? EMPTY_BYTES : FW_B_ARR;

        final ArrayList<String> keyList = new ArrayList<>(rowDbFieldDbCellHMbaseKeysRefined.size());
        final ArrayList<Object> baseValues = new ArrayList<>(rowDbFieldDbCellHMbaseKeysRefined.size());
        for (Map.Entry<String, Object> e : rowDbFieldDbCellHMbaseKeysRefined.entrySet()) {
            if ("combi_id".equals(e.getKey())) continue;   // legacy clone.remove("combi_id")
            keyList.add(e.getKey());
            baseValues.add(e.getValue());
        }
        final int K = keyList.size();
        final String[] keys = keyList.toArray(new String[0]);
        final byte[][] namePrefix = new byte[K][];
        final byte[][] ending = new byte[K][];
        final int[] sepTrim = new int[K];
        final boolean[] poison = new boolean[K];
        for (int j = 0; j < K; j++) {
            namePrefix[j] = sheetNameMapByteArr.get(keys[j]);
            ending[j] = sheetNameMapEndingByteArr.get(keys[j]);
            poison[j] = (namePrefix[j] == null) || (fwBArr.length == 0 && ending[j] == null);
            sepTrim[j] = (fwBArr.length > 0) ? fwBArr.length : (ending[j] == null ? 0 : ending[j].length);
        }

        final int[] colIdxToJ = new int[Math.max(numOfColumnsIn_fw_final_base_copy_Total, arrayListKeysRefined.size()) + 2];
        Arrays.fill(colIdxToJ, -1);
        final Map<String, Integer> keyPos = new HashMap<>();
        for (int j = 0; j < K; j++) keyPos.put(keys[j], j);
        for (int colIdx = 1; colIdx <= arrayListKeysRefined.size(); colIdx++) {
            Integer j = keyPos.get((String) arrayListKeysRefined.get(colIdx - 1));
            if (j != null && colIdx < colIdxToJ.length) colIdxToJ[colIdx] = j;
        }

        final KeyPlan plan = new KeyPlan(keys, namePrefix, ending, sepTrim, poison,
                new byte[K][], new short[K][], colIdxToJ, codeBytes, fwBArr);
        for (int j = 0; j < K; j++) {
            Object v = baseValues.get(j);
            if (v instanceof short[] sv) {
                plan.baseVal[j] = sv;
                plan.baseSeg[j] = buildSegment(plan, j, sv);
            }
        }
        return plan;
    }

    /** prefix + code bytes (NULL_ELEMENT skipped) + separator — the exact byte layout the
     *  legacy per-candidate loop wrote for one key. */
    private static byte[] buildSegment(KeyPlan p, int j, short[] v) {
        if (p.poison[j]) return POISON_SEG;
        final byte[][] cb = p.codeBytes;
        int len = p.namePrefix[j].length;
        for (short sh : v) {
            if (sh == CopyToReader.NULL_ELEMENT) continue;
            byte[] b = cb[sh - Short.MIN_VALUE];
            if (b != null) len += b.length;
        }
        final byte[] sep = (p.fwBArrLen > 0) ? p.fwBArr : p.ending[j];
        len += sep.length;
        final byte[] out = new byte[len];
        int pos = p.namePrefix[j].length;
        System.arraycopy(p.namePrefix[j], 0, out, 0, pos);
        for (short sh : v) {
            if (sh == CopyToReader.NULL_ELEMENT) continue;
            byte[] b = cb[sh - Short.MIN_VALUE];
            if (b == null) continue;
            System.arraycopy(b, 0, out, pos, b.length);
            pos += b.length;
        }
        System.arraycopy(sep, 0, out, pos, sep.length);
        return out;
    }

    private static SegRow buildSegRow(KeyPlan p, long id, LinkedHashMap<Integer, short[]> cols) {
        final int K = p.keys.length;
        final byte[][] seg = new byte[K][];
        final short[][] val = new short[K][];
        boolean rowPoison = false;
        for (Map.Entry<Integer, short[]> e : cols.entrySet()) {
            final int colIdx = e.getKey();
            if (colIdx < 0 || colIdx >= p.colIdxToJ.length) { rowPoison = true; continue; }
            final int j = p.colIdxToJ[colIdx];
            if (j < 0) { rowPoison = true; continue; }   // legacy: keys lookup would have thrown
            final short[] v = e.getValue();
            val[j] = v;
            seg[j] = buildSegment(p, j, v);
        }
        return new SegRow(id, Long.toString(id), seg, val, rowPoison);
    }

    private static SegRow[] buildSegRows(KeyPlan p, Map<Long, LinkedHashMap<Integer, short[]>> map) {
        final SegRow[] out = new SegRow[map.size()];
        int i = 0;
        for (Map.Entry<Long, LinkedHashMap<Integer, short[]>> e : map.entrySet()) {
            out[i++] = buildSegRow(p, e.getKey(), e.getValue());
        }
        return out;
    }

    /** Reusable per-task assembly state (one instance per batch task; never shared). */
    private static final class Assembler {
        final byte[][] pick;
        byte[] buf = new byte[4096];
        int len = 0;
        int lastJ = -1;
        boolean dropped = false;

        Assembler(int K) { this.pick = new byte[K][]; }

        /** Pick per-key segments (opt ▸ final ▸ base) and concatenate into the reusable buffer.
         *  Sets {@link #dropped} when a poisoned key is picked (legacy silent-NPE candidate drop). */
        void assemble(KeyPlan p, SegRow fRow, SegRow oRow) {
            final int K = p.keys.length;
            int total = 0;
            int last = -1;
            dropped = false;
            for (int j = 0; j < K; j++) {
                byte[] s = (oRow != null && oRow.seg[j] != null) ? oRow.seg[j]
                        : (fRow != null && fRow.seg[j] != null) ? fRow.seg[j]
                        : p.baseSeg[j];
                pick[j] = s;
                if (s == null) continue;
                if (s == POISON_SEG) { dropped = true; return; }
                total += s.length;
                last = j;
            }
            if (buf.length < total) buf = new byte[Math.max(total, buf.length * 2)];
            int pos = 0;
            for (int j = 0; j < K; j++) {
                byte[] s = pick[j];
                if (s == null) continue;
                System.arraycopy(s, 0, buf, pos, s.length);
                pos += s.length;
            }
            len = pos;
            lastJ = last;
        }

        int trim(KeyPlan p) { return (lastJ < 0) ? 0 : p.sepTrim[lastJ]; }
    }

    /** Everything the shared emitter needs that is constant for the whole run. */
    private record EmitEnv(KeyPlan plan,
                           com.company.sink.CandidateSink looseSink,
                           BackpressureGate bpGate,
                           LongAdder counter,
                           String[] zipDirs,
                           java.util.concurrent.atomic.AtomicInteger zipDirRR,
                           boolean zipMode,
                           boolean filesMode,
                           boolean replaceMode) {}

    /**
     * One assembled candidate → RowSink tap + zip / loose-file / joined-record emission.
     * Byte-exact port of the two legacy emission blocks:
     *  - sink row: TRIM first, then marker-replace with {@code sinkTag} (legacy replaceAll order);
     *  - loose file: sleep, marker-replace over the FULL payload with {@code fileTag}, THEN trim;
     *  - zip: full payload, untrimmed, un-replaced;
     *  - joined record: trim, then replace with {@code fileTag} (inside emitJoinedRecordBytes).
     */
    private static void emitCandidate(EmitEnv env, Assembler a,
                                      long sinkId, String sinkTag, String fileTag,
                                      String zipEntryName, String zipBaseName, String sinkFailLabel) {
        final KeyPlan p = env.plan;
        env.counter.increment();

        if (com.company.sink.RowSinkRegistry.isActive()) {
            try {
                final int end = Math.max(0, a.len - a.trim(p));
                String row;
                int[] pos = env.replaceMode ? fwMarkerPositions(a.buf, end) : null;
                if (pos != null) {
                    byte[] spl = fwSpliceMarkers(a.buf, end, pos, sinkTag.getBytes(StandardCharsets.UTF_8));
                    row = new String(spl, StandardCharsets.UTF_8);
                } else {
                    row = new String(a.buf, 0, end, StandardCharsets.UTF_8);
                }
                com.company.sink.RowSinkRegistry.current().accept(sinkId, row);
            } catch (RuntimeException __sinkEx) {
                // Sink failure must not break the file/zip emission.
                System.err.println("[Analyzer] sink dispatch failed (" + sinkFailLabel + "): " + __sinkEx);
            }
        }

        if (env.zipMode) {
            ZipParameters zipParameters = new ZipParameters();
            zipParameters.setCompressionMethod(CompressionMethod.DEFLATE);
            zipParameters.setFileNameInZip(zipEntryName);
            try {
                // RACE FIX (2026-07-02): thread-safe round-robin over the output dirs. The legacy
                // element()/remove()/add() queue rotation raced under concurrent writers — a
                // momentarily-empty queue threw NoSuchElementException inside the writer task and
                // SILENTLY dropped ~1% of zip candidates per run (verified: baseline reruns emit
                // different zip counts, all below control). Mirrors the May29 __dirRR fix the
                // loose-file path received.
                final String __zipDir = env.zipDirs[Math.floorMod(env.zipDirRR.getAndIncrement(), env.zipDirs.length)];
                new ZipFile(__zipDir + zipBaseName + ".zip")
                        .addStream(new java.io.ByteArrayInputStream(a.buf, 0, a.len), zipParameters);
            } catch (ZipException e6) {
                e6.printStackTrace();
            }
        } else if (env.filesMode) {
            try {
                Thread.sleep(FILE_GENERATION_DELAY_properties);
            } catch (InterruptedException e1) {
                e1.printStackTrace();
            }
            byte[] outBytes = a.buf;
            int outLen = a.len;
            if (env.replaceMode) {
                int[] pos = fwMarkerPositions(a.buf, a.len);
                if (pos != null) {
                    outBytes = fwSpliceMarkers(a.buf, a.len, pos, fileTag.getBytes(StandardCharsets.UTF_8));
                    outLen = outBytes.length;
                }
            }
            int __n = Math.max(0, outLen - a.trim(p));
            // STEP 34: atomically admit into the bounded queue; if cancelled (admit==false), DO NOT write —
            // a cancelled run must stop growing candidate artifacts.
            if (env.bpGate == null || env.bpGate.admit()) {
                // STEP 31: persist via the candidate sink (loose-file writer).
                env.looseSink.write(fileTag, outBytes, 0, __n);
            }
        } else {
            emitJoinedRecordBytes(a.buf, a.len, a.trim(p), fileTag);
        }
    }

    void run() throws java.sql.SQLException {
        // re-declared local: reassigned in the trailing cleanup; pre-span uses in main() were dead no-ops
        LinkedHashMap<String, Object> rowDbFieldDbCellHM;
        List keysOfMap;
        int indexOfMap;

// perf 2026-07-02: LongAdder — 67.5M concurrent increments no longer CAS-contend on one cell;
// sum() is exact at every point it is read here (all writers are awaited first), and the
// mid-run log reads were always approximate by nature.
LongAdder counter = new LongAdder();

// STEP 31: loose-file candidate output now goes through a CandidateSink. The sink
// owns directory round-robin, filename construction, the temp+atomic-move+retry
// write, and the authoritative count/bytes/index tally — the pipeline no longer
// knows those filename-writer details. One instance is shared by both the
// FINAL-only and CARTESIAN passes so the round-robin and tally span the whole run.
// Created only for the loose-file transport (FILES_MODE && !ZIP_MODE); null otherwise
// (ZIP / in-memory "read everything and concatenate" streaming keep their existing
// paths untouched — no sink runs, so none of the STEP 31 gates below apply to them).
com.company.sink.CandidateSinkRegistry.reset(); // no stale summary leaks into this run's manifest
// STEP 32: the candidate sink is now selectable (reader.out.candidateSink). "loose-files"
// (default) is byte-for-byte the pre-STEP-32 path; "sharded" packs candidates into compressed
// shard containers (ShardSink) written into the FIRST output dir, to cut inode pressure.
com.company.sink.CandidateSink __sinkTmp = null;
if (cfg().filesMode() && !cfg().zipMode()) {
String __sinkSel = (cfg().candidateSink() == null) ? "loose-files" : cfg().candidateSink().trim();
if (__sinkSel.equalsIgnoreCase("sharded") || __sinkSel.equalsIgnoreCase("compressed-shards")) {
String __first = cfg().pathFwOutZipDirList().get(0);
String __norm = (__first.endsWith("/") || __first.endsWith("\\")) ? __first.substring(0, __first.length() - 1) : __first;
__sinkTmp = new com.company.sink.ShardSink(java.nio.file.Path.of(__norm), bArr,
        cfg().shardMaxRecords(), cfg().shardMaxBytes(),
        com.company.sink.ShardSink.DEFAULT_RUN_SIZE, cfg().shardResume());
System.out.println("  [sink] candidate transport = sharded  dir=" + __norm
        + "  maxRecords=" + cfg().shardMaxRecords() + "  maxBytes=" + cfg().shardMaxBytes()
        + "  resume=" + cfg().shardResume());
} else if (__sinkSel.equalsIgnoreCase("grpc")) {
// gRPC candidate transport (2026-07-02): stream candidates live to the Executor's
// -grpcPort server instead of writing files. The sink's constructor preflights the
// connection and THROWS when no Executor listens — the run aborts before emission
// rather than silently producing nothing (fail-closed).
__sinkTmp = new com.company.sink.GrpcCandidateSink(cfg().grpcTarget(), bArr);
System.out.println("  [sink] candidate transport = grpc  target=" + cfg().grpcTarget());
} else {
__sinkTmp = new com.company.sink.LooseFileSink(cfg().pathFwOutZipDirList(), cfg().fwFileExtension(), bArr);
}
}
final com.company.sink.CandidateSink __looseSink = __sinkTmp;
final boolean __shardSink = __looseSink instanceof com.company.sink.ShardSink;
// gRPC transport: candidates leave over the wire — like shards, a loose-file on-disk
// count is meaningless; delivery is reconciled against the Executor's stream receipt.
final boolean __grpcSink = __looseSink instanceof com.company.sink.GrpcCandidateSink;

// STEP 34: closed-loop backpressure gate (complements the open-loop FILE_GENERATION_DELAY rampup
// below). When a backpressure state dir is configured, the producer PAUSES before emitting a
// candidate while the in-flight depth (produced − consumed, the latter published by the
// directory-watching Executor) is at/above the high watermark — so a slow Executor can never be
// outrun unboundedly. Inactive (null) by default → emission paced only by the rampup, unchanged.
com.company.BackpressureGate __bpTmp = null;
if (cfg().filesMode() && !cfg().zipMode()
        && cfg().backpressureDir() != null && !cfg().backpressureDir().isBlank()) {
    try {
        __bpTmp = new com.company.BackpressureGate(java.nio.file.Path.of(cfg().backpressureDir()),
                cfg().backpressureHigh(), cfg().backpressureLow());
        System.out.println("  [backpressure] gate active  dir=" + cfg().backpressureDir()
                + "  high=" + cfg().backpressureHigh() + "  low=" + cfg().backpressureLow());
    } catch (java.io.IOException __bpe) {
        System.err.println("[backpressure] gate init failed (continuing ramp-only): " + __bpe);
    }
}
final com.company.BackpressureGate __bpGate = __bpTmp;
// STEP 31 fail-closed: deferred reconciliation reason. Set at end-of-run if the sink's
// authoritative tally disagrees with the pipeline (counter) or the filesystem (on-disk),
// or if any candidate failed to persist; thrown after cleanup so the run aborts and no
// handoff manifest is written for a partial/corrupted candidate set.
String __sinkReconcileMsg = null;

Object lock28032021 = new Object();
Thread thread = new Thread(() -> {

int FILE_GENERATION_DELAY_min = Integer.parseInt(String.valueOf(FILE_GENERATION_DELAY_properties));
FILE_GENERATION_DELAY_properties = Integer.parseInt(String.valueOf(cfg().fileGenerationInitialDelay()));

while (FILE_GENERATION_DELAY_properties > cfg().fileGenerationIntermediateDelay()) {
try {
Thread.sleep(cfg().fileGenerationDelayRampup00());
if (FILE_GENERATION_DELAY_properties > cfg().fileGenerationIntermediateDelay())
FILE_GENERATION_DELAY_properties = FILE_GENERATION_DELAY_properties - cfg().fileGenerationDelayRampup00Delta();
} catch (InterruptedException e) {
e.printStackTrace();
}
}
try {
Thread.sleep(cfg().fileGenerationDelayRampup00WaitRampup0());
} catch (InterruptedException e) {
e.printStackTrace();
}
while (FILE_GENERATION_DELAY_properties > FILE_GENERATION_DELAY_min) {
try {
Thread.sleep(cfg().fileGenerationDelayRampup0());
if (FILE_GENERATION_DELAY_properties > FILE_GENERATION_DELAY_min)
FILE_GENERATION_DELAY_properties = FILE_GENERATION_DELAY_properties - cfg().fileGenerationDelayRampup0Delta();
} catch (InterruptedException e) {
e.printStackTrace();
}
}
});
thread.start();

ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

// STEP 34: on a shared cancel, shut down the producer pools so the run terminates EARLY instead
// of running every queued candidate task to completion. Driver pools are registered as created.
final com.company.ProducerCancellation __bpCancel =
        (__bpGate != null) ? new com.company.ProducerCancellation(__bpGate) : null;
if (__bpCancel != null) __bpCancel.register(executor);

System.out.println();
System.out.println("================================================================");
System.out.println("DATA PROCESSING — STAGE ANALYSIS");
System.out.println("================================================================");
long __stageStartNanos = System.nanoTime();
System.out.println("Flags:");
System.out.println("  isOpt                          = " + isOpt);
System.out.println("  IS_PROCESS_BOTH_FINAL_AND_OPT  = " + cfg().isProcessBothFinalAndOpt());
System.out.println("  STREAMING_DIRECT_WRITE_ENABLED = " + STREAMING_DIRECT_WRITE_ENABLED);
System.out.println("  ZIP_MODE                       = " + cfg().zipMode());
System.out.println("  FILES_MODE                     = " + cfg().filesMode());
System.out.println("  FW_GENERAL_TIMEOUT_TO_STOP_min = " + cfg().fwGeneralTimeoutToStop());
System.out.println("Chunking:");
System.out.println("  desiredCurrentChunkFinal       = " + desiredCurrentChunkFinal);
System.out.println("  desiredCurrentChunkOpt         = " + desiredCurrentChunkOpt);
System.out.println("Column shape:");
System.out.println("  numOfColumnsIn_fw_final_base_copy_Total = " + numOfColumnsIn_fw_final_base_copy_Total);
System.out.println("Tables (fwFinals):");
if (fwFinals == null || fwFinals.isEmpty()) {
System.out.println("  (EMPTY — no fw_final* tables selected; final-only pass will be a no-op)");
} else {
long __totalFinalChunks = 0L;
for (int __i = 0; __i < fwFinals.size(); __i++) {
String __t = fwFinals.get(__i);
int __chunks = (table2combiIdChunksEntryFinals.get(__t) != null)
? table2combiIdChunksEntryFinals.get(__t).size() : 0;
__totalFinalChunks += __chunks;
String __mode = TableSchemaInspector.useRealCombiId(__t) ? "real" : "virtual(row_number)";
System.out.println("  [" + (__i + 1) + "/" + fwFinals.size() + "] public." + __t
+ "  max_id=" + fwFinalsMaxCombiIds.get(__i)
+ "  chunks=" + __chunks
+ "  id-mode=" + __mode);
}
System.out.println("  total_final_chunks             = " + __totalFinalChunks);
}
System.out.println("Tables (fwOpts):");
if (!isOpt || fwOpts == null || fwOpts.isEmpty()) {
System.out.println("  (none / isOpt=" + isOpt + "; cartesian pass will be a no-op)");
} else {
long __totalOptChunks = 0L;
for (int __j = 0; __j < fwOpts.size(); __j++) {
String __t = fwOpts.get(__j);
int __chunks = (table2combiIdChunksEntryOpts.get(__t) != null)
? table2combiIdChunksEntryOpts.get(__t).size() : 0;
__totalOptChunks += __chunks;
String __mode = TableSchemaInspector.useRealCombiId(__t) ? "real" : "virtual(row_number)";
System.out.println("  [" + (__j + 1) + "/" + fwOpts.size() + "] public." + __t
+ "  max_id=" + fwOptsMaxCombiIds.get(__j)
+ "  chunks=" + __chunks
+ "  id-mode=" + __mode);
}
System.out.println("  total_opt_chunks               = " + __totalOptChunks);
}
boolean __willFinalOnlyBranch = !isOpt || cfg().isProcessBothFinalAndOpt();
boolean __willCartesianBranch = isOpt;
boolean __willStreamingSubPath = STREAMING_DIRECT_WRITE_ENABLED && !cfg().isProcessBothFinalAndOpt();
System.out.println("Predicted execution path:");
System.out.println("  FINAL-ONLY pass       : " + (__willFinalOnlyBranch ? "WILL RUN" : "SKIPPED"));
System.out.println("    └─ STREAMING-DIRECT sub-path : " + (__willStreamingSubPath ? "WILL RUN (replaces load+map path for finals)"
: "SKIPPED (needs STREAMING_DIRECT_WRITE_ENABLED=true AND IS_PROCESS_BOTH_FINAL_AND_OPT=false)"));
System.out.println("  CARTESIAN pass (×opt) : " + (__willCartesianBranch ? "WILL RUN" : "SKIPPED (isOpt=false)"));
if (__willFinalOnlyBranch && (fwFinals == null || fwFinals.isEmpty())) {
System.out.println("  WARNING: final-only pass scheduled but fwFinals is empty — no output will be produced from this branch.");
}
if (__willCartesianBranch && (fwOpts == null || fwOpts.isEmpty() || fwFinals == null || fwFinals.isEmpty())) {
System.out.println("  WARNING: cartesian pass scheduled but fwOpts or fwFinals is empty — no output will be produced from this branch.");
}
System.out.println("Expected control (combi products) = " + control);
System.out.println("Executor: virtual-thread-per-task (Executors.newVirtualThreadPerTaskExecutor)");
System.out.println("================================================================");
System.out.println();

// ── perf 2026-07-02: one-time write plan (see class javadoc) ──
// Pacing preservation: in loose-file mode every candidate sleeps FILE_GENERATION_DELAY on its
// own virtual thread — that sleep CONCURRENCY (in-flight cap ÷ task size) is part of the
// configured rate limitation, so there the task unit stays ONE candidate (batch=1), exactly
// like the legacy task-per-candidate submission. Only the no-sleep transports (zip /
// joined-record concatenation) batch candidates per task to amortize submission overhead.
final int __taskBatch = (cfg().filesMode() && !cfg().zipMode()) ? 1 : TASK_BATCH;
final KeyPlan __plan = buildKeyPlan();
final EmitEnv __env = new EmitEnv(__plan, __looseSink, __bpGate, counter,
        new ArrayList<>(outZipDirsConcurLQ).toArray(new String[0]),
        new java.util.concurrent.atomic.AtomicInteger(0),
        cfg().zipMode(), cfg().filesMode(), fw_replace_me_with_current_combo_sequence_mode);
{
    int __poisoned = 0;
    for (boolean b : __plan.poison) if (b) __poisoned++;
    if (__poisoned > 0) {
        System.out.println("  WARNING: " + __poisoned + " output key(s) lack a sheet name/ending mapping — "
                + "candidates containing them are dropped (legacy writer-task behaviour preserved).");
    }
}

if (!isOpt || cfg().isProcessBothFinalAndOpt()) {

System.out.println(">>> STAGE: FINAL-ONLY pass ENTERED  (fwFinals.size()=" + fwFinals.size() + ")");
long __finalStageStart = System.nanoTime();
long __finalChunkIndex = 0L;

final int __maxInFlightFinal = 20_000;

final int __streamFetchSizeFinal = 500;
System.out.println("  (stream tuning: fetchSize=" + __streamFetchSizeFinal
+ ", maxInFlightSubmits=" + __maxInFlightFinal + ")");

for (int i = 0; i < fwFinals.size(); i++) {
final String __currentFinalTable = fwFinals.get(i);
final List<Map.Entry<Long, Long>> __thisTableChunks = table2combiIdChunksEntryFinals.get(__currentFinalTable);
final int __chunkCountForTable = (__thisTableChunks == null) ? 0 : __thisTableChunks.size();
final boolean __isVirtualFor__i = !TableSchemaInspector.useRealCombiId(__currentFinalTable);
System.out.println("  FINAL-ONLY: [" + (i + 1) + "/" + fwFinals.size() + "] table=public." + __currentFinalTable
+ "  chunks=" + __chunkCountForTable
+ "  id-mode=" + (__isVirtualFor__i ? "virtual(row_number)" : "real"));
if (__chunkCountForTable == 0) {
System.out.println("    (no chunks for this table — skipping silently in legacy code; skipping here too)");
continue;
}

List<String> __plannedSqls = new ArrayList<>();
List<String> __plannedLabels = new ArrayList<>();
if (__isVirtualFor__i) {
try {
List<CtidPartitioner.Range> __ranges = CtidPartitioner.partition(__currentFinalTable, STREAM_PARALLELISM_FINAL);
int __pi = 0;
for (CtidPartitioner.Range __r : __ranges) {
__pi++;
__plannedSqls.add(CtidPartitioner.partitionedVirtualQuery(__currentFinalTable, __r));
__plannedLabels.add("virtual partition " + __pi + "/" + __ranges.size()
+ "  ctid blocks [" + __r.blockLow() + ".."
+ (__r.blockHigh() == Long.MAX_VALUE ? "end" : String.valueOf(__r.blockHigh())) + ")");
}
System.out.println("    parallel virtual streaming: " + __ranges.size()
+ " ctid partition(s)  (parallelism=" + STREAM_PARALLELISM_FINAL
+ ", bypassing " + __chunkCountForTable + " range chunks)");
} catch (SQLException __pe) {
System.out.println("    fallback: ctid partitioning failed (" + __pe + ") — single full-ordered streaming pass");
__plannedSqls.clear();
__plannedLabels.clear();
__plannedSqls.add(TableSchemaInspector.fullOrderedQuery(__currentFinalTable));
__plannedLabels.add("single streaming pass (virtual mode — fallback)");
}
} else {
int __c = 0;
for (Map.Entry<Long, Long> __ch : __thisTableChunks) {
__c++;
__plannedSqls.add(TableSchemaInspector.rangeQuery(__currentFinalTable, __ch.getKey(), __ch.getValue()));
__plannedLabels.add("chunk " + __c + "/" + __chunkCountForTable
+ "  combi_id BETWEEN " + __ch.getKey() + " AND " + __ch.getValue());
}
System.out.println("    parallel real-mode streaming: " + __plannedSqls.size()
+ " chunk(s)  (parallelism=" + STREAM_PARALLELISM_FINAL + ")");
}

final int __numCols = numOfColumnsIn_fw_final_base_copy_Total;
// perf: permits scaled by TASK_BATCH so outstanding submitted-not-executed ROWS stay ≈ the
// legacy 20k bound (each permit now covers one batch task instead of one row task).
final java.util.concurrent.Semaphore __inflight =
        new java.util.concurrent.Semaphore(Math.max(STREAM_PARALLELISM_FINAL, __maxInFlightFinal / __taskBatch));
final java.util.concurrent.atomic.AtomicLong __streamedRows = new java.util.concurrent.atomic.AtomicLong(0);

final java.util.concurrent.atomic.AtomicLong __virtualGlobalId = new java.util.concurrent.atomic.AtomicLong(0L);
final boolean __useVirtualGlobalId = __isVirtualFor__i;
final long __streamStart = System.nanoTime();

final boolean __streamingDirectActive = STREAMING_DIRECT_WRITE_ENABLED && !cfg().isProcessBothFinalAndOpt();

Heartbeat __hb = Heartbeat.start("streaming " + __currentFinalTable
+ "  rowsStreamed=… (see __streamedRows)", 5000L);

final int __driverParallelism = __streamingDirectActive ? 1 :
Math.max(1, Math.min(__plannedSqls.size(), STREAM_PARALLELISM_FINAL));
final ExecutorService __driverPool = Executors.newFixedThreadPool(__driverParallelism, r -> {
Thread t = new Thread(r, "fw-final-driver-" + __currentFinalTable);
t.setDaemon(true);
return t;
});
if (__bpCancel != null) __bpCancel.register(__driverPool);   // STEP 34: shutdownNow on cancel
final List<Future<?>> __driverFutures = new ArrayList<>(__plannedSqls.size());

try {
for (int __qi = 0; __qi < __plannedSqls.size(); __qi++) {
__finalChunkIndex++;
final String __label = __plannedLabels.get(__qi);
final String __sql = __plannedSqls.get(__qi);

if (__streamingDirectActive) {
System.out.println("    " + __label + "  (runningCounter=" + counter.sum() + ")");
try {
System.out.println("      [STREAMING-DIRECT] fetchSize=100");
final long __sdStart = System.nanoTime();
final long[] __streamRows = {0L};
final StreamRowWriter __rowWriter = new StreamRowWriter();
// perf: flat array lookup (was: CHM get + Short boxing + defensive toByteArray copy per code)
final byte[][] __codeFlat = __plan.codeBytes;
final StreamRowWriter.CodeBytesResolver __resolver = (short code) -> {
byte[] __b = __codeFlat[code - Short.MIN_VALUE];
return (__b != null) ? __b : EMPTY_BYTES;
};
// ─── Tee the output stream into the RowSink when one is installed.
// When fw.analyzer.enabled=false (default), this branch returns the
// original outStream unchanged — bytes-on-disk are identical to before.
final java.io.OutputStream __sinkOut = com.company.sink.RowSinkRegistry.isActive()
? new com.company.sink.RowSinkOutputStream(
outStream,
com.company.sink.RowSinkRegistry.current(),
// separator: prefer FW_B_ARR when configured; else the literal '\n' that's appended below
(FW_B_ARR != null && FW_B_ARR.length > 0) ? FW_B_ARR : new byte[]{'\n'},
new java.util.concurrent.atomic.AtomicLong(1L))
: outStream;
DBStreamer.streamResultAsMapMap2WithLabels(__sql, numOfColumnsIn_fw_final_base_copy_Total, 100,
(id, cols, labels) -> {
__rowWriter.writeOneRow(id, labels, cols, __sinkOut, __resolver);
if (cfg().filesMode() && !cfg().zipMode()) {
__sinkOut.write('\n');
}
__streamRows[0]++;
});
// Flush any final unterminated row buffer to the sink (no separator at EOF case).
if (__sinkOut instanceof com.company.sink.RowSinkOutputStream rsos) {
rsos.flushPending();
}
System.out.println("      [STREAMING-DIRECT] rows streamed=" + __streamRows[0]
+ "  elapsed_ms=" + ((System.nanoTime() - __sdStart) / 1_000_000L));
} catch (Exception __ex) {
System.out.println("      [STREAMING-DIRECT] EXCEPTION: " + __ex);
__ex.printStackTrace();
}
continue;
}

__driverFutures.add(__driverPool.submit(() -> {
System.out.println("    [parallel] " + __label + "  (runningCounter=" + counter.sum() + ")");
try {
// perf 2026-07-02: rows are gathered into TASK_BATCH-sized slices; each slice is ONE
// virtual-thread task that assembles+emits its rows via the shared KeyPlan machinery.
final ArrayList<long[]> __idBatch = new ArrayList<>();       // [0]=id per row
final ArrayList<LinkedHashMap<Integer, short[]>> __colBatch = new ArrayList<>();
final Runnable[] __flush = new Runnable[1];
__flush[0] = () -> {
if (__idBatch.isEmpty()) return;
final long[][] ids = __idBatch.toArray(new long[0][]);
final LinkedHashMap<Integer, short[]>[] colsArr = __colBatch.toArray(new LinkedHashMap[0]);
__idBatch.clear();
__colBatch.clear();
try {
__inflight.acquire();
} catch (InterruptedException __ie) {
Thread.currentThread().interrupt();
throw new RuntimeException(__ie);
}
executor.submit(() -> {
try {
final Assembler __as = new Assembler(__plan.keys.length);
for (int __r = 0; __r < ids.length; __r++) {
// STEP 34: stop PRODUCTION on a shared cancel — skip remaining assembly + writes.
if (__bpGate != null && __bpGate.isCancelled()) return;
try {
final SegRow __row = buildSegRow(__plan, ids[__r][0], colsArr[__r]);
if (__row.poison) continue;   // legacy: task died silently pre-write
__as.assemble(__plan, __row, null);
if (__as.dropped) continue;   // poisoned key picked (legacy silent drop)
final String __tag = __row.idStr + "_0_0";
emitCandidate(__env, __as, __row.id, __tag, __tag, __row.idStr, __row.idStr, "parallel");
} catch (Throwable __rowEx) {
// legacy: a row-task failure lost that one candidate silently; keep the
// isolation but surface it.
__rowEx.printStackTrace();
}
}
} finally {
__inflight.release();
}
});
};
DBStreamer.streamResultAsMapMap2(__sql, __numCols, __streamFetchSizeFinal,
(rawId, cols) -> {
if (__bpGate != null && __bpGate.isCancelled()) return;   // STEP 34: stop SUBMITTING candidate tasks on cancel

final long id = __useVirtualGlobalId ? __virtualGlobalId.incrementAndGet() : rawId;
long __rowsSoFar = __streamedRows.incrementAndGet();
if ((__rowsSoFar & 0xFFFFF) == 0) {
System.out.println("        progress: streamed=" + __rowsSoFar + "  counter=" + counter.sum()
+ "  in-flight~" + (__maxInFlightFinal - __inflight.availablePermits() * __taskBatch)
+ "  drivers=" + __driverParallelism
+ "  elapsed_sec=" + ((System.nanoTime() - __streamStart) / 1_000_000_000L));
}
__idBatch.add(new long[]{id});
__colBatch.add(cols);
if (__idBatch.size() >= __taskBatch) __flush[0].run();
});
__flush[0].run();   // trailing partial batch
} catch (SQLException e) {
System.out.println("      SQLException during streaming partition — skipping. " + e);
e.printStackTrace();
}
}));
}

for (Future<?> f : __driverFutures) {
try {
f.get();
} catch (Exception e) {
e.printStackTrace();
}
}
} finally {
__driverPool.shutdown();
try {
__driverPool.awaitTermination(1, TimeUnit.HOURS);
} catch (InterruptedException ie) {
Thread.currentThread().interrupt();
}
__hb.stop();
}
System.out.println("      streamed " + __streamedRows.get() + " rows from public." + __currentFinalTable
+ "  (stream_ms=" + ((System.nanoTime() - __streamStart) / 1_000_000L)
+ ", in-flight-remaining~" + (__maxInFlightFinal - __inflight.availablePermits() * __taskBatch)
+ ", parallelism=" + __driverParallelism + ")");
}

System.out.println("<<< STAGE: FINAL-ONLY pass COMPLETED"
+ "  chunksProcessed=" + __finalChunkIndex
+ "  counterNow=" + counter.sum()
+ "  stage_ms=" + ((System.nanoTime() - __finalStageStart) / 1_000_000L));
System.out.println();

}

if (isOpt) {
System.out.println(">>> STAGE: CARTESIAN pass ENTERED (final × opt)"
+ "  fwFinals.size()=" + fwFinals.size() + "  fwOpts.size()=" + fwOpts.size());
long __cartStageStart = System.nanoTime();
long __cartFinalChunkIndex = 0L;
AtomicLong __cartOptChunkIndex = new AtomicLong(0L);
// ── scalable constraint enforcement: evaluate DEFERRED optional bonds PER assembled candidate ──
// Loaded ONCE here; null when the run is not sieving (zero per-candidate cost) and the FINAL-only
// pass above is never touched. O(bonds) memory — no precomputed per-candidate skip-list.
final OptionalBondFilter __bondFilter =
        OptionalBondFilter.loadOrNull(ReaderConfig.cfg().constraintsBondsFile());
if (__bondFilter != null) {
    System.out.println("  [constraints] optional-bond filter active (" + __bondFilter.size()
            + " bond(s)); forbidden assembled candidates skipped during cartesian assembly");
}
// perf 2026-07-02: opt chunks (as prebuilt SegRow[]) survive across final chunks in a
// SoftReference cache, so multi-final-chunk runs stop re-reading the same opt rows from
// Postgres once per final chunk. Soft refs → GC-evictable, safe for arbitrarily large tables.
final ConcurrentHashMap<String, SoftReference<SegRow[]>> __optSegCache = new ConcurrentHashMap<>();

for (int i = 0; i < fwFinals.size(); i++) {

final String __currentFinalTableCart = fwFinals.get(i);
final List<Map.Entry<Long, Long>> __finalChunksForTableCart = table2combiIdChunksEntryFinals.get(__currentFinalTableCart);
final int __finalChunkCountCart = (__finalChunksForTableCart == null) ? 0 : __finalChunksForTableCart.size();
System.out.println("  CARTESIAN: [final " + (i + 1) + "/" + fwFinals.size() + "] table=public." + __currentFinalTableCart
+ "  final-chunks=" + __finalChunkCountCart
+ "  id-mode=" + (TableSchemaInspector.useRealCombiId(__currentFinalTableCart) ? "real" : "virtual(row_number)"));
if (__finalChunkCountCart == 0) {
System.out.println("    (no final chunks for this table — skipping)");
continue;
}
for (int j = 0; j < fwOpts.size(); j++) {

final String __currentOptTableCart = fwOpts.get(j);
final List<Map.Entry<Long, Long>> __optChunksForTableCart = table2combiIdChunksEntryOpts.get(__currentOptTableCart);
final int __optChunkCountCart = (__optChunksForTableCart == null) ? 0 : __optChunksForTableCart.size();
System.out.println("    CARTESIAN: × [opt " + (j + 1) + "/" + fwOpts.size() + "] table=public." + __currentOptTableCart
+ "  opt-chunks=" + __optChunkCountCart
+ "  id-mode=" + (TableSchemaInspector.useRealCombiId(__currentOptTableCart) ? "real" : "virtual(row_number)"));
if (__optChunkCountCart == 0) {
System.out.println("      (no opt chunks for this table — skipping)");
continue;
}

int __fChunkIdxInTableCart = 0;
for (Map.Entry<Long, Long> entryKVfinals : __finalChunksForTableCart) {
__fChunkIdxInTableCart++;
__cartFinalChunkIndex++;
int finalI = i;
List<String> finalFwFinals = fwFinals;
int finalJ1 = j;
Map<String, List<Map.Entry<Long, Long>>> finalTable2combiIdChunksEntryOpts = table2combiIdChunksEntryOpts;

combiIdLowLimitFinal[0] = entryKVfinals.getKey();
combiIdHighLimitFinal[0] = entryKVfinals.getValue();
System.out.println("      final-chunk " + __fChunkIdxInTableCart + "/" + __finalChunkCountCart
+ "  BETWEEN " + combiIdLowLimitFinal[0] + " AND " + combiIdHighLimitFinal[0]
+ "  (runningCounter=" + counter.sum() + ")");

try {

final long __loadFStart = System.nanoTime();
Heartbeat __hbF = Heartbeat.start("loading " + finalFwFinals.get(finalI)
+ " [" + combiIdLowLimitFinal[0] + ".." + combiIdHighLimitFinal[0] + "]", 5000L, "        ");
try {
curMap4readerFinal[0] = q2dbMgr.resultAsMapMap2(
TableSchemaInspector.rangeQuery(finalFwFinals.get(finalI), combiIdLowLimitFinal[0], combiIdHighLimitFinal[0]),
numOfColumnsIn_fw_final_base_copy_Total, 100);
} finally {
__hbF.stop();
}
System.out.println("        loaded final: " + curMap4readerFinal[0].size() + " rows from public." + finalFwFinals.get(finalI)
+ "  (load_ms=" + ((System.nanoTime() - __loadFStart) / 1_000_000L) + ")");
} catch (SQLException e) {
System.out.println("        SQLException loading final chunk — skipping. " + e);
e.printStackTrace();
continue;
}

// perf: pre-render every final row of this chunk ONCE; reused by all opt chunks × opt rows.
final SegRow[] __fSegs = buildSegRows(__plan, curMap4readerFinal[0]);

AtomicInteger __oChunkIdxInTableCart = new AtomicInteger();
int maxConcurrentDbLoads = 3;
try (ExecutorService executorY = Executors.newFixedThreadPool(maxConcurrentDbLoads)) {
List<Future<?>> futures = new ArrayList<>(); var entries = finalTable2combiIdChunksEntryOpts.get(fwOpts.get(finalJ1));
for (Map.Entry<Long, Long> entryKVopts : entries) {
int finalNumOfColumnsIn_fw_final_base_copy_Total = numOfColumnsIn_fw_final_base_copy_Total;
futures.add(executorY.submit(() -> {
__oChunkIdxInTableCart.getAndIncrement();
__cartOptChunkIndex.getAndIncrement();

long localLowLimit = entryKVopts.getKey();
long localHighLimit = entryKVopts.getValue();
System.out.println("        opt-chunk " + __oChunkIdxInTableCart + "/" + __optChunkCountCart
+ "  BETWEEN " + localLowLimit + " AND " + localHighLimit);

final String __optCacheKey = fwOpts.get(finalJ1) + "|" + localLowLimit + "|" + localHighLimit;
SegRow[] __oSegsTmp = null;
{
SoftReference<SegRow[]> __ref = __optSegCache.get(__optCacheKey);
if (__ref != null) __oSegsTmp = __ref.get();
}
if (__oSegsTmp != null) {
System.out.println("          [cache] opt chunk reused (no re-read): " + __optCacheKey
+ "  rows=" + __oSegsTmp.length);
} else {
Map<Long, LinkedHashMap<Integer, short[]>> localCurMap4readerOpt = null;

try {

final long __loadOStart = System.nanoTime();
Heartbeat __hbO = Heartbeat.start("loading " + fwOpts.get(finalJ1)
+ " [" + localLowLimit + ".." + localHighLimit + "]", 5000L, "          ");
try {
localCurMap4readerOpt = q2dbMgr.resultAsMapMap2(
TableSchemaInspector.rangeQuery(fwOpts.get(finalJ1), localLowLimit, localHighLimit),
finalNumOfColumnsIn_fw_final_base_copy_Total, 100);
} finally {
__hbO.stop();
}
System.out.println("          loaded opt: " + localCurMap4readerOpt.size() + " rows from public." + fwOpts.get(finalJ1)
+ "  (load_ms=" + ((System.nanoTime() - __loadOStart) / 1_000_000L) + ")");
} catch (SQLException e) {
System.out.println("          SQLException loading opt chunk — skipping. " + e);
e.printStackTrace();
return;
}
__oSegsTmp = buildSegRows(__plan, localCurMap4readerOpt);
__optSegCache.put(__optCacheKey, new SoftReference<>(__oSegsTmp));
}
final SegRow[] __oSegs = __oSegsTmp;

final long __pairCount = (long) __fSegs.length * (long) __oSegs.length;
System.out.println("          cartesian pairs expected = " + __pairCount
+ "  (finalRows=" + __fSegs.length + " × optRows=" + __oSegs.length + ")");

final int __maxInFlightCart = 20_000;
// perf: permits scaled by TASK_BATCH — outstanding submitted-not-executed PAIRS stay ≈ 20k.
final java.util.concurrent.Semaphore __cartInflight =
        new java.util.concurrent.Semaphore(Math.max(CARTESIAN_DRIVER_PARALLELISM, __maxInFlightCart / __taskBatch));
final java.util.concurrent.atomic.AtomicLong __cartPairsSubmitted = new java.util.concurrent.atomic.AtomicLong(0);
final long __cartPairLoopStart = System.nanoTime();

final int finalJ = finalJ1;
final String __optTableSuffix = fwOpts.get(finalJ).substring(6);

final int __finalSize = __fSegs.length;
final int __cartDriverParallelism = Math.max(1, Math.min(__finalSize, CARTESIAN_DRIVER_PARALLELISM));
final int __chunkSize = (__finalSize + __cartDriverParallelism - 1) / __cartDriverParallelism;
final ExecutorService __cartDriverPool = Executors.newFixedThreadPool(__cartDriverParallelism, r -> {
Thread t = new Thread(r, "fw-cart-driver-final" + finalI + "-opt" + finalJ);
t.setDaemon(true);
return t;
});
if (__bpCancel != null) __bpCancel.register(__cartDriverPool);   // STEP 34: shutdownNow on cancel
final List<Future<?>> __cartFutures = new ArrayList<>(__cartDriverParallelism);
try {
for (int __dIdx = 0; __dIdx < __cartDriverParallelism; __dIdx++) {
final int __from = __dIdx * __chunkSize;
final int __to = Math.min(__from + __chunkSize, __finalSize);
if (__from >= __to) continue;
__cartFutures.add(__cartDriverPool.submit(() -> {
for (int __fi = __from; __fi < __to; __fi++) {
final SegRow __fRow = __fSegs[__fi];
for (int __oiStart = 0; __oiStart < __oSegs.length; __oiStart += __taskBatch) {

if (__bpGate != null && __bpGate.isCancelled()) return;   // STEP 34: stop SUBMITTING cartesian tasks on cancel
try {
__cartInflight.acquire();
} catch (InterruptedException __ie) {
Thread.currentThread().interrupt();
throw new RuntimeException(__ie);
}
final int __oiFrom = __oiStart;
final int __oiTo = Math.min(__oiStart + __taskBatch, __oSegs.length);
long __pairsNow = __cartPairsSubmitted.addAndGet(__oiTo - __oiFrom);
long __pairsPrev = __pairsNow - (__oiTo - __oiFrom);
if ((__pairsNow >>> 20) != (__pairsPrev >>> 20)) {
System.out.println("            progress: pairs submitted=" + __pairsNow
+ "/" + __pairCount
+ "  counter=" + counter.sum()
+ "  in-flight~" + (__maxInFlightCart - __cartInflight.availablePermits() * __taskBatch)
+ "  drivers=" + __cartDriverParallelism
+ "  elapsed_sec=" + ((System.nanoTime() - __cartPairLoopStart) / 1_000_000_000L));
}
executor.submit(() -> {
try {
final Assembler __as = new Assembler(__plan.keys.length);
final int __K = __plan.keys.length;
for (int __oi = __oiFrom; __oi < __oiTo; __oi++) {
// STEP 34: stop production on a shared cancel — remaining pairs of this batch skipped.
if (__bpGate != null && __bpGate.isCancelled()) return;
try {
final SegRow __oRow = __oSegs[__oi];
if (__fRow.poison || __oRow.poison) continue;   // legacy silent task-death drop

// scalable optional-bond enforcement: skip this assembled candidate if it violates a
// deferred bond. Same pick order (opt ▸ final ▸ base) the legacy merged-map clone had;
// evaluated before the byte assembly. No-op when not sieving.
if (__bondFilter != null) {
LinkedHashMap<String, Object> __cand = new LinkedHashMap<>();
for (int __j2 = 0; __j2 < __K; __j2++) {
short[] __v = (__oRow.val[__j2] != null) ? __oRow.val[__j2]
: (__fRow.val[__j2] != null) ? __fRow.val[__j2]
: __plan.baseVal[__j2];
if (__v != null) __cand.put(__plan.keys[__j2], __v);
}
if (__bondFilter.violates(__cand)) continue;
}

__as.assemble(__plan, __fRow, __oRow);
if (__as.dropped) continue;

final String __pairIds = __fRow.idStr + "_" + __oRow.idStr;
emitCandidate(__env, __as,
__fRow.id,
__pairIds + "_0",                       // sink tag (legacy: final_opt_0)
__pairIds + "_" + __optTableSuffix,     // file/emit tag
__pairIds,                              // zip entry name
__pairIds + "_" + __optTableSuffix,     // zip file base name
"parallel-opt");
} catch (Throwable __pairEx) {
__pairEx.printStackTrace();
}
}
} finally {
__cartInflight.release();
}
});
}
}
}));
}

for (Future<?> f : __cartFutures) {
try {
f.get();
} catch (Exception e) {
e.printStackTrace();
}
}
} finally {
__cartDriverPool.shutdown();
try {
__cartDriverPool.awaitTermination(1, TimeUnit.HOURS);
} catch (InterruptedException ie) {
Thread.currentThread().interrupt();
}
}
System.out.println("          cartesian submits done: pairsSubmitted=" + __cartPairsSubmitted.get()
+ "  submit_loop_ms=" + ((System.nanoTime() - __cartPairLoopStart) / 1_000_000L)
+ "  parallelism=" + __cartDriverParallelism);
}));
}

for (Future<?> futureY : futures) {
try {
futureY.get();
} catch (Exception e) {

e.printStackTrace();
}
}
}

}
}
}

System.out.println("<<< STAGE: CARTESIAN pass COMPLETED"
+ "  finalChunks=" + __cartFinalChunkIndex
+ "  optChunks=" + __cartOptChunkIndex
+ "  counterNow=" + counter.sum()
+ "  stage_ms=" + ((System.nanoTime() - __cartStageStart) / 1_000_000L));
System.out.println();

}

System.out.println(">>> STAGE: EXECUTOR SHUTDOWN — awaiting termination up to "
+ cfg().fwGeneralTimeoutToStop() + " minute(s)…");
long __shutdownStart = System.nanoTime();
executor.shutdown();
try {
if (!executor.awaitTermination(cfg().fwGeneralTimeoutToStop(), TimeUnit.MINUTES)) {
System.err.println("Executor did not terminate in the allotted time. Forcing shutdown...");
System.out.println("!!! Executor awaitTermination TIMED OUT after "
+ cfg().fwGeneralTimeoutToStop() + " min — calling shutdownNow(). counterAtTimeout=" + counter.sum());
executor.shutdownNow();
} else {
System.out.println("    executor terminated cleanly  wait_ms="
+ ((System.nanoTime() - __shutdownStart) / 1_000_000L));
}
} catch (InterruptedException e) {
System.out.println("!!! awaitTermination interrupted — forcing shutdownNow(). counterAtInterrupt=" + counter.sum());
e.printStackTrace();
executor.shutdownNow();
}

// GRACEFUL-STOP VERIFICATION (May29): the stop already awaits the writer executor
// (shutdown + awaitTermination), so by here every per-combo file task has run. Make
// that observable — compare files actually on disk to the emitted counter.
long __onDisk = -1;
// STEP 32: the loose-file on-disk cross-check counts one *<ext> file per candidate; it is
// meaningless for the shard transport (candidates live inside a few container files), so it
// is skipped there (__onDisk stays -1) and the sink's authoritative count vs the assembled
// counter remains the reconciliation. The loose-files path is unchanged.
if (cfg().filesMode() && !__shardSink && !__grpcSink) {
try {
__onDisk = 0;
for (String __d : cfg().pathFwOutZipDirList()) {
java.io.File[] __fs = new java.io.File(__d).listFiles((_, nn) -> nn.endsWith(cfg().fwFileExtension()));
if (__fs != null) __onDisk += __fs.length;
}
System.out.println("    [graceful-stop] candidate files on disk = " + __onDisk
+ "  (emitted counter = " + counter.sum() + ")"
+ (__onDisk == counter.sum() ? "  OK all flushed" : "  MISMATCH"));
} catch (Exception __ce) { __ce.printStackTrace(); __onDisk = -1; }
}

// STEP 31: record the sink's AUTHORITATIVE summary so HandoffManifestWriter takes
// candidate_count from it (not a re-count), and reconcile it three ways — against the
// pipeline's assembled counter and the files actually on disk. Any write error or
// mismatch arms a deferred fail-closed (thrown at end-of-run, after cleanup) so a
// partial/corrupted candidate set is never handed off as success.
if (__bpGate != null) {                   // STEP 34: report + finalise backpressure metrics
System.out.println("  [backpressure] metrics: producer_wait="
        + String.format(java.util.Locale.ROOT, "%.3f", __bpGate.producerWaitSeconds())
        + "s  max_depth=" + __bpGate.maxDepth());
__bpGate.close();
}
if (__bpCancel != null) __bpCancel.close();   // STEP 34: stop the cancel-watcher thread
if (__looseSink != null) {
// STEP 32: close BEFORE reading the summary — the ShardSink finalizes (sorts + writes
// shards) at close, so its authoritative tally is only complete afterwards. Harmless for
// LooseFileSink (its per-write counters are already final; close only flips a flag).
__looseSink.close();
com.company.sink.CandidateSink.Summary __sinkSummary = __looseSink.summary();
com.company.sink.CandidateSinkRegistry.record(__sinkSummary);
long __counterNow = counter.sum();
boolean __reconciled = __sinkSummary.errors() == 0
&& __sinkSummary.candidateCount() == __counterNow
&& (__onDisk < 0 || __sinkSummary.candidateCount() == __onDisk);
System.out.println("    [sink] " + __sinkSummary + "  counter=" + __counterNow + "  onDisk=" + __onDisk
+ (__reconciled ? "  OK reconciled" : "  RECONCILE-FAIL"));
if (__sinkSummary.errors() > 0) {
__sinkReconcileMsg = "candidate sink reported " + __sinkSummary.errors() + " write error(s)";
} else if (__sinkSummary.candidateCount() != __counterNow) {
__sinkReconcileMsg = "sink count " + __sinkSummary.candidateCount() + " != assembled counter " + __counterNow;
} else if (__onDisk >= 0 && __sinkSummary.candidateCount() != __onDisk) {
__sinkReconcileMsg = "sink count " + __sinkSummary.candidateCount() + " != files on disk " + __onDisk
+ (__sinkSummary.candidateCount() < __onDisk
? " (stale files from a previous run? clean the output dir)"
: " (candidates lost/overwritten after write)");
}
}

if (!cfg().filesMode() && !cfg().zipMode()) {
System.out.println("    ReaderIoStreams.ProducerConsumerIO.finish() — draining/closing in-memory output stream");
ReaderIoStreams.ProducerConsumerIO.finish();
}

System.out.println("    disconnecting JDBC pools (q2dbMgr, q2d1, q2d, q2d4reader, q2d4reader2)");
q2dbMgr.disconnect();
q2d1.disconnect();
q2d.disconnect();
q2d4reader.disconnect();
q2d4reader2.disconnect();

if (watchService != null) {
try {
watchService.close();
} catch (IOException e) {
e.printStackTrace();
}
}

System.out.println();
System.out.println("================================================================");
System.out.println("DATA PROCESSING — SUMMARY");
System.out.println("================================================================");
System.out.println("  Total records emitted (counter) = " + counter.sum());
System.out.println("  Expected control (fwFinals×fwOpts combi products) = " + control);
if (control.compareTo(BigInteger.valueOf(counter.longValue())) != 0) {
System.out.println("  !!! MISMATCH: counter != control");
System.out.println("[WARN] [fail-honest][AI-proposition] reconciliation MISMATCH at stage boundary: expected control=" + control + " != emitted counter=" + counter + ". HIGH-confidence: silent/deceptive-success is the dominant ROI tax; a user must never mistake a partial/corrupted run for a clean one. Non-blocking note — processing logic unchanged.");
try {
if (!cfg().isProcessBothFinalAndOpt())
throw new Exception("control = " + control + " != " + counter + " = counter");
} catch (Exception e) {
e.printStackTrace();
}
} else {
System.out.println("  counter == control (OK)");
}
System.out.println("  Total elapsed since ANALYSIS banner = "
+ ((System.nanoTime() - __stageStartNanos) / 1_000_000L) + " ms");
System.out.println("================================================================");

try {
rowDbFieldDbCellHM = (LinkedHashMap<String, Object>) columnNamesFirstRowStaticHM.clone();
keysOfMap = new ArrayList(rowDbFieldDbCellHM.keySet());
for (int i = 0; i < keysOfMap.size(); i++) {
Object _ = keysOfMap.get(i);
}

indexOfMap = 0;
for (Object keyOfMap : rowDbFieldDbCellHM.keySet()) {
Object _ = rowDbFieldDbCellHM.get(keyOfMap);
++indexOfMap;
}

rowDbFieldDbCellHM.forEach((key, value) -> {
if (value == null || value instanceof Long) System.out.print("\t" + key + ":" + value);
else System.out.print("\t" + key + ":" + Arrays.toString((short[]) value));
});
System.out.println("\n=====");

} catch (Exception e) {
e.printStackTrace();
} finally {
if (q2d4reader != null) q2d4reader.disconnect();
}
System.out.println("end1");

System.out.println("end2");

// STEP 31 fail-closed: thrown AFTER cleanup/logging above. A candidate handoff that
// does not reconcile (sink vs counter vs on-disk) or that dropped candidates (errors)
// aborts the run with a non-zero exit — Main never reaches the manifest write, so no
// handoff is produced for a partial set. Concatenation / ZIP modes never set this
// (no sink ran), so this is a no-op for them.
if (__sinkReconcileMsg != null) {
throw new IllegalStateException("[STEP 31] candidate handoff reconciliation failed: "
+ __sinkReconcileMsg + " — run failed (fail-closed)");
}

    }
}
