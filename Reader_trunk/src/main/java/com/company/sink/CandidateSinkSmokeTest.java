package com.company.sink;

import java.io.BufferedOutputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentSkipListSet;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;

/**
 * STEP 31 verifier for the candidate-sink abstraction. Exercises {@link LooseFileSink}
 * directly — a focused "tiny Reader emission" that needs no PostgreSQL and no full
 * candidate-generation pipeline — and proves the STEP 31 acceptance criteria:
 *
 * <ul>
 *   <li><b>Loose-file output byte-compatible</b>: the same candidates written through
 *       the sink and through an inline replica of the legacy recipe produce identical
 *       file names and identical bytes.</li>
 *   <li><b>Count summary authoritative</b>: the sink's own count/bytes/errors tally
 *       matches what actually landed on disk, single- and multi-threaded.</li>
 *   <li><b>Pipeline knows no filename details</b>: filename, directory round-robin,
 *       trailing bytes, temp+atomic-move all live behind {@link CandidateSink#write}.</li>
 * </ul>
 *
 * Run:  java -cp ... com.company.sink.CandidateSinkSmokeTest
 */
public final class CandidateSinkSmokeTest {
    private CandidateSinkSmokeTest() {}

    private static final String EXT = ".java";

    public static void main(String[] args) throws Exception {
        int failures = 0;
        failures += testByteCompatibleWithLegacyRecipe();
        failures += testCountSummaryAuthoritative();
        failures += testTailAndTrimHandling();
        failures += testIndexOrderIndependent();
        failures += testMultiDirRoundRobin();
        failures += testConcurrentWritesAllLand();
        failures += testWriteErrorsCounted();
        failures += testRegistryTransport();

        System.out.println();
        if (failures == 0) System.out.println("✅ ALL CANDIDATE-SINK SMOKE CHECKS PASSED");
        else { System.out.println("❌ " + failures + " CANDIDATE-SINK SMOKE CHECK(S) FAILED"); System.exit(1); }
    }

