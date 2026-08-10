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

import com.company.PrintPretty;
import com.company.StringButQuotesRefiner;
import com.company.daoModelService.KeyValueService;
import com.company.daoModelService.SheetFW_EXIT_CODEService;
import com.company.file.CSVDataMapper;
import com.company.file.ReadFileToString;
import com.company.helpers.CodeLineNumber;
import com.company.models.NumberToValue1;
import com.company.models.SheetFW_EXIT_CODE;
import org.apache.poi.openxml4j.exceptions.InvalidFormatException;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.ss.usermodel.WorkbookFactory;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;


import static com.company.excel.Numerator.*;

public class ExcelDataMapper {

public static Map<Short, List<Short>> processExcel(String SAMPLE_XLSX_FILE_PATH) throws IOException, InvalidFormatException {

List<Map<Short, String>> listOfMaps;
Sheet[] sheets;
try (Workbook workbook = WorkbookFactory.create(new File(SAMPLE_XLSX_FILE_PATH))) {

PrintPretty.println(PrintPretty.Color.BLACK, "____\n" + "class '" + ExcelDataMapper.class.getName() + "' " + CodeLineNumber.getLineNumber() + ":\t" + "Workbook has " + workbook.getNumberOfSheets() + " Sheets : ");
PrintPretty.println(PrintPretty.Color.BLACK, "____\n" + "class '" + ExcelDataMapper.class.getName() + "' " + CodeLineNumber.getLineNumber() + ":\t" + "Retrieving Sheets using Java 8 forEach with lambda...");
workbook.forEach(sheet -> {
System.out.println("=> " + sheet.getSheetName());
if (sheet.getSheetName().startsWith("FW_")) ++Numerator.numOfFW_Sheets;
switch (sheet.getSheetName()) {
case "FW_Seq":
Numerator.stringSheetHM.put("FW_Seq", sheet);
break;
case "FW_Info":
Numerator.stringSheetHM.put("FW_Info", sheet);
break;
case "FW_SheetNames":
Numerator.stringSheetHM.put("FW_SheetNames", sheet);
break;
case "FW_CUSTOM_VAR":
Numerator.stringSheetHM.put("FW_CUSTOM_VAR", sheet);
break;
case "FW_RunMeFirstOnce":  {
String verifyRunMeFirstOnce__FW_ARGS = sheet.iterator().next().cellIterator().next().getStringCellValue();
if (verifyRunMeFirstOnce__FW_ARGS != null && !verifyRunMeFirstOnce__FW_ARGS.equals("")) {
if (!verifyRunMeFirstOnce__FW_ARGS.matches("(?s).*class\\s+?RunMeFirstOnce\\s*?.*") ||
!verifyRunMeFirstOnce__FW_ARGS.matches("(?s).*public\\s+?static\\s+?String\\s+?FW_ARGS.*") ||
!verifyRunMeFirstOnce__FW_ARGS.matches("(?s).*FW_ARGS\\s*?=.*")) {
try {
throw new Exception(
"____\n" + "class '" + ExcelDataMapper.class.getName() + "' " + CodeLineNumber.getLineNumber() + ":\t" +
" WARNING!: Cell of sheet 'FW_RunMeFirstOnce' does NOT contain following Regular Expressions:\n" +
"class\\s+?RunMeFirstOnce\\s*?\nor\n" +
"public\\s+?static\\s+?String\\s+?FW_ARGS;\nor\n" +
"FW_ARGS\\s*?="
+ "\nActual:\n$$\n" + verifyRunMeFirstOnce__FW_ARGS.toString() + "\n$$\n"
);
} catch (Exception e) {
e.printStackTrace();
}
}
;
}
Numerator.stringSheetHM.put("FW_RunMeFirstOnce", sheet);
}
break;
case "FW_Arguments":
Numerator.stringSheetHM.put("FW_Arguments", sheet);
break;
case "FW_Complex":
Numerator.stringSheetHM.put("FW_Complex", sheet);
break;
case "FW_Combi":
Numerator.stringSheetHM.put("FW_Combi", sheet);
break;
case "FW_CombiR":
Numerator.stringSheetHM.put("FW_CombiR", sheet);
break;
case "FW_Permut":
Numerator.stringSheetHM.put("FW_Permut", sheet);
break;
case "FW_PermutR":
Numerator.stringSheetHM.put("FW_PermutR", sheet);
break;
case "FW_Subsets":
Numerator.stringSheetHM.put("FW_Subsets", sheet);
break;
case "FW_Cartes":
Numerator.stringSheetHM.put("FW_Cartes", sheet);
break;
default: {

Numerator.shortSheetHM.put(++Numerator.shortSheetNumber, sheet);
Numerator.shortStringSheetKey2SheetNameHM.put(Numerator.shortSheetNumber, sheet.getSheetName());

Numerator.stringShortSheetName2SheetKeyHM.put(sheet.getSheetName(), Numerator.shortSheetNumber);
}
}
});
listOfMaps = new ArrayList<>(workbook.getNumberOfSheets() - Numerator.numOfFW_Sheets);

sheets = new Sheet[workbook.getNumberOfSheets()];
for (int i = 0; i < sheets.length; i++) {
sheets[i] = workbook.getSheetAt(i);
}
}
PrintPretty.println(PrintPretty.Color.GREEN, "____\n" + "class '" + ExcelDataMapper.class.getName() + "' " + CodeLineNumber.getLineNumber() + ":\t" + "Retrieving Sheets using Java 8 forEach with lambda... Done.");

DataFormatter dataFormatter = new DataFormatter();
PrintPretty.println(PrintPretty.Color.BLACK_BOLD, "____\n"+"class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber()+":\t"+"Mapping .xlsx-cells to java-based maps...\n");

for (Sheet sheet : sheets) {
FW_VAR_and_FW_EXIT_CODEperSheetCounter = 0;
Numerator.curSheetName = sheet.getSheetName();
Numerator.curSheetKey = Numerator.stringShortSheetName2SheetKeyHM.get(Numerator.curSheetName);
List<Short> lstK2cellV = new ArrayList<>();


sheet.forEach(row -> {
PrintPretty.print(PrintPretty.Color.BLACK_UNDERLINED, "ROW: ");
row.forEach(cell -> {
PrintPretty.print(PrintPretty.Color.BLACK_UNDERLINED, "Cell: ");
String cellValue = dataFormatter.formatCellValue(cell);
System.out.print(cellValue + "\t");
if ( !sheet.getSheetName().startsWith("FW_")) {
if (cellValue.startsWith("FW_") && !cellValue.startsWith("FW_EXIT_CODE") && !cellValue.startsWith("FW_VAR") && !cellValue.startsWith("FW_CUSTOM_VAR")){


if (cellValue.startsWith("FW_CSVFile=")){


Numerator.csvFile = new File(cellValue.replaceFirst("FW_CSVFile=", ""));
PrintPretty.println(PrintPretty.Color.CYAN_BACKGROUND, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " csvFile.toString() = " + Numerator.csvFile.toString());

} else if (cellValue.startsWith("FW_File=")){

Numerator.file = new File(cellValue.replaceFirst("FW_File=", ""));
PrintPretty.println(PrintPretty.Color.CYAN_BACKGROUND, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " file.toString() = " + Numerator.file.toString());
if (Numerator.file != null){





String fileContentAsString = ReadFileToString.stringFromFile(Numerator.file.getPath());

Numerator.shortSheetNumber = (short)(Numerator.shortSheetNumber + 1);
Numerator.shortStringCellValueHM.put(Numerator.shortSheetNumber, fileContentAsString);

NumberToValue1 numberToValue1 = new NumberToValue1();
numberToValue1.setKey(Numerator.shortSheetNumber);
numberToValue1.setValue(Numerator.shortStringCellValueHM.get(Numerator.shortSheetNumber));
KeyValueService kvService = new KeyValueService();
kvService.addKV(numberToValue1);

lstK2cellV.add(numberToValue1.getKey());
System.out.println("File read done for: "+ Numerator.file.getPath());


} else {
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " file == null, " + cellValue);
}

} else if (cellValue.startsWith("FW_BinaryFile=")) {
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " STUB: cell starts with 'FW_BinaryFile=' " + cellValue);
} else if (cellValue.startsWith("FW_DBURL=")){
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " STUB: cell starts with 'FW_DBURL=' " + cellValue);
} else if (cellValue.startsWith("FW_DBUSER=")){
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " STUB: cell starts with 'FW_DBUSER=' " + cellValue);
} else if (cellValue.startsWith("FW_DBPASS=")){
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " STUB: cell starts with 'FW_DBPASS=' " + cellValue);
} else if (cellValue.startsWith("FW_SQL=")){
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " STUB: cell starts with 'FW_SQL=' " + cellValue);
} else if (cellValue.startsWith("FW_Separator=")){
if (Numerator.csvFile != null){
CSVDataMapper CSVclassDataMapper = new CSVDataMapper(Numerator.csvFile, cellValue.replaceFirst("FW_Separator=", ""));
CSVclassDataMapper.readCSV();
} else {
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " csvFile == null, " + cellValue);
}
} else if (cellValue.startsWith("FW_Optional")){
KeyValueService kvService = new KeyValueService();
NumberToValue1 numberToValue1 = kvService.getKV(Numerator.shortSheetNumber);
numberToValue1.setOptional(true);
kvService.updateKV(numberToValue1);

} else if (cellValue.startsWith("FW_RefineCodeExceptQuoted")){

KeyValueService kvService = new KeyValueService();
NumberToValue1 numberToValue1 = kvService.getKV(Numerator.shortSheetNumber);
StringButQuotesRefiner strRefinery = new StringButQuotesRefiner();
numberToValue1.setValue(strRefinery.shrinkManySpacedStringExceptAnyQuoted(strRefinery.removeNewLines(strRefinery.removeCommentsFromMultipleLinedString(numberToValue1.getValue()))));
numberToValue1.setRefined(true);
kvService.updateKV(numberToValue1);
strRefinery = null;
} else if (cellValue.startsWith("FW_EMPTY_STRING")){
Numerator.shortSheetNumber = (short)(Numerator.shortSheetNumber + 1);
Numerator.shortStringCellValueHM.put(Numerator.shortSheetNumber, "");

NumberToValue1 numberToValue1 = new NumberToValue1();
numberToValue1.setKey(Numerator.shortSheetNumber);
numberToValue1.setValue(Numerator.shortStringCellValueHM.get(Numerator.shortSheetNumber));
KeyValueService kvService = new KeyValueService();
kvService.addKV(numberToValue1);

lstK2cellV.add(numberToValue1.getKey());

} else {
PrintPretty.println(PrintPretty.Color.RED, "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " Not implemented or Unsupported value ='" + cellValue + "'");
}

} else if (cellValue.contains("FW_VAR") && cellValue.contains("FW_EXIT_CODE") && cellValue.matches("(?s).*?\\s+?FW_VAR\\s*?=\\s*?FW_EXIT_CODE.*?|^\\s{0,}FW_VAR\\s*?=\\s*?FW_EXIT_CODE.*?")){
Numerator.shortSheetNumber = (short)(Numerator.shortSheetNumber + 1);
Numerator.shortStringCellValueHM.put(Numerator.shortSheetNumber, cellValue.replaceAll("FW_EXIT_CODE", String.valueOf(Numerator.stringShortSheetName2SheetKeyHM.get(sheet.getSheetName()))));

NumberToValue1 numberToValue1 = new NumberToValue1();
numberToValue1.setKey(Numerator.shortSheetNumber);
numberToValue1.setValue(Numerator.shortStringCellValueHM.get(Numerator.shortSheetNumber));
KeyValueService kvService = new KeyValueService();
kvService.addKV(numberToValue1);

lstK2cellV.add(numberToValue1.getKey());
stringSheetNameContainsFW_VAR_and_FW_EXIT_CODEMap.put(sheet.getSheetName(), (int) Numerator.shortSheetNumber);
++FW_VAR_and_FW_EXIT_CODEperSheetCounter;

SheetFW_EXIT_CODE sheetFWExitCode = new SheetFW_EXIT_CODE();
sheetFWExitCode.setSheet(sheet.getSheetName());
sheetFWExitCode.setFW_EXIT_CODE(Numerator.stringShortSheetName2SheetKeyHM.get(sheet.getSheetName()).intValue());
SheetFW_EXIT_CODEService sheetFWExitCodeService = new SheetFW_EXIT_CODEService();
if (stringSheetNameContainsFW_VAR_and_FW_EXIT_CODESet.add(sheet.getSheetName())) sheetFWExitCodeService.addSheetFW_EXIT_CODE(sheetFWExitCode);
sheetFWExitCode.setFW_VAR_and_FW_EXIT_CODEperSheetCounter(FW_VAR_and_FW_EXIT_CODEperSheetCounter);
if (!stringSheetNameContainsFW_VAR_and_FW_EXIT_CODESet.add(sheet.getSheetName())) sheetFWExitCodeService.updateSheetFW_EXIT_CODE(sheetFWExitCode);






} else {
if (Numerator.shortStringCellValueHM.containsValue(cellValue)) {
PrintPretty.println(PrintPretty.Color.RED, "[" + "class '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + "][i]\n Duplicate cell '"+ cellValue + "' loop-search in(!) java's KV-map(!): Sheet: " + sheet.getSheetName() + ", Cell: " + cellValue + " \n[/i]");
for (Map.Entry<Short, String> entry : Numerator.shortStringCellValueHM.entrySet()) {
if (entry.getValue().equals(cellValue)) {

if (Numerator.shortShortDuplicatedCellValueHM.get(entry.getKey()) == null) Numerator.shortShortDuplicatedCellValueHM.put(entry.getKey(), (short)1);
Numerator.shortShortDuplicatedCellValueHM.put(entry.getKey(), (short)(Numerator.shortShortDuplicatedCellValueHM.get(entry.getKey())+1));
PrintPretty.println(PrintPretty.Color.CYAN, Numerator.shortShortDuplicatedCellValueHM.toString());
}
}

Numerator.shortSheetNumber = (short)(Numerator.shortSheetNumber + 1);
Numerator.shortStringCellValueHM.put(Numerator.shortSheetNumber, cellValue);

NumberToValue1 numberToValue1 = new NumberToValue1();
numberToValue1.setKey(Numerator.shortSheetNumber);
numberToValue1.setValue(Numerator.shortStringCellValueHM.get(Numerator.shortSheetNumber));
KeyValueService kvService = new KeyValueService();
kvService.addKV(numberToValue1);

lstK2cellV.add(numberToValue1.getKey());

} else {
Numerator.shortSheetNumber = (short)(Numerator.shortSheetNumber + 1);
Numerator.shortStringCellValueHM.put(Numerator.shortSheetNumber, cellValue);

NumberToValue1 numberToValue1 = new NumberToValue1();
numberToValue1.setKey(Numerator.shortSheetNumber);
numberToValue1.setValue(Numerator.shortStringCellValueHM.get(Numerator.shortSheetNumber));
KeyValueService kvService = new KeyValueService();
kvService.addKV(numberToValue1);

lstK2cellV.add(numberToValue1.getKey());
}
}

if (cellValue.contains("FW_CUSTOM_VAR") && cellValue.matches("(?s).*?\\s+?FW_CUSTOM_VAR\\s*?=\\s*?\\d{1,}.*?|^\\s{0,}FW_CUSTOM_VAR\\s*?=\\s*?\\d{1,}.*?")) {
PrintPretty.println(PrintPretty.Color.RED, "STUB: class '" + ExcelDataMapper.class.getName() + "' " + CodeLineNumber.getLineNumber() + " FW_CUSTOM_VAR cell value detected =\n$$\n" + cellValue + "\n$$\n");
}
if (cellValue.contains("FW_PATH_FILES_TO")){
PrintPretty.println(PrintPretty.Color.ORANGE, "\nDetected 'FW_PATH_FILES_TO'-value cell for further processing by Reader.\nDetails and actual value substitution and refine in DB, please, see Reader (fw.properties) \nclass '"+ ExcelDataMapper.class.getName() +"' "+ CodeLineNumber.getLineNumber() + " cell 'FW_PATH_FILES_TO'-value detected =\n$$\n" + cellValue + "\n$$\n");
}

}
});
System.out.println();
});

