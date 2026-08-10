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

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * In-memory {@link IntermediateTableStore}. Replaces PostgreSQL fw_&lt;key&gt; /
 * fw2_&lt;key&gt; intermediate tables with Java structures so the engine can skip
 * COPY/DROP/SELECT round-trips on the intermediate stage. Final-stage
 * (fw_final, fw_opt&lt;i&gt;) tables still go to PG through DbClient directly.
 *
 * <p>Design:</p>
 * <ul>
 *   <li>Per-key {@code TableData} holds two parallel lists (fw and fw2).</li>
 *   <li>Each list is a synchronized ArrayList of {@code Row} (combiId,
 *       parentCombiId, combo[]).</li>
 *   <li>Distinctify uses a {@code LinkedHashMap} keyed by an {@code Arrays.hashCode}
 *       wrapper, preserving first occurrence — matches the legacy
 *       SELECT-DISTINCT semantics (TableDataDistinctor).</li>
 * </ul>
 *
 * <p>Memory: every row's combo is retained as a short[] reference. Caller is
 * responsible for ensuring the array isn't mutated after append (matches the
 * existing fwKeyShort accumulator convention). At 350 MB per 25 M rows × 7-cell
 * short[] this is feasible on a default -Xmx4g but worth monitoring on large
 * workbooks.</p>
 */
public final class JavaIntermediateTableStore implements IntermediateTableStore {

    private static final Logger log = LogManager.getLogger(JavaIntermediateTableStore.class);

    private final ConcurrentHashMap<Short, TableData> tables = new ConcurrentHashMap<>();

    private static final class Row {
        final long combiId;
        final Long parentCombiId;  // null in fw_<k>
        final short[] combo;
        Row(long combiId, Long parentCombiId, short[] combo) {
            this.combiId = combiId; this.parentCombiId = parentCombiId; this.combo = combo;
        }
    }

    private static final class TableData {
        // Synchronized lists for per-key concurrent appends (sheets are independent
        // virtual threads; same-key writes are serialized by SheetWorker's loop).
        final List<Row> fw  = Collections.synchronizedList(new ArrayList<>());
        final List<Row> fw2 = Collections.synchronizedList(new ArrayList<>());
        // Existence flags — set on createFwTable / createFw2Table or first append.
        volatile boolean fwExists  = false;
        volatile boolean fw2Exists = false;
    }

    private TableData tableFor(short key) {
        return tables.computeIfAbsent(key, k -> new TableData());
    }

    @Override public String modeName() { return "memory"; }
    @Override public boolean isPgBacked() { return false; }

    // ── lifecycle ────────────────────────────────────────────────────────

    @Override public void createFwTable(short key) throws SQLException {
        tableFor(key).fwExists = true;
    }

    @Override public void createFw2Table(short key) throws SQLException {
        tableFor(key).fw2Exists = true;
    }

    // ── writes ───────────────────────────────────────────────────────────

    @Override
    public void appendFwRow(short key, long combiId, short[] combo) {
        TableData td = tableFor(key);
        td.fwExists = true;
        td.fw.add(new Row(combiId, null, combo));
    }

    @Override
    public void appendFw2Row(short key, long combiId, Long parentCombiId, short[] combo) {
        TableData td = tableFor(key);
        td.fw2Exists = true;
        td.fw2.add(new Row(combiId, parentCombiId, combo));
    }

    @Override public void flushFw(short key)  { /* memory: noop */ }
    @Override public void flushFw2(short key) { /* memory: noop */ }

    // ── reads ────────────────────────────────────────────────────────────

    @Override
    public List<short[]> readFwCombos(short key) {
        return collectCombos(listOf(key, false), null);
    }

    @Override
    public List<short[]> readFw2Combos(short key) {
        return collectCombos(listOf(key, true), null);
    }

    @Override
    public List<short[]> readFwCombosWithCardinality(short key, int cardinality) {
        return collectCombos(listOf(key, false), cardinality);
    }

    @Override
    public List<short[]> readFw2CombosWithCardinality(short key, int cardinality) {
        return collectCombos(listOf(key, true), cardinality);
    }

    @Override
    public Map<Long, short[]> readFwAsMap(short key) {
        List<Row> rows = listOf(key, false);
        Map<Long, short[]> out = new HashMap<>(Math.max(16, rows.size()));
        synchronized (rows) {
            for (Row r : rows) out.put(r.combiId, r.combo);
        }
        return out;
    }

    private List<Row> listOf(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return Collections.emptyList();
        return fw2 ? td.fw2 : td.fw;
    }

    private static List<short[]> collectCombos(List<Row> src, Integer cardinality) {
        List<short[]> out = new ArrayList<>();
        synchronized (src) {
            for (Row r : src) {
                if (cardinality != null && r.combo.length != cardinality.intValue()) continue;
                out.add(r.combo);
            }
        }
        return out;
    }

    // ── diagnostics ──────────────────────────────────────────────────────

    @Override
    public long count(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return 0L;
        List<Row> l = fw2 ? td.fw2 : td.fw;
        synchronized (l) { return l.size(); }
    }

    @Override
    public long maxCombiId(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return 0L;
        List<Row> l = fw2 ? td.fw2 : td.fw;
        long max = 0L;
        synchronized (l) {
            for (Row r : l) if (r.combiId > max) max = r.combiId;
        }
        return max;
    }

