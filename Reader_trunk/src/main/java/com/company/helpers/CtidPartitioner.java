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
