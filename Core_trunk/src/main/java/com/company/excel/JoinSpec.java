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

package com.company.excel;

import java.util.ArrayList;
import java.util.List;

/**
 * Type-safe constructor for the engine's {@code FW_(start,_,Ei,relation,Ej,_,end,separator,multiplicity)}
 * joiner expression — the 8-comma / 9-field positional form from the project brief.
 *
 * Field map (matching the engine's reader):
 *   <ol>
 *     <li>{@code start}        — first source entity</li>
 *     <li>{@code _}            — unused</li>
 *     <li>{@code Ei}           — middle source #1 (optional)</li>
 *     <li>{@code relation}     — unused / experimental hook (empty in canonical scenarios)</li>
 *     <li>{@code Ej}           — middle source #2 (optional)</li>
 *     <li>{@code _}            — unused</li>
 *     <li>{@code end}          — last source entity</li>
 *     <li>{@code separator}    — concat separator between produced fields</li>
 *     <li>{@code multiplicity} — cardinality {@code M:N | M:M | M:1 | 1:N | 1:1}</li>
 *   </ol>
 *
 * Two middle slots is what the canonical scenarios use ({@code test_e2e_metric.json}
 * has {@code FW_(HEAD,,COST,,LAT,,TAIL,,M:N)}).  Callers needing different shapes
 * can drop to {@link ProgrammaticScheduleBuilder#joinRaw} with the literal string.
 *
 * Example:
 * <pre>{@code
 * JoinSpec spec = JoinSpec.from("HEAD")
 *                         .via("COST", "LAT")
 *                         .to("TAIL")
 *                         .as(Multiplicity.M_N);
 * b.join("ROW", spec).row("FW_EMPTY_STRING");
 * }</pre>
 */
public final class JoinSpec {

    private final String start;
    private String end = "";
    private final List<String> middle = new ArrayList<>(2);
    private String separator = "";
    private Multiplicity multiplicity = Multiplicity.M_N;

    private JoinSpec(String start) {
        if (start == null || start.isBlank())
            throw new IllegalArgumentException("JoinSpec.from: start must not be blank");
        this.start = start;
    }

    /** Begin a join with the named start entity. */
    public static JoinSpec from(String start) { return new JoinSpec(start); }

    /** Add up to two middle entities (canonical 2-slot form). */
    public JoinSpec via(String... middles) {
        if (middles == null) return this;
        for (String m : middles) if (m != null && !m.isBlank()) middle.add(m);
        return this;
    }

    /** Set the terminal entity (last source). */
    public JoinSpec to(String end) {
        if (end == null || end.isBlank())
            throw new IllegalArgumentException("JoinSpec.to: end must not be blank");
        this.end = end;
        return this;
    }

    /** Set the concat separator (empty by default — matches canonical scenarios). */
    public JoinSpec withSeparator(String sep) {
        this.separator = (sep == null) ? "" : sep;
        return this;
    }

    /** Set the cardinality relation (default {@link Multiplicity#M_N}). */
    public JoinSpec as(Multiplicity mul) {
        if (mul == null) throw new IllegalArgumentException("JoinSpec.as: multiplicity must not be null");
        this.multiplicity = mul;
        return this;
    }

    /** Render to the engine's canonical FW_(...) 9-field positional form. */
    public String toFwExpression() {
        // Field layout: start, _, Ei, relation, Ej, _, end, separator, multiplicity
        // (8 commas total, 9 fields).  Missing middle slots are emitted as empty.
        String ei = middle.size() > 0 ? middle.get(0) : "";
        String ej = middle.size() > 1 ? middle.get(1) : "";
        StringBuilder sb = new StringBuilder("FW_(");
        sb.append(start).append(',')
          .append("").append(',')      // _
          .append(ei).append(',')
          .append("").append(',')      // relation
          .append(ej).append(',')
          .append("").append(',')      // _
          .append(end).append(',')
          .append(separator).append(',')
          .append(multiplicity.token)
          .append(')');
        return sb.toString();
    }

    @Override public String toString() { return toFwExpression(); }
}
