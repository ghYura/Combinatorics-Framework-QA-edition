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

import java.sql.*;
import java.util.*;

import static com.company.Main.*;
import static com.company.ReaderConfig.*;

public class QueryToDB2 {
Driver driver;

{
try {
driver = new org.postgresql.Driver();
} catch (Exception e) {
e.printStackTrace();
}
}

Connection conn = null;
Statement st = null;
ResultSet rs = null;

public QueryToDB2(){

}

public void init(){



String url = "jdbc:postgresql://"+cfg().dbHost()+":"+cfg().dbPort()+"/"+cfg().dbName();
String user = cfg().dbUser();
String password = cfg().dbPassword();


try {
DriverManager.registerDriver(driver);
conn = DriverManager.getConnection(url, user, password);
conn.setAutoCommit(false);
} catch (SQLException e) {
e.printStackTrace();
if (conn != null) {
try {
conn.close();
} catch (SQLException e1) {
e1.printStackTrace();
}
}
}
}

public boolean disconnect(){
try {
if (driver != null) {

DriverManager.deregisterDriver(driver);
driver = null;
System.gc();
} else {
System.gc();
}
} catch (SQLException e) {
e.printStackTrace();
}
return false;
}

public Array queryGetArr(String sql){
if (driver == null) init();
Array res = null;
try {
st = conn.createStatement();

st.setFetchSize(50);
rs = st.executeQuery(sql);

while (rs.next()) {
PrintPretty.println(CodeLineNumber.getLineNumber() + " a row was returned in queryGetArr().");
              res =   rs.getArray(1);
}

rs.close();

st.close();
conn.close();
disconnect();
} catch (SQLException e) {
e.printStackTrace();
} finally {
try {
rs.close();
st.close();
conn.close();
disconnect();
} catch (Exception e){
e.printStackTrace();
}
}
return res;
}

public long queryGetCountAll(String sql){
if (driver == null) init();
long res = 0L;
try {
st = conn.createStatement();

st.setFetchSize(50);
rs = st.executeQuery(sql);

while (rs.next()) {
PrintPretty.println(CodeLineNumber.getLineNumber() + " a row was returned in queryGetCountAll().");

res = rs.getLong(1);
}

rs.close();

st.close();
conn.close();
disconnect();
} catch (SQLException e) {
e.printStackTrace();
} finally {
try {
rs.close();
st.close();
conn.close();
disconnect();
} catch (Exception e){
e.printStackTrace();
}
}
return res;
}

public boolean query(String sql){
if (driver == null) init();
boolean res = false;
try {
st = conn.createStatement();

st.setFetchSize(50);
res = st.execute(sql);

st.close();
conn.close();
disconnect();
} catch (SQLException e) {
e.printStackTrace();
} finally {
try {
st.close();
conn.close();
disconnect();
} catch (Exception e){
e.printStackTrace();
}
}
return res;
}

public String queryForStr(String sql){
if (driver == null) init();
String res = null;
try {
st = conn.createStatement();

st.setFetchSize(50);
rs = st.executeQuery(sql);

while (rs.next()) {
PrintPretty.println(CodeLineNumber.getLineNumber() + " a row was returned in queryForStr().");

res = rs.getString(1);
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

public int queryForNumber(String sql){
if (driver == null) init();
int res = 0;
try {
st = conn.createStatement();

st.setFetchSize(50);
rs = st.executeQuery(sql);

while (rs.next()) {
PrintPretty.println(CodeLineNumber.getLineNumber() + " a row was returned in queryForStr().");

res = rs.getInt(1);
}
rs.close();
st.close();

} catch (SQLException e) {
e.printStackTrace();
} finally {
try {
rs.close();
st.close();

} catch (Exception e){
e.printStackTrace();
}
}
return res;
}

public ResultSet queryForWholeResSet(String sql){
if (driver == null) init();
ResultSet res = null;
st = null;
try {
st = conn.createStatement();

st.setFetchSize(50);
rs = st.executeQuery(sql);




res = rs;




} catch (SQLException e) {
e.printStackTrace();
} finally {
try {



} catch (Exception e){
e.printStackTrace();
}
}
return res;
}


public List<Object> queryForColumnValues(String sql, String repeatColumnName_ToCheck){
if (driver == null) init();
ResultSet res = null;
st = null;
List list = new ArrayList();

try {
st = conn.createStatement();

st.setFetchSize(50);
rs = st.executeQuery(sql);
if (rs.getMetaData().getColumnName(1).equals(repeatColumnName_ToCheck)) {
while (rs.next()) {
list.add(rs.getObject(1));
}
} else {
throw new Exception("repeatColumnName_ToCheck = '"+ repeatColumnName_ToCheck +"' doesn't match requested sql: '"+ sql +"'.");
}

res = rs;




} catch (SQLException e) {
e.printStackTrace();
} catch (Exception e) {
e.printStackTrace();
} finally {
try {



} catch (Exception e){
e.printStackTrace();
}
}
return list;
}



public void readLargeQueryInChunksJdbcWay(String originalQuery, int fetchCount, ConsumerWithException<ResultSet, SQLException> consumer) throws SQLException {

boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}
try (Statement statement = conn.createStatement()) {
statement.setFetchSize(fetchCount);
ResultSet rs = statement.executeQuery(originalQuery);
while (rs.next()) {
consumer.accept(rs);
}
} finally {
if (originalAutoCommit) {
conn.setAutoCommit(true);
}
}
}
@FunctionalInterface
public interface ConsumerWithException<T, E extends Exception> {
void accept(T t) throws E;
}

public List<Map<String, Object>> resultAsListMap(String originalQuery, int fetchCount) throws SQLException {

st = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY);
ResultSet rs = st.executeQuery(originalQuery);

boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}

ResultSetMetaData md = rs.getMetaData();
int columns = md.getColumnCount();
List list = new ArrayList<Map<String, Object>>();

int currRowIndex = rs.getRow();
rs.beforeFirst();

try (Statement statement = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY)) {
statement.setFetchSize(fetchCount);
 rs = statement.executeQuery(originalQuery);

while (rs.next()) {
HashMap<String, Object> row = new LinkedHashMap<>(columns);
HashMap<Long, Object> row2 = new LinkedHashMap<>(columns);
short[] mas = null;
for (int i = 1; i <= columns; ++i) {
row.put(md.getColumnName(i), rs.getString(i));
}
list.add(row);
}
rs.absolute(currRowIndex);

} finally {
if (originalAutoCommit) {
conn.setAutoCommit(true);
}
}

return list;
}

public LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> resultAsMapMap(String originalQuery, int fetchCount) throws SQLException {

st = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY);
ResultSet rs = st.executeQuery(originalQuery);
boolean isOneTimeActionDone = false;
LinkedHashMap<String, Object> row = null;
LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> row2 = new LinkedHashMap<>();

boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}

ResultSetMetaData md = rs.getMetaData();
int columns = md.getColumnCount();
List list = new ArrayList<Map<String, Object>>();

int currRowIndex = rs.getRow();
rs.beforeFirst();
rs.close();
st.close();
rs = null;
st = null;

try (Statement statement = conn.createStatement(ResultSet.FETCH_FORWARD, ResultSet.CONCUR_READ_ONLY)) {
statement.setFetchSize(fetchCount);
 rs = statement.executeQuery(originalQuery);


while (rs.next()) {
if (!isOneTimeActionDone) row = new LinkedHashMap<>(columns);

short[] mas = null;
LinkedHashMap<Integer, short[]> element2 = new LinkedHashMap<>();
for (int i = 1; i <= columns; ++i) {
if (!isOneTimeActionDone) {
if (rs.getObject(i) != null) {
if (i == 1) { row.put(md.getColumnName(i), (Long) rs.getLong(i));
PrintPretty.println("class '"+ this.getClass().getName() +"' "+ CodeLineNumber.getLineNumber() +" TODO_"+"(i+1)" +" REVIEWME!!!!!!!!!!!!!"); row.put("TODO_"+"i+1", null);
} else row.put(md.getColumnName(i), (short[]) rs.getArray(i).getArray());
} else row.put(md.getColumnName(i), null);
}
if (i > 1) {
if (rs.getArray(i) != null){
mas = (short[])rs.getArray(i).getArray();

element2.put(i, mas);
}

}
}
row2.put(rs.getLong(1), element2);

if (!isOneTimeActionDone) {
Numerator.columnNamesFirstRowStaticHM = row;
isOneTimeActionDone = true;
}
}
rs.absolute(currRowIndex);
} finally {
if (originalAutoCommit) {
conn.setAutoCommit(true);
}
rs.close();
rs = null;
}

