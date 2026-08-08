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

package com.company.sink;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.zip.CRC32;
import java.util.zip.Deflater;

/**
 * STEP 32 — the compressed-shard {@link CandidateSink}: instead of one loose file
 * per candidate, candidates are packed into a small number of self-describing,
 * DEFLATE-compressed <em>shard</em> container files. For an {@code L}-class run this
 * collapses millions of inodes into {@code ceil(N / shardSize)} files.
 *
 * <p>Implements the STEP 31 {@link CandidateSink} interface, so the pipeline never learns
 * a second write path; {@link LooseFileSink} (transport {@code "loose-files"}) stays
 * available for debugging. Transport is {@code "sharded"} — the Handoff v2 contract enum
 * value. {@link Summary#bytes} and the order-independent {@link Summary#index} use the
 * <em>identical</em> formulas as {@code LooseFileSink} (cross-sink equivalence).
 *
 * <h2>Bounded memory via external sort (STEP 32 review blocker — memory)</h2>
 * Neither the candidate bodies nor the full per-candidate index are held in memory:
 * <ol>
 *   <li>{@link #write} compresses the body and appends it to an on-disk <em>body spool</em>,
 *       and adds a compact index entry (id, spool offset, lengths, crc) to an in-memory
 *       <em>run buffer</em> capped at {@code runSize} entries.</li>
 *   <li>When the run buffer fills it is sorted by candidate id and <em>spilled</em> to an
 *       on-disk sorted run; the buffer is cleared. Ingest memory is therefore O(runSize),
 *       independent of N.</li>
 *   <li>{@link #close} k-way merges the sorted runs (a heap over one head entry per run)
 *       into globally id-sorted order and streams bodies back from the spool into shards.
 *       Merge memory is O(numRuns) = O(N/runSize); packing holds one candidate body.</li>
 * </ol>
 * Peak resident memory is thus O(runSize + N/runSize) — sub-linear (≈O(√N) at the optimum
 * {@code runSize≈√N}), not O(N). Small runs (N ≤ runSize) never spill and sort in place.
 *
 * <h2>Determinism</h2>
 * {@link #write} runs concurrently from many virtual threads, so spool/arrival order is
 * non-deterministic; the merge emits a global id-sorted order, so shard bytes are identical
 * across runs regardless of thread scheduling.
 *
 * <h2>Shard file format (deterministic, streamable)</h2>
 * <pre>
 *   [8]  FILE_MAGIC   "FWSHARD1"
 *   repeated record (ascending candidate-id order):
 *     [4]  REC_MAGIC  "REC\0"  [4] idLen  [..] id  [8] rawLen  [8] crc32  [4] compLen  [..] comp
 *   trailer (only after a clean finalize):
 *     [4]  END_MAGIC  "FIN\0"  [4] recordCount  [8] shardIndexXor  [8] FILE_TRAILER "FWSHEND1"
 * </pre>
 * Each record is independently deflated ({@link ShardReader} inflates one at a time). A shard
 * is written to a sibling {@code .tmp}, fsynced, then {@link StandardCopyOption#ATOMIC_MOVE}d
 * to its final name, so a crash leaves only a {@code .tmp} the reader ignores / resume rebuilds.
 *
 * <p>Thread-safe: {@link #write} compresses off-lock; the spool append + run buffering and the
 * close-time merge/pack run under one monitor.
 */
public final class ShardSink implements CandidateSink {

    /** Transport descriptor recorded in the Handoff v2 manifest (contract enum value). */
    public static final String TRANSPORT = "sharded";

    /** Default shard rollover: candidates per shard. */
    public static final int DEFAULT_MAX_RECORDS = 1000;
    /** Default shard rollover: approximate compressed bytes per shard (8 MiB). */
    public static final long DEFAULT_MAX_BYTES = 8L * 1024 * 1024;
    /** Default external-sort run size: index entries held in memory before spilling. */
    public static final int DEFAULT_RUN_SIZE = 1_000_000;