    // ─── Byte-for-byte parity with the legacy inline write ──────────────────────────
    private static int testByteCompatibleWithLegacyRecipe() throws IOException {
        System.out.println("\n── Byte-compatible vs legacy inline recipe ──");
        Path root = Files.createTempDirectory("candsink-bytecompat");
        try {
            String sinkDir = root.resolve("sink").toString() + "/";
            String refDir = root.resolve("ref").toString() + "/";
            Files.createDirectories(Paths.get(sinkDir));
            Files.createDirectories(Paths.get(refDir));

            byte[] tail = new byte[0]; // FILES_MODE: bArr is empty
            CandidateSink sink = new LooseFileSink(List.of(sinkDir), EXT, tail);

            // A handful of candidates with the real id shapes (final-only + cartesian).
            String[] ids = {"100000_0_0", "100001_0_0", "100000_5_1", "200000_12_3"};
            int trim = 3; // emulate a non-empty sheet-ending trim (FW_B_ARR empty branch)
            for (int i = 0; i < ids.length; i++) {
                byte[] body = ("class C" + i + " { /* body " + i + " */ }TRIM").getBytes(StandardCharsets.UTF_8);
                int n = Math.max(0, body.length - trim);
                sink.write(ids[i], body, 0, n);
                legacyWrite(refDir, ids[i], EXT, body, trim, tail);
            }
            sink.close();

            int f = 0;
            f += assertCond("no .tmp.* leftovers in sink dir", countTmp(sinkDir) == 0);
            f += assertCond("sink wrote " + ids.length + " files", listCandidates(sinkDir).size() == ids.length);
            f += assertCond("file name set identical to legacy recipe",
                    listCandidates(sinkDir).equals(listCandidates(refDir)));
            boolean bytesEqual = true;
            for (String name : listCandidates(sinkDir)) {
                byte[] a = Files.readAllBytes(Paths.get(sinkDir + name));
                byte[] b = Files.readAllBytes(Paths.get(refDir + name));
                if (!Arrays.equals(a, b)) { bytesEqual = false; break; }
            }
            f += assertCond("every file byte-identical to legacy recipe", bytesEqual);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── The summary count/bytes is authoritative (matches disk) ────────────────────
    private static int testCountSummaryAuthoritative() throws IOException {
        System.out.println("\n── Count summary authoritative ──");
        Path root = Files.createTempDirectory("candsink-count");
        try {
            String dir = root.toString() + "/";
            CandidateSink sink = new LooseFileSink(List.of(dir), EXT, new byte[0]);
            int n = 37;
            long expectedBytes = 0;
            for (int i = 0; i < n; i++) {
                byte[] body = ("candidate-" + i).getBytes(StandardCharsets.UTF_8);
                sink.write(i + "_0_0", body, 0, body.length);
                expectedBytes += body.length;
            }
            sink.close();
            CandidateSink.Summary s = sink.summary();

            int f = 0;
            f += assertCond("summary.transport() == loose-files", "loose-files".equals(s.transport()));
            f += assertCond("summary.candidateCount() == " + n, s.candidateCount() == n);
            f += assertCond("summary.candidateCount() == files on disk",
                    s.candidateCount() == listCandidates(dir).size());
            f += assertCond("summary.bytes() == sum of payloads (" + expectedBytes + ")", s.bytes() == expectedBytes);
            f += assertCond("summary.errors() == 0", s.errors() == 0);
            f += assertCond("summary.index() is 16 hex chars", s.index() != null && s.index().matches("[0-9a-f]{16}"));
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Trim (off/len subrange) + non-empty tail land exactly ──────────────────────
    private static int testTailAndTrimHandling() throws IOException {
        System.out.println("\n── Tail + trim handling ──");
        Path root = Files.createTempDirectory("candsink-tail");
        try {
            String dir = root.toString() + "/";
            byte[] tail = "\n".getBytes(StandardCharsets.UTF_8); // simulate non-empty bArr
            CandidateSink sink = new LooseFileSink(List.of(dir), EXT, tail);
            byte[] body = "PAYLOADxxx".getBytes(StandardCharsets.UTF_8); // trim the trailing "xxx"
            sink.write("9_0_0", body, 0, body.length - 3);
            sink.close();

            byte[] got = Files.readAllBytes(Paths.get(dir + "9_0_0" + EXT));
            byte[] want = "PAYLOAD\n".getBytes(StandardCharsets.UTF_8);
            int f = 0;
            f += assertCond("payload subrange + tail written exactly", Arrays.equals(got, want));
            f += assertCond("summary.bytes() counts payload+tail", sink.summary().bytes() == want.length);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Index is order-independent (deterministic over the id set) ─────────────────
    private static int testIndexOrderIndependent() throws IOException {
        System.out.println("\n── Index order-independence ──");
        Path a = Files.createTempDirectory("candsink-idxA");
        Path b = Files.createTempDirectory("candsink-idxB");
        try {
            String[] ids = {"1_0_0", "2_0_0", "3_0_0", "4_5_1", "5_9_2"};
            CandidateSink s1 = new LooseFileSink(List.of(a.toString() + "/"), EXT, new byte[0]);
            for (String id : ids) s1.write(id, ("x" + id).getBytes(StandardCharsets.UTF_8), 0, 2);
            s1.close();
            // same set, reversed order
            CandidateSink s2 = new LooseFileSink(List.of(b.toString() + "/"), EXT, new byte[0]);
            for (int i = ids.length - 1; i >= 0; i--) s2.write(ids[i], ("x" + ids[i]).getBytes(StandardCharsets.UTF_8), 0, 2);
            s2.close();

            int f = 0;
            f += assertCond("same id set → same index regardless of order",
                    s1.summary().index().equals(s2.summary().index()));
            f += assertCond("index non-zero for non-empty set", !s1.summary().index().equals("0000000000000000"));
            return f;
        } finally {
            deleteRecursively(a);
            deleteRecursively(b);
        }
    }

    // ─── Multiple output dirs: round-robin distributes, union is complete ───────────
    private static int testMultiDirRoundRobin() throws IOException {
        System.out.println("\n── Multi-dir round-robin ──");
        Path root = Files.createTempDirectory("candsink-multidir");
        try {
            String d0 = root.resolve("d0").toString() + "/";
            String d1 = root.resolve("d1").toString() + "/";
            CandidateSink sink = new LooseFileSink(List.of(d0, d1), EXT, new byte[0]);
            int n = 10;
            for (int i = 0; i < n; i++) sink.write(i + "_0_0", ("c" + i).getBytes(StandardCharsets.UTF_8), 0, 2);
            sink.close();

            int c0 = listCandidates(d0).size();
            int c1 = listCandidates(d1).size();
            int f = 0;
            f += assertCond("union of dirs == " + n + " files", c0 + c1 == n);
            f += assertCond("round-robin split across both dirs (5/5)", c0 == 5 && c1 == 5);
            f += assertCond("sink count == union", sink.summary().candidateCount() == n);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Concurrency: many writers, every candidate lands, count is exact ───────────
    private static int testConcurrentWritesAllLand() throws Exception {
        System.out.println("\n── Concurrent writers ──");
        Path root = Files.createTempDirectory("candsink-concur");
        try {
            String dir = root.toString() + "/";
            CandidateSink sink = new LooseFileSink(List.of(dir), EXT, new byte[0]);
            int threads = 8, per = 250, total = threads * per;
            ExecutorService pool = Executors.newFixedThreadPool(threads);
            AtomicLong gid = new AtomicLong(0);
            List<Future<?>> futs = new ArrayList<>();
            for (int t = 0; t < threads; t++) {
                futs.add(pool.submit(() -> {
                    for (int i = 0; i < per; i++) {
                        long id = gid.incrementAndGet();
                        byte[] body = ("c" + id).getBytes(StandardCharsets.UTF_8);
                        sink.write(id + "_0_0", body, 0, body.length);
                    }
                }));
            }
            for (Future<?> fu : futs) fu.get();
            pool.shutdown();
            sink.close();

            int f = 0;
            f += assertCond("all " + total + " candidates on disk", listCandidates(dir).size() == total);
            f += assertCond("summary.count == " + total, sink.summary().candidateCount() == total);
            f += assertCond("summary.errors() == 0", sink.summary().errors() == 0);
            f += assertCond("no .tmp.* leftovers", countTmp(dir) == 0);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Write failures are counted (so fail-closed reconciliation has teeth) ────────
    private static int testWriteErrorsCounted() throws IOException {
        System.out.println("\n── Write-error accounting ──");
        Path root = Files.createTempDirectory("candsink-err");
        try {
            // Point the sink at an impossible directory: a regular file sits where a parent
            // directory would need to be, so every atomic write fails after its retries.
            Path blocker = root.resolve("blocker");
            Files.writeString(blocker, "i am a file, not a dir");
            String badDir = blocker.resolve("sub").toString() + "/";
            CandidateSink sink = new LooseFileSink(List.of(badDir), EXT, new byte[0]);
            System.out.println("    (expect one intentional write-failure stack trace below)");
            sink.write("9_0_0", "data".getBytes(StandardCharsets.UTF_8), 0, 4);
            sink.close();
            CandidateSink.Summary s = sink.summary();
            int f = 0;
            f += assertCond("failed write counted as error", s.errors() == 1);
            f += assertCond("failed write not counted as candidate", s.candidateCount() == 0);
            f += assertCond("no bytes tallied for failed write", s.bytes() == 0);
            return f;
        } finally {
            deleteRecursively(root);
        }
    }

    // ─── Registry round-trips the sink transport for the manifest writer ────────────
    private static int testRegistryTransport() {
        System.out.println("\n── CandidateSinkRegistry transport ──");
        CandidateSinkRegistry.reset();
        int f = 0;
        f += assertCond("default used when no sink ran",
                "loose-files".equals(CandidateSinkRegistry.transportOrDefault("loose-files")));
        CandidateSinkRegistry.record(new CandidateSink.Summary("loose-files", 3, 99, 0, "deadbeefdeadbeef"));
        f += assertCond("transport read back from recorded summary",
                "loose-files".equals(CandidateSinkRegistry.transportOrDefault("FALLBACK")));
        f += assertCond("last() returns the recorded summary",
                CandidateSinkRegistry.last() != null && CandidateSinkRegistry.last().candidateCount() == 3);
        CandidateSinkRegistry.reset();
        return f;
    }

    // ─── helpers ────────────────────────────────────────────────────────────────────

    /** Inline replica of the legacy ComboGenerationPipeline FILES_MODE write recipe. */
    private static void legacyWrite(String dir, String id, String ext, byte[] outBytes, int trimLen, byte[] tail) {
        String fin = dir + id + ext;
        String tmp = fin + ".tmp." + Thread.currentThread().threadId();
        int n = Math.max(0, outBytes.length - trimLen);
        for (int att = 0; att < 3; att++) {
            try {
                try (OutputStream fos = new FileOutputStream(tmp, false);
                     OutputStream bw = new BufferedOutputStream(fos)) {
                    bw.write(outBytes, 0, n);
                    bw.write(tail);
                }
                Files.move(Paths.get(tmp), Paths.get(fin), StandardCopyOption.ATOMIC_MOVE);
                break;
            } catch (IOException e) {
                if (att == 2) e.printStackTrace();
            }
        }
    }

    private static List<String> listCandidates(String dir) {
        java.io.File[] fs = new java.io.File(dir).listFiles((d, n) -> n.endsWith(EXT));
        ConcurrentSkipListSet<String> names = new ConcurrentSkipListSet<>();
        if (fs != null) for (java.io.File f : fs) names.add(f.getName());
        return new ArrayList<>(names);
    }

    private static long countTmp(String dir) {
        java.io.File[] fs = new java.io.File(dir).listFiles((d, n) -> n.contains(".tmp."));
        return fs == null ? 0 : fs.length;
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
