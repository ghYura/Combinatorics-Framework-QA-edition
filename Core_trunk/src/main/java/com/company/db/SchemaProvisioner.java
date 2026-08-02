package com.company.db;

import com.company.config.AppConfig;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;


public final class SchemaProvisioner {

private static final Logger log = LogManager.getLogger(SchemaProvisioner.class);

private final DbClient            db;
private final AppConfig.TablespaceConfig tbl;

public SchemaProvisioner(DbClient db, AppConfig.TablespaceConfig tbl) {
this.db  = db;
this.tbl = tbl;
}




public void provisionTablespaces(DbClient pgAdminClient) {
tbl.tablespace2Path.forEach((name, path) -> {
createDirectoryPath(path);
pgAdminClient.executeSilently(
"CREATE TABLESPACE \"" + name.trim() + "\" LOCATION '" + path.trim() + "';");
});
pgAdminClient.executeSilently(
"ALTER TABLESPACE \"" + tbl.extendedDiskTablespace
+ "\" SET (" + tbl.extendedDiskParams + ");");
pgAdminClient.executeSilently(
"ALTER TABLESPACE \"" + tbl.fastDiskTablespace
+ "\" SET (" + tbl.fastDiskParams + ");");
tbl.database2Tablespace.forEach((dbName, tsName) ->
pgAdminClient.executeSilently(
"CREATE DATABASE \"" + dbName.trim()
+ "\" OWNER DEFAULT TABLESPACE \"" + tsName.trim() + "\";"));
}




public void initStaticSchema() {
String ddl = loadSqlResource("schema-init.sql");
db.executeSilently(ddl);
log.info("Static schema initialised from schema-init.sql");
}




public void createFwTable(short key) throws SQLException {
String ddl = loadTemplate("create-fw-table.sql.template")
.replace("${KEY}",        String.valueOf(key))
.replace("${TABLESPACE}", tbl.fastDiskTablespace);
db.execute(ddl);
log.debug("Created fw_" + key);
}


public void createFw2Table(short key, String combosDataType) throws SQLException {
String ddl = loadTemplate("create-fw2-table.sql.template")
.replace("${KEY}",         String.valueOf(key))
.replace("${TABLESPACE}",  tbl.fastDiskTablespace)
.replace("${COMBOS_TYPE}", combosDataType);
db.execute(ddl);
log.debug("Created fw2_" + key);
}


public void createFinalTable(String tableNameSuffix,
Map<Short, String> sheetColumns,
String combosDataType,
String pkSuffix) throws SQLException {
createTableFromTemplate("fw_final", tableNameSuffix, sheetColumns, combosDataType, pkSuffix);
}


public void createOptTable(int optIndex,
Map<Short, String> sheetColumns,
String combosDataType) throws SQLException {
createTableFromTemplate("fw_opt", String.valueOf(optIndex), sheetColumns, combosDataType, "_pkey");
}


private void createTableFromTemplate(String baseName, String suffix,
Map<Short, String> sheetColumns,
String combosDataType,
String pkSuffix) throws SQLException {
String columns = sheetColumns.entrySet().stream()
.map(e -> "    \"combos" + e.getKey() + "_" + e.getValue()
+ "\" " + combosDataType + ",")
.collect(Collectors.joining("\n"));

String ddl = loadTemplate("create-final-table.sql.template")
.replace("${BASE_NAME}",  baseName)
.replace("${SUFFIX}",     suffix)
.replace("${COLUMNS}",    columns)
.replace("${TABLESPACE}", tbl.fastDiskTablespace)
.replace("${PK_SUFFIX}",  pkSuffix);
log.debug("createTableFromTemplate DDL for '{}{}':\n{}", baseName, suffix, ddl);
db.execute(ddl);
log.info("Created {}{}", baseName, suffix);
}




private String loadSqlResource(String filename) {
return loadResource("/sql/" + filename);
}


private String loadTemplate(String filename) {
return loadResource("/sql/" + filename);
}

private String loadResource(String path) {
try (InputStream in = SchemaProvisioner.class.getResourceAsStream(path)) {
if (in == null) {
throw new IllegalStateException("SQL resource not found on classpath: " + path);
}
return new String(in.readAllBytes(), StandardCharsets.UTF_8);
} catch (IOException e) {
throw new UncheckedIOException("Failed to load SQL resource: " + path, e);
}
}


private static void createDirectoryPath(String dirPathStr) {
String[] parts = dirPathStr.trim().split("[/\\\\]");
var current = new StringBuilder(parts[0]);
for (int i = 1; i < parts.length; i++) {
current.append(File.separator).append(parts[i]);
var dir = new File(current.toString().trim());
if (dir.mkdir()) {
log.info("Created directory: " + dir.getAbsolutePath());
} else if (!dir.exists()) {
log.warn("Failed to create directory: " + dir.getAbsolutePath());
}
}
}
}
