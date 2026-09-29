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

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/**
 * A growable ASCII byte buffer holding PostgreSQL {@code COPY ... FROM STDIN} text.
 *
 * <p>Replaces the {@code StringBuilder -> toString() -> getBytes(UTF_8) -> ByteArrayInputStream}
 * chain: the payload is built as bytes, and {@link #asInputStream()} hands the very same array to
 * the JDBC driver, so nothing is copied between formatting and the socket.  Key arrays are written
 * as {@code {1,-2,3}} by a branch-free writer: a lookup table holds every label's ASCII bytes packed
 * in one {@code long}, so one 8-byte store plus a length add emits a label whatever its digit count
 * (measured 4-7 ns/element against 10-25 ns for {@code StringBuilder.append(int)}).</p>
 *
 * <p>Not thread-safe; callers synchronise exactly as they did for the {@code StringBuilder}.</p>
 */
public final class PgCopyBuffer {

    private static final VarHandle LONG_LE =
            MethodHandles.byteArrayViewVarHandle(long[].class, ByteOrder.LITTLE_ENDIAN);

    /** A packed writer stores 8 bytes even for a 1-byte label, so the buffer keeps this much spare. */
    private static final int SLACK = 8;

    /** Label -> ASCII, byte width: indices {@code v + 128}. */
    private static final class ByteLut {
        static final long[] PACK = new long[256];
        static final byte[] LEN = new byte[256];
        static {
            for (int v = Byte.MIN_VALUE; v <= Byte.MAX_VALUE; v++) fill(PACK, LEN, v + 128, v);
        }
    }

    /** Label -> ASCII, short width: indices {@code v + 32768}; built lazily, only when a short[] is written. */
    private static final class ShortLut {
        static final long[] PACK = new long[65536];
        static final byte[] LEN = new byte[65536];
        static {
            for (int v = Short.MIN_VALUE; v <= Short.MAX_VALUE; v++) fill(PACK, LEN, v + 32768, v);
        }
    }

    private static void fill(long[] pack, byte[] len, int idx, int v) {
        byte[] t = Integer.toString(v).getBytes(StandardCharsets.US_ASCII);
        long p = 0L;
        for (int k = 0; k < t.length; k++) p |= ((long) (t[k] & 0xFF)) << (8 * k);
        pack[idx] = p;
        len[idx] = (byte) t.length;
    }

    private byte[] buf;
    private int len;
    private int rows;

    public PgCopyBuffer(int initialCapacity) {
        this.buf = new byte[Math.max(64, initialCapacity) + SLACK];
    }

    // ── state ────────────────────────────────────────────────────────────

    public int length()        { return len; }
    public boolean isEmpty()   { return len == 0; }
    /** The backing array; valid up to {@link #length()}. Do not retain across {@link #clear()}. */
    public byte[] array()      { return buf; }
    /** Free-form row counter for the producer/consumer accounting; never touched by the writers. */
    public int rows()          { return rows; }
    public void rows(int n)    { this.rows = n; }
    public void addRow()       { this.rows++; }

    public void clear() { len = 0; rows = 0; }

    /** The payload as a stream over the SAME array (no copy). */
    public InputStream asInputStream() { return new ByteArrayInputStream(buf, 0, len); }

    public byte[] toByteArray() { return Arrays.copyOf(buf, len); }

    @Override public String toString() { return new String(buf, 0, len, StandardCharsets.ISO_8859_1); }

    private void ensure(int add) {
        long need = (long) len + add;
        if (need > buf.length) {
            long n = Math.max(need, (long) buf.length * 2);
            if (n > Integer.MAX_VALUE - 16) {
                if (need > Integer.MAX_VALUE - 16) throw new OutOfMemoryError("COPY buffer exceeds 2 GB");
                n = Integer.MAX_VALUE - 16;
            }
            buf = Arrays.copyOf(buf, (int) n);
        }
    }

    // ── primitives ───────────────────────────────────────────────────────

    public PgCopyBuffer tab()     { ensure(1 + SLACK); buf[len++] = '\t'; return this; }
    public PgCopyBuffer newline() { ensure(1 + SLACK); buf[len++] = '\n'; return this; }

    public PgCopyBuffer append(byte b) { ensure(1 + SLACK); buf[len++] = b; return this; }

    public PgCopyBuffer appendBytes(byte[] src) { return appendBytes(src, 0, src.length); }

    public PgCopyBuffer appendBytes(byte[] src, int off, int n) {
        ensure(n + SLACK);
        System.arraycopy(src, off, buf, len, n);
        len += n;
        return this;
    }

    /** ASCII text such as {@code \N}; characters above 127 are a programming error. */
    public PgCopyBuffer appendAscii(String s) {
        int n = s.length();
        ensure(n + SLACK);
        for (int i = 0; i < n; i++) {
            char c = s.charAt(i);
            if (c > 127) throw new IllegalArgumentException("non-ASCII character in COPY text: U+" + Integer.toHexString(c));
            buf[len++] = (byte) c;
        }
        return this;
    }

    /** A decimal {@code long} (combi_id and friends). */
    public PgCopyBuffer appendLong(long v) {
        ensure(20 + SLACK);
        if (v < 0) {
            if (v == Long.MIN_VALUE) return appendAscii("-9223372036854775808");
            buf[len++] = '-';
            v = -v;
        }
        int digits = 1;
        for (long t = v; t >= 10; t /= 10) digits++;
        int end = len + digits;
        int p = end;
        do { buf[--p] = (byte) ('0' + (int) (v % 10)); v /= 10; } while (v != 0);
        len = end;
        return this;
    }

    // ── key arrays ───────────────────────────────────────────────────────

    /** {@code {a,b,c}} for a byte-width key array. */
    public PgCopyBuffer appendArray(byte[] a) {
        final int n = a.length;
        ensure(2 + n * 5 + SLACK);                       // widest byte label "-128" + comma
        final byte[] b = buf;
        int p = len;
        b[p++] = '{';
        if (n > 0) {
            final long[] pack = ByteLut.PACK;
            final byte[] lens = ByteLut.LEN;
            for (int i = 0; i < n; i++) {
                int idx = a[i] + 128;
                LONG_LE.set(b, p, pack[idx]);
                p += lens[idx];
                b[p++] = ',';
            }
            p--;                                          // the last comma becomes '}'
        }
        b[p++] = '}';
        len = p;
        return this;
    }

    /** {@code {a,b,c}} for a short-width key array. */
    public PgCopyBuffer appendArray(short[] a) {
        final int n = a.length;
        ensure(2 + n * 7 + SLACK);                       // widest short label "-32768" + comma
        final byte[] b = buf;
        int p = len;
        b[p++] = '{';
        if (n > 0) {
            final long[] pack = ShortLut.PACK;
            final byte[] lens = ShortLut.LEN;
            for (int i = 0; i < n; i++) {
                int idx = a[i] + 32768;
                LONG_LE.set(b, p, pack[idx]);
                p += lens[idx];
                b[p++] = ',';
            }
            p--;
        }
        b[p++] = '}';
        len = p;
        return this;
    }

    /** {@code {a,b,c}} for an int array (FW_Group interop). */
    public PgCopyBuffer appendArray(int[] a) {
        appendAscii("{");
        for (int i = 0; i < a.length; i++) {
            if (i > 0) append((byte) ',');
            appendLong(a[i]);
        }
        return appendAscii("}");
    }
}
