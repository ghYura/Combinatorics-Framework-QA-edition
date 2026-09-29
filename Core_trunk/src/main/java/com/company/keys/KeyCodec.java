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

import java.util.List;

/**
 * Everything the pipeline needs to do with a row of cell keys, independent of the primitive array it
 * is stored in: {@code byte[]} for {@link DataTypeDispatcher.Tier#BYTE} runs, {@code short[]} for
 * {@link DataTypeDispatcher.Tier#SHORT}.  The store, the sheet worker, the joiner and the final
 * assembler are generic in {@code A}; one codec instance per run keeps every call monomorphic, so the
 * JIT inlines them and the {@code short[]} path costs what the hand-written one did.
 *
 * <p>Values cross the interface as {@code short}: a byte label widens losslessly, and narrowing back
 * ({@link #set}, {@link #fromInts}, {@link #parseCsv}) is range-checked for the byte codec, so a key that
 * does not fit its tier fails loudly instead of wrapping.</p>
 *
 * @param <A> the primitive array type ({@code byte[]} or {@code short[]})
 */
public interface KeyCodec<A> {

    DataTypeDispatcher.Tier tier();

    Class<A> arrayClass();

    A newArray(int length);

    /** A shared zero-length array (never mutated). */
    A empty();

    int length(A a);

    short get(A a, int index);

    /** @throws IllegalArgumentException if the value does not fit this codec's tier */
    void set(A a, int index, short value);

    /**
     * Build a row from parsed integers (the FW_Group / FW_ReplaceRE path).  The byte codec throws
     * {@link NumberFormatException} for a value outside its range, so the caller's existing
     * "no longer a list of codes" handling applies; the short codec keeps the legacy {@code (short)} cast.
     */
    A fromInts(int[] values);

    int[] toInts(A a);

    /** Boxed copy, for the joiner's string builders. */
    Short[] box(A a);

    /** All rows back to back (the grouped FW_() operand). */
    A concat(List<A> parts);

    /**
     * The joiner's comma-separated key list ({@code "12, 13, -4"}).  Tokens that are blank or do not parse
     * as a short are skipped, as before; a parsed value outside the byte range is an error.
     */
    A parseCsv(String csv);

    /** What the PostgreSQL JDBC driver returned for an {@code int2[]} column ({@code Short[]}, {@code short[]}, ...). */
    A fromJdbc(Object jdbcArray);

    boolean arrayEquals(A x, A y);

    int arrayHash(A a);

    /** Lexicographic by value, then by length — the order FW_Group sorts its source rows in. */
    int compare(A x, A y);

    /** Append {@code {a,b,c}} to a COPY payload. */
    void encode(PgCopyBuffer out, A a);

    /** Human-readable {@code [a, b, c]}. */
    String describe(A a);
}
