














































































package com.company;

import com.company.combinatorics.CombinatorialGenerator;
import com.company.config.AppConfig;
import com.company.db.DbClient;
import com.company.db.SchemaProvisioner;
import com.company.excel.ParsedWorkbook;
import com.company.store.IntermediateTableStore;
import com.company.utils.CustomInterceptor2;
import com.company.models.FW;
import one.util.streamex.IntStreamEx;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;


public final class SheetWorker {

private static final Logger log = LogManager.getLogger(SheetWorker.class);

private static final String COMBOS_DATA_TYPE = "int2[]";


private static final Pattern PARAM_PATTERN = Pattern.compile("\\((\\d+)\\)");

private final AppConfig         config;
private final DbClient          db;
private final SchemaProvisioner schema;
private final ParsedWorkbook    workbook;

/** [Iter2] All fw_/fw2_ intermediate I/O goes through this. */
private final IntermediateTableStore store;


private final Map<Short, String>              key2tableMap;


private final Map<Short, String>              key2tableMapOptional;


private final Map<String, ArrayList<short[]>> mapTable2combs;


private final BraceOperationHandler braceHandler;


private volatile Map<Short, List<Short>> allSourceDataSnapshot;


private final ConcurrentHashMap<Short, CompletableFuture<Void>> sheetDone =
new ConcurrentHashMap<>();


private volatile Set<Short>  reuseSet;
private volatile Set<Short>  reuseTableOnlySet;
private volatile List<Short> excl1List;
private volatile List<Short> excl2List;

private volatile boolean cancelled = false;

// `core.replace.*` policy violations recorded while a `fail` policy is active.
//
// processAll runs each sheet in its own virtual thread and catches Exception per
// sheet, logging it and carrying on — so throwing inside a sheet marks that sheet
// failed but leaves the run reporting success. A `fail` policy that does not fail
// the run would be worse than no policy at all, so violations are collected here
// and re-raised on the calling thread once all sheets have finished. Only these
// policies populate it; general sheet-failure behaviour is untouched.
private final List<String> replacePolicyFailures =
java.util.Collections.synchronizedList(new ArrayList<>());

// [Iter4.5] Drain coordination — set by HeapWatchdog drain callback (AUTO-JAVA
// CRITICAL).  Sheets entering processSheet check {@code drainBarrier}; if non-
// null they block on it until the coordinator finishes migrating the in-memory
// store to PG and swaps the SwitchableIntermediateTableStore delegate.
private final java.util.Set<Short> activeSheets = java.util.concurrent.ConcurrentHashMap.newKeySet();
private volatile CompletableFuture<Void> drainBarrier;

public SheetWorker(AppConfig config, DbClient db,
SchemaProvisioner schema, ParsedWorkbook workbook,
IntermediateTableStore store) {
this.config               = config;
this.db                   = db;
this.schema               = schema;
this.workbook             = workbook;
this.store                = store;
this.key2tableMap         = new ConcurrentSkipListMap<>();
this.key2tableMapOptional = new ConcurrentSkipListMap<>();
this.mapTable2combs       = new ConcurrentHashMap<>();


this.braceHandler         = new BraceOperationHandler(
config, db, schema, workbook, store, this::awaitSheetCompletion);
}




public void processAll(
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, List<Short>> toCombinatoricsHMoptional,
Map<Short, List<Short>> toCombinatoricsHMexclude,
Map<Short, List<String>> mapShKey2seqList) throws InterruptedException {
processAll(toCombinatoricsHM, toCombinatoricsHMoptional, toCombinatoricsHMexclude,
mapShKey2seqList, new LinkedHashSet<>(), new LinkedHashSet<>(),
new LinkedList<>(), new LinkedList<>());
}


public void processAll(
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, List<Short>> toCombinatoricsHMoptional,
Map<Short, List<Short>> toCombinatoricsHMexclude,
Map<Short, List<String>> mapShKey2seqList,
Set<Short> reuseSet,
Set<Short> reuseTableOnlySet,
List<Short> excl1List,
List<Short> excl2List) throws InterruptedException {


this.reuseSet          = reuseSet;
this.reuseTableOnlySet = reuseTableOnlySet;
this.excl1List         = excl1List;
this.excl2List         = excl2List;











{
Map<Short, List<Short>> merged = new LinkedHashMap<>();
for (var entry : toCombinatoricsHM.entrySet()) {
if (entry.getValue() != null)
merged.put(entry.getKey(), new ArrayList<>(entry.getValue()));
}
for (var entry : toCombinatoricsHMoptional.entrySet()) {
if (entry.getValue() != null)
merged.putIfAbsent(entry.getKey(), new ArrayList<>(entry.getValue()));
}
for (var entry : toCombinatoricsHMexclude.entrySet()) {
if (entry.getValue() != null)
merged.putIfAbsent(entry.getKey(), new ArrayList<>(entry.getValue()));
}
this.allSourceDataSnapshot = Collections.unmodifiableMap(merged);
}

















var allKeys = new LinkedHashSet<>(toCombinatoricsHM.keySet());
allKeys.addAll(toCombinatoricsHMoptional.keySet());
allKeys.addAll(toCombinatoricsHMexclude.keySet());

List<CompletableFuture<Void>> futures = new ArrayList<>(allKeys.size());



try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
for (var key : allKeys) {
if (cancelled) break;

final List<String> seqList = mapShKey2seqList.get(key);
if (seqList == null || seqList.isEmpty()) continue;





final Short finalKey = key;
final var doneFuture = new CompletableFuture<Void>();
sheetDone.put(finalKey, doneFuture);

futures.add(CompletableFuture.runAsync(() -> {
try {
processSheet(finalKey, seqList,
toCombinatoricsHM, toCombinatoricsHMoptional,
toCombinatoricsHMexclude);
} catch (Exception e) {
log.error("Sheet {} processing failed", finalKey, e);
} finally {


doneFuture.complete(null);
}
}, executor));
}

try {
CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();
} catch (CompletionException e) {
if (Thread.currentThread().isInterrupted()) {
throw new InterruptedException("Interrupted during sheet processing");
}
}
}

// Re-raise any `core.replace.*` violation on this thread: inside a sheet it was
// swallowed by the per-sheet catch above, which would have left a `fail` policy
// silently not failing.
synchronized (replacePolicyFailures) {
if (!replacePolicyFailures.isEmpty()) {
throw new IllegalStateException(
"core.replace policy refused this run:" + System.lineSeparator()
+ "  " + String.join(System.lineSeparator() + "  ", replacePolicyFailures));
}
}
}

