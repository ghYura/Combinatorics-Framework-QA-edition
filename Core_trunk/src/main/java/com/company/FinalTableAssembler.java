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

package com.company;

import com.company.combinatorics.CombinatorialGenerator;
import com.company.config.AppConfig;
import com.company.db.DbClient;
import com.company.db.SchemaProvisioner;
import com.company.db.sql.LegacySqlHardener;
import com.company.db.sql.RelationLockRegistry;
import com.company.db.sql.SqlSelfHealingExecutor;
import com.company.db.sql.TimeoutSqlExecutor;
import com.company.excel.ParsedWorkbook;
import com.company.helpers.TableDataDistinctorFnl;
import com.company.store.IntermediateTableStore;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.math.BigInteger;
import java.nio.file.Files;
import java.sql.SQLException;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;


public final class FinalTableAssembler {

private static final Logger log = LogManager.getLogger(FinalTableAssembler.class);

private final AppConfig       config;
private final DbClient        db;
private final SchemaProvisioner schema;
private final ParsedWorkbook  workbook;
/** [Iter2] Source of per-sheet intermediate rows. */
private final IntermediateTableStore store;
/** [Iter4.3] Resolved precompute decision: AUTO collapsed to JAVA or DB by
 *  {@link com.company.precompute.PrecomputeMemoryBudget} before assembler is
 *  constructed.  Drives the fw_final_base baseline path (Java COPY vs SQL). */
private final AppConfig.PrecomputeMode resolvedPrecompute;


private final RelationLockRegistry relationLocks = new RelationLockRegistry();

/** [Iter4 Step 9] Watchdog-driven cancel flag.  Set via {@link #cancel()};
 *  checked at strategic hot-loop points (fnl producer / consumer, opts combo
 *  loop, runOptionalInsert cartesian) so a HIGH/CRITICAL heap event aborts
 *  the assembly without waiting for OOM.  Cannot interrupt PG-side
 *  distinctify in flight — that one is bounded by PG memory, not JVM. */
private volatile boolean cancelled = false;

/** [Iter4 Step 9] Signal the assembler to abort at next checkpoint.
 *  Idempotent; safe to call from any thread. */
public void cancel() {
    cancelled = true;
    log.error("[Iter4 Step 9] FinalTableAssembler.cancel() invoked — pipeline will exit at next checkpoint");
}

public FinalTableAssembler(AppConfig config, DbClient db,
SchemaProvisioner schema, ParsedWorkbook workbook,
IntermediateTableStore store) {
this(config, db, schema, workbook, store, AppConfig.PrecomputeMode.DB);
}

/** [Iter4.3] Mode-aware constructor.  Pass the RESOLVED mode (AUTO already
 *  collapsed to JAVA or DB by the orchestrator).  Pre-iter4 callers go through
 *  the legacy 5-arg constructor above which defaults to DB (byte-identical
 *  to pre-iter4 behaviour). */
public FinalTableAssembler(AppConfig config, DbClient db,
SchemaProvisioner schema, ParsedWorkbook workbook,
IntermediateTableStore store,
AppConfig.PrecomputeMode resolvedPrecompute) {
this.config   = config;
this.db       = db;
this.schema   = schema;
this.workbook = workbook;
this.store    = store;
this.resolvedPrecompute = (resolvedPrecompute == null) ? AppConfig.PrecomputeMode.DB : resolvedPrecompute;
}



public void assemble(
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, List<Short>> toCombinatoricsHMoptional,
Map<Short, String>      key2tableMap,
Map<Short, String>      key2tableMapOptional,
Map<String, ArrayList<short[]>> mapTable2combs,
String createSqlFinal) throws InterruptedException, ExecutionException {

ExecutorService exec = Executors.newFixedThreadPool(2);
try {
Future<?> fnlFuture  = exec.submit(() -> runFnlThread(
toCombinatoricsHM, key2tableMap, mapTable2combs));



Future<?> optsFuture = exec.submit(() -> runOptsThread(
toCombinatoricsHM, toCombinatoricsHMoptional,
key2tableMapOptional, mapTable2combs, createSqlFinal));

fnlFuture.get();
optsFuture.get();
} finally {
exec.shutdown();
}
}



private void runFnlThread(
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, String>      key2tableMap,
Map<String, ArrayList<short[]>> mapTable2combs) {

log.info("fnlThread started");
if (cancelled) { log.warn("fnlThread: cancelled before start"); return; }
if (config.hold.holdFnl) sleep(config.hold.delayFnlMs);














StringBuilder sb1 = new StringBuilder();
for (var key : key2tableMap.keySet()) {
sb1.append("\"combos").append(key).append("_")
.append(workbook.shortStringSheetKey2SheetNameHM.get(key))
.append("\", ");
}
if (sb1.length() > 2) sb1.setLength(sb1.length() - 2);
String commaSepFields = sb1.toString();

List<String> tableNameList  = new ArrayList<>(key2tableMap.values());
if (tableNameList.isEmpty()) {
log.error("fnlThread: no tables to combine — key2tableMap is empty. "
+ "Likely caused by an upstream processing failure (check for earlier errors).");
return;
}
List<Long>   maxCombiIdList = new ArrayList<>();
List<String> combosColList  = new ArrayList<>();


log.info("[DIAG] ══════════ fnlThread: MANDATORY tables in key2tableMap ({} entries) ══════════",
key2tableMap.size());
for (var key : key2tableMap.keySet()) {
String table = key2tableMap.get(key);
boolean fw2 = table.startsWith("fw2_");
String combosAppendix = fw2 ? "_1" : "";
// [Iter4-fix] Route through IntermediateTableStore so memory-backed
// intermediates work in all (precompute,storage) combos.  Direct
// db.queryLong on fw_/fw2_ tables fails when core.intermediate.storage=memory.
long maxId = store.maxCombiId(key, fw2);
long rowCount = store.count(key, fw2);
maxCombiIdList.add(maxId);
combosColList.add("combos" + combosAppendix);
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
log.info("[DIAG]   key={} sheet={} table={} combosCol={} maxCombiId={} rowCount={}",
key, sheetName, table, "combos" + combosAppendix, maxId, rowCount);
}

BigInteger bigIntNofCombosFinal = maxCombiIdList.stream()
.map(BigInteger::valueOf).reduce(BigInteger.ONE, BigInteger::multiply);

NumberFormat fmt = new DecimalFormat("0.######E0",
DecimalFormatSymbols.getInstance(Locale.ROOT));
log.info("Final combinations: {}", fmt.format(bigIntNofCombosFinal));

if (maxCombiIdList.size() != combosColList.size()
|| combosColList.size() != tableNameList.size()) {
log.error("MISMATCH: maxCombiIdList={}, combosColList={}, tableNameList={}",
maxCombiIdList.size(), combosColList.size(), tableNameList.size());
return;
}

long limitVar  = computeLimitVar(maxCombiIdList, config.threading.limitVarGivenLessThan);
int  idxCutoff = computeCutoffIdx(maxCombiIdList, config.threading.limitVarGivenLessThan);
String[] commaSepFieldsArr = commaSepFields.split(", ");

String sqlCoreBase = buildSqlCoreBase(tableNameList, combosColList, commaSepFieldsArr, "fw_final");
// [Refactor 18052026 / step #1] fw_final producer/consumer pipeline.
//
// Replaces the monolithic `INSERT INTO fw_final SELECT … LIMIT N` whose
// single PG backend serialised the whole assembly (1 core hot, N-1 idle).
// New flow:
//   1. Execute sqlCoreBase (small — produces fw_final_base + the _base_copy)
//   2. Read fw_final_base's row into Java as the NULLIF baseline
//   3. One producer thread walks the Cartesian product of mapTable2combs
//      slices in pure Java, emitting per-column NULLIF-encoded PG COPY rows
//      into a bounded queue (back-pressured by consumer drain rate)
//   4. N consumer threads pull batches from the queue and fire parallel
//      `COPY public.fw_final FROM STDIN` — DbClient.copyGate caps concurrency
//      at min(maxConcurrentCopies, maxPoolSize)
// Result: CPU 6/6 cores hot during emit; row order non-deterministic (same
// as before — SQL had no ORDER BY); fw_final contents identical to the
// legacy path because the NULLIF base row is preserved verbatim.
runFnlThreadJavaPipeline(sqlCoreBase, commaSepFields, commaSepFieldsArr,
        tableNameList, mapTable2combs, limitVar);

runCartesianPasses(tableNameList, combosColList, commaSepFieldsArr,
maxCombiIdList, idxCutoff, limitVar, mapTable2combs, commaSepFields);

waitForFinalTablesFilled();




try {
long actualFinalCount = db.queryLong(
"SELECT COUNT(*) FROM public.fw_final;");
log.info("Final table fw_final: actual row count = {}", actualFinalCount);
} catch (Exception e) {
log.warn("Could not query fw_final row count", e);
}

if (config.flags.distinctifyFwFinalOptTables) {
runUnderWriteLock("fw_final", () ->
new TableDataDistinctorFnl("fw_final", 0L, null, db,
config.flags.distinctifyJavaSide,
config.flags.distinctifySampleAndSkip)
.distinctifyByCopyingDistinctedDataToNewTempTableDistinctedAndRecreateGivenTableAsCopyOfNewTempTableDistincted());
}
log.info("fnlThread completed");
}




private void runOptsThread(
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, List<Short>> toCombinatoricsHMoptional,
Map<Short, String>      key2tableMapOptional,
Map<String, ArrayList<short[]>> mapTable2combs,
String createSqlFinal) {

log.info("optsThread started");
if (cancelled) { log.warn("optsThread: cancelled before start"); return; }
if (config.hold.holdOpts) sleep(config.hold.delayOptsMs);

if (toCombinatoricsHMoptional.isEmpty()) {
log.info("No optional sheets — optsThread skipped");
return;
}

final int poolSize = 2 * Runtime.getRuntime().availableProcessors();
final BlockingQueue<DbClient> dbPool = new LinkedBlockingDeque<>(poolSize);
// [Iter3.1] Each slot represents one worker that uses ONE PG connection at
// a time (read sources, build cartesian, COPY-IN).  Give each slot a tiny
// dedicated pool (min=1/max=2/copyGate=2) instead of inheriting the main
// pool's larger sizing — otherwise poolSize × maxPool potentially exceeds
// PostgreSQL's max_connections (default 100).  E.g. 12 slots × default 3 = 36
// connections just from slot pool, plus main pool plus Hibernate pool.
final AppConfig.PoolConfig slotPoolCfg = new AppConfig.PoolConfig(
        1,   // minSize
        2,   // maxSize
        1,   // acquireIncrement
        0,   // maxStatements
        2    // maxConcurrentCopies — same as maxSize so copyGate doesn't restrict
);
for (int j = 0; j < poolSize; j++) dbPool.offer(DbClient.create(config.db, slotPoolCfg));





final ExecutorService asyncExec = Executors.newCachedThreadPool(r -> {
Thread t = new Thread(r, "opt-insert-async");
t.setDaemon(false);
return t;
});

var optKeys     = new ArrayList<>(toCombinatoricsHMoptional.keySet());
var includeList = config.optional.includeOptionalCombiPairsToDB;


log.info("[DIAG] ══════════ optsThread: OPTIONAL tables in key2tableMapOptional ({} entries) ══════════",
key2tableMapOptional.size());
log.info("[DIAG] toCombinatoricsHMoptional keys ({} entries): {}",
toCombinatoricsHMoptional.size(), toCombinatoricsHMoptional.keySet());
log.info("[DIAG] optKeys for C(n,k): size={}, keys={}", optKeys.size(), optKeys);
for (var key : key2tableMapOptional.keySet()) {
String table = key2tableMapOptional.get(key);
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
try {
boolean fw2 = table.startsWith("fw2_");
// [Iter4-fix] Same routing fix as fnlThread.
long maxId = store.maxCombiId(key, fw2);
long rowCount = store.count(key, fw2);
log.info("[DIAG]   key={} sheet={} table={} maxCombiId={} rowCount={}",
key, sheetName, table, maxId, rowCount);
} catch (Exception e) {
log.warn("[DIAG]   key={} sheet={} table={} — QUERY FAILED: {}",
key, sheetName, table, e.getMessage());
}
}











final Map<Short, String> optTableColumns = new LinkedHashMap<>();
{
Map<Short, List<Short>> joined = new TreeMap<>(toCombinatoricsHM);
joined.putAll(toCombinatoricsHMoptional);
for (Short k : joined.keySet()) {
String name = workbook.shortStringSheetKey2SheetNameHM.get(k);
if (name != null) optTableColumns.put(k, name);
}
}

try {
for (int i = 0; i <= optKeys.size(); i++) {
if (!includeList.contains(i)) continue;





runOptsThreadCorePhase(i, optTableColumns, optKeys, dbPool, asyncExec,
        key2tableMapOptional, mapTable2combs);
}












asyncExec.shutdown();
try {
if (!asyncExec.awaitTermination(4, TimeUnit.HOURS)) {
log.warn("optsThread: async insert executor did not terminate within 4 hours; forcing");
asyncExec.shutdownNow();
}
} catch (InterruptedException e) {
Thread.currentThread().interrupt();
asyncExec.shutdownNow();
log.warn("optsThread: interrupted while awaiting async insert completion");
}




for (int i = 0; i <= optKeys.size(); i++) {
if (!includeList.contains(i)) continue;
try {
long rowsFinal = db.queryLong("SELECT COUNT(*) FROM fw_opt" + i + ";");
log.info("[DIAG] optsThread: fw_opt{} FINAL row count (post-async) = {}", i, rowsFinal);
} catch (Exception e) {
log.warn("[DIAG] optsThread: could not count fw_opt{} (final): {}", i, e.getMessage());
}
}
} finally {

if (!asyncExec.isShutdown()) {
asyncExec.shutdownNow();
}
while (!dbPool.isEmpty()) {
var slot = dbPool.poll();
if (slot != null) slot.close();
}
}
log.info("optsThread completed");
}




private void runUnderWriteLock(String relation, Runnable task) {
    java.util.concurrent.locks.Lock writeLock = relationLocks.get(relation).writeLock();
    writeLock.lock();
    try {
        task.run();
    } finally {
        writeLock.unlock();
    }
}




private void runFnlThreadCoreInserts(String sqlCoreBase, String sqlCore) {
    final TimeoutSqlExecutor     timeoutExec = new TimeoutSqlExecutor(db);
    final SqlSelfHealingExecutor selfHeal    =
            new SqlSelfHealingExecutor(db, timeoutExec, relationLocks);





    try {
        log.info("[Y30042026] sqlCoreBase before harden:\n{}", sqlCoreBase);
        selfHeal.executeWithSelfHeal(sqlCoreBase, "fw_final_base");
    } catch (SQLException e) {
        log.error("fnlThread sqlCoreBase execution failed (self-heal exhausted)", e);
        return;
    }





    try {
        timeoutExec.execute("DROP TABLE IF EXISTS fw_final_base_copy;");
        timeoutExec.execute("CREATE TABLE fw_final_base_copy AS TABLE fw_final_base;");
    } catch (SQLException e) {
        log.warn("fnlThread fw_final_base_copy recreate failed (continuing)", e);
    }


    try {
        log.info("[Y30042026] sqlCore before harden:\n{}", LegacySqlHardener.harden(sqlCore));
        selfHeal.executeWithSelfHeal(sqlCore, "fw_final");
    } catch (SQLException e) {
        log.error("fnlThread sqlCore execution failed (self-heal exhausted)", e);
    }
}


// ─── [Refactor 18052026 / step #1] Java-side fw_final pipeline ──────────
//
// Producer/consumer replacement for the monolithic
// `INSERT INTO fw_final SELECT … LIMIT N`.  The producer iterates the
// Cartesian product of in-memory mapTable2combs slices and emits NULLIF-
// encoded PG COPY rows into a bounded queue.  N consumer threads pull
// batches and fire parallel COPY-IN over independent connections, throttled
// by DbClient.copyGate.
//
// CPU profile vs. the legacy single-INSERT path:
//   legacy: 1 PG core hot, JVM ~5 % (parked on JDBC), 5+ min wall-clock
//   new:    JVM cartesian on producer core + N consumer cores doing
//           encode→COPY, PG drains in parallel; CPU 6/6 cores hot, disk
//           write rate becomes the natural ceiling
//
// Memory: queue cap × batch size ≈ counter4copyMax × ~200 B × queue depth.
// With counter4copyMax = 100 000 and queue depth = 4 × consumerCount,
// peak < 320 MB at typical settings.  Well under -Xmx4g.
//
// fw_final contents are byte-identical to the legacy path (modulo row
// order, which was already unordered in SQL): NULLIF baseline read directly
// from fw_final_base; same combo encoding via AppUtil.appendPgArray.
private void runFnlThreadJavaPipeline(
        String sqlCoreBase,
        String commaSepFields,
        String[] commaSepFieldsArr,
        java.util.List<String> tableNameList,
        java.util.Map<String, java.util.ArrayList<short[]>> mapTable2combs,
        long limitVar) {

    final TimeoutSqlExecutor     timeoutExec = new TimeoutSqlExecutor(db);
    final SqlSelfHealingExecutor selfHeal    = new SqlSelfHealingExecutor(db, timeoutExec, relationLocks);

    // [Iter4.3] In pure-Java mode, read per-sheet rows FIRST so we can compute
    // the NULLIF baseline directly from row[0] of each list (no SQL roundtrip).
    // In PG mode we still execute sqlCoreBase + SELECT baseline first, matching
    // the existing legacy flow byte-identically.
    //
    // [Iter4-fix] Also force the Java-baseline path whenever the intermediate
    // store is NOT PG-backed (e.g. core.precompute=db + core.intermediate.storage=memory):
    // sqlCoreBase joins against fw_/fw2_ PG tables that don't exist in memory mode.
    final boolean pureJavaMode = (resolvedPrecompute == AppConfig.PrecomputeMode.JAVA)
            || !store.isPgBacked();

    // ── Step A: read per-sheet rows from store (moved up for pure-Java path) ──
    // [Refactor 18052026 / step #11 + Iter2]: store returns post-distinctify
    // authoritative rows.  Moving this above the baseline computation is safe
    // for PG mode too — the per-sheet tables don't change while fnlThread runs.
    final java.util.List<java.util.ArrayList<short[]>> perSheetRows = new java.util.ArrayList<>();
    for (String t : tableNameList) {
        boolean fw2 = t.startsWith("fw2_");
        short k = parseKeyFromTableName(t);
        java.util.List<short[]> raw = fw2 ? store.readFw2Combos(k) : store.readFwCombos(k);
        java.util.ArrayList<short[]> rows = new java.util.ArrayList<>(raw);
        if (rows.isEmpty()) {
            log.error("[Iter2] store source {} is empty — aborting pipeline (no cartesian source)", t);
            return;
        }
        perSheetRows.add(rows);
        log.debug("[Iter2] loaded {} rows from {}", rows.size(), t);
    }
    final int n = perSheetRows.size();

    // ── Step B: baseline (mode-dependent) ─────────────────────────────────
    final String[] baseRowEncoded = new String[tableNameList.size()];
    if (pureJavaMode) {
        // [Iter4.3 pure-Java] Skip sqlCoreBase entirely.  Compute baseline as
        // row[0] of each per-sheet list — same semantics as the SQL
        // "always-true JOIN + LIMIT 1" trick which picks the first row of
        // each source — then COPY-IN the assembled baseline row to
        // fw_final_base.  Avoids two SQL roundtrips per fnlThread run.
        StringBuilder baseRow = new StringBuilder(64 * n);
        for (int i = 0; i < n; i++) {
            short[] r0 = perSheetRows.get(i).get(0);
            StringBuilder enc = new StringBuilder(r0.length * 4 + 2);
            AppUtil.appendPgArray(enc, r0);
            baseRowEncoded[i] = enc.toString();
            if (i > 0) baseRow.append('\t');
            baseRow.append(enc);
        }
        baseRow.append('\n');
        db.copyIn(baseRow, "fw_final_base", commaSepFields);
        log.info("[Iter4.3 pure-Java] fw_final_base baseline COPY'd from Java (skipped sqlCoreBase SQL)");
        try {
            timeoutExec.execute("DROP TABLE IF EXISTS fw_final_base_copy;");
            timeoutExec.execute("CREATE TABLE fw_final_base_copy AS TABLE fw_final_base;");
        } catch (SQLException e) {
            log.warn("[Iter4.3 pure-Java] fw_final_base_copy recreate failed (continuing)", e);
        }
    } else {
        // [PG mode] Legacy sqlCoreBase + SELECT baseline + base_copy.
        try {
            selfHeal.executeWithSelfHeal(sqlCoreBase, "fw_final_base");
        } catch (SQLException e) {
            log.error("[Refactor-#1] sqlCoreBase execution failed", e);
            return;
        }
        try {
            timeoutExec.execute("DROP TABLE IF EXISTS fw_final_base_copy;");
            timeoutExec.execute("CREATE TABLE fw_final_base_copy AS TABLE fw_final_base;");
        } catch (SQLException e) {
            log.warn("[Refactor-#1] fw_final_base_copy recreate failed (continuing)", e);
        }
        try (java.sql.Connection conn = db.getConnection();
             java.sql.Statement st = conn.createStatement();
             java.sql.ResultSet rs = st.executeQuery(
                     "SELECT " + commaSepFields + " FROM public.fw_final_base LIMIT 1")) {
            if (rs.next()) {
                for (int i = 0; i < tableNameList.size(); i++) {
                    java.sql.Array sqlArr = rs.getArray(i + 1);
                    Object javaArr = (sqlArr == null) ? null : sqlArr.getArray();
                    StringBuilder sb = new StringBuilder();
                    appendPgArrayOfShortOrInteger(sb, javaArr);
                    baseRowEncoded[i] = sb.toString();
                }
            }
        } catch (SQLException e) {
            log.warn("[Refactor-#1] could not read fw_final_base baseline — NULLIF disabled this run", e);
            java.util.Arrays.fill(baseRowEncoded, null);
        }
    }

    // [Refactor #11] Recompute true theoretical from PG-sourced row counts —
    // this is the actual Cartesian cardinality the pipeline will iterate
    // (independent of MAX(combi_id), which can be sparse post-DELETE
    // distinctify).  Honour the user's limitVar cap as the hard ceiling.
    java.math.BigInteger trueCartesian = java.math.BigInteger.ONE;
    for (java.util.ArrayList<short[]> rs : perSheetRows) {
        trueCartesian = trueCartesian.multiply(java.math.BigInteger.valueOf(rs.size()));
    }
    final long truncatedLimit;
    if (trueCartesian.bitLength() <= 62) {
        long tc = trueCartesian.longValueExact();
        truncatedLimit = Math.min(tc, limitVar);
    } else {
        truncatedLimit = limitVar;
    }
    log.info("[Refactor-#11] PG-sourced cartesian: trueCartesian={} limitVar={} → emitting up to {}",
            trueCartesian, limitVar, truncatedLimit);

    // 4. [Refactor 18052026 / step #8] Pre-encode every per-sheet row ONCE.
    //    Hot loop becomes a String[][] indexed lookup instead of per-row
    //    StringBuilder allocation + AppUtil.appendPgArray.  For a typical
    //    chunk with ~50 per-sheet rows × 7 sheets = ~350 strings of ~10
    //    chars each = ~3.5KB total — trivial RAM, but eliminates 100Ks of
    //    allocations per chunk.  Also pre-computes the NULLIF baseline
    //    indicator per (sheet, row) so the inner loop is two array
    //    look-ups + an append.
    final String[][] perSheetEncoded = new String[n][];
    final boolean[][] perSheetIsBase = new boolean[n][];
    for (int i = 0; i < n; i++) {
        java.util.ArrayList<short[]> rows = perSheetRows.get(i);
        String[] enc = new String[rows.size()];
        boolean[] isBase = new boolean[rows.size()];
        for (int j = 0; j < rows.size(); j++) {
            StringBuilder tmp = new StringBuilder(rows.get(j).length * 4 + 2);
            AppUtil.appendPgArray(tmp, rows.get(j));
            enc[j] = tmp.toString();
            isBase[j] = baseRowEncoded[i] != null && baseRowEncoded[i].equals(enc[j]);
        }
        perSheetEncoded[i] = enc;
        perSheetIsBase[i]  = isBase;
    }

    // 5. Producer/consumer setup.
    // [Refactor 18052026 / step #10 REVERTED] Multi-producer was tried but
    // is fundamentally incompatible with `limitVar` truncation: when
    // limitVar < sub_cartesian_size, the iteration ORDER decides which
    // tuples land in fw_final.  Single-producer iterates lexicographically;
    // multi-producer interleaves first-dim partitions.  These produce
    // DIFFERENT sets of tuples → different post-NULLIF / post-distinctify
    // fw_final.  Per the project's data-correctness > performance rule,
    // single-producer wins until a partitioning scheme that preserves
    // lexicographic prefix-order across producers is designed.
    final int batchSize     = Math.max(1_000, config.threading.counter4copyMax);
    final int consumerCount = Math.max(2, Math.min(config.pool.maxConcurrentCopies, config.pool.maxSize));
    final int producerCount = 1;  // see note above
    final int queueDepth    = (producerCount + consumerCount) * 4;
    final java.util.concurrent.BlockingQueue<String> queue =
            new java.util.concurrent.ArrayBlockingQueue<>(queueDepth);
    final java.util.concurrent.atomic.AtomicLong rowsEmittedShared = new java.util.concurrent.atomic.AtomicLong();
    final java.util.concurrent.atomic.AtomicLong rowsCopied        = new java.util.concurrent.atomic.AtomicLong();
    final java.util.concurrent.atomic.AtomicInteger producersAlive = new java.util.concurrent.atomic.AtomicInteger(producerCount);
    final java.util.concurrent.atomic.AtomicBoolean producerDone   = new java.util.concurrent.atomic.AtomicBoolean();

    java.util.concurrent.ExecutorService consumers =
            java.util.concurrent.Executors.newFixedThreadPool(consumerCount, r -> {
                Thread t = new Thread(r, "fw_final-copyIn-consumer");
                t.setDaemon(false);
                return t;
            });
    java.util.concurrent.ExecutorService producers =
            java.util.concurrent.Executors.newFixedThreadPool(producerCount, r -> {
                Thread t = new Thread(r, "fw_final-cartesian-producer");
                t.setDaemon(false);
                return t;
            });

    Runnable consumerTask = () -> {
        for (;;) {
            if (cancelled) return;  // [Iter4 Step 9]
            String batch;
            try {
                batch = queue.poll(1, java.util.concurrent.TimeUnit.SECONDS);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                return;
            }
            if (batch == null) {
                if (producerDone.get() && queue.isEmpty()) return;
                if (cancelled) return;
                continue;
            }
            StringBuilder sb = new StringBuilder(batch.length());
            sb.append(batch);
            try {
                db.copyIn(sb, "fw_final", commaSepFields);
                rowsCopied.addAndGet(countNewlines(batch));
            } catch (RuntimeException ex) {
                log.error("[Refactor-#1] consumer COPY-IN failed: {}", ex.getMessage());
            }
        }
    };
    for (int c = 0; c < consumerCount; c++) consumers.submit(consumerTask);

    // Producer task — partition by first dim [partStart, partEnd).
    // [Refactor 18052026 / step #10 v2] Per-row atomic claim instead of
    // per-batch.  Earlier per-batch check let 2 producers each over-claim
    // a full batchSize before reading the shared atomic — total emitted
    // exceeded limitVar.  Per-row claim costs ~10ns per row (single
    // AtomicLong CAS on the hot path) but enforces the contract exactly.
    final int firstDimSize = perSheetEncoded[0].length;
    final java.util.function.IntFunction<Runnable> producerFactory = (producerIdx) -> () -> {
        final int partStart = (int) (((long) producerIdx       * firstDimSize) / producerCount);
        final int partEnd   = (int) (((long) (producerIdx + 1) * firstDimSize) / producerCount);
        if (partStart >= partEnd) {
            if (producersAlive.decrementAndGet() == 0) producerDone.set(true);
            return;
        }
        StringBuilder batchBuf = new StringBuilder(batchSize * 64);
        int batchRows = 0;
        long localEmitted = 0L;

        // Sub-cartesian over dims 1..n-1 (idx[0] varies in the outer for-loop)
        int[] sub = new int[Math.max(0, n - 1)];

        OUTER:
        for (int i0 = partStart; i0 < partEnd; i0++) {
            if (cancelled) break OUTER;  // [Iter4 Step 9]
            java.util.Arrays.fill(sub, 0);
            for (;;) {
                // Atomic budget claim — exactly one row.  CAS loop avoids
                // racing producers from collectively over-claiming.
                long claim;
                do {
                    claim = rowsEmittedShared.get();
                    if (claim >= truncatedLimit) break;
                } while (!rowsEmittedShared.compareAndSet(claim, claim + 1));
                if (claim >= truncatedLimit) break OUTER;
                if ((claim & 0xFFFFL) == 0 && cancelled) break OUTER;  // [Iter4 Step 9] every 64K rows

                // Emit row: dim 0
                if (perSheetIsBase[0][i0]) batchBuf.append("\\N");
                else batchBuf.append(perSheetEncoded[0][i0]);
                // dims 1..n-1
                for (int i = 1; i < n; i++) {
                    batchBuf.append('\t');
                    int j = sub[i - 1];
                    if (perSheetIsBase[i][j]) batchBuf.append("\\N");
                    else batchBuf.append(perSheetEncoded[i][j]);
                }
                batchBuf.append('\n');
                batchRows++; localEmitted++;

                if (batchRows >= batchSize) {
                    try {
                        queue.put(batchBuf.toString());
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        break OUTER;
                    }
                    batchBuf.setLength(0);
                    batchRows = 0;
                }

                // Advance sub (n-1 dimensions)
                if (n == 1) break;
                int carry = 1;
                for (int i = n - 2; i >= 0; i--) {
                    sub[i] += carry;
                    if (sub[i] >= perSheetEncoded[i + 1].length) {
                        sub[i] = 0;
                        carry = 1;
                    } else { carry = 0; break; }
                }
                if (carry == 1) break;
            }
        }

        if (batchBuf.length() > 0) {
            try { queue.put(batchBuf.toString()); }
            catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
        }

        log.info("[Refactor-#1] producer[{}] finished: partition=[{},{}) emitted={}",
                producerIdx, partStart, partEnd, localEmitted);

        if (producersAlive.decrementAndGet() == 0) {
            producerDone.set(true);
        }
    };

    // Launch all producers
    long t0 = System.currentTimeMillis();
    for (int p = 0; p < producerCount; p++) producers.submit(producerFactory.apply(p));

    // Wait producers (limited by limitVar or cartesian exhaust)
    producers.shutdown();
    try {
        if (!producers.awaitTermination(15, java.util.concurrent.TimeUnit.MINUTES)) {
            log.warn("[Refactor-#1] producers did not finish within 15min — forcing");
            producers.shutdownNow();
        }
    } catch (InterruptedException ie) {
        Thread.currentThread().interrupt();
        producers.shutdownNow();
    }
    producerDone.set(true);  // belt + braces
    log.info("[Refactor-#1] all producers done: total emitted={} in {}ms",
            rowsEmittedShared.get(), System.currentTimeMillis() - t0);

    consumers.shutdown();
    try {
        if (!consumers.awaitTermination(15, java.util.concurrent.TimeUnit.MINUTES)) {
            log.warn("[Refactor-#1] consumers did not finish within 15min — forcing shutdown");
            consumers.shutdownNow();
        }
    } catch (InterruptedException ie) {
        Thread.currentThread().interrupt();
        consumers.shutdownNow();
    }
    log.info("[Refactor-#1] pipeline complete: rows emitted={} copied={}",
            rowsEmittedShared.get(), rowsCopied.get());
}

private static int countNewlines(String s) {
    int c = 0;
    for (int i = 0; i < s.length(); i++) if (s.charAt(i) == '\n') c++;
    return c;
}

/** [Iter2] Extract the {@code <N>} key from a table name like {@code fw_42}
 *  or {@code fw2_42}.  Used by store-routed reads in the fnl/opt pipelines. */
private static short parseKeyFromTableName(String name) {
    if (name == null) throw new IllegalArgumentException("table name must be non-null");
    int us = name.indexOf('_');
    if (us < 0 || us == name.length() - 1) {
        throw new IllegalArgumentException("Bad table name: " + name);
    }
    try {
        return Short.parseShort(name.substring(us + 1));
    } catch (NumberFormatException e) {
        throw new IllegalArgumentException("Bad table name (key not parsable): " + name, e);
    }
}

// [Refactor-#11] Convert a JDBC-returned PG array (typically Short[] for
// int2[], Integer[] for int4[]) into the canonical short[] this pipeline
// works with.  NULL elements are coerced to 0 (the engine doesn't emit
// null array elements anywhere, so this branch shouldn't fire in practice).
private static short[] toShortArrayFromJdbc(Object javaArr) {
    if (javaArr == null) return new short[0];
    if (javaArr instanceof Short[] sa) {
        short[] out = new short[sa.length];
        for (int i = 0; i < sa.length; i++) out[i] = sa[i] == null ? (short) 0 : sa[i];
        return out;
    }
    if (javaArr instanceof Integer[] ia) {
        short[] out = new short[ia.length];
        for (int i = 0; i < ia.length; i++) out[i] = ia[i] == null ? (short) 0 : ia[i].shortValue();
        return out;
    }
    if (javaArr instanceof Long[] la) {
        short[] out = new short[la.length];
        for (int i = 0; i < la.length; i++) out[i] = la[i] == null ? (short) 0 : la[i].shortValue();
        return out;
    }
    if (javaArr.getClass().isArray()) {
        int len = java.lang.reflect.Array.getLength(javaArr);
        short[] out = new short[len];
        for (int i = 0; i < len; i++) {
            Object v = java.lang.reflect.Array.get(javaArr, i);
            out[i] = (v == null) ? (short) 0 : ((Number) v).shortValue();
        }
        return out;
    }
    return new short[0];
}

private static void appendPgArrayOfShortOrInteger(StringBuilder sb, Object arr) {
    sb.append('{');
    if (arr instanceof Short[] sa) {
        for (int i = 0; i < sa.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(sa[i] == null ? "NULL" : sa[i].toString());
        }
    } else if (arr instanceof Integer[] ia) {
        for (int i = 0; i < ia.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(ia[i] == null ? "NULL" : ia[i].toString());
        }
    } else if (arr instanceof Long[] la) {
        for (int i = 0; i < la.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(la[i] == null ? "NULL" : la[i].toString());
        }
    } else if (arr != null && arr.getClass().isArray()) {
        int len = java.lang.reflect.Array.getLength(arr);
        for (int i = 0; i < len; i++) {
            if (i > 0) sb.append(',');
            Object v = java.lang.reflect.Array.get(arr, i);
            sb.append(v == null ? "NULL" : v.toString());
        }
    }
    sb.append('}');
}


private void runOptsThreadCorePhase(
        int i,
        Map<Short, String> optTableColumns,
        List<Short> optKeys,
        BlockingQueue<DbClient> dbPool,
        ExecutorService asyncExec,
        Map<Short, String> key2tableMapOptional,
        Map<String, ArrayList<short[]>> mapTable2combs) {


    try {
        schema.createOptTable(i, optTableColumns, "int2[]");
    } catch (SQLException e) {
        log.error("optsThread: failed to create fw_opt{}", i, e);
        return;
    }




    var gen = CombinatorialGenerator.combinations(
            optKeys, i, config.threading.parallelizeSubCombosIfPossible);
    log.info("[DIAG] optsThread: generating C({},{})={} combinations for fw_opt{}",
            optKeys.size(), i, gen.rowCount, i);
    final java.util.concurrent.atomic.AtomicLong comboCounter =
            new java.util.concurrent.atomic.AtomicLong(0);
    final java.util.List<java.util.concurrent.Future<?>> perIFutures =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    gen.stream().forEach(combo -> {
        if (cancelled) return;  // [Iter4 Step 9]
        comboCounter.incrementAndGet();
        if (i <= config.optional.numberOptionalSheetCombosMultithreadAfter) {
            runOptionalInsert(combo, key2tableMapOptional, mapTable2combs,
                    "fw_opt" + i, db);
        } else {
            DbClient slot;
            try {
                slot = dbPool.take();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            perIFutures.add(asyncExec.submit(() -> {
                try {
                    runOptionalInsert(combo, key2tableMapOptional, mapTable2combs,
                            "fw_opt" + i, slot);
                } catch (RuntimeException ex) {
                    log.error("Async runOptionalInsert failed for combo {} → fw_opt{}: {}",
                            combo, i, ex.getMessage(), ex);
                } finally {
                    dbPool.offer(slot);
                }
            }));
        }
    });




    log.info("[DIAG] optsThread: fw_opt{} — processed {} combos; "
            + "awaiting {} async insert(s) to complete before distinctify",
            i, comboCounter.get(), perIFutures.size());
    for (java.util.concurrent.Future<?> f : perIFutures) {
        try {
            f.get(4, TimeUnit.HOURS);
        } catch (java.util.concurrent.TimeoutException e) {
            log.error("optsThread: async insert for fw_opt{} did not complete "
                    + "within 4h — leaving orphaned Future and continuing", i);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("optsThread: interrupted while awaiting async inserts for fw_opt{}", i);
            return;
        } catch (java.util.concurrent.ExecutionException e) {

        }
    }




    try {
        long rowsBefore = db.queryLong("SELECT COUNT(*) FROM fw_opt" + i + ";");
        log.info("[DIAG] optsThread: fw_opt{} rows BEFORE distinctify = {}", i, rowsBefore);
    } catch (Exception e) {
        log.warn("[DIAG] optsThread: could not count fw_opt{}: {}", i, e.getMessage());
    }
    if (config.flags.distinctifyFwFinalOptTables) {
        final int optIdx = i;
        runUnderWriteLock("fw_opt" + i, () ->
                new TableDataDistinctorFnl("fw_opt" + optIdx, 0L, null, db,
                        config.flags.distinctifyJavaSide,
                        config.flags.distinctifySampleAndSkip)
                        .distinctifyByCopyingDistinctedDataToNewTempTableDistinctedAndRecreateGivenTableAsCopyOfNewTempTableDistincted());
    }
    try {
        long rowsAfter = db.queryLong("SELECT COUNT(*) FROM fw_opt" + i + ";");
        log.info("[DIAG] optsThread: fw_opt{} rows AFTER distinctify = {}", i, rowsAfter);
    } catch (Exception e) {
        log.warn("[DIAG] optsThread: could not count fw_opt{} after distinctify: {}", i, e.getMessage());
    }
}



private String buildSqlCore(List<String> tableNames, List<String> comboCols,
String[] fields, String targetTable,
long limitVar, int idxCutoff) {
StringBuilder sb = new StringBuilder("INSERT INTO ").append(targetTable).append(" (");
for (var f : fields) sb.append(f).append(", ");
if (sb.charAt(sb.length() - 2) == ',') sb.setLength(sb.length() - 2);
sb.append(")\nSELECT\n");

for (int i = 0; i < tableNames.size(); i++) {
if (i > 0) sb.append(",\n");
sb.append("nullif(").append(tableNames.get(i)).append(".")
.append(comboCols.get(i)).append(", b.").append(fields[i]);
if (!comboCols.get(i).endsWith("_1")) sb.append("::integer[]");
sb.append(") as ").append(fields[i]);
}
sb.append("\nFROM ").append(tableNames.get(0));
for (int i = 1; i < tableNames.size(); i++) {
sb.append("\njoin ").append(tableNames.get(i))
.append(" on (").append(tableNames.get(i)).append(".combi_id<>")
.append(tableNames.get(0)).append(".combi_id or ")
.append(tableNames.get(0)).append(".combi_id=")
.append(tableNames.get(i)).append(".combi_id)");
}
sb.append("\nCROSS JOIN fw_final_base b\nwhere 0=0\noffset 0\nlimit ")
.append(limitVar).append("\n;");
return sb.toString();
}


private String buildSqlCoreBase(List<String> tableNames, List<String> comboCols,
String[] fields, String targetTable) {


StringBuilder sb = new StringBuilder("INSERT INTO ")
.append(targetTable).append("_base (");
for (var f : fields) sb.append(f).append(", ");
if (sb.charAt(sb.length() - 2) == ',') sb.setLength(sb.length() - 2);
sb.append(")\nSELECT\n");

for (int i = 0; i < tableNames.size(); i++) {
if (i > 0) sb.append(",\n");

sb.append(tableNames.get(i)).append(".").append(comboCols.get(i))
.append(" as ").append(fields[i]);
}
sb.append("\nFROM ").append(tableNames.get(0));
for (int i = 1; i < tableNames.size(); i++) {
sb.append("\njoin ").append(tableNames.get(i))
.append(" on (").append(tableNames.get(i)).append(".combi_id<>")
.append(tableNames.get(0)).append(".combi_id or ")
.append(tableNames.get(0)).append(".combi_id=")
.append(tableNames.get(i)).append(".combi_id)");
}
sb.append("\noffset 0\nlimit 1\n;");
return sb.toString();
}

private long computeLimitVar(List<Long> maxIds, long limitGivenLessThan) {
BigInteger product = BigInteger.ONE;
long limitVar = 1L;
for (int i = maxIds.size() - 1; i >= 0; i--) {
product = product.multiply(BigInteger.valueOf(maxIds.get(i)));
if (product.compareTo(BigInteger.valueOf(limitGivenLessThan)) > 0) break;
limitVar = product.longValue();
}
return limitVar;
}

private int computeCutoffIdx(List<Long> maxIds, long limitGivenLessThan) {
BigInteger product = BigInteger.ONE;
int idx = 0;
for (int i = maxIds.size() - 1; i >= 0; i--) {
product = product.multiply(BigInteger.valueOf(maxIds.get(i)));
if (product.compareTo(BigInteger.valueOf(limitGivenLessThan)) > 0) break;
idx = i;
}
return idx;
}



private void runCartesianPasses(
List<String> tableNames, List<String> comboCols,
String[] fields, List<Long> maxCombiIdList, int idxCutoff,
long limitVar, Map<String, ArrayList<short[]>> mapTable2combs,
String commaSepFields) {

int cores = Runtime.getRuntime().availableProcessors();
List<StringBuilder> sqlPerCore = new ArrayList<>();
for (int k = 0; k < cores; k++) sqlPerCore.add(new StringBuilder());

StringBuilder sb2   = new StringBuilder();
long cartLong       = 0L;
int  cartCount      = 0;
int  coreIdx        = 0;
List<File> sqlFiles = new ArrayList<>();

List<Long> remainingIds = maxCombiIdList.subList(0, idxCutoff);
// [Fast-fix 18052026 / Cluster C] Short-circuit the cartesian decomposition.
//
// runCartesianPasses' sb2 buffer holds `idxCutoff` cells per row but every
// db.copyIn() below targets the FULL `commaSepFields` list (all mandatory
// columns).  Symmetrically, the variant INSERT in buildVariantSql lists
// all columns in its INSERT prefix but its SELECT only projects indices
// [idxCutoff..N-1].  Both produce PostgreSQL column-count mismatches;
// DbClient.copyIn swallows the SQL exception and the surrounding loop
// spins until SIGTERM.
//
// This path is only reachable when limitVarGivenLessThan is small enough
// to make idxCutoff > 0 (default 9.2E18 keeps idxCutoff == 0 — and that's
// why nobody noticed before).  Until the cartesian decomposition is
// rewritten properly (sb2 needs ALL mandatory columns; variant SELECT
// needs the leading columns as offset-literals), short-circuit with a
// clear warning so callers see what happened instead of a 15-min hang.
if (remainingIds.isEmpty() || idxCutoff > 0) {
if (idxCutoff > 0) {
log.warn("[Fast-fix-C] cartesian decomposition skipped: idxCutoff={} > 0 means "
+ "the leading mandatory columns would need offset-literal projection "
+ "in variant SQL — current implementation produces a COPY/INSERT column "
+ "count mismatch.  The single big INSERT in runFnlThreadCoreInserts has "
+ "already run; the remaining cartesian rows are NOT being emitted. "
+ "fw_final row count will reflect only what limitVar={} allowed.",
idxCutoff, limitVar);
}
return;
}

List<long[]> offsetCombinations = buildOffsetCombinations(remainingIds);

for (long[] offsets : offsetCombinations) {
for (int i = 0; i < offsets.length; i++) {
AppUtil.appendPgArray(sb2,
mapTable2combs.get(tableNames.get(i)).get((int) offsets[i]));
sb2.append('\t');
}
if (sb2.length() > 0) {
sb2.setLength(sb2.length() - 1);
sb2.append('\n');
}

String varSql = buildVariantSql(tableNames, comboCols, fields,
offsets, idxCutoff, commaSepFields, limitVar, coreIdx);
sqlPerCore.get(coreIdx).append(varSql);
coreIdx = (coreIdx + 1) % cores;
cartLong++;
cartCount++;

if (cartLong >= 40_000) { flushSqlFiles(sqlPerCore, sqlFiles, true); cartLong = 0; }
if (cartCount >= 100_000) {
db.copyIn(sb2, "fw_final", commaSepFields);
sb2.setLength(0); cartCount = 0;
}
}

flushSqlFiles(sqlPerCore, sqlFiles, false);
if (sb2.length() > 0) db.copyIn(sb2, "fw_final", commaSepFields);
invokePsql(sqlFiles);
}

private List<long[]> buildOffsetCombinations(List<Long> maxIds) {
List<long[]> result = new ArrayList<>();
result.add(new long[0]);
for (long maxId : maxIds) {
List<long[]> next = new ArrayList<>();
for (long[] prev : result) {
for (long id = 1; id <= maxId; id++) {
long[] combo = Arrays.copyOf(prev, prev.length + 1);
combo[combo.length - 1] = id;
next.add(combo);
}
}
result = next;
}
return result;
}

private String buildVariantSql(List<String> tableNames, List<String> comboCols,
String[] fields, long[] offsets, int idxCutoff,
String commaSepFields, long limitVar, int coreIdx) {
StringBuilder sel  = new StringBuilder();
StringBuilder join = new StringBuilder();
StringBuilder where = new StringBuilder("where 0=0\n");

for (int i = idxCutoff; i < offsets.length; i++) {
sel.append("nullif(").append(tableNames.get(i)).append(".")
.append(comboCols.get(i)).append(", b.").append(fields[i]);
if (!comboCols.get(i).endsWith("_1")) sel.append("::integer[]");
sel.append(") as ").append(fields[i]).append(",\n");
if (i > 0) {
join.append("join ").append(tableNames.get(i))
.append(" on (").append(tableNames.get(i)).append(".combi_id<>")
.append(tableNames.get(0)).append(".combi_id or ")
.append(tableNames.get(0)).append(".combi_id=")
.append(tableNames.get(i)).append(".combi_id)\n");
}
where.append("and ").append(tableNames.get(i))
.append(".combi_id=").append(offsets[i]).append('\n');
}

String targetTable = "fw_final" + (coreIdx == 0 ? "" : String.valueOf(coreIdx + 1));
return "INSERT INTO " + targetTable + " (" + commaSepFields + ")\n"
+ "SELECT\n" + sel + "FROM " + tableNames.get(0) + "\n"
+ join + "CROSS JOIN fw_final_base b\n" + where
+ "limit " + limitVar + ";\ncommit;\n";
}

private void flushSqlFiles(List<StringBuilder> sqlPerCore,
List<File> sqlFiles, boolean clearAfter) {
for (int k = 0; k < sqlPerCore.size(); k++) {
if (!sqlPerCore.get(k).toString().startsWith("INSERT")) continue;
File f = new File(config.paths.coreXSqlFilesPath + "core" + (k + 1) + ".sql");
try (BufferedWriter bw = new BufferedWriter(new FileWriter(f.getAbsolutePath(), true))) {
bw.newLine();
bw.write(sqlPerCore.get(k).toString());
sqlFiles.add(f);
} catch (IOException e) {
log.error("Failed to write SQL file {}", f, e);
}
if (clearAfter) sqlPerCore.get(k).setLength(0);
}
}

private void invokePsql(List<File> sqlFiles) {
String connUrl = "postgresql://" + config.db.user + ":" + config.db.passwordAsString()
+ "@" + config.db.host + ":" + config.db.port + "/" + config.db.name;

ExecutorService exec = Executors.newCachedThreadPool();
for (var f : sqlFiles) {
exec.submit(() -> {
ProcessBuilder pb = new ProcessBuilder();
String exe = config.paths.postgresqlBinPath + File.separator
+ (isWindows() ? "psql.exe" : "psql");
pb.command(exe, "--file=" + f.getAbsolutePath(), connUrl);
pb.directory(new File(config.paths.postgresqlBinPath));
try { Process p = pb.start(); p.waitFor(); }
catch (Exception e) { log.error("psql failed for {}", f, e); }
});
}
exec.shutdown();
try {
exec.awaitTermination(4, TimeUnit.HOURS);
} catch (InterruptedException e) {

Thread.currentThread().interrupt();
log.warn("invokePsql interrupted before all psql processes finished");
}

for (var f : sqlFiles) {
try { Files.deleteIfExists(f.toPath()); }
catch (IOException e) { log.warn("Could not delete {}", f); }
}
}




private void runOptionalInsert(List<Short> combo,
Map<Short, String> key2tableMapOptional,
Map<String, ArrayList<short[]>> mapTable2combs,
String targetTable, DbClient client) {


List<String> tableNames  = new ArrayList<>();
List<String> comboCols   = new ArrayList<>();
List<String> fieldNames  = new ArrayList<>();

for (Short key : combo) {
String tableName = key2tableMapOptional.get(key);
if (tableName == null) {
log.warn("runOptionalInsert: key={} has no table in key2tableMapOptional, skipping combo", key);
return;
}
tableNames.add(tableName);


String combosAppendix = tableName.replaceFirst("fw", "").startsWith("2") ? "_1" : "";
comboCols.add("combos" + combosAppendix);


String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
fieldNames.add("\"combos" + key + "_" + sheetName + "\"");
}


// [Refactor 18052026 / step #14] Java cartesian + batched COPY-IN — replaces
// the monolithic `INSERT INTO fw_opt<i> SELECT … 4-WAY JOIN LIMIT N`.
// Mirrors step #5 for fw_final (no NULLIF — OPT SQL didn't use it).
//
// Each runOptionalInsert call already runs on its own asyncExec thread for
// combo-level parallelism; this method stays single-threaded per combo to
// avoid oversubscribing PG (would otherwise be: consumerCount × asyncExec).
// CPU saturation comes from many combos × many slot threads — already
// arranged by the optsThread caller.
//
// Data integrity: source rows read from PG (post-distinctify, authoritative
// — no fwKeyShort sentinel issues), encoded via the same AppUtil.appendPgArray
// format that PG would emit for array_out in the legacy SELECT projection.
// COPY-IN target column list = same `fieldNames` legacy INSERT specified.

// 1. Read each table's rows into memory + pre-encode as PG array literals.
//    Pre-encoding is done ONCE per row and reused for every cartesian
//    iteration that row participates in — eliminates per-row allocation.
final int nDim = tableNames.size();
final String[][] perSheetEncoded = new String[nDim][];
java.math.BigInteger trueCartesian = java.math.BigInteger.ONE;
for (int i = 0; i < nDim; i++) {
String t = tableNames.get(i);
// [Iter2] Route through the store (same data either mode — see runFnlThreadJavaPipeline).
boolean fw2 = t.startsWith("fw2_");
short k = parseKeyFromTableName(t);
java.util.List<short[]> raw = fw2 ? store.readFw2Combos(k) : store.readFwCombos(k);
java.util.List<String> enc = new java.util.ArrayList<>(raw.size());
for (short[] sa : raw) {
StringBuilder tmp = new StringBuilder(sa.length * 4 + 2);
AppUtil.appendPgArray(tmp, sa);
enc.add(tmp.toString());
}
if (enc.isEmpty()) {
log.warn("[Iter2] store source {} is empty — skipping combo {} → {}",
t, combo, targetTable);
return;
}
perSheetEncoded[i] = enc.toArray(new String[0]);
trueCartesian = trueCartesian.multiply(
java.math.BigInteger.valueOf(perSheetEncoded[i].length));
}

// 2. Skip oversized combos (matches legacy semantics, but using
//    PG-rowCount-based product instead of MAX-based — they coincide when
//    combi_id is contiguous, which legacy distinctify guaranteed).
if (trueCartesian.compareTo(java.math.BigInteger.valueOf(
        config.optional.limitOptionalSheetsCombosMax)) > 0) {
log.warn("Optional combo {} exceeds limit ({}), skipped", combo, trueCartesian);
return;
}

// 3. Effective row cap.
long limitVar = config.threading.limitVarGivenLessThan;
if (trueCartesian.bitLength() <= 62) {
long tc = trueCartesian.longValueExact();
limitVar = Math.min(tc, limitVar);
}
















// 4. Build the COPY-IN target column list (= legacy INSERT INTO target's
//    columns, joined with ", ").  Other fw_opt<i> columns get default (NULL)
//    — matches what the legacy partial-column INSERT did.
StringBuilder fieldsBuf = new StringBuilder();
for (int fi = 0; fi < fieldNames.size(); fi++) {
if (fi > 0) fieldsBuf.append(", ");
fieldsBuf.append(fieldNames.get(fi));
}
final String commaSepFields = fieldsBuf.toString();

// 5. Cartesian iteration + batched COPY-IN on the slot connection.
final int batchSize = Math.max(1_000, config.threading.counter4copyMax);
StringBuilder batchBuf = new StringBuilder(batchSize * 64);
int batchRows = 0;
long emitted = 0L;
int[] idx = new int[nDim];

OUTER:
while (emitted < limitVar) {
if ((emitted & 0xFFFFL) == 0 && cancelled) break OUTER;  // [Iter4 Step 9] every 64K rows
for (int i = 0; i < nDim; i++) {
if (i > 0) batchBuf.append('\t');
batchBuf.append(perSheetEncoded[i][idx[i]]);
}
batchBuf.append('\n');
batchRows++;
emitted++;

if (batchRows >= batchSize) {
client.copyIn(batchBuf, targetTable, commaSepFields);
batchBuf.setLength(0);
batchRows = 0;
}

int carry = 1;
for (int i = nDim - 1; i >= 0; i--) {
idx[i] += carry;
if (idx[i] >= perSheetEncoded[i].length) {
idx[i] = 0;
carry = 1;
} else {
carry = 0;
break;
}
}
if (carry == 1) break;
}

if (batchBuf.length() > 0) {
client.copyIn(batchBuf, targetTable, commaSepFields);
}

if (log.isDebugEnabled()) {
log.debug("[Refactor-#14] runOptionalInsert combo={} → {} emitted={} (trueCartesian={})",
combo, targetTable, emitted, trueCartesian);
}
}



private void waitForFinalTablesFilled() {
String lockQuery =
"SELECT COUNT(*) FROM pg_locks l\n"
+ "JOIN pg_database d ON l.database = d.oid\n"
+ "WHERE d.datname = current_database()\n"
+ "  AND l.relation::regclass::text LIKE 'fw_fina%'\n"
+ "  AND l.relation IS NOT NULL\n"
+ "  AND l.mode NOT IN ('AccessShareLock')\n"
+ "  AND pid <> pg_backend_pid();";

log.info("Waiting for fw_final* tables to be fully written...");
try {
Thread.sleep(3_000);
while (true) {
long active = db.queryLong(lockQuery);
if (active == 0) break;
log.debug("Active locks on fw_final*: {}", active);
Thread.sleep(config.threading.sleepTimeCheckFinalFilled * 1_000L);
}
} catch (InterruptedException e) {

Thread.currentThread().interrupt();
log.warn("waitForFinalTablesFilled interrupted — may exit before all writes complete");
}
log.info("fw_final* tables fully written");
}

private static boolean isWindows() {
return System.getProperty("os.name", "").matches(".*[Ww]indows.*");
}

private static void sleep(int millis) {
try { Thread.sleep(millis); }
catch (InterruptedException e) { Thread.currentThread().interrupt(); }
}
}
