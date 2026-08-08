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

package com.company.helpers;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;


public final class TableSchemaInspector {

private static final String ID_COLUMN = "combi_id";

private static final ConcurrentHashMap<String, Boolean> HAS_COMBI_ID_CACHE    = new ConcurrentHashMap<>();
private static final ConcurrentHashMap<String, Boolean> USE_REAL_COMBI_CACHE  = new ConcurrentHashMap<>();
private static final ConcurrentHashMap<String, List<String>> NON_ID_COLS_CACHE = new ConcurrentHashMap<>();

private TableSchemaInspector() {}

public static String idColumn() { return ID_COLUMN; }


public static void invalidate() {
HAS_COMBI_ID_CACHE.clear();
USE_REAL_COMBI_CACHE.clear();
NON_ID_COLS_CACHE.clear();
}


public static boolean hasCombiId(String tableName) {
Boolean cached = HAS_COMBI_ID_CACHE.get(tableName);
if (cached != null) return cached;
boolean present = columnExists(tableName, ID_COLUMN);
HAS_COMBI_ID_CACHE.put(tableName, present);
return present;
}


public static boolean useRealCombiId(String tableName) {
Boolean cached = USE_REAL_COMBI_CACHE.get(tableName);
if (cached != null) return cached;
boolean usable;
if (!hasCombiId(tableName)) {
usable = false;
} else {
usable = !anyNullCombiId(tableName);
}
USE_REAL_COMBI_CACHE.put(tableName, usable);
return usable;
}

public static boolean columnExists(String tableName, String columnName) {
final String sql =
"SELECT 1 FROM information_schema.columns " +
" WHERE table_schema = 'public' " +
"   AND table_name = ? " +
"   AND column_name = ? " +
" LIMIT 1";
try (Connection conn = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = conn.prepareStatement(sql)) {
ps.setString(1, tableName);
ps.setString(2, columnName);
try (ResultSet rs = ps.executeQuery()) {
return rs.next();
}
} catch (SQLException e) {
e.printStackTrace();
return false;
}
}

private static boolean anyNullCombiId(String tableName) {
final String sql = "SELECT 1 FROM public.\"" + tableName + "\" WHERE " + ID_COLUMN + " IS NULL LIMIT 1";
try (Connection conn = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = conn.prepareStatement(sql);
ResultSet rs = ps.executeQuery()) {
return rs.next();
} catch (SQLException e) {
e.printStackTrace();

return true;
}
}


public static List<String> nonCombiIdColumns(String tableName) {
List<String> cached = NON_ID_COLS_CACHE.get(tableName);
if (cached != null) return cached;
final String sql =
"SELECT column_name FROM information_schema.columns " +
" WHERE table_schema = 'public' AND table_name = ? " +
"   AND column_name <> '" + ID_COLUMN + "' " +
" ORDER BY ordinal_position";
List<String> out = new ArrayList<>();
try (Connection conn = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = conn.prepareStatement(sql)) {
ps.setString(1, tableName);
try (ResultSet rs = ps.executeQuery()) {
while (rs.next()) out.add(rs.getString(1));
}
} catch (SQLException e) {
e.printStackTrace();
}
NON_ID_COLS_CACHE.put(tableName, out);
return out;
}


public static String fromClause(String tableName) {
if (useRealCombiId(tableName)) {
return "public.\"" + tableName + "\"";
}


String colList = nonCombiIdColumns(tableName).stream()
.map(c -> "t.\"" + c + "\"")
.collect(Collectors.joining(", "));
String sep = colList.isEmpty() ? "" : ", ";
return "(SELECT row_number() OVER (ORDER BY t.ctid)::bigint AS " + ID_COLUMN +
sep + colList +
" FROM public.\"" + tableName + "\" t) AS \"" + tableName + "\"";
}


public static String rangeQuery(String tableName, long low, long high) {
return "SELECT * FROM " + fromClause(tableName) +
" WHERE " + ID_COLUMN + " BETWEEN " + low + " AND " + high +
" ORDER BY " + ID_COLUMN + " ASC;";
}


public static String fullOrderedQuery(String tableName) {
return "SELECT * FROM " + fromClause(tableName) + " ORDER BY " + ID_COLUMN + " ASC;";
}


public static int totalColumnCount(String tableName) throws SQLException {
final String sql =
"SELECT count(column_name) FROM information_schema.columns " +
" WHERE table_schema = 'public' AND table_name = ?";
try (Connection conn = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = conn.prepareStatement(sql)) {
ps.setString(1, tableName);
try (ResultSet rs = ps.executeQuery()) {
int physical = rs.next() ? rs.getInt(1) : 0;
if (useRealCombiId(tableName)) return physical;
return hasCombiId(tableName) ? physical : physical + 1;
}
}
}


public static long effectiveMaxId(String tableName) throws SQLException {
final String sql;
if (useRealCombiId(tableName)) {
sql = "SELECT COALESCE(MAX(" + ID_COLUMN + "), 0) FROM public.\"" + tableName + "\"";
} else {
sql = "SELECT COUNT(*) FROM public.\"" + tableName + "\"";
}
try (Connection conn = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = conn.prepareStatement(sql);
ResultSet rs = ps.executeQuery()) {
return rs.next() ? rs.getLong(1) : 0L;
}
}


public static long maxOrCount(String tableName) throws SQLException {
return effectiveMaxId(tableName);
}
}
