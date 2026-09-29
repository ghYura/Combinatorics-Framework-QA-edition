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

package com.company.excel;

import com.company.StringButQuotesRefiner;
import com.company.config.AppConfig;
import com.company.daoModelService.KeyValueService;
import com.company.daoModelService.SheetFW_EXIT_CODEService;
import com.company.file.CSVDataMapper;
import com.company.file.ReadFileToString;
import com.company.helpers.CodeLineNumber;
import com.company.models.NumberToValue1;
import com.company.models.SheetFW_EXIT_CODE;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.poi.openxml4j.exceptions.InvalidFormatException;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;

import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Pattern;


public final class WorkbookParser {


private static final Logger log = LogManager.getLogger(WorkbookParser.class);

private static final Set<String> CONTROL_SHEET_NAMES = new LinkedHashSet<>(Arrays.asList(
"FW_Seq", "FW_Info", "FW_SheetNames", "FW_CUSTOM_VAR",
"FW_RunMeFirstOnce", "FW_Arguments", "FW_Complex",
"FW_Combi", "FW_CombiR", "FW_Permut", "FW_PermutR",
"FW_Subsets", "FW_Cartes"
));

private WorkbookParser() { }



public static ParsedWorkbook parse(Path xlsxPath) throws IOException, InvalidFormatException {
return parse(xlsxPath.toFile(), null);
}

public static ParsedWorkbook parse(String xlsxFilePath) throws IOException, InvalidFormatException {
return parse(new File(xlsxFilePath), null);
}



public static ParsedWorkbook parse(Path xlsxPath, AppConfig.WorkbookConfig wb)
throws IOException, InvalidFormatException {
return parse(xlsxPath.toFile(), wb);
}

public static ParsedWorkbook parse(String xlsxFilePath, AppConfig.WorkbookConfig wb)
throws IOException, InvalidFormatException {
return parse(new File(xlsxFilePath), wb);
}




private static ParsedWorkbook parse(File xlsxFile, AppConfig.WorkbookConfig wbCfg)
throws IOException, InvalidFormatException {
try (Workbook workbook = WorkbookFactory.create(xlsxFile)) {
return parseWorkbook(workbook, wbCfg, xlsxFile.getName());
}
}

/**
 * Tier-1 win 1.2: parse a pre-constructed POI {@link Workbook} into a
 * {@link ParsedWorkbook}.  Exposed publicly so alternative
 * {@link ScheduleParser} implementations ({@link JsonScheduleParser},
 * future YAML/programmatic) can build a Workbook in-memory and hand it
 * off to the same downstream pipeline.
 *
 * @param workbook   a POI workbook (in-memory or file-backed)
 * @param wbCfg      workbook config (for auto-generate-missing-sheets flag)
 * @param displayName  what to log; e.g. file name, "json:scenario.json"
 */
public static ParsedWorkbook parseWorkbook(Workbook workbook,
                                            AppConfig.WorkbookConfig wbCfg,
                                            String displayName) {
ParsedWorkbook.Builder b = new ParsedWorkbook.Builder();
log.info("Workbook '{}' has {} sheets", displayName, workbook.getNumberOfSheets());

final Sheet[] allSheets = new Sheet[workbook.getNumberOfSheets()];
for (int i = 0; i < allSheets.length; i++) {
allSheets[i] = workbook.getSheetAt(i);
}

for (var sheet : allSheets) {
String name = sheet.getSheetName();
if (name.startsWith("FW_")) {
b.numOfFwSheets++;
routeControlSheet(b, sheet, name);
} else {
b.maxSheetNumber = (short) (b.maxSheetNumber + 1);
b.shortSheetHM.put(b.maxSheetNumber, sheet);
b.key2name.put(b.maxSheetNumber, name);
b.name2key.put(name, b.maxSheetNumber);
}
}
log.info("{} FW_* control sheets, {} data sheets",
b.numOfFwSheets, b.shortSheetHM.size());

var dataFormatter = new DataFormatter();

// [Keys] DataTypeDispatcher: one lean counting pass BEFORE the first key is issued decides
// the key width (short by default; byte only as the core.keys.dispatch=auto experiment) and where the label counter
// starts.  The legacy short[] counter wrapped silently past 32767; this fails fast instead.
b.keyPlan = DataTypeDispatcher.dispatch(allSheets, b.stringSheetHM.get("FW_Seq"), wbCfg);

parseCellValues(b, allSheets, dataFormatter);

preScanFwSeq(b, wbCfg, dataFormatter);

return b.build();
}



private static final Pattern FW_FORMULA = Pattern.compile("[1MNm]:[1MNn]");


private static final Set<String> FW_SEQ_NON_TARGET_PREFIXES = Set.of(
"FW_Optional", "FW_Heading", "FW_Exclude", "FW_LastInQueue",
"FW_Reuse", "FW_ReuseTableOnly", "FW_Concatenator",
"FW_Subsets", "FW_Permut", "FW_Combi", "FW_Cartes",
"FW_Group", "FW_ReplaceRE", "FW_Separator");


private static void preScanFwSeq(ParsedWorkbook.Builder b,
AppConfig.WorkbookConfig wbCfg,
DataFormatter fmt) {
if (wbCfg == null || !wbCfg.autoGenerateMissingSheetsFromFwSeq) return;
Sheet seqSheet = b.stringSheetHM.get("FW_Seq");
if (seqSheet == null) {
log.info("[Issue1] preScanFwSeq: FW_Seq sheet missing — nothing to scan");
return;
}

for (VirtualSheet vs : discoverVirtualSheets(seqSheet, b.name2key.keySet(),
wbCfg.virtualSheetNamePrefix, fmt)) {
short k = b.registerVirtualSheet(vs.name);
if (vs.headlessRowIdx != null) {
b.fwSeqRowSyntheticTarget.put(vs.headlessRowIdx, k);
log.info("[Issue1] preScanFwSeq: headless row {} → synthesised target '{}' (key={})",
vs.headlessRowIdx, vs.name, k);
} else if (vs.fromOperand) {
log.info("[Issue1] preScanFwSeq: FW_(...) operand '{}' missing → virtual key={}", vs.name, k);
} else {
log.info("[Issue1] preScanFwSeq: column-0 missing sheet '{}' → virtual key={}", vs.name, k);
}
}
log.info("[Issue1] preScanFwSeq complete: {} virtual sheets registered, {} headless rows synthesised",
b.virtualSheetNames.size(), b.fwSeqRowSyntheticTarget.size());
}


/** One sheet {@link #discoverVirtualSheets} decided to auto-register, in registration order. */
static final class VirtualSheet {
final String name;
/** Row index of the headless FW_Seq row this sheet is the synthetic target of, else null. */
final Integer headlessRowIdx;
/** True when found as a missing operand inside an FW_(...) joiner. */
final boolean fromOperand;
VirtualSheet(String name, Integer headlessRowIdx, boolean fromOperand) {
this.name = name; this.headlessRowIdx = headlessRowIdx; this.fromOperand = fromOperand;
}
}

/**
 * The sheets FW_Seq references that the workbook does not contain, in the exact order
 * {@link #preScanFwSeq} registers them.  Pure: no key is issued and nothing is mutated, so
 * {@link DataTypeDispatcher} can count them before the first key exists while the parser
 * registers them from the very same list.
 *
 * @param knownNames the real (non-FW_) sheet names; copied, the caller's set is not touched
 */
static List<VirtualSheet> discoverVirtualSheets(Sheet seqSheet, Set<String> knownNames,
String virtualNamePrefix, DataFormatter fmt) {
List<VirtualSheet> found = new ArrayList<>();
Set<String> known = new LinkedHashSet<>(knownNames);

int rowIdx = 0;
for (Row row : seqSheet) {
List<String> rowCells = new ArrayList<>();
for (var cell : row) {
String v = fmt.formatCellValue(cell);
if (v != null && !v.isBlank()) rowCells.add(v.trim());
}
if (rowCells.isEmpty()) { rowIdx++; continue; }

String firstVal = rowCells.get(0);
boolean headless = firstVal.startsWith("FW_");

if (headless) {
String virtualName = virtualNamePrefix + (rowIdx + 1);
int suffix = 1;
while (known.contains(virtualName)) {
suffix++;
virtualName = virtualNamePrefix + (rowIdx + 1) + "_" + suffix;
}
known.add(virtualName);
found.add(new VirtualSheet(virtualName, rowIdx, false));
} else if (!known.contains(firstVal)) {


known.add(firstVal);
found.add(new VirtualSheet(firstVal, null, false));
}


for (String v : rowCells) {
if (!v.startsWith("FW_(") || !v.endsWith(")")) continue;
String inner = v.substring(v.indexOf('(') + 1, v.lastIndexOf(')'));
List<String> parts = splitTopLevelByComma(inner);
for (int i = 0; i < parts.size(); i++) {
String operand = parts.get(i);
if (operand.isEmpty()) continue;

if (operand.startsWith("FW_(") || operand.equals("FW_()")) continue;

if (i == parts.size() - 1 && FW_FORMULA.matcher(operand).matches()) continue;

boolean directiveLike = false;
for (String p : FW_SEQ_NON_TARGET_PREFIXES) {
if (operand.startsWith(p)) { directiveLike = true; break; }
}
if (directiveLike) continue;
if (!known.contains(operand)) {
known.add(operand);
found.add(new VirtualSheet(operand, null, true));
}
}
}
rowIdx++;
}
return found;
}


public static List<String> splitTopLevelByComma(String s) {
List<String> out = new ArrayList<>();
int depth = 0, start = 0;
for (int i = 0; i < s.length(); i++) {
char c = s.charAt(i);
if (c == '(') depth++;
else if (c == ')') depth = Math.max(0, depth - 1);
else if (c == ',' && depth == 0) {
out.add(s.substring(start, i).trim());
start = i + 1;
}
}
out.add(s.substring(start).trim());
return out;
}




private static void routeControlSheet(ParsedWorkbook.Builder b, Sheet sheet, String name) {
if (CONTROL_SHEET_NAMES.contains(name)) {
b.stringSheetHM.put(name, sheet);
if (name.equals("FW_RunMeFirstOnce")) {
validateRunMeFirstOnce(sheet);
}
}
}

private static void validateRunMeFirstOnce(Sheet sheet) {
String val = sheet.iterator().next().cellIterator().next().getStringCellValue();
if (val == null || val.isEmpty()) return;
if (!val.matches("(?s).*class\\s+?RunMeFirstOnce\\s*?.*")
|| !val.matches("(?s).*public\\s+?static\\s+?String\\s+?FW_ARGS.*")
|| !val.matches("(?s).*FW_ARGS\\s*?=.*")) {
log.warn("FW_RunMeFirstOnce cell does not match the expected RunMeFirstOnce class pattern.");
}
}




public static void parseCellValues(ParsedWorkbook.Builder b,
Sheet[] allSheets,
DataFormatter dataFormatter) {

File   currentCsvFile = null;
File   currentFile    = null;

Map<Short, Long> duplicatedCellValueHM = new LinkedHashMap<>();
Map<String, Integer> sheetNameToExitCodeMap = new LinkedHashMap<>();
Set<String> sheetNameExitCodeSeen = new LinkedHashSet<>();

var kvService = new KeyValueService();
var exitCodeService = new SheetFW_EXIT_CODEService();
var strRefiner = new StringButQuotesRefiner();

// [Keys] labels come from the DataTypeDispatcher plan (legacy numbering S+1.. whenever it
// fits); keyCounter[0] keeps holding "the key issued last" exactly as before.
final DataTypeDispatcher.Plan keyPlan = (b.keyPlan != null) ? b.keyPlan
: DataTypeDispatcher.dispatch(allSheets, b.stringSheetHM.get("FW_Seq"), null);
final DataTypeDispatcher.KeyLabeler labeler = keyPlan.newLabeler();
short[] keyCounter = { (short) (keyPlan.firstLabel - 1) };

for (var sheet : allSheets) {

if (sheet.getSheetName().startsWith("FW_")) continue;

String      curSheetName         = sheet.getSheetName();
Short       curSheetKey          = b.name2key.get(curSheetName);
List<Short> lstK2cellV = new ArrayList<>();
int         fwExitPerSheetCounter = 0;

currentCsvFile = null;
currentFile    = null;

log.debug("Parsing sheet '{}'", curSheetName);

for (var row : sheet) {

log.trace("Sheet '{}' row {}", curSheetName, row.getRowNum());

for (var cell : row) {


String cellValue = dataFormatter.formatCellValue(cell);
log.trace("  col={} val='{}'", cell.getColumnIndex(), cellValue);


if (cell.getCellType() == CellType.FORMULA) {
String formulaText = cell.getCellFormula();
log.info("Formula detected at row {}, col {}. Writing formula text to collection: '{}'",
row.getRowNum(), cell.getColumnIndex(), formulaText);
System.out.println(CodeLineNumber.getLineNumber()+" [Y Warning]: Excel-Formula detected and being written as text to Collection");
keyCounter[0] = labeler.next();
b.shortStringCellValueHM.put(keyCounter[0], formulaText);
NumberToValue1 nvFormula = buildNumberToValue(keyCounter[0], formulaText);
kvService.addKV(nvFormula);
lstK2cellV.add(nvFormula.getKey());
}
else {



if (isFwDirectiveCell(cellValue)) {

if (cellValue.startsWith("FW_CSVFile=")) {
currentCsvFile = new File(cellValue.replaceFirst("FW_CSVFile=", ""));

log.debug("[{}] csvFile='{}'", CodeLineNumber.getLineNumber(), currentCsvFile);

} else if (cellValue.startsWith("FW_File=")) {
currentFile = new File(cellValue.replaceFirst("FW_File=", ""));

log.debug("[{}] file='{}'", CodeLineNumber.getLineNumber(), currentFile);
if (currentFile != null) {
String content = ReadFileToString.stringFromFile(currentFile.getPath());
keyCounter[0] = labeler.next();
b.shortStringCellValueHM.put(keyCounter[0], content);
NumberToValue1 nv = buildNumberToValue(keyCounter[0], content);
kvService.addKV(nv);
lstK2cellV.add(nv.getKey());
log.info("FW_File read: '{}'", currentFile.getPath());
} else {

log.warn("[{}] file == null for: '{}'", CodeLineNumber.getLineNumber(), cellValue);
}

} else if (cellValue.startsWith("FW_BinaryFile=")
|| cellValue.startsWith("FW_DBURL=")
|| cellValue.startsWith("FW_DBUSER=")
|| cellValue.startsWith("FW_DBPASS=")
|| cellValue.startsWith("FW_SQL=")) {

log.warn("[{}] STUB (not yet implemented): '{}'",
CodeLineNumber.getLineNumber(), cellValue);

} else if (cellValue.startsWith("FW_Separator=")) {
if (currentCsvFile != null) {
new CSVDataMapper(currentCsvFile,
cellValue.replaceFirst("FW_Separator=", "")).readCSV();
} else {

log.warn("[{}] csvFile == null for: '{}'",
CodeLineNumber.getLineNumber(), cellValue);
}

} else if (cellValue.startsWith("FW_Optional")) {
NumberToValue1 nv = kvService.getKV(keyCounter[0]);
nv.setOptional(true);
kvService.updateKV(nv);

} else if (cellValue.startsWith("FW_RefineCodeExceptQuoted")) {
NumberToValue1 nv = kvService.getKV(keyCounter[0]);
nv.setValue(strRefiner.shrinkManySpacedStringExceptAnyQuoted(
strRefiner.removeNewLines(
strRefiner.removeCommentsFromMultipleLinedString(nv.getValue()))));
nv.setRefined(true);
kvService.updateKV(nv);

} else if (cellValue.startsWith("FW_EMPTY_STRING")) {
keyCounter[0] = labeler.next();
b.shortStringCellValueHM.put(keyCounter[0], "");
NumberToValue1 nv = buildNumberToValue(keyCounter[0], "");
kvService.addKV(nv);
lstK2cellV.add(nv.getKey());

} else {

log.warn("[{}] Not implemented FW_ directive: '{}'",
CodeLineNumber.getLineNumber(), cellValue);
}


} else if (isFwVarExitCode(cellValue)) {
keyCounter[0] = labeler.next();
String resolved = cellValue.replaceAll("FW_EXIT_CODE",
String.valueOf(b.name2key.get(curSheetName)));
b.shortStringCellValueHM.put(keyCounter[0], resolved);
NumberToValue1 nv = buildNumberToValue(keyCounter[0], resolved);
kvService.addKV(nv);
lstK2cellV.add(nv.getKey());

sheetNameToExitCodeMap.put(curSheetName, (int) keyCounter[0]);
fwExitPerSheetCounter++;

var rec = new SheetFW_EXIT_CODE();
rec.setSheet(curSheetName);
rec.setFW_EXIT_CODE(b.name2key.get(curSheetName).intValue());
rec.setFW_VAR_and_FW_EXIT_CODEperSheetCounter(fwExitPerSheetCounter);
if (sheetNameExitCodeSeen.add(curSheetName)) {
exitCodeService.addSheetFW_EXIT_CODE(rec);
} else {
exitCodeService.updateSheetFW_EXIT_CODE(rec);
}


} else {
if (b.shortStringCellValueHM.containsValue(cellValue)) {


log.warn("[{}] Duplicate cell '{}' in sheet '{}'",
CodeLineNumber.getLineNumber(), cellValue, curSheetName);
for (Map.Entry<Short, String> e : b.shortStringCellValueHM.entrySet()) {
if (e.getValue().equals(cellValue)) {
duplicatedCellValueHM.merge(e.getKey(), 1L, Long::sum);
log.debug("  duplicatedCellValueHM: {}", duplicatedCellValueHM);
}
}
}
keyCounter[0] = labeler.next();
b.shortStringCellValueHM.put(keyCounter[0], cellValue);
NumberToValue1 nv = buildNumberToValue(keyCounter[0], cellValue);
kvService.addKV(nv);
lstK2cellV.add(nv.getKey());
}


if (cellValue.matches("(?s).*?\\s+?FW_CUSTOM_VAR\\s*?=\\s*?\\d{1,}.*?"
+ "|^\\s{0,}FW_CUSTOM_VAR\\s*?=\\s*?\\d{1,}.*?")) {

log.warn("STUB: FW_CUSTOM_VAR detected in sheet '{}'", curSheetName);
}
if (cellValue.contains("FW_PATH_FILES_TO")) {

log.info("FW_PATH_FILES_TO detected in sheet '{}'", curSheetName);
}
}
}


log.trace("  --- end of row {} in sheet '{}'", row.getRowNum(), curSheetName);
}

if (!b.shortStringCellValueHM.isEmpty() && curSheetKey != null) {
b.shortIntSheetK2idxListOfCellK_HM.put(curSheetKey, new ArrayList<>(lstK2cellV));
b.sheetData.put(curSheetKey, new ArrayList<>(lstK2cellV));
b.shortStringCellValueHM.clear();
}


log.debug("\\ Current sheet '{}' iteration ended // — {} cell keys collected",
curSheetName, lstK2cellV.size());
}

if (!labeler.exhausted()) {
throw new IllegalStateException("DataTypeDispatcher census mismatch: counted " + keyPlan.cells
+ " keys but the parse issued " + labeler.issued()
+ " — WorkbookParser.keysConsumedBy and parseCellValues have diverged");
}
// Sheet-key line: virtual (auto-registered) sheets continue after the last cell key exactly
// as before; only when that would overflow a short do they start right after the real sheets.
b.maxSheetNumber = (short) keyPlan.virtualKeyBase();
}



private static boolean isFwDirectiveCell(String cellValue) {
return cellValue.startsWith("FW_")
&& !cellValue.startsWith("FW_EXIT_CODE")
&& !cellValue.startsWith("FW_VAR")
&& !cellValue.startsWith("FW_CUSTOM_VAR");
}

/**
 * How many keys {@link #parseCellValues} issues for this cell — the single predicate the
 * {@link DataTypeDispatcher} census and the parser share.  A formula always issues one; so
 * does every non-string cell (numbers, booleans, blanks and errors never format to text that
 * starts with {@code FW_}); a string issues one unless it is an {@code FW_} directive that
 * materialises no value (only {@code FW_File=} and {@code FW_EMPTY_STRING} do).
 */
static int keysConsumedBy(Cell cell) {
if (cell.getCellType() != CellType.STRING) return 1;
return keysConsumedBy(cell.getStringCellValue());
}

static int keysConsumedBy(String cellValue) {
if (isFwDirectiveCell(cellValue)) {
return (cellValue.startsWith("FW_File=") || cellValue.startsWith("FW_EMPTY_STRING")) ? 1 : 0;
}
return 1;
}

private static boolean isFwVarExitCode(String cellValue) {
return cellValue.contains("FW_VAR")
&& cellValue.contains("FW_EXIT_CODE")
&& cellValue.matches("(?s).*?\\s+?FW_VAR\\s*?=\\s*?FW_EXIT_CODE.*?"
+ "|^\\s{0,}FW_VAR\\s*?=\\s*?FW_EXIT_CODE.*?");
}

private static NumberToValue1 buildNumberToValue(short key, String value) {
var nv = new NumberToValue1();
nv.setKey(key);
nv.setValue(value);
return nv;
}
}
