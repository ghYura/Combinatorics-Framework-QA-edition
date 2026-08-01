package com.company.io;

import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/**
 * Extracted from the Main god-class on 2026-05-30 (behaviour-preserving Extract-Class).
 * SRP: the Reader's per-row byte-OUTPUT strategy zoo (direct-append, async-ordered, two-phase
 * chunk+merge, buffered, producer/consumer, mmap append-log / atomic-record). Verified to
 * reference NO Main state. Public (used by Main): DirectAppendOutputStream, ProducerConsumerIO,
 * ByteCache; the rest are internal collaborators.
 */
public final class ReaderIoStreams {
    private ReaderIoStreams() {}

private static final class ParallelDirectAppender {
private final java.nio.channels.FileChannel ch;
private final java.util.concurrent.atomic.AtomicLong pos;
private final java.util.concurrent.ExecutorService ioPool;
private final java.util.concurrent.ScheduledExecutorService fsync;

ParallelDirectAppender(String path, boolean append) throws java.io.IOException {
java.nio.file.Path p = java.nio.file.Paths.get(path);
java.util.Set<java.nio.file.OpenOption> opts = new java.util.HashSet<>();
opts.add(java.nio.file.StandardOpenOption.CREATE);
opts.add(java.nio.file.StandardOpenOption.WRITE);
opts.add(java.nio.file.StandardOpenOption.READ);
this.ch = java.nio.channels.FileChannel.open(p, opts);
long start = (append && java.nio.file.Files.exists(p)) ? ch.size() : 0L;
if (!append) {
ch.truncate(0L);
start = 0L;
}
this.pos = new java.util.concurrent.atomic.AtomicLong(start);
int cores = Math.max(2, java.lang.Runtime.getRuntime().availableProcessors());
int threads = Math.min(8, Math.max(2, cores));
this.ioPool = java.util.concurrent.Executors.newFixedThreadPool(threads, r -> {
Thread t = new Thread(r, "pdirect-io");
t.setDaemon(true);
return t;
});
this.fsync = java.util.concurrent.Executors.newSingleThreadScheduledExecutor(r -> {
Thread t = new Thread(r, "pdirect-fsync");
t.setDaemon(true);
return t;
});
this.fsync.scheduleAtFixedRate(() -> {
try {
ch.force(false);
} catch (Exception _) {
}
}, 200, 200, java.util.concurrent.TimeUnit.MILLISECONDS);
}

long reserve(int len) {
return pos.getAndAdd(len);
}

void writeAt(long off, byte[] b, int boff, int blen) throws java.io.IOException {
final java.nio.ByteBuffer bb = java.nio.ByteBuffer.wrap(b, boff, blen);
ioPool.submit(() -> {
try {
long written = 0L;
while (written < blen) {
int n = ch.write(bb, off + written);
if (n < 0) throw new java.io.EOFException("write failed");
written += n;
}
} catch (Exception e) {
e.printStackTrace();
}
});
}









long reserveAndWriteSync(byte[] b, int boff, int blen) throws java.io.IOException {
if (blen <= 0) return pos.get();
long start = pos.getAndAdd(blen);
java.nio.ByteBuffer bb = java.nio.ByteBuffer.wrap(b, boff, blen);
long written = 0L;
while (written < blen) {
int n = ch.write(bb, start + written);
if (n < 0) throw new java.io.EOFException("write failed");
written += n;
}
return start;
}

void close() {
try {
ioPool.shutdown();
try {
ioPool.awaitTermination(365, java.util.concurrent.TimeUnit.DAYS);
} catch (InterruptedException ie) {
Thread.currentThread().interrupt();
}
} catch (Exception _) {
}
try {
fsync.shutdownNow();
} catch (Exception _) {
}
try {
ch.force(false);
} catch (Exception _) {
}
try {
ch.close();
} catch (Exception _) {
}
}
}

public static final class DirectAppendOutputStream extends java.io.OutputStream {
private final ParallelDirectAppender app;
private final byte NL = (byte) 0x0A;
private byte[] buf = new byte[128 * 1024];
private int count = 0;
private volatile boolean closed = false;

private DirectAppendOutputStream(ParallelDirectAppender app) {
this.app = app;
}

static java.io.OutputStream open(String path, boolean append) {
try {
return new DirectAppendOutputStream(new ParallelDirectAppender(path, append));
} catch (java.io.IOException e) {
throw new RuntimeException(e);
}
}

@Override
public void write(int b) throws java.io.IOException {
ensureOpen();
if (count >= buf.length) grow(count + 1);
buf[count++] = (byte) b;
if (b == NL) flushLine();
}

@Override
public void write(byte[] b, int off, int len) throws java.io.IOException {
ensureOpen();
int i = off, end = off + len, start = i;
while (i < end) {
if (b[i] == NL) {
appendToBuf(b, start, i - start + 1);
flushLine();
i++;
start = i;
} else i++;
}
if (start < end) appendToBuf(b, start, end - start);
}

private void appendToBuf(byte[] b, int off, int len) {
if (count + len > buf.length) grow(count + len);
System.arraycopy(b, off, buf, count, len);
count += len;
}

private void grow(int minCap) {
int n = buf.length;
while (n < minCap) n = Math.min(n * 2, n + 8 * 1024 * 1024);
byte[] nb = new byte[n];
System.arraycopy(buf, 0, nb, 0, count);
buf = nb;
}

private void flushLine() throws java.io.IOException {
if (count == 0) return;
final int len = count;
final byte[] line = java.util.Arrays.copyOf(buf, len);
count = 0;
long off = app.reserve(len);
app.writeAt(off, line, 0, len);
}

@Override
public void flush() throws java.io.IOException {
ensureOpen();
if (count > 0) flushLine();
}

@Override
public void close() throws java.io.IOException {
if (closed) return;
try {
flush();
} finally {
closed = true;
app.close();
}
}

private void ensureOpen() throws java.io.IOException {
if (closed) throw new java.io.IOException("closed");
}





public void appendAtomic(byte[] b, int off, int len) throws java.io.IOException {
ensureOpen();
app.reserveAndWriteSync(b, off, len);
}
}


public static final class ByteCache {
private static final java.util.concurrent.ConcurrentHashMap<Short, byte[]> CACHE = new java.util.concurrent.ConcurrentHashMap<>();

public static byte[] getOrCompute(java.util.concurrent.ConcurrentHashMap<Short, java.io.ByteArrayOutputStream> src, short key) {
return CACHE.computeIfAbsent(key, k -> {
java.io.ByteArrayOutputStream baos = src.get(k);
if (baos == null) return new byte[0];
return baos.toByteArray();
});
}
}


private static final class AsyncOrderedOutputStream extends java.io.OutputStream {
private final java.io.OutputStream delegate;
private final java.util.concurrent.ExecutorService pool;
private final java.util.concurrent.ConcurrentHashMap<Long, byte[]> done = new java.util.concurrent.ConcurrentHashMap<>();
private final java.util.concurrent.atomic.AtomicLong seq = new java.util.concurrent.atomic.AtomicLong(0);
private final byte NL = (byte) 0x0A;
private volatile long next = 0;
private byte[] buf = new byte[128 * 1024];
private int count = 0;
private volatile boolean closed = false;

private AsyncOrderedOutputStream(java.io.OutputStream delegate, int parallelism) {
this.delegate = delegate;
this.pool = java.util.concurrent.Executors.newFixedThreadPool(parallelism);
}

static java.io.OutputStream wrap(java.io.OutputStream delegate) {
int cores = Math.max(2, Runtime.getRuntime().availableProcessors());
return new AsyncOrderedOutputStream(delegate, cores);
}

@Override
public void write(int b) throws java.io.IOException {
ensureOpen();
if (count >= buf.length) grow(count + 1);
buf[count++] = (byte) b;
if (b == NL) flushLineAsync();
}

@Override
public void write(byte[] b, int off, int len) throws java.io.IOException {
ensureOpen();
int i = off, end = off + len, start = i;
while (i < end) {
if (b[i] == NL) {
appendToBuf(b, start, i - start + 1);
flushLineAsync();
i++;
start = i;
} else i++;
}
if (start < end) appendToBuf(b, start, end - start);
}

@Override
public void flush() throws java.io.IOException {
ensureOpen();
if (count > 0) flushLineAsync();
drainInOrder(true);
delegate.flush();
}

@Override
public void close() throws java.io.IOException {
if (closed) return;
try {
flush();
pool.shutdown();
try {
pool.awaitTermination(365, java.util.concurrent.TimeUnit.DAYS);
} catch (InterruptedException ie) {
Thread.currentThread().interrupt();
}
} finally {
closed = true;
delegate.close();
}
}

private void appendToBuf(byte[] b, int off, int len) {
if (count + len > buf.length) grow(count + len);
System.arraycopy(b, off, buf, count, len);
count += len;
}

private void grow(int minCap) {
int n = buf.length;
while (n < minCap) n = Math.min(n * 2, n + 8 * 1024 * 1024);
byte[] nb = new byte[n];
System.arraycopy(buf, 0, nb, 0, count);
buf = nb;
}

private void flushLineAsync() throws java.io.IOException {
if (count == 0) return;
final long id = seq.getAndIncrement();
final byte[] line = java.util.Arrays.copyOf(buf, count);
count = 0;
pool.submit(() -> {
done.put(id, line);
try {
drainInOrder(false);
} catch (Exception _) {
}
});
}

private void drainInOrder(boolean blocking) throws java.io.IOException {
while (true) {
byte[] line = done.remove(next);
if (line == null) {
if (!blocking) break;
try {
Thread.sleep(1);
} catch (InterruptedException ie) {
Thread.currentThread().interrupt();
}
continue;
}
delegate.write(line, 0, line.length);
next++;
}
}

private void ensureOpen() throws java.io.IOException {
if (closed) throw new java.io.IOException("closed");
}
}




private static final class TwoPhaseOutput {
private static final java.util.concurrent.atomic.AtomicLong SEQ = new java.util.concurrent.atomic.AtomicLong(0L);
private static final java.util.concurrent.atomic.AtomicInteger CHUNK_ID = new java.util.concurrent.atomic.AtomicInteger(0);
private static final byte NL = (byte) 0x0A;

static java.io.OutputStream open(String finalPath, boolean append) {
return new TwoPhaseRecordStream(finalPath, append);
}


private static final class TwoPhaseRecordStream extends java.io.OutputStream {
private final String finalPath;
private final boolean append;
private final java.nio.file.Path partsDir;
private final ThreadLocal<RecordBuilder> local = ThreadLocal.withInitial(() -> new RecordBuilder());
private volatile boolean closed = false;

TwoPhaseRecordStream(String finalPath, boolean append) {
this.finalPath = finalPath;
this.append = append;
this.partsDir = java.nio.file.Paths.get(finalPath + ".parts");
try {
java.nio.file.Files.createDirectories(partsDir);
} catch (java.io.IOException _) {
}
}

@Override
public void write(int b) throws java.io.IOException {
ensureOpen();
RecordBuilder rb = local.get();
rb.put((byte) b);
if (b == NL) rb.flushLine(finalPath, partsDir);
}

@Override
public void write(byte[] b, int off, int len) throws java.io.IOException {
ensureOpen();
int i = off, end = off + len, start = i;
RecordBuilder rb = local.get();
while (i < end) {
if (b[i] == NL) {
rb.put(b, start, i - start + 1);
rb.flushLine(finalPath, partsDir);
i++;
start = i;
} else i++;
}
if (start < end) rb.put(b, start, end - start);
}

@Override
public void flush() throws java.io.IOException {
ensureOpen();
local.get().flushTail(finalPath, partsDir);
}

@Override
public void close() throws java.io.IOException {
if (closed) return;
closed = true;
try {
flush();
} catch (Exception _) {
}


TwoPhaseMerger.merge(finalPath, partsDir, append);

try (java.util.stream.Stream<java.nio.file.Path> s = java.nio.file.Files.list(partsDir)) {
s.forEach(p -> {
try {
java.nio.file.Files.deleteIfExists(p);
} catch (Exception _) {
}
});
} catch (Exception _) {
}
try {
java.nio.file.Files.deleteIfExists(partsDir);
} catch (Exception _) {
}
}

private void ensureOpen() throws java.io.IOException {
if (closed) throw new java.io.IOException("closed");
}

private static final class RecordBuilder {
private byte[] buf = new byte[64 * 1024];
private int count = 0;
private ChunkWriterDirect cw = null;

void put(byte b) {
ensureCapacity(1);
buf[count++] = b;
}

void put(byte[] b, int off, int len) {
if (len <= 0) return;
ensureCapacity(len);
System.arraycopy(b, off, buf, count, len);
count += len;
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

void flushLine(String finalPath, java.nio.file.Path partsDir) throws java.io.IOException {
if (count == 0) return;
if (cw == null) cw = ChunkWriterDirect.forThread(finalPath, partsDir, CHUNK_ID.incrementAndGet());
long seq = SEQ.getAndIncrement();
cw.writeRecord(seq, buf, 0, count);
count = 0;
}

void flushTail(String finalPath, java.nio.file.Path partsDir) throws java.io.IOException {
if (count == 0) return;
if (cw == null) cw = ChunkWriterDirect.forThread(finalPath, partsDir, CHUNK_ID.incrementAndGet());
long seq = SEQ.getAndIncrement();
cw.writeRecord(seq, buf, 0, count);
count = 0;
}
}
}
}


private static final class ChunkWriterDirect {
private final java.nio.channels.FileChannel dataCh;
private final java.io.DataOutputStream idxOut;
private long offset = 0L;

private ChunkWriterDirect(java.nio.channels.FileChannel dataCh, java.io.DataOutputStream idxOut) {
this.dataCh = dataCh;
this.idxOut = idxOut;
}

static ChunkWriterDirect forThread(String finalPath, java.nio.file.Path partsDir, int id) throws java.io.IOException {
String base = java.nio.file.Paths.get(finalPath).getFileName().toString();
String suf = ".part-" + id + "-" + java.lang.Thread.currentThread().getId();
java.nio.file.Path dataP = partsDir.resolve(base + suf + ".data");
java.nio.file.Path indexP = partsDir.resolve(base + suf + ".index");
java.nio.channels.FileChannel ch = java.nio.channels.FileChannel.open(
dataP,
java.nio.file.StandardOpenOption.CREATE,
java.nio.file.StandardOpenOption.WRITE,
java.nio.file.StandardOpenOption.TRUNCATE_EXISTING
);
java.io.DataOutputStream idx = new java.io.DataOutputStream(
new java.io.BufferedOutputStream(
java.nio.file.Files.newOutputStream(indexP, java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.WRITE, java.nio.file.StandardOpenOption.TRUNCATE_EXISTING),
1 << 20
)
);
return new ChunkWriterDirect(ch, idx);
}

void writeRecord(long seq, byte[] b, int off, int len) throws java.io.IOException {

java.nio.ByteBuffer bb = java.nio.ByteBuffer.wrap(b, off, len);
while (bb.hasRemaining()) dataCh.write(bb);

idxOut.writeLong(seq);
idxOut.writeLong(offset);
idxOut.writeInt(len);
offset += len;
}

void close() throws java.io.IOException {
try {
idxOut.flush();
idxOut.close();
} catch (Exception _) {
}
try {
dataCh.force(false);
dataCh.close();
} catch (Exception _) {
}
}
}


private static final class TwoPhaseMerger {
static void merge(String finalPath, java.nio.file.Path partsDir, boolean append) throws java.io.IOException {
java.util.List<java.nio.file.Path> idxFiles;
try (java.util.stream.Stream<java.nio.file.Path> s = java.nio.file.Files.list(partsDir)) {
idxFiles = s.filter(p -> p.getFileName().toString().endsWith(".index")).sorted().toList();
}
if (idxFiles.isEmpty()) return;

java.util.ArrayList<Reader> readers = new java.util.ArrayList<>();
java.util.PriorityQueue<Entry> pq = new java.util.PriorityQueue<>(java.util.Comparator.comparingLong(e -> e.seq));
try {
int i = 0;
for (java.nio.file.Path ip : idxFiles) {
String base = ip.getFileName().toString();
String dataName = base.substring(0, base.length() - ".index".length()) + ".data";
java.nio.file.Path dp = ip.getParent().resolve(dataName);
java.nio.channels.FileChannel dch = java.nio.channels.FileChannel.open(dp, java.nio.file.StandardOpenOption.READ);
java.io.DataInputStream dis = new java.io.DataInputStream(new java.io.BufferedInputStream(java.nio.file.Files.newInputStream(ip), 1 << 20));
Reader r = new Reader(dch, dis);
readers.add(r);
Entry e = r.next(i);
if (e != null) pq.add(e);
i++;
}
java.nio.file.Path finalP = java.nio.file.Paths.get(finalPath);
java.util.Set<java.nio.file.OpenOption> opts = new java.util.HashSet<>();
opts.add(java.nio.file.StandardOpenOption.CREATE);
opts.add(java.nio.file.StandardOpenOption.WRITE);
if (!append) opts.add(java.nio.file.StandardOpenOption.TRUNCATE_EXISTING);
try (java.nio.channels.FileChannel out = java.nio.channels.FileChannel.open(finalP, opts)) {
long pos = append && java.nio.file.Files.exists(finalP) ? out.size() : 0L;
if (append && pos > 0) out.position(pos);
while (!pq.isEmpty()) {
Entry e = pq.poll();
java.nio.channels.FileChannel src = readers.get(e.idx).dataCh;
long transferred = 0L;
long srcPos = e.off;
while (transferred < e.len) {
long n = out.transferFrom(src, pos + transferred, e.len - transferred);
if (n == 0) {
src.position(srcPos + transferred);
n = out.transferFrom(src, pos + transferred, e.len - transferred);
if (n == 0) break;
}
transferred += n;
}
pos += e.len;
Entry next = readers.get(e.idx).next(e.idx);
if (next != null) pq.add(next);
}
out.force(false);
}
} finally {
for (Reader r : readers) r.close();
}
}

private static final class Entry {
final int idx;
final long seq;
final long off;
final int len;

Entry(int idx, long seq, long off, int len) {
this.idx = idx;
this.seq = seq;
this.off = off;
this.len = len;
}
}

private static final class Reader {
final java.nio.channels.FileChannel dataCh;
final java.io.DataInputStream idxIn;

Reader(java.nio.channels.FileChannel dataCh, java.io.DataInputStream idxIn) {
this.dataCh = dataCh;
this.idxIn = idxIn;
}

Entry next(int idx) throws java.io.IOException {
try {
long seq = idxIn.readLong();
long off = idxIn.readLong();
int len = idxIn.readInt();
return new Entry(idx, seq, off, len);
} catch (java.io.EOFException eof) {
return null;
}
}

void close() {
try {
idxIn.close();
} catch (Exception _) {
}
try {
dataCh.close();
} catch (Exception _) {
}
}
}
}




private static final class FastBufferedOutputStream extends java.io.FilterOutputStream {
private final byte[] buf;
private final java.util.concurrent.ScheduledExecutorService flusher;
private final long flushMillis;
private int count = 0;
private volatile boolean closed = false;

FastBufferedOutputStream(OutputStream out, int bufferSize, long flushMillis) {
super(out);
if (bufferSize <= 0) throw new IllegalArgumentException("bufferSize must be > 0");
if (flushMillis <= 0) throw new IllegalArgumentException("flushMillis must be > 0");
this.buf = new byte[bufferSize];
this.flushMillis = flushMillis;
this.flusher = java.util.concurrent.Executors.newSingleThreadScheduledExecutor(r -> {
Thread t = new Thread(r, "fast-buf-flusher");
t.setDaemon(true);
return t;
});
this.flusher.scheduleAtFixedRate(() -> {
try {
this.flush();
} catch (IOException _) {
}
}, this.flushMillis, this.flushMillis, java.util.concurrent.TimeUnit.MILLISECONDS);
}

@Override
public synchronized void write(int b) throws IOException {
ensureOpen();
if (count >= buf.length) {
drain();
}
buf[count++] = (byte) b;
}

@Override
public synchronized void write(byte[] b, int off, int len) throws IOException {
ensureOpen();
if (len >= buf.length) {

drain();
out.write(b, off, len);
return;
}
if (len > buf.length - count) {
drain();
}
System.arraycopy(b, off, buf, count, len);
count += len;
}

private void drain() throws IOException {
if (count > 0) {
out.write(buf, 0, count);
count = 0;
}
}

private void ensureOpen() throws IOException {
if (closed) throw new IOException("Stream closed");
}

@Override
public synchronized void flush() throws IOException {
if (closed) return;
drain();
out.flush();
}

@Override
public synchronized void close() throws IOException {
if (closed) return;
closed = true;
try {
this.flusher.shutdownNow();
} catch (Exception _) {
}
try {
flush();
} finally {
out.close();
}
}
}

public static final class ProducerConsumerIO {
private static volatile ProducerConsumerIO.Writer INSTANCE;

public static java.io.OutputStream getOrStart(String path, boolean append) {
Writer inst = INSTANCE;
if (inst == null || !java.util.Objects.equals(inst.path, path)) {
synchronized (ProducerConsumerIO.class) {
inst = INSTANCE;
if (inst != null) {
inst.close();
}
java.io.OutputStream os = DirectAppendOutputStream.open(path, append);
INSTANCE = inst = new Writer(path, os);
}
}
return inst.os;
}

public static void finish() {
Writer inst;
synchronized (ProducerConsumerIO.class) {
inst = INSTANCE;
INSTANCE = null;
}
if (inst != null) inst.close();
}

private static final class Writer {
final String path;
final java.io.OutputStream os;

Writer(String path, java.io.OutputStream os) {
this.path = path;
this.os = os;
}

void close() {
try {
os.flush();
os.close();
} catch (Exception _) {
}
}
}
}




private static final class AppendOnlyMMapLog {
private static final int SEGMENT_SIZE = 64 * 1024 * 1024;
private static volatile AppendOnlyMMapLog INSTANCE;
private final String path;
private final java.nio.channels.FileChannel ch;
private final java.util.ArrayList<java.nio.MappedByteBuffer> segments = new java.util.ArrayList<>();
private final java.util.concurrent.atomic.AtomicLong writePos = new java.util.concurrent.atomic.AtomicLong(0L);
private final java.util.concurrent.atomic.AtomicInteger refCount = new java.util.concurrent.atomic.AtomicInteger(0);
private final java.util.concurrent.ScheduledExecutorService fsync = java.util.concurrent.Executors.newSingleThreadScheduledExecutor(r -> {
Thread t = new Thread(r, "mmap-fsync");
t.setDaemon(true);
return t;
});

private AppendOnlyMMapLog(String path, boolean append) throws java.io.IOException {
this.path = path;
java.nio.file.Path p = java.nio.file.Paths.get(path);
java.util.Set<java.nio.file.OpenOption> opts = new java.util.HashSet<>();
opts.add(java.nio.file.StandardOpenOption.CREATE);
opts.add(java.nio.file.StandardOpenOption.WRITE);
opts.add(java.nio.file.StandardOpenOption.READ);
this.ch = java.nio.channels.FileChannel.open(p, opts);
long size = append ? java.nio.file.Files.exists(p) ? java.nio.file.Files.size(p) : 0L : 0L;
if (!append) {
this.ch.truncate(0L);
size = 0L;
}
mapUpTo(size == 0 ? SEGMENT_SIZE : size);
this.writePos.set(size);

this.fsync.scheduleAtFixedRate(() -> {
try {
synchronized (segments) {
if (!segments.isEmpty()) segments.get(segments.size() - 1).force();
}
} catch (Throwable _) {
}
}, 200, 200, java.util.concurrent.TimeUnit.MILLISECONDS);
}

static synchronized AppendOnlyMMapLog getOrOpen(String path, boolean append) {
try {
if (INSTANCE == null || !INSTANCE.path.equals(path)) {
if (INSTANCE != null) {
INSTANCE.close();
}
INSTANCE = new AppendOnlyMMapLog(path, append);
}
return INSTANCE;
} catch (java.io.IOException e) {
throw new RuntimeException(e);
}
}

static OutputStream openStream(String path, boolean append) {
AppendOnlyMMapLog log = getOrOpen(path, append);
log.refCount.incrementAndGet();
return new MMapOutputStream(log);
}

private void mapUpTo(long targetSize) throws java.io.IOException {
long needed = targetSize;
long current = (long) segments.size() * SEGMENT_SIZE;
while (current < needed) {
long newSize = current + SEGMENT_SIZE;
ch.truncate(newSize);
java.nio.MappedByteBuffer mbb = ch.map(java.nio.channels.FileChannel.MapMode.READ_WRITE, current, SEGMENT_SIZE);
segments.add(mbb);
current = newSize;
}
}

void append(byte[] b, int off, int len) throws java.io.IOException {
if (len <= 0) return;
long pos = writePos.getAndAdd(len);
long end = pos + len;
if (end > (long) segments.size() * SEGMENT_SIZE) {
synchronized (segments) {
if (end > (long) segments.size() * SEGMENT_SIZE) {
mapUpTo(end);
}
}
}

int remaining = len;
int srcOff = off;
long p = pos;
while (remaining > 0) {
int segIdx = (int) (p / SEGMENT_SIZE);
int segOff = (int) (p % SEGMENT_SIZE);
int can = Math.min(remaining, SEGMENT_SIZE - segOff);
java.nio.MappedByteBuffer mbb;
synchronized (segments) {
mbb = segments.get(segIdx);
}
java.nio.ByteBuffer dup = mbb.duplicate();
dup.position(segOff).limit(segOff + can);
dup.put(b, srcOff, can);
p += can;
srcOff += can;
remaining -= can;
}
}

void releaseRef() {
if (refCount.decrementAndGet() == 0) {
close();
}
}

synchronized void close() {
try {
fsync.shutdownNow();
} catch (Exception _) {
}
try {
synchronized (segments) {
if (!segments.isEmpty()) segments.get(segments.size() - 1).force();
}
} catch (Throwable _) {
}
try {
ch.close();
} catch (Exception _) {
}
}
}

private static final class MMapOutputStream extends OutputStream {
private final AppendOnlyMMapLog log;
private byte[] buf = new byte[64 * 1024];
private int count = 0;
private boolean closed = false;

MMapOutputStream(AppendOnlyMMapLog log) {
this.log = log;
}


static OutputStream open(String path, boolean append) {
return AppendOnlyMMapLog.openStream(path, append);
}

@Override
public void write(int b) throws java.io.IOException {
ensureOpen();
if (count >= buf.length) flush();
buf[count++] = (byte) b;
}

@Override
public void write(byte[] b, int off, int len) throws java.io.IOException {
ensureOpen();
if (len >= 32 * 1024) {
flush();

log.append(b, off, len);
} else {
if (len > buf.length - count) flush();
System.arraycopy(b, off, buf, count, len);
count += len;
}
}

@Override
public void flush() throws java.io.IOException {
ensureOpen();
if (count > 0) {
log.append(buf, 0, count);
count = 0;
}
}

@Override
public void close() throws java.io.IOException {
if (closed) return;
try {
flush();
} finally {
closed = true;
log.releaseRef();
}
}

private void ensureOpen() throws java.io.IOException {
if (closed) throw new java.io.IOException("closed");
}
}




private static final class AtomicRecordMMapOutputStream extends OutputStream {
private final AppendOnlyMMapLog log;
private byte[] buf = new byte[128 * 1024];
private int count = 0;
private boolean closed = false;

AtomicRecordMMapOutputStream(AppendOnlyMMapLog log) {
this.log = log;
}

static OutputStream open(String path, boolean append) {
return new AtomicRecordMMapOutputStream(AppendOnlyMMapLog.getOrOpen(path, append));
}

@Override
public void write(int b) throws java.io.IOException {
ensureOpen();
if (count >= buf.length) grow(count + 1);
buf[count++] = (byte) b;
if (b == 0x0A) { //
flushLine();
}
}

@Override
public void write(byte[] b, int off, int len) throws java.io.IOException {
ensureOpen();
int i = off;
int end = off + len;
while (i < end) {
int nl = -1;
for (int j = i; j < end; j++) {
if (b[j] == 0x0A) {
nl = j;
break;
}
}
if (nl == -1) {

appendToBuf(b, i, end - i);
break;
} else {

appendToBuf(b, i, nl - i + 1);
flushLine();
i = nl + 1;
}
}
}

private void appendToBuf(byte[] b, int off, int len) {
if (len <= 0) return;
if (count + len > buf.length) grow(count + len);
System.arraycopy(b, off, buf, count, len);
count += len;
}

private void grow(int minCap) {
int n = buf.length;
while (n < minCap) n = Math.min(n * 2, n + 8 * 1024 * 1024);
byte[] nb = new byte[n];
System.arraycopy(buf, 0, nb, 0, count);
buf = nb;
}

private void flushLine() throws java.io.IOException {
if (count == 0) return;

log.append(buf, 0, count);
count = 0;
}

@Override
public void flush() throws java.io.IOException {
ensureOpen();

if (count > 0) {

log.append(buf, 0, count);
count = 0;
}
}

@Override
public void close() throws java.io.IOException {
if (closed) return;
try {
flush();
} finally {
closed = true;
log.releaseRef();
}
}

private void ensureOpen() throws java.io.IOException {
if (closed) throw new java.io.IOException("closed");
}
}

}
