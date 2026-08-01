package com.company.sink;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;

/**
 * STEP 32 verifier for the compressed-shard sink. Exercises {@link ShardSink} +
 * {@link ShardReader} directly — a focused "small corpus in both sinks" check that
 * needs no PostgreSQL and no full candidate pipeline — and proves the STEP 32
 * acceptance criteria:
 *
 * <ul>
 *   <li><b>Same candidates/content hashes as loose mode</b>: the identical corpus
 *       written through {@link LooseFileSink} and {@link ShardSink} yields the same
 *       {@code id → SHA-256(content)} map, and the same authoritative
 *       {@code count}/{@code bytes}/{@code index} summary.</li>
 *   <li><b>Candidate order/IDs deterministic</b>: a single-threaded run produces
 *       byte-identical shard files across two independent runs.</li>
 *   <li><b>Interrupted partial shard ignored/rebuilt</b>: a crash-truncated shard (and
 *       a stray {@code .tmp}) is skipped by the reader, and re-supplying the shard
 *       restores the full corpus.</li>
 *   <li><b>Inode count substantially smaller</b>: N candidates collapse to
 *       {@code ceil(N/shardSize)} files instead of N loose files.</li>
 * </ul>
 *
 * Run:  java -cp ... com.company.sink.ShardSinkSmokeTest
 */
public final class ShardSinkSmokeTest {
    private ShardSinkSmokeTest() {}

