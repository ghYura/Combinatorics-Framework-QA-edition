


















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

public void executeSilently(String sql) {
try (Connection conn = pool.getConnection();
Statement  st   = conn.createStatement()) {
st.setFetchSize(50);
st.execute(sql);
} catch (Exception e) {
log.warn("executeSilently: {}", e.getMessage());
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
