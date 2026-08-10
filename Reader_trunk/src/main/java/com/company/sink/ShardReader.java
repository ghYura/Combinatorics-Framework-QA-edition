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

package com.company.sink;

import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.BiConsumer;
import java.util.zip.CRC32;
import java.util.zip.DataFormatException;
import java.util.zip.Inflater;

/**
 * STEP 32 — streaming reader for {@link ShardSink} containers. The Executor reader
 * inflates <em>one record at a time</em> straight to memory; it never expands a whole
 * shard onto disk (STEP 32 action 4). Each record's CRC-32 is verified against the
 * inflated bytes, and a shard is accepted only when it carries the finalize trailer —
 * so a crash-truncated {@code .tmp} (or a corrupt shard) is skipped and rebuilt by
 * resume (action 5; acceptance "interrupted partial shard ignored/rebuilt").
 */
public final class ShardReader {
    private ShardReader() {}

    /**
     * Cheap O(1) finalize probe: a finalized shard begins with {@code FILE_MAGIC} and
     * ends with {@code FILE_TRAILER}. This is only a fast pre-filter — {@link #readShard}
     * still validates the full record stream and every CRC before yielding anything.
     */
    public static boolean isFinalized(Path shard) {
        try {
            long size = Files.size(shard);
            int trailerLen = ShardSink.FILE_TRAILER.length;
            if (size < ShardSink.FILE_MAGIC.length + trailerLen) return false;
            byte[] head = new byte[ShardSink.FILE_MAGIC.length];
            byte[] tail = new byte[trailerLen];
            try (FileInputStream in = new FileInputStream(shard.toFile())) {
                if (in.read(head) != head.length) return false;
            }
            try (RandomTail rt = new RandomTail(shard, trailerLen)) {
                rt.read(tail);
            }
            return Arrays.equals(head, ShardSink.FILE_MAGIC)
                    && Arrays.equals(tail, ShardSink.FILE_TRAILER);
        } catch (IOException e) {
            return false;
        }
    }

