package com.company;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Scalable enforcement of DEFERRED optional bonds (constraints that touch an FW_Optional sheet).
 *
 * <p>The Python sieve compiles each such bond into a compact, code-tuple spec — independent of the
 * candidate count — and this filter evaluates it PER assembled candidate during the Reader's
 * cartesian assembly. No constraint engine, predicate evaluator, or value decoding lives here: a
 * bond is just a polarity + a precomputed gate flag + the column names it references + the small set
 * of NumberToValue1 code-tuples for which it "holds" (pairs, sets, and {@code when} all collapse to
 * this by Python). Matching is pure {@code short} set membership over the assembled candidate's
 * per-column code arrays. Memory is O(bonds); there is NO per-candidate precomputed skip-list.
 *
 * <p>File format — one bond per line, {@code F|R} | {@code 1/0} gateOk | {@code sheet,sheet,...} |
 * {@code c,c,...;c,c,...} (semicolon-separated tuples, each comma-separated codes aligned to the
 * sheets). The sheet names are the Reader's assembled-candidate map keys:
 * <pre>F|1|O1,O3|10,14</pre>
 */
public final class OptionalBondFilter {

    private static final class Bond {
        final boolean forbid;     // forbid: a holding tuple removes the candidate; require: a non-holding one does
        final boolean gateOk;     // precomputed by Python (the referenced sheets are fixed positions)
        final String[] cols;      // referenced SHEET names (the assembled-candidate map keys, e.g. "O1")
        final short[][] tuples;   // each tuple = codes aligned to cols; the values for which the bond holds

        Bond(boolean forbid, boolean gateOk, String[] cols, short[][] tuples) {
            this.forbid = forbid;
            this.gateOk = gateOk;
            this.cols = cols;
            this.tuples = tuples;
        }
    }

    private final List<Bond> bonds;

    private OptionalBondFilter(List<Bond> bonds) {
        this.bonds = bonds;
    }

    /** Parse the bonds file; returns {@code null} if the path is blank/absent/empty so callers can
     *  gate on a single null check (a non-sieving run then pays nothing per candidate). */
    public static OptionalBondFilter loadOrNull(String path) {
        if (path == null || path.isBlank()) {
            return null;
        }
        File f = new File(path.trim());
        if (!f.isFile()) {
            return null;
        }
        List<Bond> list = new ArrayList<>();
        try (BufferedReader br = new BufferedReader(
                new InputStreamReader(new FileInputStream(f), StandardCharsets.UTF_8))) {
            String ln;
            while ((ln = br.readLine()) != null) {
                ln = ln.trim();
                if (ln.isEmpty() || ln.charAt(0) == '#') {
                    continue;
                }
                String[] p = ln.split("\\|", -1);
                if (p.length < 4 || p[2].isEmpty()) {
                    continue;
                }
                boolean forbid = !p[0].trim().equalsIgnoreCase("R");
                boolean gateOk = p[1].trim().equals("1");
                String[] cols = p[2].split(",");
                String[] tupStrs = p[3].isEmpty() ? new String[0] : p[3].split(";");
                short[][] tuples = new short[tupStrs.length][];
                for (int i = 0; i < tupStrs.length; i++) {
                    String[] cc = tupStrs[i].split(",");
                    short[] t = new short[cc.length];
                    for (int k = 0; k < cc.length; k++) {
                        t[k] = Short.parseShort(cc[k].trim());
                    }
                    tuples[i] = t;
                }
                list.add(new Bond(forbid, gateOk, cols, tuples));
            }
        } catch (IOException | NumberFormatException e) {
            System.out.println("  [constraints] bonds file unreadable, ignoring: " + e);
            return null;
        }
        return list.isEmpty() ? null : new OptionalBondFilter(list);
    }

    public int size() {
        return bonds.size();
    }

    /**
     * True if this assembled candidate violates a bond and must be skipped. {@code candidate} maps
     * a SHEET name to its {@code short[]} codes (the Reader's per-candidate merged map, combi_id
     * removed and absent/null sheets dropped).
     */
    public boolean violates(Map<String, Object> candidate) {
        for (Bond b : bonds) {
            short[][] vals = new short[b.cols.length][];
            boolean applicable = true;
            for (int k = 0; k < b.cols.length; k++) {
                Object o = candidate.get(b.cols[k]);
                if (!(o instanceof short[] arr)) {
                    applicable = false;          // a referenced sheet is ABSENT in this candidate
                    break;
                }
                if (arr.length == 0) {
                    applicable = false;
                    break;
                }
                short[] s = new short[arr.length];
                for (int i = 0; i < arr.length; i++) {
                    if (arr[i] == com.company.helpers.CopyToReader.NULL_ELEMENT) {
                        applicable = false;
                        break;
                    }
                    s[i] = arr[i];
                }
                if (!applicable) {
                    break;
                }
                vals[k] = s;
            }
            if (!applicable) {
                continue;                        // bond doesn't apply -> not violated by it
            }
            if (!b.gateOk) {                     // the referenced positions can't satisfy the gate
                if (!b.forbid) {
                    return true;                 // require can never hold here -> remove
                }
                continue;                        // forbid can never fire here -> keep
            }
            boolean holds = false;
            for (short[] tup : b.tuples) {
                boolean all = true;
                for (int k = 0; k < tup.length; k++) {
                    if (!contains(vals[k], tup[k])) {
                        all = false;
                        break;
                    }
                }
                if (all) {
                    holds = true;
                    break;
                }
            }
            if (b.forbid ? holds : !holds) {
                return true;
            }
        }
        return false;
    }

    private static boolean contains(short[] arr, short v) {
        for (short x : arr) {
            if (x == v) {
                return true;
            }
        }
        return false;
    }
}
