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

import static com.company.ReaderConfig.*;
import com.company.helpers.QueryToDB;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

// STEP 17: Reader dual-write of Handoff v2 (see generator_trunk/bundle/handoff.py,
// generator_trunk/bundle-handoff-v2.schema.json — STEP 16 formalized the contract this
// writer now emits). Writes `manifest.json` atomically alongside the legacy handshake
// (HandshakeWriter); the legacy artifacts keep being written unchanged. A hand-rolled
// JSON encoder is used on purpose — Reader_trunk carries no JSON library (Jackson/Gson),
// and the plan forbids adding one when a dependency-consistent option (plain JDK) exists.
public final class HandoffManifestWriter {
    private HandoffManifestWriter() {}

    private static final DateTimeFormatter RUN_ID_STAMP =
            DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'", Locale.ROOT).withZone(ZoneOffset.UTC);

    /** Builds and atomically writes manifest.json from the just-completed run's
     *  legacy-handshake content plus the actual on-disk candidate emission.
     *  Mirrors bundle.handoff.handoff_from_legacy's legacy-artifact -> v2 mapping
     *  (resultsDbURL -> result_target, insert.sql '?' count -> verdict_mode/result_schema_mode,
     *  args/fwVar.shift/runmefirstonce.first -> arguments/shift/preprocess).
     *  Never throws on a feature-flagged-off run — caller checks cfg().handoffDualWrite(). */
    public static void writeManifestV2() throws IOException, SQLException {
        String runId = cfg().handoffRunId() == null || cfg().handoffRunId().isBlank()
                ? mintRunId() : cfg().handoffRunId();

        String language = cfg().fwFileExtension() != null
                && cfg().fwFileExtension().trim().equalsIgnoreCase(".py")
                ? "python" : "java";

        // STEP 32: the candidate transport (recorded by the active sink) drives how `sources`
        // is described. "sharded" → ONE dir source pointing at the shard directory (the Executor
        // lists *.fwshard there) and diskCount is the candidate RECORD count summed across valid
        // shards. "loose-files" (default) is unchanged — one dir source per output dir, counting
        // *<ext> candidate files. Defaults to loose-files when no sink ran (ZIP/streaming).
        String candidateTransport = com.company.sink.CandidateSinkRegistry
                .transportOrDefault(com.company.sink.LooseFileSink.TRANSPORT);
        boolean sharded = com.company.sink.ShardSink.TRANSPORT.equals(candidateTransport);
        boolean grpc = com.company.sink.GrpcCandidateSink.TRANSPORT.equals(candidateTransport);

        List<SourceDir> sourceDirs = new ArrayList<>();
        long diskCount = 0;
        if (grpc) {
            // gRPC live transport (2026-07-02): candidates were streamed to the Executor —
            // there is no on-disk source to enumerate. The single source entry names the
            // endpoint; the count is the sink's authoritative tally (already reconciled
            // in-stream against the Executor's receipt, fail-closed) and the digest is the
            // sink's order-independent candidate-id fingerprint.
            com.company.sink.CandidateSink.Summary grpcSummary = com.company.sink.CandidateSinkRegistry.last();
            long streamed = (grpcSummary != null) ? grpcSummary.candidateCount() : 0;
            String fingerprint = (grpcSummary != null && grpcSummary.index() != null) ? grpcSummary.index() : "";
            sourceDirs.add(new SourceDir("grpc://" + cfg().grpcTarget(), streamed, fingerprint, "grpc"));
            diskCount = streamed;
        } else if (sharded) {
            String shardDir = cfg().pathFwOutZipDirList().isEmpty()
                    ? cfg().fwPathFilesTo() : cfg().pathFwOutZipDirList().get(0);
            SourceDir sd = describeShardDir(shardDir);
            sourceDirs.add(sd);
            diskCount = sd.fileCount; // candidate record count across valid shards
        } else {
            for (String dir : cfg().pathFwOutZipDirList()) {
                if (dir == null || dir.isBlank()) continue;
                SourceDir sd = describeSourceDir(dir);
                sourceDirs.add(sd);
                diskCount += sd.fileCount;
            }
            if (sourceDirs.isEmpty()) {
                // No configured zip dirs — fall back to the candidate output directory itself
                // so `sources` is never empty (schema requires >=1 entry).
                sourceDirs.add(describeSourceDir(cfg().fwPathFilesTo()));
                diskCount = sourceDirs.get(0).fileCount;
            }
        }

        // STEP 31: candidate_count is the sink's authoritative tally, not a re-count.
        // The pipeline records the sink summary in CandidateSinkRegistry before this runs.
        // Fail-closed (refuse to write a handoff) if the sink dropped candidates or its
        // count disagrees with what is actually on disk — a partial/overwritten candidate
        // set must never be advertised as a clean handoff. When no sink ran (ZIP / in-memory
        // "concatenate everything" streaming), fall back to the on-disk count unchanged.
        com.company.sink.CandidateSink.Summary sinkSummary = com.company.sink.CandidateSinkRegistry.last();
        long candidateCount;
        if (sinkSummary != null) {
            if (sinkSummary.errors() > 0) {
                throw new IOException("[STEP 31] candidate sink reported " + sinkSummary.errors()
                        + " write error(s); refusing to write a handoff manifest (fail-closed)");
            }
            if (sinkSummary.candidateCount() != diskCount) {
                throw new IOException("[STEP 31] sink candidate_count " + sinkSummary.candidateCount()
                        + " != candidate files on disk " + diskCount
                        + (sinkSummary.candidateCount() < diskCount
                                ? " (stale files in the output dir from a previous run?)"
                                : " (candidates lost/overwritten after write)")
                        + "; refusing to write a handoff manifest (fail-closed)");
            }
            candidateCount = sinkSummary.candidateCount();
        } else {
            candidateCount = diskCount;
        }

        String insertSql = readTextOrEmpty(cfg().pathFwResultsDbSqlInsertTemplateFileResults());
        int placeholders = countChar(insertSql.strip().replaceAll(";\\s*$", ""), '?');
        boolean customMode = placeholders == 6;
        String resultSchemaMode = "placeholders=" + placeholders;
        String verdictMode = customMode ? "FW_CUSTOM_VAR" : "FW_VAR";

        List<CustomVerdict> customVerdicts = customMode ? readCustomVerdicts() : List.of();

        String argsText = readTextOrEmpty(cfg().pathFwResultsArgumentsResults());
        List<String> arguments = argsText.strip().isEmpty()
                ? List.of() : Arrays.asList(argsText.strip().split("\\s+"));

        String shiftPath = cfg().pathFwResultsArgumentsResults()
                .replaceFirst("((?<=/)[^\\/]+$)|((?<=\\\\)[^\\\\/]+$)", "fwVar.shift");
        String shiftText = readTextOrEmpty(shiftPath).strip();
        int shift = shiftText.isEmpty() ? 1 : Integer.parseInt(shiftText); // P6: never-empty default

        String preprocess = cfg().pathFwResultsFirstRunOnceResults();

        // candidateTransport was resolved above (it also drives the sharded vs loose source
        // description); it flows into the manifest's candidate_transport field verbatim.
        String json = toJson(runId, language, candidateCount, sourceDirs, resultSchemaMode,
                verdictMode, customVerdicts, arguments, shift, preprocess, candidateTransport);

        atomicWrite(Path.of(cfg().pathFwResultsHandoffManifestResults()), json);
        System.out.println("Successfully wrote Handoff v2 manifest to the file "
                + cfg().pathFwResultsHandoffManifestResults()
                + "  (candidate_count=" + candidateCount + ", run_id=" + runId + ")");
    }

