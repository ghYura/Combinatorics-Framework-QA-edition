package com.company.models;

import org.hibernate.engine.spi.SharedSessionContractImplementor;
import org.hibernate.usertype.UserType;
import java.io.Serializable;
import java.sql.*;
import java.util.Objects;


public class ShortArrayType implements UserType<short[]> {

@Override
public int getSqlType() {
return Types.ARRAY;
}

@Override
public Class<short[]> returnedClass() {
return short[].class;
}

@Override
public boolean equals(short[] x, short[] y) {
return Objects.deepEquals(x, y);
}

@Override
public int hashCode(short[] x) {
return Objects.hashCode(x);
}

@Override
public short[] nullSafeGet(ResultSet rs, int position, SharedSessionContractImplementor session, Object owner) throws SQLException {
Array array = rs.getArray(position);
if (array == null) return null;



return ArrayUtil.unwrapArray((Object[]) array.getArray(), short[].class);
}

@Override
public void nullSafeSet(PreparedStatement st, short[] value, int index, SharedSessionContractImplementor session) throws SQLException {
if (value == null) {
st.setNull(index, Types.ARRAY);
} else {

Array array = st.getConnection().createArrayOf("smallint", (Object[]) ArrayUtil.wrapArray(value));
st.setArray(index, array);
}
}

@Override
public short[] deepCopy(short[] value) {
return value == null ? null : value.clone();
}

@Override
public boolean isMutable() {
return true;
}

@Override
public Serializable disassemble(short[] value) {
return (Serializable) deepCopy(value);
}

@Override
public short[] assemble(Serializable cached, Object owner) {
return (short[]) cached;
}

@Override
public short[] replace(short[] detached, short[] managed, Object owner) {
return deepCopy(detached);
}
}
