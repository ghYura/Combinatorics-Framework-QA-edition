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