public void cancel() { this.cancelled = true; }

/** [Iter4.5] Drain coordinator entry-point.  Called from the HeapWatchdog
 *  CRITICAL callback (AUTO-JAVA mode) via a dedicated daemon thread.  The
 *  coordinator:
 *  <ol>
 *    <li>Installs a barrier so newly-starting processSheet calls block.</li>
 *    <li>Waits for all currently-active sheets to complete (best-effort,
 *        10 min/sheet timeout — same bound as the brace handler's
 *        sheetWaiter so consistent failure semantics).</li>
 *    <li>Runs the supplied drain hook (typically: Java→PG migration + swap).</li>
 *    <li>Releases the barrier; queued sheets resume against the new store.</li>
 *  </ol>
 *
 *  Idempotent if called when no drain is needed — but caller should check
 *  the SwitchableStore type to avoid redundant drains. */
public void coordinateDrain(Runnable drainHook) {
    log.warn("[Iter4.5/drain] coordinator starting — installing barrier and quiescing in-flight sheets ({} active)",
            activeSheets.size());
    CompletableFuture<Void> barrier = new CompletableFuture<>();
    drainBarrier = barrier;
    try {
        // Snapshot active sheet keys at coordinator start.  Sheets that
        // haven't entered processSheet yet will check the barrier on entry;
        // sheets already past the check are tracked via activeSheets.
        java.util.List<Short> snapshot = new java.util.ArrayList<>(activeSheets);
        for (Short k : snapshot) {
            var fut = sheetDone.get(k);
            if (fut == null) continue;
            try {
                fut.get(10, java.util.concurrent.TimeUnit.MINUTES);
            } catch (java.util.concurrent.TimeoutException e) {
                log.warn("[Iter4.5/drain] sheet {} did not complete within 10 min — proceeding with drain anyway",
                        k);
            } catch (Exception e) {
                log.warn("[Iter4.5/drain] error awaiting sheet {} completion: {}", k, e.getMessage());
            }
        }
        log.warn("[Iter4.5/drain] in-flight quiesce complete; running drain hook");
        drainHook.run();
        log.warn("[Iter4.5/drain] drain hook complete; releasing barrier (queued sheets resume against new store)");
    } catch (Throwable t) {
        log.error("[Iter4.5/drain] drain coordinator failed", t);
    } finally {
        barrier.complete(null);
        drainBarrier = null;
    }
}

/** [Iter4.5] Convenience: spawn a daemon coordinator thread so the
 *  HeapWatchdog daemon doesn't block on the drain itself. */
public void requestDrain(Runnable drainHook) {
    Thread t = new Thread(() -> coordinateDrain(drainHook),
            "sheet-worker-drain-coordinator");
    t.setDaemon(true);
    t.start();
}


private void awaitSheetCompletion(Short key) {
if (key == null) return;
var future = sheetDone.get(key);
if (future == null) return;
try {
future.get(10, java.util.concurrent.TimeUnit.MINUTES);
} catch (java.util.concurrent.TimeoutException e) {
log.warn("Timeout (10 min) waiting for sheet {} to complete — "
+ "proceeding with brace operation anyway", key);
} catch (Exception e) {
log.warn("Error waiting for sheet {} completion: {}", key, e.getMessage());
}
}

public Map<Short, String>              getKey2tableMap()         { return key2tableMap; }
public Map<Short, String>              getKey2tableMapOptional()  { return key2tableMapOptional; }
public Map<String, ArrayList<short[]>> getMapTable2combs()       { return mapTable2combs; }




