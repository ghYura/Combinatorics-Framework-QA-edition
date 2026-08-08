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

package com.company;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.List;

/** STEP 23: idempotent writes into the additive {@code results_v2} table
 *  (schema: {@link ResultsV2SchemaMigrator}, STEP 22).
 *
 *  <h2>Policy (acceptance: "Count semantics документированы в schema
 *  comments/code")</h2>
 *  <ul>
 *    <li><b>Immutable samples.</b> A {@code (run_id, candidate_id, attempt,
 *        repeat_idx, env_id)} row, once durably written, is never modified. This
 *        writer issues {@code INSERT ... ON CONFLICT (run_id, candidate_id,
 *        attempt, repeat_idx, env_id) DO NOTHING} -- never {@code DO UPDATE} --
 *        so a re-run of the same batch (replay, resume, launcher retry of the
 *        whole executor stage) cannot silently overwrite or duplicate a row that
 *        already landed. This is what "Повтор того же executor batch не
 *        удваивает final results" and "no silent overwrite" require.</li>
 *    <li><b>Unique sample identity (Plan-1 Phase 3b).</b> Backed by the
 *        {@code results_v2_sample_uk} unique index
 *        ({@link ResultsV2SchemaMigrator#CREATE_SAMPLE_INDEX_SQL}): identity is
 *        the 5-column sample key (run, candidate, attempt, repeat_idx, env_id)
 *        -- {@code attempt} (retry) nested inside the (candidate, repeat_idx,
 *        env_id) sample -- because the same candidate legitimately produces one
 *        row per attempt AND one sample per repeat/env. At K=1 every row carries
 *        repeat_idx=0/env_id='', so it dedupes exactly as the retired 3-column
 *        key (see "Attempts traceable" below).</li>
 *    <li><b>One selected/final result -- latest attempt wins.</b> Selection is
 *        deterministic at read time: order a run/candidate's immutable rows by
 *        {@code attempt DESC} and take one. This writer never {@code UPDATE}s
 *        or deletes a row to "select" it as final; doing so would violate
 *        immutability and could race with a concurrent insert of a later
 *        attempt. {@code updatedSelected} in {@link WriteCounts}
 *        stays {@code 0} by design: nothing this writer does ever updates a
 *        row. The field exists so the policy is explicit in the count tuple
 *        the executor summary reports, not silently absent.</li>
 *    <li><b>Attempts traceable.</b> Every attempt -- including ones later
 *        superseded by a retry -- keeps its own immutable row; nothing is ever
 *        merged or replaced, so the full attempt history for a candidate is
 *        always reconstructable from {@code results_v2} alone.</li>
 *    <li><b>Retry creates a new attempt, not a new candidate</b> (contract for
 *        callers, not enforced by this writer: retry mechanics -- detecting an
 *        infrastructure failure and re-running -- live in the launcher/resume
 *        machinery, not here). When a candidate is retried after BROKEN/
 *        TIMEOUT/INFRA_FAIL, the caller MUST keep {@code candidate_id} stable
 *        and pass {@code attempt + 1}; minting a fresh {@code candidate_id}
 *        for the same underlying candidate would defeat both the unique key
 *        and "Attempts traceable".</li>
 *  </ul>
 *
 *  <h2>Transaction shape</h2>
 *  One transaction per bounded batch (mirrors the legacy
 *  {@code ThreadFileWriterDB}/{@code flushRemainingSync} batching): the whole
 *  batch commits or the whole batch rolls back -- no partially-applied batch is
 *  ever left straddling a commit boundary. Conflict handling is explicit and
 *  per-row ({@code ON CONFLICT ... DO NOTHING}, not a whole-batch catch), so one
 *  candidate's replay does not block its batch-mates from landing. */
public final class ResultsV2Writer {
    private ResultsV2Writer() {}

