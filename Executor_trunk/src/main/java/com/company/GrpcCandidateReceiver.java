package com.company;

import com.company.grpc.Candidate;
import com.company.grpc.CandidateFeedGrpc;
import com.company.grpc.Ping;
import com.company.grpc.Pong;
import com.company.grpc.StreamSummary;
import io.grpc.Server;
import io.grpc.netty.shaded.io.grpc.netty.NettyServerBuilder;
import io.grpc.stub.StreamObserver;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * gRPC candidate ingestion (2026-07-02) — the Executor side of the Reader's
 * {@code reader.out.candidateSink=grpc} transport. Started by
 * {@code MainWatch -grpcPort <port>}.
 *
 * <p>Design: mirrors the STEP 32 shard streaming precedent
 * ({@code MainWatch.coldStartScanShards}) — each candidate received off the wire is
 * materialised as a private scratch {@code <id>.java} file and handed to the SAME
 * per-candidate pipeline the directory watcher uses
 * ({@code MainWatch.submitGrpcCandidate} → candidate worker pool →
 * {@code processCandidateFileByMode}: compile → run → FW_VAR/FW_CUSTOM_VAR verdict →
 * outcome counters → results DB), so the Executor processes gRPC candidates fully
 * autonomously and byte-identically to file-delivered ones. The scratch file is
 * deleted after processing.
 *
 * <p>Protocol (candidate_feed.proto):
 * <ul>
 *   <li>{@code PingCheck} — cheap preflight; reports whether the legacy handshake
 *       (insert.sql template) has loaded, i.e. verdicts can be recorded.</li>
 *   <li>{@code StreamCandidates} — client-streaming; on the Reader's half-close the
 *       receipt ({@link StreamSummary}: received/errors) is returned, which the
 *       Reader reconciles fail-closed against its sent count.</li>
 * </ul>
 */
public final class GrpcCandidateReceiver {

    private final Server server;
    private final Path scratchDir;
    private final String executorId = "java:" + ProcessHandle.current().pid();
    private final AtomicLong receivedTotal = new AtomicLong(0);
    private final AtomicLong errorsTotal = new AtomicLong(0);
    /** Streams currently open / ever opened — drives MainWatch's -exitWhenComplete
     *  drain condition for the manifest-less gRPC mode (see finishCandidateProcessing). */
    private final AtomicLong openStreams = new AtomicLong(0);
    private volatile boolean anyStreamSeen = false;

    private GrpcCandidateReceiver(Server server, Path scratchDir) {
        this.server = server;
        this.scratchDir = scratchDir;
    }

    /** Bind + start the ingestion server on {@code 127.0.0.1} (the loopback-only
     *  default). Equivalent to {@link #start(String, int)} with the default host. */
    public static GrpcCandidateReceiver start(int port) throws IOException {
        return start(DEFAULT_BIND_HOST, port);
    }

    /** Bind + start the ingestion server on an EXPLICIT interface.
     *
     *  <p>Audit finding F5: this used to be {@code NettyServerBuilder.forPort(port)},
     *  which binds every interface. The Reader targeting {@code 127.0.0.1} did not
     *  constrain that, so a plaintext, unauthenticated candidate channel could be
     *  reachable from the network while the documentation described it as local.
     *
     *  <p>This channel has neither TLS nor peer authentication, so a non-loopback
     *  bind is refused outright rather than merely discouraged: there is no
     *  configuration in which exposing it off-host is correct today. When an
     *  authenticated transport exists, this is the single place that decision is
     *  relaxed.
     *
     *  <p>NettyServerBuilder is used directly (no ServiceLoader lookup) so the fat
     *  "jar-with-dependencies" packaging cannot break it. */
    public static GrpcCandidateReceiver start(String bindHost, int port) throws IOException {
        String host = (bindHost == null || bindHost.isBlank()) ? DEFAULT_BIND_HOST : bindHost.trim();
        requireLoopback(host);
        Path scratch = Files.createTempDirectory("fw-grpc-ingest-java-");
        GrpcCandidateReceiver[] holder = new GrpcCandidateReceiver[1];
        Server server = NettyServerBuilder
                .forAddress(new java.net.InetSocketAddress(java.net.InetAddress.getByName(host), port))
                .addService(new FeedService(holder))
                .build()
                .start();
        GrpcCandidateReceiver r = new GrpcCandidateReceiver(server, scratch);
        holder[0] = r;
        return r;
    }

    /** The only bind host the unauthenticated candidate channel may use by default. */
    public static final String DEFAULT_BIND_HOST = "127.0.0.1";

    // =========================================================================
    // !!! BEHAVIOUR CHANGE vs. 158ab91 -- READ BEFORE "FIXING" A BROKEN SETUP !!!
    // =========================================================================
    // This receiver previously bound every interface. It is now loopback-only,
    // and a non-loopback bind is a hard error rather than a warning.
    //
    // If a remote Reader has stopped reaching this Executor, that is this change,
    // working as intended -- see docs/38_MIGRATION_PHASE_01_05.md.
    //
    // TO REVERT: delete the two throws below (or the call to requireLoopback).
    //   Effect: a PLAINTEXT, UNAUTHENTICATED channel that accepts candidate code
    //   for execution becomes reachable from the network. Anyone who can route to
    //   the port can run arbitrary code on this host. If you need a remote
    //   transport, add TLS and peer authentication -- do not widen the bind.
    // =========================================================================

