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

package com.company.db.sql;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;


public final class RelationLockRegistry {

    private final ConcurrentMap<String, ReadWriteLock> locks = new ConcurrentHashMap<>();


    public ReadWriteLock get(String relation) {
        if (relation == null) throw new IllegalArgumentException("relation must not be null");
        String key = normalizeKey(relation);
        return locks.computeIfAbsent(key, k -> new ReentrantReadWriteLock(true));
    }


    public static String normalizeKey(String relation) {
        if (relation == null) return null;
        String r = relation.replace("\"", "").trim();
        int dot = r.indexOf('.');
        if (dot >= 0) r = r.substring(dot + 1);
        return r;
    }
}
