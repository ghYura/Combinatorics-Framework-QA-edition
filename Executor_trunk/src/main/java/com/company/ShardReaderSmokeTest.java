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

package com.company;

import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.zip.CRC32;
import java.util.zip.Deflater;

/**
 * STEP 32 verifier for the Executor-side {@link ShardReader}. It writes shard files
 * inline with the very same JDK {@link Deflater}/{@link CRC32} primitives the Reader's
 * {@code ShardSink} uses (so the bytes are format-identical), then proves the reader
 * streams + validates them, materialises candidates, and rejects partial/corrupt shards.
 *
 * <p>Cross-runtime parity (Java ShardSink ↔ Python shard_reader) is covered separately by
 * {@code Executor_trunk/test_shard_reader.py}; this focuses on the Java reader itself.
 *
 * Run:  java -cp target/classes com.company.ShardReaderSmokeTest
 */
public final class ShardReaderSmokeTest {
    private ShardReaderSmokeTest() {}

    public static void main(String[] args) throws Exception {
        int f = 0;
        f += testReadAndValidate();
        f += testStreamingOneAtATime();
        f += testPartialRejected();
        System.out.println();
        if (f == 0) System.out.println("✅ ALL SHARD-READER (Java executor) CHECKS PASSED");
        else { System.out.println("❌ " + f + " CHECK(S) FAILED"); System.exit(1); }
    }

    private static int testReadAndValidate() throws IOException {
        System.out.println("\n── read + validate ──");
        Path dir = Files.createTempDirectory("execshard-read");
        try {
            Map<String, byte[]> corpus = new LinkedHashMap<>();
            for (int i = 0; i < 7; i++) corpus.put((100000 + i) + "_0_0", ("class C" + i + " {}\n").getBytes(StandardCharsets.UTF_8));
            Path shard = dir.resolve("shard-00000.fwshard");
            writeShard(shard, corpus);

            Map<String, byte[]> got = new TreeMap<>();
            long n = ShardReader.readShard(shard, (id, body) -> got.put(id, body));
            int f = 0;
            f += assertCond("readShard returns record count", n == corpus.size());
            f += assertCond("isFinalized true", ShardReader.isFinalized(shard));
            f += assertCond("validate returns count", ShardReader.validate(shard) == corpus.size());
            f += assertCond("all ids recovered", got.keySet().equals(new TreeMap<>(corpus).keySet()));
            boolean bodiesOk = true;
            for (var e : corpus.entrySet()) if (!java.util.Arrays.equals(e.getValue(), got.get(e.getKey()))) bodiesOk = false;
            f += assertCond("all bodies byte-identical", bodiesOk);
            return f;
        } finally { rm(dir); }
    }

    // Streaming consumption: at most ONE candidate body on disk at a time (review blocker #3),
    // mirroring how MainWatch.coldStartScanShards drives the per-candidate path.
    private static int testStreamingOneAtATime() throws IOException {
        System.out.println("\n── streaming one candidate at a time ──");
        Path dir = Files.createTempDirectory("execshard-stream");
        try {
            Map<String, byte[]> a = new LinkedHashMap<>(), b = new LinkedHashMap<>();
            for (int i = 0; i < 5; i++) a.put(i + "_0_0", ("A" + i).getBytes(StandardCharsets.UTF_8));
            for (int i = 5; i < 9; i++) b.put(i + "_0_0", ("B" + i).getBytes(StandardCharsets.UTF_8));
            writeShard(dir.resolve("shard-00000.fwshard"), a);
            writeShard(dir.resolve("shard-00001.fwshard"), b);

            Path scratch = Files.createTempDirectory("execshard-scratch");
            try {
                long[] processed = {0};
                long[] peakFiles = {0};
                Map<String, byte[]> seen = new TreeMap<>();
                for (Path shard : ShardReader.listFinalizedShards(dir)) {
                    ShardReader.readShard(shard, (id, body) -> {
                        try {
                            Path cand = scratch.resolve(id + ".java");
                            Files.write(cand, body);                 // materialise ONE
                            try (var s = Files.list(scratch)) { peakFiles[0] = Math.max(peakFiles[0], s.count()); }
                            seen.put(id, Files.readAllBytes(cand));   // "process"
                            Files.deleteIfExists(cand);               // then delete it
                            processed[0]++;
                        } catch (IOException e) { throw new RuntimeException(e); }
                    });
                }
                int f = 0;
                f += assertCond("streamed all 9 candidates", processed[0] == 9 && seen.size() == 9);
                f += assertCond("never more than ONE candidate on disk at a time", peakFiles[0] == 1);
                f += assertCond("a sample candidate streamed the right bytes",
                        java.util.Arrays.equals(seen.get("7_0_0"), "B7".getBytes(StandardCharsets.UTF_8)));
                f += assertCond("scratch empty after streaming", countFiles(scratch) == 0);
                return f;
            } finally { rm(scratch); }
        } finally { rm(dir); }
    }

