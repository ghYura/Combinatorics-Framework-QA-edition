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

package com.company.store;

import com.company.AppUtil;
import com.company.db.DbClient;
import com.company.db.SchemaProvisioner;
import com.company.helpers.TableDataDistinctor;

import java.sql.Array;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * PostgreSQL-backed {@link IntermediateTableStore}. Byte-identical to the
 * legacy direct-DbClient/-SchemaProvisioner calls — exists so callers can
 * dispatch through a single abstraction. {@link JavaIntermediateTableStore}
 * is the other half.
 *
 * <p>Per-key StringBuilder buffers throttle row appends into COPY batches of
 * {@code batchSize} (= {@code core.counter4copyMax} from fw.properties).
 * Buffers are flushed on {@link #flushFw}/{@link #flushFw2} OR automatically
 * when the row count reaches {@code batchSize}.</p>
 */
public final class PgIntermediateTableStore implements IntermediateTableStore {

    private static final Logger log = LogManager.getLogger(PgIntermediateTableStore.class);

    private static final String COMBOS_DATA_TYPE = "int2[]";

    private final DbClient db;
    private final SchemaProvisioner schema;
    private final int batchSize;
    private final Map<Short, String> key2sheetName;

    private final ConcurrentHashMap<Long, BufferEntry> buffers = new ConcurrentHashMap<>();

    private static final class BufferEntry {
        // [Iter2-postfix] sb is reassigned on flush — swap-out pattern keeps
        // the buffer monitor held only for the append + swap, not the JDBC
        // copyIn that follows.  See appendFwRow comment for rationale.
        StringBuilder sb = new StringBuilder();
        int count = 0;
    }

    public PgIntermediateTableStore(DbClient db, SchemaProvisioner schema,
                                    int batchSize, Map<Short, String> key2sheetName) {
        if (db == null || schema == null) throw new IllegalArgumentException("db/schema must not be null");
        this.db = db;
        this.schema = schema;
        this.batchSize = Math.max(1, batchSize);
        this.key2sheetName = key2sheetName;
    }

    @Override public String modeName() { return "pg"; }
    @Override public boolean isPgBacked() { return true; }

    // ── lifecycle ────────────────────────────────────────────────────────

    @Override
    public void createFwTable(short key) throws SQLException {
        schema.createFwTable(key);
    }

    @Override
    public void createFw2Table(short key) throws SQLException {
        schema.createFw2Table(key, COMBOS_DATA_TYPE);
    }

    // ── writes ───────────────────────────────────────────────────────────

    @Override
    public void appendFwRow(short key, long combiId, short[] combo) {
        BufferEntry be = buffers.computeIfAbsent(bufKey(key, false), k -> new BufferEntry());
        // [Iter2-postfix] Critical: do NOT call db.copyIn inside the synchronized
        // block.  On JDK 21, a virtual thread inside `synchronized` is PINNED to
        // its carrier thread for the entire duration; db.copyIn blocks on
        // copyGate.acquire (Semaphore park), c3p0 connection acquisition (native
        // lock), and JDBC COPY socket I/O — all of which would pin the carrier
        // and rapidly exhaust the FJP carrier pool, dropping CPU to ~2% with
        // all threads hung.  Swap-out the StringBuilder under the lock; flush
        // OUTSIDE the lock so the virtual thread can correctly unmount during
        // the JDBC wait.
        StringBuilder toFlush = null;
        synchronized (be) {
            be.sb.append(combiId).append('\t');
            AppUtil.appendPgArray(be.sb, combo);
            be.sb.append('\n');
            if (++be.count >= batchSize) {
                toFlush = be.sb;
                be.sb = new StringBuilder(batchSize * 64);
                be.count = 0;
            }
        }
        if (toFlush != null) {
            db.copyIn(toFlush, "fw_" + key, "combi_id, combos");
        }
    }

    @Override
    public void appendFw2Row(short key, long combiId, Long parentCombiId, short[] combo) {
        BufferEntry be = buffers.computeIfAbsent(bufKey(key, true), k -> new BufferEntry());
        // [Iter2-postfix] See appendFwRow for the carrier-pinning rationale.
        StringBuilder toFlush = null;
        synchronized (be) {
            be.sb.append(combiId).append('\t');
            if (parentCombiId == null) be.sb.append("\\N");
            else be.sb.append(parentCombiId.longValue());
            be.sb.append('\t');
            AppUtil.appendPgArray(be.sb, combo);
            be.sb.append('\n');
            if (++be.count >= batchSize) {
                toFlush = be.sb;
                be.sb = new StringBuilder(batchSize * 64);
                be.count = 0;
            }
        }
        if (toFlush != null) {
            db.copyIn(toFlush, "fw2_" + key, "combi_id, fcombi_id, combos_1");
        }
    }

    @Override public void flushFw(short key)  { flushIfPresent(key, false); }
    @Override public void flushFw2(short key) { flushIfPresent(key, true);  }

    private void flushIfPresent(short key, boolean fw2) {
        BufferEntry be = buffers.get(bufKey(key, fw2));
        if (be == null) return;
        // [Iter2-postfix] Same swap-out pattern as appendFwRow — flush outside
        // the lock to avoid pinning the virtual thread's carrier.
        StringBuilder toFlush = null;
        synchronized (be) {
            if (be.sb.length() > 0) {
                toFlush = be.sb;
                be.sb = new StringBuilder(batchSize * 64);
                be.count = 0;
            }
        }
        if (toFlush != null) {
            String table = (fw2 ? "fw2_" : "fw_") + key;
            String cols  = fw2 ? "combi_id, fcombi_id, combos_1" : "combi_id, combos";
            db.copyIn(toFlush, table, cols);
        }
    }

    // ── reads ────────────────────────────────────────────────────────────

    @Override
    public List<short[]> readFwCombos(short key) {
        return readCombos(table(key, false), "combos", null);
    }

    @Override
    public List<short[]> readFw2Combos(short key) {
        return readCombos(table(key, true), "combos_1", null);
    }

    @Override
    public List<short[]> readFwCombosWithCardinality(short key, int cardinality) {
        return readCombos(table(key, false), "combos", cardinality);
    }

    @Override
    public List<short[]> readFw2CombosWithCardinality(short key, int cardinality) {
        return readCombos(table(key, true), "combos_1", cardinality);
    }

    @Override
    public Map<Long, short[]> readFwAsMap(short key) {
        Map<Long, short[]> result = new HashMap<>();
        String sql = "SELECT combi_id, combos FROM public." + table(key, false) + " ORDER BY combi_id";
        try (Connection conn = db.getConnection();
             Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                long cid = rs.getLong(1);
                Array sqlArr = rs.getArray(2);
                short[] combo = (sqlArr == null) ? new short[0] : toShortArray(sqlArr.getArray());
                result.put(cid, combo);
            }
        } catch (SQLException e) {
            log.error("readFwAsMap({}) failed: {}", key, e.getMessage(), e);
        }
        return result;
    }

    private List<short[]> readCombos(String tableName, String column, Integer cardinality) {
        List<short[]> result = new ArrayList<>();
        StringBuilder sql = new StringBuilder("SELECT ").append(column)
                .append(" FROM public.").append(tableName);
        if (cardinality != null) {
            sql.append(" WHERE cardinality(").append(column).append(") = ").append(cardinality.intValue());
        }
        sql.append(" ORDER BY combi_id");
        try (Connection conn = db.getConnection();
             Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(sql.toString())) {
            while (rs.next()) {
                Array sqlArr = rs.getArray(1);
                if (sqlArr == null) continue;
                result.add(toShortArray(sqlArr.getArray()));
            }
        } catch (SQLException e) {
            log.error("readCombos({}, {}, card={}) failed: {}",
                      tableName, column, cardinality, e.getMessage(), e);
        }
        return result;
    }

    // ── diagnostics ──────────────────────────────────────────────────────

    @Override
    public long count(short key, boolean fw2) {
        long n = db.queryLongQuiet("SELECT COUNT(*) FROM public." + table(key, fw2) + ";");
        return n < 0 ? 0 : n;
    }

    @Override
    public long maxCombiId(short key, boolean fw2) {
        long n = db.queryLongQuiet("SELECT MAX(combi_id) FROM public." + table(key, fw2) + ";");
        return n < 0 ? 0 : n;
    }

    @Override
    public boolean exists(short key, boolean fw2) {
        String r = db.queryString(
                "SELECT CASE WHEN to_regclass('public." + table(key, fw2)
                        + "') IS NOT NULL THEN '1' ELSE '0' END;");
        return "1".equals(r);
    }

    @Override
    public boolean isEmpty(short key, boolean fw2) {
        if (!exists(key, fw2)) return true;
        String r = db.queryString(
                "SELECT CASE WHEN EXISTS (SELECT combi_id FROM public."
                        + table(key, fw2) + " LIMIT 1) THEN '1' ELSE '0' END;");
        return !"1".equals(r);
    }

    // ── transforms ───────────────────────────────────────────────────────

    @Override
    public void distinctify(short key, boolean fw2) {
        String tableName = table(key, fw2);
        new TableDataDistinctor(tableName, key, key2sheetName, db)
                .distinctifyByCopyingDistinctedDataToNewTempTableDistinctedAndRecreateGivenTableAsCopyOfNewTempTableDistincted();
    }

    @Override
    public void deleteRows(short key, boolean fw2) {
        // Absent table is a no-op by contract: the exclusion cleanup calls this
        // for BOTH fw_<k> and fw2_<k> without knowing which exists, and the
        // memory store's deleteRows is likewise a no-op for an unknown key.
        // That tolerance is expressed as an explicit existence check — a DELETE
        // that fails for any real reason (locks, auth, pool) must throw, so the
        // old swallow-everything executeSilently is exactly wrong here.
        String tbl = table(key, fw2);
        String exists = db.queryString(
                "SELECT CASE WHEN to_regclass('public." + tbl + "') IS NOT NULL THEN '1' ELSE '0' END;");
        if (!"1".equals(exists)) return;
        db.executeOrThrow("DELETE FROM public." + tbl + ";");
    }

    @Override
    public void dropTable(short key, boolean fw2) {
        // IF EXISTS already makes absence benign at the SQL level; any error
        // that still comes back (locks, dependent objects, connection) is real.
        db.executeOrThrow("DROP TABLE IF EXISTS public." + table(key, fw2) + ";");
    }

    @Override
    public void swapFw2ToFw(short key) throws SQLException {
        // Mirrors SheetWorker.processSheet between-directive swap.
        db.execute("DROP TABLE IF EXISTS fw_" + key + " CASCADE;");
        schema.createFwTable(key);
        db.execute("INSERT INTO fw_" + key + "(combi_id, combos) SELECT combi_id, combos_1 FROM fw2_" + key + ";");
        db.execute("DROP TABLE IF EXISTS fw2_" + key + " CASCADE;");
        schema.createFw2Table(key, COMBOS_DATA_TYPE);
    }

    @Override
    public void moveFwToFw2(short key) throws SQLException {
        // Mirrors BraceOperationHandler.execute post-join fw_ → fw2_ move.
        schema.createFw2Table(key, COMBOS_DATA_TYPE);
        db.execute("INSERT INTO public.fw2_" + key
                + " (combi_id, combos_1) SELECT combi_id, combos FROM public.fw_" + key + "; commit;");
        db.execute("DELETE FROM public.fw_" + key + "; commit;");
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private static String table(short key, boolean fw2) {
        return (fw2 ? "fw2_" : "fw_") + key;
    }

    private static Long bufKey(short key, boolean fw2) {
        return Long.valueOf((fw2 ? 1L << 32 : 0L) | (key & 0xFFFFL));
    }

    /** Convert JDBC PG array to short[] — mirrors FinalTableAssembler.toShortArrayFromJdbc. */
    private static short[] toShortArray(Object javaArr) {
        if (javaArr == null) return new short[0];
        if (javaArr instanceof Short[] sa) {
            short[] out = new short[sa.length];
            for (int i = 0; i < sa.length; i++) out[i] = sa[i] == null ? (short) 0 : sa[i];
            return out;
        }
        if (javaArr instanceof Integer[] ia) {
            short[] out = new short[ia.length];
            for (int i = 0; i < ia.length; i++) out[i] = ia[i] == null ? (short) 0 : ia[i].shortValue();
            return out;
        }
        if (javaArr instanceof Long[] la) {
            short[] out = new short[la.length];
            for (int i = 0; i < la.length; i++) out[i] = la[i] == null ? (short) 0 : la[i].shortValue();
            return out;
        }
        if (javaArr.getClass().isArray()) {
            int len = java.lang.reflect.Array.getLength(javaArr);
            short[] out = new short[len];
            for (int i = 0; i < len; i++) {
                Object v = java.lang.reflect.Array.get(javaArr, i);
                out[i] = (v == null) ? (short) 0 : ((Number) v).shortValue();
            }
            return out;
        }
        return new short[0];
    }
}