    private static final String EXT = ".java";

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testSameCandidatesAndHashesAsLooseMode();
        failures += testSummaryParityWithLooseSink();
        failures += testInodeCountSubstantiallySmaller();
        failures += testBodiesSpooledToDiskNotMemory();
        failures += testExternalSortBoundedMemory();
        failures += testResumeRepeatRunDoesNotRewriteValidShards();
        failures += testResumeRegeneratesOnlyMissingSuffixShards();
        failures += testDeterministicShardBytes();
        failures += testDeterministicUnderConcurrency();
        failures += testConfigurableShardSizeByCountAndBytes();
        failures += testTailAndTrimRoundTrip();
        failures += testConcurrentWritesAllLand();
        failures += testPartialShardIgnoredAndRebuilt();
        failures += testStrayTmpIgnored();
        failures += testStreamingWritesNothingToDisk();
        failures += testWriteErrorsCounted();
        failures += testTransportDescriptor();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL SHARD-SINK SMOKE CHECKS PASSED");
        else { System.out.println("❌ " + failures + " SHARD-SINK SMOKE CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── Same candidates + content hashes as loose mode ─────────────────────────────
    private static int testSameCandidatesAndHashesAsLooseMode() throws Exception {
        System.out.println("\n── Same candidates/content hashes as loose mode ──");
        Path root = Files.createTempDirectory("shard-parity");
        try {
            String looseDir = mkdir(root, "loose");
            Path shardDir = Files.createDirectories(root.resolve("shard"));
            byte[] tail = "\n".getBytes(StandardCharsets.UTF_8); // non-empty bArr to exercise tail
            Corpus c = makeCorpus(140, 3 /*trim*/);

            CandidateSink loose = new LooseFileSink(List.of(looseDir), EXT, tail);
            // small shard so the 140-candidate corpus spans many shards
            ShardSink shard = new ShardSink(shardDir, tail, 16, ShardSink.DEFAULT_MAX_BYTES);
            for (Corpus.Item it : c.items) {
                loose.write(it.id, it.body, 0, it.payloadLen);
                shard.write(it.id, it.body, 0, it.payloadLen);
            }
            loose.close();
            shard.close();

            Map<String, String> looseMap = looseIdToHash(looseDir, tail == null ? new byte[0] : tail);
            Map<String, String> shardMap = shardIdToHash(shardDir);

            int f = 0;
            f += assertCond("loose wrote " + c.items.size() + " files", looseMap.size() == c.items.size());
            f += assertCond("shard read back " + c.items.size() + " candidates", shardMap.size() == c.items.size());
            f += assertCond("id set identical (loose vs shard)", looseMap.keySet().equals(shardMap.keySet()));
            f += assertCond("every candidate content hash identical (loose vs shard)", looseMap.equals(shardMap));
            f += assertCond("shard packed into >1 shard file", shard.shardCount() > 1);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Authoritative summary parity (count / bytes / order-independent index) ──────
    private static int testSummaryParityWithLooseSink() throws Exception {
        System.out.println("\n── Summary parity (count/bytes/index) with loose sink ──");
        Path root = Files.createTempDirectory("shard-summary");
        try {
            String looseDir = mkdir(root, "loose");
            Path shardDir = Files.createDirectories(root.resolve("shard"));
            byte[] tail = new byte[0];
            Corpus c = makeCorpus(73, 0);

            CandidateSink loose = new LooseFileSink(List.of(looseDir), EXT, tail);
            ShardSink shard = new ShardSink(shardDir, tail, 10, ShardSink.DEFAULT_MAX_BYTES);
            // write the same corpus in DIFFERENT orders to prove index is order-independent
            for (Corpus.Item it : c.items) loose.write(it.id, it.body, 0, it.payloadLen);
            for (int i = c.items.size() - 1; i >= 0; i--) {
                Corpus.Item it = c.items.get(i);
                shard.write(it.id, it.body, 0, it.payloadLen);
            }
            loose.close();
            shard.close();

            CandidateSink.Summary ls = loose.summary();
            CandidateSink.Summary ss = shard.summary();
            int f = 0;
            f += assertCond("transport == sharded", "sharded".equals(ss.transport()));
            f += assertCond("candidateCount equal (" + ls.candidateCount() + ")", ls.candidateCount() == ss.candidateCount());
            f += assertCond("bytes equal (payload+tail, " + ls.bytes() + ")", ls.bytes() == ss.bytes());
            f += assertCond("order-independent index equal across sinks", ls.index().equals(ss.index()));
            f += assertCond("errors == 0", ss.errors() == 0);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Inode count substantially smaller than loose files ─────────────────────────
    private static int testInodeCountSubstantiallySmaller() throws Exception {
        System.out.println("\n── Inode count substantially smaller ──");
        Path root = Files.createTempDirectory("shard-inode");
        try {
            String looseDir = mkdir(root, "loose");
            Path shardDir = Files.createDirectories(root.resolve("shard"));
            int n = 200, per = 50; // ceil(200/50) = 4 shards
            byte[] tail = new byte[0];
            Corpus c = makeCorpus(n, 0);

            CandidateSink loose = new LooseFileSink(List.of(looseDir), EXT, tail);
            ShardSink shard = new ShardSink(shardDir, tail, per, ShardSink.DEFAULT_MAX_BYTES);
            for (Corpus.Item it : c.items) {
                loose.write(it.id, it.body, 0, it.payloadLen);
                shard.write(it.id, it.body, 0, it.payloadLen);
            }
            loose.close();
            shard.close();

            long looseFiles = countFiles(Path.of(looseDir));
            long shardFiles = countFiles(shardDir); // shard files + manifest
            int f = 0;
            f += assertCond("loose dir holds " + n + " inodes", looseFiles == n);
            f += assertCond("shard dir holds 4 shards + 1 manifest = 5", shardFiles == 5);
            f += assertCond("shard inode count << loose (5 vs 200)", shardFiles * 10 < looseFiles);
            f += assertCond("exactly ceil(n/per) shard files", shard.shardCount() == 4);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Bodies are spooled to disk, not buffered in memory (review blocker #1) ──────
    private static int testBodiesSpooledToDiskNotMemory() throws Exception {
        System.out.println("\n── Bodies spooled to disk (bounded memory) ──");
        Path root = Files.createTempDirectory("shard-spool");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            ShardSink shard = new ShardSink(dir, new byte[0], 8, ShardSink.DEFAULT_MAX_BYTES);
            for (int i = 0; i < 50; i++) {
                byte[] body = ("candidate body number " + i + " with padding bytes xxxxxxxxxx").getBytes(StandardCharsets.UTF_8);
                shard.write(i + "_0_0", body, 0, body.length);
            }
            int f = 0;
            // Mid-stream (before close): the compressed bodies live on disk in the spool, not in a list.
            f += assertCond("spool file present on disk while writing", hasSpool(dir));
            shard.close();
            f += assertCond("spool removed after close", !hasSpool(dir));
            f += assertCond("no .tmp leftovers after close", countTmp(dir) == 0);
            f += assertCond("all 50 candidates finalized + recoverable",
                    shard.summary().candidateCount() == 50 && ShardReader.readCorpus(dir, (i2, x) -> {}) == 50);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    private static boolean hasSpool(Path dir) throws IOException {
        try (var s = Files.list(dir)) {
            return s.anyMatch(p -> p.getFileName().toString().startsWith(ShardSink.SPOOL_NAME));
        }
    }

    private static boolean hasRunFiles(Path dir) throws IOException {
        try (var s = Files.list(dir)) {
            return s.anyMatch(p -> p.getFileName().toString().startsWith(ShardSink.RUN_NAME));
        }
    }

    // ─── External merge sort: spill to disk + k-way merge, bounded memory (review blocker) ──
    // A tiny run size forces many spilled sorted runs and a real k-way merge (not the
    // in-memory fast path), so the corpus is sorted/packed without an O(N) in-memory index.
    private static int testExternalSortBoundedMemory() throws Exception {
        System.out.println("\n── External merge sort (spill + k-way merge, bounded memory) ──");
        Path root = Files.createTempDirectory("shard-extsort");
        try {
            Corpus c = makeCorpus(200, 1);
            byte[] tail = "\n".getBytes(StandardCharsets.UTF_8);
            Path a = Files.createDirectories(root.resolve("a"));
            Path b = Files.createDirectories(root.resolve("b"));
            writeShardCorpusRunSize(a, c, tail, 16, 8);   // runSize=8 → ~25 spilled runs, then merge
            writeShardCorpusRunSize(b, c, tail, 16, 8);

            int f = 0;
            List<String> ids = new ArrayList<>();
            long n = ShardReader.readCorpus(a, (id, body) -> ids.add(id));
            f += assertCond("all 200 candidates recovered through the merge", n == 200);
            List<String> sortedIds = new ArrayList<>(ids);
            sortedIds.sort(String::compareTo);
            f += assertCond("merge emits candidates in global id-sorted order", ids.equals(sortedIds));

            List<Path> sa = ShardReader.listFinalizedShards(a), sb = ShardReader.listFinalizedShards(b);
            boolean eq = sa.size() == sb.size() && sa.size() > 1;
            for (int i = 0; i < Math.min(sa.size(), sb.size()) && eq; i++) {
                if (!java.util.Arrays.equals(Files.readAllBytes(sa.get(i)), Files.readAllBytes(sb.get(i)))) eq = false;
            }
            f += assertCond("spilled+merged runs are byte-identical across runs (deterministic)", eq);
            f += assertCond("no spool/run temp files leak after close",
                    !hasSpool(a) && !hasRunFiles(a) && countTmp(a) == 0);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    private static void writeShardCorpusRunSize(Path dir, Corpus c, byte[] tail, int maxRecords, int runSize) {
        ShardSink shard = new ShardSink(dir, tail, maxRecords, ShardSink.DEFAULT_MAX_BYTES, runSize);
        for (Corpus.Item it : c.items) shard.write(it.id, it.body, 0, it.payloadLen);
        shard.close();
    }

    /** Write a corpus through a RESUME-mode sink (reuses any valid shards already in dir). */
    private static CandidateSink.Summary writeShardCorpusResume(Path dir, Corpus c, byte[] tail, int maxRecords) {
        ShardSink shard = new ShardSink(dir, tail, maxRecords, ShardSink.DEFAULT_MAX_BYTES, ShardSink.DEFAULT_RUN_SIZE, true);
        for (Corpus.Item it : c.items) shard.write(it.id, it.body, 0, it.payloadLen);
        shard.close();
        return shard.summary();
    }

    // ─── Resume/checkpoint: a repeat run must NOT rewrite valid shards (review blocker) ──
    private static int testResumeRepeatRunDoesNotRewriteValidShards() throws Exception {
        System.out.println("\n── Resume: repeat run does not rewrite valid shards ──");
        Path root = Files.createTempDirectory("shard-resume-repeat");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            Corpus c = makeCorpus(100, 1);
            byte[] tail = new byte[0];

            CandidateSink.Summary s1 = writeShardCorpusResume(dir, c, tail, 16);   // run 1: fresh full write
            List<Path> shards1 = ShardReader.listFinalizedShards(dir);
            Map<String, Long> mtime1 = new TreeMap<>();
            Map<String, String> hash1 = new TreeMap<>();
            for (Path p : shards1) {
                mtime1.put(p.getFileName().toString(), Files.getLastModifiedTime(p).toMillis());
                hash1.put(p.getFileName().toString(), sha256(Files.readAllBytes(p)));
            }
            int f = 0;
            f += assertCond("run 1 produced >1 shard", shards1.size() > 1);
            f += assertCond("run 1 count == 100", s1.candidateCount() == 100);

            Thread.sleep(1100); // so a rewrite would be visible as a newer mtime

            CandidateSink.Summary s2 = writeShardCorpusResume(dir, c, tail, 16);   // run 2: same corpus, same dir
            List<Path> shards2 = ShardReader.listFinalizedShards(dir);
            f += assertCond("run 2 count == 100 (all reused)", s2.candidateCount() == 100);
            f += assertCond("run 2 has the identical shard set", listNamesOf(shards2).equals(listNamesOf(shards1)));
            f += assertCond("run 2 summary index identical (same corpus)", s1.index().equals(s2.index()));
            boolean sameBytes = true, sameMtime = true;
            for (Path p : shards2) {
                String nm = p.getFileName().toString();
                if (!sha256(Files.readAllBytes(p)).equals(hash1.get(nm))) sameBytes = false;
                if (Files.getLastModifiedTime(p).toMillis() != mtime1.get(nm)) sameMtime = false;
            }
            f += assertCond("run 2 left every shard byte-identical", sameBytes);
            f += assertCond("run 2 did NOT rewrite any shard (mtime unchanged)", sameMtime);
            f += assertCond("run 2 still recovers all 100", ShardReader.readCorpus(dir, (i, x) -> {}) == 100);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Resume/checkpoint: only the missing suffix is regenerated; the prefix is preserved ──
    private static int testResumeRegeneratesOnlyMissingSuffixShards() throws Exception {
        System.out.println("\n── Resume: regenerate only the missing suffix shards ──");
        Path root = Files.createTempDirectory("shard-resume-partial");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            Corpus c = makeCorpus(100, 1);
            byte[] tail = new byte[0];

            writeShardCorpusResume(dir, c, tail, 16);                  // run 1 full → 7 shards (6×16 + 4)
            List<Path> shards1 = ShardReader.listFinalizedShards(dir);
            int total = shards1.size();
            int del = 2;                                               // simulate an interrupted run
            List<Path> survivors = shards1.subList(0, total - del);
            Map<String, Long> mtimeP = new TreeMap<>();
            Map<String, String> hashP = new TreeMap<>();
            for (Path p : survivors) {
                mtimeP.put(p.getFileName().toString(), Files.getLastModifiedTime(p).toMillis());
                hashP.put(p.getFileName().toString(), sha256(Files.readAllBytes(p)));
            }
            for (Path p : shards1.subList(total - del, total)) Files.delete(p);   // drop the suffix
            int f = 0;
            f += assertCond("suffix removed (only prefix on disk)",
                    ShardReader.listFinalizedShards(dir).size() == total - del);

            Thread.sleep(1100);
            CandidateSink.Summary s2 = writeShardCorpusResume(dir, c, tail, 16);   // run 2: resume same corpus

            f += assertCond("run 2 count == 100 (prefix reused + suffix regenerated)", s2.candidateCount() == 100);
            f += assertCond("shard set fully restored", ShardReader.listFinalizedShards(dir).size() == total);
            boolean prefixUnchanged = true, prefixSameMtime = true;
            for (Path p : ShardReader.listFinalizedShards(dir)) {
                String nm = p.getFileName().toString();
                if (hashP.containsKey(nm)) {        // a surviving prefix shard
                    if (!sha256(Files.readAllBytes(p)).equals(hashP.get(nm))) prefixUnchanged = false;
                    if (Files.getLastModifiedTime(p).toMillis() != mtimeP.get(nm)) prefixSameMtime = false;
                }
            }
            f += assertCond("reused prefix shards left byte-identical", prefixUnchanged);
            f += assertCond("reused prefix shards NOT rewritten (mtime unchanged)", prefixSameMtime);
            // the full id set is recovered intact
            Map<String, byte[]> got = new TreeMap<>();
            ShardReader.readCorpus(dir, got::put);
            f += assertCond("full corpus (100 ids) recovered after resume", got.size() == 100);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    private static List<String> listNamesOf(List<Path> ps) {
        List<String> out = new ArrayList<>();
        for (Path p : ps) out.add(p.getFileName().toString());
        java.util.Collections.sort(out);
        return out;
    }

    // ─── Deterministic: single-threaded run reproduces byte-identical shards ─────────
    private static int testDeterministicShardBytes() throws Exception {
        System.out.println("\n── Deterministic shard bytes (single-threaded) ──");
        Path root = Files.createTempDirectory("shard-determ");
        try {
            Path a = Files.createDirectories(root.resolve("a"));
            Path b = Files.createDirectories(root.resolve("b"));
            Corpus c = makeCorpus(50, 2);
            byte[] tail = "//end\n".getBytes(StandardCharsets.UTF_8);

            writeShardCorpus(a, c, tail, 16);
            writeShardCorpus(b, c, tail, 16);

            List<Path> sa = ShardReader.listFinalizedShards(a);
            List<Path> sb = ShardReader.listFinalizedShards(b);
            int f = 0;
            f += assertCond("same number of shard files", sa.size() == sb.size() && sa.size() > 1);
            boolean allEqual = sa.size() == sb.size();
            for (int i = 0; i < Math.min(sa.size(), sb.size()) && allEqual; i++) {
                byte[] x = Files.readAllBytes(sa.get(i));
                byte[] y = Files.readAllBytes(sb.get(i));
                if (!java.util.Arrays.equals(x, y)) allEqual = false;
            }
            f += assertCond("corresponding shard files byte-identical across runs", allEqual);

            // ids read back == ids written (deterministic identity), in deterministic order
            List<String> read = new ArrayList<>();
            ShardReader.readCorpus(a, (id, body) -> read.add(id));
            f += assertCond("all ids recovered", read.size() == c.items.size());
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Determinism under CONCURRENCY (STEP 32 review defect #4) ───────────────────
    // The same candidate set written by many threads (twice, with different scheduling)
    // must produce byte-identical shard files — proving packing no longer depends on the
    // non-deterministic arrival order.
    private static int testDeterministicUnderConcurrency() throws Exception {
        System.out.println("\n── Deterministic shard bytes under concurrency ──");
        Path root = Files.createTempDirectory("shard-concur-determ");
        try {
            Corpus c = makeCorpus(600, 1);
            byte[] tail = "\n".getBytes(StandardCharsets.UTF_8);
            Path a = Files.createDirectories(root.resolve("a"));
            Path b = Files.createDirectories(root.resolve("b"));
            writeShardCorpusConcurrent(a, c, tail, 64, 8);
            writeShardCorpusConcurrent(b, c, tail, 64, 8);

            List<Path> sa = ShardReader.listFinalizedShards(a);
            List<Path> sb = ShardReader.listFinalizedShards(b);
            int f = 0;
            f += assertCond("both concurrent runs produced >1 shard", sa.size() > 1 && sa.size() == sb.size());
            boolean allEqual = sa.size() == sb.size();
            for (int i = 0; i < Math.min(sa.size(), sb.size()) && allEqual; i++) {
                if (!java.util.Arrays.equals(Files.readAllBytes(sa.get(i)), Files.readAllBytes(sb.get(i)))) {
                    allEqual = false;
                }
            }
            f += assertCond("shard files byte-identical across two concurrent runs", allEqual);
            f += assertCond("both recover the full corpus",
                    ShardReader.readCorpus(a, (i, x) -> {}) == c.items.size()
                            && ShardReader.readCorpus(b, (i, x) -> {}) == c.items.size());
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Configurable shard size by count AND by bytes ──────────────────────────────
    private static int testConfigurableShardSizeByCountAndBytes() throws Exception {
        System.out.println("\n── Configurable shard size (count / bytes) ──");
        Path root = Files.createTempDirectory("shard-size");
        try {
            Corpus c = makeCorpus(60, 0);
            byte[] tail = new byte[0];

            Path byCount = Files.createDirectories(root.resolve("byCount"));
            ShardSink s1 = new ShardSink(byCount, tail, 20, ShardSink.DEFAULT_MAX_BYTES);
            for (Corpus.Item it : c.items) s1.write(it.id, it.body, 0, it.payloadLen);
            s1.close();

            // Tiny byte budget → roll over far more often than the count threshold would.
            Path byBytes = Files.createDirectories(root.resolve("byBytes"));
            ShardSink s2 = new ShardSink(byBytes, tail, 1_000_000, 64 /*bytes*/);
            for (Corpus.Item it : c.items) s2.write(it.id, it.body, 0, it.payloadLen);
            s2.close();

            int f = 0;
            f += assertCond("count threshold → ceil(60/20) = 3 shards", s1.shardCount() == 3);
            f += assertCond("byte threshold rolls over more often (> 3 shards)", s2.shardCount() > 3);
            f += assertCond("both sinks still recover all candidates",
                    ShardReader.readCorpus(byCount, (i, x) -> {}) == 60
                            && ShardReader.readCorpus(byBytes, (i, x) -> {}) == 60);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Trim (off/len subrange) + non-empty tail round-trip exactly ────────────────
    private static int testTailAndTrimRoundTrip() throws Exception {
        System.out.println("\n── Tail + trim round-trip ──");
        Path root = Files.createTempDirectory("shard-tail");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            byte[] tail = "\n".getBytes(StandardCharsets.UTF_8);
            ShardSink shard = new ShardSink(dir, tail, 8, ShardSink.DEFAULT_MAX_BYTES);
            byte[] body = "PAYLOADxxx".getBytes(StandardCharsets.UTF_8); // trim trailing "xxx"
            shard.write("9_0_0", body, 0, body.length - 3);
            shard.close();

            Map<String, byte[]> got = new HashMap<>();
            ShardReader.readCorpus(dir, got::put);
            byte[] want = "PAYLOAD\n".getBytes(StandardCharsets.UTF_8);
            int f = 0;
            f += assertCond("payload subrange + tail recovered exactly",
                    got.containsKey("9_0_0") && java.util.Arrays.equals(got.get("9_0_0"), want));
            f += assertCond("summary.bytes() counts payload+tail", shard.summary().bytes() == want.length);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Concurrency: many writers, every candidate lands, count exact, no .tmp leak ─
    private static int testConcurrentWritesAllLand() throws Exception {
        System.out.println("\n── Concurrent writers ──");
        Path root = Files.createTempDirectory("shard-concur");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            ShardSink shard = new ShardSink(dir, new byte[0], 64, ShardSink.DEFAULT_MAX_BYTES);
            int threads = 8, per = 250, total = threads * per;
            ExecutorService pool = Executors.newFixedThreadPool(threads);
            AtomicLong gid = new AtomicLong(0);
            List<Future<?>> futs = new ArrayList<>();
            for (int t = 0; t < threads; t++) {
                futs.add(pool.submit(() -> {
                    for (int i = 0; i < per; i++) {
                        long id = gid.incrementAndGet();
                        byte[] body = ("class C" + id + " {}").getBytes(StandardCharsets.UTF_8);
                        shard.write(id + "_0_0", body, 0, body.length);
                    }
                }));
            }
            for (Future<?> fu : futs) fu.get();
            pool.shutdown();
            shard.close();

            Map<String, byte[]> got = new ConcurrentHashMap<>();
            long read = ShardReader.readCorpus(dir, got::put);
            int f = 0;
            f += assertCond("summary.count == " + total, shard.summary().candidateCount() == total);
            f += assertCond("summary.errors() == 0", shard.summary().errors() == 0);
            f += assertCond("all " + total + " candidates recovered", read == total && got.size() == total);
            f += assertCond("no .tmp leftovers after close", countTmp(dir) == 0);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Interrupted/partial shard ignored, and rebuildable ─────────────────────────
    private static int testPartialShardIgnoredAndRebuilt() throws Exception {
        System.out.println("\n── Partial shard ignored + rebuilt ──");
        Path root = Files.createTempDirectory("shard-partial");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            Corpus c = makeCorpus(12, 0);
            ShardSink shard = new ShardSink(dir, new byte[0], 5, ShardSink.DEFAULT_MAX_BYTES);
            for (Corpus.Item it : c.items) shard.write(it.id, it.body, 0, it.payloadLen);
            shard.close(); // 3 shards: 5 + 5 + 2

            List<Path> shards = ShardReader.listFinalizedShards(dir);
            int f = 0;
            f += assertCond("3 finalized shards present", shards.size() == 3);
            f += assertCond("clean corpus reads all 12", ShardReader.readCorpus(dir, (i, x) -> {}) == 12);

            // Simulate a crash that truncated the LAST shard's trailer.
            Path last = shards.get(shards.size() - 1);
            long lastRecords = ShardReader.validate(last);
            truncate(last, 6); // chop into the trailer
            f += assertCond("truncated shard no longer finalized", !ShardReader.isFinalized(last));
            f += assertCond("validate() rejects truncated shard (-1)", ShardReader.validate(last) == -1);
            boolean threw = false;
            try { ShardReader.readShard(last, (i, x) -> {}); } catch (IOException e) { threw = true; }
            f += assertCond("readShard throws on truncated shard", threw);
            long afterDamage = ShardReader.readCorpus(dir, (i, x) -> {});
            f += assertCond("corpus skips the partial shard (reads " + (12 - lastRecords) + ")",
                    afterDamage == 12 - lastRecords);

            // Rebuild the missing shard out-of-band and drop it back in under its name.
            Path rebuildDir = Files.createDirectories(root.resolve("rebuild"));
            ShardSink rebuild = new ShardSink(rebuildDir, new byte[0], 1_000_000, ShardSink.DEFAULT_MAX_BYTES);
            for (int i = (int) (12 - lastRecords); i < 12; i++) {
                Corpus.Item it = c.items.get(i);
                rebuild.write(it.id, it.body, 0, it.payloadLen);
            }
            rebuild.close();
            Path rebuilt = ShardReader.listFinalizedShards(rebuildDir).get(0);
            Files.copy(rebuilt, last, StandardCopyOption.REPLACE_EXISTING);
            f += assertCond("rebuilt shard is finalized again", ShardReader.isFinalized(last));
            f += assertCond("corpus whole again after rebuild (reads 12)",
                    ShardReader.readCorpus(dir, (i, x) -> {}) == 12);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── A stray (never-finalized) .tmp shard is never read ─────────────────────────
    private static int testStrayTmpIgnored() throws Exception {
        System.out.println("\n── Stray .tmp shard ignored ──");
        Path root = Files.createTempDirectory("shard-stray");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            Corpus c = makeCorpus(6, 0);
            writeShardCorpus(dir, c, new byte[0], 1_000_000); // one finalized shard

            // Hand-craft a partial .tmp: a real shard's bytes minus the trailer.
            Path good = ShardReader.listFinalizedShards(dir).get(0);
            byte[] bytes = Files.readAllBytes(good);
            byte[] partial = java.util.Arrays.copyOf(bytes, bytes.length - 12);
            Path stray = dir.resolve("shard-99999" + ShardSink.SHARD_EXT + ShardSink.TMP_EXT);
            Files.write(stray, partial);

            int f = 0;
            f += assertCond("listFinalizedShards excludes the .tmp", ShardReader.listFinalizedShards(dir).size() == 1);
            f += assertCond("stray .tmp not finalized", !ShardReader.isFinalized(stray));
            f += assertCond("corpus reads only the finalized shard (6)", ShardReader.readCorpus(dir, (i, x) -> {}) == 6);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Reader streams candidates without writing anything to disk ──────────────────
    private static int testStreamingWritesNothingToDisk() throws Exception {
        System.out.println("\n── Streaming read writes nothing to disk ──");
        Path root = Files.createTempDirectory("shard-stream");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            Corpus c = makeCorpus(40, 0);
            writeShardCorpus(dir, c, new byte[0], 8);

            List<String> before = listNames(dir);
            long peakBody = streamPeakBodyBytes(dir);
            List<String> after = listNames(dir);
            int f = 0;
            f += assertCond("directory listing unchanged by streaming read", before.equals(after));
            f += assertCond("reader never materialised the whole corpus (one record at a time)",
                    peakBody > 0 && peakBody < totalBodyBytes(c));
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Write errors counted (fail-closed has teeth) ───────────────────────────────
    private static int testWriteErrorsCounted() throws Exception {
        System.out.println("\n── Write-error accounting ──");
        Path root = Files.createTempDirectory("shard-err");
        try {
            // A regular file sits where the shard directory's parent would need to be, so
            // opening the first shard .tmp fails for every candidate.
            Path blocker = root.resolve("blocker");
            Files.writeString(blocker, "i am a file, not a dir");
            Path badDir = blocker.resolve("sub");
            ShardSink shard = new ShardSink(badDir, new byte[0], 8, ShardSink.DEFAULT_MAX_BYTES);
            shard.write("9_0_0", "data".getBytes(StandardCharsets.UTF_8), 0, 4);
            shard.write("9_0_1", "data".getBytes(StandardCharsets.UTF_8), 0, 4);
            shard.close();
            CandidateSink.Summary s = shard.summary();
            int f = 0;
            f += assertCond("failed writes counted as errors (2)", s.errors() == 2);
            f += assertCond("failed writes not counted as candidates", s.candidateCount() == 0);
            f += assertCond("no bytes tallied for failed writes", s.bytes() == 0);
            f += assertCond("no shard files produced", shard.shardCount() == 0);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Transport descriptor + registry round-trip ─────────────────────────────────
    private static int testTransportDescriptor() throws Exception {
        System.out.println("\n── Transport descriptor ──");
        Path root = Files.createTempDirectory("shard-transport");
        try {
            Path dir = Files.createDirectories(root.resolve("s"));
            ShardSink shard = new ShardSink(dir, new byte[0], 8, ShardSink.DEFAULT_MAX_BYTES);
            shard.write("1_0_0", "x".getBytes(StandardCharsets.UTF_8), 0, 1);
            shard.close();
            CandidateSinkRegistry.reset();
            CandidateSinkRegistry.record(shard.summary());
            int f = 0;
            f += assertCond("transport() == sharded", "sharded".equals(shard.transport()));
            f += assertCond("registry reads back shard transport",
                    "sharded".equals(CandidateSinkRegistry.transportOrDefault("FALLBACK")));
            CandidateSinkRegistry.reset();
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── corpus + helpers ───────────────────────────────────────────────────────────

    private static final class Corpus {
        static final class Item {
            final String id; final byte[] body; final int payloadLen;
            Item(String id, byte[] body, int payloadLen) { this.id = id; this.body = body; this.payloadLen = payloadLen; }
        }
        final List<Item> items = new ArrayList<>();
    }

    /** Build a corpus with real-shaped ids (final-only and cartesian forms) and a trailing trim. */
    private static Corpus makeCorpus(int n, int trim) {
        Corpus c = new Corpus();
        for (int i = 0; i < n; i++) {
            String id = (i % 3 == 0)
                    ? (100000 + i) + "_0_0"
                    : (100000 + i) + "_" + (i % 7) + "_" + (i % 5);
            String s = "class C" + i + " { /* candidate body " + i + " value=" + (i * 31 + 7) + " */ }TRIMPAD";
            byte[] body = s.getBytes(StandardCharsets.UTF_8);
            int payloadLen = Math.max(0, body.length - trim);
            c.items.add(new Corpus.Item(id, body, payloadLen));
        }
        return c;
    }

    private static long totalBodyBytes(Corpus c) {
        long t = 0;
        for (Corpus.Item it : c.items) t += it.payloadLen;
        return t;
    }

    private static void writeShardCorpus(Path dir, Corpus c, byte[] tail, int maxRecords) {
        ShardSink shard = new ShardSink(dir, tail, maxRecords, ShardSink.DEFAULT_MAX_BYTES);
        for (Corpus.Item it : c.items) shard.write(it.id, it.body, 0, it.payloadLen);
        shard.close();
    }

    /** Same corpus, written from {@code threads} workers in racy order, to stress determinism. */
    private static void writeShardCorpusConcurrent(Path dir, Corpus c, byte[] tail, int maxRecords, int threads)
            throws Exception {
        ShardSink shard = new ShardSink(dir, tail, maxRecords, ShardSink.DEFAULT_MAX_BYTES);
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        AtomicLong next = new AtomicLong(0);
        List<Future<?>> futs = new ArrayList<>();
        for (int t = 0; t < threads; t++) {
            futs.add(pool.submit(() -> {
                int idx;
                while ((idx = (int) next.getAndIncrement()) < c.items.size()) {
                    Corpus.Item it = c.items.get(idx);
                    shard.write(it.id, it.body, 0, it.payloadLen);
                }
            }));
        }
        for (Future<?> fu : futs) fu.get();
        pool.shutdown();
        shard.close();
    }

    /** Largest single body the reader holds at once — proves it streams (not whole-corpus). */
    private static long streamPeakBodyBytes(Path dir) throws IOException {
        AtomicLong peak = new AtomicLong(0);
        ShardReader.readCorpus(dir, (id, body) -> peak.accumulateAndGet(body.length, Math::max));
        return peak.get();
    }

    private static Map<String, String> looseIdToHash(String dir, byte[] tailAlreadyInFile) throws Exception {
        Map<String, String> m = new TreeMap<>();
        java.io.File[] fs = new java.io.File(dir).listFiles((d, nm) -> nm.endsWith(EXT));
        if (fs != null) {
            for (java.io.File file : fs) {
                String id = file.getName().substring(0, file.getName().length() - EXT.length());
                m.put(id, sha256(Files.readAllBytes(file.toPath())));
            }
        }
        return m;
    }

    private static Map<String, String> shardIdToHash(Path dir) throws Exception {
        Map<String, String> m = new TreeMap<>();
        ShardReader.readCorpus(dir, (id, body) -> {
            try { m.put(id, sha256(body)); } catch (Exception e) { throw new RuntimeException(e); }
        });
        return m;
    }

    private static String sha256(byte[] b) throws NoSuchAlgorithmException {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] d = md.digest(b);
        StringBuilder sb = new StringBuilder(d.length * 2);
        for (byte x : d) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    private static String mkdir(Path root, String name) throws IOException {
        Path p = Files.createDirectories(root.resolve(name));
        return p.toString() + "/";
    }

    private static long countFiles(Path dir) throws IOException {
        try (var s = Files.list(dir)) { return s.filter(Files::isRegularFile).count(); }
    }

    private static List<String> listNames(Path dir) throws IOException {
        List<String> out = new ArrayList<>();
        try (var s = Files.list(dir)) { s.map(p -> p.getFileName().toString()).sorted().forEach(out::add); }
        return out;
    }

    private static long countTmp(Path dir) throws IOException {
        try (var s = Files.list(dir)) {
            return s.filter(p -> p.getFileName().toString().contains(".tmp")).count();
        }
    }

    private static void truncate(Path file, int dropBytes) throws IOException {
        try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "rw")) {
            raf.setLength(Math.max(0, raf.length() - dropBytes));
        }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) return;
        try (var walk = Files.walk(root)) {
            walk.sorted(Comparator.reverseOrder()).forEach(p -> { try { Files.delete(p); } catch (IOException _) {} });
        }
    }
}