    static final byte[] FILE_MAGIC   = "FWSHARD1".getBytes(StandardCharsets.US_ASCII); // 8 bytes
    static final byte[] FILE_TRAILER = "FWSHEND1".getBytes(StandardCharsets.US_ASCII); // 8 bytes
    static final int REC_MAGIC = 0x52454300; // "REC\0"
    static final int END_MAGIC = 0x46494E00; // "FIN\0"

    static final String SHARD_EXT = ".fwshard";
    static final String TMP_EXT = ".tmp";
    static final String MANIFEST_NAME = "shard-manifest.txt";
    static final String SPOOL_NAME = ".shard-spool";
    static final String RUN_NAME = ".shard-run";

    private static final Comparator<Rec> BY_ID =
            Comparator.comparing((Rec r) -> r.id).thenComparingLong(Rec::crc);

    private final Path outputDir;
    private final byte[] tail;
    private final int maxRecords;
    private final long maxBytes;
    private final int runSize;
    private final boolean resume;
    private final String unique;

    private final Object lock = new Object();

    /** On-disk spool of compressed bodies (bounded memory); lazily opened on first write. */
    private final Path spoolPath;
    private DataOutputStream spoolOut;
    private long spoolPos;

    /** Current in-memory run (≤ runSize entries); spilled to disk when full. */
    private final List<Rec> runBuffer = new ArrayList<>();
    private final List<Path> sortedRuns = new ArrayList<>();
    private int runSeq;
    private long received;
    /** Resume: highest candidate id already covered by a reused valid prefix shard (null = none). */
    private String checkpointMaxId;

    // ── run totals, populated at close (guarded by {@link #lock}) ──
    private long finalizedCount;
    private long finalizedBytes; // payload + tail, matching LooseFileSink semantics
    private long errors;
    private long finalizedXor;
    private final List<FinalizedShard> finalized = new ArrayList<>();

    private boolean closed = false;

    /** One candidate's index entry: id + spool location + integrity metadata. No body held. */
    private record Rec(String id, long idHash, long spoolOffset, int compLen, long rawLen, long crc) {}

    /** Per-shard summary captured at finalize, used to render the sink manifest. */
    private record FinalizedShard(String name, int records, long bytes, long xor) {}

    /** Build a shard sink with the default rollover thresholds and run size. */
    public ShardSink(Path outputDir, byte[] tail) {
        this(outputDir, tail, DEFAULT_MAX_RECORDS, DEFAULT_MAX_BYTES, DEFAULT_RUN_SIZE);
    }

    public ShardSink(Path outputDir, byte[] tail, int maxRecords, long maxBytes) {
        this(outputDir, tail, maxRecords, maxBytes, DEFAULT_RUN_SIZE, false);
    }

    public ShardSink(Path outputDir, byte[] tail, int maxRecords, long maxBytes, int runSize) {
        this(outputDir, tail, maxRecords, maxBytes, runSize, false);
    }

    /**
     * @param outputDir   directory that will hold the shard files + manifest (created if needed).
     * @param tail        bytes appended after every candidate payload (the framework's
     *                    {@code bArr}; empty in FILES_MODE). Stored as part of the candidate
     *                    content so a shard record's bytes equal the loose file's bytes.
     * @param maxRecords  roll to a new shard once this many candidates are in the current one.
     * @param maxBytes    roll to a new shard once it reaches this many compressed bytes.
     * @param runSize     external-sort run size: in-memory index entries before spilling a
     *                    sorted run to disk. Caps ingest memory; lower = more, smaller runs.
     * @param resume      checkpoint/resume mode (STEP 32 action 5). When {@code true}, on
     *                    {@link #close} the sink REUSES the valid contiguous-prefix shards
     *                    already in {@code outputDir} (a previous/interrupted run): candidates
     *                    those shards already cover are skipped and the reused shard files are
     *                    NEVER rewritten — only the missing suffix is (re)generated. When
     *                    {@code false} (fresh), any stale {@code *.fwshard} is cleared first so
     *                    a from-scratch run leaves no leftovers. Assumes the same deterministic
     *                    corpus across runs (the launcher guarantees this: same spec → same ids).
     */
    public ShardSink(Path outputDir, byte[] tail, int maxRecords, long maxBytes, int runSize, boolean resume) {
        if (outputDir == null) throw new IllegalArgumentException("ShardSink requires an output directory");
        if (maxRecords <= 0) throw new IllegalArgumentException("maxRecords must be > 0");
        if (maxBytes <= 0) throw new IllegalArgumentException("maxBytes must be > 0");
        if (runSize <= 0) throw new IllegalArgumentException("runSize must be > 0");
        this.outputDir = outputDir;
        this.tail = (tail == null) ? new byte[0] : tail.clone();
        this.maxRecords = maxRecords;
        this.maxBytes = maxBytes;
        this.runSize = runSize;
        this.resume = resume;
        this.unique = ProcessHandle.current().pid() + "." + Integer.toHexString(System.identityHashCode(this));
        this.spoolPath = outputDir.resolve(SPOOL_NAME + "." + unique);
        try {
            Files.createDirectories(outputDir);
        } catch (IOException _) {
            // Mirror LooseFileSink tolerance: a missing dir surfaces later as a write error.
        }
    }