private void processSheet(
Short key, List<String> seqList,
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, List<Short>> toCombinatoricsHMoptional,
Map<Short, List<Short>> toCombinatoricsHMexclude) throws Exception {

Thread.currentThread().setName(
workbook.shortStringSheetKey2SheetNameHM.getOrDefault(key, key.toString())
+ "-sheetWorker");

// [Iter4.5] Drain barrier check.  If a heap-pressure drain is in progress,
// block here until the coordinator finishes migrating Java→PG and swaps
// the underlying store.  This sheet then proceeds against the new store
// transparently (store field still points at the SwitchableStore wrapper).
{
    var barrier = drainBarrier;
    if (barrier != null) {
        log.info("[Iter4.5/drain] sheet {} waiting at drain barrier", key);
        try { barrier.get(10, java.util.concurrent.TimeUnit.MINUTES); }
        catch (Exception e) {
            log.warn("[Iter4.5/drain] sheet {} barrier wait failed ({}); proceeding anyway",
                    key, e.getMessage());
        }
    }
}
activeSheets.add(key);
try {

final boolean isExclude = toCombinatoricsHMexclude.containsKey(key);
boolean       isCombi2  = false;



final SheetState sheetState = new SheetState();





ArrayList<short[]> fwKeyShort = new ArrayList<>();
fwKeyShort.add(new short[]{});



var fComboId = new AtomicLong(0L);
var fwId = new AtomicLong(0L);
var fwId2 = new AtomicLong(0L);

log.info("Processing sheet key={} seq={}", key, seqList);

if (seqList.size() > 1) {
store.createFw2Table(key);
}

for (int i = 0; i < seqList.size(); i++) {
if (cancelled) {
log.info("Cancelled at sheet {}, seq[{}]", key, i);
return;
}
final String directive = seqList.get(i);
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
log.info("[DIAG-PASS] Sheet {} (key={}) directive[{}]='{}' isCombi2={} BEFORE",
sheetName, key, i, directive.length() > 40 ? directive.substring(0, 40) + "..." : directive, isCombi2);

isCombi2 = runDirective(key, i, directive, isCombi2,
fwKeyShort, fwId, fwId2, fComboId,
toCombinatoricsHM, toCombinatoricsHMoptional, toCombinatoricsHMexclude,
sheetState);


{
// [Iter2] Counts come from store regardless of mode (PG-backed routes
// to SELECT COUNT; memory routes to list.size()).  Same diagnostic
// purpose — confirm a directive emitted into the expected table.
long fwRows  = store.count(key, false);
long fw2Rows = store.count(key, true);
log.info("[DIAG-PASS] Sheet {} (key={}) directive[{}] AFTER: isCombi2={} fw_rows={} fw2_rows={} fwKeyShort.size={}",
sheetName, key, i, isCombi2, fwRows, fw2Rows, fwKeyShort.size());
}

















if (config.flags.distinctifyFwXYTables
&& (isCombiDirective(directive) || directive.startsWith("FW_("))) {
String activeTable = (isCombi2 ? "fw2_" : "fw_") + key;
log.debug("[HOTFIX] Per-directive distinctify: table={} after directive[{}]", activeTable, i);
store.distinctify(key, isCombi2);
}





if (isCombi2 && i > 0 && i < seqList.size() - 1) {
try {
store.swapFw2ToFw(key);
isCombi2 = false;
log.debug("Table rebuild: fw_ ↔ fw2_ swap for key={} between directives", key);
} catch (SQLException e) {
log.error("Table rebuild failed for key={}", key, e);
}
}
}

final String finalTable = (isCombi2 ? "fw2_" : "fw_") + key;
















{
if (store.isEmpty(key, isCombi2)) {
log.warn("Sheet {} final table '{}' is empty — not registering in key maps", key, finalTable);

toCombinatoricsHM.remove(key);
toCombinatoricsHMoptional.remove(key);
mapTable2combs.remove(finalTable);

fwKeyShort.clear();

if (config.flags.distinctifyFwXYTables) {
store.distinctify(key, isCombi2);
}
log.info("Sheet {} done → table {} (empty)", key, finalTable);
return;
}
}

if (toCombinatoricsHMoptional.containsKey(key)) {
key2tableMapOptional.put(key, finalTable);
} else if (!isExclude) {
key2tableMap.put(key, finalTable);
}


if (isCombi2) {
mapTable2combs.remove("fw_" + key);
}


if (!isExclude) {
mapTable2combs.put(finalTable, (ArrayList<short[]>) fwKeyShort.clone());
}
fwKeyShort.clear();


{
long preDistinctCount = store.count(key, isCombi2);
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
log.info("[DIAG] Sheet {} (key={}) table={}: {} rows BEFORE distinctify",
sheetName, key, finalTable, preDistinctCount);
}

if (config.flags.distinctifyFwXYTables) {
store.distinctify(key, isCombi2);
}


{
long postDistinctCount = store.count(key, isCombi2);
String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
log.info("[DIAG] Sheet {} (key={}) table={}: {} rows AFTER distinctify",
sheetName, key, finalTable, postDistinctCount);
}
log.info("Sheet {} done → table {}", key, finalTable);
} finally {
    // [Iter4.5] Always remove from activeSheets so the drain coordinator's
    // quiesce-wait can complete cleanly regardless of how processSheet exits.
    activeSheets.remove(key);
}
}




private boolean runDirective(
Short key, int pass, String directive, boolean isCombi2,
ArrayList<short[]> fwKeyShort,
AtomicLong fwId, AtomicLong fwId2, AtomicLong fComboId,
Map<Short, List<Short>> toCombinatoricsHM,
Map<Short, List<Short>> toCombinatoricsHMoptional,
Map<Short, List<Short>> toCombinatoricsHMexclude,
SheetState sheetState) throws Exception {


if (directive.startsWith("FW_(")) {
final Map<Short, List<Short>> toCombinatoricsHMcopy = buildCopy(toCombinatoricsHM);
return braceHandler.execute(directive, key, toCombinatoricsHMcopy,
fwKeyShort, fwId, mapTable2combs, key2tableMap, key2tableMapOptional,
reuseSet != null ? reuseSet : Set.of(),
reuseTableOnlySet != null ? reuseTableOnlySet : Set.of(),
excl1List != null ? excl1List : List.of(),
excl2List != null ? excl2List : List.of());
}



if (directive.startsWith("FW_Group")) {
sheetState.isGroup = true;
final Map<Short, List<Short>> srcMap = buildCopy(toCombinatoricsHM);
String patternString1 = "(FW_ReplaceRE\\([\"](.+?)[\"],\\s+(\"(.*)\")\\))";
java.util.regex.Matcher matcher = Pattern.compile(patternString1).matcher(directive);
while (matcher.find()) {
if (!matcher.group(2).isEmpty()) {
if (matcher.group(3).contains("+")) {
Short joinKey = workbook.stringShortSheetName2SheetKeyHM.get(
matcher.group(3).replaceAll("\\W+", ""));
if (joinKey != null && srcMap.containsKey(joinKey)) {
String replacement = Arrays.stream(
matcher.group(3)
.replaceAll("\\w+", srcMap.get(joinKey).get(0).toString())
.replaceAll("\"", "")
.split("\\s?\\+\\s?"))
.collect(Collectors.joining());
sheetState.replacerHM.put(matcher.group(2), replacement);
}
} else if (matcher.group(3).equals("\"\"")) {
sheetState.replacerHM.put(matcher.group(2), "");
} else {
sheetState.replacerHM.put(matcher.group(2), matcher.group(4));
}
}
}
applyReplaceAuthoringPolicies(key, sheetState);
sheetState.resetReplaceCounters();
log.debug("FW_Group parsed: {} replacements", sheetState.replacerHM.size());
return isCombi2;
}



if (directive.startsWith("FW_Separator(")) {
sheetState.isSeparate = true;
String sepName = directive.substring(directive.indexOf('(') + 1, directive.lastIndexOf(')'));
sheetState.separatorKey = workbook.stringShortSheetName2SheetKeyHM.get(sepName);
final Map<Short, List<Short>> srcMap = buildCopy(toCombinatoricsHM);
if (sheetState.separatorKey != null && srcMap.containsKey(sheetState.separatorKey)) {
sheetState.separatorValue = srcMap.get(sheetState.separatorKey).get(0).intValue();
}
log.debug("FW_Separator parsed: key={} value={}", sheetState.separatorKey, sheetState.separatorValue);
return isCombi2;
}

if (!isCombiDirective(directive)) return isCombi2;

final Map<Short, List<Short>> toCombinatoricsHMcopy = buildCopy(toCombinatoricsHM);






final String  algoType = resolveAlgoType(directive);
final int     rawM     = resolveM(directive, algoType, toCombinatoricsHMcopy, key, pass);

if (pass == 0 && rawM == -2) {

final int n = toCombinatoricsHMcopy.getOrDefault(key, Collections.emptyList()).size();
log.debug("All/Full first pass for key={}: iterating m=1..{}", key, n);
for (int m = 1; m <= n; m++) {
final GeneratorSpec<Short> spec = buildDirectiveGeneratorWithM(
key, pass, directive, toCombinatoricsHMcopy, m);
runFirstPass(key, spec, fwKeyShort, fwId);
}
boolean result = false;


String checkTable = "fw_" + key;
if (store.isEmpty(key, false)) {
log.warn("Table '{}' is empty after processing — removing from key maps", checkTable);
log.warn("[fail-honest][AI-proposition] reconciliation: dropping sheet '{}' means fw_final will MISS its combos column — a PARTIAL result. HIGH-confidence: silent/deceptive-success is the dominant ROI tax; a user must never mistake a partial/corrupted run for a clean one. Non-blocking note — processing logic unchanged.", checkTable);
key2tableMap.remove(key);
key2tableMapOptional.remove(key);
mapTable2combs.remove(checkTable);
toCombinatoricsHM.remove(key);
toCombinatoricsHMoptional.remove(key);
}
return result;
}

final GeneratorSpec<Short>    spec                  =
buildDirectiveGenerator(key, pass, directive, toCombinatoricsHMcopy);


boolean result = (pass == 0)
? runFirstPass(key, spec, fwKeyShort, fwId)
: runSubsequentPass(key, spec, fwKeyShort, fwId2, fComboId, sheetState);



String checkTable = (result ? "fw2_" : "fw_") + key;
if (store.isEmpty(key, result)) {
log.warn("Table '{}' is empty after processing — removing from key maps", checkTable);
log.warn("[fail-honest][AI-proposition] reconciliation: dropping sheet '{}' means fw_final will MISS its combos column — a PARTIAL result. HIGH-confidence: silent/deceptive-success is the dominant ROI tax; a user must never mistake a partial/corrupted run for a clean one. Non-blocking note — processing logic unchanged.", checkTable);
key2tableMap.remove(key);
key2tableMapOptional.remove(key);
mapTable2combs.remove(checkTable);
toCombinatoricsHM.remove(key);
toCombinatoricsHMoptional.remove(key);
}

return result;
}




