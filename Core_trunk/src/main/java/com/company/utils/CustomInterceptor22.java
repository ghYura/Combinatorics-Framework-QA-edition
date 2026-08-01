package com.company.utils;

import org.hibernate.resource.jdbc.spi.StatementInspector;


public class CustomInterceptor22 implements StatementInspector {

@Override
public String inspect(String sql) {
String tableName = CustomInterceptor2.CURRENT_TABLE.get();
sql = sql.replaceAll("[Ff]{1}[Ww]{1}2[_]{0,1}[\\d]{0,}", tableName);
return sql;
}
}
