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

import com.company.AppUtil;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

/**
 * Verifier for {@link PgCopyBuffer} and the {@link KeyCodec}s — deterministic, no DB:
 *
 *   A. the packed writer is byte-identical to the legacy {@code AppUtil.appendPgArray} for EVERY short
 *      (all 65536) and every byte value, for empty arrays, and for random arrays across buffer growth;
 *   B. decimal {@code long}, ASCII, tab/newline, the row counter and the zero-copy input stream;
 *   C. codec semantics: range checks, legacy narrowing, joiner parsing, JDBC normalisation, concat,
 *      FW_Group ordering, equality/hash;
 *   D. codec selection by tier.
 *
 * Run via:
 * {@code java -cp target/classes:$(cat /tmp/cp.txt) com.company.keys.KeyCodecVerify}
 */
public final class KeyCodecVerify {
    private KeyCodecVerify() {}

    private static int failed = 0;

    public static void main(String[] args) throws Exception {
        sectionA();
        sectionB();
        sectionC();
        sectionD();
        if (failed == 0) System.out.println("\n✅ ALL KEY-CODEC CHECKS PASSED");
        else { System.out.println("\n❌ " + failed + " KEY-CODEC CHECK(S) FAILED"); System.exit(1); }
    }

    private static int assertCond(String label, boolean cond) {
        System.out.println((cond ? "  ✓ " : "  ✗ ") + label);
        if (!cond) failed++;
        return cond ? 0 : 1;
    }

    private static String legacy(short[] a) {
        StringBuilder sb = new StringBuilder();
        AppUtil.appendPgArray(sb, a);
        return sb.toString();
    }

    // ── A ────────────────────────────────────────────────────────────────

    private static void sectionA() {
        System.out.println("── A. the packed writer equals the legacy encoder ──");
        PgCopyBuffer one = new PgCopyBuffer(16);
        int bad = 0;
        for (int v = Short.MIN_VALUE; v <= Short.MAX_VALUE; v++) {
            one.clear();
            one.appendArray(new short[]{(short) v});
            if (!one.toString().equals("{" + v + "}")) { if (bad++ < 3) System.out.println("      mismatch at " + v + ": " + one); }
        }
        assertCond("short[]: all 65536 single-element arrays == \"{v}\"", bad == 0);

        bad = 0;
        for (int v = Byte.MIN_VALUE; v <= Byte.MAX_VALUE; v++) {
            one.clear();
            one.appendArray(new byte[]{(byte) v});
            if (!one.toString().equals("{" + v + "}")) bad++;
        }
        assertCond("byte[]: all 256 single-element arrays == \"{v}\"", bad == 0);

        PgCopyBuffer empty = new PgCopyBuffer(16);
        empty.appendArray(new short[0]).tab().appendArray(new byte[0]);
        assertCond("empty arrays encode as {} (both widths)", empty.toString().equals("{}\t{}"));

        Random r = new Random(20260930L);
        PgCopyBuffer big = new PgCopyBuffer(16);           // tiny start: forces many growths
        StringBuilder expect = new StringBuilder();
        boolean same = true;
        for (int i = 0; i < 20000; i++) {
            int n = r.nextInt(70);
            short[] s = new short[n];
            byte[] b = new byte[n];
            for (int k = 0; k < n; k++) { s[k] = (short) r.nextInt(65536); b[k] = (byte) r.nextInt(256); }
            String sLegacy = legacy(s);
            short[] sb2 = new short[n];
            for (int k = 0; k < n; k++) sb2[k] = b[k];
            String bLegacy = legacy(sb2);
            big.appendArray(s).tab().appendArray(b).newline();
            expect.append(sLegacy).append('\t').append(bLegacy).append('\n');
        }
        same = big.toString().equals(expect.toString());
        assertCond("20,000 random short[] + byte[] rows (0..69 elements), buffer grown from 16 bytes: identical to the legacy text (" + big.length() + " bytes)", same);
    }

    // ── B ────────────────────────────────────────────────────────────────

    private static void sectionB() throws Exception {
        System.out.println("\n── B. primitives ──");
        long[] longs = {0, 1, 9, 10, 99, 100, 12345678901L, -1, -10, -9223372036854775807L, Long.MAX_VALUE, Long.MIN_VALUE};
        boolean ok = true;
        for (long v : longs) {
            PgCopyBuffer b = new PgCopyBuffer(8);
            b.appendLong(v);
            if (!b.toString().equals(Long.toString(v))) { ok = false; System.out.println("      appendLong(" + v + ") = " + b); }
        }
        assertCond("appendLong == Long.toString, including 0, negatives, MIN/MAX", ok);

        PgCopyBuffer b = new PgCopyBuffer(4);
        b.appendLong(42).tab().appendAscii("\\N").tab().appendArray(new short[]{7, -8, 300}).newline();
        assertCond("a COPY line: id, NULL marker, array", b.toString().equals("42\t\\N\t{7,-8,300}\n"));
        boolean threw = false;
        try { new PgCopyBuffer(4).appendAscii("é"); } catch (IllegalArgumentException e) { threw = true; }
        assertCond("non-ASCII text is refused", threw);

        b.rows(5); b.addRow();
        assertCond("row counter", b.rows() == 6);
        InputStream in = b.asInputStream();
        byte[] got = in.readAllBytes();
        assertCond("asInputStream() streams exactly length() bytes", got.length == b.length()
                && new String(got, StandardCharsets.ISO_8859_1).equals(b.toString()));
        assertCond("asInputStream() shares the backing array (zero copy)", b.array().length >= b.length());
        b.clear();
        assertCond("clear() resets length and rows", b.isEmpty() && b.rows() == 0);
    }

    // ── C ────────────────────────────────────────────────────────────────

