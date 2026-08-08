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
