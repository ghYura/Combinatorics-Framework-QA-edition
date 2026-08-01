package com.company.file;

import com.company.daoModelService.KeyValueService;
import com.company.models.NumberToValue1;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.*;
import java.util.ArrayList;
import java.util.List;


public class FileDataMapper {

private static final Logger log = LogManager.getLogger(FileDataMapper.class);

private static final String DEFAULT_FILE_PATH = System.getenv().getOrDefault("FRAMEWORK_INPUT_TEXT", "input.txt");
private static final String DEFAULT_SPLIT_BY  = "\n";

private final File   fFile;
private final String fileSplitBy;

public FileDataMapper() {
this.fFile       = new File(DEFAULT_FILE_PATH);
this.fileSplitBy = DEFAULT_SPLIT_BY;
}

public FileDataMapper(File fFile, String fileSplitBy) {
this.fFile       = fFile;
this.fileSplitBy = fileSplitBy;
}


public void readFileY(short[] keyCounter, List<Short> outCellKeyList) {
var kvService = new KeyValueService();


List<NumberToValue1> batch = new ArrayList<>(500);
String line;

try (BufferedReader br = new BufferedReader(new FileReader(fFile))) {
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
log.error("File not found: '{}'", fFile.getPath(), e);
} catch (IOException e) {
log.error("I/O error reading '{}': {}", fFile.getPath(), e.getMessage(), e);
}

log.info("File '{}' read: {} entries", fFile.getName(), outCellKeyList.size());
}


@Deprecated
public void readFileY() {
log.warn("FileDataMapper.readFileY() called without state injection — migrate to readFileY(short[], List<Short>).");
short[] stub = {0}; List<Short> out = new ArrayList<>();
readFileY(stub, out);
}
}
