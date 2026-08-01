package com.company.models;

import org.hibernate.engine.spi.SharedSessionContractImplementor;
import org.hibernate.usertype.UserType;
import java.io.Serializable;
import java.sql.*;
import java.util.Objects;


public class IntArrayType implements UserType<int[]> {

@Override
public int getSqlType() {
return Types.ARRAY;
}

@Override
public Class<int[]> returnedClass() {
return int[].class;
}

@Override
public boolean equals(int[] x, int[] y) {
return Objects.deepEquals(x, y);
}

@Override
public int hashCode(int[] x) {
return Objects.hashCode(x);
}

@Override
public int[] nullSafeGet(ResultSet rs, int position, SharedSessionContractImplementor session, Object owner) throws SQLException {
Array array = rs.getArray(position);
if (array == null) return null;

Object raw = array.getArray();
if (raw instanceof int[]) return (int[]) raw;
return ArrayUtil.unwrapArray((Object[]) raw, int[].class);
}

@Override
public void nullSafeSet(PreparedStatement st, int[] value, int index, SharedSessionContractImplementor session) throws SQLException {
if (value == null) {
st.setNull(index, Types.ARRAY);
} else {

Array array = st.getConnection().createArrayOf("integer", (Object[]) ArrayUtil.wrapArray(value));
st.setArray(index, array);
}
}

@Override
public int[] deepCopy(int[] value) {
return value == null ? null : value.clone();
}

@Override
public boolean isMutable() {
return true;
}

@Override
public Serializable disassemble(int[] value) {
return (Serializable) deepCopy(value);
}

@Override
public int[] assemble(Serializable cached, Object owner) {
return deepCopy((int[]) cached);
}

@Override
public int[] replace(int[] detached, int[] managed, Object owner) {
return deepCopy(detached);
}
}