    /** One canonical, persistence-ready outcome row. Mirrors the fields STEP 22
     *  added to {@code results_v2} beyond the legacy positional schema:
     *  attempt/duration/exit/signal/worker/source-hash/stdout-stderr-refs.
     *  {@code outcome} is {@link MainWatch.Outcome#name()} (kept as text so the
     *  schema stays backend-neutral across the Java and Python Executors --
     *  mirrors {@code py_executor.Outcome}, a plain str enum, for the same
     *  reason). Nullable provenance fields are {@code null} when the
     *  corresponding signal was not observed (e.g. {@code signal} for a
     *  candidate that exited normally). */
    public record CanonicalResult(
            String runId,
            String candidateId,
            int attempt,
            String outcome,
            Integer verdictCode,
            String verdictMessage,
            Long durationMs,
            Integer exitCode,
            String signal,
            String worker,
            String sourceHash,
            String stdoutRef,
            String stderrRef,
            String policyId,    // STEP 27: execution policy (bundle/policy.py) id ...
            String policyHash,  // ... and full sha256 the candidate ran under (nullable)
            int repeatIdx,      // Plan-1 sample identity: repeat ordinal 0..K-1 (0 = the verdict sample)
            String envId) {     // Plan-1 sample identity: assignment-time environment ('' at K=1)
    }

    /** The four buckets the executor summary reports (action item 3):
     *  every attempted row lands in exactly one of {@code inserted} /
     *  {@code alreadyPresent} / {@code updatedSelected} -- so
     *  {@code attempted == inserted + alreadyPresent + updatedSelected} always
     *  holds (the launcher-checkable invariant action item 4 calls for).
     *  {@code updatedSelected} is always {@code 0} for this writer (see the
     *  "one selected/final result" policy note on the class) -- carried as an
     *  explicit field rather than omitted so the count tuple documents the
     *  policy by its shape, not by silence. */
    public record WriteCounts(int attempted, int inserted, int alreadyPresent, int updatedSelected) {
        public WriteCounts {
            if (attempted != inserted + alreadyPresent + updatedSelected) {
                throw new IllegalArgumentException("WriteCounts must satisfy attempted == inserted + alreadyPresent "
                        + "+ updatedSelected (got attempted=" + attempted + " inserted=" + inserted
                        + " alreadyPresent=" + alreadyPresent + " updatedSelected=" + updatedSelected + ")");
            }
        }

        static final WriteCounts EMPTY = new WriteCounts(0, 0, 0, 0);
    }

    /** {@code DO NOTHING} (never {@code DO UPDATE}) is the load-bearing choice
     *  that makes samples immutable -- see the class-level policy note.
     *
     *  <p>{@code ON CONFLICT (run_id, candidate_id, attempt, repeat_idx, env_id)}
     *  -- column-list inference, not {@code ON CONFLICT ON CONSTRAINT <name>} --
     *  on purpose: {@link ResultsV2SchemaMigrator#CREATE_SAMPLE_INDEX_SQL}
     *  provisions a plain {@code CREATE UNIQUE INDEX}, not a named {@code UNIQUE}
     *  table constraint, and Postgres only accepts {@code ON CONFLICT ON
     *  CONSTRAINT} for the latter. Column-list inference matches *any* unique
     *  index on exactly these columns, so the arity here (5 columns) is
     *  co-versioned with the live unique index -- it must match
     *  {@code results_v2_sample_uk}, never the retired 3-column key. At K=1 every
     *  row binds repeat_idx=0/env_id='', so this dedupes exactly as the old key. */
    private static final String IDEMPOTENT_INSERT_SQL =
            "INSERT INTO public.results_v2 "
            + "(run_id, candidate_id, attempt, outcome, verdict_code, verdict_message, duration_ms, "
            + "exit_code, signal, worker, source_hash, stdout_ref, stderr_ref, policy_id, policy_hash, "
            + "repeat_idx, env_id) "
            + "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            + "ON CONFLICT (run_id, candidate_id, attempt, repeat_idx, env_id) DO NOTHING";

