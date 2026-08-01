package com.company.helpers;

import java.util.LinkedHashMap;


@FunctionalInterface
public interface RowConsumer {
void onRow(long id, LinkedHashMap<Integer, short[]> cols) throws Exception;
}
