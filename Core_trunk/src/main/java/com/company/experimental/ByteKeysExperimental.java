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
import com.company.db.DbClient;
import com.company.excel.DataTypeDispatcher;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

/**
 * Everything that exists only when the EXPERIMENTAL byte-width cell keys are switched on with
 * {@code core.keys.dispatch=auto} — and nothing that a default run touches.
 *
 * <p>The default is the legacy behaviour: short keys, numbered {@code S+1..S+C}.  When the
 * experiment is requested and the workbook's key plan resolves to the byte tier
 * ({@code -127..127}), the run additionally:</p>
 * <ol>
 *   <li>announces itself loudly (a WARN banner) on the dedicated logger
 *       {@value #LOGGER_NAME}, which {@code log4j2.xml} routes to
 *       {@code logs/experimental-byte-keys.log} (the file is created on the first event only,
 *       so a default run never creates it);</li>
 *   <li>installs the DB-side guard {@code sql/experimental/byte-keys-enable.sql} (a CHECK on the
 *       key -> text map, plus the audit function), right after the workbook is parsed;</li>
 *   <li>after final assembly, audits every key-array column with
 *       {@code sql/experimental/byte-keys-audit.sql} and fails the run if any element is outside
 *       the byte window — defence in depth behind the Java-side range checks of
 *       {@code ByteKeyCodec}.</li>
 * </ol>
 * <p>{@code core.keys.audit=false} skips steps 2 and 3.  The SQL files carry
 * {@code ${BYTE_MIN}} / {@code ${BYTE_MAX}}, substituted from
 * {@link DataTypeDispatcher.Tier#BYTE} so they cannot drift from the Java constants.</p>
 */
public final class ByteKeysExperimental {

    /** Dedicated logger; used ONLY by the experiment so that its log file exists only when it is on. */
    public static final String LOGGER_NAME = "fw.experimental.byteKeys";

    public static final String ENABLE_SQL  = "/sql/experimental/byte-keys-enable.sql";
    public static final String AUDIT_SQL   = "/sql/experimental/byte-keys-audit.sql";
    public static final String DISABLE_SQL = "/sql/experimental/byte-keys-disable.sql";

    private static final Logger log = LogManager.getLogger(LOGGER_NAME);

    private ByteKeysExperimental() { }

    /** One row of the audit: a key-array column, how many elements it holds, their range, and the bad ones. */
    public record AuditRow(String table, String column, long elements, Long min, Long max, long violations) {
        @Override public String toString() {
            return table + "." + column + " elements=" + elements + " range=" + min + ".." + max
                    + " violations=" + violations;
        }
    }

    // ── decisions ────────────────────────────────────────────────────────

    /** True when the properties ask for the experiment, whatever the workbook then resolves to. */
    public static boolean requested(AppConfig.KeysConfig keys) {
        return keys != null && keys.dispatch == AppConfig.KeysConfig.Dispatch.AUTO;
    }

    /** True when this run really uses byte keys. */
    public static boolean active(DataTypeDispatcher.Plan plan) {
        return plan != null && plan.tier == DataTypeDispatcher.Tier.BYTE;
    }

    /** True when the DB-side guard and audit are to run: byte tier active and {@code core.keys.audit} on. */
    public static boolean guardsWanted(AppConfig.KeysConfig keys, DataTypeDispatcher.Plan plan) {
        return requested(keys) && active(plan) && keys.audit;
    }

    // ── announcement ─────────────────────────────────────────────────────

    /** Logs what the experiment resolved to; silent (no output at all) unless the experiment was requested. */
    public static void announce(AppConfig.KeysConfig keys, DataTypeDispatcher.Plan plan) {
        if (!requested(keys)) return;
        if (active(plan)) {
            log.warn("[EXPERIMENTAL] byte-width cell keys are ACTIVE (core.keys.dispatch=auto): rows are byte[], labels {}..{}. "
                    + "This is not the default -- set core.keys.dispatch=short (or remove the property) to return to the legacy short keys.",
                    plan.firstLabel, plan.lastLabel());
            log.info("[EXPERIMENTAL] key plan: {}", plan.describe());
            log.info("[EXPERIMENTAL] DB guard + audit: {} (core.keys.audit)", keys.audit ? "ON" : "OFF");
        } else {
            log.info("[EXPERIMENTAL] core.keys.dispatch=auto was requested, but the byte tier does not apply to this workbook -> "
                    + "short keys, exactly as in a default run. Plan: {}", plan == null ? "none" : plan.describe());
        }
    }

