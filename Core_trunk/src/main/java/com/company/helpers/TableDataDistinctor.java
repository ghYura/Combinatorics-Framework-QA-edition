package com.company.helpers;

import com.company.db.DbClient;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.util.Map;
import java.util.concurrent.CountDownLatch;


public class TableDataDistinctor {

private static final Logger log = LogManager.getLogger(TableDataDistinctor.class);

private final long               keyDistinctor;
private final String             tableToDistinct;
private final String             tableTempDistincted;
private final String             tableDistincted;
private final Map<Short, String> key2name;
private final DbClient           db;

public TableDataDistinctor(String tableToDistinct,
Map<Short, String> key2name, DbClient db) {
this(tableToDistinct, 0L, key2name, db);
}

public TableDataDistinctor(String tableToDistinct, long keyDistinctor,
Map<Short, String> key2name, DbClient db) {
this.tableToDistinct    = tableToDistinct;
this.keyDistinctor      = keyDistinctor;
this.key2name           = key2name;
this.db                 = db;
this.tableTempDistincted = tableToDistinct + "_distincted";
this.tableDistincted     = tableToDistinct;
}

public void distinctifyByCopyingDistinctedDataToNewTempTableDistinctedAndRecreateGivenTableAsCopyOfNewTempTableDistincted() {
var done = new CountDownLatch(1);

var distinctificationThread = new Thread(() -> {
try { doDistinctify(); }
catch (Exception e) {
log.error("[FAILED] DISTINCT-ify '{}': {}", tableToDistinct, e.getMessage(), e);
} finally { done.countDown(); }
}, "distinctify-" + tableToDistinct);

var infoThread = new Thread(() -> {
int secs = 0;
while (distinctificationThread.isAlive()) {
log.info("Table '{}{}' being distincted for {} seconds...",
tableToDistinct, sheetSuffix(), secs += 2);
try { Thread.sleep(2_000); }
catch (InterruptedException e) { Thread.currentThread().interrupt(); break; }
}
}, "distinctify-info-" + tableToDistinct);

distinctificationThread.start();
infoThread.start();

try { done.await(); }
catch (InterruptedException e) { Thread.currentThread().interrupt(); }

log.info("Table '{}{}' distincted. Done.", tableToDistinct, sheetSuffix());
}

private void doDistinctify() {



String tblspc = db.queryString(
"SELECT tablespace FROM pg_tables "
+ "WHERE tablename = '" + tableToDistinct + "' AND schemaname = 'public';");

// Strict, and deliberately NOT tolerate-already-exists: a leftover
// _distincted table from a crashed earlier attempt still holds that
// attempt's rows, and quietly INSERTing into it would poison the swap
// below. 42P07 here is corruption waiting to happen, not benignity.
db.executeOrThrow(
"CREATE TABLE \"" + tableTempDistincted + "\"\n"
+ (tblspc != null ? "TABLESPACE \"" + tblspc + "\"\n" : "")
+ " AS TABLE \"" + tableToDistinct + "\" WITH NO DATA;");

// [Iter4 Step 8 / sheet-E fix] No sequence-reassign on combi_id any more.
// The new INSERT below explicitly provides MIN(combi_id) per dup-group, which
// preserves first-occurrence cid (matches JavaIntermediateTableStore.distinctify's
// documented "MIN(combi_id) GROUP BY data_cols" intent).  This eliminates PG-
// HashAggregate / TID-order non-determinism that previously made downstream
// cid-sorted iteration (e.g. FW_Group's Collections.sort(ids) at
// SheetWorker.java:951) produce different SubsetsG input orders in PG vs Java
// modes, which manifested as fw_opt4 = 34_368_597 (PG) vs 33_674_483 (Java).






























String excludedCols = tableToDistinct.matches("fw\\d?_\\d{0,}")
? "AND column_name NOT IN ('combi_id', 'fcombi_id', 'combo_txt')"
: "AND column_name NOT IN ('combi_id')";


// [Iter4 Step 8] Build INSERT with MIN(combi_id) + GROUP BY non-id cols +
// ORDER BY MIN(combi_id).  Preserves first-occurrence combi_id; downstream
// cid-sorted iteration now sees deterministic insertion order regardless of
// PG's distinct plan choice (HashAggregate vs Sort+Unique vs Group).
String insertDistinctSql = db.queryString(
"SELECT\n"
+ "  'INSERT INTO ' || quote_ident('" + tableTempDistincted + "') || ' (combi_id, ' \n"
+ "  || STRING_AGG(quote_ident(column_name), ', ') || ') '\n"
+ "  || 'SELECT MIN(o.combi_id) AS combi_id, ' || STRING_AGG('o.' || quote_ident(column_name), ', ')\n"
+ "  || ' FROM ' || quote_ident('" + tableToDistinct + "') || ' AS o'\n"
+ "  || ' GROUP BY ' || STRING_AGG('o.' || quote_ident(column_name), ', ')\n"
+ "  || ' ORDER BY MIN(o.combi_id)'\n"
+ "FROM information_schema.columns\n"
+ "WHERE table_name = '" + tableToDistinct + "'\n"
+ "  AND table_schema = 'public'\n"
+ "  " + excludedCols + ";");

if (insertDistinctSql != null && !insertDistinctSql.isBlank()) {
// Strict: if this INSERT fails, the temp table is EMPTY — and the swap
// below would then happily replace the original with nothing. The old
// swallow made that scenario a silent total data loss.
db.executeOrThrow(insertDistinctSql);
}

// Strict: the destructive swap. Any failure inside this batch (it runs as
// one implicit transaction on a single Statement) must abort the run, not
// leave a half-swapped table behind a one-line WARN. Multi-statement —
// Statement-based executeOrThrow is required, prepared execute() refuses it.
db.executeOrThrow(
"DELETE FROM \"" + tableToDistinct + "\";\n"
+ "DROP TABLE \"" + tableToDistinct + "\";\n"
+ "CREATE TABLE \"" + tableDistincted + "\"\n"
+ (tblspc != null ? "TABLESPACE \"" + tblspc + "\"\n" : "")
+ " AS TABLE \"" + tableTempDistincted + "\";\n"
+ "DELETE FROM \"" + tableTempDistincted + "\";\n"
+ "DROP TABLE \"" + tableTempDistincted + "\";\n"
+ "COMMIT;");
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