private GeneratorSpec<Short> buildDirectiveGenerator(
Short key, int pass, String directive,
Map<Short, List<Short>> toCombinatoricsHMcopy) {

final String  algoType      = resolveAlgoType(directive);
final boolean isCartesFirst = directive.matches("FW_Cartes(?i)_first\\(.*\\)");


Short keyShort2 = null;
if (algoType.equals("FW_Cartes")) {
final String inner = directive.substring(
directive.indexOf('(') + 1, directive.lastIndexOf(')'));
keyShort2 = workbook.stringShortSheetName2SheetKeyHM.get(inner);
}


CombinatorialGenerator.SubsetMode subsetMode   = CombinatorialGenerator.SubsetMode.DEFAULT;
int[]                             subsetParams = new int[]{};

if (algoType.equals("FW_Subsets") && directive.contains("_")) {

final String modeStr =
directive.replaceAll("FW_Subsets_|\\s+|[,]+|\\d+|\\(|\\)", "");
try {
subsetMode = CombinatorialGenerator.SubsetMode.valueOf(modeStr.toUpperCase());
} catch (IllegalArgumentException ignored) {

}




subsetParams = Arrays.stream(
directive.replaceAll("[^\\d,]+", "").split(","))
.filter(s -> !s.isEmpty())
.mapToInt(Integer::parseInt)
.toArray();
}

final int     mElementsPerRow = resolveM(directive, algoType, toCombinatoricsHMcopy, key, pass);
final boolean allowDuplicates = directive.endsWith(
"FW_Permut(PermutationGenerator.TreatDuplicatesAs.IDENTICAL)");

final List<Short> srcList  = toCombinatoricsHMcopy.get(key);
final List<Short> srcList2 = toCombinatoricsHMcopy.get(keyShort2);





if (srcList == null) {
log.warn("buildDirectiveGenerator: srcList is null for key={}. "
+ "Returning empty generator.", key);
return new GeneratorSpec<>(
CombinatorialGenerator.subsets(Collections.emptyList(),
CombinatorialGenerator.SubsetMode.DEFAULT, new int[]{},
config.threading.parallelizeSubCombosIfPossible),
algoType, key, keyShort2, mElementsPerRow, isCartesFirst);
}


final boolean par = config.threading.parallelizeSubCombosIfPossible;








final int safeM = (mElementsPerRow < 0) ? 1 : mElementsPerRow;

final CombinatorialGenerator<Short> gen = buildGenerator(
algoType, srcList, safeM, allowDuplicates,
srcList2, isCartesFirst, subsetMode, subsetParams, par);

return new GeneratorSpec<>(gen, algoType, key, keyShort2, mElementsPerRow, isCartesFirst);
}


private GeneratorSpec<Short> buildDirectiveGeneratorWithM(
Short key, int pass, String directive,
Map<Short, List<Short>> toCombinatoricsHMcopy, int explicitM) {

final String  algoType      = resolveAlgoType(directive);
final boolean isCartesFirst = directive.matches("FW_Cartes(?i)_first\\(.*\\)");

Short keyShort2 = null;
if (algoType.equals("FW_Cartes")) {
final String inner = directive.substring(
directive.indexOf('(') + 1, directive.lastIndexOf(')'));
keyShort2 = workbook.stringShortSheetName2SheetKeyHM.get(inner);
}

CombinatorialGenerator.SubsetMode subsetMode   = CombinatorialGenerator.SubsetMode.DEFAULT;
int[]                             subsetParams = new int[]{};
if (algoType.equals("FW_Subsets") && directive.contains("_")) {
final String modeStr =
directive.replaceAll("FW_Subsets_|\\s+|[,]+|\\d+|\\(|\\)", "");
try {
subsetMode = CombinatorialGenerator.SubsetMode.valueOf(modeStr.toUpperCase());
} catch (IllegalArgumentException ignored) { }

subsetParams = Arrays.stream(
directive.replaceAll("[^\\d,]+", "").split(","))
.filter(s -> !s.isEmpty())
.mapToInt(Integer::parseInt)
.toArray();
}

final boolean allowDuplicates = directive.endsWith(
"FW_Permut(PermutationGenerator.TreatDuplicatesAs.IDENTICAL)");
final List<Short> srcList  = toCombinatoricsHMcopy.get(key);
final List<Short> srcList2 = toCombinatoricsHMcopy.get(keyShort2);
final boolean par = config.threading.parallelizeSubCombosIfPossible;


if (srcList == null) {
log.warn("buildDirectiveGeneratorWithM: srcList is null for key={}. "
+ "Returning empty generator.", key);
return new GeneratorSpec<>(
CombinatorialGenerator.subsets(Collections.emptyList(),
CombinatorialGenerator.SubsetMode.DEFAULT, new int[]{}, par),
algoType, key, keyShort2, explicitM, isCartesFirst);
}

final CombinatorialGenerator<Short> gen = buildGenerator(
algoType, srcList, explicitM, allowDuplicates,
srcList2, isCartesFirst, subsetMode, subsetParams, par);

return new GeneratorSpec<>(gen, algoType, key, keyShort2, explicitM, isCartesFirst);
}




