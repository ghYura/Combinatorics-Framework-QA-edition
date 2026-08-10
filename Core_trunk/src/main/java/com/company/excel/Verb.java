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
 * Static factory for the verb tokens that populate columns 4..6 of an
 * {@code FW_Seq} row.  Each factory returns the exact string the engine
 * recognises — so the builder API stays additive (no second source of truth
 * for verb names) while the call sites read like a typed DSL.
 *
 * The hidden requirement noted in the project brief (Open Tier-0 bug 0.6)
 * — TWO {@code FW_Combi(1)} entries per source row — is the caller's
 * responsibility; the builder will faithfully pass through whatever you
 * supply via {@code .verbs(...)}.
 */
public final class Verb {
    private Verb() {}

    /** k-combinations without repetition: choose k of the entity's rows. */
    public static String combi(int k)      { return "FW_Combi("   + k + ")"; }
    /** k-combinations with repetition. */
    public static String combiR(int k)     { return "FW_CombiR("  + k + ")"; }
    /** k-permutations without repetition. */
    public static String permut(int k)     { return "FW_Permut("  + k + ")"; }
    /** k-permutations with repetition. */
    public static String permutR(int k)    { return "FW_PermutR(" + k + ")"; }
    /** All non-empty subsets (power-set minus ∅). */
    public static String subsets()         { return "FW_Subsets";          }
    /** Cartesian product across all listed entities. */
    public static String cartes()          { return "FW_Cartes";           }
    /** Cartesian product, first-only variant. */
    public static String cartesFirst()     { return "FW_Cartes_first";     }
    /** Group rows into a single concatenated cell. */
    public static String group()           { return "FW_Group";            }
    /** Custom field separator when concatenating. */
    public static String separator(String s) { return "FW_Separator(" + s + ")"; }
    /** Regex replacement on cell text. */
    public static String replaceRe(String pattern, String repl) {
        return "FW_ReplaceRE(" + pattern + "," + repl + ")";
    }
}
