package com.company.config;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import java.util.stream.Collectors;


public final class AppConfig {

private static final Logger log = LogManager.getLogger(AppConfig.class);

/** [Iter2] Selects how per-sheet intermediate tables (fw_&lt;key&gt;, fw2_&lt;key&gt;)
 *  are materialised during a run.  Final tables (fw_final, fw_opt&lt;i&gt;) always
 *  go to PostgreSQL regardless. */
public enum IntermediateStorageMode {
    /** Legacy default — intermediates live as PostgreSQL UNLOGGED tables. */
    PG,
    /** New — intermediates live in JVM heap; no COPY/SELECT round-trips on the
     *  intermediate stage.  Faster for small/medium workbooks; trades heap for
     *  speed. */
    MEMORY
}

public final DbConfig        db;

public final PoolConfig      pool;
public final ThreadingConfig threading;
public final PathConfig      paths;
public final TablespaceConfig tablespace;
public final FeatureFlags    flags;
public final OptionalConfig  optional;
public final HoldConfig      hold;


public final WorkbookConfig  workbook;

public final SeqConfig       seq;

/** [Iter2] Storage mode for fw_/fw2_ intermediates.  Property:
 *  {@code core.intermediate.storage=pg|memory}.  Default: {@link IntermediateStorageMode#PG}. */
public final IntermediateStorageMode intermediateStorage;

/** [Iter4] End-to-end pipeline path selector.  Property:
 *  {@code core.precompute=auto|db|java}.  Default: {@link PrecomputeMode#AUTO}.
 *  - {@code AUTO}  → Layer-1 estimator decides JAVA vs DB based on heap budget.
 *  - {@code JAVA}  → force pure-Java end-to-end (intermediate + final stages
 *                    all in JVM heap; only the four terminal PG tables get COPY'd).
 *                    {@link #intermediateStorage} is IGNORED in this mode.
 *  - {@code DB}    → force legacy PG-way; {@link #intermediateStorage} controls
 *                    intermediate storage choice for fw_/fw2_ tables. */
public enum PrecomputeMode { AUTO, DB, JAVA }
public final PrecomputeMode precomputeMode;

// ---------------------------------------------------------------------------
// FW_ReplaceRE authoring policies.
//
// `FW_ReplaceRE` inside `FW_Group` rewrites the *code-string* of a produced
// combination — `w.toString()` over a list of `Short` value-codes, e.g.
// "[47, 48]" — and the result is parsed straight back with Integer.parseInt.
// That is deliberate and powerful: it is how one expresses tuple surgery
// (remap a symbol, splice one in from another sheet, delete one) and it
// composes to depths a typed operator would not reach.
//
// Per the author, Yurii Baranov: the functionality that existed at this place
// beforehand allowed one to combine even deeper. Operating on the interned
// keys — rather than on the text they stand for — is the reason. These
// policies therefore add observation only; they remove no reach, and the
// pre-existing behaviour remains the default in every one of them.
//
// The cost is that both ways of getting it wrong are silent. A pattern written
// against rendered *value text* (say "@S@") can never match a code-string, so
// it is a no-op and the run still reports green; a replacement that is not
// integer-parseable makes the row unparseable and it is dropped. Both have
// cost real debugging time (see ZEN_OF_COMBINATORICS.md, 2026-06-12).
//
// These policies make each of those observable — and, at the operator's
// choice, fatal — WITHOUT restricting what the feature can express. Every
// default is exactly the behaviour that shipped before they existed, so an
// existing fw.properties, or none at all, changes nothing.
// ---------------------------------------------------------------------------

/** What to do with a `FW_ReplaceRE` pattern that cannot match a code-string.
 *  Property: {@code core.replace.patternPolicy=permissive|warn|strict}.
 *  Default {@link ReplacePatternPolicy#PERMISSIVE} — the historical behaviour.
 *  A code-string contains only digits, comma, space and bracket characters, so
 *  a pattern needing anything else is provably a no-op before the run starts. */
public enum ReplacePatternPolicy { PERMISSIVE, WARN, STRICT }
public final ReplacePatternPolicy replacePatternPolicy;

/** What to do when a declared replacement matches nothing over the whole sheet.
 *  Property: {@code core.replace.unmatchedPolicy=ignore|warn|fail}.
 *  Default {@link ReplaceUnmatchedPolicy#IGNORE} — the historical behaviour.
 *  Catches patterns that are syntactically capable of matching but never do. */
public enum ReplaceUnmatchedPolicy { IGNORE, WARN, FAIL }
public final ReplaceUnmatchedPolicy replaceUnmatchedPolicy;

/** What to do when a rewritten combination no longer parses as short codes.
 *  Property: {@code core.replace.unparseablePolicy=warn|drop|fail}.
 *  Default {@link ReplaceUnparseablePolicy#WARN} — the historical behaviour
 *  (log one WARN and drop the row). {@code drop} silences the warning for
 *  rewrites that discard rows on purpose; {@code fail} refuses the run. */
public enum ReplaceUnparseablePolicy { WARN, DROP, FAIL }
public final ReplaceUnparseablePolicy replaceUnparseablePolicy;

/** What to do with a replacement whose pattern and replacement are identical.
 *  Property: {@code core.replace.identityPolicy=allow|warn}.
 *  Default {@link ReplaceIdentityPolicy#ALLOW} — the historical behaviour.
 *  An identity rewrite such as ("47","47") does nothing at run time yet still
 *  changes the emitted directive, and therefore the FW_Seq graph fingerprint. */
public enum ReplaceIdentityPolicy { ALLOW, WARN }
public final ReplaceIdentityPolicy replaceIdentityPolicy;

/** Per-sheet rewrite accounting.
 *  Property: {@code core.replace.diagnostics=off|summary}.
 *  Default {@link ReplaceDiagnostics#OFF} — the historical behaviour.
 *  {@code summary} logs one INFO line per grouped sheet: rows seen, rows whose
 *  code-string the rewrites changed, rows dropped, and the per-pattern match
 *  counts. It changes no outcome; it makes a silent no-op visible. */
public enum ReplaceDiagnostics { OFF, SUMMARY }
public final ReplaceDiagnostics replaceDiagnostics;

/** Tier-1 win 1.2: raw properties bag.  Lets callers read arbitrary
 *  keys (e.g. {@code core.input.format}) without needing a typed field
 *  for every new property.  Always non-null; empty if the constructor
 *  legacy path was used. */
public final Properties raw;


private AppConfig(DbConfig db, ThreadingConfig threading, PathConfig paths,
TablespaceConfig tablespace, FeatureFlags flags,
OptionalConfig optional, HoldConfig hold, PoolConfig pool,
WorkbookConfig workbook, SeqConfig seq) {
this(db, threading, paths, tablespace, flags, optional, hold, pool, workbook, seq, new Properties());
}

private AppConfig(DbConfig db, ThreadingConfig threading, PathConfig paths,
TablespaceConfig tablespace, FeatureFlags flags,
OptionalConfig optional, HoldConfig hold, PoolConfig pool,
WorkbookConfig workbook, SeqConfig seq, Properties raw) {
this.db         = db;
this.threading  = threading;
this.paths      = paths;
this.tablespace = tablespace;
this.flags      = flags;
this.optional   = optional;
this.hold       = hold;
this.pool       = pool;
this.workbook   = workbook;
this.seq        = seq;
this.raw        = (raw == null) ? new Properties() : raw;
this.intermediateStorage = parseStorageMode(this.raw.getProperty("core.intermediate.storage"));
this.precomputeMode = parsePrecomputeMode(this.raw.getProperty("core.precompute"));
this.replacePatternPolicy = parseEnum(this.raw.getProperty("core.replace.patternPolicy"),
        ReplacePatternPolicy.class, ReplacePatternPolicy.PERMISSIVE, "core.replace.patternPolicy");
this.replaceUnmatchedPolicy = parseEnum(this.raw.getProperty("core.replace.unmatchedPolicy"),
        ReplaceUnmatchedPolicy.class, ReplaceUnmatchedPolicy.IGNORE, "core.replace.unmatchedPolicy");
this.replaceUnparseablePolicy = parseEnum(this.raw.getProperty("core.replace.unparseablePolicy"),
        ReplaceUnparseablePolicy.class, ReplaceUnparseablePolicy.WARN, "core.replace.unparseablePolicy");
this.replaceIdentityPolicy = parseEnum(this.raw.getProperty("core.replace.identityPolicy"),
        ReplaceIdentityPolicy.class, ReplaceIdentityPolicy.ALLOW, "core.replace.identityPolicy");
this.replaceDiagnostics = parseEnum(this.raw.getProperty("core.replace.diagnostics"),
        ReplaceDiagnostics.class, ReplaceDiagnostics.OFF, "core.replace.diagnostics");
}

/**
 * Case-insensitive enum property with a default for absent/blank.
 *
 * An unrecognised value throws rather than falling back: a policy key exists to
 * make something fail loudly, so silently ignoring a typo in that very key —
 * `strict` spelled `stict` quietly meaning `permissive` — would defeat it.
 */
private static <E extends Enum<E>> E parseEnum(String raw, Class<E> type, E fallback, String key) {
    if (raw == null || raw.isBlank()) return fallback;
    for (E candidate : type.getEnumConstants()) {
        if (candidate.name().equalsIgnoreCase(raw.trim())) return candidate;
    }
    StringBuilder allowed = new StringBuilder();
    for (E candidate : type.getEnumConstants()) {
        if (allowed.length() > 0) allowed.append('|');
        allowed.append(candidate.name().toLowerCase(java.util.Locale.ROOT));
    }
    throw new IllegalArgumentException(
            "'" + key + "': unknown value '" + raw.trim() + "'; allowed: " + allowed);
}

private static PrecomputeMode parsePrecomputeMode(String raw) {
    if (raw == null || raw.isBlank()) return PrecomputeMode.AUTO;
    switch (raw.trim().toLowerCase(java.util.Locale.ROOT)) {
        case "java":
        case "jvm":
        case "memory":
            return PrecomputeMode.JAVA;
        case "db":
        case "pg":
        case "postgres":
        case "postgresql":
            return PrecomputeMode.DB;
        case "auto":
        case "":
            return PrecomputeMode.AUTO;
        default:
            log.warn("Unknown core.precompute='{}', falling back to AUTO", raw);
            return PrecomputeMode.AUTO;
    }
}

private static IntermediateStorageMode parseStorageMode(String raw) {
    if (raw == null || raw.isBlank()) return IntermediateStorageMode.PG;
    switch (raw.trim().toLowerCase(java.util.Locale.ROOT)) {
        case "memory":
        case "java":
        case "mem":
        case "in-memory":
            return IntermediateStorageMode.MEMORY;
        case "pg":
        case "postgres":
        case "postgresql":
        case "":
            return IntermediateStorageMode.PG;
        default:
            log.warn("Unknown core.intermediate.storage='{}', falling back to PG", raw);
            return IntermediateStorageMode.PG;
    }
}

/** Tier-1 win 1.2: return a raw property value from fw.properties, or
 *  null if absent.  Used by {@link com.company.MainRefactored} to pick
 *  the {@link com.company.excel.ScheduleParser} impl without bloating
 *  AppConfig with new typed fields for every minor knob. */
public String rawProperty(String key) {
    return raw.getProperty(key);
}




public static AppConfig load() throws IOException {
return load(Paths.get("./fw.properties"));
}


public static AppConfig load(Path propsFile) throws IOException {
var p = new Properties();
try (InputStream in = Files.newInputStream(propsFile)) {
p.load(in);
}
applyEnvSecretFallback(p);
return fromProperties(p);
}

// A blank/missing 'db.password' falls back to CORE_DB_PASSWORD from the
// environment — lets fw.properties be committed without a literal credential
// while keeping direct (non-Bundle) launches working for an operator who has
// the env var set. The file value still wins when present (never silently
// overridden), so existing deployments that *do* set it explicitly see no
// change.
private static void applyEnvSecretFallback(Properties p) {
String filePassword = p.getProperty("db.password");
if (filePassword == null || filePassword.isBlank()) {
String envPassword = System.getenv("CORE_DB_PASSWORD");
if (envPassword != null && !envPassword.isBlank()) {
p.setProperty("db.password", envPassword);
}
}
}

private static AppConfig fromProperties(Properties p) {


validateProperties(p);
return new AppConfig(
parseDb(p),
parseThreading(p),
parsePaths(p),
parseTablespace(p),
parseFlags(p),
parseOptional(p),
parseHold(p),
parsePool(p),
parseWorkbook(p),
parseSeq(p),
p   // Tier-1 win 1.2: stash raw Properties for ad-hoc lookups
);
}




private static void validateProperties(Properties p) {
log.warn("[fail-honest][AI-proposition] pre-flight: config/contract checks are best-effort (MEDIUM-confidence: pre-flight validation of config/contract is worth it). Non-blocking note — processing logic unchanged.");
List<String> errors = new ArrayList<>();


requireNonBlank(p, "db.user",   errors);
requireNonBlank(p, "db.password", errors);
requireNonBlank(p, "db.host",   errors);
requireNonBlank(p, "db.name",   errors);
requireNonBlank(p, "excel.file", errors);


requireInt(p, "db.port",                                 1, 65535, errors);
requireLong(p, "core.limitVarGivenLessThan",             1L, Long.MAX_VALUE, errors);
requireInt(p, "core.counter4copyMax",                    1, Integer.MAX_VALUE, errors);
requireInt(p, "core.sleepTimeAfterDisconnect4copyDB",    0, Integer.MAX_VALUE, errors);
requireInt(p, "core.sleepTimeCheckFinalFilled",          0, Integer.MAX_VALUE, errors);
requireInt(p, "core.optional.limitOptionalSheetsCombosMax", 0, Integer.MAX_VALUE, errors);
requireInt(p, "core.optional.numberOptionalSheetCombosMultithreadStartsAfter", 0, Integer.MAX_VALUE, errors);


requireInt(p, "delay_holdCleanupAndEraseExcludedTablesThread",       0, Integer.MAX_VALUE, errors);
requireInt(p, "delay_holdMockupPreparationOfSqlFinalTableThread",    0, Integer.MAX_VALUE, errors);
requireInt(p, "delay_holdFnlThread",                                 0, Integer.MAX_VALUE, errors);
requireInt(p, "delay_holdOptsThread",                                0, Integer.MAX_VALUE, errors);


String workerRaw = p.getProperty("core.providedNofWorkerThreadsIntoFixedThreadPool");
if (workerRaw != null && !workerRaw.isBlank() && !workerRaw.trim().matches("\\d+")) {
errors.add("'core.providedNofWorkerThreadsIntoFixedThreadPool': must be a positive integer " +
"(or empty/absent to use all CPU cores). Got: '" + workerRaw.trim() + "'");
}

if (!errors.isEmpty()) {
var sb = new StringBuilder();
sb.append("\n╔══════════════════════════════════════════════════════════════╗\n");
sb.append("║  fw.properties configuration errors (").append(errors.size()).append(" problem");
sb.append(errors.size() == 1 ? "" : "s").append(" found)").append("  ║\n");
sb.append("╠══════════════════════════════════════════════════════════════╣\n");
for (int i = 0; i < errors.size(); i++) {
sb.append("║  ").append(i + 1).append(". ").append(errors.get(i)).append("\n");
}
sb.append("╚══════════════════════════════════════════════════════════════╝\n");
sb.append("→ Please fix the above in fw.properties and restart the application.");
String msg = sb.toString();
log.error(msg);
throw new ConfigurationException(msg);
}
log.debug("fw.properties validation passed — all required keys present and valid");
}

private static void requireNonBlank(Properties p, String key, List<String> errors) {
String v = p.getProperty(key);
if (v == null || v.isBlank()) {
errors.add("'" + key + "': required but missing or blank");
}
}

private static void requireInt(Properties p, String key, int min, int max, List<String> errors) {
String v = p.getProperty(key);
if (v == null || v.isBlank()) {
errors.add("'" + key + "': required integer key is missing or blank");
return;
}
try {
int n = Integer.parseInt(v.trim());
if (n < min || n > max) {
errors.add("'" + key + "': value " + n + " is outside allowed range [" + min + ".." + max + "]");
}
} catch (NumberFormatException e) {
errors.add("'" + key + "': must be an integer, got '" + v.trim() + "'");
}
}

private static void requireLong(Properties p, String key, long min, long max, List<String> errors) {
String v = p.getProperty(key);
if (v == null || v.isBlank()) {
errors.add("'" + key + "': required long integer key is missing or blank");
return;
}
try {
long n = Long.parseLong(v.trim());
if (n < min || n > max) {
errors.add("'" + key + "': value " + n + " is outside allowed range [" + min + ".." + max + "]");
}
} catch (NumberFormatException e) {
errors.add("'" + key + "': must be a long integer, got '" + v.trim() + "'");
}
}




public static final class DbConfig {
public final String user;

public final char[] password;
public final String host;
public final String hostIp;
public final int    port;
public final String name;

public DbConfig(String user, char[] password, String host,
String hostIp, int port, String name) {
this.user     = user;
this.password = password;
this.host     = host;
this.hostIp   = hostIp;
this.port     = port;
this.name     = name;
}


public String jdbcUrl() {
return "jdbc:postgresql://" + host + ":" + port + "/" + name;
}


public String passwordAsString() {
return new String(password);
}
}


public static final class ThreadingConfig {
public final int  workerCount;
public final long limitVarGivenLessThan;
public final int  counter4copyMax;
public final int  sleepTimeAfterDisconnect4copyDb;
public final int  sleepTimeCheckFinalFilled;

public final boolean parallelizeSubCombosIfPossible;
public final long    parallelThreshold;
public final int     parallelChunks;


public ThreadingConfig(int workerCount, long limitVarGivenLessThan,
int counter4copyMax, int sleepTimeAfterDisconnect4copyDb,
int sleepTimeCheckFinalFilled,
boolean parallelizeSubCombosIfPossible,
long parallelThreshold,
int parallelChunks) {
this.workerCount                   = workerCount;
this.limitVarGivenLessThan         = limitVarGivenLessThan;
this.counter4copyMax               = counter4copyMax;
this.sleepTimeAfterDisconnect4copyDb = sleepTimeAfterDisconnect4copyDb;
this.sleepTimeCheckFinalFilled     = sleepTimeCheckFinalFilled;

this.parallelizeSubCombosIfPossible = parallelizeSubCombosIfPossible;
this.parallelThreshold              = parallelThreshold;
this.parallelChunks                 = parallelChunks;

}
}


public static final class PathConfig {
public final String xlsxFilePath;
public final String coreXSqlFilesPath;
public final String postgresqlBinPath;
public final String javaExePath;
public final String combinatoricsReaderPath;

public PathConfig(String xlsxFilePath, String coreXSqlFilesPath,
String postgresqlBinPath, String javaExePath,
String combinatoricsReaderPath) {
this.xlsxFilePath           = xlsxFilePath;
this.coreXSqlFilesPath      = coreXSqlFilesPath;
this.postgresqlBinPath      = postgresqlBinPath;
this.javaExePath            = javaExePath;
this.combinatoricsReaderPath = combinatoricsReaderPath;
}
}


public static final class TablespaceConfig {
public final String              fastDiskTablespace;
public final String              fastDiskParams;
public final String              extendedDiskTablespace;
public final String              extendedDiskParams;
public final List<String>        additionalTablespaces;
public final boolean             isCopyDb;
public final Map<String, String> tablespace2Path;
public final Map<String, String> database2Tablespace;

public TablespaceConfig(String fastDiskTablespace, String fastDiskParams,
String extendedDiskTablespace, String extendedDiskParams,
List<String> additionalTablespaces, boolean isCopyDb,
Map<String, String> tablespace2Path,
Map<String, String> database2Tablespace) {
this.fastDiskTablespace    = fastDiskTablespace;
this.fastDiskParams        = fastDiskParams;
this.extendedDiskTablespace = extendedDiskTablespace;
this.extendedDiskParams    = extendedDiskParams;
this.additionalTablespaces = Collections.unmodifiableList(new ArrayList<>(additionalTablespaces));
this.isCopyDb              = isCopyDb;
this.tablespace2Path       = Collections.unmodifiableMap(new LinkedHashMap<>(tablespace2Path));
this.database2Tablespace   = Collections.unmodifiableMap(new LinkedHashMap<>(database2Tablespace));
}
}


public static final class FeatureFlags {
public final boolean printPretty;
public final boolean preEraseDb;
public final boolean setLoggedTablesAtEnd;
public final boolean distinctifyFwFinalOptTables;
public final boolean distinctifyFwXYTables;
public final boolean countInDbTest;
public final boolean countInDbTestNotEqualStop;
public final boolean launchReader;
public final boolean skipIfInvalidFilePath;
/** [Iter3.2 Option C] When true, fw_final / fw_opt&lt;i&gt; distinctify uses an
 *  in-JVM HashSet of 64-bit row hashes (streams rows, identifies duplicates
 *  by hash collision, then issues PG DELETE) instead of the PG-side
 *  in-place DELETE/GROUP-BY.  Trades JVM heap for compute speed.  Only
 *  consulted when {@link #distinctifyFwFinalOptTables} (or
 *  {@link #distinctifySampleAndSkip} fall-through) actually invokes a
 *  distinctify pass.  Property: {@code core.distinctify.javaSide}. */
public final boolean distinctifyJavaSide;
/** [Iter3.3 Option D] When true, run a TABLESAMPLE-based duplicate probe
 *  BEFORE the actual distinctify pass.  If the sample shows no duplicates,
 *  skip the pass entirely.  Overrides all other distinctify strategy flags
 *  (PG-side AND in-JVM Option C) for the skip decision; when the sample
 *  does see duplicates the run falls through to whatever strategy
 *  {@link #distinctifyJavaSide} selects.  Property:
 *  {@code core.distinctify.sampleAndSkip}. */
public final boolean distinctifySampleAndSkip;

public FeatureFlags(boolean printPretty, boolean preEraseDb, boolean setLoggedTablesAtEnd,
boolean distinctifyFwFinalOptTables, boolean distinctifyFwXYTables,
boolean countInDbTest, boolean countInDbTestNotEqualStop,
boolean launchReader, boolean skipIfInvalidFilePath,
boolean distinctifyJavaSide, boolean distinctifySampleAndSkip) {
this.printPretty                  = printPretty;
this.preEraseDb                   = preEraseDb;
this.setLoggedTablesAtEnd         = setLoggedTablesAtEnd;
this.distinctifyFwFinalOptTables  = distinctifyFwFinalOptTables;
this.distinctifyFwXYTables        = distinctifyFwXYTables;
this.countInDbTest                = countInDbTest;
this.countInDbTestNotEqualStop    = countInDbTestNotEqualStop;
this.launchReader                 = launchReader;
this.skipIfInvalidFilePath        = skipIfInvalidFilePath;
this.distinctifyJavaSide          = distinctifyJavaSide;
this.distinctifySampleAndSkip     = distinctifySampleAndSkip;
}
}


public static final class OptionalConfig {
public final int          limitOptionalSheetsCombosMax;
public final int          numberOptionalSheetCombosMultithreadAfter;
public final List<Integer> includeOptionalCombiPairsToDB;

public OptionalConfig(int limitOptionalSheetsCombosMax,
int numberOptionalSheetCombosMultithreadAfter,
List<Integer> includeOptionalCombiPairsToDB) {
this.limitOptionalSheetsCombosMax            = limitOptionalSheetsCombosMax;
this.numberOptionalSheetCombosMultithreadAfter = numberOptionalSheetCombosMultithreadAfter;
this.includeOptionalCombiPairsToDB           =
Collections.unmodifiableList(new ArrayList<>(includeOptionalCombiPairsToDB));
}
}



public static final class WorkbookConfig {
public final boolean autoGenerateMissingSheetsFromFwSeq;
public final boolean autoGenerateMissingFwSheetNames;
public final String  virtualSheetNamePrefix;

public WorkbookConfig(boolean autoGenerateMissingSheetsFromFwSeq,
boolean autoGenerateMissingFwSheetNames,
String  virtualSheetNamePrefix) {
this.autoGenerateMissingSheetsFromFwSeq = autoGenerateMissingSheetsFromFwSeq;
this.autoGenerateMissingFwSheetNames    = autoGenerateMissingFwSheetNames;
this.virtualSheetNamePrefix             = virtualSheetNamePrefix;
}
}


public static final class SeqConfig {
public final boolean headlessRowsAutoSynthesizeTarget;
public final boolean nestedFwBraceEnabled;
/**
 * Tier-0 bug fix 0.6 — auto-promote rows that carry exactly one
 * combo-rule verb (FW_Combi / FW_CombiR / FW_Permut / FW_PermutR /
 * FW_Subsets) so the engine reliably populates both fw_&lt;key&gt; AND
 * fw2_&lt;key&gt; tables.  Without the duplicate, joiners read fw2_&lt;key&gt;
 * and find 0 rows.  Default true; set
 * {@code seq.autoPromoteSingleVerb=false} to restore the legacy
 * single-verb behaviour (e.g. for fixtures that rely on the bug).
 */
public final boolean autoPromoteSingleVerb;

/** Legacy 2-arg constructor — defaults autoPromoteSingleVerb to true. */
public SeqConfig(boolean headlessRowsAutoSynthesizeTarget,
boolean nestedFwBraceEnabled) {
this(headlessRowsAutoSynthesizeTarget, nestedFwBraceEnabled, true);
}

public SeqConfig(boolean headlessRowsAutoSynthesizeTarget,
boolean nestedFwBraceEnabled,
boolean autoPromoteSingleVerb) {
this.headlessRowsAutoSynthesizeTarget = headlessRowsAutoSynthesizeTarget;
this.nestedFwBraceEnabled             = nestedFwBraceEnabled;
this.autoPromoteSingleVerb            = autoPromoteSingleVerb;
}
}



public static final class HoldConfig {
public final boolean holdCleanup;
public final boolean holdMockup;
public final boolean holdFnl;
public final boolean holdOpts;
public final int     delayCleanupMs;
public final int     delayMockupMs;
public final int     delayFnlMs;
public final int     delayOptsMs;

public HoldConfig(boolean holdCleanup, boolean holdMockup,
boolean holdFnl,     boolean holdOpts,
int delayCleanupMs,  int delayMockupMs,
int delayFnlMs,      int delayOptsMs) {
this.holdCleanup    = holdCleanup;
this.holdMockup     = holdMockup;
this.holdFnl        = holdFnl;
this.holdOpts       = holdOpts;
this.delayCleanupMs = delayCleanupMs;
this.delayMockupMs  = delayMockupMs;
this.delayFnlMs     = delayFnlMs;
this.delayOptsMs    = delayOptsMs;
}
}



private static DbConfig parseDb(Properties p) {
return new DbConfig(
p.getProperty("db.user"),
p.getProperty("db.password").toCharArray(),
p.getProperty("db.host"),
p.getProperty("db.hostIP"),
Integer.parseInt(p.getProperty("db.port")),
p.getProperty("db.name")
);
}

private static ThreadingConfig parseThreading(Properties p) {
return new ThreadingConfig(
resolveWorkerCount(p.getProperty("core.providedNofWorkerThreadsIntoFixedThreadPool")),
Long.parseLong(p.getProperty("core.limitVarGivenLessThan")),
Integer.parseInt(p.getProperty("core.counter4copyMax")),
Integer.parseInt(p.getProperty("core.sleepTimeAfterDisconnect4copyDB")),
Integer.parseInt(p.getProperty("core.sleepTimeCheckFinalFilled")),
Boolean.parseBoolean(p.getProperty("core.threading.parallelizeSubCombosIfPossible", "false")),
getLongOrDefault(p, "core.threading.parallelThreshold", 10_000L),
getIntOrDefault(p,  "core.threading.parallelChunks",    0)

);
}

private static PathConfig parsePaths(Properties p) {
return new PathConfig(
p.getProperty("excel.file"),
p.getProperty("sql.generate.files.pathCoreXsqlFiles"),
p.getProperty("sql.generate.path2PostgresqlBinFolder"),
p.getProperty("JavaExe_fileLocationPath"),
p.getProperty("CombinatoricsReader_fileLocationPath")
);
}

private static TablespaceConfig parseTablespace(Properties p) {
return new TablespaceConfig(
p.getProperty("db.fastDiskTablespace"),
p.getProperty("db.fastDiskTablespace.paramsCSVList"),
p.getProperty("db.extendedDiskTablespace"),
p.getProperty("db.extendedDiskTablespace.paramsCSVList"),
splitCsvList(p.getProperty("db.additionalDiskTablespacesCSVList")),
Boolean.parseBoolean(p.getProperty("db.isCopyDBtoAdditionalDiskTablespaces")),
parseKvMap(p.getProperty("db.tablespace2pathMappingCSVList")),
parseKvMap(p.getProperty("db.database2tablespaceMappingCSVList"))
);
}

private static FeatureFlags parseFlags(Properties p) {
return new FeatureFlags(
Boolean.parseBoolean(p.getProperty("console.output.isPrintPretty")),
Boolean.parseBoolean(p.getProperty("db.preEraseDB")),
Boolean.parseBoolean(p.getProperty("db.setLoggedAllTablesAtTheEndOfAllINSERTs")),
Boolean.parseBoolean(p.getProperty("distinctify__fw_final_opt__Tables")),
Boolean.parseBoolean(p.getProperty("distinctify__fwX_Y__Tables")),
Boolean.parseBoolean(p.getProperty("countInDBtest")),
Boolean.parseBoolean(p.getProperty("countInDBtest_notEqualStop")),
Boolean.parseBoolean(p.getProperty("isLaunchReader")),
Boolean.parseBoolean(p.getProperty("skipIf_invalidFileLocationPath")),
getBoolOrDefault(p, "core.distinctify.javaSide",      false),
getBoolOrDefault(p, "core.distinctify.sampleAndSkip", false)
);
}

private static OptionalConfig parseOptional(Properties p) {
return new OptionalConfig(
Integer.parseInt(p.getProperty("core.optional.limitOptionalSheetsCombosMax")),
Integer.parseInt(p.getProperty("core.optional.numberOptionalSheetCombosMultithreadStartsAfter")),
parseIntList(p.getProperty("core.optional.includeOptionalCombiPairsToDBCSVList"))
);
}


private static WorkbookConfig parseWorkbook(Properties p) {
return new WorkbookConfig(
getBoolOrDefault(p, "workbook.autoGenerateMissingSheetsFromFwSeq", true),
getBoolOrDefault(p, "workbook.autoGenerateMissingFwSheetNames",    true),
getStringOrDefault(p, "workbook.virtualSheetNamePrefix", "FW_VIRTUAL_")
);
}

private static SeqConfig parseSeq(Properties p) {
return new SeqConfig(
getBoolOrDefault(p, "seq.headlessRowsAutoSynthesizeTarget", true),
getBoolOrDefault(p, "seq.nestedFwBraceEnabled",             true),
getBoolOrDefault(p, "seq.autoPromoteSingleVerb",            true)
);
}

private static boolean getBoolOrDefault(Properties p, String key, boolean defaultVal) {
String v = p.getProperty(key);
if (v == null || v.isBlank()) return defaultVal;
return Boolean.parseBoolean(v.trim());
}

private static String getStringOrDefault(Properties p, String key, String defaultVal) {
String v = p.getProperty(key);
return (v == null || v.isBlank()) ? defaultVal : v.trim();
}


private static HoldConfig parseHold(Properties p) {
return new HoldConfig(
Boolean.parseBoolean(p.getProperty("holdCleanupAndEraseExcludedTablesThread")),
Boolean.parseBoolean(p.getProperty("holdMockupPreparationOfSqlFinalTableThread")),
Boolean.parseBoolean(p.getProperty("holdFnlThread")),
Boolean.parseBoolean(p.getProperty("holdOptsThread")),
Integer.parseInt(p.getProperty("delay_holdCleanupAndEraseExcludedTablesThread")),
Integer.parseInt(p.getProperty("delay_holdMockupPreparationOfSqlFinalTableThread")),
Integer.parseInt(p.getProperty("delay_holdFnlThread")),
Integer.parseInt(p.getProperty("delay_holdOptsThread"))
);
}



private static int resolveWorkerCount(String raw) {
if (raw == null || !raw.trim().matches("\\d+")) {
return Runtime.getRuntime().availableProcessors();
}
int n = Integer.parseInt(raw.trim());
return n < 1 ? Runtime.getRuntime().availableProcessors() : n;
}

private static List<String> splitCsvList(String raw) {
if (raw == null || raw.isBlank()) return Collections.emptyList();
return Arrays.stream(raw.replaceAll("\\R", "").trim().split("\\s{0,},\\s{0,}"))
.filter(s -> !s.isEmpty())
.collect(Collectors.toList());
}

private static Map<String, String> parseKvMap(String raw) {
if (raw == null || raw.isBlank()) return Collections.emptyMap();
return Arrays.stream(raw.replaceAll("\\R", "").trim().split(","))
.collect(Collectors.toMap(
kv -> kv.trim().split(";")[0],
kv -> kv.trim().split(";")[1],
(a, b) -> b,
LinkedHashMap::new
));
}

private static List<Integer> parseIntList(String raw) {
if (raw == null || raw.isBlank()) return Collections.emptyList();
return Arrays.stream(raw.trim().split("\\s{0,},\\s{0,}"))
.mapToInt(Integer::parseInt)
.boxed()
.collect(Collectors.toList());
}



public static final class PoolConfig {
public final int minSize;
public final int maxSize;
public final int acquireIncrement;
public final int maxStatements;

public final int maxConcurrentCopies;

public PoolConfig(int minSize, int maxSize, int acquireIncrement,
int maxStatements, int maxConcurrentCopies) {
this.minSize              = minSize;
this.maxSize              = maxSize;
this.acquireIncrement     = acquireIncrement;
this.maxStatements        = maxStatements;
this.maxConcurrentCopies  = maxConcurrentCopies;
}
}


private static PoolConfig parsePool(Properties p) {
return new PoolConfig(
getIntOrDefault(p, "db.pool.minSize",             2),
getIntOrDefault(p, "db.pool.maxSize",             3),
getIntOrDefault(p, "db.pool.acquireIncrement",    1),
getIntOrDefault(p, "db.pool.maxStatements",       0),
getIntOrDefault(p, "db.pool.maxConcurrentCopies", 4)
);
}

private static int getIntOrDefault(Properties p, String key, int defaultVal) {
String v = p.getProperty(key);
if (v == null || v.isBlank()) return defaultVal;
try { return Integer.parseInt(v.trim()); }
catch (NumberFormatException e) { return defaultVal; }
}

private static long getLongOrDefault(Properties p, String key, long defaultVal) {
String v = p.getProperty(key);
if (v == null || v.isBlank()) return defaultVal;
try { return Long.parseLong(v.trim()); }
catch (NumberFormatException e) { return defaultVal; }
}




public Properties toHibernateProperties() {
Properties p = new Properties();


p.setProperty("hibernate.connection.url",      db.jdbcUrl());
p.setProperty("hibernate.connection.username", db.user);
p.setProperty("hibernate.connection.password", db.passwordAsString());


p.setProperty("hibernate.c3p0.min_size",         String.valueOf(pool.minSize));
p.setProperty("hibernate.c3p0.max_size",         String.valueOf(pool.maxSize));
p.setProperty("hibernate.c3p0.acquire_increment",String.valueOf(pool.acquireIncrement));
p.setProperty("hibernate.c3p0.max_statements",   String.valueOf(pool.maxStatements));

return p;
}




public static final class ConfigurationException extends RuntimeException {
public ConfigurationException(String message) {
super(message);
}
}
}