    @Override
    public void write(String candidateId, byte[] content, int off, int len) {
        if (closed) throw new IllegalStateException("ShardSink is closed");
        final int n = Math.max(0, len);

        // Assemble the candidate body (payload + tail) and compress it OFF-lock.
        final byte[] raw = new byte[n + tail.length];
        System.arraycopy(content, off, raw, 0, n);
        System.arraycopy(tail, 0, raw, n, tail.length);

        final CRC32 crc = new CRC32();
        crc.update(raw, 0, raw.length);
        final byte[] comp = deflate(raw);
        final long h = fnv1a64(candidateId);

        synchronized (lock) {
            if (closed) throw new IllegalStateException("ShardSink is closed");
            try {
                if (spoolOut == null) {
                    spoolOut = new DataOutputStream(new BufferedOutputStream(
                            new FileOutputStream(spoolPath.toFile(), false)));
                    spoolPos = 0;
                }
                long offset = spoolPos;
                spoolOut.write(comp);
                spoolPos += comp.length;
                runBuffer.add(new Rec(candidateId, h, offset, comp.length, raw.length, crc.getValue()));
                received++;
                if (runBuffer.size() >= runSize) {
                    spoolOut.flush();      // body must be durable on disk before we may read it back
                    spillRun();
                }
            } catch (IOException e) {
                errors++;
                System.err.println("[ShardSink] failed to spool candidate " + candidateId + ": " + e);
            }
        }
    }

    @Override
    public String transport() {
        return TRANSPORT;
    }

    @Override
    public Summary summary() {
        synchronized (lock) {
            return new Summary(TRANSPORT, finalizedCount, finalizedBytes, errors,
                    String.format("%016x", finalizedXor));
        }
    }

    @Override
    public void close() {
        synchronized (lock) {
            if (closed) return;
            closed = true;
            if (spoolOut != null) {
                try { spoolOut.flush(); spoolOut.close(); } catch (IOException _) { }
            }
            // STEP 32 action 5 (review): reuse existing valid shards from a prior/interrupted run
            // (never rewrite them), or — fresh — clear stale shards so no leftovers remain.
            if (resume) loadExistingCheckpoint(); else clearStaleShards();
            try (RandomAccessFile spool = (received == 0) ? null
                    : new RandomAccessFile(spoolPath.toFile(), "r")) {
                packSortedCandidates(spool);
            } catch (IOException e) {
                errors += Math.max(0, received - finalizedCount);
                System.err.println("[ShardSink] external sort/pack failed at close: " + e);
            }
            runBuffer.clear();
            for (Path run : sortedRuns) { try { Files.deleteIfExists(run); } catch (IOException _) { } }
            sortedRuns.clear();
            writeManifestQuietly();
            try { Files.deleteIfExists(spoolPath); } catch (IOException _) { }
        }
    }

    /** Number of shard files finalized (meaningful after {@link #close}). */
    public int shardCount() {
        synchronized (lock) {
            return finalized.size();
        }
    }

    // ── external sort: ingest (all callers hold {@link #lock}) ──────────────────────

