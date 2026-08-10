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

import java.sql.*;

import static com.company.Main.*;
import static com.company.ReaderConfig.*;

public class QueryToDBpostgres {
Driver driver = new org.postgresql.Driver();
Connection conn = null;
Statement st = null;
ResultSet rs = null;
boolean defaultInit = true;
String host;
int    port;
String usr;
String pswrd;

public QueryToDBpostgres(){
init();
    }


public QueryToDBpostgres(String host, int port, String usr, String pswrd) {
defaultInit = false;
this.host = host;
this.port = port;
this.usr = usr;
this.pswrd = pswrd;
init(host, port, usr, pswrd);
}


public void init(String host, int port, String usr, String pswrd){
Driver driver = new org.postgresql.Driver();

String url = "jdbc:postgresql://"+host+":"+port+"/postgres";


try {
DriverManager.registerDriver(driver);
conn = DriverManager.getConnection(url, usr, pswrd);

} catch (SQLException e) {
e.printStackTrace();
try {
conn.close();
} catch (SQLException e1) {
e1.printStackTrace();
}
}
}

public void init(){
Driver driver = new org.postgresql.Driver();

String url = "jdbc:postgresql://"+cfg().dbHost()+":"+cfg().dbPort()+"/postgres";
String user = cfg().dbUser();
String password = cfg().dbPassword();


try {
DriverManager.registerDriver(driver);
conn = DriverManager.getConnection(url, user, password);

} catch (SQLException e) {
e.printStackTrace();
try {
conn.close();
} catch (SQLException e1) {
e1.printStackTrace();
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
if (driver == null) {if (defaultInit) init(); else init(host, port, usr, pswrd);}
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
if (driver == null) {if (defaultInit) init(); else init(host, port, usr, pswrd);}
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
if (driver == null) {if (defaultInit) init(); else init(host, port, usr, pswrd);}
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
if (driver == null) {if (defaultInit) init(); else init(host, port, usr, pswrd);}
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
}