    /**
     * Stream every candidate of one finalized shard to {@code consumer} as
     * {@code (candidateId, content)}, inflating one record at a time. The shard's
     * trailer (record count + XOR index) must reconcile and every record CRC must match.
     *
     * @return the number of candidates streamed.
     * @throws IOException if the shard is partial, truncated, or fails CRC/trailer checks.
     */
    public static long readShard(Path shard, BiConsumer<String, byte[]> consumer) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(new FileInputStream(shard.toFile())))) {
            byte[] magic = new byte[ShardSink.FILE_MAGIC.length];
            in.readFully(magic);
            if (!Arrays.equals(magic, ShardSink.FILE_MAGIC)) {
                throw new IOException("not a shard file (bad magic): " + shard);
            }
            long count = 0;
            long xor = 0;
            while (true) {
                int marker;
                try {
                    marker = in.readInt();
                } catch (EOFException eof) {
                    // Reached EOF without a trailer → partial/interrupted shard.
                    throw new IOException("shard not finalized (no trailer): " + shard);
                }
                if (marker == ShardSink.END_MAGIC) {
                    int recordCount = in.readInt();
                    long shardXor = in.readLong();
                    byte[] trailer = new byte[ShardSink.FILE_TRAILER.length];
                    in.readFully(trailer);
                    if (!Arrays.equals(trailer, ShardSink.FILE_TRAILER)) {
                        throw new IOException("bad shard trailer magic: " + shard);
                    }
                    if (recordCount != count) {
                        throw new IOException("shard record-count mismatch: header=" + recordCount
                                + " streamed=" + count + " in " + shard);
                    }
                    if (shardXor != xor) {
                        throw new IOException("shard index/XOR mismatch in " + shard);
                    }
                    return count;
                }
                if (marker != ShardSink.REC_MAGIC) {
                    throw new IOException("corrupt shard (bad record marker " + Integer.toHexString(marker)
                            + ") in " + shard);
                }
                int idLen = in.readInt();
                if (idLen < 0 || idLen > (1 << 20)) throw new IOException("implausible id length " + idLen);
                byte[] idBytes = new byte[idLen];
                in.readFully(idBytes);
                long rawLen = in.readLong();
                long crcExpected = in.readLong();
                int compLen = in.readInt();
                if (rawLen < 0 || rawLen > Integer.MAX_VALUE - 8) throw new IOException("implausible rawLen " + rawLen);
                if (compLen < 0) throw new IOException("implausible compLen " + compLen);
                byte[] comp = new byte[compLen];
                in.readFully(comp);

                byte[] raw = inflate(comp, (int) rawLen);
                CRC32 crc = new CRC32();
                crc.update(raw, 0, raw.length);
                if (crc.getValue() != crcExpected) {
                    throw new IOException("shard record CRC mismatch for id "
                            + new String(idBytes, StandardCharsets.UTF_8) + " in " + shard);
                }
                String id = new String(idBytes, StandardCharsets.UTF_8);
                consumer.accept(id, raw);
                count++;
                xor ^= ShardSink.fnv1a64(id);
            }
        }
    }

    /**
     * Validate a shard end-to-end without materialising bodies (a no-op consumer).
     * Resume calls this to decide whether a shard is reusable ({@code >= 0}) or must be
     * rebuilt ({@code -1}).
     *
     * @return record count if the shard is a valid finalized shard, else {@code -1}.
     */
    public static long validate(Path shard) {
        try {
            return readShard(shard, (id, body) -> { });
        } catch (IOException e) {
            return -1;
        }
    }

    /** Finalized {@code *.fwshard} files in a directory, in deterministic name order (skips {@code .tmp}). */
    public static List<Path> listFinalizedShards(Path dir) throws IOException {
        List<Path> out = new ArrayList<>();
        if (!Files.isDirectory(dir)) return out;
        try (var s = Files.list(dir)) {
            s.filter(p -> {
                String n = p.getFileName().toString();
                return n.endsWith(ShardSink.SHARD_EXT) && !n.endsWith(ShardSink.TMP_EXT);
            }).sorted().forEach(out::add);
        }
        return out;
    }

    /**
     * Stream an entire shard corpus: every finalized shard in deterministic order, skipping
     * any partial/{@code .tmp}/corrupt shard. This is the Executor/resume entry point.
     *
     * @return total candidates streamed across all valid shards.
     */
    public static long readCorpus(Path dir, BiConsumer<String, byte[]> consumer) throws IOException {
        long total = 0;
        for (Path shard : listFinalizedShards(dir)) {
            if (!isFinalized(shard)) continue; // crash-truncated finalized name → skip & rebuild
            total += readShard(shard, consumer);
        }
        return total;
    }

    // ── helpers ─────────────────────────────────────────────────────────────────────

    private static byte[] inflate(byte[] comp, int rawLen) throws IOException {
        Inflater inf = new Inflater(false);
        try {
            inf.setInput(comp);
            byte[] raw = new byte[rawLen];
            int got = 0;
            while (got < rawLen && !inf.finished()) {
                int k = inf.inflate(raw, got, rawLen - got);
                if (k == 0) {
                    if (inf.finished() || inf.needsDictionary()) break;
                    if (inf.needsInput()) throw new IOException("truncated deflate stream");
                }
                got += k;
            }
            if (got != rawLen) throw new IOException("inflated length " + got + " != expected " + rawLen);
            return raw;
        } catch (DataFormatException e) {
            throw new IOException("corrupt deflate stream", e);
        } finally {
            inf.end();
        }
    }

    /** Reads the last {@code n} bytes of a file without pulling the whole file into memory. */
    private static final class RandomTail implements AutoCloseable {
        private final java.io.RandomAccessFile raf;

        RandomTail(Path file, int n) throws IOException {
            this.raf = new java.io.RandomAccessFile(file.toFile(), "r");
            raf.seek(Math.max(0, raf.length() - n));
        }

        void read(byte[] dst) throws IOException {
            raf.readFully(dst);
        }

        @Override
        public void close() throws IOException {
            raf.close();
        }
    }
}
