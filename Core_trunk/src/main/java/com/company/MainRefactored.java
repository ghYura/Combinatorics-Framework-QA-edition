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

import com.company.config.AppConfig;
import com.company.daoModelService.FW_CUSTOM_VARService;
import com.company.daoModelService.SheetNameService;
import com.company.db.DbClient;
import com.company.db.SchemaProvisioner;
import com.company.precompute.HeapWatchdog;
import com.company.precompute.PrecomputeMemoryBudget;
import com.company.store.IntermediateTableStore;
import com.company.store.JavaIntermediateTableStore;
import com.company.store.PgIntermediateTableStore;
import com.company.store.SwitchableIntermediateTableStore;
import com.company.utils.HibernateSessionFactoryUtil;
import com.company.excel.ParsedWorkbook;
import com.company.excel.WorkbookParser;
import com.company.models.FW_CUSTOM_VAR;
import com.company.models.SheetName;
import com.company.utils.PowerShellCommand;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Sheet;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ExecutionException;


public class MainRefactored {





private static final Logger log = LogManager.getLogger(MainRefactored.class);


public static final boolean USE_FLUSH_HELPER    = true;
public static final boolean USE_EMPTY_TBL_GUARD = true;




@Deprecated
public static void appendPgArray(StringBuilder sb, int[] arr) {
AppUtil.appendPgArray(sb, arr);
}


@Deprecated
public static void appendPgArray(StringBuilder sb, short[] arr) {
AppUtil.appendPgArray(sb, arr);
}



@FunctionalInterface
public interface TriFunction<T, U, V, R> {
R apply(T t, U u, V v);
default <K> TriFunction<T, U, V, K> andThen(
java.util.function.Function<? super R, ? extends K> after) {
Objects.requireNonNull(after);
return (T t, U u, V v) -> after.apply(apply(t, u, v));
}
}



public static void main(String[] args) {


System.setProperty("com.mchange.v2.log.MLog",
"com.mchange.v2.log.FallbackMLog");
System.setProperty("com.mchange.v2.log.FallbackMLog.DEFAULT_CUTOFF_LEVEL",
"OFF");

long startTime = System.currentTimeMillis();


AppConfig config;
try {
config = AppConfig.load();
} catch (IOException e) {
log.fatal("Cannot load fw.properties", e);
return;
}
log.info("Configuration loaded from fw.properties");














HibernateSessionFactoryUtil.init(
config.threading.workerCount,
config.toHibernateProperties());
log.info("[REFACTOR11] HibernateSessionFactoryUtil initialised (workerCount={})",
config.threading.workerCount);



PrintPretty.configure(config.flags.printPretty);


if (config.flags.preEraseDb) {
// Each statement is strict; the enclosing catch below is the ONE deliberate
// tolerance here (pre-erase is best-effort by design), and it now sees the
// real failure with SQLSTATE + statement instead of a swallowed WARN line.
try (DbClient pgAdmin = DbClient.createForDb(config.db, "postgres")) {
pgAdmin.executeOrThrow(
"SELECT pg_terminate_backend(pg_stat_activity.pid)\n"
+ "FROM pg_stat_activity\n"
+ "WHERE pg_stat_activity.datname = '" + config.db.name + "'\n"
+ "  AND pid <> pg_backend_pid();");
pgAdmin.executeOrThrow(
"DROP DATABASE IF EXISTS \"" + config.db.name + "\";");
// [Fast-fix 18052026] Without this CREATE, the very next DbClient.create()
// below blows up Hibernate's C3P0 with 235× "FATAL: database <name> does not
// exist" (SQLState 08001) and the engine spends 3+ min in retry storms.
pgAdmin.executeOrThrow(
"CREATE DATABASE \"" + config.db.name + "\";");
log.info("Pre-erase completed for database '{}' (dropped + recreated)", config.db.name);
} catch (Exception e) {
log.warn("Pre-erase step encountered an error (continuing)", e);
}
} else {
// [Iter2-fix 19052026] CREATE DATABASE IF NOT EXISTS workaround.
//
// When preEraseDB=false the engine USED to assume the target database
// already existed.  If not, the very next DbClient.create() below would
// open a c3p0 pool that fails every checkout with
//   FATAL: database "<config.db.name>" does not exist  (SQLState 08001)
// — and the Hibernate SessionFactory build NPEs trying to read JDBC
// metadata.  Logs show hundreds of repeats, no useful work done.
//
// Mirror of the preEraseDB=true path but non-destructive: query
// pg_database first, only CREATE when the row is absent.  Data in
// existing databases is preserved.
try (DbClient pgAdmin = DbClient.createForDb(config.db, "postgres")) {
String exists = pgAdmin.queryString(
"SELECT '1' FROM pg_database WHERE datname = '" + config.db.name + "';");
if (!"1".equals(exists)) {
log.warn("Database '{}' does not exist — auto-creating "
+ "(preEraseDB=false; data-preserving one-shot CREATE)",
config.db.name);
// Tolerate 42P04 only: the pg_database check above is racy, and a
// concurrently-created database IS the desired end state here.
pgAdmin.executeTolerateAlreadyExists(
"CREATE DATABASE \"" + config.db.name + "\";");
} else {
log.debug("Database '{}' already exists — skipping auto-create",
config.db.name);
}
} catch (Exception e) {
log.warn("Could not verify/create database '{}' (continuing; "
+ "subsequent DbClient.create() will likely fail): {}",
config.db.name, e.getMessage());
}
}


if (config.flags.launchReader) {
validatePath("JavaExe_fileLocationPath",
config.paths.javaExePath, "java.exe", config.flags);
validatePath("CombinatoricsReader_fileLocationPath",
config.paths.combinatoricsReaderPath,
"CombinatoricsReader.jar", config.flags);
}


// Fail closed: SchemaProvisioner refuses topologies where the PostgreSQL
// server cannot see the requested tablespace directories. Catching that
// here would silently land every table on pg_default — the exact defect
// this call used to have — so the exception is left to abort the run.
try (DbClient pgAdmin = DbClient.createForDb(config.db, "postgres")) {
SchemaProvisioner provisioner =
new SchemaProvisioner(pgAdmin, config.tablespace);
provisioner.provisionTablespaces(pgAdmin);
}


// [Iter3.1] Pass config.pool so db.pool.* properties from fw.properties
// actually reach the main client.  Previously this used the no-PoolConfig
// overload → silently capped at the hardcoded 2/3 default regardless of
// what the user set.  Admin pgAdmin clients above stay on the default
// because they're short-lived and don't need bigger pools.
try (DbClient db = DbClient.create(config.db, config.pool)) {
SchemaProvisioner schema = new SchemaProvisioner(db, config.tablespace);
schema.initStaticSchema();
log.info("Static schema initialised");









HibernateSessionFactoryUtil.buildEager();


// Tier-1 win 1.2: pick ScheduleParser impl by file extension or by
// explicit `core.input.format` property.  Legacy XLSX path is unchanged.
java.nio.file.Path inputPath = java.nio.file.Path.of(config.paths.xlsxFilePath);
String declaredFormat = config.rawProperty("core.input.format");
com.company.excel.ScheduleParser scheduleParser = (declaredFormat != null && !declaredFormat.isBlank())
        ? com.company.excel.ScheduleParser.byName(declaredFormat)
        : com.company.excel.ScheduleParser.forFile(inputPath);
log.info("Processing input file: {}  (parser={})",
        config.paths.xlsxFilePath, scheduleParser.getClass().getSimpleName());
ParsedWorkbook workbook;
try {
workbook = scheduleParser.parse(inputPath, config.workbook);
} catch (Exception e) {
log.fatal("Schedule parsing failed", e);
return;
}
log.info("Workbook parsed: {} data sheets ({} virtual)",
workbook.shortSheetHM.size(), workbook.virtualSheetNames.size());

// Tier-3.5 — dump the canonical ParsedWorkbook as JSON sibling so
// subsequent iterations (orchestrator-driven) can mutate plain text
// instead of XLSX.  Format-symmetric with JsonScheduleParser: re-feeding
// the dumped JSON via core.input.format=json yields an equivalent
// downstream pipeline.
//
// Default behaviour: ON when input is non-JSON — auto-derives sibling
// path next to the input file (e.g. test_e2e_metric.xlsx →
// test_e2e_metric.iter0.json).  Skipped automatically when input is
// already JSON (don't dump JSON over JSON).  Set
//   core.input.dumpJsonPath=/custom/path.json   → explicit override
//   core.input.dumpJsonAuto=false                → disable entirely
//   core.input.dumpJsonSuffix=.dump.json         → customise the suffix
{
    String explicitPath = config.rawProperty("core.input.dumpJsonPath");
    String autoStr      = config.rawProperty("core.input.dumpJsonAuto");
    String suffix       = config.rawProperty("core.input.dumpJsonSuffix");
    // Default-on; explicit "false" / "0" / "no" disables auto-derivation.
    boolean autoOn = (autoStr == null) || !autoStr.trim().toLowerCase(java.util.Locale.ROOT)
            .matches("false|0|no|off|disable");

    java.nio.file.Path dumpPath = null;
    if (explicitPath != null && !explicitPath.isBlank()) {
        dumpPath = java.nio.file.Path.of(explicitPath);
    } else if (autoOn) {
        dumpPath = com.company.excel.JsonScheduleWriter.deriveSiblingJsonPath(
                inputPath, suffix);
        // Defensive: never overwrite the source itself.
        if (dumpPath != null && dumpPath.toAbsolutePath().equals(inputPath.toAbsolutePath())) {
            log.warn("[Tier-3.5] auto-derived dump path equals input — skipping to avoid overwrite");
            dumpPath = null;
        }
    }

    if (dumpPath != null) {
        try {
            com.company.excel.JsonScheduleWriter.writeToFile(workbook, dumpPath);
            log.info("[Tier-3.5] ParsedWorkbook dumped as JSON sibling: {} ({} sheets, maxSheetNumber={})",
                    dumpPath, workbook.stringSheetHM.size(), workbook.maxSheetNumber);
        } catch (Exception dumpEx) {
            log.warn("[Tier-3.5] JSON dump to {} FAILED: {}", dumpPath, dumpEx.getMessage());
        }
    }
}


writeSheetNames(workbook, db, config);
writeCustomVars(workbook, db);
writeRunMeFirstOnce(workbook, db);
writeArguments(workbook, db);

// Tier-3.5 — optional closed-loop feedback ingestion.  When the previous
// iteration's Analyzer wrote a BundleSeed JSON to disk, MainRefactored
// loads it here so the rest of the pipeline (SheetWorker / FinalTableAssembler,
// future narrowing strategies) has visibility into "what worked last time".
// Empty path → no-op, byte-for-byte identical legacy behaviour.
{
    String seedPath = config.rawProperty("core.seed.inputPath");
    if (seedPath != null && !seedPath.isBlank()) {
        try {
            com.company.bundle.BundleSeedAdapter seed =
                    com.company.bundle.BundleSeedAdapter.loadFromFile(java.nio.file.Path.of(seedPath));
            log.info("[Tier-3.5] {}", seed.renderSummary());
            // Per-metric range diagnostics — when narrowing strategies land
            // they'll consume this same data.
            for (var e : seed.observedRanges.entrySet()) {
                log.info("[Tier-3.5] observed range '{}'  n={}  min={}  max={}  mean={}  stdev={}",
                        e.getKey(), e.getValue().n,
                        e.getValue().min, e.getValue().max, e.getValue().mean, e.getValue().stdev);
            }
            // Winner-class telemetry — confirms the seed isn't degenerate.
            log.info("[Tier-3.5] winners by role: pareto={}, champion-min={}, champion-max={}, balanced={}",
                    seed.winnersWithRolePrefix("pareto").size(),
                    seed.winnersWithRolePrefix("champion-min:").size(),
                    seed.winnersWithRolePrefix("champion-max:").size(),
                    seed.winnersWithRolePrefix("balanced:").size());
        } catch (Exception seedEx) {
            log.warn("[Tier-3.5] Failed to load BundleSeed from {}: {}", seedPath, seedEx.getMessage());
        }
    }
}


SeqParser.SeqParseResult seq =
SeqParser.parse(workbook, workbook.sheetData, config.seq);
log.info("FW_Seq parsed: {} sheet directives", seq.mapShKey2seqList.size());


















// [Iter4.3] Resolve precompute mode (AUTO consults Layer-1 estimator).
// JAVA forces in-JVM intermediates + pure-Java fnl baseline.  DB keeps the
// legacy PG-way; intermediate.storage then controls fw_/fw2_ storage choice.
AppConfig.PrecomputeMode resolvedPrecompute = resolvePrecomputeMode(config, seq, workbook);

// [Iter2 + Iter4.3] Pick intermediate-storage backend.  When precompute=JAVA
// (resolved), forces in-JVM regardless of intermediate.storage.  Otherwise
// intermediate.storage decides.
IntermediateTableStore intermediateStore =
        createIntermediateStore(config, db, schema, workbook, resolvedPrecompute);
log.info("[Iter2] Intermediate storage mode: {} (precompute resolved: {})",
        intermediateStore.modeName(), resolvedPrecompute);

for (var key : workbook.sheetData.keySet()) {
if (!seq.mapShKey2seqList.containsKey(key)
|| seq.mapShKey2seqList.get(key).isEmpty()) {
continue;
}
try {
intermediateStore.createFwTable(key);
} catch (SQLException e) {
log.error("Failed to create fw_{}", key, e);
}
}


SheetWorker worker = new SheetWorker(config, db, schema, workbook, intermediateStore);

// [Iter4 Step 9] Holder for the FinalTableAssembler so the watchdog ABORT
// callback (defined below, before FA is constructed) can reach into it.
final java.util.concurrent.atomic.AtomicReference<FinalTableAssembler> assemblerRef =
        new java.util.concurrent.atomic.AtomicReference<>();

// [Iter4.4] Heap watchdog — mode depends on RAW config (forced vs auto)
// and RESOLVED decision.  PASSIVE for db (diagnostic only); ABORT_ON_HIGH
// for forced JAVA (clean fail before OOM); DRAIN_ON_CRITICAL for
// auto-resolved JAVA (would drain to PG; drain mechanism is future work).
HeapWatchdog.Mode watchdogMode = watchdogModeFor(config.precomputeMode, resolvedPrecompute);
Runnable drainHook = buildDrainHook(intermediateStore, config, db, schema, workbook);
try (HeapWatchdog watchdog = new HeapWatchdog(
        watchdogMode,
        evt -> {
            // ABORT callback (forced-JAVA HIGH): cancel SheetWorker at its
            // next checkpoint.  [Iter4 Step 9] also cancel FA so it bails out
            // of its producer/consumer + opts cartesian loops instead of
            // grinding toward OOM.
            worker.cancel();
            FinalTableAssembler fa = assemblerRef.get();
            if (fa != null) fa.cancel();
            log.error("[Iter4.4] SheetWorker.cancel() + FinalTableAssembler.cancel() called via watchdog abort signal");
        },
        evt -> {
            // [Iter4.5] DRAIN callback (AUTO-JAVA CRITICAL): request the
            // SheetWorker coordinator to quiesce in-flight sheets, migrate
            // the in-memory store to PG, and swap the SwitchableStore wrapper.
            // Subsequent sheets resume against PG transparently.  No-op in
            // forced-JAVA / db modes (drainHook is logged-no-op for non-
            // switchable stores).
            worker.requestDrain(drainHook);
        })) {
    watchdog.start();
    watchdog.setStage("SheetWorker.processAll");
    try {
        worker.processAll(
                seq.toCombinatoricsHM,
                seq.toCombinatoricsHMoptional,
                seq.toCombinatoricsHMexclude,
                seq.mapShKey2seqList,
                seq.reuseSet,
                seq.reuseTableOnlySet,
                seq.keyShortExcluded1List,
                seq.keyShortExcluded2List);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        log.error("Sheet processing interrupted", e);
        return;
    }
    watchdog.setStage("post-processing + FinalTableAssembler.assemble");
    // (the rest of the try-block below — post-processing maps, final assembly,
    // cleanup — runs with watchdog still active.  Watchdog stops on close().)





















{
Set<Short> allSheetKeys = new LinkedHashSet<>(workbook.sheetData.keySet());
for (Short key : allSheetKeys) {
boolean hasDirectives = seq.mapShKey2seqList.containsKey(key)
&& !seq.mapShKey2seqList.get(key).isEmpty();

if (!hasDirectives) {




seq.toCombinatoricsHM.remove(key);
seq.toCombinatoricsHMoptional.remove(key);
seq.toCombinatoricsHMexclude.remove(key);
} else {


List<Short> dataList;

dataList = seq.toCombinatoricsHM.get(key);
if (dataList != null && dataList.isEmpty())
seq.toCombinatoricsHM.remove(key);

dataList = seq.toCombinatoricsHMoptional.get(key);
if (dataList != null && dataList.isEmpty())
seq.toCombinatoricsHMoptional.remove(key);

dataList = seq.toCombinatoricsHMexclude.get(key);
if (dataList != null && dataList.isEmpty())
seq.toCombinatoricsHMexclude.remove(key);
}
}
log.info("[REFACTOR21] Post-processing cleanup: toCombinatoricsHM={} keys, "
+ "optional={} keys, exclude={} keys",
seq.toCombinatoricsHM.size(),
seq.toCombinatoricsHMoptional.size(),
seq.toCombinatoricsHMexclude.size());
}


for (var key : seq.toCombinatoricsHMoptional.keySet()) {
if (worker.getKey2tableMap().containsKey(key)) {
worker.getKey2tableMapOptional().put(
key, worker.getKey2tableMap().remove(key));
log.debug("key={} moved to key2tableMapOptional", key);
}
}


log.info("[DIAG] ══════════ After step 11: key maps ══════════");
log.info("[DIAG] key2tableMap ({} entries):", worker.getKey2tableMap().size());
for (var entry : worker.getKey2tableMap().entrySet()) {
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(entry.getKey());
log.info("[DIAG]   key={} sheet={} table={}", entry.getKey(), sheetName, entry.getValue());
}
log.info("[DIAG] key2tableMapOptional ({} entries):", worker.getKey2tableMapOptional().size());
for (var entry : worker.getKey2tableMapOptional().entrySet()) {
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(entry.getKey());
log.info("[DIAG]   key={} sheet={} table={}", entry.getKey(), sheetName, entry.getValue());
}
log.info("[DIAG] toCombinatoricsHMoptional ({} keys): {}",
seq.toCombinatoricsHMoptional.size(), seq.toCombinatoricsHMoptional.keySet());






Map<Short, String> finalTableColumns = new LinkedHashMap<>();
var joinedKeys = new java.util.TreeMap<>(seq.toCombinatoricsHM);
joinedKeys.putAll(seq.toCombinatoricsHMoptional);
for (Short k : joinedKeys.keySet()) {
if (!seq.mapShKey2seqList.containsKey(k)
|| seq.mapShKey2seqList.get(k).isEmpty()) continue;
String name = workbook.shortStringSheetKey2SheetNameHM.get(k);
if (name != null) finalTableColumns.put(k, name);
}

String createSqlFinal;
try {



schema.createFinalTable("", finalTableColumns, "int2[]", "_pkey");
schema.createFinalTable("_base", finalTableColumns, "int2[]", "_pkey");
createSqlFinal = "";
} catch (SQLException e) {
log.error("Failed to create fw_final tables", e);
return;
}


FinalTableAssembler assembler = new FinalTableAssembler(
config, db, schema, workbook, intermediateStore, resolvedPrecompute);
assemblerRef.set(assembler);  // [Iter4 Step 9] expose to watchdog ABORT callback
try {
assembler.assemble(
seq.toCombinatoricsHM,
seq.toCombinatoricsHMoptional,
worker.getKey2tableMap(),
worker.getKey2tableMapOptional(),
worker.getMapTable2combs(),
createSqlFinal);
} catch (InterruptedException | ExecutionException e) {
log.error("Final assembly failed", e);
return;
}


// Strict: CREATE OR REPLACE cannot hit a benign duplicate; any failure
// here means the cleanup function is absent and the SELECT below lies.
db.executeOrThrow(
"CREATE OR REPLACE FUNCTION footgun(IN _schema TEXT, IN _base TEXT)\n"
+ "RETURNS void LANGUAGE plpgsql AS $$\n"
+ "DECLARE row record;\n"
+ "BEGIN\n"
+ "  FOR row IN SELECT table_schema, table_name\n"
+ "    FROM information_schema.tables\n"
+ "    WHERE table_type='BASE TABLE' AND table_schema=_schema\n"
+ "      AND table_name ILIKE (_base||'%')\n"
+ "      AND table_name !~ 'fw_(final|opt){1}(\\d)?(_base_copy)?'\n"
+ "  LOOP\n"
+ "    EXECUTE 'DROP TABLE '||quote_ident(row.table_schema)"
+ "||'.'||quote_ident(row.table_name);\n"
+ "  END LOOP;\n"
+ "END; $$;");
// Strict: a failed sweep used to leave stale fw_ tables for later runs
// to trip over, behind one WARN line nobody read.
db.executeOrThrow("SELECT footgun('public','fw_');");

// IF EXISTS instead of the old DELETE-then-DROP pair: fw_final_base only
// exists when the assembler's base path ran, and its absence is expected —
// the old swallow was papering over exactly that 42P01. (The DELETE before
// a DROP did nothing and could not survive the absence case either.)
db.executeOrThrow("DROP TABLE IF EXISTS public.fw_final_base;");


if (config.tablespace.isCopyDb) {
copyCrossDatabase(config, db);
}


if (config.flags.setLoggedTablesAtEnd) {
// Strict: the user explicitly asked for LOGGED tables; delivering
// UNLOGGED ones behind a WARN would betray that request on crash.
db.executeOrThrow(
"DO $$DECLARE r record;\n"
+ "DECLARE v_schema varchar := 'public';\n"
+ "BEGIN\n"
+ "  FOR r IN\n"
+ "    SELECT 'ALTER TABLE \"'||table_schema||'\".\"'"
+ "||table_name||'\" SET LOGGED;' AS a\n"
+ "    FROM information_schema.tables WHERE table_schema=v_schema\n"
+ "  LOOP EXECUTE r.a; END LOOP;\n"
+ "END$$;");
log.info("All tables set to LOGGED");
}


if (config.flags.launchReader && !config.flags.skipIfInvalidFilePath) {
try {
// Cross-platform launch (May30): replaced the Windows-only PowerShellCommand path with a plain
// ProcessBuilder so the Core->Reader auto-launch hook works on Linux too (the old powershell.exe
// exec was a silent no-op off Windows). The Reader starts in THIS process's working dir, so it
// reads the same ./fw.properties (unified Core+Reader config); inheritIO streams its
// stdout/stderr/stdin through the Core. FIRE-AND-FORGET (May30, user request): the Core does NOT
// block on the Reader — waitFor() is commented out below, so the Core launches the Reader and
// returns; the Reader keeps running as a detached child (survives the Core's exit on Linux).
String javaExe = config.paths.javaExePath;
Path configuredJava = Paths.get(javaExe);
if (configuredJava.getParent() != null) {
javaExe = configuredJava.normalize().toAbsolutePath().toString();
}
log.info("Launching CombinatoricsReader (ProcessBuilder, fire-and-forget): {} -jar {}",
javaExe, config.paths.combinatoricsReaderPath);
Process reader = new ProcessBuilder(javaExe, "-jar", config.paths.combinatoricsReaderPath)
.inheritIO()
.start();
// fire-and-forget: do NOT block the Core on the Reader run. Re-enable by uncommenting these two lines.
// int rc = reader.waitFor();
// log.info("CombinatoricsReader exited with code {}", rc);
} catch (Exception e) {
log.warn("Failed to launch CombinatoricsReader", e);
}
}

}  // [Iter4.4] end of try-with-resources for HeapWatchdog (started at line ~371)

} catch (Exception e) {
log.fatal("Unhandled exception in main", e);
return;
}

long elapsed = System.currentTimeMillis() - startTime;
long minutes  = elapsed / 60_000;
double seconds = (elapsed % 60_000) / 1_000.0;
log.info("Done. Time spent: {} min {} sec", minutes, String.format("%.3f", seconds));
}



private static void writeSheetNames(ParsedWorkbook wb, DbClient db, AppConfig config) {
var sheet = wb.stringSheetHM.get("FW_SheetNames");
var fmt = new DataFormatter();
var svc = new SheetNameService();




Set<String> covered = new LinkedHashSet<>();



if (sheet != null) {
for (var row : sheet) {
SheetName sn = null;
for (var cell : row) {
var v   = fmt.formatCellValue(cell);
int col = cell.getColumnIndex();
if (col == 0) sn = new SheetName();
if (sn == null) continue;
switch (col) {
case 0 -> sn.setSheet(v);
case 1 -> sn.setName(normEmpty(v));
case 2 -> { sn.setEnding(normEmpty(v)); svc.addSheetName(sn); }
}
}

if (sn != null && sn.getSheet() != null) covered.add(sn.getSheet());

}
} else {
log.warn("[Issue1] writeSheetNames: FW_SheetNames sheet missing — every data sheet will get a synthetic entry");
}

boolean autoGen = config != null
&& config.workbook != null
&& config.workbook.autoGenerateMissingFwSheetNames;
if (autoGen) {
int synthesised = 0;
for (Map.Entry<Short, String> e : wb.shortStringSheetKey2SheetNameHM.entrySet()) {
String sheetName = e.getValue();
if (sheetName == null || covered.contains(sheetName)) continue;
SheetName sn = new SheetName();
sn.setSheet(sheetName);
sn.setName("");
sn.setEnding("");
svc.addSheetName(sn);
synthesised++;
log.info("[Issue1] writeSheetNames: synthesised entry for uncovered sheet '{}'", sheetName);
}
log.info("[Issue1] writeSheetNames: {} synthetic FW_SheetNames entries inserted", synthesised);
}

log.info("SheetNames written to DB");
}

private static void writeCustomVars(ParsedWorkbook wb, DbClient db) {
var sheet = wb.stringSheetHM.get("FW_CUSTOM_VAR");
if (sheet == null) return;
var fmt = new DataFormatter();
var svc = new FW_CUSTOM_VARService();


for (var row : sheet) {
FW_CUSTOM_VAR c = null;
for (var cell : row) {
var v   = fmt.formatCellValue(cell);
int col = cell.getColumnIndex();
if (col == 0) c = new FW_CUSTOM_VAR();
if (c == null) continue;
switch (col) {
case 0 -> c.setFwCustomVar(Integer.parseInt(v));
case 1 -> { c.setMessage(normEmpty(v)); svc.addFW_CUSTOM_VAR(c); }
}
}
}
log.info("CustomVars written to DB");
}

private static void writeRunMeFirstOnce(ParsedWorkbook wb, DbClient db) {
Sheet sheet = wb.stringSheetHM.get("FW_RunMeFirstOnce");
if (sheet == null) return;
DataFormatter fmt = new DataFormatter();
sheet.forEach(row -> row.forEach(cell -> {
String v = fmt.formatCellValue(cell);
// Strict: the table always exists (schema-init.sql); a lost INSERT here
// silently dropped user-authored setup code from the run.
db.executeOrThrow(
"INSERT INTO public.runmefirstonce (code_once) VALUES ($$" + v + "$$)");
}));
log.info("RunMeFirstOnce written to DB");
}

private static void writeArguments(ParsedWorkbook wb, DbClient db) {
Sheet sheet = wb.stringSheetHM.get("FW_Arguments");
if (sheet == null) return;
DataFormatter fmt = new DataFormatter();
sheet.forEach(row -> row.forEach(cell -> {
String v = fmt.formatCellValue(cell);
// Strict: same as RunMeFirstOnce — a lost row here was a silently
// incomplete arguments table.
db.executeOrThrow(
"INSERT INTO public.arguments (args) VALUES ($$" + v + "$$)");
}));
log.info("Arguments written to DB");
}



private static String normEmpty(String v) {
return "FW_EMPTY_STRING".equalsIgnoreCase(v) ? "" : v;
}

private static void removeEmptySheetFromAllMaps(Short key,
SeqParser.SeqParseResult seq) {
seq.toCombinatoricsHM.remove(key);
seq.toCombinatoricsHMoptional.remove(key);
seq.toCombinatoricsHMexclude.remove(key);
}


@Deprecated
public static long countRowsEstimate(String tableName, DbClient db) {
return AppUtil.countRowsEstimate(tableName, db);
}

private static void copyCrossDatabase(AppConfig config, DbClient db) {
String connTemplate = "port=" + config.db.port
+ " user=" + config.db.user
+ " password=" + config.db.passwordAsString()
+ " dbname=";
// Strict: the batch is self-idempotent (IF EXISTS / IF NOT EXISTS), so a
// failure means dblink is genuinely unavailable or the copy itself broke —
// the one thing the isCopyDb user asked for cannot be allowed to no-op.
db.executeOrThrow(
"DROP EXTENSION IF EXISTS dblink CASCADE;\n"
+ "CREATE EXTENSION IF NOT EXISTS dblink;\n"
+ "DO $$\n"
+ "DECLARE database_name TEXT;\n"
+ "DECLARE conn_string TEXT;\n"
+ "DECLARE row record;\n"
+ "BEGIN\n"
+ "FOR database_name IN\n"
+ "  (SELECT datname FROM pg_database\n"
+ "   WHERE datistemplate=false AND datname!='postgres')\n"
+ "LOOP\n"
+ "  conn_string = '" + connTemplate + "' || database_name;\n"
+ "  FOR row IN\n"
+ "    SELECT tablename FROM dblink(conn_string,\n"
+ "      'SELECT tablename FROM pg_tables\n"
+ "       WHERE tablename ~ ''fw(\\d)*?_(\\d)*?(_base)?$''\n"
+ "         AND tablename != ''fw''\n"
+ "         AND tablename != ''fw_final_base_copy''\n"
+ "         AND tablename not like ''fw_opt%''\n"
+ "         AND tablename !~ ''fw_(final){1}(\\d){0,}(_base_copy)?'';')\n"
+ "    AS t1(tablename TEXT)\n"
+ "  LOOP\n"
+ "    perform dblink_exec(conn_string,\n"
+ "      'drop table public.'||quote_ident(row.tablename)||';');\n"
+ "  END LOOP;\n"
+ "END LOOP;\n"
+ "end; $$");
log.info("Cross-database copy completed");
}

/** [Iter4.4] Pick the heap-watchdog mode based on user intent + resolved decision.
 *  - DB (resolved)        → PASSIVE (logs heap pressure as diagnostic only).
 *  - JAVA forced          → ABORT_ON_HIGH (clean abort at 90% rather than OOM).
 *  - JAVA via AUTO-resolve → DRAIN_ON_CRITICAL (graceful drain at 95% — drain
 *                            mechanism itself is future work).
 */
private static HeapWatchdog.Mode watchdogModeFor(
        AppConfig.PrecomputeMode raw, AppConfig.PrecomputeMode resolved) {
    if (resolved != AppConfig.PrecomputeMode.JAVA) return HeapWatchdog.Mode.PASSIVE;
    return (raw == AppConfig.PrecomputeMode.JAVA)
            ? HeapWatchdog.Mode.ABORT_ON_HIGH
            : HeapWatchdog.Mode.DRAIN_ON_CRITICAL;
}

/** [Iter4.3] Resolve core.precompute={auto|db|java} into a concrete JAVA/DB
 *  decision.  AUTO consults the Layer-1 memory-budget estimator; FORCE_* modes
 *  bypass the estimator and return the forced value.  Called once per run,
 *  after SeqParse + before SheetWorker construction. */
private static AppConfig.PrecomputeMode resolvePrecomputeMode(
        AppConfig config, SeqParser.SeqParseResult seq, ParsedWorkbook workbook) {
    if (config.precomputeMode == AppConfig.PrecomputeMode.JAVA) {
        log.info("[Iter4.3] core.precompute=JAVA (forced; estimator skipped)");
        return AppConfig.PrecomputeMode.JAVA;
    }
    if (config.precomputeMode == AppConfig.PrecomputeMode.DB) {
        log.info("[Iter4.3] core.precompute=DB (forced; estimator skipped)");
        return AppConfig.PrecomputeMode.DB;
    }
    // AUTO: invoke estimator.  Logs its own full breakdown at INFO.
    PrecomputeMemoryBudget.Report rep = PrecomputeMemoryBudget.estimate(
            seq, workbook, config, PrecomputeMemoryBudget.Mode.AUTO);
    AppConfig.PrecomputeMode resolved = (rep.decision == PrecomputeMemoryBudget.Decision.JAVA)
            ? AppConfig.PrecomputeMode.JAVA
            : AppConfig.PrecomputeMode.DB;
    log.info("[Iter4.3] core.precompute=AUTO → resolved to {}", resolved);
    return resolved;
}

/** [Iter2 + Iter4.3 + Iter4.5] Build the intermediate-table store.
 *  - resolvedPrecompute=JAVA via AUTO   → SwitchableStore wrapping Java; can
 *    drain to PG if watchdog fires CRITICAL.
 *  - resolvedPrecompute=JAVA via FORCED → plain Java (no drain support;
 *    forced mode aborts on HIGH instead of draining).
 *  - resolvedPrecompute=DB              → intermediate.storage decides between
 *    PG and Java for the intermediate fw_/fw2_ tables independently. */
private static IntermediateTableStore createIntermediateStore(
        AppConfig config, DbClient db, SchemaProvisioner schema,
        ParsedWorkbook workbook, AppConfig.PrecomputeMode resolvedPrecompute) {
    if (resolvedPrecompute == AppConfig.PrecomputeMode.JAVA) {
        JavaIntermediateTableStore javaStore = new JavaIntermediateTableStore();
        if (config.precomputeMode == AppConfig.PrecomputeMode.AUTO) {
            return new SwitchableIntermediateTableStore(javaStore);
        }
        return javaStore;
    }
    switch (config.intermediateStorage) {
        case MEMORY:
            return new JavaIntermediateTableStore();
        case PG:
        default:
            return new PgIntermediateTableStore(
                    db, schema,
                    config.threading.counter4copyMax,
                    workbook.shortStringSheetKey2SheetNameHM);
    }
}

/** [Iter4.5] Build the drain hook that the watchdog's DRAIN callback runs
 *  when AUTO-JAVA hits CRITICAL.  Migrates in-memory state to a fresh PG
 *  store and swaps the SwitchableStore wrapper to point at PG.  Returns a
 *  no-op when the store isn't a SwitchableStore (forced-JAVA / db path). */
private static Runnable buildDrainHook(
        IntermediateTableStore store, AppConfig config, DbClient db,
        SchemaProvisioner schema, ParsedWorkbook workbook) {
    if (!(store instanceof SwitchableIntermediateTableStore sw)) {
        return () -> log.warn("[Iter4.5/drain] store is not switchable ({}) — no drain available",
                store.modeName());
    }
    return () -> {
        IntermediateTableStore current = sw.current();
        if (!(current instanceof JavaIntermediateTableStore javaStore)) {
            log.warn("[Iter4.5/drain] already drained — current store is {}", current.modeName());
            return;
        }
        log.warn("[Iter4.5/drain] migrating in-memory store → PG");
        IntermediateTableStore pgStore = new PgIntermediateTableStore(
                db, schema, config.threading.counter4copyMax,
                workbook.shortStringSheetKey2SheetNameHM);
        try {
            javaStore.drainAllTo(pgStore);
        } catch (java.sql.SQLException e) {
            log.error("[Iter4.5/drain] migration failed; store NOT swapped (pipeline continues in-memory and likely OOMs)", e);
            return;
        }
        sw.swap(pgStore);
        log.warn("[Iter4.5/drain] swap complete — remaining pipeline runs against PG-backed store");
    };
}

private static void validatePath(String propKey, String pathStr,
String expectedFile, AppConfig.FeatureFlags flags) {
try {
Path p = Paths.get(pathStr);
if ("JavaExe_fileLocationPath".equals(propKey) && p.getParent() == null) return;
if (Files.notExists(p)) {
log.error("Path '{}' for property '{}' does not exist", pathStr, propKey);
if (!flags.skipIfInvalidFilePath) System.exit(-1);
}
} catch (InvalidPathException e) {
log.error("Invalid path '{}' for property '{}'", pathStr, propKey);
if (!flags.skipIfInvalidFilePath) System.exit(-1);
}
}
}
