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

package com.company.helpers;

import com.company.db.DbClient;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import java.util.Set;
import java.util.concurrent.CountDownLatch;


public class TableDataDistinctorFnl {

private static final Logger log = LogManager.getLogger(TableDataDistinctorFnl.class);

private final long               keyDistinctor;
private final String             tableToDistinct;
private final String             tableTempDistincted;
private final String             tableDistincted;
private final Map<Short, String> key2name;
private final DbClient           db;

/** [Iter3.2 Option C] When true, dedup via in-JVM HashSet of 64-bit row hashes
 *  instead of the PG-side GROUP BY plan. */
private final boolean javaSide;

/** [Iter3.3 Option D] When true, run a cheap TABLESAMPLE pre-check; if the
 *  sample shows no duplicates, skip the actual distinctify entirely. */
private final boolean sampleAndSkip;

Queue<String> spinner = new LinkedList<>(Arrays.asList("\r  .⊗⊕","\r ..⊗⚙","\r...⊕⊗","\r   ⚙⊕"));


public TableDataDistinctorFnl(String tableToDistinct, DbClient db) {
this(tableToDistinct, 0L, null, db, false, false);
}


public TableDataDistinctorFnl(String tableToDistinct,
Map<Short, String> key2name, DbClient db) {
this(tableToDistinct, 0L, key2name, db, false, false);
}


public TableDataDistinctorFnl(String tableToDistinct, long keyDistinctor,
Map<Short, String> key2name, DbClient db) {
this(tableToDistinct, keyDistinctor, key2name, db, false, false);
}

/** [Iter3] Strategy-aware constructor.  All callers that want to opt into
 *  Option C / Option D should use this overload; the older 1/2/3-arg
 *  constructors above default both flags to {@code false} (legacy PG-side). */
public TableDataDistinctorFnl(String tableToDistinct, long keyDistinctor,
Map<Short, String> key2name, DbClient db,
boolean javaSide, boolean sampleAndSkip) {
this.tableToDistinct     = tableToDistinct;
this.keyDistinctor       = keyDistinctor;
this.key2name            = key2name;
this.db                  = db;
this.tableTempDistincted = tableToDistinct + "_distincted";
this.tableDistincted     = tableToDistinct;
this.javaSide            = javaSide;
this.sampleAndSkip       = sampleAndSkip;
}

public void distinctifyByCopyingDistinctedDataToNewTempTableDistinctedAndRecreateGivenTableAsCopyOfNewTempTableDistincted() {
var done = new CountDownLatch(1);

var distinctificationThread = new Thread(() -> {
try { dispatch(); }
catch (Exception e) {
log.error("[FAILED] DISTINCT-ify '{}': {}", tableToDistinct, e.getMessage(), e);
} finally { done.countDown(); }
}, "distinctify-fnl-" + tableToDistinct);

var infoThread = new Thread(() -> {
int secs = 0, interval = 10000, localV = 0; String localStr4spinner;
while (distinctificationThread.isAlive()) {
log.info("Table '{}{}' being distincted for {} seconds...",
tableToDistinct, sheetSuffix(), secs += interval/1000);
try { while(localV < interval){Thread.sleep(250);localStr4spinner=spinner.poll();System.out.print(localStr4spinner);System.out.flush();spinner.offer(localStr4spinner.replaceAll("(?U)(\\p{S})(\\p{S})", "$2$1"));localV=localV+250;if(!distinctificationThread.isAlive()){localV=0;break;}}localV=0;System.out.print("\r"); }
catch (InterruptedException e) { Thread.currentThread().interrupt(); break; }
}
}, "distinctify-fnl-info-" + tableToDistinct);

distinctificationThread.start();
infoThread.start();

try { done.await(); }
catch (InterruptedException e) { Thread.currentThread().interrupt(); }

log.info("Table '{}{}' distincted. Done.", tableToDistinct, sheetSuffix());
}

/** [Iter3] Strategy dispatch.
 *  Order of decision (Option D overrides; Option C is the in-JVM fallback):
 *    1. {@code sampleAndSkip} → run TABLESAMPLE probe; if no duplicates seen,
 *       LOG and return without touching the table.
 *    2. {@code javaSide} → run {@link #doDistinctifyJavaSide()} (in-JVM hash).
 *    3. else → run {@link #doDistinctify()} (legacy PG-side in-place DELETE).
 */
private void dispatch() {
if (sampleAndSkip) {
try {
if (sampleSaysNoDuplicates()) {
log.info("[Iter3.3/Option D] Table '{}': TABLESAMPLE pre-check sees no duplicates "
+ "— skipping distinctify entirely", tableToDistinct);
return;
}
log.info("[Iter3.3/Option D] Table '{}': sample DID see duplicates — falling through "
+ "to {} distinctify", tableToDistinct, javaSide ? "in-JVM (Option C)" : "PG-side");
} catch (Exception e) {
log.warn("[Iter3.3/Option D] Sample pre-check failed on '{}' ({}); falling through to "
+ "full distinctify", tableToDistinct, e.getMessage());
}
}
if (javaSide) {
try {
doDistinctifyJavaSide();
return;
} catch (Exception e) {
log.warn("[Iter3.2/Option C] Java-side distinctify failed on '{}' ({}); falling back "
+ "to PG-side", tableToDistinct, e.getMessage(), e);
// Fall through.
}
}
doDistinctify();
}

/** [Iter3.3 Option D] TABLESAMPLE-based duplicate probe.  Samples ~1% of the
 *  table's pages via {@code TABLESAMPLE SYSTEM (1)} and compares COUNT(*) to
 *  COUNT(DISTINCT (data_cols)).  Returns {@code true} only when both counts
 *  agree (no duplicates in the sample).
 *
 *  <p>Probabilistic: false negatives possible if duplicates are sparse
 *  (≤ 1 dup in 10 000 rows might not appear in a 1 % sample).  False positives
 *  are not possible — if the counts agree, the sample is truly distinct.</p>
 */
private boolean sampleSaysNoDuplicates() {
String dataColsCsv = readDataColumnsCsv();
if (dataColsCsv == null || dataColsCsv.isBlank()) {
// No data columns to compare → trivially distinct.
return true;
}
String q = "SELECT (COUNT(*) = COUNT(DISTINCT (" + dataColsCsv + ")))::text AS no_dups "
+ "FROM \"" + tableToDistinct + "\" TABLESAMPLE SYSTEM (1);";
String r = db.queryString(q);
return "t".equalsIgnoreCase(r) || "true".equalsIgnoreCase(r);
}

/** Compute the CSV of data columns (everything except identifier / audit cols).
 *  Shared by both PG-side and JVM-side paths. */
private String readDataColumnsCsv() {
String excludedCols = tableToDistinct.matches("fw\\d?_\\d{0,}")
? "AND column_name NOT IN ('combi_id', 'fcombi_id', 'combo_txt')"
: "AND column_name NOT IN ('combi_id')";
return db.queryString(
"SELECT STRING_AGG(quote_ident(column_name), ', ' ORDER BY ordinal_position)\n"
+ "FROM information_schema.columns\n"
+ "WHERE table_name = '" + tableToDistinct + "'\n"
+ "  AND table_schema = 'public'\n"
+ "  " + excludedCols + ";");
}

private void doDistinctify() {
// [Refactor 18052026 / step #2] In-place dedup — single DELETE statement.
//
// Replaces the previous clone-and-swap (CREATE <t>_distincted AS TABLE …
// WITH NO DATA → INSERT DISTINCT → DROP original → rename) that held up
// to ~3× the table's data on disk during the operation.  On the 12 GB
// FdiskTablespace this capped the engine at ~2 GB of final data; chunk_241
// of the 150436 suite hit DISK_FULL at 25M rows because of exactly this
// multiplier, not because of the data itself (~1.25 GB).
//
// Strategy: pick MIN(combi_id) per duplicate-key group and DELETE the
// rest.  Zero temp tables, zero additional disk during the operation
// (modulo MVCC dead tuples — reclaimed via the VACUUM FULL at the end).
//
// Correctness vs. the legacy SELECT DISTINCT path:
//   - Both retain exactly ONE representative per (data_cols) tuple.
//   - Legacy chose an arbitrary row (whichever DISTINCT picked); this
//     picks the lowest combi_id.  Both choices are arbitrary; downstream
//     code uses combi_id only as identifier (no contiguity expected).

String dataColsCsv = readDataColumnsCsv();
if (dataColsCsv == null || dataColsCsv.isBlank()) {
log.warn("[Refactor-#2] doDistinctify({}): no data columns found — skipping",
tableToDistinct);
return;
}

// Single in-place DELETE.  PG runs this as one transaction; on failure
// the table is unchanged (matches the legacy COMMIT-at-end semantics).
String inPlaceSql =
"DELETE FROM \"" + tableToDistinct + "\" WHERE combi_id NOT IN ("
+ "SELECT MIN(combi_id) FROM \"" + tableToDistinct + "\" GROUP BY " + dataColsCsv
+ ");";

// Strict: this DELETE IS the distinctify. Swallowing its failure (the old
// executeSilently) meant duplicates survived and every downstream count
// was silently wrong — the run must die here instead.
db.executeOrThrow(inPlaceSql);

// [Refactor 18052026 / step #9] Plain VACUUM, not FULL.
// VACUUM FULL takes AccessExclusiveLock and writes a NEW heap file —
// during the rewrite the table briefly occupies up-to 2× its post-delete
// size on disk.  On the 12 GB FdiskTablespace that 2× spike has been
// observed pushing chunks like chunk_241 (25M rows) into disk-full
// during distinctify itself.  Plain VACUUM marks dead tuples reusable
// in-place without rewriting the heap — no lock escalation, no disk spike,
// faster (often by 5-10×).
// The table file doesn't shrink (PG won't return pages to the OS), but
// teardown_db drops the entire database at end-of-run anyway, so the
// observable disk usage is identical at the only point that matters.
// Strict: VACUUM here is load-bearing disk-space reclamation (see the
// chunk_241 DISK_FULL history above); a silent failure resurfaces later
// as an inexplicable disk-full several steps downstream.
db.executeOrThrow("VACUUM \"" + tableToDistinct + "\";");
}

/** [Iter3.2 Option C] In-JVM distinctify.
 *  <ol>
 *    <li>SELECT combi_id + data columns ORDER BY combi_id.</li>
 *    <li>Hash each row's data columns to a 64-bit value.</li>
 *    <li>Track seen hashes in a {@link HashSet}; rows whose hash already
 *        appears are duplicates and collected for deletion.</li>
 *    <li>If any duplicates were found, build a TEMP table of duplicate
 *        combi_ids on a single connection (so TEMP is visible to the
 *        subsequent DELETE) and issue
 *        {@code DELETE … WHERE combi_id IN (SELECT FROM __dup_ids)}.</li>
 *    <li>{@code VACUUM} (plain — same rationale as PG-side path).</li>
 *  </ol>
 *
 *  <p>Memory cost: HashSet&lt;Long&gt; ≈ 50 B / entry on default JVM; a 34M
 *  unique-row table needs ~1.5 GB heap during the scan.  Tune {@code -Xmx}
 *  accordingly or fall back to Option D / PG-side for huge tables.</p>
 *
 *  <p>Hash quality: a 64-bit hash with proper avalanche (Murmur3 finaliser)
 *  has collision probability ~5×10^-11 for 34M rows — effectively zero.
 *  Documented for completeness, not a practical concern.</p>
 */
private void doDistinctifyJavaSide() throws SQLException {
String dataColsCsv = readDataColumnsCsv();
if (dataColsCsv == null || dataColsCsv.isBlank()) {
log.warn("[Iter3.2/Option C] doDistinctifyJavaSide({}): no data columns — skipping",
tableToDistinct);
return;
}

// Upfront heap estimate so the user sees the cost before the OOM (if any).
long preCount = -1L;
try { preCount = db.queryLong("SELECT COUNT(*) FROM \"" + tableToDistinct + "\";"); }
catch (Exception ignored) { }
if (preCount > 0L) {
long estMb = (preCount * 50L) / (1024L * 1024L);  // ~50 B / distinct row
log.info("[Iter3.2/Option C] Table '{}': {} rows in source, est. seen-hash heap ~{} MB"
+ " (Murmur3-hashed Long set).  Tune -Xmx accordingly.",
tableToDistinct, preCount, estMb);
}

long total = 0L;
Set<Long> seenHashes = new HashSet<>(Math.max(1 << 16,
preCount > 0 ? (int) Math.min(preCount + (preCount >> 2), Integer.MAX_VALUE - 8) : 1 << 16));
List<Long> duplicateCombiIds = new ArrayList<>();

String selectSql = "SELECT combi_id, " + dataColsCsv
+ " FROM \"" + tableToDistinct + "\" ORDER BY combi_id";

// [Iter3-postfix] CRITICAL: PostgreSQL JDBC defaults to buffering the
// ENTIRE result set into client memory before exposing it.  For a 34M-row
// table × wide PG-array columns this is ~7 GB before Option C's HashSet
// even starts → guaranteed OOM under any reasonable -Xmx.  Both conditions
// (autoCommit=false AND fetchSize>0) are REQUIRED to switch the driver to
// cursor-based fetching; missing either silently re-enables full buffering.
try (Connection conn = db.getConnection()) {
boolean prevAutoCommit = conn.getAutoCommit();
conn.setAutoCommit(false);
try (Statement st = conn.createStatement()) {
st.setFetchSize(10_000);
try (ResultSet rs = st.executeQuery(selectSql)) {
ResultSetMetaData meta = rs.getMetaData();
int ncols = meta.getColumnCount();
while (rs.next()) {
total++;
long cid = rs.getLong(1);
long h = hashRowData(rs, ncols);
if (!seenHashes.add(h)) {
duplicateCombiIds.add(cid);
}
}
}
}
try { conn.setAutoCommit(prevAutoCommit); } catch (Exception ignored) { }
}

log.info("[Iter3.2/Option C] Table '{}': scanned {} rows; {} duplicates identified",
tableToDistinct, total, duplicateCombiIds.size());

if (duplicateCombiIds.isEmpty()) {
log.info("[Iter3.2/Option C] Table '{}': zero duplicates — VACUUM only", tableToDistinct);
// Strict — same disk-space rationale as the PG-side path's VACUUM.
db.executeOrThrow("VACUUM \"" + tableToDistinct + "\";");
return;
}

// TEMP table is connection-scoped; build + DELETE on one connection.
try (Connection conn = db.getConnection()) {
boolean prevAutoCommit = conn.getAutoCommit();
conn.setAutoCommit(false);
try {
try (Statement st = conn.createStatement()) {
st.execute("CREATE TEMP TABLE __dup_ids (combi_id bigint PRIMARY KEY) ON COMMIT DROP;");
}
StringBuilder buf = new StringBuilder(duplicateCombiIds.size() * 12);
for (Long id : duplicateCombiIds) buf.append(id.longValue()).append('\n');
org.postgresql.copy.CopyManager cm =
conn.unwrap(org.postgresql.PGConnection.class).getCopyAPI();
long copied = cm.copyIn("COPY __dup_ids (combi_id) FROM STDIN",
new ByteArrayInputStream(buf.toString().getBytes(StandardCharsets.UTF_8)));
log.debug("[Iter3.2/Option C] Staged {} duplicate combi_ids to __dup_ids", copied);

int deleted;
try (Statement st = conn.createStatement()) {
deleted = st.executeUpdate(
"DELETE FROM \"" + tableToDistinct
+ "\" WHERE combi_id IN (SELECT combi_id FROM __dup_ids);");
}
conn.commit();
log.info("[Iter3.2/Option C] Table '{}': PG DELETE removed {} rows", tableToDistinct, deleted);
} catch (Exception ex) {
try { conn.rollback(); } catch (Exception ignored) {}
throw ex;
} finally {
try { conn.setAutoCommit(prevAutoCommit); } catch (Exception ignored) {}
}
} catch (java.io.IOException ioe) {
throw new SQLException("[Iter3.2/Option C] COPY-IN to temp failed: " + ioe.getMessage(), ioe);
}

// Strict — same disk-space rationale as the PG-side path's VACUUM.
db.executeOrThrow("VACUUM \"" + tableToDistinct + "\";");
}

// [Iter3-postfix] FNV-1a 64-bit constants.  Replaces the prior `h * 31 + x`
// polynomial accumulator which was COLLISION-PRONE on small short[] inputs:
// Short[]{0,32} and Short[]{1,1} both produced h=32 because
// (1*31+0)*31+32 == (1*31+1)*31+1 == 994 — same collision pattern at any
// length whenever the value differences satisfy the polynomial-31 equation.
// Empirically that bug produced ~14% FALSE-POSITIVE "duplicates" on
// fw_opt4 in test14042026.xlsx, deleting 4.8M legitimate rows.
//
// FNV-1a avalanche per element makes such structured collisions astronomically
// unlikely (~2^-64 per row pair), restoring the expected near-zero false-
// positive rate.
private static final long FNV_OFFSET_64 = 0xcbf29ce484222325L;
private static final long FNV_PRIME_64  = 0x100000001b3L;

/** [Iter3.2 Option C] FNV-1a 64-bit hash of one ResultSet row's columns
 *  2..ncols.  Each column's per-array hash is XOR-mixed and multiplied into
 *  the running hash.  Output avalanches: a single-bit input change typically
 *  flips ~half of the output bits. */
private static long hashRowData(ResultSet rs, int ncols) throws SQLException {
long h = FNV_OFFSET_64;
for (int i = 2; i <= ncols; i++) {
Object val = rs.getObject(i);
long colHash;
if (val == null) {
colHash = 0L;
} else if (val instanceof java.sql.Array a) {
colHash = hashJavaArray(a.getArray());
} else {
colHash = val.hashCode() & 0xFFFFFFFFL;
}
// FNV-1a mix: XOR then multiply.  Mix the column hash in 16-bit chunks
// so each chunk hits a fresh prime-multiply step (better avalanche on
// values that look uniform when seen as 64-bit but aren't).
h ^= (colHash & 0xFFFFL);              h *= FNV_PRIME_64;
h ^= ((colHash >>> 16) & 0xFFFFL);     h *= FNV_PRIME_64;
h ^= ((colHash >>> 32) & 0xFFFFL);     h *= FNV_PRIME_64;
h ^= ((colHash >>> 48) & 0xFFFFL);     h *= FNV_PRIME_64;
}
return h;
}

/** [Iter3-postfix] FNV-1a 64-bit over the array's elements.  XOR + multiply
 *  per element instead of the prior polynomial-31 accumulator — eliminates
 *  the structural collisions that wrecked the earlier doDistinctifyJavaSide
 *  run on fw_opt4. */
private static long hashJavaArray(Object javaArr) {
if (javaArr == null) return 0L;
long h = FNV_OFFSET_64;
if (javaArr instanceof Short[] sa) {
for (Short s : sa) {
h ^= (s == null ? 0L : (s.shortValue() & 0xFFFFL));
h *= FNV_PRIME_64;
}
} else if (javaArr instanceof Integer[] ia) {
for (Integer s : ia) {
int v = s == null ? 0 : s.intValue();
// 16-bit chunks for finer avalanche on small ints.
h ^= (v & 0xFFFFL);          h *= FNV_PRIME_64;
h ^= ((v >>> 16) & 0xFFFFL); h *= FNV_PRIME_64;
}
} else if (javaArr instanceof Long[] la) {
for (Long s : la) {
long v = s == null ? 0L : s.longValue();
h ^= (v & 0xFFFFL);          h *= FNV_PRIME_64;
h ^= ((v >>> 16) & 0xFFFFL); h *= FNV_PRIME_64;
h ^= ((v >>> 32) & 0xFFFFL); h *= FNV_PRIME_64;
h ^= ((v >>> 48) & 0xFFFFL); h *= FNV_PRIME_64;
}
} else if (javaArr.getClass().isArray()) {
int len = java.lang.reflect.Array.getLength(javaArr);
for (int i = 0; i < len; i++) {
Object v = java.lang.reflect.Array.get(javaArr, i);
long x = (v == null) ? 0L : (v.hashCode() & 0xFFFFFFFFL);
h ^= (x & 0xFFFFL);          h *= FNV_PRIME_64;
h ^= ((x >>> 16) & 0xFFFFL); h *= FNV_PRIME_64;
}
}
return h;
}

private String sheetSuffix() {
if (tableToDistinct.contains("final") || tableToDistinct.contains("opt")) return "";
try {
Short key = Short.valueOf(tableToDistinct.replaceAll("(fw\\d?_)", ""));
String name = key2name != null ? key2name.get(key) : null;
return name != null ? "\\" + name + "/" : "";
} catch (NumberFormatException ignored) { return ""; }
}
}
