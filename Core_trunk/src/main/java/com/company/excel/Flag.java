package com.company.excel;

/**
 * Type-safe enumeration of the {@code FW_*} flag tokens that appear in
 * positional columns 2 and 3 of an {@code FW_Seq} row.
 *
 * Used by {@link ProgrammaticScheduleBuilder} to express what XLSX authors
 * would otherwise hand-type into a cell.  The {@link #token} field is the
 * literal string the engine expects to read.
 *
 * Note: not every flag is meaningful in every positional column — the engine
 * decides semantics by column index AND content.  The builder enforces no
 * ordering rules; if you set an inappropriate combination, downstream
 * behaviour matches what you'd see if you'd typed the same combination into
 * an XLSX cell.  This keeps the DSL a faithful mirror, not a re-validator.
 */
public enum Flag {
    EXCLUDE          ("FW_Exclude"),
    OPTIONAL         ("FW_Optional"),
    REUSE            ("FW_Reuse"),
    REUSE_TABLE_ONLY ("FW_ReuseTableOnly"),
    HEADING          ("FW_Heading"),
    LAST_IN_QUEUE    ("FW_LastInQueue"),
    CONCATENATOR     ("FW_Concatenator");

    public final String token;
    Flag(String token) { this.token = token; }

    @Override public String toString() { return token; }
}
