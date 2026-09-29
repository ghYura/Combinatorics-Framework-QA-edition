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

package com.company.excel;

import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Estimates how often each cell key is going to be printed, from the FW_Seq program alone
 * (no parse, no DB) — the "potentially most abundant row" analysis {@link DataTypeDispatcher}
 * uses to place the label window.
 *
 * <p>An estimate, not a promise: it only steers where the window sits, and the dispatcher
 * adopts a window only when the predicted saving clears a threshold.  What it models, in the
 * order the engine runs it:</p>
 * <ul>
 *   <li><b>Verb chains</b> per sheet ({@code SheetWorker}): pass 0 combines the sheet's cells,
 *       every later pass combines the elements of each previous row (rows multiply);
 *       {@code FW_Group} makes the next verb combine the previous <em>rows</em> (so lines get
 *       {@code m x rowLength} long); {@code FW_Separator} interleaves a key (L -> 2L-1).
 *       Row counts and lengths use the same closed forms as {@code CombinatorialGenerator}.</li>
 *   <li><b>Joiners</b> {@code FW_(...)} ({@code BraceOperationHandler}): 1:N / M:1 repeat the
 *       whole other operand once per element; relation, separator, start and end contribute their
 *       sheet's FIRST cell many times per line; nested / grouped operands are honoured.</li>
 *   <li><b>fw_final</b> is the Cartesian product of the mandatory sheets, so a row of sheet s
 *       is printed {@code Rtotal / rows(s)} times: a cell of s appears
 *       {@code Rtotal * len(s) / cells(s)} times in total, independent of how many rows s has.</li>
 * </ul>
 * All quantities are relative and saturating ({@code double}); only their ratios matter.
 */
final class KeyWeightModel {

    private static final double HUGE = 1e290;

    /** True when some FW_Seq cell holds an {@code FW_ReplaceRE}: its regexes run on key text. */
    final boolean replaceRePresent;

    private final double[] perCell;        // aligned with Census.sheetNames
    private final int[]    extraOrdinal;   // absolute cell ordinals
    private final double[] extraWeight;
    private final int[]    sheetOffset;
    private final double   maxTotal;

    private KeyWeightModel(boolean replaceRePresent, double[] perCell, int[] extraOrdinal,
                           double[] extraWeight, int[] sheetOffset, int[] cellsPerSheet) {
        this.replaceRePresent = replaceRePresent;
        this.sheetOffset = sheetOffset;
        double max = 0.0;
        for (double w : perCell) max = Math.max(max, w);
        for (double w : extraWeight) max = Math.max(max, w);
        this.maxTotal = max;
        // normalise so every later product stays finite
        this.perCell = new double[perCell.length];
        for (int i = 0; i < perCell.length; i++) this.perCell[i] = max > 0 ? perCell[i] / max : 0.0;
        this.extraOrdinal = extraOrdinal;
        this.extraWeight = new double[extraWeight.length];
        for (int i = 0; i < extraWeight.length; i++) this.extraWeight[i] = max > 0 ? extraWeight[i] / max : 0.0;
    }

    boolean hasWeights() { return maxTotal > 0; }

    /** Index (in census order) of the sheet whose cells carry the most weight, or the named one. */
    int heavySheet(String forcedName, DataTypeDispatcher.Census c) {
        if (forcedName != null) {
            for (int s = 0; s < c.sheetNames.length; s++) {
                if (c.sheetNames[s].equals(forcedName)) return s;
            }
            // unknown name: fall through to the estimate
        }
        int best = 0;
        double bestW = -1;
        for (int s = 0; s < c.sheetNames.length; s++) {
            double w = perCell[s] * c.cellsPerSheet[s];
            for (int e = 0; e < extraOrdinal.length; e++) {
                int o = extraOrdinal[e];
                if (o >= sheetOffset[s] && o < sheetOffset[s] + c.cellsPerSheet[s]) w += extraWeight[e];
            }
            if (w > bestW) { bestW = w; best = s; }
        }
        return best;
    }

