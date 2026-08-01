package com.company.helpers;

import java.util.LinkedHashMap;
import java.util.Map;


@FunctionalInterface
public interface LabeledRowConsumer {
void onRow(long id, LinkedHashMap<Integer, short[]> cols, Map<Integer, String> labels) throws Exception;
}