    private static String mintRunId() {
        return RUN_ID_STAMP.format(Instant.now()) + "-" + Long.toHexString(System.nanoTime()).substring(0, 8);
    }

    // ----------------------------- candidate source dirs ----------------------------- //
    private static final class SourceDir {
        final String path;
        final long fileCount;
        final String digest;
        final String kind;   // "dir" (loose-files/sharded) | "grpc" (live-stream endpoint)
        SourceDir(String path, long fileCount, String digest) { this(path, fileCount, digest, "dir"); }
        SourceDir(String path, long fileCount, String digest, String kind) {
            this.path = path; this.fileCount = fileCount; this.digest = digest; this.kind = kind;
        }
    }

    /** Lists `*<FW_FILE_EXTENSION>` candidate files in `dir`, sorted by name, and returns
     *  the count plus a sha256 over the sorted name list — a deterministic source summary
     *  (plan item: "checksums or deterministic shard/source summary"), not a per-file hash. */
    private static SourceDir describeSourceDir(String dir) {
        String norm = dir.endsWith("/") || dir.endsWith("\\") ? dir.substring(0, dir.length() - 1) : dir;
        java.io.File[] files = new java.io.File(norm).listFiles((d, n) -> n.endsWith(cfg().fwFileExtension()));
        List<String> names = new ArrayList<>();
        if (files != null) for (java.io.File f : files) names.add(f.getName());
        names.sort(String::compareTo);
        return new SourceDir(norm, names.size(), sha256OfLines(names));
    }