private boolean runFirstPass(
Short key, GeneratorSpec<Short> spec,
ArrayList<short[]> fwKeyShort,
AtomicLong fwId) {

final boolean useParallel =
spec.generator.parallel
&& spec.generator.rowCount.longValue() > config.threading.parallelThreshold;

if (useParallel) {
final int chunkCount = resolveParallelChunks();
final List<Stream<List<Short>>> chunks = spec.generator.parallelStreams(chunkCount);
final List<CompletableFuture<Void>> futs = new ArrayList<>(chunks.size());
try (var exec = Executors.newVirtualThreadPerTaskExecutor()) {
for (Stream<List<Short>> chunk : chunks) {
futs.add(CompletableFuture.runAsync(
() -> consumeFirstPassChunk(chunk, key, fwKeyShort, fwId),
exec));
}
CompletableFuture.allOf(futs.toArray(new CompletableFuture[0])).join();
}
} else {

consumeFirstPassChunk(
spec.generator.stream().limit(Integer.MAX_VALUE - 8L),
key, fwKeyShort, fwId);
}








return false;
}


private void consumeFirstPassChunk(
Stream<List<Short>> chunk,
Short key,
ArrayList<short[]> fwKeyShort,
AtomicLong fwId) {


// [Iter2] First-pass chunk emit goes through the store.  In PG mode the
// store still amortises writes via its internal StringBuilder + COPY-IN
// (batchSize == config.threading.counter4copyMax); in memory mode the row
// goes straight into the in-heap list.  Identical wire-format for fwKeyShort
// (used by mapTable2combs / legacy diagnostics).
chunk.forEach(row -> {
final int n = row.size();
final short[] combo = new short[n];
int idx = 0;
for (Short s : row) combo[idx++] = s.shortValue();

final long cid = fwId.incrementAndGet();

synchronized (fwKeyShort) {
fwKeyShort.add(combo);
}

store.appendFwRow(key, cid, combo);
});

store.flushFw(key);
}