if (!Numerator.shortStringCellValueHM.isEmpty()){

Map<Short, String> longStringCellValueHMlocal = new LinkedHashMap<>(Numerator.shortStringCellValueHM);
listOfMaps.add(longStringCellValueHMlocal);
for (Map.Entry<Short, String> entry : Numerator.shortStringSheetKey2SheetNameHM.entrySet()) {
if (entry.getValue().equals(sheet.getSheetName())){
Numerator.curSheetKey = entry.getKey();
Numerator.shortIntegerSheetKey2idxListOfMapsHM.put(Numerator.curSheetKey, listOfMaps.indexOf(longStringCellValueHMlocal));
listOfMaps.clear();
Numerator.shortIntSheetK2idxListOfCellK_HM.put(Numerator.curSheetKey, (List<Short>) ((ArrayList<Short>) lstK2cellV).clone());
lstK2cellV.clear();
}
} shortStringCellValueHMList.add(new LinkedHashMap<>(shortStringCellValueHM));
Numerator.shortStringCellValueHM.clear();

}
if (true) PrintPretty.println(PrintPretty.Color.GREEN_BOLD, "\033[4m" + "\\ Current sheet '" + sheet.getSheetName() + "' iteration ended /" + "==============");
else PrintPretty.println("" + "\\ Current sheet '" + sheet.getSheetName() + "' iteration ended /" + "==============");
}

return Numerator.shortIntSheetK2idxListOfCellK_HM;
}
}
