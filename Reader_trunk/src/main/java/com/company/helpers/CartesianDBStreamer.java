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

import java.sql.*;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;


public final class CartesianDBStreamer {
private CartesianDBStreamer() {}

public interface CartesianConsumer {
void onRow(long finalId, long optId, LinkedHashMap<Integer, short[]> cols, Map<Integer, String> labels) throws Exception;
}

public static void streamFinalOptProductCrossJoin(
String finalTable,
long finalLow, long finalHigh,
String optTable,
long optLow, long optHigh,
int fetchSize,
CartesianConsumer consumer
) throws SQLException {




final String finalSide = TableSchemaInspector.fromClause(finalTable);
final String optSide   = TableSchemaInspector.fromClause(optTable);

final String sql =
"SELECT f.*, o.* " +
"FROM " + finalSide + " f " +
"CROSS JOIN " + optSide + " o " +
"WHERE f.combi_id BETWEEN " + finalLow + " AND " + finalHigh + " " +
"AND o.combi_id BETWEEN " + optLow + " AND " + optHigh + " " +
"ORDER BY f.combi_id ASC, o.combi_id ASC;";

try (Connection conn = DataBaseManager2.getInstance().getConnection();
PreparedStatement pStmt = conn.prepareStatement(
sql,
ResultSet.TYPE_FORWARD_ONLY,
ResultSet.CONCUR_READ_ONLY,
ResultSet.FETCH_FORWARD)) {

pStmt.setFetchSize(fetchSize <= 0 ? 1000 : fetchSize);

try (ResultSet rs = pStmt.executeQuery()) {
ResultSetMetaData md = rs.getMetaData();
int colCount = md.getColumnCount();


Map<Integer, String> labels = new TreeMap<>();
while (rs.next()) {
long finalId = -1L;
long optId = -1L;
LinkedHashMap<Integer, short[]> arrays = new LinkedHashMap<>();
int outIdx = 2;

for (int i = 1; i <= colCount; i++) {

Array arr = null;
try {
arr = rs.getArray(i);
} catch (SQLException _) {}

if (arr != null) {
Object a = arr.getArray();
if (a instanceof short[] sa) {
arrays.put(outIdx, sa);

if (!labels.containsKey(outIdx)) {
labels.put(outIdx, md.getColumnLabel(i));
}
outIdx++;
} else {

}
} else {


if (finalId < 0) {
finalId = safeGetLong(rs, i);
} else if (optId < 0) {
optId = safeGetLong(rs, i);
} else {

}
}
}

if (finalId < 0 || optId < 0) {
throw new SQLException("Failed to detect both IDs in CROSS JOIN row");
}

try {
consumer.onRow(finalId, optId, arrays, labels);
} catch (Exception ex) {
throw new SQLException("Cartesian consumer failed for finalId=" + finalId + ", optId=" + optId, ex);
}
}
}
}
}

private static long safeGetLong(ResultSet rs, int idx) {
try {
return rs.getLong(idx);
} catch (SQLException e) {

try {
String s = rs.getString(idx);
if (s == null) return -1L;
return Long.parseLong(s.trim());
} catch (Exception _) {
return -1L;
}
}
}
}
