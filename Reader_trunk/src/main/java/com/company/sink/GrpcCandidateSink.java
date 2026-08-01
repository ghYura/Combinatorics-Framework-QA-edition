package com.company.sink;

import com.company.grpc.Candidate;
import com.company.grpc.CandidateFeedGrpc;
import com.company.grpc.Ping;
import com.company.grpc.Pong;
import com.company.grpc.StreamSummary;
import com.google.protobuf.ByteString;
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;
import io.grpc.stub.ClientCallStreamObserver;
import io.grpc.stub.ClientResponseObserver;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * gRPC candidate transport (2026-07-02) — the live {@link CandidateSink}: instead of
 * persisting one file per candidate, every assembled candidate is streamed to the
 * Executor's {@code -grpcPort} ingestion server ({@code GrpcCandidateReceiver} in
 * Executor_trunk), which routes it through the SAME per-candidate compile/run/record
 * pipeline the directory watcher uses. Selected via
 * {@code reader.out.candidateSink=grpc} + {@code reader.out.grpc.target=host:port}.
 *
 * <p>Contract parity with the file sinks:
 * <ul>
 *   <li><b>Bytes</b> — {@code content[off,off+len) + tail} is exactly what
 *       {@link LooseFileSink} would have written to {@code <id><ext>}.</li>
 *   <li><b>Thread-safe</b> — {@link #write} is called concurrently from many
 *       virtual-thread writers; sends are serialised on an internal monitor.</li>
 *   <li><b>Backpressure</b> — a write BLOCKS while the transport is not ready
 *       (gRPC flow control), so a slow Executor/network throttles the producers the
 *       same way slow disk I/O throttles the loose-file writers.</li>
 *   <li><b>Fail-closed</b> — a preflight {@code PingCheck} aborts the run before any
 *       emission when no Executor is listening; a mid-stream failure counts every
 *       subsequent candidate as an error; at {@link #close()} the Executor's
 *       {@link StreamSummary} receipt is awaited and any received/sent divergence is
 *       recorded as errors — the pipeline's STEP 31 reconciliation then fails the run
 *       and no handoff manifest is written.</li>
 * </ul>
 */
public final class GrpcCandidateSink implements CandidateSink {

    /** Transport descriptor recorded in the Handoff v2 manifest. */
    public static final String TRANSPORT = "grpc";

    /** How long close() waits for the Executor's end-of-stream receipt. */
    private static final long SUMMARY_WAIT_SECONDS = 300;

    private final String target;
    private final ByteString tail;
    private final ManagedChannel channel;

    /** Set by beforeStart before any write can happen (streamCandidates returns it). */
    private final ClientCallStreamObserver<Candidate> requestStream;

    private final Object sendLock = new Object();
    private final CountDownLatch summaryLatch = new CountDownLatch(1);
    private volatile StreamSummary receipt;
    private volatile Throwable streamFailure;

    private final AtomicLong count = new AtomicLong(0);
    private final AtomicLong bytes = new AtomicLong(0);
    private final AtomicLong errors = new AtomicLong(0);
    /** Order-independent (XOR-folded) fingerprint of the candidate-id set — same scheme as LooseFileSink. */
    private final AtomicLong indexXor = new AtomicLong(0);

    private volatile boolean closed = false;

    /**
     * Connects, preflights, and opens the candidate stream. Throws (aborting the run
     * before any candidate is assembled) when the Executor is not reachable.
     *
     * @param target host:port of the Executor's gRPC ingestion server
     * @param tailBytes bytes appended after every payload (the framework's {@code bArr}
     *                  — empty in FILES_MODE); {@code null} treated as empty
     */
    public GrpcCandidateSink(String target, byte[] tailBytes) {
        this.target = target;
        this.tail = (tailBytes == null || tailBytes.length == 0)
                ? ByteString.EMPTY : ByteString.copyFrom(tailBytes);
        this.channel = NettyChannelBuilder.forTarget(target).usePlaintext().build();

        final Pong pong;
        try {
            pong = CandidateFeedGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(10, TimeUnit.SECONDS)
                    .pingCheck(Ping.newBuilder().setSender("reader:" + ProcessHandle.current().pid()).build());
        } catch (RuntimeException preflight) {
            try { channel.shutdownNow(); } catch (RuntimeException _) { }
            throw new IllegalStateException("[sink grpc] preflight PingCheck failed — no Executor listening at "
                    + target + "? (" + preflight + ")", preflight);
        }
        System.out.println("  [sink grpc] connected to executor " + pong.getExecutorId()
                + " at " + target + "  handshakeReady=" + pong.getReady());

        // Open the client-streaming call. The returned observer IS the flow-controlled
        // ClientCallStreamObserver; the response observer captures the receipt / failure.
        io.grpc.stub.StreamObserver<Candidate> req = CandidateFeedGrpc.newStub(channel)
                .streamCandidates(new ClientResponseObserver<Candidate, StreamSummary>() {
                    @Override
                    public void beforeStart(ClientCallStreamObserver<Candidate> rs) {
                        rs.setOnReadyHandler(() -> {
                            synchronized (sendLock) { sendLock.notifyAll(); }
                        });
                    }

                    @Override
                    public void onNext(StreamSummary value) {
                        receipt = value;
                    }

                    @Override
                    public void onError(Throwable t) {
                        streamFailure = t;
                        summaryLatch.countDown();
                        synchronized (sendLock) { sendLock.notifyAll(); }
                    }

                    @Override
                    public void onCompleted() {
                        summaryLatch.countDown();
                        synchronized (sendLock) { sendLock.notifyAll(); }
                    }
                });
        this.requestStream = (ClientCallStreamObserver<Candidate>) req;
    }

    @Override
    public void write(String candidateId, byte[] content, int off, int len) {
        if (closed) throw new IllegalStateException("GrpcCandidateSink is closed");
        final int n = Math.max(0, len);
        ByteString body = ByteString.copyFrom(content, off, n);
        if (!tail.isEmpty()) body = body.concat(tail);
        final Candidate msg = Candidate.newBuilder().setId(candidateId).setContent(body).build();

        synchronized (sendLock) {
            try {
                // gRPC flow control: onNext buffers unboundedly, so gate on isReady —
                // this is what turns a slow Executor into producer backpressure.
                while (streamFailure == null && !requestStream.isReady()) {
                    sendLock.wait(50);
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
                errors.incrementAndGet();
                return;
            }
            if (streamFailure != null) {
                // Stream already broken: every further candidate is an error → the
                // pipeline's reconciliation fails the run (fail-closed), mirroring
                // LooseFileSink's per-write error accounting.
                errors.incrementAndGet();
                return;
            }
            requestStream.onNext(msg);
        }
        count.incrementAndGet();
        bytes.addAndGet((long) n + tail.size());
        final long h = fnv1a64(candidateId);
        indexXor.accumulateAndGet(h, (a, b) -> a ^ b);
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

    /** Half-close, await the Executor's receipt, reconcile, release the channel. */
    @Override
    public void close() {
        if (closed) return;
        closed = true;
        synchronized (sendLock) {
            if (streamFailure == null) {
                try {
                    requestStream.onCompleted();
                } catch (RuntimeException e) {
                    if (streamFailure == null) streamFailure = e;
                }
            }
        }
        boolean got = false;
        try {
            got = summaryLatch.await(SUMMARY_WAIT_SECONDS, TimeUnit.SECONDS);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
        final long sent = count.get();
        if (streamFailure != null) {
            System.err.println("[sink grpc] stream to " + target + " FAILED: " + streamFailure);
            errors.incrementAndGet();
        } else if (!got || receipt == null) {
            System.err.println("[sink grpc] no end-of-stream receipt from " + target
                    + " within " + SUMMARY_WAIT_SECONDS + "s — cannot prove delivery");
            errors.incrementAndGet();
        } else {
            System.out.println("  [sink grpc] executor receipt: received=" + receipt.getReceived()
                    + "  errors=" + receipt.getErrors()
                    + "  executor=" + receipt.getExecutorId()
                    + "  (sent=" + sent + ")");
            if (receipt.getReceived() != sent) {
                System.err.println("[sink grpc] RECEIPT MISMATCH: sent " + sent
                        + " but executor received " + receipt.getReceived());
                errors.incrementAndGet();
            }
            // Executor-side persist/schedule failures are delivery failures too.
            errors.addAndGet(receipt.getErrors());
        }
        channel.shutdown();
        try {
            if (!channel.awaitTermination(10, TimeUnit.SECONDS)) channel.shutdownNow();
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            channel.shutdownNow();
        }
    }

    /** 64-bit FNV-1a — identical to LooseFileSink's, so the index fingerprint is comparable. */
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
