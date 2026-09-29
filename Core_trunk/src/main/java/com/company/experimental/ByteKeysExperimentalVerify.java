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

package com.company.experimental;

import com.company.config.AppConfig;
import com.company.excel.DataTypeDispatcher;
import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.core.Appender;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.LoggerContext;
import org.apache.logging.log4j.core.appender.AbstractAppender;
import org.apache.logging.log4j.core.config.Configuration;
import org.apache.logging.log4j.core.config.LoggerConfig;
import org.apache.logging.log4j.core.config.Property;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * Verifier for the EXPERIMENTAL byte-key artifacts — deterministic, no DB:
 *
 *   A. the gates: the experiment exists only for {@code core.keys.dispatch=auto}, and the DB guard
 *      only for a byte-tier plan with {@code core.keys.audit} on;
 *   B. the SQL artifacts: present, placeholders resolved from {@code DataTypeDispatcher.Tier.BYTE},
 *      idempotent shapes, and an unresolved placeholder is refused;
 *   C. log4j2.xml: the experimental appender is created on demand and attached to the dedicated
 *      logger only — never to the root, so a default run cannot create the file;
 *   D. the logging contract: a default run says nothing on the experimental logger, an
 *      experimental run announces itself with a WARN, and a fallback to short is reported;
 *   E. the audit verdict: clean rows pass, an element outside the window fails the run.
 *
 * The SQL itself is executed against PostgreSQL by the end-to-end runs, not here.
 *
 * Run via:
 * {@code java -cp target/classes:$(cat /tmp/cp.txt) com.company.experimental.ByteKeysExperimentalVerify}
 */
public final class ByteKeysExperimentalVerify {
    private ByteKeysExperimentalVerify() {}

    private static int failed = 0;

    public static void main(String[] args) throws Exception {
        sectionA();
        sectionB();
        sectionC();
        sectionD();
        sectionE();
        if (failed == 0) System.out.println("\n✅ ALL BYTE-KEYS-EXPERIMENTAL CHECKS PASSED");
        else { System.out.println("\n❌ " + failed + " BYTE-KEYS-EXPERIMENTAL CHECK(S) FAILED"); System.exit(1); }
    }

