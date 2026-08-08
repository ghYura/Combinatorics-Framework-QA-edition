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

package com.company;

import static com.company.ReaderConfig.*;

import com.company.io.ReaderIoStreams;



import java.util.concurrent.TimeUnit;

import com.company.helpers.DBStreamer;
import com.company.helpers.StreamRowWriter;


import com.company.daoModelService.KeyValueService;
import com.company.daoModelService.SheetNameService;
import com.company.helpers.*;
import com.company.models.NumberToValue1;
import com.company.models.SheetName;
import net.lingala.zip4j.ZipFile;
import net.lingala.zip4j.exception.ZipException;
import net.lingala.zip4j.model.ZipParameters;
import net.lingala.zip4j.model.enums.CompressionMethod;
import one.util.streamex.StreamEx;

import java.io.*;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.logging.Level;
import java.util.stream.Collectors;
import java.util.stream.Stream;



import static com.company.excel.Numerator.fwOpts;
import static com.company.excel.Numerator.columnNamesFirstRowStaticHM;
import static com.company.excel.Numerator.sheetNameMapEndingByteArrGetStrKlength;
import static com.company.excel.Numerator.bArr2;

import static java.nio.file.StandardWatchEventKinds.ENTRY_MODIFY;

public class Main {






public static final int STREAM_PARALLELISM_FINAL =
Math.max(2, Math.min(8, Runtime.getRuntime().availableProcessors()));
public static final int CARTESIAN_DRIVER_PARALLELISM =
Math.max(2, Math.min(8, Runtime.getRuntime().availableProcessors()));










private static final byte[] BARR_NEWLINE = "\n".getBytes(java.nio.charset.StandardCharsets.UTF_8);
private static final byte[] BARR_EMPTY = new byte[0];

public static boolean STREAMING_DIRECT_WRITE_ENABLED = true;

public static volatile boolean alreadyExecuted = false;

public static OutputStream outStream;

public static volatile Scanner sc;

public static String actualAnswer;














public static boolean isFirstEntered = false;



public static final java.util.concurrent.atomic.AtomicInteger __dirRR = new java.util.concurrent.atomic.AtomicInteger(0); // RACE FIX (May29): thread-safe round-robin over output dirs (replaces fragile queue element()/remove()/add())
/**
* Tier-0 bug fix (0.1).  When {@code true}, BYPASS the StringButQuotesRefiner
* on cell values when populating the byte-array cache — preserves leading /
* trailing / multi-whitespace verbatim from {@code NumberToValue1}.
*
* Why this exists: the refiner's {@code method()} regex (line 220 of
* {@code StringButQuotesRefiner}) strips spaces at word-boundary positions
* to clean up Java-code cells.  That's correct for code, but DESTRUCTIVE for
* metric-payload cells where a leading-space is the K=V boundary (e.g. cell
* content " latency=10ms" becomes "latency=10ms", collapsing into preceding
* "cost=0.10latency=10ms").  Set this property to {@code true} for
* metric-rich scenarios; leave {@code false} (default) for legacy Java-code
* scenarios where the refiner's behaviour is desired.
*
* Property:  reader.cells.preserveWhitespace=true | false   (default false)
*/
public static WatchService watchService = null;
public static volatile boolean isStreamClosed1 = false;
public static volatile boolean isStreamClosed2 = false;





static void appendFullRecord(byte[] record, int off, int len) throws java.io.IOException {
if (len <= 0) return;
OutputStream s = outStream;
if (s instanceof ReaderIoStreams.DirectAppendOutputStream das) {
das.appendAtomic(record, off, len);
} else {
synchronized (Main.class) {
s.write(record, off, len);
s.flush();
}
}
}

// ── perf 2026-07-02: byte-level FW_REPLACE marker machinery ─────────────────────────────
// The marker is pure ASCII, so a byte-level scan/splice over UTF-8 payload bytes finds and
// replaces EXACTLY the same occurrences String.replace found after a full decode/encode
// round-trip (UTF-8 continuation bytes are >= 0x80 and can never alias ASCII) — but with
// zero decode/encode work and zero allocation when the marker is absent.
static final byte[] FW_MARKER_BYTES = "FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE".getBytes(java.nio.charset.StandardCharsets.UTF_8);

/** Left-to-right, non-overlapping marker positions in a[0..len); null when none (no alloc). */
static int[] fwMarkerPositions(byte[] a, int len) {
final byte[] m = FW_MARKER_BYTES;
final byte first = m[0];
int[] pos = null;
int n = 0;
int i = 0;
final int last = len - m.length;
outer:
while (i <= last) {
if (a[i] != first) { i++; continue; }
for (int j = 1; j < m.length; j++) {
if (a[i + j] != m[j]) { i++; continue outer; }
}
if (pos == null) pos = new int[4];
else if (n == pos.length) pos = java.util.Arrays.copyOf(pos, n * 2);
pos[n++] = i;
i += m.length;
}
if (pos == null) return null;
return (n == pos.length) ? pos : java.util.Arrays.copyOf(pos, n);
}

/** Replace the marker at the given positions with repl; returns a new exact-size array. */
static byte[] fwSpliceMarkers(byte[] a, int len, int[] pos, byte[] repl) {
final int mLen = FW_MARKER_BYTES.length;
final byte[] out = new byte[len + pos.length * (repl.length - mLen)];
int src = 0, dst = 0;
for (int p : pos) {
int chunk = p - src;
System.arraycopy(a, src, out, dst, chunk);
dst += chunk;
System.arraycopy(repl, 0, out, dst, repl.length);
dst += repl.length;
src = p + mLen;
}
System.arraycopy(a, src, out, dst, len - src);
return out;
}

/** Bytes-based twin of emitJoinedRecord: the caller supplies the record bytes and the
 *  per-record trim length (RACE FIX vs the legacy static Numerator ending-length — the
 *  static could hold another thread's value; this is the actual last-field separator
 *  length of THIS record). Output bytes are identical to the legacy String round-trip. */
static void emitJoinedRecordBytes(byte[] payload, int fullLen, int truncateBy, String currentTag) {
try {
int dataLen = Math.max(0, fullLen - truncateBy);
byte[] data = payload;
int dLen = dataLen;
if (fw_replace_me_with_current_combo_sequence_mode) {
int[] pos = fwMarkerPositions(payload, dataLen);
if (pos != null) {
data = fwSpliceMarkers(payload, dataLen, pos, currentTag.getBytes(java.nio.charset.StandardCharsets.UTF_8));
dLen = data.length;
}
}
byte[] tail = cfg().filesMode() ? BARR_EMPTY : BARR_NEWLINE;
if (tail.length == 0) {
appendFullRecord(data, 0, dLen);
} else {
byte[] full = new byte[dLen + tail.length];
System.arraycopy(data, 0, full, 0, dLen);
System.arraycopy(tail, 0, full, dLen, tail.length);
appendFullRecord(full, 0, full.length);
}
} catch (java.io.IOException e) {
e.printStackTrace();
}
}

// package-private (was private) so the extracted ComboGenerationPipeline can call it. 2026-05-30
static void emitJoinedRecord(org.apache.commons.io.output.UnsynchronizedByteArrayOutputStream src, String currentTag) {
try {
byte[] payload = src.toByteArray();
int truncateBy = (FW_B_ARR.length > 0) ? FW_B_ARR_LENGTH : sheetNameMapEndingByteArrGetStrKlength;
int dataLen = Math.max(0, payload.length - truncateBy);
byte[] data;
int dLen;
if (fw_replace_me_with_current_combo_sequence_mode) {
String s = new String(payload, 0, dataLen, java.nio.charset.StandardCharsets.UTF_8)
.replace("FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE", currentTag);
data = s.getBytes(java.nio.charset.StandardCharsets.UTF_8);
dLen = data.length;
} else {
data = payload;
dLen = dataLen;
}
byte[] tail = cfg().filesMode() ? BARR_EMPTY : BARR_NEWLINE;
if (tail.length == 0) {
appendFullRecord(data, 0, dLen);
} else {
byte[] full = new byte[dLen + tail.length];
System.arraycopy(data, 0, full, 0, dLen);
System.arraycopy(tail, 0, full, dLen, tail.length);
appendFullRecord(full, 0, full.length);
}
} catch (java.io.IOException e) {
e.printStackTrace();
}
}


private static void parallelMethodLineTout(long tout) {
Stream.generate(() -> " ").limit(tout - 1).forEach(System.out::print);
System.out.print("(timeout)\n");
AtomicInteger secondTout = new AtomicInteger(0);
new Thread(() -> {
while (secondTout.get() < tout) {
try {
Thread.sleep(1000);
System.err.print("¯");
secondTout.set(secondTout.incrementAndGet());
} catch (InterruptedException e) {
e.printStackTrace();
}
}
}).start();
}

private static String getChoiceWithTimeout2(String prefix, int range) {
Callable<String> k = () -> new Scanner(System.in).nextLine();
long start = System.currentTimeMillis();
String choice = null;
boolean valid = false;
ExecutorService l = Executors.newFixedThreadPool(1);
Future<String> g = null;
System.out.println("Enter your choice in " + range + " seconds :\n" + prefix);
g = l.submit(k);
done:
while (System.currentTimeMillis() - start < range * 1000) {
do {
if (System.currentTimeMillis() - start > range * 1000 && ((choice != null) ? !choice.matches(".{1,}") : true)) {
g.cancel(true);
isFirstEntered = false;
return (choice == null) ? "" : choice;
}
valid = false;
if (g.isDone()) {
try {
choice = g.get();
if (choice == null || choice.equals("") || choice.equals("\n") || choice.equals("\r")) {
choice = "";
valid = true;
break done;
} else if (choice != null) {
valid = true;
isFirstEntered = true;
break done;
} else {
throw new IllegalArgumentException();
}
} catch (InterruptedException | ExecutionException | IllegalArgumentException e) {
System.out.println("Wrong choice.");
g = l.submit(k);
valid = false;
}
}
} while (!valid);
}

g.cancel(true);
return choice;
}

public static void copyTableDataBetweenDBs(String table, Connection from, Connection to) throws SQLException {
try (PreparedStatement s1 = from.prepareStatement("select * from " + table);
ResultSet rs = s1.executeQuery()) {
ResultSetMetaData meta = rs.getMetaData();
List<String> columns = new ArrayList<>();
for (int i = 1; i <= meta.getColumnCount(); i++)
columns.add(meta.getColumnName(i));
try (PreparedStatement s2 = to.prepareStatement(
"INSERT INTO " + table + " ("
+ columns.stream().collect(Collectors.joining(", "))
+ ") VALUES ("
+ columns.stream().map(c -> "?").collect(Collectors.joining(", "))
+ ")"
)) {
while (rs.next()) {
for (int i = 1; i <= meta.getColumnCount(); i++)
s2.setObject(i, rs.getObject(i));
s2.addBatch();
}
s2.executeBatch();
}
}
}


public static long isStreamClosed(FileOutputStream out) {
try {
return out.getChannel().position();
} catch (java.nio.channels.ClosedChannelException cce) {
return 0;
} catch (IOException e) {
}
return 0;
}

public static void main(String[] args) throws SQLException {

System.setProperty("com.mchange.v2.log.MLog", "com.mchange.v2.log.FallbackMLog");
System.setProperty("com.mchange.v2.log.FallbackMLog.DEFAULT_CUTOFF_LEVEL", "OFF");
java.util.logging.Logger.getLogger("org.hibernate").setLevel(Level.OFF);
java.util.logging.Logger.getLogger("org.jboss").setLevel(Level.OFF);
loadProperties();
outStream = ReaderIoStreams.ProducerConsumerIO.getOrStart(cfg().pathFwOutFile(), true);
JarMirrorWatcher.startAsync();

ResultsDbProvisioner.create(cfg().dbHostResults(), cfg().dbPortResults(), cfg().dbUserResults(), cfg().dbPasswordResults());

Queue<String> outZipDirsConcurLQ = new ConcurrentLinkedQueue<>(cfg().pathFwOutZipDirList());
SheetName sheetName = new SheetName();
SheetNameService sheetNameService = new SheetNameService();
Map<String, byte[]> sheetNameMapByteArr = new LinkedHashMap<>();
Map<String, byte[]> sheetNameMapEndingByteArr = new LinkedHashMap<>();
sheetNameService.getListOfSheetNames().forEach(e -> sheetNameMapByteArr.put(e.getSheet(), e.getName().getBytes()));
sheetNameService.getListOfSheetNames().forEach(e -> sheetNameMapEndingByteArr.put(e.getSheet(), e.getEnding().getBytes()));

QueryToDB q2drunFirstOnce_args = new QueryToDB();
q2drunFirstOnce_args.init();
StringBuilder sbArgs = new StringBuilder();
try {
QueryToDB q2drunFirstOnceFW_PATH_FILES_TO = new QueryToDB();
q2drunFirstOnceFW_PATH_FILES_TO.init();
String updated = q2drunFirstOnceFW_PATH_FILES_TO.queryForStr("SELECT code_once FROM public.runmefirstonce;").replaceAll("String\\s{0,}(\\n\\s{0,}){0,}FW_PATH_FILES_TO\\s{0,}[^;]{0,}(\\n\\s{0,}){0,}[^;]{0,}(\\n\\s{0,}){0,}[^;]{0,};", "String FW_PATH_FILES_TO = \"" + cfg().fwPathFilesTo() + "\";");
q2drunFirstOnceFW_PATH_FILES_TO.disconnect();
QueryToDB q2drunFirstOnceFW_PATH_FILES_TOupdated = new QueryToDB();
q2drunFirstOnceFW_PATH_FILES_TOupdated.init();
q2drunFirstOnceFW_PATH_FILES_TOupdated.query("UPDATE public.runmefirstonce SET code_once='" + updated + "'; commit;");
q2drunFirstOnceFW_PATH_FILES_TOupdated.disconnect();

HandshakeWriter.writeArgsRunOnceShift(q2drunFirstOnce_args);

q2drunFirstOnce_args.disconnect();
} catch (IOException e) {
System.out.println("An error occurred.");
e.printStackTrace();
}

byte[] bArr = (cfg().filesMode()) ? "".getBytes() : "\n".getBytes();

















ConcurrentHashMap<Short, ByteArrayOutputStream> concurrentHashMapKVbyteArrStream = new ConcurrentHashMap<>();

boolean refineInDB = cfg().refineCodeInDb();
StringButQuotesRefiner strRefinery2 = new StringButQuotesRefiner();

if ((cfg().newLine2AddBeforeThatStartsWithButNotInquotesList() != null) && !cfg().newLine2AddBeforeThatStartsWithButNotInquotesList().isEmpty())
strRefinery2.setNewLine2AddBeforeThatStartsWithButNotInQuotesList(cfg().newLine2AddBeforeThatStartsWithButNotInquotesList());
if ((cfg().newLine2AddAfterThatEndsWithButNotInquotesList() != null) && !cfg().newLine2AddAfterThatEndsWithButNotInquotesList().isEmpty())
strRefinery2.setNewLine2AddAfterThatEndsWithButNotInQuotesList(cfg().newLine2AddAfterThatEndsWithButNotInquotesList());
if ((cfg().oneSpace2AddBeforeCharsButNotInQuotesList() != null) && !cfg().oneSpace2AddBeforeCharsButNotInQuotesList().isEmpty())
strRefinery2.setOneSpace2AddBeforeCharsButNotInQuotesList(cfg().oneSpace2AddBeforeCharsButNotInQuotesList());
if ((cfg().oneSpace2AddAfterCharsButNotInQuotesList() != null) && !cfg().oneSpace2AddAfterCharsButNotInQuotesList().isEmpty())
strRefinery2.setOneSpace2AddAfterCharsButNotInQuotesList(cfg().oneSpace2AddAfterCharsButNotInQuotesList());

KeyValueService kvService = new KeyValueService();
List<NumberToValue1> kvList = kvService.getListOfKVs();
final int sizeKvList = kvList.size();
final byte[][] dummyBArr = {null};
for (NumberToValue1 numberToValue1 : kvList) {
if (numberToValue1.getValue().contains("FW_PATH_FILES_TO")) {
String refinedStrFromDB = numberToValue1.getValue().replaceAll("String\\s{0,}(\\n\\s{0,}){0,}FW_PATH_FILES_TO\\s{0,}[^;]{0,}(\\n\\s{0,}){0,}[^;]{0,}(\\n\\s{0,}){0,}[^;]{0,};", "String FW_PATH_FILES_TO = \"" + cfg().fwPathFilesTo() + "\";");
numberToValue1.setValue(refinedStrFromDB);
numberToValue1.setRefined(true);
kvService.updateKV(numberToValue1);
}
}
// ─── Tier-0 bug fix 0.1: preserveWhitespace ─────────────────────────────
// When set, BYPASS the StringButQuotesRefiner entirely.  Cell values from
// NumberToValue1 are cached verbatim — leading/trailing/multi whitespace
// preserved.  Required for metric-rich XLSX scenarios where a leading
// space is the K=V boundary.  See cfg().preserveWhitespace() javadoc.
if (cfg().preserveWhitespace()) {
kvList.forEach(e -> {
byte[] valBytes = (e.getValue() + "").getBytes(StandardCharsets.UTF_8);
ByteArrayOutputStream baos = new ByteArrayOutputStream(valBytes.length);
try {
baos.write(valBytes);
baos.close();
concurrentHashMapKVbyteArrStream.put(e.getKey(), baos);
} catch (IOException e1) { e1.printStackTrace(); }
});
} else if (refineInDB) {
for (NumberToValue1 numberToValue1 : kvList) {
if (numberToValue1.isRefined() != null) {
if (!numberToValue1.isRefined()) {
String refinedStrFromDB = strRefinery2.shrinkManySpacedStringExceptAnyQuoted(strRefinery2.removeNewLines(strRefinery2.removeCommentsFromMultipleLinedString(numberToValue1.getValue())));
numberToValue1.setValue(refinedStrFromDB);
numberToValue1.setRefined(true);
kvService.updateKV(numberToValue1);
}
}
}





kvList.forEach(e -> {
byte[] valBytes = (e.getValue() + "").getBytes(StandardCharsets.UTF_8);
ByteArrayOutputStream baos = new ByteArrayOutputStream(valBytes.length);
try {
baos.write(valBytes);
baos.close();
concurrentHashMapKVbyteArrStream.put(e.getKey(), baos);
} catch (IOException e1) {
e1.printStackTrace();
}
});
} else {



kvList.forEach(e -> {
if (e.isRefined() == null || !e.isRefined()) {
String refinedStr = strRefinery2.shrinkManySpacedStringExceptAnyQuoted(
strRefinery2.removeNewLines(
strRefinery2.removeCommentsFromMultipleLinedString(e.getValue())
)
);
e.setValue(refinedStr);
e.setRefined(true);
}
});



kvList.forEach(e -> {
byte[] valBytes = (e.getValue() + "").getBytes(StandardCharsets.UTF_8);
ByteArrayOutputStream baos = new ByteArrayOutputStream(valBytes.length);
try {
baos.write(valBytes);
baos.close();
concurrentHashMapKVbyteArrStream.put(e.getKey(), baos);
} catch (IOException e1) {
e1.printStackTrace();
}
});
}
kvList.clear();
kvList = null;
System.out.println();

String tbl = "fw_final";













List list4reader;
LinkedHashMap<String, Object> rowDbFieldDbCellHM, rowDbFieldDbCellHMbase = null;
LinkedHashMap<String, Object> rowDbFieldDbCellHMbaseKeysRefined = null;

Map<Long, LinkedHashMap<Integer, short[]>> map4reader;
Map<Long, LinkedHashMap<Integer, short[]>> map4readerBase;
final Map<Long, LinkedHashMap<Integer, short[]>>[] curMap4readerFinal = new Map[]{new LinkedHashMap<>()};
final Map<Long, LinkedHashMap<Integer, short[]>>[] curMap4readerOpt = new Map[]{new LinkedHashMap<>()};
List<String> fwFinals = null;
List<Long> fwFinalsMaxCombiIds = null, fwOptsMaxCombiIds = null;
QueryToDB q2d1 = new QueryToDB();
QueryToDB2 q2d = new QueryToDB2();
DataBaseManager2 q2dbMgr = new DataBaseManager2(cfg().dbHost(), cfg().dbPort(), cfg().dbName());
QueryToDB2 q2d4reader = new QueryToDB2();
QueryToDB2 q2d4reader2 = new QueryToDB2();

q2d1.init();
q2d.init();
q2d4reader.init();
q2d4reader2.init();


List<String> fwFinalCandidates = q2d.queryForColumnValues(
"""
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
   AND table_name ~ 'fw_fina.*'
   AND table_name NOT IN ('fw_final_base','fw_final_base_copy')
 ORDER BY substring(table_name, '^[^0-9]+'),
          (substring(table_name, '[0-9].*$'))::bigint NULLS FIRST;""",
"table_name").stream().map(Object::toString).collect(Collectors.toList());



fwFinals = new ArrayList<>(fwFinalCandidates.size());
fwFinalsMaxCombiIds = new ArrayList<>(fwFinalCandidates.size());
for (String t : fwFinalCandidates) {
long mx;
try {
mx = TableSchemaInspector.effectiveMaxId(t);
} catch (SQLException __e) {
__e.printStackTrace();
continue;
}
if (mx <= 0L) continue;
fwFinals.add(t);
fwFinalsMaxCombiIds.add(mx);
String mode = TableSchemaInspector.useRealCombiId(t) ? "real combi_id" : "virtual combi_id (row_number over ctid)";
System.out.println("  [" + mode + "]  public." + t + "  max_id=" + mx);
}

boolean isOpt = false;
if (cfg().overrideIsOpt() != null) isOpt = cfg().overrideIsOpt();
ResultSet rs = q2d.queryForWholeResSet("""
SELECT EXISTS (
   SELECT FROM information_schema.tables\s
   WHERE  table_schema = 'public'
   AND    table_name   ~ 'fw_opt(\\d){0,}'
   );""");
while (rs.next()) {
isOpt = rs.getBoolean(1);
}
if (cfg().overrideIsOpt() != null) isOpt = cfg().overrideIsOpt();

if (isOpt) {
List<String> fwOptCandidates = q2d.queryForColumnValues(
"SELECT table_name FROM information_schema.tables\n" +
" WHERE table_schema = 'public' AND table_type = 'BASE TABLE'\n" +
"   AND table_name ~ 'fw_opt.*'\n" +
((cfg().overrideOptionalList() != null && !cfg().overrideOptionalList().isEmpty())
? "   AND table_name IN (" + cfg().overrideOptionalList().stream().map(i -> "'fw_opt" + i.toString() + "'").collect(Collectors.joining(", ")) + ")\n"
: "") +
" ORDER BY substring(table_name, '^[^0-9]+'),\n" +
"          (substring(table_name, '[0-9].*$'))::bigint NULLS FIRST;",
"table_name").stream().map(Object::toString).collect(Collectors.toList());

fwOpts = new ArrayList<>(fwOptCandidates.size());
fwOptsMaxCombiIds = new ArrayList<>(fwOptCandidates.size());
for (String t : fwOptCandidates) {
long mx;
try {
mx = TableSchemaInspector.effectiveMaxId(t);
} catch (SQLException __e) {
__e.printStackTrace();
continue;
}
if (mx <= 0L) continue;
fwOpts.add(t);
fwOptsMaxCombiIds.add(mx);
String mode = TableSchemaInspector.useRealCombiId(t) ? "real combi_id" : "virtual combi_id (row_number over ctid)";
System.out.println("  [" + mode + "]  public." + t + "  max_id=" + mx);
}
}

BigInteger finalSum = BigInteger.valueOf(fwFinalsMaxCombiIds.stream().mapToLong(Long::longValue).sum());
BigInteger control;
if (isOpt) {
BigInteger optSum = BigInteger.valueOf(fwOptsMaxCombiIds.stream().mapToLong(Long::longValue).sum());
BigInteger cartesianTotal = finalSum.multiply(optSum);
boolean bothStages = (cfg().isProcessBothFinalAndOpt() != null && cfg().isProcessBothFinalAndOpt());
control = bothStages ? finalSum.add(cartesianTotal) : cartesianTotal;
} else {
control = finalSum;
}









q2d1.init();
map4readerBase = q2d1.resultAsMapMap(TableSchemaInspector.fullOrderedQuery("fw_final_base_copy"), 1);
rowDbFieldDbCellHMbase = (LinkedHashMap<String, Object>) columnNamesFirstRowStaticHM.clone();
rowDbFieldDbCellHMbaseKeysRefined = new LinkedHashMap<>();
for (String k : rowDbFieldDbCellHMbase.keySet()) {
rowDbFieldDbCellHMbaseKeysRefined.put(k.replaceFirst("combos(\\d){1,}_", ""), rowDbFieldDbCellHMbase.get(k));
}

rowDbFieldDbCellHMbaseKeysRefined.keySet().stream().skip(2).forEach(e -> {
if (!sheetNameMapByteArr.keySet().contains(e)) {
System.out.print("\nWARNING!!!\n Table 'names' in DB does NOT contain sheet name mapping for key \n'" + e + "'\nWill be used empty \"\" string for its start and end\nor enter new value for beginning(1) and ending(2):\n");
String entered1 = getChoiceWithTimeout2("(1):", 10);
sheetNameMapByteArr.put(e, entered1.getBytes());
System.out.println("\nYou've entered:" + entered1 + "\n");

String entered2 = (isFirstEntered) ? getChoiceWithTimeout2("(2):", 10) : "";
sheetNameMapEndingByteArr.put(e, entered2.getBytes());
System.out.println("\nYou've entered:" + entered2 + "\n");
try {
System.out.print("Sleeping for " + 10 + " seconds...");
Thread.sleep(10000);
System.out.println("Done;");
} catch (InterruptedException e1) {
e1.printStackTrace();
}
System.out.println("\n");
}
});

List arrayListKeysRefined = new ArrayList(rowDbFieldDbCellHMbaseKeysRefined.keySet());

List arrayList = new ArrayList(rowDbFieldDbCellHMbase.keySet());

List keysOfMap = new ArrayList(rowDbFieldDbCellHMbase.keySet());
for (int i = 0; i < keysOfMap.size(); i++) {
Object _ = keysOfMap.get(i);
}
int indexOfMap = 0;
for (Object keyOfMap : rowDbFieldDbCellHMbase.keySet()) {
Object _ = rowDbFieldDbCellHMbase.get(keyOfMap);
++indexOfMap;
}
rowDbFieldDbCellHMbase.forEach((key, value) -> {
if (value == null || value instanceof Long) System.out.print("\t" + key + ":" + value);
else System.out.print("\t" + key + ":" + Arrays.toString((short[]) value));
});
System.out.println("\n=====");

long desiredCurrentChunkFinal = (cfg().desiredCurrentChunkFinal() != null) ? cfg().desiredCurrentChunkFinal() : 1000L;

long desiredCurrentChunkOpt = (cfg().desiredCurrentChunkOpt() != null) ? cfg().desiredCurrentChunkOpt() : 1000L;
final long[] combiIdLowLimitFinal = {0L};
final long[] combiIdLowLimitOpt = {0L};
final long[] combiIdHighLimitFinal = {Long.MAX_VALUE};
final long[] combiIdHighLimitOpt = {Long.MAX_VALUE};
Map<String, List<Map.Entry<Long, Long>>> table2combiIdChunksEntryFinals = new LinkedHashMap();
Map<String, List<Map.Entry<Long, Long>>> table2combiIdChunksEntryOpts = new LinkedHashMap();

table2combiIdChunksEntryFinals = Chunker.chunk(fwFinalsMaxCombiIds, fwFinals, desiredCurrentChunkFinal);

if (isOpt)
table2combiIdChunksEntryOpts = Chunker.chunk(fwOptsMaxCombiIds, fwOpts, desiredCurrentChunkOpt);




int numOfColumnsIn_fw_final_base_copy_Total;
try {
numOfColumnsIn_fw_final_base_copy_Total = TableSchemaInspector.totalColumnCount("fw_final_base_copy");
} catch (SQLException __sqle) {
__sqle.printStackTrace();
numOfColumnsIn_fw_final_base_copy_Total = q2d.queryForNumber("select count(COLUMN_NAME)\n" +
"from information_schema.columns\n" +
"where table_schema = 'public'\n" +
"and table_name = 'fw_final_base_copy'\n" +
"");
}

// ── [extracted 2026-05-30 → ComboGenerationPipeline] generator/stream loop + executor shutdown + cleanup ──
ComboGenerationPipeline __pipe = new ComboGenerationPipeline();
__pipe.outZipDirsConcurLQ = outZipDirsConcurLQ;
__pipe.sheetNameMapByteArr = sheetNameMapByteArr;
__pipe.sheetNameMapEndingByteArr = sheetNameMapEndingByteArr;
__pipe.concurrentHashMapKVbyteArrStream = concurrentHashMapKVbyteArrStream;
__pipe.bArr = bArr;
__pipe.rowDbFieldDbCellHMbaseKeysRefined = rowDbFieldDbCellHMbaseKeysRefined;
__pipe.curMap4readerFinal = curMap4readerFinal;
__pipe.fwFinals = fwFinals;
__pipe.fwFinalsMaxCombiIds = fwFinalsMaxCombiIds;
__pipe.fwOptsMaxCombiIds = fwOptsMaxCombiIds;
__pipe.isOpt = isOpt;
__pipe.control = control;
__pipe.arrayListKeysRefined = arrayListKeysRefined;
__pipe.desiredCurrentChunkFinal = desiredCurrentChunkFinal;
__pipe.desiredCurrentChunkOpt = desiredCurrentChunkOpt;
__pipe.combiIdLowLimitFinal = combiIdLowLimitFinal;
__pipe.combiIdHighLimitFinal = combiIdHighLimitFinal;
__pipe.table2combiIdChunksEntryFinals = table2combiIdChunksEntryFinals;
__pipe.table2combiIdChunksEntryOpts = table2combiIdChunksEntryOpts;
__pipe.numOfColumnsIn_fw_final_base_copy_Total = numOfColumnsIn_fw_final_base_copy_Total;
__pipe.q2d = q2d;
__pipe.q2d1 = q2d1;
__pipe.q2d4reader = q2d4reader;
__pipe.q2d4reader2 = q2d4reader2;
__pipe.q2dbMgr = q2dbMgr;
__pipe.run();

// STEP 17: dual-write Handoff v2 manifest alongside the legacy handshake
// (HandshakeWriter, written earlier in this run). Candidates are on disk and
// counted from the actual emission now, not a config guess. Feature-flagged —
// dual-write defaults on; set reader.handoff.dualWrite=false for legacy-only rollback.
// When the flag is on, manifest.json is a REQUIRED artifact of a successful run:
// a write failure must fail the run, not be swallowed — a Reader run that reports
// success without the manifest a dual-write consumer expects is a worse failure
// mode than a loud crash (see plan acceptance criterion: "Partial manifest не наблюдается").
if (cfg().handoffDualWrite()) {
try {
HandoffManifestWriter.writeManifestV2();
} catch (IOException __handoffIoEx) {
throw new java.io.UncheckedIOException("[STEP 17] Handoff v2 manifest write failed — failing the run (legacy-only rollback: reader.handoff.dualWrite=false)", __handoffIoEx);
}
}
}







class innerCls extends Observable {

}
}