    /** Predicted emitted characters (labels + one comma each) for a window starting at {@code base}. */
    double cost(DataTypeDispatcher.Census c, int base, DataTypeDispatcher.Tier tier, int[] prefix) {
        double total = 0.0;
        for (int s = 0; s < c.cellsPerSheet.length; s++) {
            int n = c.cellsPerSheet[s];
            if (n == 0 || perCell[s] == 0.0) continue;
            int from = base + sheetOffset[s] - tier.min;
            total += perCell[s] * ((prefix[from + n] - prefix[from]) + n);
        }
        for (int e = 0; e < extraOrdinal.length; e++) {
            total += extraWeight[e] * (DataTypeDispatcher.labelChars(base + extraOrdinal[e]) + 1);
        }
        return total;
    }

    /** The feasible window start with the smallest predicted cost (ties: the larger base). */
    int optimalBase(DataTypeDispatcher.Census c, DataTypeDispatcher.Tier tier, int[] prefix, int lo, int hi) {
        int best = hi;
        double bestCost = Double.MAX_VALUE;
        for (int base = hi; base >= lo; base--) {
            double cost = cost(c, base, tier, prefix);
            if (cost < bestCost) { bestCost = cost; best = base; }
        }
        return best;
    }

    // ── construction ─────────────────────────────────────────────────────

    /** Rows and per-row element count of one FW_Seq target after its verb chain. */
    private static final class Vol {
        double rows = 1.0;
        double len;
        Vol(double rows, double len) { this.rows = rows; this.len = len; }
    }

    private static final class SeqRow {
        final String target; final List<String> verbs; final boolean exclude, optional;
        SeqRow(String target, List<String> verbs, boolean exclude, boolean optional) {
            this.target = target; this.verbs = verbs; this.exclude = exclude; this.optional = optional;
        }
    }

    private static final class Joiner {
        final String target, a, b, relation, sep, start, end, formula;
        final boolean groupedA, groupedB;
        Joiner(String target, String a, String b, String relation, String sep, String start, String end,
               String formula, boolean groupedA, boolean groupedB) {
            this.target = target; this.a = a; this.b = b; this.relation = relation; this.sep = sep;
            this.start = start; this.end = end; this.formula = formula;
            this.groupedA = groupedA; this.groupedB = groupedB;
        }
    }

