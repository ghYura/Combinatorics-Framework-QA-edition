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
// Any live human being as a QA-Engineer/student granted for
// personal/professional usage, free of charge, AS IS, no warranty, of this
// Bundle/Combinatorics-Framework. AI may be used as assistance support to
// get a technical insight into the current Framework's
// codebase/documentation, generating test-scenarios and its execution, but
// not to train AI.
//
// (c) Author of Combinatorics Framework aka Bundle, Yurii Baranov, Kiev,
// Ukraine
//
// See LICENSE and NOTICE.md for the binding terms.














package com.company.db;

import com.company.config.AppConfig;
import com.mchange.v2.c3p0.ComboPooledDataSource;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

import java.beans.PropertyVetoException;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;


public final class DbClient implements AutoCloseable {

private static final Logger log = LogManager.getLogger(DbClient.class);

private static final int DEFAULT_MIN_POOL  = 2;
private static final int DEFAULT_MAX_POOL  = 3;
private static final int DEFAULT_INCREMENT = 1;
private static final int DEFAULT_MAX_STMTS = 0;
private static final int DEFAULT_MAX_CONCURRENT_COPIES = 4;

private final ComboPooledDataSource pool;


private final Semaphore copyGate;



public static DbClient create(AppConfig.DbConfig cfg) {
return new DbClient(cfg, cfg.name, null);
}

public static DbClient create(AppConfig.DbConfig cfg, AppConfig.PoolConfig poolCfg) {
return new DbClient(cfg, cfg.name, poolCfg);
}

public static DbClient createForDb(AppConfig.DbConfig cfg, String dbName) {
return new DbClient(cfg, dbName, null);
}

public static DbClient createForDb(AppConfig.DbConfig cfg, String dbName,
AppConfig.PoolConfig poolCfg) {
return new DbClient(cfg, dbName, poolCfg);
}

private DbClient(AppConfig.DbConfig cfg, String dbName, AppConfig.PoolConfig poolCfg) {
int minPool  = poolCfg != null ? poolCfg.minSize         : DEFAULT_MIN_POOL;
int maxPool  = poolCfg != null ? poolCfg.maxSize         : DEFAULT_MAX_POOL;
int incr     = poolCfg != null ? poolCfg.acquireIncrement : DEFAULT_INCREMENT;
int maxStmts = poolCfg != null ? poolCfg.maxStatements   : DEFAULT_MAX_STMTS;
int maxCopy  = poolCfg != null ? poolCfg.maxConcurrentCopies : DEFAULT_MAX_CONCURRENT_COPIES;

var cpds = new ComboPooledDataSource();
try {
cpds.setDriverClass("org.postgresql.Driver");
} catch (PropertyVetoException e) {
throw new RuntimeException("Cannot load PostgreSQL driver", e);
}
cpds.setJdbcUrl("jdbc:postgresql://" + cfg.host + ":" + cfg.port + "/" + dbName);
cpds.setUser(cfg.user);
cpds.setPassword(cfg.passwordAsString());
cpds.setMinPoolSize(minPool);
cpds.setAcquireIncrement(incr);
cpds.setMaxPoolSize(maxPool);
cpds.setMaxStatements(maxStmts);
cpds.setAutoCommitOnClose(true);
this.pool = cpds;
this.copyGate = new Semaphore(Math.min(maxCopy, maxPool));

log.debug("DbClient created: jdbc:postgresql://{}:{}/{} pool=[{},{}] copyGate={}",
cfg.host, cfg.port, dbName, minPool, maxPool, Math.min(maxCopy, maxPool));
}



public long queryLong(String sql) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.setFetchSize(50);
try (ResultSet rs = st.executeQuery(sql)) {
return rs.next() ? rs.getLong(1) : 0L;
}
} catch (SQLException e) {
log.error("queryLong failed: {}", e.getMessage(), e);
return 0L;
}
}

