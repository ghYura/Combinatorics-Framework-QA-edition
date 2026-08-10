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

package com.company;

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
 * STEP 32 — Executor-side reader for the {@code ShardSink} compressed-shard format
 * (Reader_trunk {@code com.company.sink.ShardSink}/{@code ShardReader}; Python
 * counterpart {@code Executor_trunk/shard_reader.py}). Lets the Java Executor consume a
 * {@code candidate_transport == "sharded"} Handoff v2 manifest.
 *
 * <p>It inflates one candidate at a time (the whole shard is never expanded in memory)
 * and CRC-checks every record; a partial {@code .tmp}/truncated/corrupt shard fails
 * {@link #validate} and is skipped. The Java Executor's watch loop runs loose
 * {@code *.java} files, so {@link #materialize} expands the corpus into a scratch dir
 * — a contained compromise for the legacy Java path (the Python Executor streams
 * shards without materialising).
 */
public final class ShardReader {
    private ShardReader() {}

    static final byte[] FILE_MAGIC   = "FWSHARD1".getBytes(StandardCharsets.US_ASCII);
    static final byte[] FILE_TRAILER = "FWSHEND1".getBytes(StandardCharsets.US_ASCII);
    static final int REC_MAGIC = 0x52454300; // "REC\0"
    static final int END_MAGIC = 0x46494E00; // "FIN\0"
    static final String SHARD_EXT = ".fwshard";
    static final String TMP_EXT = ".tmp";

    public static boolean isFinalized(Path shard) {
        try {
            long size = Files.size(shard);
            if (size < FILE_MAGIC.length + FILE_TRAILER.length) return false;
            byte[] head = new byte[FILE_MAGIC.length];
            byte[] tail = new byte[FILE_TRAILER.length];
            try (FileInputStream in = new FileInputStream(shard.toFile())) {
                if (in.read(head) != head.length) return false;
            }
            try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(shard.toFile(), "r")) {
                raf.seek(Math.max(0, raf.length() - tail.length));
                raf.readFully(tail);
            }
            return Arrays.equals(head, FILE_MAGIC) && Arrays.equals(tail, FILE_TRAILER);
        } catch (IOException e) {
            return false;
        }
    }

    /** Stream one finalized shard to {@code consumer} as {@code (id, content)}, CRC-checked. */
    public static long readShard(Path shard, BiConsumer<String, byte[]> consumer) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(new FileInputStream(shard.toFile())))) {
            byte[] magic = new byte[FILE_MAGIC.length];
            in.readFully(magic);
            if (!Arrays.equals(magic, FILE_MAGIC)) throw new IOException("not a shard file: " + shard);
            long count = 0, xor = 0;
            while (true) {
                int marker;
                try {
                    marker = in.readInt();
                } catch (EOFException eof) {
                    throw new IOException("shard not finalized (no trailer): " + shard);
                }
                if (marker == END_MAGIC) {
                    int recordCount = in.readInt();
                    long shardXor = in.readLong();
                    byte[] trailer = new byte[FILE_TRAILER.length];
                    in.readFully(trailer);
                    if (!Arrays.equals(trailer, FILE_TRAILER)) throw new IOException("bad trailer: " + shard);
                    if (recordCount != count) throw new IOException("record-count mismatch: " + shard);
                    if (shardXor != xor) throw new IOException("index/xor mismatch: " + shard);
                    return count;
                }
                if (marker != REC_MAGIC) throw new IOException("corrupt shard marker in " + shard);
                int idLen = in.readInt();
                if (idLen < 0 || idLen > (1 << 20)) throw new IOException("implausible id length " + idLen);
                byte[] idBytes = new byte[idLen];
                in.readFully(idBytes);
                long rawLen = in.readLong();
                long crcExpected = in.readLong();
                int compLen = in.readInt();
                if (rawLen < 0 || rawLen > Integer.MAX_VALUE - 8 || compLen < 0)
                    throw new IOException("implausible record lengths in " + shard);
                byte[] comp = new byte[compLen];
                in.readFully(comp);
                byte[] raw = inflate(comp, (int) rawLen);
                CRC32 crc = new CRC32();
                crc.update(raw, 0, raw.length);
                if (crc.getValue() != crcExpected) {
                    throw new IOException("record CRC mismatch for "
                            + new String(idBytes, StandardCharsets.UTF_8) + " in " + shard);
                }
                consumer.accept(new String(idBytes, StandardCharsets.UTF_8), raw);
                count++;
                xor ^= fnv1a64(new String(idBytes, StandardCharsets.UTF_8));
            }
        }
    }

    /** Record count for a valid finalized shard, or {@code -1} if partial/corrupt. */
    public static long validate(Path shard) {
        try {
            return readShard(shard, (id, body) -> { });
        } catch (IOException e) {
            return -1;
        }
    }

    public static List<Path> listFinalizedShards(Path dir) throws IOException {
        List<Path> out = new ArrayList<>();
        if (!Files.isDirectory(dir)) return out;
        try (var s = Files.list(dir)) {
            s.filter(p -> {
                String n = p.getFileName().toString();
                return n.endsWith(SHARD_EXT) && !n.endsWith(TMP_EXT);
            }).sorted().forEach(out::add);
        }
        return out;
    }

    /** Total candidate records across all VALID finalized shards in {@code dir}. */
    public static long corpusCount(Path dir) throws IOException {
        long total = 0;
        for (Path shard : listFinalizedShards(dir)) {
            long n = validate(shard);
            if (n >= 0) total += n;
        }
        return total;
    }

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

    static long fnv1a64(String s) {
        long h = 0xcbf29ce484222325L;
        for (byte x : s.getBytes(StandardCharsets.UTF_8)) {
            h ^= (x & 0xffL);
            h *= 0x100000001b3L;
        }
        return h;
    }
}
