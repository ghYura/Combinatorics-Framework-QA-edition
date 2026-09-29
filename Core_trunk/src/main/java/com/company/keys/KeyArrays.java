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

package com.company.keys;

/** Conversions shared by the codecs; package-private on purpose. */
final class KeyArrays {
    private KeyArrays() { }

    /**
     * Normalise whatever the JDBC driver returns for an {@code int2[]} (or wider) column into a
     * {@code short[]}.  A NULL element becomes 0 (the engine never emits one), a NULL array becomes empty.
     */
    static short[] jdbcToShorts(Object javaArr) {
        if (javaArr == null) return new short[0];
        if (javaArr instanceof short[] s) return s.clone();
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
        if (javaArr instanceof int[] ip) {
            short[] out = new short[ip.length];
            for (int i = 0; i < ip.length; i++) out[i] = (short) ip[i];
            return out;
        }
        if (javaArr instanceof byte[] bp) {
            short[] out = new short[bp.length];
            for (int i = 0; i < bp.length; i++) out[i] = bp[i];
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

    /** The joiner's list: tokens that are blank or not a short are dropped (legacy behaviour). */
    static short[] parseCsvToShorts(String csv) {
        if (csv == null || csv.isEmpty()) return new short[0];
        String[] toks = csv.split(",");
        short[] out = new short[toks.length];
        int j = 0;
        for (String t : toks) {
            String s = t.trim();
            if (s.isEmpty()) continue;
            try {
                // Parse BEFORE the slot is claimed: the legacy `out[j++] = Short.parseShort(s)` bumped j first, so a
                // token that failed to parse left a stray 0 behind instead of being skipped — harmless while 0 was
                // never a key, a wrong element now that the anchor strategy can give a real cell the key 0.
                short v = Short.parseShort(s);
                out[j++] = v;
            } catch (NumberFormatException e) {
                // Skip non-numeric tokens (shouldn't occur in normal brace output).
            }
        }
        if (j == out.length) return out;
        short[] trimmed = new short[j];
        System.arraycopy(out, 0, trimmed, 0, j);
        return trimmed;
    }
}