return row2;
}

public LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> callMe(String originalQuery, int fetchCount) {

ResultSet rs0 = null;
try {
st = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY);
rs0 = st.executeQuery(originalQuery);
} catch (SQLException e) {
e.printStackTrace();
}
final boolean[] isOneTimeActionDone = {false};
final LinkedHashMap<String, Object>[] row = new LinkedHashMap[]{null};
LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> row2 = new LinkedHashMap<>();







ResultSetMetaData md = null;
int columns = 1;
int currRowIndex = 1;
try {
md = rs0.getMetaData();
columns = md.getColumnCount();
currRowIndex = rs0.getRow();
rs0.beforeFirst();
} catch (SQLException e) {
e.printStackTrace();
}

List list = new ArrayList<Map<String, Object>>();

;

int finalColumns = columns;
ResultSetMetaData finalMd = md;
ConsumerWithException<ResultSet, SQLException> consumer = rs -> {



if (!isOneTimeActionDone[0]) row[0] = new LinkedHashMap<>(finalColumns);

short[] mas = null;
LinkedHashMap<Integer, short[]> element2 = new LinkedHashMap<>();
for (int i = 1; i <= finalColumns; ++i) {
if (!isOneTimeActionDone[0]) {
if (rs.getObject(i) != null) {
if (i == 1) { row[0].put(finalMd.getColumnName(i), (Long) rs.getLong(i));
PrintPretty.println("class '"+ this.getClass().getName() +"' "+ CodeLineNumber.getLineNumber() +" TODO_"+"(i+1)" +" REVIEWME!!!!!!!!!!!!!"); row[0].put("TODO_"+"i+1", null);
} else row[0].put(finalMd.getColumnName(i), (short[]) rs.getArray(i).getArray());
} else row[0].put(finalMd.getColumnName(i), null);
}
if (i > 1) {
if (rs.getArray(i) != null){
mas = (short[])rs.getArray(i).getArray();

element2.put(i, mas);
}

}
}
row2.put(rs.getLong(1), element2);

if (!isOneTimeActionDone[0]) {
Numerator.columnNamesFirstRowStaticHM = row[0];
isOneTimeActionDone[0] = true;
}
};

try {
readLargeQueryInChunksJdbcWay(conn, originalQuery, fetchCount, consumer);
} catch (SQLException e) {
e.printStackTrace();
}

return row2;
}

void readLargeQueryInChunksJdbcWay(Connection conn, String originalQuery, int fetchCount, ConsumerWithException<ResultSet, SQLException> consumer) throws SQLException {
boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}
try (Statement statement = conn.createStatement()) {
statement.setFetchSize(fetchCount);
ResultSet rs = statement.executeQuery(originalQuery);
while (rs.next()) {
consumer.accept(rs);
}
} finally {
if (originalAutoCommit) {
conn.setAutoCommit(true);
}
}
}
@FunctionalInterface
public interface ConsumerWithExceptionOrig<T, E extends Exception> {
void accept(T t) throws E;
}


public LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> resultAsMapMap2(String originalQuery, int numOfColumnsIn_fw_final_base_copy_Total, int fetchCount) throws SQLException {
boolean isOneTimeActionDone = true;
Statement st0 = null;
ResultSet rs0 = null;
ResultSetMetaData md0 = null;
int columns = 0;
if (!isOneTimeActionDone) {
 st0 = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY);
 rs0 = st0.executeQuery(originalQuery.replaceFirst("from ([A-Za-z0-9_])+ ", "from fw_final_base_copy "));


 md0 = rs0.getMetaData();




rs0.beforeFirst();




}



PreparedStatement pStmt = conn.prepareStatement(
originalQuery,
ResultSet.TYPE_FORWARD_ONLY,
ResultSet.CONCUR_READ_ONLY,
ResultSet.FETCH_FORWARD);
pStmt.setFetchSize(fetchCount);




LinkedHashMap<String, Object> row = null;
LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> row2 = new LinkedHashMap<>();

boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}

ResultSet rs = pStmt.executeQuery();


if (!isOneTimeActionDone) columns = md0.getColumnCount();
else columns = numOfColumnsIn_fw_final_base_copy_Total;
List list = new ArrayList<Map<String, Object>>();






while (rs.next()) {

if (!isOneTimeActionDone) {rs0.next(); row = new LinkedHashMap<>(columns);}

short[] mas = null;
LinkedHashMap<Integer, short[]> element2 = new LinkedHashMap<>();
for (int i = 1; i <= columns; ++i) {
if (!isOneTimeActionDone) {
if (rs0.getObject(i) != null) {
if (i == 1) {
row.put(md0.getColumnName(i), (Long) rs0.getLong(i));
PrintPretty.println("class '"+ this.getClass().getName() +"' "+ CodeLineNumber.getLineNumber() +" TODO_"+"(i+1)" +" REVIEWME!!!!!!!!!!!!!"); row.put("TODO_"+"i+1", null);
} else {
row.put(md0.getColumnName(i), (short[]) rs0.getArray(i).getArray());
}
} else {
row.put(md0.getColumnName(i), null);
}
}
if (i > 1) {
if (rs.getArray(i) != null){
mas = (short[])rs.getArray(i).getArray();

element2.put(i, mas);
}

}
}
row2.put(rs.getLong(1), element2);

if (!isOneTimeActionDone) {
Numerator.columnNamesFirstRowStaticHM = row;
isOneTimeActionDone = true;
rs0.close();
st0.close();
rs0 = null;
st0 = null;
System.gc();
}
}


if (originalAutoCommit) {
conn.setAutoCommit(true);
}
rs.close();
rs = null;


return row2;
}


public LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> resultAsMapMap22(String originalQuery, int fetchCount) throws SQLException {

Statement st0 = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY);
ResultSet rs0 = st0.executeQuery(originalQuery.replaceFirst("from ([A-Za-z0-9_])+ ", "from fw_final_base_copy "));

ResultSetMetaData md0 = rs0.getMetaData();




rs0.beforeFirst();








PreparedStatement pStmt = conn.prepareStatement(
originalQuery,
ResultSet.TYPE_FORWARD_ONLY,
ResultSet.CONCUR_READ_ONLY,
ResultSet.FETCH_FORWARD);
pStmt.setFetchSize(fetchCount);



boolean isOneTimeActionDone = false;
LinkedHashMap<String, Object> row = null;
LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> row2 = new LinkedHashMap<>();

boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}//

ResultSet rs = pStmt.executeQuery();


int columns = md0.getColumnCount();
List list = new ArrayList<Map<String, Object>>();






