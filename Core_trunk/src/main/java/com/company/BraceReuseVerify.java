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

package com.company;

import com.company.store.JavaIntermediateTableStore;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/**
 * Verifier for the post-join cleanup of a brace operand (author's semantics, 2026-09-26) —
 * deterministic, no DB, no threads:
 *
 *   A. FW_Reuse            → the operand keeps its table AND its generated rows
 *                            (a later FW_Seq row calling this sheet reuses the data);
 *   B. FW_ReuseTableOnly   → the table stays, emptied of rows;
 *   C. neither flag        → rows deleted, table dropped;
 *   D. both flags          → FW_Reuse wins (nested FW_() operands carry both);
 *   E. every operand leaves mapTable2combs.
 *
 * Run via:
 * {@code java -cp target/classes:$(cat /tmp/cp.txt) com.company.BraceReuseVerify}
 */
public final class BraceReuseVerify {
    private BraceReuseVerify() {}

    public static void main(String[] args) throws Exception {
        JavaIntermediateTableStore store = new JavaIntermediateTableStore();
        Map<String, ArrayList<short[]>> mapTable2combs = new HashMap<>();
        for (short key = 1; key <= 4; key++) {
            store.createFwTable(key);
            store.createFw2Table(key);
            for (long id = 1; id <= 3; id++) {
                store.appendFwRow(key, id, new short[]{ (short) (key * 10 + id) });
                store.appendFw2Row(key, id + 10, id, new short[]{ (short) (key * 10 + id), (short) id });
            }
            mapTable2combs.put("fw_" + key, new ArrayList<>());
            mapTable2combs.put("fw2_" + key, new ArrayList<>());
        }
        final short reuse = 1, tableOnly = 2, neither = 3, both = 4;
        Set<Short> reuseSet = Set.of(reuse, both);
        Set<Short> reuseTableOnlySet = Set.of(tableOnly, both);

        BraceOperationHandler handler = new BraceOperationHandler(null, null, null, null, store, null);
        for (short key = 1; key <= 4; key++) {
            handler.cleanupOperand(key, reuseSet, reuseTableOnlySet, mapTable2combs);
        }

        int failed = 0;
        System.out.println("A. FW_Reuse keeps table + rows");
        failed += assertCond("fw_1 / fw2_1 keep 3 rows each", store.count(reuse, false) == 3 && store.count(reuse, true) == 3);
        failed += assertCond("fw_1 / fw2_1 still exist", store.exists(reuse, false) && store.exists(reuse, true));
        System.out.println("B. FW_ReuseTableOnly keeps an empty table");
        failed += assertCond("fw_2 / fw2_2 have 0 rows", store.count(tableOnly, false) == 0 && store.count(tableOnly, true) == 0);
        failed += assertCond("fw_2 / fw2_2 still exist", store.exists(tableOnly, false) && store.exists(tableOnly, true));
        System.out.println("C. no flag: rows deleted, table dropped");
        failed += assertCond("fw_3 / fw2_3 have 0 rows", store.count(neither, false) == 0 && store.count(neither, true) == 0);
        failed += assertCond("fw_3 / fw2_3 dropped", !store.exists(neither, false) && !store.exists(neither, true));
        System.out.println("D. both flags: FW_Reuse wins");
        failed += assertCond("fw_4 / fw2_4 keep 3 rows each", store.count(both, false) == 3 && store.count(both, true) == 3);
        System.out.println("E. operands leave mapTable2combs");
        failed += assertCond("mapTable2combs is empty", mapTable2combs.isEmpty());

        if (failed == 0) System.out.println("✅ ALL BRACE-REUSE CHECKS PASSED");
        else { System.out.println("❌ " + failed + " BRACE-REUSE CHECK(S) FAILED"); System.exit(1); }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        return cond ? 0 : 1;
    }
}
