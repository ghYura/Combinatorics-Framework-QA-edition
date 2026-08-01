package com.company.utils;

import com.company.PrintPretty;
import com.company.helpers.CodeLineNumber;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.hibernate.resource.jdbc.spi.StatementInspector;


@Deprecated
public class CustomInterceptor implements StatementInspector {

private static final Logger log = LogManager.getLogger(CustomInterceptor.class);

@Override
public String inspect(String sql) {
String tableName = CustomInterceptor2.CURRENT_TABLE.get();


log.debug("[{}] Before SQL rewrite: {}", CodeLineNumber.getLineNumber(), sql);

sql = sql.replaceAll("[Ff]{1}[Ww]{1}[_]{0,1}[\\d]{0,}", tableName);


log.debug("[{}] After SQL rewrite:  {}", CodeLineNumber.getLineNumber(), sql);

return sql;
}
}