    static KeyWeightModel build(DataTypeDispatcher.Census c, Sheet fwSeq) {
        final int S = c.sheetNames.length;
        final Map<String, Integer> idx = new HashMap<>();
        final int[] offset = new int[S];
        int acc = 0;
        for (int s = 0; s < S; s++) { idx.put(c.sheetNames[s], s); offset[s] = acc; acc += c.cellsPerSheet[s]; }

        // virtual targets (headless rows / missing names) are sheets without cells
        final Map<Integer, String> headless = new HashMap<>();
        final Map<String, Boolean> virtualNames = new HashMap<>();
        for (WorkbookParser.VirtualSheet v : WorkbookParser.discoverVirtualSheets(
                fwSeq, new java.util.LinkedHashSet<>(idx.keySet()), "FW_VIRTUAL_", new DataFormatter())) {
            virtualNames.put(v.name, Boolean.TRUE);
            if (v.headlessRowIdx != null) headless.put(v.headlessRowIdx, v.name);
        }

        // 1. FW_Seq rows -> per-target verb lists (last row of a target wins, as in SeqParser)
        final DataFormatter fmt = new DataFormatter();
        final Map<String, SeqRow> rows = new LinkedHashMap<>();
        final List<String> braceTargets = new ArrayList<>();
        final List<Joiner> joiners = new ArrayList<>();
        boolean replaceRe = false;
        String keySheet = null;
        int rowIdx = 0;
        for (Row row : fwSeq) {
            List<String> verbs = new ArrayList<>();
            boolean exclude = false, optional = false;
            String syn = headless.get(rowIdx);
            if (syn != null) keySheet = syn;
            for (Cell cell : row) {
                String v = fmt.formatCellValue(cell);
                if (v == null || v.isBlank()) continue;
                if (idx.containsKey(v) || virtualNames.containsKey(v)) keySheet = v;
                if (v.contains("FW_ReplaceRE")) replaceRe = true;
                if (v.endsWith("FW_Exclude") || v.endsWith("FW_Heading")) exclude = true;
                else if (v.endsWith("FW_Optional")) optional = true;
                else if (v.endsWith("FW_LastInQueue") || v.endsWith("FW_Reuse")
                        || v.endsWith("FW_ReuseTableOnly") || v.startsWith("FW_Concatenator")) { /* flags */ }
                else if (v.startsWith("FW_")) verbs.add(v);
            }
            rowIdx++;
            if (verbs.isEmpty() || keySheet == null) continue;

            // SeqParser auto-promotion: a lone combo-rule verb runs twice
            boolean hasJoiner = false; int comboCount = 0, comboIdx = -1;
            for (int i = 0; i < verbs.size(); i++) {
                String s = verbs.get(i);
                if (s.startsWith("FW_(")) { hasJoiner = true; break; }
                if (isComboRule(s)) { comboCount++; if (comboIdx < 0) comboIdx = i; }
            }
            if (!hasJoiner && comboCount == 1) verbs.add(verbs.get(comboIdx));

            for (String verb : verbs) {
                if (verb.startsWith("FW_(")) {
                    Joiner j = parseJoiner(keySheet, verb, braceTargets);
                    if (j != null) joiners.add(j);
                    braceTargets.add(keySheet);
                }
            }
            rows.put(keySheet, new SeqRow(keySheet, verbs, exclude, optional));
        }

        // 2. volumes in FW_Seq order (operands precede joiners)
        final Map<String, Vol> vols = new HashMap<>();
        final Map<String, String> separatorOf = new HashMap<>();
        final Map<String, Double> separatorLen = new HashMap<>();
        final Map<String, String> cartesOperand = new HashMap<>();
        final java.util.Set<String> braceTargets2 = new java.util.HashSet<>();
        for (SeqRow r : rows.values()) {
            double n = idx.containsKey(r.target) ? c.cellsPerSheet[idx.get(r.target)] : 0.0;
            Vol vol = new Vol(1.0, n);
            String sepName = null;
            double sepLenBefore = 0;
            boolean first = true, group = false;
            for (String verb : r.verbs) {
                String algo = algoType(verb);
                switch (algo) {
                    case "BRACE": {
                        Joiner j = null;
                        for (Joiner cand : joiners) { if (cand.target.equals(r.target)) j = cand; }
                        if (j != null) vol = joinerVolume(j, vols, idx, c);
                        braceTargets2.add(r.target);
                        first = false; group = false;
                        continue;
                    }
                    case "FW_Group": group = true; continue;
                    case "FW_Separator": sepName = innerOf(verb); continue;
                    case "UNKNOWN": continue;
                    default: break;
                }
                double other = 1.0;
                if (algo.equals("FW_Cartes")) {
                    Integer o = idx.get(innerOf(verb));
                    other = (o == null) ? 1.0 : c.cellsPerSheet[o];
                    if (o != null) cartesOperand.put(r.target, innerOf(verb));
                }
                boolean pass0 = first;
                first = false;
                double listSize = (group && !pass0) ? vol.rows : (pass0 ? n : vol.len);
                double unit = (group && !pass0) ? vol.len : 1.0;
                double[] f = fanout(algo, verb, listSize, other);     // {rows, itemsPerRow}
                if (group && !pass0) { vol = new Vol(f[0], f[1] * unit); }
                else if (pass0)      { vol = new Vol(f[0], f[1]); }
                else                 { vol = new Vol(sat(vol.rows * f[0]), f[1]); }
                if (sepName != null && !pass0) {
                    sepLenBefore = vol.len;
                    if (vol.len > 1) vol.len = 2 * vol.len - 1;
                    separatorOf.put(r.target, sepName);
                    separatorLen.put(r.target, sepLenBefore);
                }
                group = false;
            }
            vols.put(r.target, vol);
        }

        // 3. weights
        double logRtotal = 0.0;
        for (SeqRow r : rows.values()) {
            if (!r.exclude && !r.optional) logRtotal += Math.log(Math.max(1.0, vols.get(r.target).rows));
        }
        final double rTotal = Math.min(HUGE, Math.exp(Math.min(logRtotal, 690.0)));

        final double[] perCell = new double[S];
        final Map<Integer, Double> extras = new HashMap<>();

        for (SeqRow r : rows.values()) {
            Integer si = idx.get(r.target);
            Vol v = vols.get(r.target);
            boolean mandatory = !r.exclude && !r.optional;
            // A joiner's output is built from its operands' rows: the joiner sheet's OWN cells are never printed.
            if (si != null && c.cellsPerSheet[si] > 0 && !braceTargets2.contains(r.target)) {
                double perRow = v.len / c.cellsPerSheet[si];
                perCell[si] = sat(perCell[si] + v.rows * perRow + (mandatory ? rTotal * perRow : 0.0));
            }
            // FW_Cartes(X): every produced row holds exactly one cell of X
            String cartes = cartesOperand.get(r.target);
            if (cartes != null) {
                Integer xi = idx.get(cartes);
                if (xi != null && c.cellsPerSheet[xi] > 0) {
                    perCell[xi] = sat(perCell[xi] + (v.rows + (mandatory ? rTotal : 0.0)) / c.cellsPerSheet[xi]);
                }
            }
            String sepName = separatorOf.get(r.target);
            if (sepName != null) {
                Integer sep = idx.get(sepName);
                if (sep != null && c.cellsPerSheet[sep] > 0) {
                    double occ = (v.rows + (mandatory ? rTotal : 0.0)) * Math.max(0.0, separatorLen.get(r.target) - 1.0);
                    extras.merge(offset[sep], sat(occ), (x, y) -> sat(x + y));
                }
            }
        }
        for (Joiner j : joiners) {
            SeqRow jr = rows.get(j.target);
            if (jr == null) continue;
            Vol vj = vols.get(j.target);
            double factor = (!jr.exclude && !jr.optional) ? rTotal : vj.rows;
            double[] m = joinerMultiplicity(j, vols, idx, c);           // {mA, mB, mRel, mSep}
            attribute(j.a, j.groupedA, m[0], factor, vols, idx, c, perCell);
            attribute(j.b, j.groupedB, m[1], factor, vols, idx, c, perCell);
            firstCell(j.relation, m[2] * factor, idx, offset, c, extras);
            firstCell(j.sep,      m[3] * factor, idx, offset, c, extras);
            firstCell(j.start,    factor, idx, offset, c, extras);
            firstCell(j.end,      factor, idx, offset, c, extras);
        }

        int[] ords = new int[extras.size()];
        double[] ws = new double[extras.size()];
        int e = 0;
        for (Map.Entry<Integer, Double> en : extras.entrySet()) { ords[e] = en.getKey(); ws[e] = en.getValue(); e++; }
        return new KeyWeightModel(replaceRe, perCell, ords, ws, offset, c.cellsPerSheet);
    }

