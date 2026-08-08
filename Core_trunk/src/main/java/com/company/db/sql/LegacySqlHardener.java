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

package com.company.db.sql;

import java.util.function.UnaryOperator;
import java.util.regex.Pattern;


public final class LegacySqlHardener {

    private static final Pattern TRAILING_SEMI   = Pattern.compile("(?is)\\s*;\\s*$");
    private static final Pattern TRAILING_OFFSET = Pattern.compile("(?is)\\s+offset\\s+0\\s*$");


    public static final UnaryOperator<String> NORMALIZE = sql -> {
        if (sql == null) return null;
        String out = sql.trim();
        out = TRAILING_SEMI.matcher(out).replaceAll("");
        out = TRAILING_OFFSET.matcher(out).replaceAll("");
        return out;
    };


    public static final UnaryOperator<String> HARDEN = NORMALIZE;


    public static String harden(String sql) {
        return HARDEN.apply(sql);
    }


    public static String normalize(String sql) {
        return NORMALIZE.apply(sql);
    }

    private LegacySqlHardener() {  }
}