    private static void assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        if (!cond) failed++;
    }

    private static AppConfig.KeysConfig keys(AppConfig.KeysConfig.Dispatch d, boolean audit) {
        return new AppConfig.KeysConfig(d, AppConfig.KeysConfig.Strategy.IDENTITY, AppConfig.KeysConfig.Scope.ALL, null, 5.0, audit);
    }

    private static DataTypeDispatcher.Plan bytePlan() {
        return DataTypeDispatcher.Plan.custom(DataTypeDispatcher.Tier.BYTE, 3, 0, 100, 4);
    }

    private static DataTypeDispatcher.Plan shortPlan() {
        return DataTypeDispatcher.Plan.custom(DataTypeDispatcher.Tier.SHORT, 3, 0, 300, 4);
    }

    // ── A: gates ─────────────────────────────────────────────────────────

    private static void sectionA() {
        System.out.println("── A. the experiment exists only when the properties ask for it ──");
        AppConfig.KeysConfig dflt = AppConfig.KeysConfig.DEFAULT;
        AppConfig.KeysConfig auto = keys(AppConfig.KeysConfig.Dispatch.AUTO, true);
        AppConfig.KeysConfig autoNoAudit = keys(AppConfig.KeysConfig.Dispatch.AUTO, false);
        assertCond("default configuration: not requested", !ByteKeysExperimental.requested(dflt) && !ByteKeysExperimental.requested(null));
        assertCond("dispatch=short: not requested", !ByteKeysExperimental.requested(keys(AppConfig.KeysConfig.Dispatch.SHORT, true)));
        assertCond("dispatch=auto: requested", ByteKeysExperimental.requested(auto));
        assertCond("active() is true for a byte-tier plan only",
                ByteKeysExperimental.active(bytePlan()) && !ByteKeysExperimental.active(shortPlan()) && !ByteKeysExperimental.active(null));
        assertCond("guards: default config never wants them, even with a byte-tier plan",
                !ByteKeysExperimental.guardsWanted(dflt, bytePlan()));
        assertCond("guards: experiment requested but the workbook fell back to short -> none",
                !ByteKeysExperimental.guardsWanted(auto, shortPlan()));
        assertCond("guards: experiment + byte tier + core.keys.audit=false -> none",
                !ByteKeysExperimental.guardsWanted(autoNoAudit, bytePlan()));
        assertCond("guards: experiment + byte tier + core.keys.audit=true -> installed and audited",
                ByteKeysExperimental.guardsWanted(auto, bytePlan()));
    }

    // ── B: SQL artifacts ─────────────────────────────────────────────────

    private static void sectionB() {
        System.out.println("── B. the SQL artifacts ──");
        String min = String.valueOf(DataTypeDispatcher.Tier.BYTE.min), max = String.valueOf(DataTypeDispatcher.Tier.BYTE.max);
        String enable = null, audit = null, disable = null;
        try { enable = ByteKeysExperimental.render(ByteKeysExperimental.ENABLE_SQL); } catch (RuntimeException e) { /* reported below */ }
        try { audit = ByteKeysExperimental.render(ByteKeysExperimental.AUDIT_SQL); } catch (RuntimeException e) { /* reported below */ }
        try { disable = ByteKeysExperimental.render(ByteKeysExperimental.DISABLE_SQL); } catch (RuntimeException e) { /* reported below */ }
        assertCond("byte-keys-enable / -audit / -disable are on the classpath and render", enable != null && audit != null && disable != null);
        if (enable == null || audit == null || disable == null) return;
        assertCond("no ${...} placeholder is left in any script",
                !enable.contains("${") && !audit.contains("${") && !disable.contains("${"));
        assertCond("the window in the SQL is the Java constant (" + min + ".." + max + "), not a copy of it",
                enable.contains("BETWEEN " + min + " AND " + max) && enable.contains("k < " + min + " OR k > " + max)
                        && DataTypeDispatcher.Tier.BYTE.min == Byte.MIN_VALUE + 1 && DataTypeDispatcher.Tier.BYTE.max == Byte.MAX_VALUE);
        assertCond("enable is idempotent: DROP CONSTRAINT IF EXISTS before ADD, CREATE OR REPLACE for the function",
                enable.contains("DROP CONSTRAINT IF EXISTS fw_byte_key_range") && enable.contains("ADD CONSTRAINT fw_byte_key_range")
                        && enable.contains("CREATE OR REPLACE FUNCTION public.fw_byte_keys_audit()"));
        assertCond("the CHECK guards the key -> text map (NumberToValue1.\"bigint\"), the column the Reader decodes",
                enable.contains("public.\"NumberToValue1\"") && enable.contains("\"bigint\" BETWEEN"));
        assertCond("the audit covers int2[], int4[] and int8[] key columns of fw_final*, fw_opt*, fw_<k>, fw2_<k>",
                enable.contains("'_int2', '_int4', '_int8'") && enable.contains("^fw_(final|opt)") && enable.contains("^fw2?_[0-9]+$"));
        assertCond("the audit query reads the function and orders its rows", audit.contains("FROM public.fw_byte_keys_audit()") && audit.contains("ORDER BY"));
        assertCond("disable is idempotent and removes what enable installed",
                disable.contains("DROP FUNCTION IF EXISTS public.fw_byte_keys_audit()")
                        && disable.contains("DROP CONSTRAINT IF EXISTS fw_byte_key_range") && disable.contains("ALTER TABLE IF EXISTS"));
        boolean refused = false;
        try { ByteKeysExperimental.substitute("SELECT ${BYTE_MIN}, ${SOMETHING_ELSE}"); } catch (IllegalStateException e) { refused = e.getMessage().contains("${SOMETHING_ELSE}"); }
        assertCond("an unresolved placeholder is refused, naming it", refused);
        boolean homePath = enable.contains("/home/") || audit.contains("/home/") || disable.contains("/home/");
        assertCond("no machine-specific path in any script", !homePath);
    }

    // ── C: log4j2.xml ────────────────────────────────────────────────────

    private static void sectionC() throws Exception {
        System.out.println("── C. log4j2.xml routes the experiment to its own file, on demand ──");
        Document doc;
        try (InputStream in = ByteKeysExperimental.class.getResourceAsStream("/log4j2.xml")) {
            assertCond("log4j2.xml is on the classpath", in != null);
            if (in == null) return;
            DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
            f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            doc = f.newDocumentBuilder().parse(in);
        }
        Element routing = null;
        NodeList routings = doc.getElementsByTagName("Routing");
        for (int i = 0; i < routings.getLength(); i++) {
            Element e = (Element) routings.item(i);
            if ("ExperimentalByteKeys".equals(e.getAttribute("name"))) routing = e;
        }
        assertCond("a Routing appender named ExperimentalByteKeys exists (it builds its file on the first event only)", routing != null);
        if (routing != null) {
            NodeList inner = routing.getElementsByTagName("File");
            Element file = inner.getLength() == 1 ? (Element) inner.item(0) : null;
            assertCond("...wrapping exactly one File appender", file != null);
            if (file != null) {
                assertCond("...writing logs/experimental-byte-keys.log", "logs/experimental-byte-keys.log".equals(file.getAttribute("fileName")));
                assertCond("...created on demand as well", "true".equals(file.getAttribute("createOnDemand")));
            }
        }
        NodeList plainFiles = doc.getElementsByTagName("File");
        boolean topLevelFile = false;
        for (int i = 0; i < plainFiles.getLength(); i++) {
            if ("Appenders".equals(plainFiles.item(i).getParentNode().getNodeName())) topLevelFile = true;
        }
        assertCond("no plain top-level File appender (log4j would create the logs/ directory at every start)", !topLevelFile);
        Element dedicated = null, root = null;
        NodeList loggers = doc.getElementsByTagName("Logger");
        for (int i = 0; i < loggers.getLength(); i++) {
            Element e = (Element) loggers.item(i);
            if (ByteKeysExperimental.LOGGER_NAME.equals(e.getAttribute("name"))) dedicated = e;
        }
        NodeList roots = doc.getElementsByTagName("Root");
        if (roots.getLength() > 0) root = (Element) roots.item(0);
        assertCond("the logger named " + ByteKeysExperimental.LOGGER_NAME + " (the Java constant) is defined", dedicated != null);
        if (dedicated != null) {
            NodeList refs = dedicated.getElementsByTagName("AppenderRef");
            boolean toFile = false;
            for (int i = 0; i < refs.getLength(); i++) if ("ExperimentalByteKeys".equals(((Element) refs.item(i)).getAttribute("ref"))) toFile = true;
            assertCond("...and it alone feeds the file appender; the console still gets its events (additive)",
                    toFile && !"false".equals(dedicated.getAttribute("additivity")));
        }
        boolean rootLeaks = false;
        if (root != null) {
            NodeList refs = root.getElementsByTagName("AppenderRef");
            for (int i = 0; i < refs.getLength(); i++) if ("ExperimentalByteKeys".equals(((Element) refs.item(i)).getAttribute("ref"))) rootLeaks = true;
        }
        assertCond("the root logger does NOT feed the experimental file (every ordinary message would create it)", !rootLeaks);
    }

    // ── D: logging contract ──────────────────────────────────────────────

    private static void sectionD() {
        System.out.println("── D. what the experiment says, and that a default run says nothing ──");
        final List<LogEvent> events = new ArrayList<>();
        LoggerContext ctx = (LoggerContext) LogManager.getContext(false);
        Configuration cfg = ctx.getConfiguration();
        Appender capture = new AbstractAppender("byteKeysCapture", null, null, true, Property.EMPTY_ARRAY) {
            @Override public void append(LogEvent e) { synchronized (events) { events.add(e.toImmutable()); } }
        };
        capture.start();
        cfg.addAppender(capture);
        LoggerConfig lc = cfg.getLoggerConfig(ByteKeysExperimental.LOGGER_NAME);
        // keep this verifier from creating logs/experimental-byte-keys.log itself
        lc.removeAppender("ExperimentalByteKeys");
        lc.addAppender(capture, Level.ALL, null);
        ctx.updateLoggers();
        try {
            ByteKeysExperimental.announce(AppConfig.KeysConfig.DEFAULT, shortPlan());
            ByteKeysExperimental.announce(AppConfig.KeysConfig.DEFAULT, null);
            ByteKeysExperimental.announce(keys(AppConfig.KeysConfig.Dispatch.SHORT, true), shortPlan());
            assertCond("a default (dispatch=short) run: not one message on the experimental logger", events.isEmpty());

            ByteKeysExperimental.announce(keys(AppConfig.KeysConfig.Dispatch.AUTO, true), bytePlan());
            boolean warn = false, mentionsOff = false;
            synchronized (events) {
                for (LogEvent e : events) {
                    String m = e.getMessage().getFormattedMessage();
                    if (e.getLevel() == Level.WARN && m.contains("[EXPERIMENTAL]") && m.contains("ACTIVE") && m.contains("core.keys.dispatch=short")) warn = true;
                }
            }
            assertCond("experiment on, byte tier: a WARN says it is active and how to switch it off", warn);
            events.clear();
            ByteKeysExperimental.announce(keys(AppConfig.KeysConfig.Dispatch.AUTO, false), bytePlan());
            synchronized (events) {
                for (LogEvent e : events) if (e.getMessage().getFormattedMessage().contains("OFF")) mentionsOff = true;
            }
            assertCond("core.keys.audit=false is reported as OFF", mentionsOff);
            events.clear();
            ByteKeysExperimental.announce(keys(AppConfig.KeysConfig.Dispatch.AUTO, true), shortPlan());
            boolean fallback = false;
            synchronized (events) {
                for (LogEvent e : events) {
                    String m = e.getMessage().getFormattedMessage();
                    if (e.getLevel() == Level.INFO && m.contains("does not apply") && m.contains("short keys")) fallback = true;
                }
            }
            assertCond("experiment requested but the workbook overflows the byte range: reported as a fallback to short", fallback);
        } finally {
            lc.removeAppender("byteKeysCapture");
            capture.stop();
            ctx.updateLoggers();
        }
    }

    // ── E: audit verdict ─────────────────────────────────────────────────

    private static void sectionE() {
        System.out.println("── E. the audit verdict ──");
        List<ByteKeysExperimental.AuditRow> clean = List.of(
                new ByteKeysExperimental.AuditRow("fw_final", "combos1_A", 90L, -41L, 127L, 0),
                new ByteKeysExperimental.AuditRow("fw_opt1", "combos2_B", 0L, null, null, 0));
        boolean cleanPasses = true;
        try { ByteKeysExperimental.enforce(clean); } catch (RuntimeException e) { cleanPasses = false; }
        assertCond("every element inside the window (an empty table included): the run passes", cleanPasses);
        List<ByteKeysExperimental.AuditRow> dirty = List.of(
                new ByteKeysExperimental.AuditRow("fw_final", "combos1_A", 90L, -32768L, 127L, 3),
                new ByteKeysExperimental.AuditRow("fw_opt1", "combos2_B", 10L, 1L, 9L, 0));
        String msg = null;
        try { ByteKeysExperimental.enforce(dirty); } catch (IllegalStateException e) { msg = e.getMessage(); }
        assertCond("an element outside -127..127 fails the run, naming the table, the column and the count",
                msg != null && msg.contains("fw_final.combos1_A") && msg.contains("3 element(s)") && msg.contains("-127..127")
                        && !msg.contains("fw_opt1"));
    }
}