private boolean runSubsequentPass(
Short key, GeneratorSpec<Short> spec,
ArrayList<short[]> fwKeyShort,
AtomicLong fwId2, AtomicLong fComboId,
SheetState sheetState) throws Exception {

// [Iter2] Hibernate retarget kept as a no-op for downstream code paths
// (FW_Group + brace handler post-read) that still use CustomInterceptor2
// when in PG mode.  In memory mode it costs nothing.
CustomInterceptor2.setCurrentTable("fw_" + key);


synchronized (fwKeyShort) {
fwKeyShort.clear();
fwKeyShort.add(new short[]{});
}

// [Iter2] Replaces:
//   final FwService fwService = new FwService();
//   final long maxId = db.queryLong("SELECT MAX(combi_id) FROM public.fw_<k>;");
//   fwService.getFWfromPreloadedMap(j) inside the j-loop
// Pre-load fw_<key> rows ONCE via store; the j-loop maps into fwRowsByCombiId.
final long maxId = store.maxCombiId(key, false);
final java.util.Map<Long, short[]> fwRowsByCombiId = store.readFwAsMap(key);

final int mParam = spec.rawM;







if (sheetState.isGroup) {
// [Iter2] Replaces fwService.getListOfFW().  Build the List<FW> from the
// pre-loaded map ordered by combi_id (Hibernate's default getListOf order).
List<FW> inListFWasList;
{
    // [Iter4 Step 10] Sort source rows by COMBO CONTENT (lex), not by combi_id.
    //
    // Why: FW_Group's downstream SubsetsG enumerates subsets by INDEX into
    // this list, and concatenates rows in index order.  When source-list
    // order depends on store backend (PG SELECT DISTINCT order, Java
    // LinkedHashMap insertion order, MIN(combi_id) ORDER BY ...) the same
    // logical workload produces DIFFERENT concatenations → different
    // post-distinctify counts (the 33,674,483 vs 34,368,597 fw_opt4 split
    // observed across pre-Iter2 legacy, post-Step-8, etc).
    //
    // Content-sort makes the source-list order a pure function of the data,
    // independent of store backend / PG version / planner choice.  This
    // gives a SINGLE deterministic fw_opt4 count across every reasonable
    // implementation — the canonical truth the algorithm should always
    // produce, regardless of who computed the distinctify.
    inListFWasList = new ArrayList<>(fwRowsByCombiId.size());
    for (Map.Entry<Long, short[]> e : fwRowsByCombiId.entrySet()) {
        short[] sc = e.getValue();
        FW fwr = new FW();
        fwr.setCombiId(e.getKey());
        int[] ic = new int[sc.length];
        for (int i = 0; i < sc.length; i++) ic[i] = sc[i];
        fwr.setCombo(ic);
        inListFWasList.add(fwr);
    }
    inListFWasList.sort((a, b) -> {
        int[] ca = a.getCombo();
        int[] cb = b.getCombo();
        int min = Math.min(ca.length, cb.length);
        for (int i = 0; i < min; i++) {
            int c = Integer.compare(ca[i], cb[i]);
            if (c != 0) return c;
        }
        return Integer.compare(ca.length, cb.length);
    });
}


if (inListFWasList == null || inListFWasList.isEmpty()) {
log.warn("FW_Group: fw_{} returned empty (no rows in store), skipping", key);
sheetState.replacerHM.clear();
sheetState.isGroup = false;
CustomInterceptor2.clearCurrentTable();
return true;
}



int groupSize = (int) maxId;
List<Integer> mValues = new ArrayList<>();
if (mParam == -1) {
mValues.add(groupSize);
} else if (mParam == -2) {
for (int t = 1; t <= groupSize; t++) mValues.add(t);
} else {
mValues.add(Math.max(1, mParam));
}

for (int curM : mValues) {



if (curM < 0) {
log.warn("FW_Group: skipping negative curM={} for key={}", curM, key);
continue;
}
if ("FW_Combi".equals(spec.algoType) && curM > inListFWasList.size()) {
log.debug("FW_Group: skipping FW_Combi curM={} > listSize={} for key={}",
curM, inListFWasList.size(), key);
continue;
}


Stream<?> gStream;
switch (spec.algoType) {
case "FW_Combi":
gStream = new com.company.combinatorics.CombinationsDistinctG(inListFWasList, curM).getDistinctCombinations();
break;
case "FW_CombiR":
gStream = new com.company.combinatorics.CombinationsWithRepetitionsG(inListFWasList, curM).getRepeatedCombinations();
break;
case "FW_Permut":
gStream = new com.company.combinatorics.PermutationsSimpleG(inListFWasList, false).getPermutationsSimple();
break;
case "FW_PermutR":
gStream = new com.company.combinatorics.PermutationsWithRepetitionsG(inListFWasList, curM).getRepeatedPermutations();
break;
case "FW_Subsets":
gStream = new com.company.combinatorics.SubsetsG(inListFWasList).getDistinctCombinations();
break;
case "FW_Cartes":
gStream = new com.company.combinatorics.CartesianProductG(inListFWasList, inListFWasList).getCartesianProduct();
break;
default:
log.warn("FW_Group: unsupported algo type '{}', skipping", spec.algoType);
continue;
}

gStream.forEach(w -> {
String curStr = w.toString();
final String beforeRewrite = curStr;
sheetState.rowsSeen.increment();

for (var entry : sheetState.replacerHM.entrySet()) {
final String beforeThisPattern = curStr;
curStr = curStr.replaceAll(entry.getKey(), entry.getValue());
// Count a hit when this pattern changed the string. An identity rewrite
// therefore reads as "no hits", which is exactly what it is.
if (!curStr.equals(beforeThisPattern)) {
var hits = sheetState.replaceHits.get(entry.getKey());
if (hits != null) hits.increment();
}
}
if (!curStr.equals(beforeRewrite)) sheetState.rowsRewritten.increment();

if (sheetState.isSeparate && sheetState.separatorValue != Integer.MIN_VALUE) {
curStr = curStr.replaceAll(", ", ", " + sheetState.separatorValue + ", ");
}

try {
short[] parsed = IntStreamEx.of(
Arrays.stream(curStr.replaceAll("[{}\\[\\]]", "").split(", "))
.map(String::trim).filter(s -> !s.isEmpty())
.mapToInt(Integer::parseInt).toArray()
).toShortArray();


if (parsed.length == 0) return;

synchronized (fwKeyShort) { fwKeyShort.add(parsed); }








// [Iter2] FW_Group writes to fw2_<k> with NULL parent (was \\N literal
// in the old StringBuilder; store renders the null parent itself).
store.appendFw2Row(key, fwId2.incrementAndGet(), null, parsed);
} catch (NumberFormatException e) {
sheetState.rowsDropped.increment();
switch (config.replaceUnparseablePolicy) {
case FAIL:
final String failure =
"FW_ReplaceRE produced a combination that is no longer a list of short codes: \""
+ curStr + "\" (was \"" + beforeRewrite + "\"). The rewritten code-string must stay "
+ "integer-parseable — a textual replacement drops the row. "
+ "[core.replace.unparseablePolicy=fail]";
replacePolicyFailures.add(failure);
throw new IllegalStateException(failure, e);
case DROP:
break;   // intentional discard; the summary still counts it
case WARN:
default:
log.warn("FW_Group: failed to parse combo string: {}", curStr, e);
}
}
});
}

store.flushFw2(key);

reportReplaceOutcome(key, sheetState);

sheetState.replacerHM.clear();
sheetState.isGroup = false;

CustomInterceptor2.clearCurrentTable();
return true;
}





final int sepVal = (sheetState.isSeparate && sheetState.separatorValue != Integer.MIN_VALUE)
? sheetState.separatorValue : Integer.MIN_VALUE;

try {
for (long j = 1L; j <= maxId; j++) {
if (cancelled) return true;

// [Iter2] Replaces fwService.getFWfromPreloadedMap(j).
short[] combo = fwRowsByCombiId.get(j);
if (combo == null || combo.length == 0) continue;

fComboId.set(j);

final List<Short> inList = new ArrayList<>(combo.length);
for (short v : combo) inList.add(v);



List<Integer> mValues = new ArrayList<>();
if (mParam == -1) {
mValues.add(inList.size());
} else if (mParam == -2) {
for (int t = 1; t <= inList.size(); t++) mValues.add(t);
} else {
mValues.add(Math.max(1, mParam));
}

for (int curM : mValues) {
final boolean par = config.threading.parallelizeSubCombosIfPossible;




final List<Short> srcList2ForRow =
(spec.keyShort2 != null && allSourceDataSnapshot != null)
? allSourceDataSnapshot.get(spec.keyShort2)
: null;

final CombinatorialGenerator<Short> rowGen = buildGenerator(
spec.algoType, inList, curM,
false, srcList2ForRow, spec.isCartesFirst,
CombinatorialGenerator.SubsetMode.DEFAULT, new int[]{}, par);

final boolean useParallel =
rowGen.parallel
&& rowGen.rowCount.longValue() > config.threading.parallelThreshold;

if (useParallel) {
final int chunkCount = resolveParallelChunks();
final List<Stream<List<Short>>> chunks = rowGen.parallelStreams(chunkCount);
final List<CompletableFuture<Void>> futs = new ArrayList<>(chunks.size());
try (var exec = Executors.newVirtualThreadPerTaskExecutor()) {
for (Stream<List<Short>> chunk : chunks) {
final long parentId = fComboId.get();
futs.add(CompletableFuture.runAsync(
() -> consumeSubsequentPassChunk(
chunk, key, fwKeyShort, fwId2, parentId, sepVal),
exec));
}
CompletableFuture.allOf(futs.toArray(new CompletableFuture[0])).join();
}
} else {
consumeSubsequentPassChunk(
rowGen.stream(), key, fwKeyShort, fwId2, fComboId.get(), sepVal);
}
}
}
} finally {
CustomInterceptor2.clearCurrentTable();
}







return true;
}


