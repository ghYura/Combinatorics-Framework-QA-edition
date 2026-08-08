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

package com.company.sink;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Tee-style {@link OutputStream} that wraps the framework's existing file/zip
 * destination and ALSO splits the byte stream on a configurable row separator,
 * decoding each completed row into a UTF-8 string and dispatching it to a
 * {@link RowSink}.
 *
 * Designed for the STREAMING-DIRECT path in {@code Main}, where rows are
 * written through {@code StreamRowWriter.writeOneRow(...)} into a single long
 * OutputStream and separated by {@code FW_B_ARR} (or, when neither FW_B_ARR
 * nor sheet ending is configured, by a literal {@code '\n'} that {@code Main}
 * appends explicitly in {@code FILES_MODE && !ZIP_MODE}).
 *
 * Behaviour preservation:
 *   • Every byte written to this stream is forwarded verbatim to the wrapped
 *     OutputStream FIRST — file output is unchanged byte-for-byte.
 *   • The sink is fed only AFTER the wrapped write succeeds, so a sink
 *     exception cannot corrupt the file.
 *   • Each row id is derived from a strictly-monotonic counter; the sink can
 *     correlate to the framework's primary key only if the wrapped stream
 *     was emitting rows in the same order (which STREAMING-DIRECT does).
 *
 * Not safe for concurrent writers (the STREAMING-DIRECT path is single-
 * threaded by design).  The parallel path in {@code Main} calls the sink
 * directly with the row bytes already in hand, bypassing this class.
 *
 * perf 2026-07-02 rewrite (dispatched rows identical to the previous version):
 * the old implementation materialised the whole pending buffer with
 * toByteArray() on EVERY write and re-scanned it from offset 0 — O(rowLen²)
 * per row across the many per-segment writes.  This version keeps one
 * grow-only buffer and an incremental scan cursor, so each byte is examined
 * once and no per-write copies are made.
 */
public final class RowSinkOutputStream extends OutputStream {

    private final OutputStream wrapped;
    private final RowSink sink;
    private final byte[] separator;
    private final AtomicLong rowCounter;
    private boolean closed;

    /** Pending (not yet separator-terminated) bytes. */
    private byte[] rbuf = new byte[64 * 1024];
    private int rcount = 0;
    /** Positions strictly below this offset are known not to start a separator match. */
    private int scanFrom = 0;

    /**
     * @param wrapped    existing destination (file/zip/etc.) — unchanged
     * @param sink       receiver of completed row strings (UTF-8 decoded);
     *                   may be {@code null} or {@link RowSinkRegistry#NULL}
     *                   for a pure pass-through (with row-counting disabled)
     * @param separator  byte sequence that ends one row and starts the next.
     * @param firstRowId starting value for the row id passed to sink
     */
    public RowSinkOutputStream(OutputStream wrapped, RowSink sink,
                                byte[] separator, AtomicLong firstRowId) {
        if (wrapped == null) throw new IllegalArgumentException("wrapped == null");
        if (separator == null || separator.length == 0)
            throw new IllegalArgumentException("separator must be non-empty");
        this.wrapped = wrapped;
        this.sink = (sink == null) ? RowSinkRegistry.NULL : sink;
        this.separator = separator.clone();
        this.rowCounter = (firstRowId == null) ? new AtomicLong(1L) : firstRowId;
    }

    @Override public void write(int b) throws IOException {
        wrapped.write(b);
        if (sink == RowSinkRegistry.NULL) return;
        ensureCapacity(1);
        rbuf[rcount++] = (byte) b;
        scanBoundaries();
    }

    @Override public void write(byte[] b, int off, int len) throws IOException {
        wrapped.write(b, off, len);
        if (sink == RowSinkRegistry.NULL) return;
        if (len <= 0) return;
        ensureCapacity(len);
        System.arraycopy(b, off, rbuf, rcount, len);
        rcount += len;
        scanBoundaries();
    }

    @Override public void flush() throws IOException { wrapped.flush(); }

    @Override public void close() throws IOException {
        if (closed) return;
        closed = true;
        // Anything left in the buffer is the last row that wasn't terminated
        // by a separator — emit it as a final row so the sink doesn't lose data.
        flushPending();
        try { wrapped.close(); } catch (IOException _) {}
    }

    /** Force-emit whatever's buffered as one row (without a terminator).
     *  Useful to flush at end-of-stage when the framework may have written
     *  the last row without a trailing separator. */
    public void flushPending() {
        if (rcount == 0 || sink == RowSinkRegistry.NULL) {
            rcount = 0;
            scanFrom = 0;
            return;
        }
        String row = new String(rbuf, 0, rcount, StandardCharsets.UTF_8);
        rcount = 0;
        scanFrom = 0;
        try { sink.accept(rowCounter.getAndIncrement(), row); }
        catch (RuntimeException _) { /* sink errors must not break the file write */ }
    }

    private void ensureCapacity(int add) {
        int need = rcount + add;
        if (need <= rbuf.length) return;
        int n = rbuf.length;
        while (n < need) n = Math.min(n * 2, n + 8 * 1024 * 1024);
        byte[] nb = new byte[n];
        System.arraycopy(rbuf, 0, nb, 0, rcount);
        rbuf = nb;
    }

    /** Emit every complete row now visible; keep only the unconsumed tail.
     *  Left-to-right, non-overlapping — same row boundaries as the legacy scan. */
    private void scanBoundaries() {
        final int sepLen = separator.length;
        int start = 0;
        int i = Math.max(scanFrom, 0);
        while (i <= rcount - sepLen) {
            if (matchesAt(i)) {
                String row = new String(rbuf, start, i - start, StandardCharsets.UTF_8);
                try { sink.accept(rowCounter.getAndIncrement(), row); }
                catch (RuntimeException _) {}
                start = i + sepLen;
                i = start;
            } else {
                i++;
            }
        }
        // next append may complete a match starting in the last (sepLen-1) bytes
        scanFrom = Math.max(start, rcount - sepLen + 1);
        if (start > 0) {
            int live = rcount - start;
            if (live > 0) System.arraycopy(rbuf, start, rbuf, 0, live);
            rcount = live;
            scanFrom -= start;
            if (scanFrom < 0) scanFrom = 0;
        }
    }

    private boolean matchesAt(int i) {
        for (int j = 0; j < separator.length; j++) {
            if (rbuf[i + j] != separator[j]) return false;
        }
        return true;
    }
}