    @Override
    public boolean exists(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return false;
        return fw2 ? td.fw2Exists : td.fwExists;
    }

    @Override
    public boolean isEmpty(short key, boolean fw2) {
        return count(key, fw2) == 0L;
    }

    // ── transforms ───────────────────────────────────────────────────────

    @Override
    public void distinctify(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return;
        List<Row> src = fw2 ? td.fw2 : td.fw;
        // Dedup by combos, preserve first occurrence (matches legacy SELECT DISTINCT /
        // MIN(combi_id) GROUP BY data_cols). combi_id is NOT a distinctifying field
        // because TableDataDistinctor excludes it via the excludedCols filter.
        LinkedHashMap<ComboKey, Row> dedup;
        synchronized (src) {
            dedup = new LinkedHashMap<>(src.size());
            for (Row r : src) dedup.putIfAbsent(new ComboKey(r.combo), r);
            src.clear();
            src.addAll(dedup.values());
        }
    }

    @Override
    public void deleteRows(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return;
        List<Row> l = fw2 ? td.fw2 : td.fw;
        synchronized (l) { l.clear(); }
    }

    @Override
    public void dropTable(short key, boolean fw2) {
        TableData td = tables.get(key);
        if (td == null) return;
        List<Row> l = fw2 ? td.fw2 : td.fw;
        synchronized (l) { l.clear(); }
        if (fw2) td.fw2Exists = false; else td.fwExists = false;
        // Don't remove the TableData entry — caller may still query exists/empty
        // and SheetWorker often drops fw_ then re-creates it.
    }

    @Override
    public void swapFw2ToFw(short key) throws SQLException {
        TableData td = tableFor(key);
        synchronized (td.fw) {
            synchronized (td.fw2) {
                td.fw.clear();
                for (Row r : td.fw2) {
                    // fw_ rows have null parentCombiId (combos column is the array)
                    td.fw.add(new Row(r.combiId, null, r.combo));
                }
                td.fw2.clear();
                td.fwExists  = true;
                td.fw2Exists = true;  // recreated empty (matches PG schema.createFw2Table after DROP)
            }
        }
    }

    @Override
    public void moveFwToFw2(short key) throws SQLException {
        TableData td = tableFor(key);
        synchronized (td.fw) {
            synchronized (td.fw2) {
                // PG creates fw2_ if missing then INSERT INTO fw2_ (combi_id, combos_1)
                // SELECT combi_id, combos FROM fw_, then DELETE FROM fw_.
                td.fw2Exists = true;
                for (Row r : td.fw) {
                    td.fw2.add(new Row(r.combiId, null, r.combo));
                }
                td.fw.clear();
            }
        }
    }

    // ── Iter4.5 drain support ────────────────────────────────────────────

    /** [Iter4.5] Migrate every (key, fw|fw2) row in this in-memory store to
     *  the supplied target store (typically a {@link PgIntermediateTableStore})
     *  so the pipeline can switch backends mid-run after a heap-pressure event.
     *
     *  <p>CALLER MUST ensure no concurrent writes to THIS store while
     *  {@code drainAllTo} runs (e.g. by quiescing the pipeline first).  Calls
     *  {@link IntermediateTableStore#createFwTable}/{@code createFw2Table} on
     *  the target before appending so PG-backed targets get their UNLOGGED
     *  tables materialised.  Flushes after each key so per-key COPY batches
     *  reach PG promptly.</p>
     *
     *  <p>After this returns, the in-memory state is left intact — caller can
     *  drop the JavaIntermediateTableStore reference (GC reclaims the heap)
     *  OR keep it for inspection.  Recommend dropping to free memory.</p> */
    public void drainAllTo(IntermediateTableStore target) throws SQLException {
        if (target == null) throw new IllegalArgumentException("target must be non-null");
        if (target == this) throw new IllegalArgumentException("cannot drain to self");
        long totalRows = 0L;
        for (Map.Entry<Short, TableData> entry : tables.entrySet()) {
            Short key = entry.getKey();
            TableData td = entry.getValue();
            if (td.fwExists) {
                target.createFwTable(key);
                synchronized (td.fw) {
                    for (Row r : td.fw) {
                        target.appendFwRow(key, r.combiId, r.combo);
                        totalRows++;
                    }
                }
                target.flushFw(key);
            }
            if (td.fw2Exists) {
                target.createFw2Table(key);
                synchronized (td.fw2) {
                    for (Row r : td.fw2) {
                        target.appendFw2Row(key, r.combiId, r.parentCombiId, r.combo);
                        totalRows++;
                    }
                }
                target.flushFw2(key);
            }
        }
        log.info("[Iter4.5/drain] migrated {} rows across {} keys from in-memory store to '{}'",
                totalRows, tables.size(), target.modeName());
    }

    // ── helpers ──────────────────────────────────────────────────────────

    /** Wrapper around short[] giving proper hashCode/equals (Arrays.* semantics)
     *  so it can serve as a LinkedHashMap key during distinctify. */
    private static final class ComboKey {
        final short[] arr;
        final int hash;
        ComboKey(short[] arr) {
            this.arr = arr;
            this.hash = Arrays.hashCode(arr);
        }
        @Override public int hashCode() { return hash; }
        @Override public boolean equals(Object o) {
            return (o instanceof ComboKey ck) && Arrays.equals(arr, ck.arr);
        }
    }
}
