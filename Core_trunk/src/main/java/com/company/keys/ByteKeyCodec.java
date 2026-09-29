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

/**
 * {@code byte[]} rows for runs whose keys all fit a byte ({@link DataTypeDispatcher.Tier#BYTE}, labels
 * {@code -127..127}).  Every narrowing is range-checked: a label that does not fit fails loudly here rather
 * than wrapping to a different key downstream.
 */
public final class ByteKeyCodec implements KeyCodec<byte[]> {

    public static final ByteKeyCodec INSTANCE = new ByteKeyCodec();

    private static final byte[] EMPTY = new byte[0];

    private ByteKeyCodec() { }

    private static byte narrow(int v) {
        if (v < Byte.MIN_VALUE || v > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("key " + v + " does not fit the BYTE tier (" + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE + ")");
        }
        return (byte) v;
    }

    @Override public DataTypeDispatcher.Tier tier()  { return DataTypeDispatcher.Tier.BYTE; }
    @Override public Class<byte[]> arrayClass()      { return byte[].class; }
    @Override public byte[] newArray(int length)     { return new byte[length]; }
    @Override public byte[] empty()                  { return EMPTY; }
    @Override public int length(byte[] a)            { return a.length; }
    @Override public short get(byte[] a, int i)      { return a[i]; }
    @Override public void set(byte[] a, int i, short v) { a[i] = narrow(v); }

    @Override public byte[] fromInts(int[] values) {
        byte[] out = new byte[values.length];
        for (int i = 0; i < values.length; i++) {
            int v = values[i];
            if (v < Byte.MIN_VALUE || v > Byte.MAX_VALUE) {
                throw new NumberFormatException("code " + v + " does not fit the BYTE key tier (" + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE + ")");
            }
            out[i] = (byte) v;
        }
        return out;
    }

    @Override public int[] toInts(byte[] a) {
        int[] out = new int[a.length];
        for (int i = 0; i < a.length; i++) out[i] = a[i];
        return out;
    }

    @Override public Short[] box(byte[] a) {
        Short[] o = new Short[a.length];
        for (int i = 0; i < a.length; i++) o[i] = (short) a[i];
        return o;
    }

    @Override public byte[] concat(List<byte[]> parts) {
        int total = 0;
        for (byte[] r : parts) total += r.length;
        byte[] mega = new byte[total];
        int idx = 0;
        for (byte[] r : parts) {
            System.arraycopy(r, 0, mega, idx, r.length);
            idx += r.length;
        }
        return mega;
    }

    @Override public byte[] parseCsv(String csv) {
        short[] s = KeyArrays.parseCsvToShorts(csv);
        byte[] out = new byte[s.length];
        for (int i = 0; i < s.length; i++) out[i] = narrow(s[i]);
        return out;
    }

    @Override public byte[] fromJdbc(Object jdbcArray) {
        if (jdbcArray instanceof byte[] b) return b.clone();
        short[] s = KeyArrays.jdbcToShorts(jdbcArray);
        byte[] out = new byte[s.length];
        for (int i = 0; i < s.length; i++) out[i] = narrow(s[i]);
        return out;
    }

    @Override public boolean arrayEquals(byte[] x, byte[] y) { return Arrays.equals(x, y); }
    @Override public int arrayHash(byte[] a)                 { return Arrays.hashCode(a); }

    @Override public int compare(byte[] x, byte[] y) {
        int min = Math.min(x.length, y.length);
        for (int i = 0; i < min; i++) {
            int c = Integer.compare(x[i], y[i]);
            if (c != 0) return c;
        }
        return Integer.compare(x.length, y.length);
    }

    @Override public void encode(PgCopyBuffer out, byte[] a) { out.appendArray(a); }
    @Override public String describe(byte[] a)               { return Arrays.toString(a); }
}
