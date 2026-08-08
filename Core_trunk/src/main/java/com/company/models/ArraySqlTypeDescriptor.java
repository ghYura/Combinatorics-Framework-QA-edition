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

package com.company.models;

import org.hibernate.type.SqlTypes;
import org.hibernate.type.descriptor.ValueBinder;
import org.hibernate.type.descriptor.ValueExtractor;
import org.hibernate.type.descriptor.WrapperOptions;
import org.hibernate.type.descriptor.java.JavaType;
import org.hibernate.type.descriptor.jdbc.JdbcType;

import java.sql.*;


public class ArraySqlTypeDescriptor implements JdbcType {

public static final ArraySqlTypeDescriptor INSTANCE = new ArraySqlTypeDescriptor();

@Override
public int getJdbcTypeCode() {
return SqlTypes.ARRAY;
}

@Override
public <X> ValueBinder<X> getBinder(JavaType<X> javaType) {
return new ValueBinder<X>() {
@Override
public void bind(PreparedStatement st, X value, int index, WrapperOptions options) throws SQLException {
if (value == null) {
st.setNull(index, Types.ARRAY);
} else {
AbstractArrayTypeDescriptor<X> castedJavaType = (AbstractArrayTypeDescriptor<X>) javaType;
Object[] unwrapped = castedJavaType.unwrap(value, Object[].class, options);

Array array = st.getConnection().createArrayOf(
castedJavaType.getSqlArrayType(),
unwrapped
);
st.setArray(index, array);
}
}

@Override
public void bind(CallableStatement st, X value, String name, WrapperOptions options) throws SQLException {
throw new UnsupportedOperationException("Binding by name is not supported.");
}
};
}

@Override
public <X> ValueExtractor<X> getExtractor(JavaType<X> javaType) {
return new ValueExtractor<X>() {


@Override
public X extract(ResultSet resultSet, int i, WrapperOptions wrapperOptions) throws SQLException {
Array sqlArray = resultSet.getArray(i);
return (sqlArray == null) ? null : javaType.wrap(sqlArray, wrapperOptions);
}


@Override
public X extract(CallableStatement callableStatement, int i, WrapperOptions wrapperOptions) throws SQLException {
Array sqlArray = callableStatement.getArray(i);
return (sqlArray == null) ? null : javaType.wrap(sqlArray, wrapperOptions);
}


@Override
public X extract(CallableStatement callableStatement, String s, WrapperOptions wrapperOptions) throws SQLException {
Array sqlArray = callableStatement.getArray(s);
return (sqlArray == null) ? null : javaType.wrap(sqlArray, wrapperOptions);
}
};
}

@Override
public String getFriendlyName() {
return "ARRAY";
}
}
