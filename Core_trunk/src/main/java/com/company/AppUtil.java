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

package com.company;


public final class AppUtil {

private AppUtil() { }




public static void appendPgArray(StringBuilder sb, int[] arr) {
if (arr == null) { sb.append("\\N"); return; }
sb.append('{');
for (int i = 0; i < arr.length; i++) {
if (i > 0) sb.append(',');
sb.append(arr[i]);
}
sb.append('}');
}


public static void appendPgArray(StringBuilder sb, short[] arr) {
if (arr == null) { sb.append("\\N"); return; }
sb.append('{');
for (int i = 0; i < arr.length; i++) {
if (i > 0) sb.append(',');
sb.append(arr[i]);
}
sb.append('}');
}




public static long countRowsEstimate(String tableName, com.company.db.DbClient db) {
return db.queryLong(
"SELECT (CASE WHEN c.reltuples < 0 THEN NULL\n"
+ "     WHEN c.relpages = 0 THEN float8 '0'\n"
+ "     ELSE c.reltuples / c.relpages END\n"
+ "   * (pg_catalog.pg_relation_size(c.oid)\n"
+ "    / pg_catalog.current_setting('block_size')::int)\n"
+ "     )::bigint\n"
+ "FROM pg_catalog.pg_class c\n"
+ "WHERE c.oid = 'public." + tableName + "'::regclass;");
}
}
