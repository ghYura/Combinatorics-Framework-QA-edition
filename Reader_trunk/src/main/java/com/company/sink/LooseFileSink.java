package com.company.sink;

import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * STEP 31 — the loose-file {@link CandidateSink}: one file per candidate, named
 * {@code <dir><candidateId><extension>}, written atomically. This is a
 * behaviour-preserving extraction of the inline file-write that used to live in
 * {@code ComboGenerationPipeline}'s two {@code FILES_MODE} branches; the on-disk
 * bytes, filenames, and directory round-robin are unchanged.
 *
 * <p>Write recipe (verbatim from the legacy inline path, GI-winner
 * {@code W14_tmpatomicretry}): pick an output directory by thread-safe round-robin,
 * write {@code payload + tail} into a sibling {@code .tmp.<threadId>} file through a
 * {@link BufferedOutputStream}, then {@link StandardCopyOption#ATOMIC_MOVE} it onto
 * the final name — so the Executor's directory watcher never observes a torn or
 * partial candidate. Up to three attempts survive transient I/O errors.
 *
 * <p>Thread-safe: {@link #write} is invoked concurrently from many virtual-thread
 * writers. All counters are atomic and each candidate writes to its own unique
 * path, so there is no shared mutable file state.
 */
public final class LooseFileSink implements CandidateSink {

    /** Transport descriptor recorded in the Handoff v2 manifest. */
    public static final String TRANSPORT = "loose-files";

    private static final int MAX_ATTEMPTS = 3;

    private final String[] dirs;
    private final String extension;
    private final byte[] tail;

    /** Round-robin index over {@link #dirs}; replaces the legacy {@code Main.__dirRR}. */
    private final AtomicInteger dirRR = new AtomicInteger(0);
    private final AtomicLong count = new AtomicLong(0);
    private final AtomicLong bytes = new AtomicLong(0);
    private final AtomicLong errors = new AtomicLong(0);
    /** Order-independent (XOR-folded) fingerprint of the candidate-id set. */
    private final AtomicLong indexXor = new AtomicLong(0);

    private volatile boolean closed = false;

    /**
     * @param outputDirs  candidate output directories (each is concatenated verbatim
     *                    with the id, so callers pass them with their trailing
     *                    separator as in {@code reader.out.outZipDirPathList}).
     * @param extension   file extension appended after the id (e.g. {@code .java});
     *                    {@code null} is treated as empty.
     * @param tail        bytes appended after the payload of every file (the
     *                    framework's {@code bArr} — empty in FILES_MODE); {@code null}
     *                    is treated as empty. A defensive copy is taken.
     */
    public LooseFileSink(List<String> outputDirs, String extension, byte[] tail) {
        if (outputDirs == null || outputDirs.isEmpty()) {
            throw new IllegalArgumentException("LooseFileSink requires at least one output directory");
        }
        this.dirs = outputDirs.toArray(new String[0]);
        this.extension = (extension == null) ? "" : extension;
        this.tail = (tail == null) ? new byte[0] : tail.clone();
        // Defensive, idempotent: the live Reader already pre-creates these in
        // ReaderConfig.loadProperties(); creating here keeps the sink self-sufficient
        // (e.g. for focused emission tests) without changing production behaviour.
        for (String d : this.dirs) {
            if (d == null || d.isBlank()) continue;
            try {
                Files.createDirectories(Path.of(d.endsWith("/") ? d.substring(0, d.length() - 1) : d));
            } catch (IOException _) {
                // Mirror legacy tolerance: a missing dir surfaces later as a write error.
            }
        }
    }

    @Override
    public void write(String candidateId, byte[] content, int off, int len) {
        if (closed) throw new IllegalStateException("LooseFileSink is closed");
        final String dir = dirs[Math.floorMod(dirRR.getAndIncrement(), dirs.length)];
        final String finPath = dir + candidateId + extension;
        final String tmpPath = finPath + ".tmp." + Thread.currentThread().threadId();
        final int n = Math.max(0, len);
        boolean ok = false;
        for (int att = 0; att < MAX_ATTEMPTS; att++) {
            try {
                // perf 2026-07-02: write the two byte runs directly — a BufferedOutputStream
                // here only added an 8KB allocation + extra memcpy per candidate.
                try (OutputStream fos = new FileOutputStream(tmpPath, false)) {
                    fos.write(content, off, n);
                    if (tail.length > 0) fos.write(tail);
                }
                Files.move(Paths.get(tmpPath), Paths.get(finPath), StandardCopyOption.ATOMIC_MOVE);
                ok = true;
                break;
            } catch (IOException e) {
                if (att == MAX_ATTEMPTS - 1) e.printStackTrace();
            }
        }
        if (ok) {
            count.incrementAndGet();
            bytes.addAndGet((long) n + tail.length);
            // XOR-fold keeps the fingerprint independent of concurrent write order.
            final long h = fnv1a64(candidateId);
            indexXor.accumulateAndGet(h, (a, b) -> a ^ b);
        } else {
            errors.incrementAndGet();
        }
    }

    @Override
    public String transport() {
        return TRANSPORT;
    }

    @Override
    public Summary summary() {
        return new Summary(TRANSPORT, count.get(), bytes.get(), errors.get(),
                String.format("%016x", indexXor.get()));
    }

    @Override
    public void close() {
        closed = true; // each candidate is opened/flushed/closed per write; nothing buffered to drain
    }

    /** 64-bit FNV-1a — a fast, non-cryptographic hash for the order-independent index. */
    private static long fnv1a64(String s) {
        long h = 0xcbf29ce484222325L;
        byte[] b = s.getBytes(StandardCharsets.UTF_8);
        for (byte x : b) {
            h ^= (x & 0xffL);
            h *= 0x100000001b3L;
        }
        return h;
    }
}
