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

import com.company.keys.KeyCodec;
import com.company.keys.KeyCodecs;

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Iter4.5 verification — exercises the drain mechanism end-to-end with no DB:
 *
 * <ol>
 *   <li>Populate a {@link JavaIntermediateTableStore} with several sheets' worth
 *       of fw and fw2 rows.</li>
 *   <li>Wrap it in a {@link SwitchableIntermediateTableStore}.</li>
 *   <li>Use a mock {@link IntermediateTableStore} as the drain target that
 *       just records every append.</li>
 *   <li>Call {@code drainAllTo(mock)} and {@code sw.swap(mock)}.</li>
 *   <li>Assert: every original row appears in the mock; counts agree;
 *       swap() takes effect (subsequent writes go to mock, not the old Java
 *       store).</li>
 * </ol>
 *
 * <p>Run via:
 * {@code java -cp target/classes:$(cat /tmp/cp.txt) com.company.store.DrainMechanismVerify}</p>
 */
public final class DrainMechanismVerify {

    public static void main(String[] args) throws Exception {
        // The drain mechanism is generic in the row type; prove it for BOTH key widths.  The byte run
        // uses small labels (a byte[] cannot hold the short run's 1000+ values).
        int[] sh = run("short[]", KeyCodecs.SHORT, 10, 100);
        int[] by = run("byte[] ", KeyCodecs.BYTE, 5, 1);
        int passed = sh[0] + by[0], failed = sh[1] + by[1];
        System.out.println();
        System.out.printf("Summary: PASS=%d  FAIL=%d%n", passed, failed);
        if (failed > 0) System.exit(1);
    }

    private static <A> int[] run(String label, KeyCodec<A> codec, int mulA, int mulB) throws Exception {
        int passed = 0, failed = 0;
        System.out.println("── " + label + " store ──");

        // ── Step 1: populate Java store ───────────────────────────────────
        JavaIntermediateTableStore<A> java = new JavaIntermediateTableStore<>(codec);
        Map<Short, List<A>> expectedFw = new HashMap<>();
        Map<Short, List<A>> expectedFw2 = new HashMap<>();
        for (short key = 10; key <= 13; key++) {
            java.createFwTable(key);
            java.createFw2Table(key);
            List<A> fwRows = new ArrayList<>();
            List<A> fw2Rows = new ArrayList<>();
            for (long i = 1; i <= 5; i++) {
                A fwCombo  = codec.fromInts(new int[]{ (int) (key * mulA + i),      (int) (key * mulB + i) });
                A fw2Combo = codec.fromInts(new int[]{ (int) (key * mulA + i + 50), (int) (key * mulB + i + 50) });
                java.appendFwRow(key, i, fwCombo);
                java.appendFw2Row(key, i + 100, (long) i, fw2Combo);
                fwRows.add(fwCombo);
                fw2Rows.add(fw2Combo);
            }
            expectedFw.put(key, fwRows);
            expectedFw2.put(key, fw2Rows);
        }
        System.out.printf("populated Java store: %d keys, %d fw rows, %d fw2 rows%n",
                expectedFw.size(),
                expectedFw.values().stream().mapToInt(List::size).sum(),
                expectedFw2.values().stream().mapToInt(List::size).sum());

        // ── Step 2: wrap in switchable ────────────────────────────────────
        SwitchableIntermediateTableStore<A> sw = new SwitchableIntermediateTableStore<>(java);
        if (sw.current() == java) { passed++; System.out.println("PASS  sw.current() returns the Java delegate"); }
        else                       { failed++; System.out.println("FAIL  sw.current() did NOT return the Java delegate"); }
        if (sw.codec() == codec)   { passed++; System.out.println("PASS  sw.codec() is the run's codec"); }
        else                       { failed++; System.out.println("FAIL  sw.codec() is not the run's codec"); }

        // ── Step 3: drain into a recording mock ──────────────────────────
        RecordingStore<A> mock = new RecordingStore<>(codec);
        java.drainAllTo(mock);

        // ── Step 4: verify mock contents ─────────────────────────────────
        for (Short key : expectedFw.keySet()) {
            List<A> exp = expectedFw.get(key);
            List<A> got = mock.fwRowsByKey.getOrDefault(key, List.of());
            if (rowsEqual(codec, exp, got)) { passed++; System.out.printf("PASS  fw_%d  rows migrated (%d)%n", key, got.size()); }
            else                             { failed++; System.out.printf("FAIL  fw_%d  expected %d rows, got %d%n", key, exp.size(), got.size()); }
        }
        for (Short key : expectedFw2.keySet()) {
            List<A> exp = expectedFw2.get(key);
            List<A> got = mock.fw2RowsByKey.getOrDefault(key, List.of());
            if (rowsEqual(codec, exp, got)) { passed++; System.out.printf("PASS  fw2_%d rows migrated (%d)%n", key, got.size()); }
            else                             { failed++; System.out.printf("FAIL  fw2_%d expected %d rows, got %d%n", key, exp.size(), got.size()); }
        }

        // ── Step 5: swap and verify subsequent writes hit the new delegate ─
        sw.swap(mock);
        sw.appendFwRow((short) 99, 9999L, codec.fromInts(new int[]{ 1, 2 }));
        if (mock.fwRowsByKey.containsKey((short) 99)) {
            passed++; System.out.println("PASS  post-swap append landed in mock (not in original Java store)");
        } else {
            failed++; System.out.println("FAIL  post-swap append did NOT land in mock");
        }
        return new int[]{ passed, failed };
    }