while (rs.next()) {

if (!isOneTimeActionDone) {rs0.next(); row = new LinkedHashMap<>(columns);}

short[] mas = null;
LinkedHashMap<Integer, short[]> element2 = new LinkedHashMap<>();
for (int i = 1; i <= columns; ++i) {
if (!isOneTimeActionDone) {
if (rs0.getObject(i) != null) {
if (i == 1) {
row.put(md0.getColumnName(i), (Long) rs0.getLong(i));
PrintPretty.println("class '"+ this.getClass().getName() +"' "+ CodeLineNumber.getLineNumber() +" TODO_"+"(i+1)" +" REVIEWME!!!!!!!!!!!!!"); row.put("TODO_"+"i+1", null);
} else {
row.put(md0.getColumnName(i), (short[]) rs0.getArray(i).getArray());
}
} else {
row.put(md0.getColumnName(i), null);
}
}
if (i > 1) {
if (rs.getArray(i) != null){
mas = (short[])rs.getArray(i).getArray();

element2.put(i, mas);
}

}
}
row2.put(rs.getLong(1), element2);

if (!isOneTimeActionDone) {
Numerator.columnNamesFirstRowStaticHM = row;
isOneTimeActionDone = true;
rs0.close();
st0.close();
rs0 = null;
st0 = null;
System.gc();
}
}


if (originalAutoCommit) {
conn.setAutoCommit(true);
}
rs.close();
rs = null;


return row2;
}


public LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> resultAsMapMap3(String originalQuery, int fetchCount) throws SQLException {

String createFunction = "CREATE OR REPLACE FUNCTION getCombos(mycurs OUT refcursor) "
+ " RETURNS refcursor "
+ " AS $$ "
+ " BEGIN "
+ "     OPEN mycurs FOR "+ originalQuery +" "
+ " END; "
+ " $$ "
+ " LANGUAGE plpgsql";

String runFunction = "{? = call getCombos()}";

Statement st0 = conn.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY);
ResultSet rs0 = st0.executeQuery(originalQuery.replaceFirst("from ([A-Za-z0-9_])+ ", "from fw_final_base_copy "));

ResultSetMetaData md0 = rs0.getMetaData();

rs0.beforeFirst();


boolean isOneTimeActionDone = false;
LinkedHashMap<String, Object> row = null;
LinkedHashMap<Long, LinkedHashMap<Integer, short[]>> row2 = new LinkedHashMap<>();

boolean originalAutoCommit = conn.getAutoCommit();
if (originalAutoCommit) {
conn.setAutoCommit(false);
}

Statement statement = conn.createStatement();
statement.setFetchSize(fetchCount);
CallableStatement cs = conn.prepareCall(runFunction);
cs.setFetchSize(fetchCount);

statement.execute(createFunction);
cs.registerOutParameter(1, Types.REF_CURSOR);
cs.execute();
ResultSet rs = (ResultSet) cs.getObject(1);

int columns = md0.getColumnCount();

while (rs.next()) {

if (!isOneTimeActionDone) {rs0.next(); row = new LinkedHashMap<>(columns);}

short[] mas = null;
LinkedHashMap<Integer, short[]> element2 = new LinkedHashMap<>();
for (int i = 1; i <= columns; ++i) {
if (!isOneTimeActionDone) {
if (rs0.getObject(i) != null) {
if (i == 1) {
row.put(md0.getColumnName(i), (Long) rs0.getLong(i));
PrintPretty.println("class '"+ this.getClass().getName() +"' "+ CodeLineNumber.getLineNumber() +" TODO_"+"(i+1)" +" REVIEWME!!!!!!!!!!!!!"); row.put("TODO_"+"i+1", null);
} else {
row.put(md0.getColumnName(i), (short[]) rs0.getArray(i).getArray());
}
} else {
row.put(md0.getColumnName(i), null);
}
}
if (i > 1) {
if (rs.getArray(i) != null){
mas = (short[])rs.getArray(i).getArray();

element2.put(i, mas);
}
}
}
row2.put(rs.getLong(1), element2);
if (!isOneTimeActionDone) {
Numerator.columnNamesFirstRowStaticHM = row;
isOneTimeActionDone = true;
md0 = null;
rs0.close();
st0.close();
rs0 = null;
st0 = null;
System.gc();
}
}

if (originalAutoCommit) {
conn.setAutoCommit(true);
}
rs.close();
rs = null;
if (st != null) {
st.clearBatch();
st.close();
}
if (statement != null) {statement.clearBatch(); statement.close();}
return row2;
}
}
