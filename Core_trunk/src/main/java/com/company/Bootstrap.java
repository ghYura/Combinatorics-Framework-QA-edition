package com.company;
































import com.company.config.AppConfig;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Properties;

public final class Bootstrap {

private static final Logger log = LogManager.getLogger(Bootstrap.class);

/** [Iter4 Step 11] Authoritative invariants doc.  Read + logged at every
 *  startup so any future user / log-archaeologist immediately sees what
 *  the canonical output numbers are and why the engine claims them.
 *  External copy lives next to fw.properties (editable / inspectable);
 *  classpath copy in src/main/resources/ is the immutable fallback. */
private static final String CANONICAL_TRUTH_FILENAME = "README_CANONICAL_TRUTH.txt";

private Bootstrap() {
}

public static void main(String[] args) {
if (isBridgeEnabled()) {
LoggerConsoleToSmartConsolePrinterBridge.install();
}

logCanonicalTruthBanner();

try {
AppConfig.load();
} catch (IOException e) {
throw new RuntimeException(e);
}

MainRefactored.main(args);
}

/** [Iter4 Step 11] Read README_CANONICAL_TRUTH.txt and dump it to the log
 *  at INFO level inside a visible banner.  Prefer the external copy
 *  (project root, next to fw.properties).  Fall back to the classpath
 *  copy if external is missing/unreadable, and auto-restore the external
 *  copy from the classpath fallback so subsequent runs see it back in
 *  place.  Never throws — logging a doc is best-effort, not fatal. */
private static void logCanonicalTruthBanner() {
    String content = null;
    String source = null;
    Path external = Path.of(CANONICAL_TRUTH_FILENAME);
    try {
        if (Files.isReadable(external)) {
            content = Files.readString(external, StandardCharsets.UTF_8);
            source  = "external: " + external.toAbsolutePath();
        }
    } catch (Exception e) {
        log.warn("[Iter4 Step 11] External {} unreadable: {} — falling back to classpath copy",
                external, e.getMessage());
    }
    if (content == null) {
        try (InputStream in = Bootstrap.class.getClassLoader()
                .getResourceAsStream(CANONICAL_TRUTH_FILENAME)) {
            if (in != null) {
                byte[] data = in.readAllBytes();
                content = new String(data, StandardCharsets.UTF_8);
                source  = "classpath fallback (project root copy missing — auto-restoring)";
                try {
                    Files.write(external, data);
                    log.warn("[Iter4 Step 11] Auto-restored {} from classpath fallback", external);
                } catch (Exception writeErr) {
                    log.warn("[Iter4 Step 11] Auto-restore of {} failed: {}",
                            external, writeErr.getMessage());
                }
            }
        } catch (Exception e) {
            log.warn("[Iter4 Step 11] Classpath fallback {} unreadable: {}",
                    CANONICAL_TRUTH_FILENAME, e.getMessage());
        }
    }
    if (content == null) {
        log.error("[Iter4 Step 11] {} NOT FOUND in either project root or classpath — "
                + "engine continuing without canonical-truth banner.  Restore the file "
                + "to enable invariant auditing at startup.", CANONICAL_TRUTH_FILENAME);
        return;
    }
    log.info("╔══════════════════════════════════════════════════════════════════════════════╗");
    log.info("║  {} loaded from {}", CANONICAL_TRUTH_FILENAME, source);
    log.info("╠══════════════════════════════════════════════════════════════════════════════╣");
    try (BufferedReader reader = new BufferedReader(new java.io.StringReader(content))) {
        String line;
        while ((line = reader.readLine()) != null) log.info("║ {}", line);
    } catch (IOException e) {
        log.warn("[Iter4 Step 11] error streaming {} into log: {}",
                CANONICAL_TRUTH_FILENAME, e.getMessage());
    }
    log.info("╚══════════════════════════════════════════════════════════════════════════════╝");
}

private static boolean isBridgeEnabled() {
Properties p = new Properties();
Path file = Path.of("fw.properties");

if (!Files.exists(file)) {
return false;
}

try (InputStream in = Files.newInputStream(file)) {
p.load(in);
// [Refactor 18052026 / step #5] Default flipped from true → false.
// The SmartConsolePrinter daemon runs a 1600-line regex/Levenshtein/
// n-gram pipeline on every log line, burning 5-10% of one CPU core on
// log decoration that batch ingestion never reads.  Opt-in for interactive
// sessions where the pretty-print actually matters.
return Boolean.parseBoolean(
p.getProperty("loggerConsoleToSmartConsolePrinterBridgeFlag", "false").trim()
);
} catch (Exception e) {
System.err.println("fw.properties read error: " + e.getMessage());
return false;
}
}
}
