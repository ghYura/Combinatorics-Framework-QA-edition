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

package com.company.db;

import com.company.config.AppConfig;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
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




/**
 * Provisions the configured named tablespaces — where that is actually possible.
 *
 * <p>{@code CREATE TABLESPACE} needs the directory to exist on the <b>PostgreSQL
 * server's</b> filesystem, and PostgreSQL rejects relative {@code LOCATION} paths
 * outright. Historically this method passed the configured path through verbatim
 * (relative paths → permanent {@code tablespace location must be an absolute path})
 * and created the directory in the <i>client</i> process only — with a containerised
 * or remote server the directory was invisible to it. Both errors were swallowed,
 * so every table silently landed on {@code pg_default} while the log claimed success.
 *
 * <p>Now: nothing requested → nothing done (the canonical configuration requests
 * nothing). Requested → the path is resolved to an absolute one, created client-side
 * best-effort, and the server is asked via {@code pg_stat_file()} whether it can see
 * the directory — the exact precondition {@code CREATE TABLESPACE} has. If the server
 * cannot see it (containerised/remote server without a shared filesystem), this
 * method <b>fails closed</b> with a specific message instead of warning and carrying
 * on onto {@code pg_default}.
 */
public void provisionTablespaces(DbClient pgAdminClient) {
if (tbl.tablespace2Path.isEmpty() && tbl.database2Tablespace.isEmpty()) {
log.info("Tablespace provisioning: nothing requested — tables use the database default tablespace");
return;
}
tbl.tablespace2Path.forEach((name, path) -> {
String absPath = Path.of(path.trim()).toAbsolutePath().normalize().toString();
ensureDirectoryOnClient(absPath);
requireServerVisibleDirectory(pgAdminClient, name.trim(), absPath);
// Re-running against an existing cluster is normal; a tablespace that is
// already there (42710) is the desired end state. Anything else throws.
pgAdminClient.executeTolerateAlreadyExists(
"CREATE TABLESPACE \"" + name.trim() + "\" LOCATION '" + absPath.replace("'", "''") + "';");
log.info("Tablespace '{}' provisioned at {}", name.trim(), absPath);
});
alterTablespaceParams(pgAdminClient, tbl.extendedDiskTablespace, tbl.extendedDiskParams);
alterTablespaceParams(pgAdminClient, tbl.fastDiskTablespace,     tbl.fastDiskParams);
tbl.database2Tablespace.forEach((dbName, tsName) ->
// Same rerun tolerance (42P04); a missing tablespace or any other
// failure must abort, not leave the database silently uncreated.
pgAdminClient.executeTolerateAlreadyExists(
"CREATE DATABASE \"" + dbName.trim()
+ "\" OWNER DEFAULT TABLESPACE \"" + tsName.trim() + "\";"));
}


private static void alterTablespaceParams(DbClient pgAdminClient, String name, String params) {
// Historically ran unconditionally: an absent property rendered as
// ALTER TABLESPACE "null" SET (null) and the failure was swallowed.
if (name == null || name.isBlank() || params == null || params.isBlank()) return;
// Strict: the named tablespace exists (pg_default or just provisioned);
// a failure to apply requested params is a real misconfiguration.
pgAdminClient.executeOrThrow(
"ALTER TABLESPACE \"" + name.trim() + "\" SET (" + params.trim() + ");");
}


/** Client-side directory creation covers the supported shared-filesystem
 * topology. Best-effort by design: a remote server may see a path this
 * process cannot create, and {@link #requireServerVisibleDirectory} is the
 * authority on whether provisioning may proceed. */
private static void ensureDirectoryOnClient(String absPath) {
try {
Path dir = Path.of(absPath);
if (!Files.isDirectory(dir)) {
Files.createDirectories(dir);
log.info("Created directory: {}", dir);
}
} catch (Exception e) {
log.debug("Could not create '{}' from this process ({}); the PostgreSQL server may still see it",
absPath, e.getMessage());
}
}


/** Asks the server itself whether it can see a directory at {@code absPath} —
 * the precise precondition of {@code CREATE TABLESPACE}. Fails closed when it
 * cannot: continuing would silently place every table on pg_default. */
private static void requireServerVisibleDirectory(DbClient pgAdminClient, String name, String absPath) {
String visible = pgAdminClient.queryString(
"SELECT COALESCE(((pg_stat_file('" + absPath.replace("'", "''")
+ "', true)).isdir)::text, 'missing');");
if (!"true".equals(visible)) {
throw new IllegalStateException(
"Tablespace '" + name + "' cannot be provisioned: the PostgreSQL server does not see a directory at '"
+ absPath + "' (server probe reports " + (visible == null ? "an error" : "'" + visible + "'") + "). "
+ "A containerised or remote server has its own filesystem, so a directory created on this machine is "
+ "invisible to it. Refusing to continue — the run would silently place every table on pg_default "
+ "instead of the requested tablespace. Either run against a PostgreSQL server that shares this "
+ "machine's filesystem, or remove the db.tablespace2pathMappingCSVList / "
+ "db.database2tablespaceMappingCSVList configuration.");
}
}




public void initStaticSchema() {
String ddl = loadSqlResource("schema-init.sql");
// Strict: the script is self-idempotent (every CREATE is preceded by
// DROP TABLE IF EXISTS), so any failure means the static schema is
// broken and no later stage can be trusted. Multi-statement script —
// executeOrThrow is Statement-based and runs it as one batch.
db.executeOrThrow(ddl);
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


}