    /** Writes one bounded batch inside a single transaction and reports exactly
     *  which of the four buckets each row fell into.
     *
     *  <p>Conflict detection relies on the PostgreSQL JDBC driver's documented
     *  per-row batch update counts: a row that the {@code ON CONFLICT ... DO
     *  NOTHING} clause skipped reports an update count of {@code 0} (it
     *  modified nothing), while a row that was actually inserted reports a
     *  positive count -- so {@code count == 0} <=> "already present", precisely
     *  the "already-present" bucket the executor summary must report.
     *
     *  @return {@link WriteCounts#EMPTY} for an empty batch (no transaction is
     *          opened -- nothing was attempted, nothing to commit or roll back).
     *  @throws SQLException on any genuine DB error; the transaction is rolled
     *          back before the exception propagates, so a failed batch leaves
     *          no partial trace (mirrors {@code flushRemainingSync}'s
     *          rollback-on-failure, just scoped to {@code results_v2} alone --
     *          it never touches the legacy table or {@code bq}). */
    public static WriteCounts writeBatch(Connection conn, List<CanonicalResult> batch) throws SQLException {
        if (batch.isEmpty()) return WriteCounts.EMPTY;

        boolean previousAutoCommit = conn.getAutoCommit();
        try {
            conn.setAutoCommit(false);
            int inserted = 0;
            try (PreparedStatement ps = conn.prepareStatement(IDEMPOTENT_INSERT_SQL)) {
                for (CanonicalResult r : batch) {
                    bind(ps, r);
                    ps.addBatch();
                }
                int[] updateCounts = ps.executeBatch();
                for (int count : updateCounts) {
                    // count == 0  -> ON CONFLICT ... DO NOTHING skipped this row: already present
                    // count != 0  -> the row was actually written (1 exact, or a driver-specific
                    //                "wrote something but can't say how many" sentinel -- either
                    //                way it is not zero, i.e. not a no-op)
                    if (count != 0) inserted++;
                }
            }
            conn.commit();
            int alreadyPresent = batch.size() - inserted;
            return new WriteCounts(batch.size(), inserted, alreadyPresent, 0);
        } catch (SQLException ex) {
            try {
                conn.rollback();
            } catch (SQLException rollbackEx) {
                ex.addSuppressed(rollbackEx);
            }
            throw ex;
        } finally {
            conn.setAutoCommit(previousAutoCommit);
        }
    }

    private static void bind(PreparedStatement ps, CanonicalResult r) throws SQLException {
        int col = 1;
        ps.setString(col++, r.runId());
        ps.setString(col++, r.candidateId());
        ps.setInt(col++, r.attempt());
        ps.setString(col++, r.outcome());
        setNullableInt(ps, col++, r.verdictCode());
        setNullableString(ps, col++, r.verdictMessage());
        setNullableLong(ps, col++, r.durationMs());
        setNullableInt(ps, col++, r.exitCode());
        setNullableString(ps, col++, r.signal());
        setNullableString(ps, col++, r.worker());
        setNullableString(ps, col++, r.sourceHash());
        setNullableString(ps, col++, r.stdoutRef());
        setNullableString(ps, col++, r.stderrRef());
        setNullableString(ps, col++, r.policyId());
        setNullableString(ps, col++, r.policyHash());
        ps.setInt(col++, r.repeatIdx());          // NOT NULL sample identity (0 at K=1)
        ps.setString(col, r.envId());             // NOT NULL sample identity ('' at K=1)
    }

    private static void setNullableInt(PreparedStatement ps, int col, Integer value) throws SQLException {
        if (value == null) ps.setNull(col, Types.INTEGER);
        else ps.setInt(col, value);
    }

    private static void setNullableLong(PreparedStatement ps, int col, Long value) throws SQLException {
        if (value == null) ps.setNull(col, Types.BIGINT);
        else ps.setLong(col, value);
    }

    private static void setNullableString(PreparedStatement ps, int col, String value) throws SQLException {
        if (value == null) ps.setNull(col, Types.VARCHAR);
        else ps.setString(col, value);
    }
}
