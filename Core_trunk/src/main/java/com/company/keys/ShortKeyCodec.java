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

import com.company.excel.DataTypeDispatcher;

import java.util.Arrays;
import java.util.List;

/** {@code short[]} rows: the legacy representation, byte-for-byte the behaviour the pipeline always had. */
public final class ShortKeyCodec implements KeyCodec<short[]> {

    public static final ShortKeyCodec INSTANCE = new ShortKeyCodec();

    private static final short[] EMPTY = new short[0];

    private ShortKeyCodec() { }

    @Override public DataTypeDispatcher.Tier tier()  { return DataTypeDispatcher.Tier.SHORT; }
    @Override public Class<short[]> arrayClass()     { return short[].class; }
    @Override public short[] newArray(int length)    { return new short[length]; }
    @Override public short[] empty()                 { return EMPTY; }
    @Override public int length(short[] a)           { return a.length; }
    @Override public short get(short[] a, int i)     { return a[i]; }
    @Override public void set(short[] a, int i, short v) { a[i] = v; }

    @Override public short[] fromInts(int[] values) {
        short[] out = new short[values.length];
        for (int i = 0; i < values.length; i++) out[i] = (short) values[i];      // legacy IntStreamEx.toShortArray()
        return out;
    }

    @Override public int[] toInts(short[] a) {
        int[] out = new int[a.length];
        for (int i = 0; i < a.length; i++) out[i] = a[i];
        return out;
    }

    @Override public Short[] box(short[] a) {
        Short[] o = new Short[a.length];
        for (int i = 0; i < a.length; i++) o[i] = a[i];
        return o;
    }

    @Override public short[] concat(List<short[]> parts) {
        int total = 0;
        for (short[] r : parts) total += r.length;
        short[] mega = new short[total];
        int idx = 0;
        for (short[] r : parts) {
            System.arraycopy(r, 0, mega, idx, r.length);
            idx += r.length;
        }
        return mega;
    }

    @Override public short[] parseCsv(String csv)          { return KeyArrays.parseCsvToShorts(csv); }
    @Override public short[] fromJdbc(Object jdbcArray)    { return KeyArrays.jdbcToShorts(jdbcArray); }
    @Override public boolean arrayEquals(short[] x, short[] y) { return Arrays.equals(x, y); }
    @Override public int arrayHash(short[] a)              { return Arrays.hashCode(a); }

    @Override public int compare(short[] x, short[] y) {
        int min = Math.min(x.length, y.length);
        for (int i = 0; i < min; i++) {
            int c = Integer.compare(x[i], y[i]);
            if (c != 0) return c;
        }
        return Integer.compare(x.length, y.length);
    }

    @Override public void encode(PgCopyBuffer out, short[] a) { out.appendArray(a); }
    @Override public String describe(short[] a)                { return Arrays.toString(a); }
}
