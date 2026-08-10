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
import java.util.List;
import java.util.Map;

/**
 * Iter4.5 — wrapper that delegates to a CURRENT underlying store and supports
 * hot-swapping the delegate at runtime (e.g. when the heap watchdog fires a
 * drain event and the pipeline migrates from {@link JavaIntermediateTableStore}
 * to {@link PgIntermediateTableStore}).
 *
 * <p><strong>Concurrency contract</strong>: the {@link #swap(IntermediateTableStore)}
 * method MUST be invoked while no other thread has an in-flight call to any
 * delegate method.  The caller (typically a coordinator on the orchestrator
 * side) is responsible for quiescing concurrent users via a barrier/latch BEFORE
 * invoking {@code swap}.  This wrapper does NOT internally synchronize — adding
 * a read-write lock per method call would impose too much per-op overhead on
 * the hot per-sheet append path.</p>
 *
 * <p>After {@code swap}, subsequent calls go to the new delegate.  Any rows
 * already written to the OLD delegate are caller's responsibility to migrate
 * (typically via {@link JavaIntermediateTableStore#drainAllTo} BEFORE
 * swapping).</p>
 */
public final class SwitchableIntermediateTableStore implements IntermediateTableStore {

    private volatile IntermediateTableStore delegate;

    public SwitchableIntermediateTableStore(IntermediateTableStore initial) {
        if (initial == null) throw new IllegalArgumentException("initial delegate must be non-null");
        this.delegate = initial;
    }

    /** Currently-active delegate.  Useful for the drain coordinator that needs
     *  to call type-specific methods on the old delegate (e.g.
     *  {@code ((JavaIntermediateTableStore) sw.current()).drainAllTo(...)}). */
    public IntermediateTableStore current() {
        return delegate;
    }

    /** Atomic delegate replacement.  CALLER MUST quiesce concurrent users
     *  before invoking — this method does not block on in-flight calls. */
    public void swap(IntermediateTableStore newDelegate) {
        if (newDelegate == null) throw new IllegalArgumentException("new delegate must be non-null");
        this.delegate = newDelegate;
    }

    // ── pass-through (no extra synchronization; delegate field is volatile) ──

    @Override public String  modeName()    { return "switchable[" + delegate.modeName() + "]"; }
    @Override public boolean isPgBacked()  { return delegate.isPgBacked(); }

    @Override public void createFwTable(short k)  throws SQLException { delegate.createFwTable(k); }
    @Override public void createFw2Table(short k) throws SQLException { delegate.createFw2Table(k); }

    @Override public void appendFwRow(short k, long combiId, short[] combo) {
        delegate.appendFwRow(k, combiId, combo);
    }
    @Override public void appendFw2Row(short k, long combiId, Long parentCombiId, short[] combo) {
        delegate.appendFw2Row(k, combiId, parentCombiId, combo);
    }
    @Override public void flushFw(short k)  { delegate.flushFw(k); }
    @Override public void flushFw2(short k) { delegate.flushFw2(k); }

    @Override public List<short[]> readFwCombos(short k)  { return delegate.readFwCombos(k); }
    @Override public List<short[]> readFw2Combos(short k) { return delegate.readFw2Combos(k); }
    @Override public List<short[]> readFwCombosWithCardinality(short k, int c) {
        return delegate.readFwCombosWithCardinality(k, c);
    }
    @Override public List<short[]> readFw2CombosWithCardinality(short k, int c) {
        return delegate.readFw2CombosWithCardinality(k, c);
    }
    @Override public Map<Long, short[]> readFwAsMap(short k) { return delegate.readFwAsMap(k); }

    @Override public long    count(short k, boolean fw2)       { return delegate.count(k, fw2); }
    @Override public long    maxCombiId(short k, boolean fw2)  { return delegate.maxCombiId(k, fw2); }
    @Override public boolean exists(short k, boolean fw2)      { return delegate.exists(k, fw2); }
    @Override public boolean isEmpty(short k, boolean fw2)     { return delegate.isEmpty(k, fw2); }

    @Override public void distinctify(short k, boolean fw2) { delegate.distinctify(k, fw2); }
    @Override public void deleteRows(short k, boolean fw2)  { delegate.deleteRows(k, fw2); }
    @Override public void dropTable(short k, boolean fw2)   { delegate.dropTable(k, fw2); }

    @Override public void swapFw2ToFw(short k) throws SQLException { delegate.swapFw2ToFw(k); }
    @Override public void moveFwToFw2(short k) throws SQLException { delegate.moveFwToFw2(k); }
}
