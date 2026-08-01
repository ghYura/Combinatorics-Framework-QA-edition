package com.company.utils;

import org.hibernate.resource.jdbc.spi.StatementInspector;


public class CustomInterceptor2 implements StatementInspector {


static final ThreadLocal<String> CURRENT_TABLE =
ThreadLocal.withInitial(() -> "fw");


public static void setCurrentTable(String tableName) {
CURRENT_TABLE.set(tableName);
}


public static void clearCurrentTable() {
CURRENT_TABLE.remove();
}

@Override
public String inspect(String sql) {
String tableName = CURRENT_TABLE.get();
sql = sql.replaceAll("[Ff]{1}[Ww]{1}[_]{0,1}[\\d]{0,}[_]{0,1}", tableName);
if (tableName.startsWith("fw2_")) {
sql = sql.replaceAll("combos", "combos_1");
}
return sql;
}
}
