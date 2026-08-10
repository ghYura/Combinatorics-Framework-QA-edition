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

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;

/**
 * STEP 32 cross-language fixture: writes a deterministic shard corpus of runnable
 * Python candidates into {@code argv[0]} via {@link ShardSink}, and prints one
 * {@code "<id>\t<sha256-of-body>"} line per candidate to stdout so a Python test
 * ({@code Executor_trunk/test_shard_reader.py}) can verify that {@code shard_reader.py}
 * reads byte-for-byte what {@code ShardSink} wrote (zlib/CRC/endianness/format parity).
 *
 * <p>Usage: {@code java ... com.company.sink.ShardCorpusEmitter <dir> <count> [maxRecords]}
 */
public final class ShardCorpusEmitter {
    private ShardCorpusEmitter() {}

    public static void main(String[] args) throws Exception {
        Path dir = Path.of(args[0]);
        int n = Integer.parseInt(args[1]);
        int maxRecords = args.length > 2 ? Integer.parseInt(args[2]) : 4;

        ShardSink sink = new ShardSink(dir, new byte[0], maxRecords, ShardSink.DEFAULT_MAX_BYTES);
        String[] ids = new String[n];
        byte[][] bodies = new byte[n][];
        for (int i = 0; i < n; i++) {
            ids[i] = (100000 + i) + "_0_0";
            // A runnable Python candidate: alternates PASS (0) / DOMAIN_FAIL (1).
            bodies[i] = ("FW_VAR = " + (i % 2) + "  # candidate " + i + "\n").getBytes(StandardCharsets.UTF_8);
            sink.write(ids[i], bodies[i], 0, bodies[i].length);
        }
        sink.close();

        MessageDigest md = MessageDigest.getInstance("SHA-256");
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < n; i++) {
            md.reset();
            byte[] d = md.digest(bodies[i]);
            StringBuilder hex = new StringBuilder(d.length * 2);
            for (byte b : d) hex.append(String.format("%02x", b));
            out.append(ids[i]).append('\t').append(hex).append('\n');
        }
        System.out.print(out);
        CandidateSink.Summary s = sink.summary();
        System.err.println("emitted candidates=" + s.candidateCount() + " shards=" + sink.shardCount()
                + " bytes=" + s.bytes() + " index=" + s.index() + " errors=" + s.errors());
        if (s.errors() != 0 || s.candidateCount() != n) {
            System.err.println("EMITTER FAILED: errors=" + s.errors() + " count=" + s.candidateCount());
            System.exit(1);
        }
    }
}