    /** Sort the current in-memory run by id and spill it to a disk run file. */
    private void spillRun() throws IOException {
        if (runBuffer.isEmpty()) return;
        runBuffer.sort(BY_ID);
        Path run = outputDir.resolve(RUN_NAME + "." + unique + "." + (runSeq++));
        try (DataOutputStream out = new DataOutputStream(new BufferedOutputStream(
                new FileOutputStream(run.toFile(), false)))) {
            for (Rec r : runBuffer) {
                byte[] id = r.id.getBytes(StandardCharsets.UTF_8);
                out.writeInt(id.length);
                out.write(id);
                out.writeLong(r.idHash);
                out.writeLong(r.spoolOffset);
                out.writeInt(r.compLen);
                out.writeLong(r.rawLen);
                out.writeLong(r.crc);
            }
        }
        sortedRuns.add(run);
        runBuffer.clear();
    }

    // ── external sort: merge + pack ─────────────────────────────────────────────────

    /** Emit candidates in global id order (in-memory if a single run, else k-way merge of
     *  spilled runs) and pack them into size-bounded shards, bodies streamed from the spool. */
    private void packSortedCandidates(RandomAccessFile spool) throws IOException {
        ShardPacker packer = new ShardPacker(spool);
        if (sortedRuns.isEmpty()) {
            // Fast path: everything fits in one in-memory run — sort in place, no spill.
            runBuffer.sort(BY_ID);
            for (Rec r : runBuffer) { if (alreadyCovered(r)) continue; packer.add(r); }
        } else {
            spillRun(); // flush the final partial run
            List<RunReader> readers = new ArrayList<>(sortedRuns.size());
            PriorityQueue<RunReader> heap = new PriorityQueue<>(
                    Math.max(1, sortedRuns.size()), Comparator.comparing(rr -> rr.head, BY_ID));
            try {
                for (Path run : sortedRuns) {
                    RunReader rr = new RunReader(run);
                    readers.add(rr);
                    if (rr.advance()) heap.add(rr);
                }
                while (!heap.isEmpty()) {
                    RunReader rr = heap.poll();
                    if (!alreadyCovered(rr.head)) packer.add(rr.head);
                    if (rr.advance()) heap.add(rr);
                }
            } finally {
                for (RunReader rr : readers) rr.close();
            }
        }
        packer.close();
    }

    /** A candidate whose id is already covered by a reused valid prefix shard (resume mode). */
    private boolean alreadyCovered(Rec r) {
        return checkpointMaxId != null && r.id.compareTo(checkpointMaxId) <= 0;
    }

    /**
     * Resume (STEP 32 action 5): scan {@code outputDir} for the valid <em>contiguous prefix</em>
     * of finalized shards left by a prior/interrupted run, register them as already-finalized
     * (so new shards continue the sequence and the manifest lists them) and remember the highest
     * id they cover in {@link #checkpointMaxId} so {@link #alreadyCovered} skips re-emitting it.
     * The reused shard files are never opened for writing. Because shards are packed in global
     * id-sorted order with sequential names, the surviving prefix {@code shard-00000..K} covers
     * exactly the id-prefix {@code id ≤ checkpointMaxId}. Anything after the first invalid /
     * missing / non-monotonic shard is discarded and regenerated.
     */
    private void loadExistingCheckpoint() {
        List<Path> existing;
        try { existing = ShardReader.listFinalizedShards(outputDir); }
        catch (IOException e) { return; }
        int reused = 0;
        for (int seq = 0; seq < existing.size(); seq++) {
            Path shard = existing.get(seq);
            String expectedName = String.format("shard-%05d%s", seq, SHARD_EXT);
            if (!shard.getFileName().toString().equals(expectedName)) break; // gap → stop prefix
            final long[] acc = {0, 0, 0};            // {count, xor, rawBytes}
            final String[] maxId = {checkpointMaxId};
            final boolean[] monotonic = {true};
            try {
                ShardReader.readShard(shard, (id, body) -> {
                    if (maxId[0] != null && id.compareTo(maxId[0]) <= 0) monotonic[0] = false;
                    maxId[0] = id;
                    acc[0]++;
                    acc[1] ^= fnv1a64(id);
                    acc[2] += body.length;
                });
            } catch (IOException invalid) {
                break;                                // truncated/corrupt shard → stop prefix here
            }
            if (!monotonic[0] || acc[0] == 0) break;  // disordered/overlapping/empty → stop prefix
            long fileBytes;
            try { fileBytes = Files.size(shard); } catch (IOException e) { fileBytes = 0; }
            finalized.add(new FinalizedShard(shard.getFileName().toString(), (int) acc[0], fileBytes, acc[1]));
            finalizedCount += acc[0];
            finalizedBytes += acc[2];
            finalizedXor ^= acc[1];
            checkpointMaxId = maxId[0];
            reused = seq + 1;
        }
        // Drop any existing shards beyond the reused valid prefix; they are regenerated.
        for (int seq = reused; seq < existing.size(); seq++) {
            try { Files.deleteIfExists(existing.get(seq)); } catch (IOException _) { }
        }
        if (reused > 0) {
            System.out.println("[ShardSink] resume: reusing " + reused + " valid finalized shard(s), "
                    + finalizedCount + " candidate(s) already persisted (will not rewrite them)");
        }
    }

