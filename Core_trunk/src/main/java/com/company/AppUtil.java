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
