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

package com.company.helpers;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;


public final class CtidPartitioner {

private CtidPartitioner() {}

public record Range(long blockLow, long blockHigh) {}


public static long heapPageCount(String tableName) throws SQLException {
final String sql = "SELECT (pg_relation_size('public.\"" + tableName + "\"') / 8192)::bigint";
try (Connection c = DataBaseManager2.getInstance().getConnection();
PreparedStatement ps = c.prepareStatement(sql);
ResultSet rs = ps.executeQuery()) {
return rs.next() ? Math.max(0L, rs.getLong(1)) : 0L;
}
}


public static List<Range> partition(String tableName, int n) throws SQLException {
if (n <= 1) return List.of(new Range(0L, Long.MAX_VALUE));
long pages = heapPageCount(tableName);
if (pages <= 0L) return List.of(new Range(0L, Long.MAX_VALUE));
long step = Math.max(1L, pages / n);
List<Range> out = new ArrayList<>(n);
long lo = 0L;
for (int i = 0; i < n; i++) {
long hi = (i == n - 1) ? Long.MAX_VALUE : lo + step;
if (hi <= lo) continue;
out.add(new Range(lo, hi));
lo = hi;
}
if (out.isEmpty()) out.add(new Range(0L, Long.MAX_VALUE));
return out;
}


public static String partitionedVirtualQuery(String tableName, Range r) {



String colList = TableSchemaInspector.nonCombiIdColumns(tableName).stream()
.map(c -> "t.\"" + c + "\"")
.collect(Collectors.joining(", "));
String sep = colList.isEmpty() ? "" : ", ";
StringBuilder sb = new StringBuilder();
sb.append("(SELECT row_number() OVER (ORDER BY t.ctid)::bigint AS combi_id")
.append(sep).append(colList)
.append(" FROM public.\"").append(tableName).append("\" t")
.append(" WHERE t.ctid >= '(").append(r.blockLow()).append(",0)'::tid");
if (r.blockHigh() != Long.MAX_VALUE) {
sb.append(" AND t.ctid < '(").append(r.blockHigh()).append(",0)'::tid");
}
sb.append(") AS \"").append(tableName).append("\"");
return "SELECT * FROM " + sb + " ORDER BY combi_id ASC;";
}
}