    /** Fresh (non-resume): remove any stale {@code *.fwshard} so a from-scratch run leaves none. */
    private void clearStaleShards() {
        try {
            for (Path shard : ShardReader.listFinalizedShards(outputDir)) Files.deleteIfExists(shard);
        } catch (IOException _) { }
    }

    /** Streaming reader over one spilled sorted run; exposes its current {@link Rec} as {@code head}. */
    private static final class RunReader implements AutoCloseable {
        private final DataInputStream in;
        Rec head;

        RunReader(Path run) throws IOException {
            this.in = new DataInputStream(new BufferedInputStream(new FileInputStream(run.toFile())));
        }

        boolean advance() throws IOException {
            try {
                int idLen = in.readInt();
                byte[] id = new byte[idLen];
                in.readFully(id);
                long idHash = in.readLong();
                long off = in.readLong();
                int compLen = in.readInt();
                long rawLen = in.readLong();
                long crc = in.readLong();
                head = new Rec(new String(id, StandardCharsets.UTF_8), idHash, off, compLen, rawLen, crc);
                return true;
            } catch (EOFException eof) {
                head = null;
                return false;
            }
        }

        @Override
        public void close() {
            try { in.close(); } catch (IOException _) { }
        }
    }

    /** Incremental packer: appends id-sorted candidates into size-bounded, atomically-finalized
     *  shards, reading each body from the spool by offset (one body resident at a time). */
    private final class ShardPacker {
        private final RandomAccessFile spool;
        private FileOutputStream curFos;
        private DataOutputStream curOut;
        private Path curTmp, curFin;
        private int curRecs;
        private long curComp, curXor, curRawSum;

        ShardPacker(RandomAccessFile spool) { this.spool = spool; }

        void add(Rec r) {
            try {
                if (curOut == null) openShard();
                byte[] comp = new byte[r.compLen];
                spool.seek(r.spoolOffset);
                spool.readFully(comp);
                byte[] id = r.id.getBytes(StandardCharsets.UTF_8);
                curOut.writeInt(REC_MAGIC);
                curOut.writeInt(id.length);
                curOut.write(id);
                curOut.writeLong(r.rawLen);
                curOut.writeLong(r.crc);
                curOut.writeInt(r.compLen);
                curOut.write(comp);
                curRecs++;
                curComp += r.compLen;
                curXor ^= r.idHash;
                curRawSum += r.rawLen;
                if (curRecs >= maxRecords || curComp >= maxBytes) finalizeShard();
            } catch (IOException e) {
                // The in-flight shard is now inconsistent: its buffered records are lost.
                errors += curRecs + 1L;
                System.err.println("[ShardSink] failed to write shard record " + r.id
                        + " (" + (curRecs + 1) + " candidate(s) lost): " + e);
                discardShard();
            }
        }

        void close() {
            if (curOut != null && curRecs > 0) {
                try { finalizeShard(); }
                catch (IOException e) { errors += curRecs; discardShard(); }
            } else {
                discardShard();
            }
        }

