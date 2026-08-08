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

package com.company.file;

import com.company.daoModelService.KeyValueService;
import com.company.models.NumberToValue1;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.*;
import java.util.ArrayList;
import java.util.List;


public class CSVDataMapper {

private static final Logger log = LogManager.getLogger(CSVDataMapper.class);

private static final String DEFAULT_CSV_PATH = System.getenv().getOrDefault("FRAMEWORK_INPUT_CSV", "input.csv");
private static final String DEFAULT_SPLIT_BY = ";";

private final File   csvFile;
private final String csvSplitBy;

public CSVDataMapper() {
this.csvFile    = new File(DEFAULT_CSV_PATH);
this.csvSplitBy = DEFAULT_SPLIT_BY;
}

public CSVDataMapper(File csvFile, String csvSplitBy) {
this.csvFile    = csvFile;
this.csvSplitBy = csvSplitBy;
}


public void readCSV(short[] keyCounter, List<Short> outCellKeyList) {
var kvService = new KeyValueService();

List<NumberToValue1> batch = new ArrayList<>(500);
String line;

try (BufferedReader br = new BufferedReader(new FileReader(csvFile))) {
while ((line = br.readLine()) != null) {
var kv = new NumberToValue1();
kv.setKey(++keyCounter[0]);
kv.setValue(line);
batch.add(kv);
outCellKeyList.add(kv.getKey());

if (batch.size() == 500) {
kvService.addLotsKV(batch);
batch.clear();
}
}
if (!batch.isEmpty()) {
kvService.addLotsKV(batch);
}
} catch (FileNotFoundException e) {
log.error("CSV file not found: '{}'", csvFile.getPath(), e);
} catch (IOException e) {
log.error("I/O error reading CSV '{}': {}", csvFile.getPath(), e.getMessage(), e);
}


log.info("CSV '{}' read: {} entries", csvFile.getName(), outCellKeyList.size());
}


@Deprecated
public void readCSV() {
log.warn("CSVDataMapper.readCSV() called without state injection — Numerator coupling not resolved. "
+ "Migrate caller to use readCSV(short[], List<Short>).");

short[] stubCounter = {0};
List<Short> stubList = new ArrayList<>();
readCSV(stubCounter, stubList);
}
}
