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

import static com.company.Main.*;
import java.io.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

// Extracted from the Main god-class 2026-05-30 (behaviour-preserving). SRP: the Reader's
// configuration — every fw.properties-derived static + loadProperties(). Read elsewhere via
// `import static com.company.ReaderConfig.*`.
public final class ReaderConfig {
    private ReaderConfig() {}

    // ── Java 25 structural migration (config-record holder) ──────────────────────────────────────
    // The Reader's config is migrating off the ~70 scattered `XXX_properties` statics onto this
    // immutable record, read via cfg() from ANY thread. This is a static holder — deliberately NOT a
    // ScopedValue, which is not inherited by this code's ExecutorService / new Thread() pools, and
    // cannot model the few genuinely runtime-mutable fields (e.g. FILE_GENERATION_DELAY_properties,
    // reassigned by the ramp thread — that one stays static). Built once at the end of loadProperties()
    // from the parsed statics; the record grows and read-sites migrate group-by-group.
    public record ReaderConfiguration(
        Long fwGeneralTimeoutToStop,
        String fwConcatenator,
        boolean zipMode,
        boolean filesMode,
        String fwFileExtension,
        int fileGenerationInitialDelay,
        int fileGenerationDelayRampup00,
        int fileGenerationDelayRampup00Delta,
        int fileGenerationDelayRampup00WaitRampup0,
        int fileGenerationIntermediateDelay,
        int fileGenerationDelayRampup0,
        int fileGenerationDelayRampup0Delta,
        String pathJarFilesFrom,
        String pathJarFilesTo,
        String fwPathFilesTo,
        String pathFwOutFile,
        List<String> pathFwOutZipDirList,
        String pathFwResultsDbCfgFileResults,
        String pathFwResultsDbSqlInsertTemplateFileResults,
        String pathFwResultsFirstRunOnceResults,
        String pathFwResultsArgumentsResults,
        String pathFwResultsHandoffManifestResults,
        String handoffRunId,
        boolean handoffDualWrite,
        String candidateSink,
        int shardMaxRecords,
        long shardMaxBytes,
        boolean shardResume,
        String backpressureDir,
        int backpressureHigh,
        int backpressureLow,
        boolean refineCodeInDb,
        boolean preserveWhitespace,
        List<String> newLine2AddBeforeThatStartsWithButNotInquotesList,
        List<String> newLine2AddAfterThatEndsWithButNotInquotesList,
        List<String> oneSpace2AddBeforeCharsButNotInQuotesList,
        List<String> oneSpace2AddAfterCharsButNotInQuotesList,
        Boolean overrideIsOpt,
        Boolean isProcessBothFinalAndOpt,
        List<Integer> overrideOptionalList,
        Long desiredCurrentChunkFinal,
        Long desiredCurrentChunkOpt,
        boolean isPrintPretty,
        String dbUser,
        String dbPassword,
        String dbHost,
        int dbPort,
        String dbName,
        String dbUserResults,
        String dbPasswordResults,
        String dbHostResults,
        int dbPortResults,
        String dbTablespaceResults,
        String dbTablespaceLocationResults,
        Boolean dbFwExitCodeColumnsOnlyResults,
        Boolean dbFwCustomVarOnlyResults,
        Boolean dbFwCustomvarmapCreateTableResults,
        String fastDiskTablespace,
        String extendedDiskTablespace,
        List<String> additionalDiskTablespacesList,
        int counter4CopyMax,
        long limitVarGivenLessThan,
        int sleepTimeAfterDisconnect4CopyDb,
        String pathCoreXSqlFiles,
        String path2PostgresqlBin,
        int limitOptionalSheetsCombosMax,
        int numberOptionalSheetCombosMultithreadAfter,
        String constraintsBondsFile,
        List<Integer> includeOptionalCombiPairs2DbList,
        String grpcTarget
    ) {}
    private static volatile ReaderConfiguration CFG;
    private static ReaderConfiguration snapshotFromStatics() {
        return new ReaderConfiguration(FW_GENERAL_TIMEOUT_TO_STOP_properties, FW_CONCATENATOR_properties, ZIP_MODE_properties, FILES_MODE_properties, FW_FILE_EXTENSION_properties, FILE_GENERATION_INITIAL_DELAY_properties, FILE_GENERATION_DELAY_RAMPUP00_properties, FILE_GENERATION_DELAY_RAMPUP00_DELTA_properties, FILE_GENERATION_DELAY_RAMPUP00_WAIT_RAMPUP0_properties, FILE_GENERATION_INTERMEDIATE_DELAY_properties, FILE_GENERATION_DELAY_RAMPUP0_properties, FILE_GENERATION_DELAY_RAMPUP0_DELTA_properties, PATH_JAR_FILES_FROM_properties, PATH_JAR_FILES_TO_properties, FW_PATH_FILES_TO_properties, PATH_FW_OUT_FILE_properties, PATH_FW_OUT_ZIP_DIR_LIST_properties, PATH_FW_RESULTS_DB_CFG_FILE_results_properties, PATH_FW_RESULTS_DB_SQL_INSERT_TEMPLATE_FILE_results_properties, PATH_FW_RESULTS_FIRST_RUN_ONCE_results_properties, PATH_FW_RESULTS_ARGUMENTS_results_properties, PATH_FW_RESULTS_HANDOFF_MANIFEST_results_properties, HANDOFF_RUN_ID_properties, HANDOFF_DUAL_WRITE_properties, CANDIDATE_SINK_properties, SHARD_MAX_RECORDS_properties, SHARD_MAX_BYTES_properties, SHARD_RESUME_properties, BACKPRESSURE_DIR_properties, BACKPRESSURE_HIGH_properties, BACKPRESSURE_LOW_properties, REFINE_CODE_IN_DB_properties, PRESERVE_WHITESPACE_properties, NEW_LINE_2_ADD_BEFORE_THAT_STARTS_WITH_BUT_NOT_INQUOTES_LIST_properties, NEW_LINE_2_ADD_AFTER_THAT_ENDS_WITH_BUT_NOT_INQUOTES_LIST_properties, ONE_SPACE_2_ADD_BEFORE_CHARS_BUT_NOT_IN_QUOTES_LIST_properties, ONE_SPACE_2_ADD_AFTER_CHARS_BUT_NOT_IN_QUOTES_LIST_properties, OVERRIDE_IS_OPT_properties, IS_PROCESS_BOTH_FINAL_AND_OPT_properties, OVERRIDE_OPTIONAL_LIST_properties, DESIRED_CURRENT_CHUNK_FINAL_properties, DESIRED_CURRENT_CHUNK_OPT_properties, IS_PRINT_PRETTY_properties, DB_USER_properties, DB_PASSWORD_properties, DB_HOST_properties, DB_PORT_properties, DB_NAME_properties, DB_USER_results_properties, DB_PASSWORD_results_properties, DB_HOST_results_properties, DB_PORT_results_properties, DB_TABLESPACE_results_properties, DB_TABLESPACE_LOCATION_results_properties, DB_FW_EXIT_CODE_columns_only_results_properties, DB_FW_CUSTOM_VAR_only_results_properties, DB_FW_CUSTOMVARMAP_CREATE_TABLE_results_properties, FAST_DISK_TABLESPACE_properties, EXTENDED_DISK_TABLESPACE_properties, ADDITIONAL_DISK_TABLESPACES_LIST_properties, COUNTER_4_COPY_MAX_properties, LIMIT_VAR_GIVEN_LESS_THAN_properties, SLEEP_TIME_AFTER_DISCONNECT_4_COPY_DB_properties, PATH_CORE_X_SQL_FILES_properties, PATH_2_POSTGRESQL_BIN_properties, LIMIT_OPTIONAL_SHEETS_COMBOS_MAX_properties, NUMBER_OPTIONAL_SHEET_COMBOS_MULTITHREAD_AFTER_properties, CONSTRAINTS_BONDS_FILE_properties, INCLUDE_OPTIONAL_COMBI_PAIRS_2_DB_LIST_properties, GRPC_TARGET_properties);
    }
    /** Immutable config snapshot, readable from any thread. After loadProperties() this is the built
     *  snapshot; before it (a focused test that sets statics directly) it falls back to a live view of
     *  the statics, so a read never NPEs and mirrors the pre-migration static behaviour exactly. */
    public static ReaderConfiguration cfg() {
        ReaderConfiguration c = CFG;
        return (c != null) ? c : snapshotFromStatics();
    }
    /** Package-private test hook: install a config snapshot directly (for focused tests that bypass
     *  loadProperties and previously injected config by reassigning the statics). */
    static void installForTest(ReaderConfiguration c) { CFG = c; }

public static String thisProp = "";
public static int inputTimeout = 10;
public static Properties prop = new Properties();
public static Long FW_GENERAL_TIMEOUT_TO_STOP_properties;
public static String FW_CONCATENATOR_properties;
public static byte[] FW_B_ARR;
public static int FW_B_ARR_LENGTH;
public static boolean ZIP_MODE_properties;
public static boolean FILES_MODE_properties;
public static String FW_REPLACE_WITH_properities;
public static boolean fw_replace_me_with_current_combo_sequence_mode;
public static String FW_FILE_EXTENSION_properties;
public static int FILE_GENERATION_INITIAL_DELAY_properties;
public static int FILE_GENERATION_DELAY_RAMPUP00_properties;
public static int FILE_GENERATION_DELAY_RAMPUP00_DELTA_properties;
public static int FILE_GENERATION_DELAY_RAMPUP00_WAIT_RAMPUP0_properties;
public static int FILE_GENERATION_INTERMEDIATE_DELAY_properties;
public static int FILE_GENERATION_DELAY_RAMPUP0_properties;
public static int FILE_GENERATION_DELAY_RAMPUP0_DELTA_properties;
// volatile (2026-07-02 perf pass): mutated by the ramp thread while read from many
// writer virtual-threads inside tight per-candidate loops — without volatile a JIT'd
// loop could legally cache the pre-ramp 500ms delay forever.
public static volatile int FILE_GENERATION_DELAY_properties;
public static String PATH_JAR_FILES_FROM_properties;
public static String PATH_JAR_FILES_TO_properties;
public static String FW_PATH_FILES_TO_properties;
public static String PATH_FW_OUT_FILE_properties;
public static List<String> PATH_FW_OUT_ZIP_DIR_LIST_properties;
public static String PATH_FW_RESULTS_DB_CFG_FILE_results_properties;
public static String PATH_FW_RESULTS_DB_SQL_INSERT_TEMPLATE_FILE_results_properties;
public static String PATH_FW_RESULTS_FIRST_RUN_ONCE_results_properties;
public static String PATH_FW_RESULTS_ARGUMENTS_results_properties;
public static String PATH_FW_RESULTS_HANDOFF_MANIFEST_results_properties;
public static String HANDOFF_RUN_ID_properties;
public static boolean HANDOFF_DUAL_WRITE_properties;
// STEP 32: candidate output transport selection + shard rollover thresholds.
public static String CANDIDATE_SINK_properties;   // "loose-files" (default) | "sharded" | "grpc"
// gRPC candidate transport (2026-07-02): host:port of the Executor's -grpcPort ingestion server.
public static String GRPC_TARGET_properties;
public static int SHARD_MAX_RECORDS_properties;   // candidates per shard before rollover
public static long SHARD_MAX_BYTES_properties;    // approx compressed bytes per shard before rollover
public static boolean SHARD_RESUME_properties;    // reuse valid shards already in the output dir (checkpoint)
// STEP 34: closed-loop backpressure (complements the open-loop FILE_GENERATION_DELAY rampup).
public static String BACKPRESSURE_DIR_properties;  // shared state dir; "" → gate inactive (ramp-only)
public static int BACKPRESSURE_HIGH_properties;    // pause emission while in-flight depth ≥ this
public static int BACKPRESSURE_LOW_properties;     // resume once drained to this
public static boolean REFINE_CODE_IN_DB_properties;
public static boolean PRESERVE_WHITESPACE_properties = false;
public static List<String> NEW_LINE_2_ADD_BEFORE_THAT_STARTS_WITH_BUT_NOT_INQUOTES_LIST_properties;
public static List<String> NEW_LINE_2_ADD_AFTER_THAT_ENDS_WITH_BUT_NOT_INQUOTES_LIST_properties;
public static List<String> ONE_SPACE_2_ADD_BEFORE_CHARS_BUT_NOT_IN_QUOTES_LIST_properties;
public static List<String> ONE_SPACE_2_ADD_AFTER_CHARS_BUT_NOT_IN_QUOTES_LIST_properties;
public static Boolean OVERRIDE_IS_OPT_properties;
public static Boolean IS_PROCESS_BOTH_FINAL_AND_OPT_properties;
public static List<Integer> OVERRIDE_OPTIONAL_LIST_properties;
public static Long DESIRED_CURRENT_CHUNK_FINAL_properties;
public static Long DESIRED_CURRENT_CHUNK_OPT_properties;
public static boolean IS_PRINT_PRETTY_properties;
public static String DB_USER_properties;
public static String DB_PASSWORD_properties;
public static String DB_HOST_properties;
public static int DB_PORT_properties;
public static String DB_NAME_properties;
public static String DB_USER_results_properties;
public static String DB_PASSWORD_results_properties;
public static String DB_HOST_results_properties;
public static int DB_PORT_results_properties;
public static String DB_TABLESPACE_results_properties;
public static String DB_TABLESPACE_LOCATION_results_properties;
public static Boolean DB_FW_EXIT_CODE_columns_only_results_properties;
public static Boolean DB_FW_CUSTOM_VAR_only_results_properties;
public static Boolean DB_FW_CUSTOMVARMAP_CREATE_TABLE_results_properties;
public static String FAST_DISK_TABLESPACE_properties;
public static String EXTENDED_DISK_TABLESPACE_properties;
public static List<String> ADDITIONAL_DISK_TABLESPACES_LIST_properties;
public static int COUNTER_4_COPY_MAX_properties;
public static long LIMIT_VAR_GIVEN_LESS_THAN_properties;
public static int SLEEP_TIME_AFTER_DISCONNECT_4_COPY_DB_properties;
public static String PATH_CORE_X_SQL_FILES_properties;
public static String PATH_2_POSTGRESQL_BIN_properties;
public static int SLEEP_TIME_CHECK_FINAL_FILLED_properies;
public static int LIMIT_OPTIONAL_SHEETS_COMBOS_MAX_properties;
public static int NUMBER_OPTIONAL_SHEET_COMBOS_MULTITHREAD_AFTER_properties;
// Optional constraint enforcement: a file of compact, code-tuple bond specs (the DEFERRED bonds
// touching FW_Optional sheets, compiled by the Python sieve). The Reader evaluates them PER
// assembled candidate during cartesian assembly — O(bonds) memory, no per-candidate precompute.
// Null/absent when the run is not sieving — the cartesian path then does ZERO extra work (gated
// behind a null check in ComboGenerationPipeline; the final-only pass is untouched).
public static String CONSTRAINTS_BONDS_FILE_properties;
public static List<Integer> INCLUDE_OPTIONAL_COMBI_PAIRS_2_DB_LIST_properties;

// Blank/missing 'db.password', 'hibernate.connection.password', or 'results.db.password' fall back to
// READER_DB_PASSWORD/READER_RESULTS_DB_PASSWORD from the environment — lets
// fw.properties be committed without a literal credential while keeping
// direct (non-Bundle) launches working for an operator who has the env var
// set. The file value still wins when present (never silently overridden).
private static void applyEnvSecretFallback(Properties p) {
applyEnvSecretFallback(p, "db.password", "READER_DB_PASSWORD");
applyEnvSecretFallback(p, "hibernate.connection.password", "READER_DB_PASSWORD");
applyEnvSecretFallback(p, "results.db.password", "READER_RESULTS_DB_PASSWORD");
}

private static void applyEnvSecretFallback(Properties p, String key, String envVar) {
String filePassword = p.getProperty(key);
if (filePassword == null || filePassword.isBlank()) {
String envPassword = System.getenv(envVar);
if (envPassword != null && !envPassword.isBlank()) {
p.setProperty(key, envPassword);
}
}
}

public static void loadProperties() {
if (thisProp.equals("")) thisProp = "./fw.properties";
System.out.println("[WARN] [fail-honest][AI-proposition] pre-flight: config/contract checks are best-effort (MEDIUM-confidence: pre-flight validation of config/contract is worth it). Non-blocking note — processing logic unchanged.");
System.out.println("\nfw.properties:\n");
System.out.println(Paths.get(thisProp).normalize().toAbsolutePath().normalize().toString());
System.out.println("\n:fw.properties\n");
try (InputStream input = new FileInputStream(thisProp)) {
prop.load(input);
applyEnvSecretFallback(prop);

FW_GENERAL_TIMEOUT_TO_STOP_properties = Long.parseLong(prop.getProperty("reader.generalTimeoutToStop"));
FW_CONCATENATOR_properties = prop.getProperty("reader.core.concatenator");
// optional, may be absent (getProperty -> null) — kept backward-compatible with older fw.properties
CONSTRAINTS_BONDS_FILE_properties = prop.getProperty("reader.constraints.bondsFile");
FW_B_ARR = (FW_CONCATENATOR_properties == null) ? new byte[]{} : FW_CONCATENATOR_properties.getBytes();
FW_B_ARR_LENGTH = FW_B_ARR.length;

// ─── Optional: install Heuristic Analyzer bridge (fw.analyzer.enabled=true) ──
// When the property is absent or false the framework's behaviour is unchanged.
// When enabled, every emitted row is also fed into the analyzer's streaming
// pipeline via com.company.sink.AnalyzerBridge — see com/company/sink/.
AnalyzerWiring.installIfEnabled(prop);

ZIP_MODE_properties = Boolean.parseBoolean(prop.getProperty("reader.out.zipMode"));
FILES_MODE_properties = Boolean.parseBoolean(prop.getProperty("reader.out.filesMode"));
FW_REPLACE_WITH_properities = prop.getProperty("reader.out.replaceWithCurrentComboSequence");
if (FW_REPLACE_WITH_properities.equalsIgnoreCase("FW_REPLACE_ME_WITH_CURRENT_COMBO_SEQUENCE")) {
fw_replace_me_with_current_combo_sequence_mode = true;
}
FW_FILE_EXTENSION_properties = prop.getProperty("reader.out.fileExtension");

FILE_GENERATION_INITIAL_DELAY_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationInitialDelay"));
FILE_GENERATION_DELAY_RAMPUP00_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationDelay.rampUp00"));
FILE_GENERATION_DELAY_RAMPUP00_DELTA_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationDelay.rampUp00.delta"));
FILE_GENERATION_DELAY_RAMPUP00_WAIT_RAMPUP0_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationDelay.rampUp00_wait_rampUp0"));
FILE_GENERATION_INTERMEDIATE_DELAY_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationIntermediateDelay"));
FILE_GENERATION_DELAY_RAMPUP0_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationDelay.rampUp0"));
FILE_GENERATION_DELAY_RAMPUP0_DELTA_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationDelay.rampUp0.delta"));
FILE_GENERATION_DELAY_properties = Integer.parseInt(prop.getProperty("reader.out.fileGenerationDelay"));
if (!(FILE_GENERATION_INTERMEDIATE_DELAY_properties > FILE_GENERATION_DELAY_properties) ||
!(FILE_GENERATION_INITIAL_DELAY_properties > FILE_GENERATION_INTERMEDIATE_DELAY_properties))
try {
throw new Exception("(fileGenerationIntermediateDelay == " + FILE_GENERATION_INTERMEDIATE_DELAY_properties + " is not > " + FILE_GENERATION_DELAY_properties + " == fileGenerationDelay) " +
"\nor\n" +
" (fileGenerationInitialDelay == " + FILE_GENERATION_INITIAL_DELAY_properties + " is not > " + FILE_GENERATION_INTERMEDIATE_DELAY_properties + " == fileGenerationIntermediateDelay)");
} catch (Exception e) {
e.printStackTrace();
}
if ((FILE_GENERATION_INTERMEDIATE_DELAY_properties + FILE_GENERATION_DELAY_RAMPUP00_DELTA_properties > FILE_GENERATION_INITIAL_DELAY_properties) ||
(FILE_GENERATION_DELAY_properties + FILE_GENERATION_DELAY_RAMPUP0_DELTA_properties > FILE_GENERATION_INTERMEDIATE_DELAY_properties))
try {
throw new Exception("(fileGenerationIntermediateDelay + rampUp00.delta:\n" + FILE_GENERATION_INTERMEDIATE_DELAY_properties + " + " + FILE_GENERATION_DELAY_RAMPUP00_DELTA_properties + "\n" +
" is not <= " + FILE_GENERATION_INITIAL_DELAY_properties + " == fileGenerationInitialDelay) " +
"\nor\n" +
" (fileGenerationDelay + rampUp0.delta:\n" + FILE_GENERATION_DELAY_properties + " + " + FILE_GENERATION_DELAY_RAMPUP0_DELTA_properties + "\n" +
" is not <= " + FILE_GENERATION_INTERMEDIATE_DELAY_properties + " == fileGenerationIntermediateDelay)");
} catch (Exception e) {
e.printStackTrace();
}

// Tier-0 bug fix 0.8: default helper paths to /tmp/fw-reader/\*  and auto-create
// missing dirs/files.  Caller can override per-property in fw.properties; null
// or missing → safe defaults so the Reader doesn't fail early on path absence.
java.nio.file.Path defaultHelperRoot = java.nio.file.Path.of(System.getProperty("java.io.tmpdir"), "fw-reader");
PATH_JAR_FILES_FROM_properties = prop.getProperty("reader.in.jarFilesFromPath",       defaultHelperRoot.resolve("jarsFrom").toString());
PATH_JAR_FILES_TO_properties = prop.getProperty("reader.out.jarFilesToPath",          defaultHelperRoot.resolve("jars").toString());
FW_PATH_FILES_TO_properties = prop.getProperty("reader.out.fwPathFilesTo",            defaultHelperRoot.resolve("jars").toString() + "/");
PATH_FW_OUT_FILE_properties = prop.getProperty("reader.out.outFilePathAndName",       defaultHelperRoot.resolve("FW_out.tsv").toString());
String zipList = prop.getProperty("reader.out.outZipDirPathList",                     defaultHelperRoot.resolve("src").toString() + "/");
PATH_FW_OUT_ZIP_DIR_LIST_properties = Arrays.stream(zipList.trim().split("\\s{0,},\\s{0,}")).collect(Collectors.toList());
PATH_FW_RESULTS_DB_CFG_FILE_results_properties = prop.getProperty("reader.results.db.configFile",  defaultHelperRoot.resolve("resultsDbURL/resultsDbURL.properties").toString());
PATH_FW_RESULTS_DB_SQL_INSERT_TEMPLATE_FILE_results_properties = prop.getProperty("reader.results.db.sqlInsertTemplateFile", defaultHelperRoot.resolve("sqlTemplate/insert.sql").toString());
PATH_FW_RESULTS_FIRST_RUN_ONCE_results_properties = prop.getProperty("reader.results.firstRunOnce", defaultHelperRoot.resolve("runFirstOnce/runmefirstonce.first").toString());
PATH_FW_RESULTS_ARGUMENTS_results_properties = prop.getProperty("reader.results.arguments",         defaultHelperRoot.resolve("arguments/args").toString());
// STEP 17: Handoff v2 manifest dual-write alongside the legacy handshake (HandoffManifestWriter).
PATH_FW_RESULTS_HANDOFF_MANIFEST_results_properties = prop.getProperty("reader.results.handoffManifest", defaultHelperRoot.resolve("handoff/manifest.json").toString());
HANDOFF_RUN_ID_properties = prop.getProperty("reader.handoff.runId", "");
HANDOFF_DUAL_WRITE_properties = Boolean.parseBoolean(prop.getProperty("reader.handoff.dualWrite", "true"));
// STEP 32: "loose-files" (default) keeps one-file-per-candidate byte-for-byte; "sharded"
// packs candidates into compressed shard containers (ShardSink) to cut inode pressure.
CANDIDATE_SINK_properties = prop.getProperty("reader.out.candidateSink", "loose-files");
// gRPC candidate transport (2026-07-02): only read when candidateSink=grpc; safe default.
GRPC_TARGET_properties = prop.getProperty("reader.out.grpc.target", "localhost:50061");
SHARD_MAX_RECORDS_properties = Integer.parseInt(prop.getProperty("reader.out.shard.maxRecords", "1000"));
SHARD_MAX_BYTES_properties = Long.parseLong(prop.getProperty("reader.out.shard.maxBytes", String.valueOf(8L * 1024 * 1024)));
// STEP 32 action 5: reuse valid finalized shards already present in the output dir (resume a
// prior/interrupted run without rewriting them). Default off → fresh, deterministic full write.
SHARD_RESUME_properties = Boolean.parseBoolean(prop.getProperty("reader.out.shard.resume", "false"));
// STEP 34: a configured backpressure dir turns on the closed-loop depth gate; default "" leaves
// emission paced only by the legacy FILE_GENERATION_DELAY rampup (behaviour unchanged).
BACKPRESSURE_DIR_properties = prop.getProperty("reader.out.backpressure.dir", "");
BACKPRESSURE_HIGH_properties = Integer.parseInt(prop.getProperty("reader.out.backpressure.high", "1024"));
BACKPRESSURE_LOW_properties = Integer.parseInt(prop.getProperty("reader.out.backpressure.low", "512"));
// Pre-create the helper dirs + empty files so downstream code doesn't fail on read.
try {
for (String dirPath : new String[]{
PATH_JAR_FILES_FROM_properties, PATH_JAR_FILES_TO_properties,
FW_PATH_FILES_TO_properties }) {
if (dirPath != null) java.nio.file.Files.createDirectories(java.nio.file.Path.of(dirPath.endsWith("/") ? dirPath.substring(0, dirPath.length()-1) : dirPath));
}
for (String zip : PATH_FW_OUT_ZIP_DIR_LIST_properties) {
if (zip != null && !zip.isBlank()) java.nio.file.Files.createDirectories(java.nio.file.Path.of(zip.endsWith("/") ? zip.substring(0, zip.length()-1) : zip));
}
for (String filePath : new String[]{
PATH_FW_RESULTS_DB_CFG_FILE_results_properties,
PATH_FW_RESULTS_DB_SQL_INSERT_TEMPLATE_FILE_results_properties,
PATH_FW_RESULTS_FIRST_RUN_ONCE_results_properties,
PATH_FW_RESULTS_ARGUMENTS_results_properties }) {
java.nio.file.Path p = java.nio.file.Path.of(filePath);
if (p.getParent() != null) java.nio.file.Files.createDirectories(p.getParent());
if (!java.nio.file.Files.exists(p)) java.nio.file.Files.writeString(p, "");
}
{
java.nio.file.Path manifestParent = java.nio.file.Path.of(PATH_FW_RESULTS_HANDOFF_MANIFEST_results_properties).getParent();
if (manifestParent != null) java.nio.file.Files.createDirectories(manifestParent);
}
} catch (Exception __pathPrep) {
System.err.println("[Tier-0 fix 0.8] Helper path auto-create encountered: " + __pathPrep);
}

REFINE_CODE_IN_DB_properties = Boolean.parseBoolean(prop.getProperty("reader.javacode.refineInDB"));
PRESERVE_WHITESPACE_properties = Boolean.parseBoolean(prop.getProperty("reader.cells.preserveWhitespace", "false"));
NEW_LINE_2_ADD_BEFORE_THAT_STARTS_WITH_BUT_NOT_INQUOTES_LIST_properties = (prop.getProperty("reader.javacode.newLine2AddBeforeThatStartsWithButNotInQuotesList") != null) ? Arrays.stream(prop.getProperty("reader.javacode.newLine2AddBeforeThatStartsWithButNotInQuotesList").trim().split("\\n")).collect(Collectors.toList()) : new ArrayList<>();
NEW_LINE_2_ADD_AFTER_THAT_ENDS_WITH_BUT_NOT_INQUOTES_LIST_properties = (prop.getProperty("reader.javacode.newLine2AddAfterThatEndsWithButNotInQuotesList") != null) ? Arrays.stream(prop.getProperty("reader.javacode.newLine2AddAfterThatEndsWithButNotInQuotesList").trim().split("\\n")).collect(Collectors.toList()) : new ArrayList<>();
ONE_SPACE_2_ADD_BEFORE_CHARS_BUT_NOT_IN_QUOTES_LIST_properties = (prop.getProperty("reader.javacode.oneSpace2AddBeforeCharsButNotInQuotesList") != null) ? Arrays.stream(prop.getProperty("reader.javacode.oneSpace2AddBeforeCharsButNotInQuotesList").trim().split("\\s{1}")).collect(Collectors.toList()) : new ArrayList<>();
ONE_SPACE_2_ADD_AFTER_CHARS_BUT_NOT_IN_QUOTES_LIST_properties = (prop.getProperty("reader.javacode.oneSpace2AddAfterCharsButNotInQuotesList") != null) ? Arrays.stream(prop.getProperty("reader.javacode.oneSpace2AddAfterCharsButNotInQuotesList").trim().split("\\s{1}")).collect(Collectors.toList()) : new ArrayList<>();

OVERRIDE_IS_OPT_properties = (prop.getProperty("reader.core.processIsOpt") == null) ? null : Boolean.parseBoolean(prop.getProperty("reader.core.processIsOpt"));
IS_PROCESS_BOTH_FINAL_AND_OPT_properties = (prop.getProperty("reader.core.processBothFinalAndOpt") == null) ? null : Boolean.parseBoolean(prop.getProperty("reader.core.processBothFinalAndOpt"));
OVERRIDE_OPTIONAL_LIST_properties = (prop.getProperty("reader.core.isOptCSVList") != null) ? Arrays.stream(prop.getProperty("reader.core.isOptCSVList").trim().split("\\s{0,},\\s{0,}")).mapToInt(Integer::parseInt).boxed().collect(Collectors.toList()) : null;

DESIRED_CURRENT_CHUNK_FINAL_properties = Long.valueOf(prop.getProperty("reader.core.desiredCurrentChunkFinal"));
DESIRED_CURRENT_CHUNK_OPT_properties = Long.valueOf(prop.getProperty("reader.core.desiredCurrentChunkOpt"));

IS_PRINT_PRETTY_properties = Boolean.parseBoolean(prop.getProperty("console.output.isPrintPretty"));

DB_USER_properties = prop.getProperty("db.user");
DB_PASSWORD_properties = prop.getProperty("db.password");
DB_HOST_properties = prop.getProperty("db.host");
DB_PORT_properties = Integer.parseInt(prop.getProperty("db.port"));
DB_NAME_properties = prop.getProperty("db.name");

DB_USER_results_properties = prop.getProperty("results.db.user");
DB_PASSWORD_results_properties = prop.getProperty("results.db.password");
DB_HOST_results_properties = prop.getProperty("results.db.host");
DB_PORT_results_properties = Integer.parseInt(prop.getProperty("results.db.port"));
DB_TABLESPACE_results_properties = prop.getProperty("results.db.tablespace");
DB_TABLESPACE_LOCATION_results_properties = prop.getProperty("results.db.tablespaceLocation");
DB_FW_EXIT_CODE_columns_only_results_properties = Boolean.parseBoolean(prop.getProperty("results.db.onlyFW_EXIT_CODEcolumns"));
DB_FW_CUSTOM_VAR_only_results_properties = Boolean.parseBoolean(prop.getProperty("results.db.onlyFW_CUSTOM_VAR"));
DB_FW_CUSTOMVARMAP_CREATE_TABLE_results_properties = Boolean.parseBoolean(prop.getProperty("results.db.customvarmapCreateTable"));

FAST_DISK_TABLESPACE_properties = prop.getProperty("db.fastDiskTablespace");
EXTENDED_DISK_TABLESPACE_properties = prop.getProperty("db.extendedDiskTablespace");
ADDITIONAL_DISK_TABLESPACES_LIST_properties = Arrays.stream(prop.getProperty("db.additionalDiskTablespacesCSVList").trim().split("\\s{0,},\\s{0,}")).collect(Collectors.toList());

LIMIT_VAR_GIVEN_LESS_THAN_properties = Long.valueOf(prop.getProperty("core.limitVarGivenLessThan"));
COUNTER_4_COPY_MAX_properties = Integer.valueOf(prop.getProperty("core.counter4copyMax"));
SLEEP_TIME_AFTER_DISCONNECT_4_COPY_DB_properties = Integer.valueOf(prop.getProperty("core.sleepTimeAfterDisconnect4copyDB"));
PATH_CORE_X_SQL_FILES_properties = prop.getProperty("sql.generate.files.pathCoreXsqlFiles");
PATH_2_POSTGRESQL_BIN_properties = prop.getProperty("sql.generate.path2PostgresqlBinFolder");
SLEEP_TIME_CHECK_FINAL_FILLED_properies = Integer.valueOf(prop.getProperty("core.sleepTimeCheckFinalFilled"));
LIMIT_OPTIONAL_SHEETS_COMBOS_MAX_properties = Integer.parseInt(prop.getProperty("core.optional.limitOptionalSheetsCombosMax"));
NUMBER_OPTIONAL_SHEET_COMBOS_MULTITHREAD_AFTER_properties = Integer.parseInt(prop.getProperty("core.optional.numberOptionalSheetCombosMultithreadStartsAfter"));
INCLUDE_OPTIONAL_COMBI_PAIRS_2_DB_LIST_properties = Arrays.stream(prop.getProperty("core.optional.includeOptionalCombiPairsToDBCSVList").trim().split("\\s{0,},\\s{0,}")).mapToInt(Integer::parseInt).boxed().collect(Collectors.toList());
// ── Java 25 structural migration: build the immutable config snapshot (db.* group; grows per iteration) ──
CFG = snapshotFromStatics();
} catch (IOException ex) {
ex.printStackTrace();
}
}

}