/**
 * Tier-0 bug fix 0.4: quiet variant — diagnostic counts on tables that
 * may legitimately not exist yet ({@code fw2_<key>} before the second
 * verb pass, etc.).  Returns sentinel {@code -1L} on failure instead of
 * logging at ERROR level.  Caller decides what to do with the sentinel.
 */
public long queryLongQuiet(String sql) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.setFetchSize(50);
try (ResultSet rs = st.executeQuery(sql)) {
return rs.next() ? rs.getLong(1) : 0L;
}
} catch (SQLException e) {
log.debug("queryLongQuiet (expected-may-miss) failed: {}", e.getMessage());
return -1L;
}
}

public String queryString(String sql) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.setFetchSize(50);
try (ResultSet rs = st.executeQuery(sql)) {
return rs.next() ? rs.getString(1) : null;
}
} catch (SQLException e) {
log.error("queryString failed: {}", e.getMessage(), e);
return null;
}
}

public String queryStringWithFunction(String sqlCreateFunction, String sqlRunFunction) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.execute(sqlCreateFunction);
try (ResultSet rs = st.executeQuery(sqlRunFunction)) {
return rs.next() ? rs.getString(1) : null;
}
} catch (SQLException e) {
log.error("queryStringWithFunction failed: {}", e.getMessage(), e);
return null;
}
}

@SuppressWarnings("rawtypes")
public List<Object> queryArrayList(String sql) {
List<Object> result = new LinkedList<>();
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.setFetchSize(50);
try (ResultSet rs = st.executeQuery(sql)) {
while (rs.next()) {
result.add(rs.getArray(1).getArray());
}
}
} catch (SQLException e) {
log.error("queryArrayList failed: {}", e.getMessage(), e);
}
return result;
}



public void execute(String sql) throws SQLException {
try (Connection conn = pool.getConnection();
PreparedStatement pst = conn.prepareStatement(sql)) {
pst.execute();
}
}

/** PostgreSQL SQLSTATEs of the duplicate-object family — the ONLY failures
 * {@link #executeTolerateAlreadyExists} treats as benign. Grow this list only
 * with a written reason; anything not listed is a real failure and throws.
 *   42P07 duplicate_table
 *   42710 duplicate_object   (tablespaces, roles, extensions, ...)
 *   42P06 duplicate_schema
 *   42701 duplicate_column
 *   42P04 duplicate_database (reason: MainRefactored's ensure-database-exists
 *          paths race against concurrent creators; "it already exists" is the
 *          caller's desired end state there, exactly like the others). */
private static final Set<String> DUPLICATE_OBJECT_SQLSTATES =
Set.of("42P07", "42710", "42P06", "42701", "42P04");

/** Replaces executeSilently(), which caught {@code Exception}, logged one WARN
 * line and swallowed everything — connection-pool exhaustion, authentication
 * failures and constraint violations with equal serenity. Real schema failures
 * therefore surfaced (if at all) several steps later, somewhere misleading.
 *
 * <p>Statement-based on purpose: {@link #execute(String)} prepares, and the
 * PostgreSQL driver refuses multi-statement scripts in a prepared statement,
 * while several call sites (schema-init.sql, table-swap batches) are scripts.
 *
 * <p>Throws unchecked {@link DbExecutionException} (SQLSTATE + failing
 * statement in the message) rather than checked SQLException because the
 * migrated call sites never had throws-clauses; failures must propagate, not
 * force blind signature churn through every caller. Non-SQLException
 * throwables are never caught here at all — nothing about them is benign. */
public void executeOrThrow(String sql) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.execute(sql);
} catch (SQLException e) {
throw executionFailure(sql, e);
}
}

/** Like {@link #executeOrThrow}, but tolerates — silently, at DEBUG — the
 * genuine "it already exists" conditions in {@link #DUPLICATE_OBJECT_SQLSTATES}.
 * The check is on {@link SQLException#getSQLState()}, never on message text:
 * messages are localised and unstable, SQLSTATEs are contractual. Everything
 * else throws exactly like {@link #executeOrThrow}. */