    // ── joiners ──────────────────────────────────────────────────────────

    private static Joiner parseJoiner(String target, String directive, List<String> braceTargets) {
        int open = directive.indexOf('('), close = directive.lastIndexOf(')');
        if (open < 0 || close <= open) return null;
        List<String> p = WorkbookParser.splitTopLevelByComma(directive.substring(open + 1, close));
        if (p.size() < 9) return null;
        String start = p.get(0), a = p.get(2), rel = p.get(3), b = p.get(4);
        String end = p.get(p.size() - 3), sep = p.get(p.size() - 2), formula = p.get(p.size() - 1);
        boolean nestedA = a.startsWith("FW_("), nestedB = b.startsWith("FW_(");
        boolean groupedA = nestedA && a.endsWith(")G"), groupedB = nestedB && b.endsWith(")G");
        int i = braceTargets.size() - 1;
        if (nestedA) { a = i >= 0 ? braceTargets.get(i) : ""; i--; }
        if (nestedB) { b = i >= 0 ? braceTargets.get(i) : ""; i--; }
        return new Joiner(target, a, b, rel, sep, start, end, formula, groupedA, groupedB);
    }

    private static Vol operand(String name, boolean grouped, Map<String, Vol> vols,
                               Map<String, Integer> idx, DataTypeDispatcher.Census c) {
        Vol v = vols.get(name);
        if (v == null) {
            Integer s = idx.get(name);
            v = new Vol(s == null ? 1.0 : Math.max(1, c.cellsPerSheet[s]), 1.0);
        }
        return grouped ? new Vol(1.0, sat(v.rows * v.len)) : v;
    }

