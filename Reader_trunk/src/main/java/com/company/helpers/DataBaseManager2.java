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

package com.company.helpers;
import com.company.ReaderConfig;

import com.company.PrintPretty;
import com.company.excel.Numerator;
import com.gc.iotools.stream.os.OutputStreamToInputStream;
import com.mchange.v2.c3p0.ComboPooledDataSource;
import org.postgresql.PGConnection;

import java.beans.PropertyVetoException;
import java.io.IOException;
import java.io.InputStream;
import java.sql.*;
import java.util.*;
import java.util.concurrent.Executors;

import static com.company.Main.*;
import static com.company.ReaderConfig.*;

public class DataBaseManager2 extends Observable {

private ComboPooledDataSource cpds;

private static final Integer MINIMUM_POOL_SIZE = 5;
private static final Integer MAXIMUM_POOL_SIZE = 900;
private static final Integer INCREMENT_SIZE = 5;
private static final Integer MAX_STATEMENTS = 0;

private String DB_HOST = cfg().dbHost();
private int DB_PORT = cfg().dbPort();
private String DB_USER = cfg().dbUser();
private String DB_PASS = cfg().dbPassword();
private String DB_NAME = cfg().dbName();
private String URL_TABLE = "url";

private static volatile DataBaseManager2 dbInstance = null;


private static final java.util.concurrent.ExecutorService NETWORK_TIMEOUT_EXECUTOR =
java.util.concurrent.Executors.newSingleThreadExecutor(r -> {
Thread t = new Thread(r, "db-netto");
t.setDaemon(true);
return t;
});

private static String jdbcUrl(String host, int port, String db) {




String base = "jdbc:postgresql://" + host + ":" + port + "/" + db;
String params = "reWriteBatchedInserts=true&preferQueryMode=simple&tcpKeepAlive=true";
return base + "?" + params;
}

private DataBaseManager2() {
cpds = new ComboPooledDataSource();
try {
cpds.setDriverClass("org.postgresql.Driver");
} catch (PropertyVetoException e) {
e.printStackTrace();
}
cpds.setJdbcUrl(jdbcUrl(getDB_HOST(), getDB_PORT(), getDB_NAME()));
cpds.setUser(getDB_USER());
cpds.setPassword(getDB_PASS());

cpds.setMinPoolSize(MINIMUM_POOL_SIZE);
cpds.setAcquireIncrement(INCREMENT_SIZE);
cpds.setMaxPoolSize(MAXIMUM_POOL_SIZE);
cpds.setMaxStatements(MAX_STATEMENTS);
cpds.setAutoCommitOnClose(true);


cpds.setCheckoutTimeout(60_000);
cpds.setMaxIdleTime(300);
cpds.setIdleConnectionTestPeriod(120);
cpds.setTestConnectionOnCheckout(false);
cpds.setTestConnectionOnCheckin(false);
}

public DataBaseManager2(String DB_HOST, int DB_PORT, String DB_NAME) {
this.setDB_HOST(DB_HOST);
this.setDB_PORT(DB_PORT);
this.setDB_NAME(DB_NAME);
cpds = new ComboPooledDataSource();
try {
cpds.setDriverClass("org.postgresql.Driver");
} catch (PropertyVetoException e) {
e.printStackTrace();
}
cpds.setJdbcUrl(jdbcUrl(DB_HOST, DB_PORT, DB_NAME));
cpds.setUser(getDB_USER());
cpds.setPassword(getDB_PASS());

cpds.setMinPoolSize(MINIMUM_POOL_SIZE);
cpds.setAcquireIncrement(INCREMENT_SIZE);
cpds.setMaxPoolSize(MAXIMUM_POOL_SIZE);
cpds.setMaxStatements(MAX_STATEMENTS);
cpds.setAutoCommitOnClose(true);

cpds.setCheckoutTimeout(60_000);
cpds.setMaxIdleTime(300);
cpds.setIdleConnectionTestPeriod(120);
cpds.setTestConnectionOnCheckout(false);
cpds.setTestConnectionOnCheckin(false);
}

public static DataBaseManager2 getInstance() {
if (dbInstance == null) {
synchronized (DataBaseManager2.class) {
if (dbInstance == null) {
dbInstance = new DataBaseManager2();
}
}
}
return dbInstance;
}

public Connection getConnection() throws SQLException {
Connection c = this.cpds.getConnection();

try {
c.setAutoCommit(false);
c.setReadOnly(true);


c.setNetworkTimeout(NETWORK_TIMEOUT_EXECUTOR, 120_000);
} catch (Throwable _) {}
return c;
}

public long queryGetCountAll(String sql){
long res = 0L;
try (Connection conn = DataBaseManager2.getInstance().getConnection();
Statement st = conn.createStatement();
ResultSet rs = st.executeQuery(sql)) {

while (rs.next()) {
res = rs.getLong(1);
}
} catch (SQLException e) {
e.printStackTrace();
}
return res;
}

public boolean disconnect(){
cpds.close();
dbInstance = null;
System.gc();
return false;
}

public void execAndForget(String sql) throws SQLException {
try (Connection connection = this.getConnection();
PreparedStatement pstmt = connection.prepareStatement(sql)) {
pstmt.execute();
setChanged();
notifyObservers(this);
}
}

public void writeData(StringBuilder strToCopy, final String tableName, final String commaSepFields) {
try (Connection connection = DataBaseManager2.getInstance().getConnection()) {
final Connection finalConnection = connection;
OutputStreamToInputStream oStream2IStream = new OutputStreamToInputStream(false) {
protected String doRead(final InputStream istream) throws Exception {
final String sql = "COPY public." + tableName + " (" + commaSepFields + ") FROM STDIN";
try {
finalConnection.unwrap(PGConnection.class).getCopyAPI().copyIn(sql, istream);
} catch (SQLException sqe){
sqe.printStackTrace();
}
return null;
}
};
try {
oStream2IStream.write(strToCopy.toString().getBytes());
oStream2IStream.close();
} catch (IOException e) {
e.printStackTrace();
} finally {
try { oStream2IStream.close(); } catch (IOException _) {}
}
} catch (SQLException e) {
e.printStackTrace();
}
}

public void execAndForget0(String sql) throws SQLException {
try (Connection connection = this.getConnection();
PreparedStatement pstmt = connection.prepareStatement(sql)) {
pstmt.execute();
}
}


public LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> resultAsMapMap2(String originalQuery, int numOfColumnsIn_fw_final_base_copy_Total, int fetchCount) throws SQLException {
return CopyToReader.loadAsMapMap(originalQuery);
}

public String getDB_HOST() { return DB_HOST; }
public int getDB_PORT() { return DB_PORT; }
public String getDB_USER() { return DB_USER; }
public String getDB_PASS() { return DB_PASS; }
public String getDB_NAME() { return DB_NAME; }
public String getURL_TABLE() { return URL_TABLE; }

public void setDB_HOST(String DB_HOST) { this.DB_HOST = DB_HOST; }
public void setDB_PORT(int DB_PORT) { this.DB_PORT = DB_PORT; }
public void setDB_NAME(String DB_NAME) { this.DB_NAME = DB_NAME; }

public void setDB_USER(String dbUser) {
this.DB_USER = dbUser;
}

public void setDB_PASS(String dbPass) {
this.DB_PASS = dbPass;
}
}