    /** STEP 32: describes the shard directory for a "sharded" manifest. The `fileCount`
     *  carries the candidate RECORD count summed across VALID finalized shards (each shard
     *  is fully streamed + CRC-checked via ShardReader.validate), and the digest is a sha256
     *  over the sorted *.fwshard file-name list — a deterministic source summary symmetric
     *  with describeSourceDir. A corrupt/partial shard contributes 0 records, so the count
     *  falls short of the sink's tally and the caller's reconciliation fails closed. */
    private static SourceDir describeShardDir(String dir) {
        String norm = dir.endsWith("/") || dir.endsWith("\\") ? dir.substring(0, dir.length() - 1) : dir;
        Path shardDir = Path.of(norm);
        List<String> names = new ArrayList<>();
        long records = 0;
        try {
            for (Path shard : com.company.sink.ShardReader.listFinalizedShards(shardDir)) {
                long n = com.company.sink.ShardReader.validate(shard);
                if (n >= 0) {
                    records += n;
                    names.add(shard.getFileName().toString());
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("[STEP 32] cannot enumerate shard dir " + norm, e);
        }
        names.sort(String::compareTo);
        return new SourceDir(norm, records, sha256OfLines(names));
    }

    private static String sha256OfLines(List<String> lines) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            for (String l : lines) md.update((l + "\n").getBytes(StandardCharsets.UTF_8));
            byte[] digest = md.digest();
            StringBuilder sb = new StringBuilder(digest.length * 2);
            for (byte b : digest) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    // ------------------------------- custom verdicts --------------------------------- //
    private static final class CustomVerdict {
        final int code; final String message;
        CustomVerdict(int code, String message) { this.code = code; this.message = message; }
    }

    /** Reads code/message pairs from the results-DB `customvarmap` table — the same
     *  source ResultsDbProvisioner copies into the results DB — since the legacy
     *  handshake carries no FW_CUSTOM_VAR map of its own (it lives in the spec's
     *  custom_vars, per handoff_from_legacy's docstring). Opens its own short-lived
     *  connection: by the time this runs, the pipeline has disconnected its pools. */
    private static List<CustomVerdict> readCustomVerdicts() throws SQLException {
        List<CustomVerdict> out = new ArrayList<>();
        QueryToDB q = new QueryToDB();
        q.init(cfg().dbHostResults(), cfg().dbPortResults(), cfg().dbName(),
                cfg().dbUserResults(), cfg().dbPasswordResults());
        try {
            ResultSet rs = q.queryForWholeResSet("SELECT fw_custom_var, message FROM public.customvarmap ORDER BY fw_custom_var;");
            while (rs.next()) {
                out.add(new CustomVerdict(rs.getInt("fw_custom_var"), rs.getString("message")));
            }
        } finally {
            q.disconnect();
        }
        return out;
    }

    // ----------------------------------- IO helpers ---------------------------------- //
    private static String readTextOrEmpty(String path) throws IOException {
        Path p = Path.of(path);
        return Files.exists(p) ? Files.readString(p, StandardCharsets.UTF_8) : "";
    }

    private static int countChar(String s, char c) {
        int n = 0;
        for (int i = 0; i < s.length(); i++) if (s.charAt(i) == c) n++;
        return n;
    }

    /** temp file in the same directory -> flush/close -> atomic move: never observable
     *  as a partial manifest (plan acceptance criterion). */
    private static void atomicWrite(Path target, String content) throws IOException {
        Path dir = target.toAbsolutePath().getParent();
        Files.createDirectories(dir);
        Path tmp = Files.createTempFile(dir, target.getFileName().toString(), ".tmp");
        try {
            try (var out = Files.newOutputStream(tmp)) {
                out.write(content.getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
            Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            Files.deleteIfExists(tmp);
            throw e;
        }
    }

    // ------------------------------- JSON serialization ------------------------------ //
    // Hand-rolled (see class javadoc for why no library is pulled in). Covers exactly the
    // value shapes bundle.handoff.HandoffV2/handoff_to_dict emits — strings, ints, arrays
    // of small records, and nullable strings — nothing more.
    private static String toJson(String runId, String language, long candidateCount,
            List<SourceDir> sources, String resultSchemaMode, String verdictMode,
            List<CustomVerdict> customVerdicts, List<String> arguments, int shift, String preprocess,
            String candidateTransport) {
        StringBuilder sb = new StringBuilder(1024);
        sb.append('{');
        field(sb, "protocol", "bundle.handoff/v2", true);
        field(sb, "run_id", runId, true);
        field(sb, "language", language, true);
        field(sb, "candidate_transport", candidateTransport, true);
        fieldRaw(sb, "candidate_count", Long.toString(candidateCount), true);
        field(sb, "id_format", "<combi_id>_0_0", true);

        sb.append("\"sources\":[");
        for (int i = 0; i < sources.size(); i++) {
            if (i > 0) sb.append(',');
            SourceDir sd = sources.get(i);
            sb.append('{');
            field(sb, "kind", sd.kind, true);
            field(sb, "path", sd.path, true);
            field(sb, "sha256", sd.digest, false);
            sb.append('}');
        }
        sb.append("],");

        sb.append("\"result_target\":{");
        field(sb, "host", cfg().dbHostResults(), true);
        fieldRaw(sb, "port", Integer.toString(cfg().dbPortResults()), true);
        field(sb, "database", cfg().dbName(), true);
        field(sb, "user", cfg().dbUserResults(), false);
        sb.append("},");

        field(sb, "result_schema_mode", resultSchemaMode, true);
        field(sb, "verdict_mode", verdictMode, true);

        sb.append("\"custom_verdicts\":[");
        for (int i = 0; i < customVerdicts.size(); i++) {
            if (i > 0) sb.append(',');
            CustomVerdict cv = customVerdicts.get(i);
            sb.append('{');
            fieldRaw(sb, "code", Integer.toString(cv.code), true);
            field(sb, "message", cv.message, false);
            sb.append('}');
        }
        sb.append("],");

        sb.append("\"arguments\":[");
        for (int i = 0; i < arguments.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append(quote(arguments.get(i)));
        }
        sb.append("],");

        fieldRaw(sb, "shift", Integer.toString(shift), true);
        field(sb, "preprocess", preprocess, true);
        fieldRaw(sb, "execution_policy_ref", "null", false);

        sb.append('}');
        return sb.toString();
    }

    private static void field(StringBuilder sb, String name, String value, boolean comma) {
        sb.append(quote(name)).append(':');
        sb.append(value == null ? "null" : quote(value));
        if (comma) sb.append(',');
    }

    private static void fieldRaw(StringBuilder sb, String name, String rawValue, boolean comma) {
        sb.append(quote(name)).append(':').append(rawValue);
        if (comma) sb.append(',');
    }

    private static String quote(String s) {
        StringBuilder sb = new StringBuilder(s.length() + 2);
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
                }
            }
        }
        sb.append('"');
        return sb.toString();
    }
}