    // ── SQL artifacts ────────────────────────────────────────────────────

    /** The classpath SQL resource with {@code ${BYTE_MIN}} / {@code ${BYTE_MAX}} substituted. */
    public static String render(String resource) {
        try (InputStream in = ByteKeysExperimental.class.getResourceAsStream(resource)) {
            if (in == null) throw new IllegalStateException("SQL resource not found on classpath: " + resource);
            return substitute(new String(in.readAllBytes(), StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to load SQL resource: " + resource, e);
        }
    }

    /** Pure substitution step of {@link #render}; fails if a placeholder is left unresolved. */
    static String substitute(String template) {
        String sql = template
                .replace("${BYTE_MIN}", String.valueOf(DataTypeDispatcher.Tier.BYTE.min))
                .replace("${BYTE_MAX}", String.valueOf(DataTypeDispatcher.Tier.BYTE.max));
        int open = sql.indexOf("${");
        if (open >= 0) {
            throw new IllegalStateException("unresolved placeholder in experimental SQL: "
                    + sql.substring(open, Math.min(sql.length(), open + 24)));
        }
        return sql;
    }

    /** Installs the CHECK on the key map and the audit function; throws when the DB rejects it. */
    public static void installGuards(DbClient db) {
        try {
            db.executeOrThrow(render(ENABLE_SQL));
        } catch (RuntimeException e) {
            throw new IllegalStateException("[EXPERIMENTAL] byte keys: the DB guard could not be installed ("
                    + e.getMessage() + "). Set core.keys.dispatch=short to run without the experiment, "
                    + "or core.keys.audit=false to run it without the guard.", e);
        }
        log.info("[EXPERIMENTAL] DB guard installed: NumberToValue1 CHECK {}..{}, audit function ready",
                DataTypeDispatcher.Tier.BYTE.min, DataTypeDispatcher.Tier.BYTE.max);
    }

    /** Runs the audit query and returns its rows. */
    public static List<AuditRow> audit(DbClient db) {
        List<AuditRow> rows = new ArrayList<>();
        try (Connection conn = db.getConnection();
             Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(render(AUDIT_SQL))) {
            while (rs.next()) {
                long min = rs.getLong(4);  boolean minNull = rs.wasNull();
                long max = rs.getLong(5);  boolean maxNull = rs.wasNull();
                rows.add(new AuditRow(rs.getString(1), rs.getString(2), rs.getLong(3),
                        minNull ? null : min, maxNull ? null : max, rs.getLong(6)));
            }
        } catch (SQLException e) {
            throw new IllegalStateException("[EXPERIMENTAL] byte keys: the audit query failed: " + e.getMessage(), e);
        }
        return rows;
    }

    /** Logs the audit and throws if any element lies outside the byte window. */
    public static void enforce(List<AuditRow> rows) {
        long bad = 0;
        StringBuilder offenders = new StringBuilder();
        for (AuditRow r : rows) {
            bad += r.violations();
            if (r.violations() > 0) offenders.append("\n  ").append(r);
        }
        if (bad == 0) {
            log.info("[EXPERIMENTAL] byte-key audit passed: {} key column(s), every element within {}..{}",
                    rows.size(), DataTypeDispatcher.Tier.BYTE.min, DataTypeDispatcher.Tier.BYTE.max);
            return;
        }
        String msg = "[EXPERIMENTAL] byte-key audit FAILED: " + bad + " element(s) outside "
                + DataTypeDispatcher.Tier.BYTE.min + ".." + DataTypeDispatcher.Tier.BYTE.max + offenders;
        log.error(msg);
        throw new IllegalStateException(msg);
    }

    /** Removes the guard and the audit function (manual clean-up and the self tests; never automatic). */
    public static void removeGuards(DbClient db) {
        db.executeOrThrow(render(DISABLE_SQL));
        log.info("[EXPERIMENTAL] DB guard removed");
    }
}
