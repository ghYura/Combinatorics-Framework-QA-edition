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
} else {cpds.setJdbcUrl(DB_URL);}

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
} else {cpds.setJdbcUrl(DB_URL);}

cpds.setMinPoolSize(MINIMUM_POOL_SIZE);
cpds.setAcquireIncrement(INCREMENT_SIZE);
cpds.setMaxPoolSize(MAXIMUM_POOL_SIZE);
cpds.setMaxStatements(MAX_STATEMENTS);
cpds.setAutoCommitOnClose(false);

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