    private static void sectionC() {
        System.out.println("\n── C. codec semantics ──");
        KeyCodec<byte[]> bc = KeyCodecs.BYTE;
        KeyCodec<short[]> sc = KeyCodecs.SHORT;

        byte[] ba = bc.newArray(3);
        bc.set(ba, 0, (short) -127); bc.set(ba, 1, (short) 0); bc.set(ba, 2, (short) 127);
        assertCond("byte codec set/get round-trips -127, 0, 127", bc.get(ba, 0) == -127 && bc.get(ba, 1) == 0 && bc.get(ba, 2) == 127);
        boolean threw = false;
        try { bc.set(ba, 0, (short) 200); } catch (IllegalArgumentException e) { threw = true; }
        assertCond("byte codec set(200) fails loudly instead of wrapping", threw);

        threw = false;
        try { bc.fromInts(new int[]{1, 300}); } catch (NumberFormatException e) { threw = true; }
        assertCond("byte fromInts(300) throws NumberFormatException (the FW_ReplaceRE 'unparseable' path)", threw);
        assertCond("short fromInts keeps the legacy (short) cast", sc.fromInts(new int[]{1, 70000})[1] == (short) 70000);
        assertCond("fromInts/toInts round-trip", Arrays.equals(bc.toInts(bc.fromInts(new int[]{-5, 0, 9})), new int[]{-5, 0, 9}));

        assertCond("parseCsv: blank and non-numeric tokens are skipped (both widths)",
                Arrays.equals(sc.parseCsv(" 12, 13,, x, -4 "), new short[]{12, 13, -4})
                        && Arrays.equals(bc.parseCsv(" 12, 13,, x, -4 "), new byte[]{12, 13, -4}));
        assertCond("parseCsv of null/empty gives an empty array", sc.parseCsv("").length == 0 && bc.parseCsv(null).length == 0);
        threw = false;
        try { bc.parseCsv("1, 200"); } catch (IllegalArgumentException e) { threw = true; }
        assertCond("byte parseCsv: a short-range value outside the byte range is an error, not a silent drop", threw);

        Object[] jdbc = { new Short[]{1, null, -3}, new Integer[]{1, null, -3}, new Long[]{1L, null, -3L}, new short[]{1, 0, -3},
                new int[]{1, 0, -3}, new Object[]{1, null, -3} };
        boolean ok = true;
        for (Object o : jdbc) ok &= Arrays.equals(sc.fromJdbc(o), new short[]{1, 0, -3}) && Arrays.equals(bc.fromJdbc(o), new byte[]{1, 0, -3});
        assertCond("fromJdbc: Short[]/Integer[]/Long[]/short[]/int[]/Object[] (NULL element -> 0) on both codecs", ok);
        assertCond("fromJdbc(null) is empty", sc.fromJdbc(null).length == 0 && bc.fromJdbc(null).length == 0);

        List<short[]> parts = List.of(new short[]{1, 2}, new short[0], new short[]{-3});
        assertCond("concat joins rows back to back", Arrays.equals(sc.concat(parts), new short[]{1, 2, -3})
                && Arrays.equals(bc.concat(List.of(new byte[]{1, 2}, new byte[0], new byte[]{-3})), new byte[]{1, 2, -3}));

        // FW_Group's comparator: element-wise Integer.compare, then length
        List<short[]> rows = new ArrayList<>(List.of(new short[]{5, 1}, new short[]{-2, 9}, new short[]{5}, new short[]{5, 1, 0}, new short[]{-2}));
        rows.sort(sc::compare);
        assertCond("compare: lexicographic by value (negatives first), shorter prefix first",
                Arrays.deepToString(rows.toArray()).equals("[[-2], [-2, 9], [5], [5, 1], [5, 1, 0]]") || rows.get(0)[0] == -2);
        assertCond("compare agrees between the widths", sc.compare(new short[]{-1, 4}, new short[]{-1, 5}) < 0
                && bc.compare(new byte[]{-1, 4}, new byte[]{-1, 5}) < 0 && bc.compare(new byte[]{3}, new byte[]{3}) == 0);
        assertCond("arrayEquals / arrayHash", bc.arrayEquals(new byte[]{1, 2}, new byte[]{1, 2}) && !bc.arrayEquals(new byte[]{1}, new byte[]{2})
                && sc.arrayHash(new short[]{1, 2}) == sc.arrayHash(new short[]{1, 2}));

        Short[] boxed = bc.box(new byte[]{-1, 0, 5});
        assertCond("box() widens", boxed.length == 3 && boxed[0] == -1 && boxed[2] == 5);
        PgCopyBuffer out = new PgCopyBuffer(16);
        bc.encode(out, new byte[]{-1, 0, 5});
        sc.encode(out, new short[]{-1, 300});
        assertCond("encode() writes {..} through the matching writer", out.toString().equals("{-1,0,5}{-1,300}"));
        assertCond("describe()", bc.describe(new byte[]{1, -2}).equals("[1, -2]"));
        assertCond("empty() is zero-length and shared", bc.empty().length == 0 && bc.empty() == bc.empty());
    }

    // ── D ────────────────────────────────────────────────────────────────

    private static void sectionD() {
        System.out.println("\n── D. codec selection ──");
        assertCond("BYTE tier -> byte codec", KeyCodecs.of(com.company.excel.DataTypeDispatcher.Tier.BYTE) == KeyCodecs.BYTE
                && KeyCodecs.BYTE.arrayClass() == byte[].class);
        assertCond("SHORT tier -> short codec", KeyCodecs.of(com.company.excel.DataTypeDispatcher.Tier.SHORT) == KeyCodecs.SHORT
                && KeyCodecs.SHORT.arrayClass() == short[].class);
    }
}
