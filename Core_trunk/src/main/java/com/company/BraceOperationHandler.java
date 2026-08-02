package com.company;

import com.company.config.AppConfig;
import com.company.db.DbClient;
import com.company.db.SchemaProvisioner;
import com.company.excel.ParsedWorkbook;
import com.company.excel.WorkbookParser;
import com.company.store.IntermediateTableStore;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;
import java.util.stream.Stream;


public final class BraceOperationHandler {

private static final Logger log = LogManager.getLogger(BraceOperationHandler.class);

private final AppConfig      config;
private final DbClient       db;
private final SchemaProvisioner schema;
private final ParsedWorkbook workbook;
/** [Iter2] All fw_/fw2_ intermediate I/O routes through here. */
private final IntermediateTableStore store;


private final java.util.function.Consumer<Short> sheetWaiter;

public BraceOperationHandler(AppConfig config, DbClient db,
SchemaProvisioner schema, ParsedWorkbook workbook,
IntermediateTableStore store,
java.util.function.Consumer<Short> sheetWaiter) {
this.config      = config;
this.db          = db;
this.schema      = schema;
this.workbook    = workbook;
this.store       = store;
this.sheetWaiter = sheetWaiter;
}




public boolean execute(
String directive,
Short key,
Map<Short, List<Short>> toCombinatoricsHMcopy,
ArrayList<short[]> fwKeyShort,
AtomicLong fwId,
Map<String, ArrayList<short[]>> mapTable2combs,
Map<Short, String> key2tableMap,
Map<Short, String> key2tableMapOpt,
Set<Short> reuseSet,
Set<Short> reuseTableOnlySet,
List<Short> excl1List,
List<Short> excl2List) {


String inner = directive.substring(directive.indexOf('(') + 1, directive.lastIndexOf(')'));





List<String> partsList = WorkbookParser.splitTopLevelByComma(inner);
String[] parts = partsList.toArray(new String[0]);


String startName     = parts[0];
String excluded1Name = parts[2];
String relationName  = parts[3];
String excluded2Name = parts[4];
String endName       = parts[parts.length - 3];
String separatorName = parts[parts.length - 2];
String formula       = parts[parts.length - 1];






boolean excl1Nested  = false, excl1Grouped = false;
boolean excl2Nested  = false, excl2Grouped = false;
if (excluded1Name.endsWith(SeqParser.NESTED_MARK_GROUPED)) {
excluded1Name = excluded1Name.substring(0,
excluded1Name.length() - SeqParser.NESTED_MARK_GROUPED.length());
excl1Nested = true; excl1Grouped = true;
} else if (excluded1Name.endsWith(SeqParser.NESTED_MARK_PLAIN)) {
excluded1Name = excluded1Name.substring(0,
excluded1Name.length() - SeqParser.NESTED_MARK_PLAIN.length());
excl1Nested = true;
}
if (excluded2Name.endsWith(SeqParser.NESTED_MARK_GROUPED)) {
excluded2Name = excluded2Name.substring(0,
excluded2Name.length() - SeqParser.NESTED_MARK_GROUPED.length());
excl2Nested = true; excl2Grouped = true;
} else if (excluded2Name.endsWith(SeqParser.NESTED_MARK_PLAIN)) {
excluded2Name = excluded2Name.substring(0,
excluded2Name.length() - SeqParser.NESTED_MARK_PLAIN.length());
excl2Nested = true;
}


if (excluded1Name.startsWith("FW_(")) excluded1Name = "";
if (excluded2Name.startsWith("FW_(")) excluded2Name = "";


Short keyStart    = startName.isEmpty()     ? null : workbook.stringShortSheetName2SheetKeyHM.get(startName);
Short keyExcl1    = excluded1Name.isEmpty()  ? null : workbook.stringShortSheetName2SheetKeyHM.get(excluded1Name);
Short keyRelation = relationName.isEmpty()   ? null : workbook.stringShortSheetName2SheetKeyHM.get(relationName);
Short keyExcl2    = excluded2Name.isEmpty()  ? null : workbook.stringShortSheetName2SheetKeyHM.get(excluded2Name);
Short keyEnd      = endName.isEmpty()        ? null : workbook.stringShortSheetName2SheetKeyHM.get(endName);
Short keySep      = separatorName.isEmpty()  ? null : workbook.stringShortSheetName2SheetKeyHM.get(separatorName);

log.info("FW_( brace: key={} formula={} excl1={}{} excl2={}{}",
key, formula, keyExcl1, excl1Nested ? (excl1Grouped ? "[G]" : "[N]") : "",
keyExcl2, excl2Nested ? (excl2Grouped ? "[G]" : "[N]") : "");






if (keyExcl1 != null) {
log.debug("FW_( brace: waiting for excluded sheet {} to complete", keyExcl1);
sheetWaiter.accept(keyExcl1);
}
if (keyExcl2 != null) {
log.debug("FW_( brace: waiting for excluded sheet {} to complete", keyExcl2);
sheetWaiter.accept(keyExcl2);
}







// [Iter2] BraceOperand abstracts the prior tmp_brace_ table machinery.
// In PG mode the operand wraps a (possibly temp) table name; in memory
// mode it wraps an in-heap List<short[]> filtered/grouped as needed.
BraceOperand operandA = (keyExcl1 != null)
? prepareBraceOperand(key, "a", keyExcl1, excl1Nested, excl1Grouped)
: null;
BraceOperand operandB = (keyExcl2 != null)
? prepareBraceOperand(key, "b", keyExcl2, excl2Nested, excl2Grouped)
: null;

try {
if (formula.startsWith("1:")) {
processOneToFormula(formula, operandA, operandB, keyRelation,
keySep, keyStart, keyEnd, startName, endName,
toCombinatoricsHMcopy, fwId, key);
} else if (formula.startsWith("M:")) {
processManyToFormula(formula, operandA, operandB, keyRelation,
keySep, keyStart, keyEnd, startName, endName,
toCombinatoricsHMcopy, fwId, key);
}

// [Iter2] Was: db.copyIn(sb, "fw_<k>", "combi_id, combos") for any tail
// rows.  Now: store flushes its internal buffer (PG mode) or noop (memory).
store.flushFw(key);
} finally {

if (operandA != null) operandA.dispose();
if (operandB != null) operandB.dispose();

}


fwKeyShort.clear();
fwKeyShort.add(new short[]{});

// [Iter2] Was: schema.createFw2Table + INSERT INTO fw2_ SELECT combi_id, combos FROM fw_ + DELETE FROM fw_.
// Now: store.moveFwToFw2 encapsulates the same effect (PG: 3 SQL statements;
// memory: in-place list move).
try {
store.moveFwToFw2(key);
} catch (SQLException e) {
log.error("FW_( brace: failed to create fw2_ copy for key={}", key, e);
}


// [Iter2] Was: Fw2Service().getListOfFW2() via Hibernate + CustomInterceptor2
// retarget.  Now: store.readFw2Combos directly (same source-of-truth).
try {
com.company.utils.CustomInterceptor2.setCurrentTable("fw2_" + key);
for (short[] combo : store.readFw2Combos(key)) {
fwKeyShort.add(combo);
}
} catch (Exception e) {
log.warn("FW_( brace: failed to reload fw2_ data for key={}", key, e);
} finally {
com.company.utils.CustomInterceptor2.clearCurrentTable();
}









cleanupExcludedTables(keyExcl1, keyExcl2, reuseSet, reuseTableOnlySet, mapTable2combs);

log.info("FW_( brace: completed for key={}", key);
return true;
}



private void processOneToFormula(
String formula, BraceOperand operandA, BraceOperand operandB,
Short keyRelation, Short keySep, Short keyStart, Short keyEnd,
String startName, String endName,
Map<Short, List<Short>> srcMap,
AtomicLong fwId, Short outerKey) {

List<Short[]> listA = (operandA != null) ? operandA.readAll() : Collections.emptyList();

for (Short[] a : listA) {
if (formula.equals("1:1")) {
List<Short[]> listB = (operandB != null) ? operandB.readWithCardinality(a.length) : Collections.emptyList();
for (Short[] b : listB) {
String result = alternateAndBuild(a, b, keyRelation, keySep, srcMap);
result = wrapWithStartEnd(result, keyStart, keyEnd, startName, endName, srcMap);
appendRow(fwId, outerKey, result);
}
} else if (formula.equals("1:N")) {
List<Short[]> listB = (operandB != null) ? operandB.readAll() : Collections.emptyList();
for (Short[] b : listB) {
String result = buildOneToN(a, b, keyRelation, keySep, srcMap);
result = wrapWithStartEnd(result, keyStart, keyEnd, startName, endName, srcMap);
appendRow(fwId, outerKey, result);
}
}
}
}

private void processManyToFormula(
String formula, BraceOperand operandA, BraceOperand operandB,
Short keyRelation, Short keySep, Short keyStart, Short keyEnd,
String startName, String endName,
Map<Short, List<Short>> srcMap,
AtomicLong fwId, Short outerKey) {

if (formula.equals("M:M")) {
List<Short[]> listA = (operandA != null) ? operandA.readAll() : Collections.emptyList();
for (Short[] a : listA) {
List<Short[]> listB = (operandB != null) ? operandB.readWithCardinality(a.length) : Collections.emptyList();
for (Short[] b : listB) {
String result = buildManyToMany(a, b, keyRelation, srcMap);
result = wrapWithStartEnd(result, keyStart, keyEnd, startName, endName, srcMap);
appendRow(fwId, outerKey, result);
}
}
} else if (formula.equals("M:N")) {
List<Short[]> listA = (operandA != null) ? operandA.readAll() : Collections.emptyList();
for (Short[] a : listA) {
List<Short[]> listB = (operandB != null) ? operandB.readAll() : Collections.emptyList();
for (Short[] b : listB) {
String result = buildManyToMany(a, b, keyRelation, srcMap);
result = wrapWithStartEnd(result, keyStart, keyEnd, startName, endName, srcMap);
appendRow(fwId, outerKey, result);
}
}
} else if (formula.equals("M:1")) {
List<Short[]> listB = (operandB != null) ? operandB.readAll() : Collections.emptyList();
for (Short[] b : listB) {
List<Short[]> listA = (operandA != null) ? operandA.readAll() : Collections.emptyList();
for (Short[] a : listA) {
String result = buildManyToOne(a, b, keyRelation, keySep, srcMap);
result = wrapWithStartEnd(result, keyStart, keyEnd, startName, endName, srcMap);
appendRow(fwId, outerKey, result);
}
}
}
}




private static String safeFirst(Map<Short, List<Short>> srcMap, Short key) {
if (key == null) return null;
List<Short> list = srcMap.get(key);
if (list == null || list.isEmpty()) return null;
return list.get(0).toString();
}


private String alternateAndBuild(Short[] a, Short[] b,
Short keyRelation, Short keySep,
Map<Short, List<Short>> srcMap) {
List<String> alternated = new ArrayList<>();
int maxLen = Math.max(a.length, b.length);
for (int i = 0; i < maxLen; i++) {
if (i < a.length) alternated.add(String.valueOf(a[i]));
if (i < b.length) alternated.add(String.valueOf(b[i]));
}


String relationVal = safeFirst(srcMap, keyRelation);
String sepVal      = safeFirst(srcMap, keySep);

String[] arr = alternated.toArray(new String[0]);
for (int j = 0; j < arr.length; j++) {
if (j % 2 == 0) {
arr[j] = arr[j] + (relationVal != null
? ", " + relationVal : "");
} else {
if (j != arr.length - 1) {
arr[j] = arr[j] + (sepVal != null
? ", " + sepVal : "");
}
}
}
return String.join(", ", arr);
}

private String buildOneToN(Short[] a, Short[] b,
Short keyRelation, Short keySep,
Map<Short, List<Short>> srcMap) {

String relationVal = safeFirst(srcMap, keyRelation);
String sepVal      = safeFirst(srcMap, keySep);
String relation = relationVal != null ? relationVal + ", " : "";
String sep = sepVal != null ? ", " + sepVal : "";
String bStr = Arrays.stream(b).map(String::valueOf).collect(Collectors.joining(", "));

List<String> parts = Arrays.stream(a)
.map(e -> e + ", " + relation + bStr + sep)
.collect(Collectors.toList());
String result = String.join(", ", parts);
if (sepVal != null) {
result = result.substring(0, result.lastIndexOf(","));
}
return result;
}

private String buildManyToMany(Short[] a, Short[] b,
Short keyRelation,
Map<Short, List<Short>> srcMap) {
String aStr = Arrays.stream(a).map(String::valueOf).collect(Collectors.joining(", "));
String bStr = Arrays.stream(b).map(String::valueOf).collect(Collectors.joining(", "));

String relationVal = safeFirst(srcMap, keyRelation);
String relation = relationVal != null
? relationVal + ", " : "";
return aStr + ", " + relation + bStr;
}

private String buildManyToOne(Short[] a, Short[] b,
Short keyRelation, Short keySep,
Map<Short, List<Short>> srcMap) {
String aStr = Arrays.stream(a).map(String::valueOf).collect(Collectors.joining(", "));

String relationVal = safeFirst(srcMap, keyRelation);
String sepVal      = safeFirst(srcMap, keySep);
String relation = relationVal != null ? relationVal + ", " : "";
String sep = sepVal != null ? ", " + sepVal : "";

List<String> parts = Stream.of(b)
.map(bVal -> aStr + ", " + relation + bVal + sep)
.collect(Collectors.toList());
String result = String.join(", ", parts);
if (sepVal != null) {
result = result.substring(0, result.lastIndexOf(","));
}
return result;
}



private String wrapWithStartEnd(String result, Short keyStart, Short keyEnd,
String startName, String endName,
Map<Short, List<Short>> srcMap) {

if (!startName.isEmpty() && keyStart != null) {
String startVal = safeFirst(srcMap, keyStart);
if (startVal != null) result = startVal + ", " + result;
}
if (!endName.isEmpty() && keyEnd != null) {
String endVal = safeFirst(srcMap, keyEnd);
if (endVal != null) result = result + ", " + endVal;
}
return result;
}

private void appendRow(AtomicLong fwId, Short outerKey, String arrayContent) {
// [Iter2] Was: StringBuilder accumulation + db.copyIn at counter4copyMax.
// Now: parse the comma-separated cell-key string to short[], dispatch
// through store.appendFwRow (PG mode: store buffers + COPY; memory mode:
// list.add).
short[] combo = parseCommaSeparatedToShortArray(arrayContent);
if (combo.length == 0) return;
store.appendFwRow(outerKey, fwId.incrementAndGet(), combo);
}

private static short[] parseCommaSeparatedToShortArray(String csv) {
if (csv == null || csv.isEmpty()) return new short[0];
String[] toks = csv.split(",");
short[] out = new short[toks.length];
int j = 0;
for (String t : toks) {
String s = t.trim();
if (s.isEmpty()) continue;
try {
out[j++] = Short.parseShort(s);
} catch (NumberFormatException e) {
// Skip non-numeric tokens (shouldn't occur in normal brace output).
}
}
if (j != out.length) {
short[] trimmed = new short[j];
System.arraycopy(out, 0, trimmed, 0, j);
return trimmed;
}
return out;
}



private static final String TMP_BRACE_PREFIX = "public.tmp_brace_";

// ─── [Iter2] Brace operand abstraction ──────────────────────────────
//
// Encapsulates "read the operand rows" + "filter by cardinality" + "dispose
// any temporary state".  Two impls:
//   - PgBraceOperand: wraps a table name (might be a tmp_brace_ table that
//     must be DROP-ed on dispose; might be the durable fw2_<k>/fw_<k>).
//   - JavaBraceOperand: wraps an in-memory List<short[]>; dispose is noop.
private interface BraceOperand {
    List<Short[]> readAll();
    List<Short[]> readWithCardinality(int cardinality);
    void dispose();
}

private final class PgBraceOperand implements BraceOperand {
    private final String tableName;
    private final boolean isTemp;
    PgBraceOperand(String tableName, boolean isTemp) {
        this.tableName = tableName;
        this.isTemp = isTemp;
    }
    @SuppressWarnings("unchecked")
    public List<Short[]> readAll() {
        if (tableName == null) return Collections.emptyList();
        return (List<Short[]>) (List<?>) db.queryArrayList(
                "SELECT combos_1 FROM " + tableName + ";");
    }
    @SuppressWarnings("unchecked")
    public List<Short[]> readWithCardinality(int cardinality) {
        if (tableName == null) return Collections.emptyList();
        return (List<Short[]>) (List<?>) db.queryArrayList(
                "SELECT combos_1 FROM " + tableName
                + " WHERE cardinality(combos_1) = " + cardinality + ";");
    }
    public void dispose() {
        if (isTemp && tableName != null) {
            // IF EXISTS covers the only benign case (already gone); any other
            // failure to drop a temp operand table is a real problem.
            db.executeOrThrow("DROP TABLE IF EXISTS " + tableName + ";");
            log.debug("[Issue2] Dropped temp operand table {}", tableName);
        }
    }
}

private static final class JavaBraceOperand implements BraceOperand {
    private final List<short[]> rows;
    JavaBraceOperand(List<short[]> rows) { this.rows = rows; }
    public List<Short[]> readAll() {
        List<Short[]> out = new ArrayList<>(rows.size());
        for (short[] r : rows) out.add(boxArray(r));
        return out;
    }
    public List<Short[]> readWithCardinality(int cardinality) {
        List<Short[]> out = new ArrayList<>();
        for (short[] r : rows) if (r.length == cardinality) out.add(boxArray(r));
        return out;
    }
    public void dispose() { /* no temp state */ }
    private static Short[] boxArray(short[] s) {
        Short[] o = new Short[s.length];
        for (int i = 0; i < s.length; i++) o[i] = s[i];
        return o;
    }
}

/** [Iter2] Build a {@link BraceOperand} for innerKey.  Mode-aware:
 *  PG-backed store → tmp_brace_ table (legacy behaviour); memory store →
 *  in-heap snapshot with grouped/cardinality filtering applied in Java. */
private BraceOperand prepareBraceOperand(Short outerKey, String slot,
        Short innerKey, boolean nested, boolean grouped) {

    if (!store.isPgBacked()) {
        return prepareJavaBraceOperand(innerKey, grouped);
    }
    return preparePgBraceOperand(outerKey, slot, innerKey, nested, grouped);
}

private BraceOperand prepareJavaBraceOperand(Short innerKey, boolean grouped) {
    // Source resolution mirrors PG path's resolveSourceTableForInner + Fast-fix B:
    // prefer fw2_<k> if it has rows, else fw_<k>.
    boolean useFw2 = !store.isEmpty(innerKey, true);
    List<short[]> src;
    if (useFw2) {
        src = store.readFw2Combos(innerKey);
    } else if (!store.isEmpty(innerKey, false)) {
        log.warn("[Issue2/memory] inner operand fw2_{} missing — falling back to fw_{}",
                innerKey, innerKey);
        src = store.readFwCombos(innerKey);
    } else {
        log.warn("[Issue2/memory] inner operand has neither fw2_{} nor fw_{} — empty",
                innerKey, innerKey);
        return new JavaBraceOperand(Collections.emptyList());
    }
    if (grouped) {
        int total = 0;
        for (short[] r : src) total += r.length;
        short[] mega = new short[total];
        int idx = 0;
        for (short[] r : src) {
            System.arraycopy(r, 0, mega, idx, r.length);
            idx += r.length;
        }
        return new JavaBraceOperand(Collections.singletonList(mega));
    }
    return new JavaBraceOperand(src);
}

private BraceOperand preparePgBraceOperand(Short outerKey, String slot,
        Short innerKey, boolean nested, boolean grouped) {

    if (!nested) {
        // [Fast-fix 18052026 / Cluster B] Prefer durable fw2_; build a temp
        // aliasing combos→combos_1 from fw_ as a fallback.  See pre-iter2
        // BraceOperationHandler.prepareInnerOperandTable for the original
        // commentary.
        String fw2 = "public.fw2_" + innerKey;
        String existsFw2 = db.queryString(
                "SELECT CASE WHEN to_regclass('" + fw2 + "') IS NOT NULL THEN '1' ELSE '0' END;");
        if ("1".equals(existsFw2)) return new PgBraceOperand(fw2, false);
        String fw1 = "public.fw_" + innerKey;
        String existsFw1 = db.queryString(
                "SELECT CASE WHEN to_regclass('" + fw1 + "') IS NOT NULL THEN '1' ELSE '0' END;");
        if (!"1".equals(existsFw1)) {
            log.warn("[Fast-fix-B] neither fw2_{} nor fw_{} exists — brace operand will be empty",
                    innerKey, innerKey);
            return new PgBraceOperand(fw2, false);
        }
        String tmpName = TMP_BRACE_PREFIX + outerKey + "_" + slot;
        // Strict: IF EXISTS makes absence benign; a drop that fails otherwise
        // would leave a stale operand table for the CREATE below to trip on.
        db.executeOrThrow("DROP TABLE IF EXISTS " + tmpName + ";");
        try {
            db.execute("CREATE UNLOGGED TABLE " + tmpName + " AS "
                    + "SELECT combi_id, combos AS combos_1 FROM " + fw1 + ";");
            log.info("[Fast-fix-B] fw2_{} missing — built temp {} from fw_{}",
                    innerKey, tmpName, innerKey);
            return new PgBraceOperand(tmpName, true);
        } catch (SQLException e) {
            log.warn("[Fast-fix-B] could not materialise temp {} from fw_{}: {} — falling through to (likely-missing) fw2_",
                    tmpName, innerKey, e.getMessage());
            return new PgBraceOperand(fw2, false);
        }
    }

    String sourceTable = resolveSourceTableForInner(innerKey);
    String comboCol    = comboColForSourceTable(sourceTable);

    String tmpName = TMP_BRACE_PREFIX + outerKey + "_" + slot;
    // Strict for the same reason as the non-nested path above: absence is the
    // one benign case and IF EXISTS already covers it.
    db.executeOrThrow("DROP TABLE IF EXISTS " + tmpName + ";");

    String ddl;
    if (grouped) {
        ddl = "CREATE UNLOGGED TABLE " + tmpName + " AS "
                + "SELECT 1::bigint AS combi_id, "
                + "       (array_agg(elem ORDER BY rn))::int2[] AS combos_1 "
                + "FROM (SELECT row_number() OVER (ORDER BY combi_id) AS rn, "
                + "             unnest(" + comboCol + ") AS elem "
                + "      FROM " + sourceTable + ") z;";
    } else {
        ddl = "CREATE UNLOGGED TABLE " + tmpName + " AS "
                + "SELECT combi_id, " + comboCol + " AS combos_1 FROM " + sourceTable + ";";
    }

    try {
        db.execute(ddl);
        log.info("[Issue2] preparePgBraceOperand: built {} (innerKey={}, grouped={}, source={})",
                tmpName, innerKey, grouped, sourceTable);
        return new PgBraceOperand(tmpName, true);
    } catch (SQLException e) {
        log.error("[Issue2] Failed to build {} for innerKey={} (grouped={}, source={})",
                tmpName, innerKey, grouped, sourceTable, e);
        // Fall back to the source itself (no transformation) — matches legacy.
        return new PgBraceOperand(sourceTable, false);
    }
}



private String resolveSourceTableForInner(Short innerKey) {
String fw2 = "public.fw2_" + innerKey;
String fw  = "public.fw_"  + innerKey;
String exists = db.queryString(
"SELECT CASE WHEN to_regclass('" + fw2 + "') IS NOT NULL THEN '2' "
+ "WHEN to_regclass('" + fw + "') IS NOT NULL THEN '1' ELSE '0' END;");
if ("2".equals(exists)) return fw2;
if ("1".equals(exists)) {
log.warn("[Issue2] inner operand fw2_{} missing — falling back to fw_{} "
+ "(upstream sheet likely had only one algorithm directive)", innerKey, innerKey);
return fw;
}
log.warn("[Issue2] inner operand has neither fw2_{} nor fw_{} — operand will be empty",
innerKey, innerKey);
return fw2;
}


private static String comboColForSourceTable(String sourceTable) {
return sourceTable.contains(".fw2_") ? "combos_1" : "combos";
}



private void cleanupExcludedTables(Short keyExcl1, Short keyExcl2,
Set<Short> reuseSet,
Set<Short> reuseTableOnlySet,
Map<String, ArrayList<short[]>> mapTable2combs) {
if (keyExcl1 != null) {
if (!reuseTableOnlySet.contains(keyExcl1)) {
store.deleteRows(keyExcl1, true);
store.deleteRows(keyExcl1, false);
}
if (!reuseSet.contains(keyExcl1)) {
store.dropTable(keyExcl1, true);
store.dropTable(keyExcl1, false);
}
mapTable2combs.remove("fw2_" + keyExcl1);
mapTable2combs.remove("fw_" + keyExcl1);
}
if (keyExcl2 != null) {
if (!reuseTableOnlySet.contains(keyExcl2)) {
store.deleteRows(keyExcl2, true);
store.deleteRows(keyExcl2, false);
}
if (!reuseSet.contains(keyExcl2)) {
store.dropTable(keyExcl2, true);
store.dropTable(keyExcl2, false);
}
mapTable2combs.remove("fw2_" + keyExcl2);
mapTable2combs.remove("fw_" + keyExcl2);
}
}
}
