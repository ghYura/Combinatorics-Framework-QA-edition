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
