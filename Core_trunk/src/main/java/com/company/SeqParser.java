package com.company;

import com.company.config.AppConfig;
import com.company.excel.ParsedWorkbook;
import com.company.excel.WorkbookParser;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

import java.util.*;
import java.util.regex.Pattern;


public final class SeqParser {

private static final Logger log = LogManager.getLogger(SeqParser.class);

private static final Pattern CARTES_PATTERN =
Pattern.compile("(?i)FW_Cartes(_first)?\\(.*\\)");
private static final Pattern FW_BRACE_VALID =
Pattern.compile("FW_\\([A-Za-z0-9_]*\\,\\,[A-Za-z0-9_]+\\,[A-Za-z0-9_]*"
+ "\\,[A-Za-z0-9_]+\\,\\,[A-Za-z0-9_]*\\,[A-Za-z0-9_]*"
+ "\\,(([1]:[1Nn])|([Mm]:[1MmNn])){1}\\)");

private SeqParser() { }



public static SeqParseResult parse(ParsedWorkbook workbook,
Map<Short, List<Short>> toCombinatoricsHM) {
return parse(workbook, toCombinatoricsHM, null);
}



public static SeqParseResult parse(ParsedWorkbook workbook,
Map<Short, List<Short>> toCombinatoricsHM,
AppConfig.SeqConfig seqCfg) {


Sheet seqSheet = workbook.stringSheetHM.get("FW_Seq");
if (seqSheet == null) {
log.warn("FW_Seq sheet not found — returning empty result");
return new SeqParseResult(toCombinatoricsHM);
}

var fmt = new DataFormatter();

// [Refactor 18052026 / step #17] These four maps are downstream-mutated
// from SheetWorker.processSheet by multiple concurrent virtual threads
// (`.remove(key)` calls when a sheet's table ends up empty).  A plain
// LinkedHashMap is NOT thread-safe under concurrent mutation — race
// conditions can silently lose entries.  The visible symptom on
// test14042026.xlsx was 6 930 OPT combos finding their key missing from
// key2tableMapOptional (which is itself derived from toCombinatoricsHMoptional
// via runOptsThread's `toCombinatoricsHMoptional.keySet()`) → 9M rows lost
// from fw_opt4 vs the engine's intended output (34 368 597).
//
// ConcurrentHashMap is the minimal-change fix: same Map<K,V> interface,
// thread-safe mutations, no extra locking.  Insertion order is sacrificed
// but downstream code uses these maps as SETs (keySet() iteration order
// not depended on for correctness — combinatorial generation enumerates
// the full set regardless of order).
Map<Short, List<Short>> toCombi        = new java.util.concurrent.ConcurrentHashMap<>(toCombinatoricsHM);
Map<Short, List<Short>> toCombiOpt     = new java.util.concurrent.ConcurrentHashMap<>();
Map<Short, List<Short>> toCombiExclude = new java.util.concurrent.ConcurrentHashMap<>();
Map<Short, List<Short>> toCombiLast    = new java.util.concurrent.ConcurrentHashMap<>();
Map<Short, List<String>> seqListMap    = new LinkedHashMap<>();
Map<Short, String> key2concat = new LinkedHashMap<>();
Set<Short> reuseSet = new LinkedHashSet<>();
Set<Short> reuseOnlySet = new LinkedHashSet<>();
List<Short> excl1List = new LinkedList<>();
List<Short> excl2List = new LinkedList<>();
Queue<Short> braceQueue = new PriorityQueue<>();


List<Short> priorFwBraceTargets = new ArrayList<>();
final boolean headlessEnabled    = seqCfg != null && seqCfg.headlessRowsAutoSynthesizeTarget;
final boolean nestedEnabled      = seqCfg != null && seqCfg.nestedFwBraceEnabled;
// Tier-0 bug fix 0.6 — default on; suppress only when caller explicitly opts out.
final boolean autoPromoteEnabled = (seqCfg == null) || seqCfg.autoPromoteSingleVerb;














String keySheetName = null;
int rowIdx = 0;

for (var row : seqSheet) {

List<String> seqList = new LinkedList<>();
boolean isOptional       = false;
boolean isExclude        = false;
boolean isReuse          = false;
boolean isReuseOnly      = false;






Short syntheticTarget = headlessEnabled
? workbook.fwSeqRowSyntheticTarget.get(rowIdx)
: null;
if (syntheticTarget != null) {
String synthName = workbook.shortStringSheetKey2SheetNameHM.get(syntheticTarget);
keySheetName = synthName;
log.info("[Issue1] SeqParser: row {} headless → using synthetic target '{}' (key={})",
rowIdx, synthName, syntheticTarget);
}


for (var cell : row) {
String v = fmt.formatCellValue(cell);
if (v.isBlank()) continue;


if (workbook.stringShortSheetName2SheetKeyHM.containsKey(v)) {
keySheetName = v;
}

Short curKey = keySheetName != null
? workbook.stringShortSheetName2SheetKeyHM.get(keySheetName)
: null;



if (v.endsWith("FW_Exclude") || v.endsWith("FW_Heading")) {
if (curKey != null) {
List<Short> moved = toCombi.remove(curKey);








if (moved != null) {
toCombiExclude.put(curKey, moved);
}
isExclude = true;
braceQueue.add(curKey);
}

} else if (v.endsWith("FW_LastInQueue")) {
if (curKey != null) {


List<Short> val = toCombi.get(curKey);
if (val != null) toCombiLast.put(curKey, val);
}

} else if (v.endsWith("FW_Reuse")) {
isReuse = true;
if (curKey != null) reuseSet.add(curKey);

} else if (v.endsWith("FW_ReuseTableOnly")) {
isReuseOnly = true;
if (curKey != null) reuseOnlySet.add(curKey);

} else if (v.endsWith("FW_Optional")) {
if (curKey != null) {
List<Short> moved = toCombi.remove(curKey);

if (moved != null) {
toCombiOpt.put(curKey, moved);
}
}
isOptional = true;

} else if (v.startsWith("FW_Concatenator")) {
if (curKey != null)
key2concat.put(curKey, v.replaceFirst("FW_Concatenator=", ""));

} else if (v.startsWith("FW_") && isAlgorithmDirective(v)) {

String resolved = nestedEnabled
? resolveNestedFwBrace(v, priorFwBraceTargets, workbook,
reuseSet, reuseOnlySet)
: v;
seqList.add(resolved);
validateDirective(resolved, workbook);

if (resolved.startsWith("FW_(")) {
braceQueue.add(curKey);
parseExcludedKeys(resolved, workbook, excl1List, excl2List);


if (curKey != null) priorFwBraceTargets.add(curKey);
}

}
}


// Tier-0 bug fix 0.6: auto-promote a single combo-rule verb to dual.
// The engine expects TWO identical FW_Combi(k) / FW_CombiR(k) / FW_Permut(k)
// / FW_PermutR(k) / FW_Subsets in cols 4..5 so both fw_<key> AND fw2_<key>
// get populated; joiners then read fw2_<key>.  Without the duplicate, data
// lands in fw_<key> only and joiners report 0 rows.  Skipped when:
//   • the row carries a joiner expression FW_(...) — joiners don't follow
//     the dual-verb rule;
//   • the row already has ≥ 2 combo verbs (already correct);
//   • the only verb is Cartes / Group / Separator / ReplaceRE — those are
//     intentionally single-use operators.
if (autoPromoteEnabled && !seqList.isEmpty()) {
boolean hasJoiner = false;
int comboVerbIdx = -1;
int comboVerbCount = 0;
for (int i = 0; i < seqList.size(); i++) {
String s = seqList.get(i);
if (s.startsWith("FW_(")) { hasJoiner = true; break; }
if (isComboRuleVerb(s)) {
comboVerbCount++;
if (comboVerbIdx < 0) comboVerbIdx = i;
}
}
if (!hasJoiner && comboVerbCount == 1) {
String only = seqList.get(comboVerbIdx);
seqList.add(only);
log.info("[Tier-0 fix 0.6] auto-promoted single combo verb '{}' to dual for row '{}'",
only, keySheetName);
}
}

if (!seqList.isEmpty() && keySheetName != null) {
Short rowKey = workbook.stringShortSheetName2SheetKeyHM.get(keySheetName);
if (rowKey != null) seqListMap.put(rowKey, seqList);
}

rowIdx++;

}


return new SeqParseResult(
toCombi, toCombiOpt, toCombiExclude, toCombiLast,
seqListMap, key2concat,
reuseSet, reuseOnlySet,
excl1List, excl2List,
braceQueue
);
}



/**
 * Tier-0 bug fix 0.6 — verbs that participate in the dual-write
 * (fw_&lt;key&gt; AND fw2_&lt;key&gt;) requirement.  Joiner FW_(...) and the
 * non-combinatorial verbs FW_Cartes / FW_Cartes_first / FW_Group /
 * FW_Separator / FW_ReplaceRE are intentionally excluded: those are
 * single-use operators that don't need duplication and would change
 * semantics if duplicated.
 */
private static boolean isComboRuleVerb(String v) {
if (v == null) return false;
return v.startsWith("FW_Combi(")
|| v.startsWith("FW_CombiR(")
|| v.startsWith("FW_Permut(")
|| v.startsWith("FW_PermutR(")
|| v.equals("FW_Subsets")
|| v.startsWith("FW_Subsets(");
}

private static boolean isAlgorithmDirective(String v) {
return !v.endsWith("FW_Optional")
&& !v.endsWith("FW_Heading")
&& !v.endsWith("FW_LastInQueue")
&& !v.endsWith("FW_Exclude")
&& !v.endsWith("FW_Reuse")
&& !v.endsWith("FW_ReuseTableOnly")
&& !v.startsWith("FW_Concatenator");
}

private static void validateDirective(String v, ParsedWorkbook workbook) {
if (CARTES_PATTERN.matcher(v).matches()) {
String inner = v.replaceFirst("(?i)FW_Cartes(_first)?\\(", "").replace(")", "");
Short k = workbook.stringShortSheetName2SheetKeyHM.get(inner);
if (k == null) log.error("FW_Cartes operand '{}' not found in sheet map", inner);
else           log.debug("FW_Cartes operand '{}' → key={} [PASS]", inner, k);
}
if (v.startsWith("FW_(")) {




if (v.contains(NESTED_MARK_PLAIN) || v.contains(NESTED_MARK_GROUPED)) {
log.debug("{} mask verification [SKIPPED — nested-rewrite marker present]", v);
return;
}

if (FW_BRACE_VALID.matcher(v).matches()) log.debug("{} mask verification [PASS]", v);
else                                       log.warn("{} mask verification [FAILED]", v);
}
}

private static void parseExcludedKeys(String v, ParsedWorkbook workbook,
List<Short> excl1List, List<Short> excl2List) {
String inner   = v.substring(v.indexOf('(') + 1, v.lastIndexOf(')'));

List<String> parts = WorkbookParser.splitTopLevelByComma(inner);

if (parts.size() > 2 && !parts.get(2).isEmpty()) {

Short k = workbook.stringShortSheetName2SheetKeyHM.get(stripNestedMark(parts.get(2)));
if (k != null) excl1List.add(k);
}
if (parts.size() > 4 && !parts.get(4).isEmpty()) {
Short k = workbook.stringShortSheetName2SheetKeyHM.get(stripNestedMark(parts.get(4)));
if (k != null) excl2List.add(k);
}
}



private static String stripNestedMark(String s) {
if (s == null) return null;
if (s.endsWith(NESTED_MARK_GROUPED)) return s.substring(0, s.length() - NESTED_MARK_GROUPED.length());
if (s.endsWith(NESTED_MARK_PLAIN))   return s.substring(0, s.length() - NESTED_MARK_PLAIN.length());
return s;
}




public static final String NESTED_MARK_PLAIN   = "~FWN";
public static final String NESTED_MARK_GROUPED = "~FWG";


private static String resolveNestedFwBrace(String directive,
List<Short> priorFwBraceTargets,
ParsedWorkbook workbook,
Set<Short> reuseSet, Set<Short> reuseOnlySet) {
if (!directive.startsWith("FW_(")) return directive;
String inner = directive.substring(directive.indexOf('(') + 1, directive.lastIndexOf(')'));
List<String> parts = WorkbookParser.splitTopLevelByComma(inner);

boolean nested1  = parts.size() > 2 && isNestedOperand(parts.get(2));
boolean nested2  = parts.size() > 4 && isNestedOperand(parts.get(4));
boolean grouped1 = nested1 && isGroupedNested(parts.get(2));
boolean grouped2 = nested2 && isGroupedNested(parts.get(4));
if (!nested1 && !nested2) return directive;






int idx = priorFwBraceTargets.size() - 1;
Short  key1 = null, key2 = null;
String name1 = null, name2 = null;
if (nested1 && idx >= 0) {
key1  = priorFwBraceTargets.get(idx);
name1 = workbook.shortStringSheetKey2SheetNameHM.get(key1);
idx--;
}
if (nested2 && idx >= 0) {
key2  = priorFwBraceTargets.get(idx);
name2 = workbook.shortStringSheetKey2SheetNameHM.get(key2);
idx--;
}

if (nested1) {
parts.set(2, name1 == null ? "" : (name1 + (grouped1 ? NESTED_MARK_GROUPED : NESTED_MARK_PLAIN)));
log.info("[Issue2] resolveNestedFwBrace: excluded1 nested {} → '{}' (grouped={})",
grouped1 ? "FW_()G" : "FW_()", name1, grouped1);
}
if (nested2) {
parts.set(4, name2 == null ? "" : (name2 + (grouped2 ? NESTED_MARK_GROUPED : NESTED_MARK_PLAIN)));
log.info("[Issue2] resolveNestedFwBrace: excluded2 nested {} → '{}' (grouped={})",
grouped2 ? "FW_()G" : "FW_()", name2, grouped2);
}







if (key1 != null) { reuseSet.add(key1); reuseOnlySet.add(key1); }
if (key2 != null) { reuseSet.add(key2); reuseOnlySet.add(key2); }

String rebuiltInner = String.join(",", parts);
return "FW_(" + rebuiltInner + ")";
}


private static boolean isNestedOperand(String operand) {
return operand != null && operand.startsWith("FW_(");
}


private static boolean isGroupedNested(String operand) {
return operand != null && operand.startsWith("FW_(") && operand.endsWith(")G");
}




public static final class SeqParseResult {

public final Map<Short, List<Short>>  toCombinatoricsHM;
public final Map<Short, List<Short>>  toCombinatoricsHMoptional;
public final Map<Short, List<Short>>  toCombinatoricsHMexclude;
public final Map<Short, List<Short>>  toCombinatoricsHMlastInQueue;
public final Map<Short, List<String>> mapShKey2seqList;
public final Map<Short, String>       key2concat;
public final Set<Short>               reuseSet;
public final Set<Short>               reuseTableOnlySet;
public final List<Short>              keyShortExcluded1List;
public final List<Short>              keyShortExcluded2List;
public final Queue<Short>             fw_BraceQueue;

private SeqParseResult(Map<Short, List<Short>> toCombinatoricsHM) {
this(toCombinatoricsHM,
new LinkedHashMap<>(), new LinkedHashMap<>(), new LinkedHashMap<>(),
new LinkedHashMap<>(), new LinkedHashMap<>(),
new LinkedHashSet<>(), new LinkedHashSet<>(),
new LinkedList<>(), new LinkedList<>(),
new PriorityQueue<>());
}

private SeqParseResult(
Map<Short, List<Short>>  toCombinatoricsHM,
Map<Short, List<Short>>  toCombinatoricsHMoptional,
Map<Short, List<Short>>  toCombinatoricsHMexclude,
Map<Short, List<Short>>  toCombinatoricsHMlastInQueue,
Map<Short, List<String>> mapShKey2seqList,
Map<Short, String>       key2concat,
Set<Short>               reuseSet,
Set<Short>               reuseTableOnlySet,
List<Short>              keyShortExcluded1List,
List<Short>              keyShortExcluded2List,
Queue<Short>             fw_BraceQueue) {
this.toCombinatoricsHM           = toCombinatoricsHM;
this.toCombinatoricsHMoptional   = toCombinatoricsHMoptional;
this.toCombinatoricsHMexclude    = toCombinatoricsHMexclude;
this.toCombinatoricsHMlastInQueue = toCombinatoricsHMlastInQueue;
this.mapShKey2seqList            = mapShKey2seqList;
this.key2concat                  = key2concat;
this.reuseSet                    = reuseSet;
this.reuseTableOnlySet           = reuseTableOnlySet;
this.keyShortExcluded1List       = keyShortExcluded1List;
this.keyShortExcluded2List       = keyShortExcluded2List;
this.fw_BraceQueue               = fw_BraceQueue;
}
}
}
