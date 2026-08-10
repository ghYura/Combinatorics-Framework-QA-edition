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

import com.company.excel.Numerator;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

import java.io.IOException;
import java.io.OutputStream;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;


public final class CopyToReader {

private CopyToReader() {}


private static final int OID_INT2 = 21;

    /** C4: short[] cannot hold null; this reserved value stands in for a null array element (SQL NULL / non-2-byte). */
    public static final short NULL_ELEMENT = Short.MIN_VALUE;

private static final byte[] EXPECTED_SIG = new byte[] {
'P', 'G', 'C', 'O', 'P', 'Y', '\n', (byte) 0xFF, '\r', '\n', 0
};


public static void stream(String selectSql, RowConsumer consumer) throws SQLException {
final String inner = stripTrailingSemicolon(selectSql);
final String copySql = "COPY (" + inner + ") TO STDOUT (FORMAT BINARY)";
final long t0 = System.nanoTime();
final BinaryDecoderSink sink = new BinaryDecoderSink(consumer);
try (Connection c = DataBaseManager2.getInstance().getConnection()) {
CopyManager cm = c.unwrap(PGConnection.class).getCopyAPI();
long handled = cm.copyOut(copySql, sink);
sink.flushPending();

System.out.println("        [COPY-BINARY] rows=" + handled
+ "  decodedRows=" + sink.rowsEmitted()
+ "  elapsed_ms=" + ((System.nanoTime() - t0) / 1_000_000L)
+ "  sql=" + truncate(inner, 140));
} catch (IOException ioe) {
throw new SQLException("COPY TO binary parse failure", ioe);
}
}


public static void streamWithLabels(String selectSql, LabeledRowConsumer consumer) throws SQLException {
final List<String> names = describeSelect(selectSql);
final Map<Integer, String> labels = new TreeMap<>();
for (int i = 2; i <= names.size(); i++) labels.put(i, names.get(i - 1));
stream(selectSql, (id, cols) -> consumer.onRow(id, cols, labels));
}


public static LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> loadAsMapMap(String selectSql) throws SQLException {
final LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> out = new LinkedHashMap<>();
stream(selectSql, out::put);
return out;
}


public static LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> loadAsMapMapAndCaptureSeed(String selectSql) throws SQLException {
final List<String> colNames = describeSelect(selectSql);
final LinkedHashMap<String, Object> seed = new LinkedHashMap<>(colNames.size());
final LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> out = new LinkedHashMap<>();
final boolean[] firstSeen = { false };

stream(selectSql, (id, cols) -> {
if (!firstSeen[0]) {
if (!colNames.isEmpty()) {
seed.put(colNames.get(0), Long.valueOf(id));
}
for (int i = 2; i <= colNames.size(); i++) {
seed.put(colNames.get(i - 1), cols.get(i));
}
Numerator.columnNamesFirstRowStaticHM = seed;
firstSeen[0] = true;
}
out.put(id, cols);
});

if (!firstSeen[0]) {
for (String n : colNames) seed.put(n, null);
Numerator.columnNamesFirstRowStaticHM = seed;
}
return out;
}


public static List<String> describeSelect(String selectSql) throws SQLException {
final String preview = stripTrailingSemicolon(selectSql) + " LIMIT 0";
try (Connection c = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = c.prepareStatement(preview);
ResultSet rs = ps.executeQuery()) {
ResultSetMetaData md = rs.getMetaData();
int n = md.getColumnCount();
List<String> names = new ArrayList<>(n);
for (int i = 1; i <= n; i++) names.add(md.getColumnLabel(i));
return names;
}
}

private static String stripTrailingSemicolon(String s) {
return s == null ? "" : s.replaceFirst(";\\s*$", "");
}

private static String truncate(String s, int max) {
if (s == null) return "";
return s.length() <= max ? s : s.substring(0, max) + "…";
}


private static final class BinaryDecoderSink extends OutputStream {
private final RowConsumer consumer;
private byte[] buf = new byte[256 * 1024];
private int writePos = 0;
private int readPos = 0;
private boolean headerSeen = false;
private boolean trailerSeen = false;
private long rowsEmitted = 0L;

BinaryDecoderSink(RowConsumer consumer) {
this.consumer = consumer;
}

long rowsEmitted() { return rowsEmitted; }

void flushPending() throws IOException {


}

@Override public void write(int b) throws IOException {
ensureSpace(1);
buf[writePos++] = (byte) b;
decodeAvailable();
compactIfNeeded();
}

@Override public void write(byte[] b, int off, int len) throws IOException {
if (len <= 0) return;
ensureSpace(len);
System.arraycopy(b, off, buf, writePos, len);
writePos += len;
decodeAvailable();
compactIfNeeded();
}

private int available() { return writePos - readPos; }

private void ensureSpace(int n) {
if (writePos + n <= buf.length) return;

if (readPos > 0) {
int live = writePos - readPos;
System.arraycopy(buf, readPos, buf, 0, live);
writePos = live;
readPos = 0;
if (writePos + n <= buf.length) return;
}
int newSize = buf.length;
while (newSize < writePos + n) {
newSize = Math.min(newSize * 2, newSize + 32 * 1024 * 1024);
}
byte[] nb = new byte[newSize];
System.arraycopy(buf, 0, nb, 0, writePos);
buf = nb;
}

private void compactIfNeeded() {

if (readPos >= 64 * 1024) {
int live = writePos - readPos;
System.arraycopy(buf, readPos, buf, 0, live);
writePos = live;
readPos = 0;
}
}

private void decodeAvailable() throws IOException {
if (trailerSeen) return;


if (!headerSeen) {
if (available() < 19) return;
for (int i = 0; i < EXPECTED_SIG.length; i++) {
if (buf[readPos + i] != EXPECTED_SIG[i]) {
throw new IOException("invalid COPY BINARY signature at offset " + i
+ " (got 0x" + Integer.toHexString(buf[readPos + i] & 0xFF) + ")");
}
}
int extLen = peekIntAt(readPos + 15);
if (extLen < 0) throw new IOException("negative COPY BINARY ext_len: " + extLen);
if (available() < 19 + extLen) return;
readPos += 19 + extLen;
headerSeen = true;
}


while (true) {
final int rowStart = readPos;
if (available() < 2) return;
short fieldCount = readShort();
if (fieldCount == -1) {
trailerSeen = true;
return;
}

long id = 0L;
// perf 2026-07-02: presize for the known column count (avoids per-row rehash growth)
LinkedHashMap<Integer, short[]> cols = new LinkedHashMap<>(Math.max(16, (int) (fieldCount / 0.75f) + 1));
boolean rowComplete = true;
for (int i = 1; i <= fieldCount; i++) {
if (available() < 4) { readPos = rowStart; return; }
int len = readInt();
if (len < 0) {

continue;
}
if (available() < len) {
readPos = rowStart;
rowComplete = false;
break;
}
if (i == 1) {
if (len != 8) throw new IOException("expected bigint(8) for column 1, got len=" + len);
id = readLong();
} else {
// perf 2026-07-02: decode in place from the stream buffer — the old per-column
// byte[] payload copy doubled the allocation volume of the whole COPY decode.
short[] arr = decodeSmallintArrayPayload(buf, readPos, len);
readPos += len;
if (arr != null) cols.put(i, arr);
}
}
if (!rowComplete) return;

try {
consumer.onRow(id, cols);
} catch (IOException ioe) {
throw ioe;
} catch (Exception ex) {
throw new IOException("row consumer failed at id=" + id, ex);
}
rowsEmitted++;
}
}

private short readShort() {
int hi = buf[readPos++] & 0xFF;
int lo = buf[readPos++] & 0xFF;
return (short) ((hi << 8) | lo);
}

private int readInt() {
int b0 = buf[readPos++] & 0xFF;
int b1 = buf[readPos++] & 0xFF;
int b2 = buf[readPos++] & 0xFF;
int b3 = buf[readPos++] & 0xFF;
return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}

private long readLong() {
long hi = readInt() & 0xFFFFFFFFL;
long lo = readInt() & 0xFFFFFFFFL;
return (hi << 32) | lo;
}

private void readBytes(byte[] dst) {
System.arraycopy(buf, readPos, dst, 0, dst.length);
readPos += dst.length;
}

private int peekIntAt(int idx) {
return ((buf[idx] & 0xFF) << 24)
| ((buf[idx + 1] & 0xFF) << 16)
| ((buf[idx + 2] & 0xFF) << 8)
| (buf[idx + 3] & 0xFF);
}
}


// perf 2026-07-02: in-place variant — decodes the array payload directly from the
// stream buffer at [off, off+len) with no intermediate copy. Same wire semantics as
// the old byte[]-payload version (kept below for any external callers).
private static short[] decodeSmallintArrayPayload(byte[] a, int off, int len) throws IOException {
if (len < 12) return null;
final int end = off + len;
int p = off;
int ndim   = readIntFromArray(a, p); p += 4;
  readIntFromArray(a, p); p += 4;
int elemOid = readIntFromArray(a, p); p += 4;
if (elemOid != OID_INT2) {
throw new IOException("unsupported array element OID " + elemOid + " (expected int2/smallint)");
}
if (ndim <= 0) return new short[0];

long totalLen = 1L;
for (int d = 0; d < ndim; d++) {
if (p + 8 > end) throw new IOException("truncated array dim header");
int dimLen = readIntFromArray(a, p); p += 4;
 p += 4;
totalLen *= dimLen;
}
if (totalLen < 0 || totalLen > Integer.MAX_VALUE) {
throw new IOException("smallint[] array length out of range: " + totalLen);
}
final int n = (int) totalLen;
final short[] out = new short[n];
for (int i = 0; i < n; i++) {
if (p + 4 > end) throw new IOException("truncated array element length");
int elen = readIntFromArray(a, p); p += 4;
if (elen < 0) {
out[i] = NULL_ELEMENT;
} else if (elen == 2) {
if (p + 2 > end) throw new IOException("truncated int2 element");
int hi = a[p] & 0xFF;
int lo = a[p + 1] & 0xFF;
out[i] = (short) ((hi << 8) | lo);
p += 2;
} else {

if (p + elen > end) throw new IOException("truncated array element data");
p += elen;
out[i] = NULL_ELEMENT;
}
}
return out;
}

private static short[] decodeSmallintArrayPayload(byte[] payload) throws IOException {
return decodeSmallintArrayPayload(payload, 0, payload.length);
}

private static int readIntFromArray(byte[] a, int off) {
return ((a[off] & 0xFF) << 24)
| ((a[off + 1] & 0xFF) << 16)
| ((a[off + 2] & 0xFF) << 8)
| (a[off + 3] & 0xFF);
}
}