    private static boolean on(String name, Map<String, Integer> idx, DataTypeDispatcher.Census c) {
        Integer s = (name == null || name.isEmpty()) ? null : idx.get(name);
        return s != null && c.cellsPerSheet[s] > 0;
    }

    /** {mA, mB, mRel, mSep}: how often, per joiner row, an A-row / B-row / relation / separator is printed. */
    private static double[] joinerMultiplicity(Joiner j, Map<String, Vol> vols, Map<String, Integer> idx,
                                               DataTypeDispatcher.Census c) {
        Vol a = operand(j.a, j.groupedA, vols, idx, c), b = operand(j.b, j.groupedB, vols, idx, c);
        double rel = on(j.relation, idx, c) ? 1.0 : 0.0, sep = on(j.sep, idx, c) ? 1.0 : 0.0;
        switch (j.formula.trim()) {
            case "1:N": return new double[]{1.0, a.len, a.len * rel, a.len * sep};
            case "M:1": return new double[]{b.len, 1.0, b.len * rel, b.len * sep};
            case "1:1": {
                double half = (a.len + b.len) / 2.0;
                return new double[]{1.0, 1.0, half * rel, half * sep};
            }
            default:    return new double[]{1.0, 1.0, rel, 0.0};          // M:N, M:M
        }
    }

    private static Vol joinerVolume(Joiner j, Map<String, Vol> vols, Map<String, Integer> idx,
                                    DataTypeDispatcher.Census c) {
        Vol a = operand(j.a, j.groupedA, vols, idx, c), b = operand(j.b, j.groupedB, vols, idx, c);
        double[] m = joinerMultiplicity(j, vols, idx, c);
        double len = m[0] * a.len + m[1] * b.len + m[2] + m[3]
                + (on(j.start, idx, c) ? 1 : 0) + (on(j.end, idx, c) ? 1 : 0);
        return new Vol(sat(a.rows * b.rows), len);
    }

    private static void attribute(String name, boolean grouped, double mult, double factor,
                                  Map<String, Vol> vols, Map<String, Integer> idx,
                                  DataTypeDispatcher.Census c, double[] perCell) {
        Integer s = name.isEmpty() ? null : idx.get(name);
        if (s == null || c.cellsPerSheet[s] == 0) return;
        Vol v = vols.get(name);
        double perRowCell;
        if (v == null) perRowCell = 1.0 / c.cellsPerSheet[s];
        else if (grouped) perRowCell = v.rows * v.len / c.cellsPerSheet[s];   // whole table in one line
        else perRowCell = v.len / c.cellsPerSheet[s];
        perCell[s] = sat(perCell[s] + factor * perRowCell * mult);
    }

    private static void firstCell(String name, double occurrences, Map<String, Integer> idx, int[] offset,
                                  DataTypeDispatcher.Census c, Map<Integer, Double> extras) {
        if (occurrences <= 0 || !on(name, idx, c)) return;
        extras.merge(offset[idx.get(name)], sat(occurrences), (x, y) -> sat(x + y));
    }

    // ── verb maths (closed forms of CombinatorialGenerator, in doubles) ──

    private static boolean isComboRule(String v) {
        return v.startsWith("FW_Combi(") || v.startsWith("FW_CombiR(") || v.startsWith("FW_Permut(")
                || v.startsWith("FW_PermutR(") || v.equals("FW_Subsets") || v.startsWith("FW_Subsets(");
    }

    private static String algoType(String d) {
        if (d.startsWith("FW_("))         return "BRACE";
        if (d.startsWith("FW_CombiR"))    return "FW_CombiR";
        if (d.startsWith("FW_Combi"))     return "FW_Combi";
        if (d.startsWith("FW_PermutR"))   return "FW_PermutR";
        if (d.startsWith("FW_Permut"))    return "FW_Permut";
        if (d.startsWith("FW_Subsets"))   return "FW_Subsets";
        if (d.startsWith("FW_Cartes"))    return "FW_Cartes";
        if (d.startsWith("FW_Group"))     return "FW_Group";
        if (d.startsWith("FW_Separator")) return "FW_Separator";
        return "UNKNOWN";
    }

    private static String innerOf(String verb) {
        int o = verb.indexOf('('), c = verb.lastIndexOf(')');
        return (o < 0 || c <= o) ? "" : verb.substring(o + 1, c).trim();
    }

