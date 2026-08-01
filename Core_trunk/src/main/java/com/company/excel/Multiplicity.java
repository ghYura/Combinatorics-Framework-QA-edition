package com.company.excel;

/**
 * Cardinality relationship in a {@code FW_(...)} joiner expression.
 * Corresponds to the documented {M:N, M:M, M:1, 1:N, 1:1} set from the
 * project brief — the engine recognises these literal tokens in field 9
 * (last positional slot) of the joiner.
 */
public enum Multiplicity {
    /** Many-to-many across distinct sources. */
    M_N  ("M:N"),
    /** Many-to-many across the same source (self-join semantics). */
    M_M  ("M:M"),
    /** Many-to-one. */
    M_1  ("M:1"),
    /** One-to-many. */
    ONE_N("1:N"),
    /** One-to-one. */
    ONE_1("1:1");

    public final String token;
    Multiplicity(String token) { this.token = token; }

    @Override public String toString() { return token; }
}
