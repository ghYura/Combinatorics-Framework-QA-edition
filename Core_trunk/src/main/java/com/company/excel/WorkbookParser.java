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
String virtualName = wbCfg.virtualSheetNamePrefix + (rowIdx + 1);
int suffix = 1;
while (b.name2key.containsKey(virtualName)) {
suffix++;
virtualName = wbCfg.virtualSheetNamePrefix + (rowIdx + 1) + "_" + suffix;
}
short k = b.registerVirtualSheet(virtualName);
b.fwSeqRowSyntheticTarget.put(rowIdx, k);
log.info("[Issue1] preScanFwSeq: headless row {} → synthesised target '{}' (key={})",
rowIdx, virtualName, k);
} else if (!b.name2key.containsKey(firstVal)) {


short k = b.registerVirtualSheet(firstVal);
log.info("[Issue1] preScanFwSeq: column-0 missing sheet '{}' → virtual key={}", firstVal, k);
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
if (!b.name2key.containsKey(operand)) {
short k = b.registerVirtualSheet(operand);
log.info("[Issue1] preScanFwSeq: FW_(...) operand '{}' missing → virtual key={}", operand, k);
}
}
}
rowIdx++;
}
log.info("[Issue1] preScanFwSeq complete: {} virtual sheets registered, {} headless rows synthesised",
b.virtualSheetNames.size(), b.fwSeqRowSyntheticTarget.size());
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

short[] keyCounter = { b.maxSheetNumber };

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
keyCounter[0]++;
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
keyCounter[0]++;
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
keyCounter[0]++;
b.shortStringCellValueHM.put(keyCounter[0], "");
NumberToValue1 nv = buildNumberToValue(keyCounter[0], "");
kvService.addKV(nv);
lstK2cellV.add(nv.getKey());

} else {

log.warn("[{}] Not implemented FW_ directive: '{}'",
CodeLineNumber.getLineNumber(), cellValue);
}


} else if (isFwVarExitCode(cellValue)) {
keyCounter[0]++;
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
keyCounter[0]++;
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

b.maxSheetNumber = keyCounter[0];
}



private static boolean isFwDirectiveCell(String cellValue) {
return cellValue.startsWith("FW_")
&& !cellValue.startsWith("FW_EXIT_CODE")
&& !cellValue.startsWith("FW_VAR")
&& !cellValue.startsWith("FW_CUSTOM_VAR");
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