    /** {rows, elements per row} of one verb over a list of {@code n} items. */
    private static double[] fanout(String algo, String verb, double n, double other) {
        final boolean size = verb.matches(algo + "\\((?i)size\\)");
        final boolean all  = verb.matches(algo + "\\((?i)(all|full)\\)");
        double m = 1.0;
        if (size) m = n;
        else if (verb.matches(algo + "\\(\\d+\\)")) m = Double.parseDouble(verb.replaceAll("\\D", ""));
        else if (algo.equals("FW_Subsets") && verb.contains("_") && verb.contains("(")) {
            String digits = verb.replaceAll("\\D*", "");
            if (!digits.isEmpty()) m = Double.parseDouble(digits.length() > 9 ? digits.substring(0, 9) : digits);
        }
        switch (algo) {
            case "FW_Combi":
                if (all) return new double[]{sat(Math.pow(2, Math.min(n, 1000)) - 1), Math.max(1, n / 2)};
                return new double[]{binom(n, m), m};
            case "FW_CombiR":
                if (all) return new double[]{binom(2 * n, n), Math.max(1, n / 2)};
                return new double[]{binom(n + m - 1, m), m};
            case "FW_Permut":
                return new double[]{expLog(logFactorial(n)), n};
            case "FW_PermutR":
                if (all) return new double[]{expLog(n * Math.log(Math.max(1, n))), n};
                return new double[]{expLog(m * Math.log(Math.max(1, n))), m};
            case "FW_Subsets": {
                if (!verb.contains("_") || verb.equals("FW_Subsets") || !verb.contains("(")) {
                    return new double[]{expLog(n * Math.log(2)), Math.max(1.0, n / 2)};
                }
                return subsetsByMode(verb, n);
            }
            case "FW_Cartes":
                return new double[]{sat(n * other), 2.0};
            default:
                return new double[]{1.0, n};
        }
    }

    private static double[] subsetsByMode(String verb, double n) {
        String mode = verb.replaceAll("FW_Subsets_|\\s+|[,]+|\\d+|\\(|\\)", "").toUpperCase(java.util.Locale.ROOT);
        String[] parts = verb.replaceAll("[^\\d,]+", "").split(",");
        List<Integer> p = new ArrayList<>();
        for (String s : parts) if (!s.isEmpty()) p.add(Integer.parseInt(s.length() > 9 ? s.substring(0, 9) : s));
        double rows = 0, elems = 0;
        int top = (int) Math.min(n, 5000);
        for (int sz = 0; sz <= top; sz++) {
            boolean match;
            switch (mode) {
                case "BEFORE": match = !p.isEmpty() && sz < p.get(0); break;
                case "AFTER":  match = !p.isEmpty() && sz > p.get(0); break;
                case "EXACT":  match = !p.isEmpty() && sz == p.get(0); break;
                case "RANGE":  match = p.size() > 1 && sz >= p.get(0) && sz <= p.get(1); break;
                case "GIVEN":  match = p.contains(sz); break;
                default:       match = true; break;
            }
            if (match) { double b = binom(n, sz); rows = sat(rows + b); elems = sat(elems + b * sz); }
        }
        return new double[]{rows, rows > 0 ? Math.max(1.0, elems / rows) : 1.0};
    }

    private static double[] lf = new double[]{0.0, 0.0};

    private static synchronized double logFactorial(double nD) {
        int n = (int) Math.min(Math.max(0, nD), 1_000_000);
        if (n >= lf.length) {
            double[] grown = new double[Math.max(n + 1, lf.length * 2)];
            System.arraycopy(lf, 0, grown, 0, lf.length);
            for (int i = lf.length; i < grown.length; i++) grown[i] = grown[i - 1] + Math.log(i);
            lf = grown;
        }
        return lf[n];
    }

    private static double binom(double nD, double kD) {
        if (kD < 0 || kD > nD) return 0.0;
        return expLog(logFactorial(nD) - logFactorial(kD) - logFactorial(nD - kD));
    }

    private static double expLog(double x) { return Math.min(HUGE, Math.exp(Math.min(x, 690.0))); }

    private static double sat(double x) { return x > HUGE ? HUGE : x; }
}