        private void openShard() throws IOException {
            String base = String.format("shard-%05d", finalized.size());
            curFin = outputDir.resolve(base + SHARD_EXT);
            curTmp = outputDir.resolve(base + SHARD_EXT + TMP_EXT);
            curFos = new FileOutputStream(curTmp.toFile(), false);
            curOut = new DataOutputStream(new BufferedOutputStream(curFos));
            curOut.write(FILE_MAGIC);
            curRecs = 0; curComp = 0; curXor = 0; curRawSum = 0;
        }

        private void finalizeShard() throws IOException {
            curOut.writeInt(END_MAGIC);
            curOut.writeInt(curRecs);
            curOut.writeLong(curXor);
            curOut.write(FILE_TRAILER);
            curOut.flush();
            curFos.getFD().sync();
            curOut.close();
            Files.move(curTmp, curFin, StandardCopyOption.ATOMIC_MOVE);
            finalized.add(new FinalizedShard(curFin.getFileName().toString(), curRecs, Files.size(curFin), curXor));
            finalizedCount += curRecs;
            finalizedBytes += curRawSum;
            finalizedXor ^= curXor;
            reset();
        }

        private void discardShard() {
            if (curOut != null) { try { curOut.close(); } catch (IOException _) { } }
            if (curTmp != null) { try { Files.deleteIfExists(curTmp); } catch (IOException _) { } }
            reset();
        }

        private void reset() {
            curOut = null; curFos = null; curTmp = null; curFin = null;
            curRecs = 0; curComp = 0; curXor = 0; curRawSum = 0;
        }
    }

    /** Render the sink-level manifest atomically (convenience/index — the *.fwshard directory
     *  is the source of truth, so a missing/stale manifest never blocks {@link ShardReader}). */
    private void writeManifestQuietly() {
        StringBuilder sb = new StringBuilder();
        sb.append("# fw-shard-manifest v1\n");
        sb.append("transport ").append(TRANSPORT).append('\n');
        sb.append("shards ").append(finalized.size()).append('\n');
        sb.append("candidates ").append(finalizedCount).append('\n');
        sb.append("bytes ").append(finalizedBytes).append('\n');
        sb.append("errors ").append(errors).append('\n');
        sb.append(String.format("index %016x%n", finalizedXor));
        for (FinalizedShard fs : finalized) {
            sb.append(String.format("shard %s records=%d bytes=%d index=%016x%n",
                    fs.name, fs.records, fs.bytes, fs.xor));
        }
        Path tmp = outputDir.resolve(MANIFEST_NAME + TMP_EXT);
        Path fin = outputDir.resolve(MANIFEST_NAME);
        try (FileOutputStream fos = new FileOutputStream(tmp.toFile(), false)) {
            fos.write(sb.toString().getBytes(StandardCharsets.UTF_8));
            fos.flush();
            fos.getFD().sync();
        } catch (IOException _) {
            return;
        }
        try {
            Files.move(tmp, fin, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException _) {
            try { Files.deleteIfExists(tmp); } catch (IOException ignored2) { }
        }
    }

    // ── helpers ─────────────────────────────────────────────────────────────────────

    /** DEFLATE a buffer into a fresh array. Independent per record → independently inflatable. */
    static byte[] deflate(byte[] data) {
        Deflater def = new Deflater(Deflater.DEFAULT_COMPRESSION, false);
        try {
            def.setInput(data);
            def.finish();
            ByteArrayOutputStream bos = new ByteArrayOutputStream(Math.max(16, data.length / 2));
            byte[] buf = new byte[8192];
            while (!def.finished()) {
                int k = def.deflate(buf);
                bos.write(buf, 0, k);
            }
            return bos.toByteArray();
        } finally {
            def.end();
        }
    }

    /** 64-bit FNV-1a — identical to {@link LooseFileSink} so the index is cross-sink comparable. */
    static long fnv1a64(String s) {
        long h = 0xcbf29ce484222325L;
        for (byte x : s.getBytes(StandardCharsets.UTF_8)) {
            h ^= (x & 0xffL);
            h *= 0x100000001b3L;
        }
        return h;
    }
}
