package com.company.helpers;

import java.sql.SQLException;


public final class DBStreamer {
private DBStreamer() {}

public static void streamResultAsMapMap2(
String originalQuery,
int numColumns,
int fetchSize,
RowConsumer consumer
) throws SQLException {
CopyToReader.stream(originalQuery, consumer);
}

public static void streamResultAsMapMap2WithLabels(
String originalQuery,
int numColumns,
int fetchSize,
LabeledRowConsumer consumer
) throws SQLException {
CopyToReader.streamWithLabels(originalQuery, consumer);
}
}
