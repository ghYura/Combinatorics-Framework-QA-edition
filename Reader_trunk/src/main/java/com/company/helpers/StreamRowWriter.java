package com.company.helpers;
import com.company.ReaderConfig;

import com.company.daoModelService.SheetNameService;

import java.io.IOException;
import java.io.OutputStream;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;


/**
 * perf 2026-07-02 rewrite (output byte-for-byte identical to the previous version):
 *  - ONE reusable grow-only row buffer per writer instance instead of a fresh 64KB
 *    UnsynchronizedByteArrayOutputStream per row (the class is single-threaded by design);
 *  - the label -> sheet-key normalisation (a regex replaceFirst) is computed once per
 *    column index and cached — it used to compile/run per column per row;
 *  - the trailing-separator trim and the combo-id marker splice write straight out of
 *    the buffer (the old code did toByteArray() copies per row for both).
 */
public final class StreamRowWriter {

@FunctionalInterface
public interface CodeBytesResolver {
byte[] resolve(short code);
}

private static final byte[] MARKER = "FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE".getBytes();

private final Map<String, byte[]> sheetNameMapByteArr;
private final Map<String, byte[]> sheetNameMapEndingByteArr;
private final byte[] FW_B_ARR;
private final int FW_B_ARR_LENGTH;
private final boolean replaceComboId;

/** colIdx -> normalised sheet key; the label set is constant for the writer's stream. */
private final Map<Integer, String> sheetKeyByColIdx = new HashMap<>();

/** Reusable row buffer (single-threaded use per instance, matching the class contract). */
private byte[] buf = new byte[64 * 1024];
private int count = 0;

public StreamRowWriter() {

SheetNameService sheetNameService = new SheetNameService();
this.sheetNameMapByteArr = new java.util.LinkedHashMap<>();
this.sheetNameMapEndingByteArr = new java.util.LinkedHashMap<>();
sheetNameService.getListOfSheetNames().forEach(e -> sheetNameMapByteArr.put(e.getSheet(), e.getName().getBytes()));
sheetNameService.getListOfSheetNames().forEach(e -> sheetNameMapEndingByteArr.put(e.getSheet(), e.getEnding().getBytes()));

this.FW_B_ARR = (ReaderConfig.FW_B_ARR == null) ? new byte[]{} : ReaderConfig.FW_B_ARR;
this.FW_B_ARR_LENGTH = (ReaderConfig.FW_B_ARR == null) ? 0 : ReaderConfig.FW_B_ARR_LENGTH;
this.replaceComboId = ReaderConfig.fw_replace_me_with_current_combo_sequence_mode;
}


private static String normalizeSheetKey(String dbColumnLabel) {
return dbColumnLabel == null ? "" : dbColumnLabel.replaceFirst("(?i)combos(\\d){1,}_", "");
}

private String sheetKeyFor(int colIdx, Map<Integer, String> labelByIndex) {
String cached = sheetKeyByColIdx.get(colIdx);
if (cached != null) return cached;
String label = (labelByIndex == null) ? null : labelByIndex.get(colIdx);
String key = normalizeSheetKey(label);
sheetKeyByColIdx.put(colIdx, key);
return key;
}

private void ensureCapacity(int add) {
int need = count + add;
if (need <= buf.length) return;
int n = buf.length;
while (n < need) n = Math.min(n * 2, n + 8 * 1024 * 1024);
byte[] nb = new byte[n];
System.arraycopy(buf, 0, nb, 0, count);
buf = nb;
}

private void put(byte[] b) {
ensureCapacity(b.length);
System.arraycopy(b, 0, buf, count, b.length);
count += b.length;
}

/** Assemble one row into the reusable buffer; returns the trailing-separator length of the last field. */
private int assemble(Map<Integer, String> labelByIndex,
LinkedHashMap<Integer, short[]> cols,
CodeBytesResolver resolver) {
count = 0;
int lastFieldSepLen = 0;
for (Map.Entry<Integer, short[]> e : cols.entrySet()) {
final int colIdx = e.getKey();
final short[] codes = e.getValue();
final String sheetKey = sheetKeyFor(colIdx, labelByIndex);


byte[] sheetPrefix = (sheetKey != null && sheetNameMapByteArr.containsKey(sheetKey))
? sheetNameMapByteArr.get(sheetKey) : null;
if (sheetPrefix != null) {
put(sheetPrefix);
}


if (codes != null) {
for (short code : codes) {
if (code != CopyToReader.NULL_ELEMENT) {
byte[] b = resolver.resolve(code);
if (b != null && b.length > 0) {
put(b);
}
}
}
}


if (FW_B_ARR_LENGTH > 0) {
put(FW_B_ARR);
lastFieldSepLen = FW_B_ARR_LENGTH;
} else if (sheetKey != null && sheetNameMapEndingByteArr.containsKey(sheetKey)) {
byte[] end = sheetNameMapEndingByteArr.get(sheetKey);
put(end);
lastFieldSepLen = end.length;
} else {
lastFieldSepLen = 0;
}
}
return lastFieldSepLen;
}

/** Trim + (first-occurrence) marker splice + write — straight from the buffer, no copies. */
private void finishRow(byte[] idBytes, OutputStream out) throws IOException {
int n = count;
// legacy trim: drop the last field's separator if the buffer is at least that long
// (matches the old `lastFieldSepLen > 0 && size >= lastFieldSepLen` reset+rewrite)
// n already adjusted by caller before invoking this method.

if (idBytes != null) {
int idx = indexOf(buf, n, MARKER);
if (idx >= 0) {
out.write(buf, 0, idx);
out.write(idBytes);
out.write(buf, idx + MARKER.length, n - (idx + MARKER.length));
return;
}
}

out.write(buf, 0, n);
}


public void writeOneRow(long id,
Map<Integer, String> labelByIndex,
LinkedHashMap<Integer, short[]> cols,
OutputStream out,
CodeBytesResolver resolver) throws IOException {

int lastFieldSepLen = assemble(labelByIndex, cols, resolver);
if (lastFieldSepLen > 0 && count >= lastFieldSepLen) {
count -= lastFieldSepLen;
}
finishRow(replaceComboId ? Long.toString(id).getBytes() : null, out);
}

private static int indexOf(byte[] data, int len, byte[] pattern) {
if (pattern.length == 0) return 0;
outer: for (int i = 0; i <= len - pattern.length; i++) {
for (int j = 0; j < pattern.length; j++) {
if (data[i + j] != pattern[j]) continue outer;
}
return i;
}
return -1;
}


public void writeOneRowWithComboString(String comboId,
Map<Integer, String> labelByIndex,
LinkedHashMap<Integer, short[]> cols,
OutputStream out,
CodeBytesResolver resolver) throws IOException {

int lastFieldSepLen = assemble(labelByIndex, cols, resolver);
if (lastFieldSepLen > 0 && count >= lastFieldSepLen) {
count -= lastFieldSepLen;
}
finishRow((replaceComboId && comboId != null) ? comboId.getBytes() : null, out);
}
}