    /** Reject a wildcard or non-loopback bind address (fail closed).
     *
     *  <p>{@code ::1} is accepted alongside {@code 127.0.0.0/8} and {@code localhost}.
     *  Everything else — including the {@code 0.0.0.0} / {@code ::} wildcards — is an
     *  error, not a warning: a warning on this path would be read once and ignored. */
    static void requireLoopback(String host) throws IOException {
        if ("localhost".equalsIgnoreCase(host) || "::1".equals(host) || "[::1]".equals(host)) return;
        java.net.InetAddress address;
        try {
            address = java.net.InetAddress.getByName(host);
        } catch (java.net.UnknownHostException e) {
            throw new IOException("gRPC candidate receiver bind host '" + host
                    + "' cannot be resolved", e);
        }
        if (address.isAnyLocalAddress()) {
            throw new IOException("refusing to bind the gRPC candidate receiver to the wildcard "
                    + "address '" + host + "': this channel is plaintext and unauthenticated, so it "
                    + "must listen on loopback only (127.0.0.1 or ::1)");
        }
        if (!address.isLoopbackAddress()) {
            throw new IOException("refusing to bind the gRPC candidate receiver to non-loopback "
                    + "address '" + host + "': this channel is plaintext and unauthenticated and is "
                    + "not a remote transport. Keep it on 127.0.0.1 (or ::1)");
        }
    }

    public long receivedTotal() { return receivedTotal.get(); }

    /** True once at least one candidate stream has been opened AND all opened
     *  streams have closed (completed or aborted) — i.e. no more candidates can
     *  arrive from the current feed. Half of the gRPC drain-exit condition. */
    public boolean feedFinished() {
        return anyStreamSeen && openStreams.get() == 0;
    }

    public void shutdown() {
        server.shutdown();
        try {
            if (!server.awaitTermination(10, TimeUnit.SECONDS)) server.shutdownNow();
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            server.shutdownNow();
        }
        try { Files.deleteIfExists(scratchDir); } catch (IOException ignored) { }
    }

    /** Wire-id → filesystem-safe candidate id (ids are digits/underscores in practice;
     *  never trust the wire with path characters). */
    private static String sanitizeId(String id) {
        String s = (id == null || id.isBlank()) ? "unnamed" : id;
        return s.replaceAll("[^A-Za-z0-9_.-]", "_");
    }

    private static final class FeedService extends CandidateFeedGrpc.CandidateFeedImplBase {
        private final GrpcCandidateReceiver[] holder;

        FeedService(GrpcCandidateReceiver[] holder) {
            this.holder = holder;
        }

        @Override
        public void pingCheck(Ping request, StreamObserver<Pong> responseObserver) {
            GrpcCandidateReceiver r = holder[0];
            responseObserver.onNext(Pong.newBuilder()
                    .setExecutorId(r != null ? r.executorId : "java:starting")
                    .setReady(MainWatch.isInsertTemplateLoaded())
                    .build());
            responseObserver.onCompleted();
            System.out.println("MainWatch[grpc]: PingCheck from \"" + request.getSender()
                    + "\"  handshakeReady=" + MainWatch.isInsertTemplateLoaded());
        }

        @Override
        public StreamObserver<Candidate> streamCandidates(StreamObserver<StreamSummary> responseObserver) {
            final GrpcCandidateReceiver r = holder[0];
            final AtomicLong received = new AtomicLong(0);
            final AtomicLong errors = new AtomicLong(0);
            final long startNanos = System.nanoTime();
            r.anyStreamSeen = true;
            r.openStreams.incrementAndGet();
            System.out.println("MainWatch[grpc]: candidate stream OPENED");

            return new StreamObserver<>() {
                @Override
                public void onNext(Candidate c) {
                    try {
                        Path cand = r.scratchDir.resolve(sanitizeId(c.getId()) + ".java");
                        Files.write(cand, c.getContent().toByteArray());
                        MainWatch.submitGrpcCandidate(cand);
                        long n = received.incrementAndGet();
                        r.receivedTotal.incrementAndGet();
                        if ((n % 100_000) == 0) {
                            System.out.println("MainWatch[grpc]: received=" + n
                                    + "  elapsed_sec=" + ((System.nanoTime() - startNanos) / 1_000_000_000L));
                        }
                    } catch (Exception e) {
                        errors.incrementAndGet();
                        r.errorsTotal.incrementAndGet();
                        System.err.println("MainWatch[grpc]: candidate persist/schedule FAILED (id="
                                + c.getId() + "): " + e);
                    }
                }

                @Override
                public void onError(Throwable t) {
                    r.openStreams.decrementAndGet();
                    System.err.println("MainWatch[grpc]: candidate stream ABORTED by peer after received="
                            + received.get() + ": " + t);
                    MainWatch.maybeExitAfterGrpcDrain();   // aborted feed still drains + exits
                }

                @Override
                public void onCompleted() {
                    StreamSummary summary = StreamSummary.newBuilder()
                            .setReceived(received.get())
                            .setErrors(errors.get())
                            .setExecutorId(r.executorId)
                            .build();
                    responseObserver.onNext(summary);
                    responseObserver.onCompleted();
                    r.openStreams.decrementAndGet();
                    System.out.println("MainWatch[grpc]: candidate stream COMPLETED  received=" + received.get()
                            + "  errors=" + errors.get()
                            + "  elapsed_sec=" + ((System.nanoTime() - startNanos) / 1_000_000_000L)
                            + "  (processing continues asynchronously on the candidate worker pool)");
                    MainWatch.maybeExitAfterGrpcDrain();   // in case every candidate already processed
                }
            };
        }
    }
}