    /** Compares two row lists element-wise. */
    private static <A> boolean rowsEqual(KeyCodec<A> codec, List<A> a, List<A> b) {
        if (a.size() != b.size()) return false;
        for (int i = 0; i < a.size(); i++) {
            if (!codec.arrayEquals(a.get(i), b.get(i))) return false;
        }
        return true;
    }

    /** Minimal IntermediateTableStore that records every append into in-memory
     *  lists.  Used solely by this verifier to inspect drain output without a DB. */
    static final class RecordingStore<A> implements IntermediateTableStore<A> {
        final Map<Short, List<A>> fwRowsByKey  = new ConcurrentHashMap<>();
        final Map<Short, List<A>> fw2RowsByKey = new ConcurrentHashMap<>();
        private final KeyCodec<A> codec;
        RecordingStore(KeyCodec<A> codec) { this.codec = codec; }
        @Override public KeyCodec<A> codec() { return codec; }
        @Override public String modeName()   { return "mock-recording"; }
        @Override public boolean isPgBacked(){ return false; }
        @Override public void createFwTable(short k)  { fwRowsByKey.computeIfAbsent(k, kk -> new ArrayList<>()); }
        @Override public void createFw2Table(short k) { fw2RowsByKey.computeIfAbsent(k, kk -> new ArrayList<>()); }
        @Override public void appendFwRow(short k, long c, A combo) {
            fwRowsByKey.computeIfAbsent(k, kk -> new ArrayList<>()).add(combo);
        }
        @Override public void appendFw2Row(short k, long c, Long p, A combo) {
            fw2RowsByKey.computeIfAbsent(k, kk -> new ArrayList<>()).add(combo);
        }
        @Override public void flushFw(short k)  {}
        @Override public void flushFw2(short k) {}
        @Override public List<A> readFwCombos(short k)  { return fwRowsByKey.getOrDefault(k, List.of()); }
        @Override public List<A> readFw2Combos(short k) { return fw2RowsByKey.getOrDefault(k, List.of()); }
        @Override public List<A> readFwCombosWithCardinality(short k, int c)  { return List.of(); }
        @Override public List<A> readFw2CombosWithCardinality(short k, int c) { return List.of(); }
        @Override public Map<Long, A> readFwAsMap(short k) { return Map.of(); }
        @Override public long count(short k, boolean fw2) {
            return (fw2 ? fw2RowsByKey : fwRowsByKey).getOrDefault(k, List.of()).size();
        }
        @Override public long maxCombiId(short k, boolean fw2)  { return 0; }
        @Override public boolean exists(short k, boolean fw2)   { return true; }
        @Override public boolean isEmpty(short k, boolean fw2)  { return false; }
        @Override public void distinctify(short k, boolean fw2) {}
        @Override public void deleteRows(short k, boolean fw2)  {}
        @Override public void dropTable(short k, boolean fw2)   {}
        @Override public void swapFw2ToFw(short k) {}
        @Override public void moveFwToFw2(short k) {}
    }
}
