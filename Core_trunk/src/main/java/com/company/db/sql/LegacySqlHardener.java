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
