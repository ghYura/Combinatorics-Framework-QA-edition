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