    private static int testPartialRejected() throws IOException {
        System.out.println("\n── partial/corrupt rejected ──");
        Path dir = Files.createTempDirectory("execshard-partial");
        try {
            Map<String, byte[]> corpus = new LinkedHashMap<>();
            for (int i = 0; i < 4; i++) corpus.put(i + "_0_0", ("x" + i).getBytes(StandardCharsets.UTF_8));
            Path shard = dir.resolve("shard-00000.fwshard");
            writeShard(shard, corpus);
            // Chop into the trailer.
            try (var raf = new java.io.RandomAccessFile(shard.toFile(), "rw")) {
                raf.setLength(raf.length() - 6);
            }
            int f = 0;
            f += assertCond("isFinalized false after truncation", !ShardReader.isFinalized(shard));
            f += assertCond("validate returns -1", ShardReader.validate(shard) == -1);
            boolean threw = false;
            try { ShardReader.readShard(shard, (id, body) -> {}); } catch (IOException e) { threw = true; }
            f += assertCond("readShard throws on partial", threw);
            return f;
        } finally { rm(dir); }
    }

    // ── inline shard writer: byte-identical to ShardSink.writeOneShard ──
    private static void writeShard(Path shard, Map<String, byte[]> corpus) throws IOException {
        byte[] FILE_MAGIC = "FWSHARD1".getBytes(StandardCharsets.US_ASCII);
        byte[] FILE_TRAILER = "FWSHEND1".getBytes(StandardCharsets.US_ASCII);
        int REC_MAGIC = 0x52454300, END_MAGIC = 0x46494E00;
        long xor = 0;
        try (FileOutputStream fos = new FileOutputStream(shard.toFile());
             DataOutputStream out = new DataOutputStream(new BufferedOutputStream(fos))) {
            out.write(FILE_MAGIC);
            for (var e : corpus.entrySet()) {
                byte[] id = e.getKey().getBytes(StandardCharsets.UTF_8);
                byte[] raw = e.getValue();
                CRC32 crc = new CRC32(); crc.update(raw, 0, raw.length);
                byte[] comp = deflate(raw);
                out.writeInt(REC_MAGIC);
                out.writeInt(id.length);
                out.write(id);
                out.writeLong(raw.length);
                out.writeLong(crc.getValue());
                out.writeInt(comp.length);
                out.write(comp);
                xor ^= ShardReader.fnv1a64(e.getKey());
            }
            out.writeInt(END_MAGIC);
            out.writeInt(corpus.size());
            out.writeLong(xor);
            out.write(FILE_TRAILER);
        }
    }

    private static byte[] deflate(byte[] data) {
        Deflater def = new Deflater(Deflater.DEFAULT_COMPRESSION, false);
        try {
            def.setInput(data); def.finish();
            ByteArrayOutputStream bos = new ByteArrayOutputStream(Math.max(16, data.length / 2));
            byte[] buf = new byte[8192];
            while (!def.finished()) { int k = def.deflate(buf); bos.write(buf, 0, k); }
            return bos.toByteArray();
        } finally { def.end(); }
    }

    private static long countFiles(Path dir) throws IOException {
        try (var s = Files.list(dir)) { return s.filter(Files::isRegularFile).count(); }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static void rm(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var w = Files.walk(root)) {
            w.sorted(Comparator.reverseOrder()).forEach(p -> { try { Files.delete(p); } catch (IOException ignored) {} });
        }
    }
}
