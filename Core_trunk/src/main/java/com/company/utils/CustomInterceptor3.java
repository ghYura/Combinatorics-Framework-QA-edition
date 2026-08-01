package com.company.utils;

import org.hibernate.resource.jdbc.spi.StatementInspector;


public class CustomInterceptor3 implements StatementInspector {

@Override
public String inspect(String sql) {
String tableName = CustomInterceptor2.CURRENT_TABLE.get();
return "COPY public." + tableName + " FROM STDIN";
}
}