public void executeTolerateAlreadyExists(String sql) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.execute(sql);
} catch (SQLException e) {
if (e.getSQLState() != null && DUPLICATE_OBJECT_SQLSTATES.contains(e.getSQLState())) {
log.debug("executeTolerateAlreadyExists: benign duplicate (SQLSTATE {}): {}",
e.getSQLState(), e.getMessage());
return;
}
throw executionFailure(sql, e);
}
}

private static DbExecutionException executionFailure(String sql, SQLException e) {
String stmt = sql != null && sql.length() > 2000
? sql.substring(0, 2000) + " …(+" + (sql.length() - 2000) + " chars)"
: sql;
return new DbExecutionException("SQL failed (SQLSTATE " + e.getSQLState() + "): "
+ e.getMessage() + " — statement: " + stmt, e);
}

/** Unchecked carrier for {@link #executeOrThrow}/{@link #executeTolerateAlreadyExists}
 * failures; message always includes the SQLSTATE and the failing statement. */
public static final class DbExecutionException extends RuntimeException {
DbExecutionException(String message, SQLException cause) {
super(message, cause);
}
}




public void copyIn(StringBuilder data, String tableName, String commaSepFields) {
if (data == null || data.isEmpty()) return;

String copySql = "COPY public." + tableName + " (" + commaSepFields + ") FROM STDIN";
byte[] bytes = data.toString().getBytes(StandardCharsets.UTF_8);

try {
copyGate.acquire();
} catch (InterruptedException e) {
Thread.currentThread().interrupt();
log.warn("copyIn interrupted while waiting for copyGate permit");
return;
}

try (Connection conn = pool.getConnection();
ByteArrayInputStream bais = new ByteArrayInputStream(bytes)) {
CopyManager cm = conn.unwrap(PGConnection.class).getCopyAPI();
long rowsCopied = cm.copyIn(copySql, bais);
log.trace("copyIn to '{}': {} rows", tableName, rowsCopied);
} catch (SQLException e) {
log.error("copyIn COPY API error for '{}': {}", tableName, e.getMessage(), e);
} catch (IOException e) {
log.error("copyIn I/O error for '{}': {}", tableName, e.getMessage(), e);
} finally {
copyGate.release();
}
}

public void copyInRow(String rowData, String tableName, String commaSepFields) {
copyIn(new StringBuilder(rowData), tableName, commaSepFields);
}


@Deprecated
public void copyInPiped(StringBuilder data, String tableName, String commaSepFields) {
ExecutorService exec = Executors.newFixedThreadPool(2);
String copySql = "COPY public." + tableName + " (" + commaSepFields + ") FROM STDIN";
try (Connection conn = pool.getConnection();
var pis = new PipedInputStream();
var pos = new PipedOutputStream(pis);
var bw = new BufferedWriter(new OutputStreamWriter(pos, StandardCharsets.UTF_8));
var br = new BufferedReader(new InputStreamReader(pis,  StandardCharsets.UTF_8))) {
Future<?> writeTask = exec.submit(() -> {
try { bw.write(data.toString()); bw.flush(); }
catch (IOException e) { throw new UncheckedIOException(e); }
return null;
});
CopyManager cm = conn.unwrap(PGConnection.class).getCopyAPI();
Future<?> copyTask = exec.submit(() -> {
try { cm.copyIn(copySql, br); }
catch (Exception e) { throw new RuntimeException(e); }
return null;
});
writeTask.get();
copyTask.get();
} catch (Exception e) {
log.error("copyInPiped to '{}' failed: {}", tableName, e.getMessage(), e);
} finally {
exec.shutdown();
}
}



@Override
public void close() {
if (pool != null) {
pool.close();
log.debug("DbClient pool closed");
}
}

public Connection getConnection() throws SQLException {
return pool.getConnection();
}
}
