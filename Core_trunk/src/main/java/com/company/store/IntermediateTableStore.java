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
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.

package com.company.store;

import java.sql.SQLException;
import java.util.List;
import java.util.Map;

/**
 * Abstraction over the per-sheet intermediate tables fw_&lt;key&gt; / fw2_&lt;key&gt;.
 * Two impls:
 *   - {@link PgIntermediateTableStore} — current default, byte-identical PG behaviour.
 *   - {@link JavaIntermediateTableStore} — in-memory Java structures, no PG round-trips
 *     for intermediates.
 *
 * <p>Selected at startup via fw.properties property
 * {@code core.intermediate.storage=pg|memory} (default {@code pg}).</p>
 *
 * <p>Final-stage tables (fw_final, fw_final_base, fw_opt&lt;i&gt;) are NOT covered by
 * this interface — they continue to be written through DbClient/SchemaProvisioner
 * directly regardless of mode (per user requirement: "PostgreSQL last staged DB
 * all tables gotta be filled as current codebase version does").</p>
 *
 * <p>Thread-safety: implementations must be safe for concurrent writes to
 * different keys (SheetWorker submits one virtual thread per sheet) and safe
 * for reads of one key after that key's writes complete (signalled via
 * SheetWorker.sheetDone CompletableFuture). Writes to the SAME key are
 * serialised by the SheetWorker / BraceOperationHandler call pattern.</p>
 */
public interface IntermediateTableStore {

    /** Human-readable mode label for logging, e.g. {@code "pg"} or {@code "memory"}. */
    String modeName();

    /** True if intermediate state is materialised in PostgreSQL. Callers
     *  occasionally need this to gate PG-only constructs (e.g. brace handler
     *  tmp tables, Hibernate statement-inspector retargets). */
    boolean isPgBacked();

    // ── lifecycle ────────────────────────────────────────────────────────

    /** Create fw_&lt;key&gt; intermediate table (PG: CREATE UNLOGGED TABLE …;
     *  memory: register key so subsequent appends/reads succeed). Idempotent. */
    void createFwTable(short key) throws SQLException;

    /** Create fw2_&lt;key&gt; intermediate table (PG: CREATE UNLOGGED TABLE …;
     *  memory: register key). Idempotent. */
    void createFw2Table(short key) throws SQLException;

    // ── writes ───────────────────────────────────────────────────────────

    /** Append a row to fw_&lt;key&gt;. {@code combiId} is the caller-managed id
     *  (existing semantics: {@code fwId.incrementAndGet()}). The caller MUST
     *  NOT mutate {@code combo} after this call (implementations retain the
     *  reference). */
    void appendFwRow(short key, long combiId, short[] combo);

    /** Append a row to fw2_&lt;key&gt;. {@code parentCombiId} may be null
     *  (encoded in PG as {@code \N}). */
    void appendFw2Row(short key, long combiId, Long parentCombiId, short[] combo);

    /** Flush pending writes to the underlying medium (PG: COPY-flush any
     *  buffered rows; memory: noop). Should be called at the end of each
     *  logical batch (matches existing per-counter4copyMax flush points). */
    void flushFw(short key);
    void flushFw2(short key);

    // ── reads ────────────────────────────────────────────────────────────

    /** All combos from fw_&lt;key&gt;, in combi_id (insertion) order. */
    List<short[]> readFwCombos(short key);

    /** All combos from fw2_&lt;key&gt;, in combi_id order. */
    List<short[]> readFw2Combos(short key);

    /** Combos from fw_&lt;key&gt; filtered by length == cardinality. */
    List<short[]> readFwCombosWithCardinality(short key, int cardinality);

    /** Combos from fw2_&lt;key&gt; filtered by length == cardinality. */
    List<short[]> readFw2CombosWithCardinality(short key, int cardinality);

    /** Map combi_id → combo for fw_&lt;key&gt;. Used by SheetWorker.runSubsequentPass
     *  in place of FwService.getFWfromPreloadedMap. */
    Map<Long, short[]> readFwAsMap(short key);

    // ── diagnostics ──────────────────────────────────────────────────────

    long count(short key, boolean fw2);

    long maxCombiId(short key, boolean fw2);

    /** True iff the named table has been created (PG: to_regclass non-null;
     *  memory: key registered via {@code createFw*Table} OR has rows). */
    boolean exists(short key, boolean fw2);

    /** True iff the named table has zero rows (or doesn't exist). */
    boolean isEmpty(short key, boolean fw2);

    // ── transforms ───────────────────────────────────────────────────────

    /** Dedup rows in-place; preserve first occurrence per distinct combos
     *  (matches the legacy "SELECT DISTINCT" / "MIN(combi_id) GROUP BY data_cols"
     *  semantics). */
    void distinctify(short key, boolean fw2);

    /** Empty the rows but keep the table existence (PG: DELETE FROM …;
     *  memory: clear the list). */
    void deleteRows(short key, boolean fw2);

    /** Drop the table (PG: DROP TABLE IF EXISTS …; memory: remove the key
     *  from the map). */
    void dropTable(short key, boolean fw2);

    /** Move fw2_&lt;key&gt; contents into fw_&lt;key&gt;, then recreate empty fw2_&lt;key&gt;.
     *  Used by SheetWorker between directives when {@code isCombi2} transitions
     *  back to fw_. PG equivalent:
     *  <pre>DROP fw_; CREATE fw_; INSERT INTO fw_ (combi_id, combos)
     *  SELECT combi_id, combos_1 FROM fw2_; DROP fw2_; CREATE fw2_</pre> */
    void swapFw2ToFw(short key) throws SQLException;

    /** Move fw_&lt;key&gt; contents into fw2_&lt;key&gt; (creating fw2_ if missing),
     *  then clear fw_&lt;key&gt;. Used by BraceOperationHandler after the join
     *  phase. PG equivalent:
     *  <pre>CREATE fw2_; INSERT INTO fw2_ (combi_id, combos_1)
     *  SELECT combi_id, combos FROM fw_; DELETE FROM fw_</pre> */
    void moveFwToFw2(short key) throws SQLException;
}