private void consumeSubsequentPassChunk(
Stream<List<Short>> chunk,
Short key,
ArrayList<short[]> fwKeyShort,
AtomicLong fwId2,
long parentId,
int separatorValue) {

// [Iter2] Was: per-row sb.append + db.copyIn at threshold.  Now: per-row
// store.appendFw2Row.  Store throttles into PG batches internally (PG mode)
// or appends to in-memory list (memory mode).
chunk.forEach(w -> {
short[] combo;
if (separatorValue != Integer.MIN_VALUE) {
int n = w.size();
if (n == 0) return;
if (n > 1) {
combo = new short[n * 2 - 1];
int i = 0;
for (Short s : w) {
combo[i * 2] = s.shortValue();
if (i < n - 1) combo[i * 2 + 1] = (short) separatorValue;
i++;
}
} else {
combo = new short[]{ w.get(0).shortValue() };
}
} else {
combo = new short[w.size()];
int i = 0;
for (Short s : w) combo[i++] = s.shortValue();
}

synchronized (fwKeyShort) {
fwKeyShort.add(combo);
}

store.appendFw2Row(key, fwId2.incrementAndGet(), parentId, combo);
});

store.flushFw2(key);
}




private static final class GeneratorSpec<T> {


final CombinatorialGenerator<T> generator;


final String algoType;


final Short key;


final Short keyShort2;


final int rawM;


final boolean isCartesFirst;

GeneratorSpec(CombinatorialGenerator<T> generator, String algoType,
Short key, Short keyShort2, int rawM, boolean isCartesFirst) {
this.generator      = generator;
this.algoType       = algoType;
this.key            = key;
this.keyShort2      = keyShort2;
this.rawM           = rawM;
this.isCartesFirst  = isCartesFirst;
}
}




/**
 * Run-time `core.replace.*` accounting, once per grouped sheet after the stream.
 *
 * A pattern with zero hits is the failure mode that reads as success: the run is
 * green, the rows are all there, and the substitution the author intended simply
 * never happened. Nothing here changes an outcome unless the operator asks for it.
 */
private void reportReplaceOutcome(Short key, SheetState sheetState) {
if (sheetState.replacerHM.isEmpty()) return;
final String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);

if (config.replaceDiagnostics == AppConfig.ReplaceDiagnostics.SUMMARY) {
final StringBuilder perPattern = new StringBuilder();
for (var entry : sheetState.replaceHits.entrySet()) {
if (perPattern.length() > 0) perPattern.append(", ");
perPattern.append('"').append(entry.getKey()).append("\"=").append(entry.getValue().sum());
}
log.info("FW_ReplaceRE summary — sheet {} (key={}): rows seen={} rewritten={} dropped={}; "
+ "rows changed per pattern: {}",
sheetName, key, sheetState.rowsSeen.sum(), sheetState.rowsRewritten.sum(),
sheetState.rowsDropped.sum(), perPattern);
}

if (config.replaceUnmatchedPolicy == AppConfig.ReplaceUnmatchedPolicy.IGNORE) return;

final List<String> unmatched = new ArrayList<>();
for (var entry : sheetState.replaceHits.entrySet()) {
if (entry.getValue().sum() == 0L) unmatched.add(entry.getKey());
}
if (unmatched.isEmpty()) return;

final String message =
"FW_ReplaceRE on sheet " + sheetName + " (key=" + key + "): pattern(s) " + unmatched
+ " changed no row out of " + sheetState.rowsSeen.sum() + ". The rewrite runs against the "
+ "code-string of each produced combination (a list of Short value-codes), so a pattern "
+ "written against rendered value text never matches and passes through as a silent no-op.";

if (config.replaceUnmatchedPolicy == AppConfig.ReplaceUnmatchedPolicy.FAIL) {
final String failure = message + " [core.replace.unmatchedPolicy=fail]";
replacePolicyFailures.add(failure);
throw new IllegalStateException(failure);
}
log.warn(message);
}


private static final class SheetState {

boolean isSeparate = false;

Short separatorKey = null;

int separatorValue = Integer.MIN_VALUE;


boolean isGroup = false;

final Map<String, String> replacerHM = new LinkedHashMap<>();

// Rewrite accounting for core.replace.* policies. The grouped stream may run
// in parallel (core.threading.parallelizeSubCombosIfPossible), so every
// counter touched inside gStream.forEach is atomic.
final Map<String, java.util.concurrent.atomic.LongAdder> replaceHits = new LinkedHashMap<>();
final java.util.concurrent.atomic.LongAdder rowsSeen = new java.util.concurrent.atomic.LongAdder();
final java.util.concurrent.atomic.LongAdder rowsRewritten = new java.util.concurrent.atomic.LongAdder();
final java.util.concurrent.atomic.LongAdder rowsDropped = new java.util.concurrent.atomic.LongAdder();

void resetReplaceCounters() {
replaceHits.clear();
for (String pattern : replacerHM.keySet()) {
replaceHits.put(pattern, new java.util.concurrent.atomic.LongAdder());
}
rowsSeen.reset(); rowsRewritten.reset(); rowsDropped.reset();
}
}

/**
 * Authoring-time `core.replace.*` checks, run once per parsed FW_Group directive.
 *
 * Nothing here restricts what FW_ReplaceRE can express — every check is inert at
 * the shipped defaults. They exist because the two ways to get a rewrite wrong are
 * both silent, and an operator who wants them loud currently has no way to ask.
 */
