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

import com.gc.iotools.stream.os.OutputStreamToInputStream;
import com.mchange.v2.c3p0.ComboPooledDataSource;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

import java.beans.PropertyVetoException;
import java.io.IOException;
import java.io.InputStream;
import java.sql.*;

import static com.company.MainWatch.*;

public class DataBaseManager {

private ComboPooledDataSource cpds;

private static final Integer MINIMUM_POOL_SIZE = 3;
private static final Integer MAXIMUM_POOL_SIZE = 10;
private static final Integer INCREMENT_SIZE = 1;
private static final Integer MAX_STATEMENTS = 0;






private static final String DB_HOST = DB_HOST_properties;
private static final String DB_PORT = String.valueOf(DB_PORT_properties);
private static final String DB_USER = DB_USER_properties;
private static final String DB_PASS = DB_PASSWORD_properties;
private static final String DB_NAME = DB_NAME_properties;
private static final String URL_TABLE = "url";

public static String DB_URL = null;



private static volatile DataBaseManager dbInstance = null;

private DataBaseManager() {
cpds = new ComboPooledDataSource();
try {
cpds.setDriverClass("org.postgresql.Driver");
} catch (PropertyVetoException e) {
e.printStackTrace();
}
if (DB_URL == null) {
cpds.setJdbcUrl("jdbc:postgresql://" + DB_HOST + ":" + DB_PORT + "/" + DB_NAME);
cpds.setUser(DB_USER);
cpds.setPassword(DB_PASS);
} else {applyUrlWithoutCredentials(cpds, DB_URL);}

cpds.setMinPoolSize(MINIMUM_POOL_SIZE);
cpds.setAcquireIncrement(INCREMENT_SIZE);
cpds.setMaxPoolSize(MAXIMUM_POOL_SIZE);
cpds.setMaxStatements(MAX_STATEMENTS);
cpds.setAutoCommitOnClose(false);

}


public void init(){
cpds = new ComboPooledDataSource();
try {
cpds.setDriverClass("org.postgresql.Driver");
} catch (PropertyVetoException e) {
e.printStackTrace();
}
if (DB_URL == null) {
cpds.setJdbcUrl("jdbc:postgresql://" + DB_HOST + ":" + DB_PORT + "/" + DB_NAME);
cpds.setUser(DB_USER);
cpds.setPassword(DB_PASS);
} else {applyUrlWithoutCredentials(cpds, DB_URL);}

cpds.setMinPoolSize(MINIMUM_POOL_SIZE);
cpds.setAcquireIncrement(INCREMENT_SIZE);
cpds.setMaxPoolSize(MAXIMUM_POOL_SIZE);
cpds.setMaxStatements(MAX_STATEMENTS);
cpds.setAutoCommitOnClose(false);

}

/**
 * Point the pool at {@code url}, moving any {@code user}/{@code password} out of
 * the query string and into the pool's own properties.
 *
 * c3p0 dumps every property of {@link ComboPooledDataSource} at INFO on the first
 * checkout, including {@code jdbcUrl} verbatim. When the handshake URL carried
 * {@code ?user=...&password=...}, that dump wrote the database password to the
 * console and into the run's executor.log. c3p0 masks {@code password} itself, so
 * the credentials survive here but stop appearing in logs.
 */
private static void applyUrlWithoutCredentials(ComboPooledDataSource pool, String url) {
int q = url.indexOf('?');
if (q < 0) {
pool.setJdbcUrl(url);
return;
}
String user = null;
String password = null;
StringBuilder keep = new StringBuilder();
for (String param : url.substring(q + 1).split("&")) {
if (param.isEmpty()) continue;
int eq = param.indexOf('=');
String key = eq < 0 ? param : param.substring(0, eq);
String value = eq < 0 ? "" : param.substring(eq + 1);
if ("user".equals(key)) {
user = decodeParam(value);
} else if ("password".equals(key)) {
password = decodeParam(value);
} else {
if (keep.length() > 0) keep.append('&');
keep.append(param);
}
}
pool.setJdbcUrl(keep.length() > 0 ? url.substring(0, q) + "?" + keep : url.substring(0, q));
if (user != null) pool.setUser(user);
if (password != null) pool.setPassword(password);
}

/**
 * Decode one query-string value the way pgjdbc would, so moving a parameter out of
 * the URL does not change its value. A value that is not valid percent-encoding is
 * passed through unchanged rather than throwing.
 */
private static String decodeParam(String value) {
try {
return java.net.URLDecoder.decode(value, java.nio.charset.StandardCharsets.UTF_8);
} catch (IllegalArgumentException e) {
return value;
}
}

public static DataBaseManager getInstance() {
if (dbInstance == null) {
synchronized (DataBaseManager.class) {
if (dbInstance == null) {
dbInstance = new DataBaseManager();
}
}
}
return dbInstance;
}

public Connection getConnection() throws SQLException {

return this.cpds.getConnection();
}

public boolean disconnect(){
cpds.close();
dbInstance = null;
System.gc();
return false;
}
public boolean disconnectSimple(){
cpds.close();
return false;
}

public boolean connect(){
init();
return true;
}

public long queryGetCountAll(String sql){
long res = 0L;
ResultSet rs = null;
Statement st = null;
Connection conn = null;
try {
conn = DataBaseManager.getInstance().getConnection();
st = conn.createStatement();
rs = st.executeQuery(sql);


while (rs.next()) {


res = rs.getLong(1);
}

rs.close();

st.close();
conn.close();
} catch (SQLException e) {
e.printStackTrace();
} finally {
try {
rs.close();
st.close();
conn.close();
} catch (Exception e){
e.printStackTrace();
}
}
return res;
}

public synchronized void execAndForget(String sql) throws SQLException {
Connection connection = null;
PreparedStatement pstmt = null;
ResultSet resultSet = null;
try {

connection = DataBaseManager.getInstance().getConnection();
pstmt = connection.prepareStatement(sql);

pstmt.execute();



connection.close();
}
catch (Exception e) {
connection.close();
e.printStackTrace();
} finally {
if (pstmt != null) pstmt.close();
if (resultSet != null) resultSet.close();
if (connection != null) connection.close();
}

}

public  void writeData(StringBuilder strToCopy, final String tableName, final String commaSepFields) {

Connection connection = null;
Statement statement = null;
PreparedStatement preparedStatement = null;
CopyManager copyAPI;




try {
connection = DataBaseManager.getInstance().getConnection();


final Connection finalConnection = connection;
OutputStreamToInputStream oStream2IStream = new OutputStreamToInputStream(false) {

protected  String doRead(final InputStream istream) throws Exception {


final String url = "jdbc:postgresql://"+DB_HOST+":"+DB_PORT+"/"+DB_NAME;
final String user = DB_USER;
final String password = DB_PASS;
final String sql = "COPY public." + tableName + " (" + commaSepFields + ") FROM STDIN";
try {


final long cp = finalConnection.unwrap(PGConnection.class).getCopyAPI().copyIn(sql, istream);












} catch (SQLException sqe){
sqe.printStackTrace();
}



return null;
}
};
try {

try {
oStream2IStream.write(strToCopy.toString().getBytes());

oStream2IStream.close();

connection.close();
} catch (IOException e) {
e.printStackTrace();
}
} finally {

try {
oStream2IStream.close();

connection.close();
} catch (IOException e) {
e.printStackTrace();
}
}











} catch (SQLException e) {
e.printStackTrace();
} finally {
try {


connection.close();
} catch (SQLException e) {
e.printStackTrace();
}
}

}


}