private void applyReplaceAuthoringPolicies(Short key, SheetState sheetState) {
final String sheetName = workbook.shortStringSheetKey2SheetNameHM.get(key);
for (var entry : sheetState.replacerHM.entrySet()) {
final String pattern = entry.getKey();

if (config.replaceIdentityPolicy == AppConfig.ReplaceIdentityPolicy.WARN
&& pattern.equals(entry.getValue())) {
log.warn("FW_ReplaceRE on sheet {} (key={}): pattern and replacement are both \"{}\" — "
+ "this rewrite does nothing at run time, but it still changes the emitted "
+ "directive and therefore the FW_Seq graph fingerprint. Remove it, or set "
+ "core.replace.identityPolicy=allow to silence this.",
sheetName, key, pattern);
}

if (config.replacePatternPolicy == AppConfig.ReplacePatternPolicy.PERMISSIVE) continue;
if (canMatchCodeString(pattern)) continue;

final String message =
"FW_ReplaceRE on sheet " + sheetName + " (key=" + key + "): pattern \"" + pattern
+ "\" cannot match a Core code-string. The rewrite runs against the code-string of a "
+ "produced combination (e.g. \"[47, 48]\" — a list of Short value-codes), never against "
+ "rendered value text, so this pattern can only ever be a silent no-op. Rewrite it "
+ "against codes/structure, or move the substitution to the value itself. "
+ "See ZEN_OF_COMBINATORICS.md (FW_ReplaceRE rewrites the short key, not value text).";

if (config.replacePatternPolicy == AppConfig.ReplacePatternPolicy.STRICT) {
final String failure = message + " [core.replace.patternPolicy=strict]";
replacePolicyFailures.add(failure);
throw new IllegalStateException(failure);
}
log.warn(message);
}
}

/** Characters a Core code-string can contain: digits, separators, brackets, space.
 *  A pattern that requires anything outside this set can never match, so it is a
 *  no-op that {@code core.replace.patternPolicy} can surface before the run. */
private static final Pattern CODE_STRING_CHARS = Pattern.compile("[0-9,\\[\\]{}\\s]*");

/** True when {@code pattern} could conceivably match a code-string.
 *  Regex metacharacters are stripped first, so structural patterns such as
 *  {@code "^\\[|\\]$"} or {@code "\\d+"} stay acceptable; only literal text that
 *  cannot appear among value-codes (letters, {@code @}, quotes, …) is rejected. */
private static boolean canMatchCodeString(String pattern) {
String literals = pattern
.replaceAll("\\\\[dDwWsSbBAZzGQE]", "")   // classes/anchors that are not literals
.replaceAll("\\\\[pP]\\{\\w+}", "")        // unicode classes
.replaceAll("\\\\.", "")                    // any other escaped literal
.replaceAll("[\\[\\]{}()|.*+?^$\\-]", "");  // regex structure
return CODE_STRING_CHARS.matcher(literals).matches();
}




@SuppressWarnings("unchecked")
private <T> CombinatorialGenerator<T> buildGenerator(
String algoType, List<T> src, int m,
boolean allowDuplicates, List<T> src2, boolean isCartesFirst,
CombinatorialGenerator.SubsetMode subsetMode, int[] subsetParams,
boolean par) {

switch (algoType) {
case "FW_Combi":



if (m < 0 || m > src.size()) {
return CombinatorialGenerator.subsets(Collections.emptyList(),
CombinatorialGenerator.SubsetMode.DEFAULT, new int[]{}, par);
}
return CombinatorialGenerator.combinations(src, m, par);
case "FW_CombiR":
if (m < 0) {
return CombinatorialGenerator.subsets(Collections.emptyList(),
CombinatorialGenerator.SubsetMode.DEFAULT, new int[]{}, par);
}
return CombinatorialGenerator.combinationsWithRepetitions(src, m, par);
case "FW_Permut":
return CombinatorialGenerator.permutations(src, allowDuplicates, par);
case "FW_PermutR":
if (m < 0) {
return CombinatorialGenerator.subsets(Collections.emptyList(),
CombinatorialGenerator.SubsetMode.DEFAULT, new int[]{}, par);
}
return CombinatorialGenerator.permutationsWithRepetitions(src, m, par);
case "FW_Cartes":


List<T> safeA = isCartesFirst ? (src2 != null ? src2 : Collections.emptyList()) : src;
List<T> safeB = isCartesFirst ? src : (src2 != null ? src2 : Collections.emptyList());
return CombinatorialGenerator.cartesian(safeA, safeB, par);
case "FW_Subsets":
return CombinatorialGenerator.subsets(src, subsetMode, subsetParams, par);
default:
throw new IllegalArgumentException("Unknown algo type: " + algoType);
}
}




private static boolean isCombiDirective(String d) {
return d.startsWith("FW_Combi")
|| d.startsWith("FW_Permut")
|| d.startsWith("FW_Subsets")
|| d.startsWith("FW_Cartes");
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


private int resolveM(String directive, String algoType,
Map<Short, List<Short>> toCombinatoricsHMcopy,
Short key, int pass) {

if (directive.endsWith(algoType) || directive.endsWith(algoType + "()")) return 1;


if (directive.matches(algoType + "\\(\\d+\\)")) {
Matcher m = PARAM_PATTERN.matcher(directive);
if (m.find()) {
try {
return Integer.parseInt(m.group(1));
} catch (NumberFormatException ignored) {  }
}
}


if (directive.matches(algoType + "\\((?i)size\\)")) {


if (pass > 0) return -1;
return toCombinatoricsHMcopy.getOrDefault(key, Collections.emptyList()).size();
}
















if (directive.matches(algoType + "\\((?i)(all|full)\\)")) {
if (algoType.equals("FW_Combi") || algoType.equals("FW_CombiR")
|| algoType.equals("FW_PermutR")) {
return -2;
}

return 1;
}


if (algoType.equals("FW_Subsets") && directive.contains("_") && directive.contains("(")) {
String digits = directive.replaceAll("\\D*", "");
if (!digits.isEmpty()) {
try {
return Integer.parseInt(digits);
} catch (NumberFormatException ignored) {  }
}
}


return 1;
}


private Map<Short, List<Short>> buildCopy(Map<Short, List<Short>> src) {

final Map<Short, List<Short>> dataSource =
(allSourceDataSnapshot != null) ? allSourceDataSnapshot : src;

Stream<Map.Entry<Short, String>> filtered = workbook.shortStringSheetKey2SheetNameHM.entrySet().stream()
.filter(e -> dataSource.containsKey(e.getKey()));
return filtered.collect(Collectors.toMap(
Map.Entry::getKey,
e -> new ArrayList<Short>(dataSource.get(e.getKey())),
(a, b) -> a,
LinkedHashMap::new
));
}




private int resolveParallelChunks() {
int configured = config.threading.parallelChunks;
if (configured > 0) return configured;
return Math.max(8, Runtime.getRuntime().availableProcessors() * 2);
}
}
